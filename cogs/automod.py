import re
import unicodedata
from datetime import timedelta

import discord
import emoji as emoji_lib
from discord import app_commands
from discord.ext import commands

from database import db, parse_time


class AutoMod(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.embed_color = 0x1536BA
        self.skin_tones = {"\U0001F3FB", "\U0001F3FC", "\U0001F3FD", "\U0001F3FE", "\U0001F3FF"}
        self._cache_blacklist: dict[int, list[str]] = {}

    # ── Helpers ────────────────────────────────────────────────────────────────

    def _get_blacklist(self, guild_id: int) -> list[str]:
        if guild_id not in self._cache_blacklist:
            raw = db.get_val(guild_id, "emoji_blacklist", "")
            self._cache_blacklist[guild_id] = raw.split(",") if raw else []
        return self._cache_blacklist[guild_id]

    def _invalidate_cache(self, guild_id: int):
        self._cache_blacklist.pop(guild_id, None)

    def norm(self, t: str) -> str:
        return unicodedata.normalize("NFKC", t)

    def sin_tono(self, t: str) -> str:
        return "".join(c for c in t if c not in self.skin_tones)

    def extraer_identificadores(self, texto: str) -> list[str]:
        resultado = []
        resultado.extend(re.findall(r"<a?:[\w]+:(\d+)>", texto))
        texto_sin_custom = re.sub(r"<a?:[\w]+:\d+>", "", texto)
        for item in emoji_lib.emoji_list(texto_sin_custom):
            resultado.append(self.sin_tono(self.norm(item["emoji"])))
        return resultado

    def puede_sancionar(self, objetivo: discord.Member) -> bool:
        me = objetivo.guild.me
        if objetivo.id == objetivo.guild.owner_id:
            return False
        return me.top_role > objetivo.top_role and me.guild_permissions.moderate_members

    def es_protegido(self, member: discord.Member) -> bool:
        if member.bot or member.id == member.guild.owner_id:
            return True
        p = member.guild_permissions
        return any([p.administrator, p.moderate_members, p.manage_roles])

    # ── Listeners ──────────────────────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if not message.guild or message.author.bot or self.es_protegido(message.author):
            return

        blacklist = self._get_blacklist(message.guild.id)
        if not blacklist:
            return

        encontrados = self.extraer_identificadores(message.content)
        for e in encontrados:
            if e in blacklist:
                if self.puede_sancionar(message.author):
                    try:
                        await message.delete()
                        await self._aplicar_sancion(message.author, e, False)
                    except discord.Forbidden:
                        pass
                break

    @commands.Cog.listener()
    async def on_reaction_add(self, reaction: discord.Reaction, user: discord.Member):
        if user.bot or not reaction.message.guild or self.es_protegido(user):
            return

        blacklist = self._get_blacklist(reaction.message.guild.id)
        if not blacklist:
            return

        e_id = (
            str(reaction.emoji.id)
            if reaction.is_custom_emoji()
            else self.sin_tono(self.norm(str(reaction.emoji)))
        )

        if e_id in blacklist:
            if self.puede_sancionar(user):
                try:
                    await reaction.remove(user)
                    await self._aplicar_sancion(user, e_id, True)
                except discord.Forbidden:
                    pass

    # ── Sanción interna ────────────────────────────────────────────────────────

    async def _aplicar_sancion(self, member: discord.Member, emoji_det: str, es_reaccion: bool):
        duracion_seg = int(db.get_val(member.guild.id, "timeout_time", 3600))
        canal_id = db.get_val(member.guild.id, "sanciones_channel")

        try:
            await member.timeout(
                timedelta(seconds=duracion_seg),
                reason="AutoMod: Emoji prohibido"
            )

            if canal_id:
                canal = self.bot.get_channel(int(canal_id))
                if canal:
                    accion = "reaccionó con" if es_reaccion else "usó en un mensaje"
                    embed = discord.Embed(
                        title="🛡️ Moderación Automática",
                        description=f"{member.mention} ha sido silenciado.",
                        color=self.embed_color,
                        timestamp=discord.utils.utcnow(),
                    )
                    embed.add_field(name="Motivo", value=f"Emoji prohibido ({accion})", inline=True)
                    embed.add_field(name="Duración", value=f"{duracion_seg // 60}m", inline=True)
                    embed.set_footer(text=f"ID del Usuario: {member.id}")
                    await canal.send(embed=embed)
        except Exception as e:
            print(f"❌ Error al aplicar sanción: {e}")

    # ── Slash Commands ─────────────────────────────────────────────────────────

    @app_commands.command(name="automod_setup", description="Configura los emojis prohibidos y el canal de sanciones")
    @app_commands.describe(
        emojis="Emojis a prohibir (puedes pegar varios)",
        tiempo="Duración del timeout (ej: 30m, 1h, 1d)",
        canal="Canal donde se reportan las sanciones",
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def automod_setup(
        self,
        interaction: discord.Interaction,
        emojis: str,
        tiempo: str,
        canal: discord.TextChannel,
    ):
        td = parse_time(tiempo)
        if not td:
            return await interaction.response.send_message(
                "❌ Formato de tiempo inválido. Ejemplos: `30s`, `5m`, `1h`, `2d`", ephemeral=True
            )

        ids_prohibidos = self.extraer_identificadores(emojis)
        if not ids_prohibidos:
            return await interaction.response.send_message(
                "❌ No detecté emojis válidos en tu mensaje.", ephemeral=True
            )

        db.set_val(interaction.guild.id, "emoji_blacklist", ",".join(ids_prohibidos))
        db.set_val(interaction.guild.id, "sanciones_channel", canal.id)
        db.set_val(interaction.guild.id, "timeout_time", int(td.total_seconds()))
        self._invalidate_cache(interaction.guild.id)

        await interaction.response.send_message(
            f"✅ **AutoMod actualizado**\n"
            f"🚫 Emojis prohibidos: **{len(ids_prohibidos)}**\n"
            f"⏳ Duración del timeout: **{tiempo}**\n"
            f"📢 Canal de sanciones: {canal.mention}",
            ephemeral=True,
        )

    @app_commands.command(name="automod_info", description="Muestra la configuración actual de AutoMod")
    @app_commands.checks.has_permissions(administrator=True)
    async def automod_info(self, interaction: discord.Interaction):
        blacklist = self._get_blacklist(interaction.guild.id)
        canal_id = db.get_val(interaction.guild.id, "sanciones_channel")
        duracion = int(db.get_val(interaction.guild.id, "timeout_time", 3600))
        canal_mention = f"<#{canal_id}>" if canal_id else "No configurado"

        embed = discord.Embed(title="🛡️ Configuración de AutoMod", color=self.embed_color)
        embed.add_field(name="Emojis prohibidos", value=str(len(blacklist)) if blacklist else "Ninguno", inline=True)
        embed.add_field(name="Timeout", value=f"{duracion // 60}m", inline=True)
        embed.add_field(name="Canal de sanciones", value=canal_mention, inline=True)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="automod_reset", description="Desactiva el AutoMod en este servidor")
    @app_commands.checks.has_permissions(administrator=True)
    async def automod_reset(self, interaction: discord.Interaction):
        db.del_val(interaction.guild.id, "emoji_blacklist")
        db.del_val(interaction.guild.id, "sanciones_channel")
        db.del_val(interaction.guild.id, "timeout_time")
        self._invalidate_cache(interaction.guild.id)
        await interaction.response.send_message("✅ AutoMod desactivado y configuración eliminada.", ephemeral=True)


async def setup(bot):
    await bot.add_cog(AutoMod(bot))
