import discord
from discord.ext import commands

class AutoBan(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.bans = [123, 456, 789]

    @commands.Cog.listener()
    async def on_member_join(self, member):
        guild = member.guild
        if member.id in self.bans:
            embed = discord.Embed(title="AutoBan", description="You have been AutoBanned in **{guild.name}**", color=self.bot.main_color)
            await member.send(embed=embed)
            await guild.ban(member, reason="AutoBanned due to AutoBan List")

def setup(bot):
    bot.add_cog(AutoBan(bot))
