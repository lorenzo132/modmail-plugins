import discord
from discord.ext import commands
from core import checks
from core.checks import PermissionLevel

class BotLogout(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @checks.has_permissions(PermissionLevel.OWNER)
    @commands.command()
    async def botlogout(self, _):
        """Logs out the bot"""
        await self.bot.close()

async def setup(bot):
    await bot.add_cog(BotLogout(bot))
