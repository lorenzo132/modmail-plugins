import discord
from discord.ext import commands

class BotLogout(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @checks.has_permissions(PermissionLevel.OWNER)
    @commands.command()
    async def botlogout(self,__):
        await self.bot.close()

async def setup(bot):
    await bot.add_cog(BotLogout(bot))
