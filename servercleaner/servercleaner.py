import discord
from discord.ext import commands, tasks
 
 # Add your whitelisted server IDs here
 WHITELISTED_GUILD_IDS = {807290662671220746, 770400759530913822}  # Replace with actual server IDs
 
 class ServerCleaner(commands.Cog):
     def __init__(self, bot):
         self.bot = bot
         self.guild_check_loop.start()
 
     def cog_unload(self):
         self.guild_check_loop.cancel()
 
     @tasks.loop(minutes=5)
     async def guild_check_loop(self):
         """Checks all guilds every 5 minutes and leaves those not whitelisted"""
         for guild in self.bot.guilds:
             if guild.id not in WHITELISTED_GUILD_IDS:
                 await guild.leave()
 
     @guild_check_loop.before_loop
     async def before_guild_check(self):
         await self.bot.wait_until_ready()
 
 async def setup(bot):
     await bot.add_cog(ServerCleaner(bot))
