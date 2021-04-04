import os, asyncio, discord, discord.ext
from discord.ext import commands
from colorama import Fore

banlist = ["767398969147392030", "531602381591543818", "617711889169776641"]

class autoban(commands.Cog):

    def __init__(self, bot):
        self.bot = bot
        

    @commands.command()
    async def on_member_join(self, member):
        await member.ban(banlist)
        print(f"{member} was banned, fuck you fatal")

    async def cog_command_error(self, ctx, error):
        # Handle the errors from the cog here
        if isinstance(error, god.CommandInvokeError):
            await ctx.send("Missing args and/or permissions")
        if isinstance(error, god.MissingPermissions):
            await ctx.send("Missing args and/or permissions")
        if isinstance(error, god.CommandOnCooldown):
            await ctx.send("Calm down bud, you're not god. (15seconds)")
        if isinstance(error, god.MissingRequiredArgument):
            await ctx.send("Missing args and/or permissions")




def setup(bot):
    bot.add_cog(autoban(bot))
