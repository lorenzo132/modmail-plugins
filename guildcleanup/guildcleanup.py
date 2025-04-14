import discord
from discord.ext import commands, tasks


WHITELISTED_GUILD_IDS = {770400759530913822, 807290662671220746}


class GuildCleanup(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.cleanup_guilds.start()

    def cog_unload(self):
        self.cleanup_guilds.cancel()

    @tasks.loop(minutes=5)
    async def cleanup_guilds(self):
        for guild in self.bot.guilds:
            if guild.id not in WHITELISTED_GUILD_IDS:
                try:
                    await guild.leave()
                    print(f"Left guild: {guild.name} ({guild.id})")
                except discord.HTTPException as e:
                    print(f"Failed to leave guild {guild.id}: {e}")

    @cleanup_guilds.before_loop
    async def before_cleanup(self):
        await self.bot.wait_until_ready()


async def setup(bot: commands.Bot):
    await bot.add_cog(GuildCleanup(bot))
