import random
import discord
from discord.ext import commands

class Cerebro(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    # =====================================
    # COMANDO FLEXIBLE: !cerebro
    # =====================================
    @commands.command(name="cerebro")
    async def cerebro(self, ctx):

        porcentaje = random.randint(1, 100)

        respuestas = [
            f"🧠 Tu cerebro funciona al **{porcentaje}%**.",
            f"🤖 Nivel cerebral detectado: **{porcentaje}%**.",
            f"📊 Inteligencia calculada: **{porcentaje}%**.",
            f"⚡ Poder mental encontrado: **{porcentaje}%**.",
            f"🧪 Resultado del análisis cerebral: **{porcentaje}%**."
        ]

        embed = discord.Embed(
            description=random.choice(respuestas),
            color=0x1536BA
        )

        await ctx.send(embed=embed)

    # =====================================
    # DETECTOR CON ESPACIOS Y MAYÚSCULAS
    # =====================================
    @commands.Cog.listener()
    async def on_message(self, message):

        if message.author.bot:
            return

        contenido = message.content.lower().replace(" ", "")

        # Acepta:
        # !cerebro
        # ! Cerebro
        # !   CeReBrO
        # etc
        if contenido == "!cerebro":

            porcentaje = random.randint(1, 100)

            respuestas = [
                f"🧠 Tu cerebro funciona al **{porcentaje}%**.",
                f"🤖 Nivel cerebral detectado: **{porcentaje}%**.",
                f"📊 Inteligencia calculada: **{porcentaje}%**.",
                f"⚡ Poder mental encontrado: **{porcentaje}%**.",
                f"🧪 Resultado del análisis cerebral: **{porcentaje}%**."
            ]

            embed = discord.Embed(
                description=random.choice(respuestas),
                color=0x640f48
            )

            await message.channel.send(embed=embed)

async def setup(bot):
    await bot.add_cog(Cerebro(bot))