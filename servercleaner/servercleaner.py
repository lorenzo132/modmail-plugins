import discord
from discord.ext import commands
from core import checks

# Add your whitelisted server IDs here
WHITELISTED_GUILD_IDS = {770400759530913822, 807290662671220746}  # Replace with actual server IDs

class ServerCleaner(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command()
    @checks.thread_only()
    async def id(self, ctx):
        """Returns the Recipient's ID"""
        await ctx.send(ctx.thread.id)

    @commands.Cog.listener()
    async def on_guild_join(self, guild):
        """Leaves the server if it's not whitelisted"""
        if guild.id not in WHITELISTED_GUILD_IDS:
            await guild.leave()

async def setup(bot):
    await bot.add_cog(ServerCleaner(bot))
