import discord
from discord.ext import commands


class Argos(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    # Con case_insensitive=True en el bot, !Argos / !ARGOS / !argos funcionan
    # sin necesidad de listar variantes manualmente en aliases.
    @commands.command(name="argos")
    async def argos(self, ctx: commands.Context):
        """Saludo del bot Argos."""
        embed = discord.Embed(
            description="👋 ¡Hola soy Argos, podría hablar más después!",
            color=0x1536BA,
        )
        await ctx.send(embed=embed)


async def setup(bot):
    await bot.add_cog(Argos(bot))
