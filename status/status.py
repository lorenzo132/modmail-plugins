import discord
from discord.ext import commands,tasks
import asyncio

class Status(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @tasks.loop(seconds=10)
    async def start_status(self):
        await self.bot.change_presence(activity=discord.Activity(type=discord.ActivityType.watching, name=f"{server.member_count} Members!"))
        await asyncio.sleep(10)

    @commands.command(name="status_start")
    async def start_start_cmd(self, ctx):
        self.start_status.start()
        await ctx.send("Done! Re-run this command if it stops working")

def setup(bot):
    bot.add_cog(Status(bot))
