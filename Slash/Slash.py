import discord
from discord.ext import commands
from discord_slash import SlashCommand
from discord_slash import SlashContext


class Slash(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.slash = SlashCommand(bot, override_type=True)
        # Cog is only supported by commands ext, so just skip checking type.

        # Make sure all commands should be inside `__init__`
        # or some other functions that can put commands.
        @self.slash.slash(name="test")
        async def _test(ctx: SlashContext):
            await ctx.send(content="Hello, World!")

    def cog_unload(self):
        self.slash.remove()


def setup(bot):
    bot.add_cog(Slash(bot))