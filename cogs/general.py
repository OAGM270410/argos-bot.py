import time

import discord
from discord import app_commands
from discord.ext import commands

from database import db


class General(commands.Cog):
    """Comandos generales de utilidad."""

    def __init__(self, bot):
        self.bot = bot
        self.embed_color = 0x640f48

    # ── Slash Commands ─────────────────────────────────────────────────────────

    @app_commands.command(name="ping", description="Muestra la latencia del bot")
    async def ping(self, interaction: discord.Interaction):
        latencia = round(self.bot.latency * 1000)
        embed = discord.Embed(
            title="🏓 Pong!",
            description=f"Latencia: **{latencia}ms**",
            color=self.embed_color,
        )
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="info", description="Información sobre el bot")
    async def info(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title=f"ℹ️ {self.bot.user.name}",
            color=self.embed_color,
            timestamp=discord.utils.utcnow(),
        )
        embed.add_field(name="Servidores", value=str(len(self.bot.guilds)), inline=True)
        embed.add_field(name="Latencia", value=f"{round(self.bot.latency * 1000)}ms", inline=True)
        embed.add_field(name="Cogs cargados", value=str(len(self.bot.cogs)), inline=True)
        embed.set_thumbnail(url=self.bot.user.display_avatar.url)
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="config_set", description="Guarda un valor de configuración del servidor")
    @app_commands.describe(clave="Nombre de la configuración", valor="Valor a guardar")
    @app_commands.checks.has_permissions(administrator=True)
    async def config_set(self, interaction: discord.Interaction, clave: str, valor: str):
        db.set_val(interaction.guild.id, clave, valor)
        await interaction.response.send_message(
            f"✅ Configuración guardada: `{clave}` = `{valor}`", ephemeral=True
        )

    @app_commands.command(name="config_get", description="Muestra un valor de configuración del servidor")
    @app_commands.describe(clave="Nombre de la configuración")
    @app_commands.checks.has_permissions(administrator=True)
    async def config_get(self, interaction: discord.Interaction, clave: str):
        valor = db.get_val(interaction.guild.id, clave)
        if valor is None:
            await interaction.response.send_message(f"❌ No existe configuración para `{clave}`.", ephemeral=True)
        else:
            await interaction.response.send_message(f"`{clave}` = `{valor}`", ephemeral=True)

    @app_commands.command(name="config_list", description="Lista todas las configuraciones del servidor")
    @app_commands.checks.has_permissions(administrator=True)
    async def config_list(self, interaction: discord.Interaction):
        config = db.get_all(interaction.guild.id)
        if not config:
            return await interaction.response.send_message("No hay configuraciones guardadas.", ephemeral=True)

        embed = discord.Embed(title="⚙️ Configuración del servidor", color=self.embed_color)
        for k, v in config.items():
            embed.add_field(name=k, value=f"`{v}`", inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot):
    await bot.add_cog(General(bot))
