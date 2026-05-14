import os
import asyncio
import logging
from pathlib import Path

import discord
from discord.ext import commands

# ── Logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("bot")

# ── Configuración ─────────────────────────────────────────────────────────────
TOKEN = os.environ["DISCORD_TOKEN"]

INTENTS = discord.Intents.default()
INTENTS.message_content = True
INTENTS.members = True
INTENTS.reactions = True

COGS_DIR = Path(__file__).parent / "cogs"


# ── Bot ───────────────────────────────────────────────────────────────────────
class Bot(commands.Bot):
    def __init__(self):
        super().__init__(
            command_prefix="!",
            intents=INTENTS,
            help_command=None,
            case_insensitive=True,
        )

    async def setup_hook(self):
        await self._load_cogs()
        await self.tree.sync()
        log.info("Slash commands sincronizados globalmente.")

    async def _load_cogs(self):
        for path in sorted(COGS_DIR.glob("*.py")):
            if path.stem.startswith("_"):
                continue
            module = f"cogs.{path.stem}"
            try:
                await self.load_extension(module)
                log.info(f"✅ Cog cargado: {module}")
            except Exception as e:
                log.error(f"❌ Error al cargar {module}: {e}", exc_info=True)

    async def on_ready(self):
        activity = discord.Activity(
            type=discord.ActivityType.watching,
            name=f"{len(self.guilds)} servidores"
        )
        await self.change_presence(status=discord.Status.online, activity=activity)
        log.info(f"Bot listo — conectado como {self.user} (ID: {self.user.id})")
        log.info(f"Servidores: {len(self.guilds)}")

    async def on_command_error(self, ctx, error):
        if isinstance(error, commands.CommandNotFound):
            return
        log.error(f"Error en comando '{ctx.command}': {error}", exc_info=error)


async def main():
    async with Bot() as bot:
        await bot.start(TOKEN)


if __name__ == "__main__":
    asyncio.run(main())
