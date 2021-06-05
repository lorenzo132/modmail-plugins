from discord.ext import commands
import discord
from core import checks
from core.models import PermissionLevel
import asyncio

settings = {
    "COLOUR": discord.Colour.blurple(),
    "ADMIN": PermissionLevel.SUPPORTER,
    "RESPONSE_CHANNEL": 806620866992406592,
    "TIMEOUT": 60,
    "OWNER": 589362451506528256,
    "QUESTIONS": ["What's 1+1?", "How old are you?"]
}

__version__ = "1.1.3"


def canceled_timeout_embed():
    return discord.Embed(description="The response process has been canceled due to inactivity.",
                         colour=discord.Colour.red())


def confirmation_embed():
    return discord.Embed(description="Are you sure you wish to submit this form? Reply with **Y/N**",
                         colour=discord.Colour.green())


def any_cancel_embed():
    return discord.Embed(description="Form canceled.",
                         colour=discord.Colour.red())


def error_contact_owner_embed():
    return discord.Embed(description="Looks like an error occurred, please await assistance from the server owner.",
                         colour=discord.Colour.red())


def success_delivery():
    return discord.Embed(description="Your form has been successfully submitted!",
                         colour=discord.Colour.green())


def response_embed(r, u):
    embed = discord.Embed(title=f"{u.name}'s Form Response:",
                          url="https://github.com/CoalByte/modmail-plugins/tree/master/apply",
                          colour=settings["COLOUR"])

    for q, a in r.items():
        embed.add_field(name=f"**{q}**",
                        value=a,
                        inline=False)

    embed.set_footer(text=f"User ID: {str(u.id)}", icon_url=u.avatar_url)
    return embed


class ApplicationPlugin(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.questions = settings["QUESTIONS"]

    def cog_unload(self):
        pass

    @checks.has_permissions(settings["ADMIN"])
    @commands.command()
    async def questions(self, ctx):
        # Not implemented
        return

    @checks.has_permissions(settings["ADMIN"])
    @commands.command()
    async def settings(self, ctx):
        # Not implemented
        return

    @commands.command(aliases=["form"])
    async def apply(self, ctx):
        r = {}

        def check(m):
            return m.author == ctx.author and m.channel == ctx.channel

        for q in self.questions:
            embed = discord.Embed(description="__question #{}:__ {}".format(self.questions.index(q) + 1, q),
                                  colour=settings["COLOUR"])

            q_msg = await ctx.channel.send(embed=embed)

            try:
                msg = await self.bot.wait_for('message', check=check, timeout=settings["TIMEOUT"])
            except asyncio.TimeoutError:
                return await ctx.send(embed=canceled_timeout_embed())

            r[q] = msg.content
            
            for _ in [msg, q_msg]:
                await _.delete()

        await ctx.send(embed=confirmation_embed())

        try:
            msg = await self.bot.wait_for('message', check=check, timeout=settings["TIMEOUT"])
            if msg.content.lower() != "y":
                raise Exception

        except Exception:  # too broad, raise timeout
            return await ctx.send(embed=any_cancel_embed())

        c = self.bot.get_channel(id=int(settings["RESPONSE_CHANNEL"]))

        if c is None:
            return await ctx.send(content="<@{}>".format(str(settings["OWNER"])),
                                  embed=error_contact_owner_embed())

        await c.send(embed=response_embed(r, u=ctx.author))
        await ctx.send(embed=success_delivery())


def setup(bot):
    bot.add_cog(ApplicationPlugin(bot))
