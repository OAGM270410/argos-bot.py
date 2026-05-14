import sqlite3
import re
import asyncio
import aiosqlite
import os
import time
import struct
import lz4.frame
import logging
import orjson
import hmac
import hashlib
import aiofiles
from collections import deque                          # ✅ BUG 1 CORREGIDO: faltaba este import
from dataclasses import dataclass, field, asdict
from datetime import timedelta
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple
from cachetools import TTLCache
from fastapi import FastAPI, HTTPException, Request, Depends, status
from fastapi.security import APIKeyHeader
from contextlib import asynccontextmanager

# ══════════════════════════════════════════════════════════════
#  ANTIGUA DATABASE — API que usan los cogs (no tocar)
# ══════════════════════════════════════════════════════════════

DB_PATH = Path(__file__).parent / "bot_data.db"

def _connect():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def _ensure_table():
    with _connect() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS guild_settings (
                guild_id   INTEGER NOT NULL,
                key        TEXT    NOT NULL,
                value      TEXT    NOT NULL,
                PRIMARY KEY (guild_id, key)
            )
        """)
        conn.commit()

_ensure_table()


class Database:
    def get_val(self, guild_id: int, key: str, default=None):
        with _connect() as conn:
            row = conn.execute(
                "SELECT value FROM guild_settings WHERE guild_id = ? AND key = ?",
                (guild_id, key)
            ).fetchone()
        return row["value"] if row else default

    def set_val(self, guild_id: int, key: str, value):
        with _connect() as conn:
            conn.execute(
                """
                INSERT INTO guild_settings (guild_id, key, value)
                VALUES (?, ?, ?)
                ON CONFLICT(guild_id, key) DO UPDATE SET value = excluded.value
                """,
                (guild_id, key, str(value))
            )
            conn.commit()

    def del_val(self, guild_id: int, key: str):
        with _connect() as conn:
            conn.execute(
                "DELETE FROM guild_settings WHERE guild_id = ? AND key = ?",
                (guild_id, key)
            )
            conn.commit()

    def get_all(self, guild_id: int) -> dict:
        with _connect() as conn:
            rows = conn.execute(
                "SELECT key, value FROM guild_settings WHERE guild_id = ?",
                (guild_id,)
            ).fetchall()
        return {r["key"]: r["value"] for r in rows}


def parse_time(text: str) -> timedelta | None:
    """
    Convierte strings como '30s', '5m', '2h', '1d' en timedelta.
    También acepta combinaciones: '1h30m', '2d12h'.
    """
    pattern = r"(?:(\d+)d)?(?:(\d+)h)?(?:(\d+)m)?(?:(\d+)s)?"
    match = re.fullmatch(pattern, text.strip().lower())
    if not match or not any(match.groups()):
        return None
    days    = int(match.group(1) or 0)
    hours   = int(match.group(2) or 0)
    minutes = int(match.group(3) or 0)
    seconds = int(match.group(4) or 0)
    td = timedelta(days=days, hours=hours, minutes=minutes, seconds=seconds)
    return td if td.total_seconds() > 0 else None


db = Database()


# ══════════════════════════════════════════════════════════════
#  NUEVA DATABASE — TITAN V7 (alto rendimiento)
# ══════════════════════════════════════════════════════════════

# --- CONFIGURACIÓN DE GRADO ENTERPRISE ---
SECRET_KEY = os.getenv("TITAN_SECRET", "32-chars-of-extreme-entropy-here-!!").encode()
DATA_DIR = os.getenv("TITAN_DATA_DIR", "./titan_v7_data")
SHARD_COUNT = int(os.getenv("SHARD_COUNT", "16"))
MAX_BATCH_SIZE = 1000 # Para throughput masivo
os.makedirs(DATA_DIR, exist_ok=True)

logging.basicConfig(level=logging.INFO, format='{"ts": "%(asctime)s", "shard": "%(name)s", "lvl": "%(levelname)s", "msg": "%(message)s"}')
logger = logging.getLogger("TITAN-CORE")

@dataclass(frozen=True)
class TitanEvent:
    guild_id: int
    type: str
    data: Dict[str, Any] = field(default_factory=dict)
    user_id: Optional[int] = None
    amount: int = 0
    ts: int = field(default_factory=lambda: int(time.time() * 1000))
    tx_id: str = field(default_factory=lambda: os.urandom(16).hex())

# --- OBSERVABILIDAD Y MÉTRICAS ---
class Metrics:
    def __init__(self):
        self.ops = 0
        self.errors = 0
        self.latency_ms = deque(maxlen=100)            # ✅ BUG 1 CORREGIDO: deque ahora importado
        self.queue_depth = 0

# --- CIRCUIT BREAKER ---
class CircuitBreaker:
    def __init__(self):
        self.state = "CLOSED" # CLOSED, OPEN, HALF-OPEN
        self.fail_count = 0
        self.threshold = 5

    def record_failure(self):
        self.fail_count += 1
        if self.fail_count >= self.threshold: self.state = "OPEN"

    def record_success(self):
        self.fail_count = 0
        self.state = "CLOSED"

# --- SHARD PROCESSOR (EL CORAZÓN) ---
class ShardProcessor:
    def __init__(self, shard_id: int):
        self.shard_id = shard_id
        self.db_path = f"{DATA_DIR}/shard_{shard_id}.db"
        self.queue = asyncio.Queue(maxsize=20000)
        self.metrics = Metrics()
        self.breaker = CircuitBreaker()
        self._db: Optional[aiosqlite.Connection] = None
        self._running = True

    async def bootstrap(self):
        self._db = await aiosqlite.connect(self.db_path)
        await self._db.executescript("""
            PRAGMA journal_mode=WAL;
            PRAGMA synchronous=NORMAL;
            PRAGMA mmap_size=536870912;

            CREATE TABLE IF NOT EXISTS state_meta (key TEXT PRIMARY KEY, val INTEGER);
            CREATE TABLE IF NOT EXISTS accounts (
                guild_id INTEGER, user_id INTEGER, balance INTEGER,
                PRIMARY KEY(guild_id, user_id)
            ) WITHOUT ROWID;
            CREATE TABLE IF NOT EXISTS idempotency (tx_hash TEXT PRIMARY KEY, ts INTEGER);
        """)
        asyncio.create_task(self._main_loop())
        logger.info(f"Shard {self.shard_id} initialized with high-performance PRAGMAs.")

    async def _execute_batch(self, batch: List[TitanEvent]):
        """Procesamiento por lotes atómicos (Dynamic Batching)."""
        start_time = time.perf_counter()

        # ✅ BUG 2 CORREGIDO: transacción con BEGIN/commit/rollback explícitos
        await self._db.execute("BEGIN IMMEDIATE")
        try:
            for ev in batch:
                # Idempotencia Robusta
                dedup = hashlib.blake2b(ev.tx_id.encode(), digest_size=16).hexdigest()
                res = await self._db.execute("INSERT OR IGNORE INTO idempotency VALUES (?,?)", (dedup, ev.ts))

                if res.rowcount > 0:
                    if ev.type == "ECON_TX":
                        await self._db.execute(
                            "INSERT INTO accounts VALUES (?,?,?) ON CONFLICT DO UPDATE SET balance=balance+?",
                            (ev.guild_id, ev.user_id, ev.amount, ev.amount)
                        )

            await self._db.commit()
            self.metrics.ops += len(batch)
            self.breaker.record_success()
        except Exception as e:
            await self._db.rollback()
            self.breaker.record_failure()
            logger.error(f"Batch failed on Shard {self.shard_id}: {e}")
            raise

        duration = (time.perf_counter() - start_time) * 1000
        self.metrics.latency_ms.append(duration)

    async def _main_loop(self):
        """Consumidor con drenaje dinámico de cola."""
        while self._running:
            try:
                # Esperar al primer evento
                ev = await asyncio.wait_for(self.queue.get(), timeout=1.0)
                batch = [ev]

                # Drenar el resto de la cola hasta MAX_BATCH_SIZE (Throughput Tuning)
                while len(batch) < MAX_BATCH_SIZE and not self.queue.empty():
                    batch.append(self.queue.get_nowait())

                await self._execute_batch(batch)

                for _ in batch: self.queue.task_done()
            except asyncio.TimeoutError:
                continue
            except Exception as e:
                await asyncio.sleep(1) # Backoff ante errores críticos

# --- API GATEWAY CON HARDENING ---
db_engine = [ShardProcessor(i) for i in range(SHARD_COUNT)]
api_key_header = APIKeyHeader(name="X-Titan-Auth")

@asynccontextmanager
async def lifespan(app: FastAPI):
    await asyncio.gather(*(s.bootstrap() for s in db_engine))
    yield
    for s in db_engine: s._running = False

app = FastAPI(lifespan=lifespan)

@app.post("/emit")
async def emit(ev: TitanEvent, auth: str = Depends(api_key_header)):
    # ✅ BUG 3 CORREGIDO: hmac.compare_digest evita timing attacks
    if not hmac.compare_digest(auth.encode(), SECRET_KEY):
        raise HTTPException(status_code=403)

    # Shard Dispatching
    shard = db_engine[ev.guild_id % SHARD_COUNT]

    # Circuit Breaker & Backpressure
    if shard.breaker.state == "OPEN":
        raise HTTPException(status_code=503, detail="Shard temporarily unavailable (Circuit Breaker OPEN)")

    if shard.queue.full():
        shard.breaker.record_failure() # Saturación cuenta como presión de falla
        raise HTTPException(status_code=429, detail="High backpressure on shard")

    # Ingestión
    await shard.queue.put(ev)
    shard.metrics.queue_depth = shard.queue.qsize()

    return {"tx_id": ev.tx_id, "shard": shard.shard_id}

@app.get("/metrics")
async def get_metrics():
    return {
        f"shard_{s.shard_id}": {
            "ops": s.metrics.ops,
            "q_depth": s.metrics.queue_depth,
            "p95_lat_ms": sorted(list(s.metrics.latency_ms))[int(len(s.metrics.latency_ms)*0.95)] if s.metrics.latency_ms else 0,
            "state": s.breaker.state
        } for s in db_engine
    }
