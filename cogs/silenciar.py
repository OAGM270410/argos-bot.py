import discord
from discord import app_commands
from discord.ext import commands
import re
from datetime import timedelta

EMBED_COLOR = 0x640f48


# =========================
# ⏱ PARSER DE TIEMPO FLEXIBLE
# =========================
def parse_time(text: str) -> int:
    text = text.lower().replace(" ", "")

    patterns = {
        "d": r"(\d+)(d|dia|dias|day|days)",
        "h": r"(\d+)(h|hr|hrs|hora|horas)",
        "m": r"(\d+)(m|min|mins|minuto|minutos)",
        "s": r"(\d+)(s|seg|segs|segundo|segundos)"
    }

    seconds = 0

    for unit, pattern in patterns.items():
        matches = re.findall(pattern, text)

        for match in matches:
            value = int(match[0])

            if unit == "d":
                seconds += value * 86400
            elif unit == "h":
                seconds += value * 3600
            elif unit == "m":
                seconds += value * 60
            elif unit == "s":
                seconds += value

    return seconds


# =========================
# 🔇 COG
# =========================
class SilenciarCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(
        name="silenciar",
        description="🔇 Silencia a un miembro"
    )
    async def silenciar(
        self,
        interaction: discord.Interaction,
        usuario: discord.Member,
        tiempo: str,
        motivo: str = "No se explicó un motivo."
    ):

        author = interaction.user
        guild = interaction.guild

        # ---------------- PERMISOS ----------------
        if not author.guild_permissions.moderate_members and not author.guild_permissions.administrator:
            return await interaction.response.send_message(
                "**❌ No tienes permisos.**",
                ephemeral=True
            )

        # ---------------- AUTO SILENCIO ----------------
        if author.id == usuario.id:
            return await interaction.response.send_message(
                "**❌ No puedes auto silenciarte.**",
                ephemeral=True
            )

        # ---------------- BOT ----------------
        if usuario.id == self.bot.user.id:
            return await interaction.response.send_message(
                "**❌ No puedes silenciar a Argos.**",
                ephemeral=True
            )

        # ---------------- JERARQUÍA MOD ----------------
        if usuario.top_role >= author.top_role and not author.guild_permissions.administrator:
            return await interaction.response.send_message(
                "**❌ No puedo sancionar este miembro.**",
                ephemeral=True
            )

        # ---------------- JERARQUÍA BOT ----------------
        if usuario.top_role >= guild.me.top_role:
            return await interaction.response.send_message(
                "**❌ No puedes silenciar a este miembro.**",
                ephemeral=True
            )

        # ---------------- TIEMPO ----------------
        seconds = parse_time(tiempo)

        if seconds <= 0:
            return await interaction.response.send_message(
                "**❌ Tiempo inválido.**",
                ephemeral=True
            )

        # máximo 30 días
        if seconds > 2592000:
            return await interaction.response.send_message(
                "**❌ El máximo de silencio es 30 días.**",
                ephemeral=True
            )

        # ---------------- TIMEOUT ----------------
        try:
            until = discord.utils.utcnow() + timedelta(seconds=seconds)

            await usuario.timeout(until, reason=motivo)

        except Exception:
            return await interaction.response.send_message(
                "**❌ No se pudo silenciar a este miembro.**",
                ephemeral=True
            )

        # ---------------- EMBED ----------------
        embed = discord.Embed(
            title="**Usuario silenciado. ✅**",
            description="Un usuario fue silenciado en el servidor.",
            color=EMBED_COLOR
        )

        embed.add_field(name="👤 Usuario:", value=usuario.mention, inline=False)
        embed.add_field(name="🧑‍⚖️ Responsable:", value=author.mention, inline=False)
        embed.add_field(name="📌 Motivo:", value=motivo, inline=False)

        embed.set_thumbnail(url=usuario.display_avatar.url)

        await interaction.response.send_message(embed=embed)


# =========================
# SETUP
# =========================
async def setup(bot: commands.Bot):
    await bot.add_cog(SilenciarCog(bot))