import discord
from discord.ext import commands

class AutoBan(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.bans = [767398969147392030, 531602381591543818]

    @commands.Cog.listener()
    async def on_member_join(self, member):
        guild = member.guild
        if member.id in self.bans:
            await guild.ban(member, reason="AutoBanned due to AutoBan List")

def setup(bot):
    bot.add_cog(AutoBan(bot))
