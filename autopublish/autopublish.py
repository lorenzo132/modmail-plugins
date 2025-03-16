import discord
from discord.ext import commands

class AutoPublish(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.channel.type == discord.ChannelType.news and not message.author.bot:
            try:
                await message.publish()
            except discord.Forbidden:
                print(f"Missing permissions to publish messages in {message.channel.name}")
            except discord.HTTPException:
                print(f"Failed to publish message in {message.channel.name}")

async def setup(bot):
    await bot.add_cog(AutoPublish(bot))
