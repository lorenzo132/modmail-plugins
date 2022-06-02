import discord
from discord.ext import commands

from core import checks
from core.models import PermissionLevel


class EmbedRaw(commands.Cog):
    def __init__(self, bot):
        self.bot = bot


    @commands.command()
    @checks.has_permissions(PermissionLevel.SUPPORTER)
    async def raw(self, ctx, message_id: int=None):
        if message_id is None:
            return await ctx.send("Please provide a message ID")
        
        try:
            msg = await ctx.fetch_message(message_id)
        except Exception as e:
            print(str(e))
        msgg = msg.embeds[0]
        await ctx.send(f"```{msgg.description}```")
        

def setup(bot):
    bot.add_cog(EmbedRaw(bot))
