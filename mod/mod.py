import discord
import os
import sys
import random
import asyncio
import time
import json
from random import choice
from discord.ext import commands
from discord.ext.commands import has_permissions, CheckFailure, Bot
from datetime import timedelta

footer = "『 TacoBot ✦ Tacoz 』"
start_time = time.monotonic()


def get_config():
    with open("config.json", "r") as fp:
        return json.load(fp)


def is_staff(ctx):
    if isinstance(ctx.author, discord.Member):
        return get_config()["staff_role"] in [role.id for role in ctx.author.roles]
    return ctx.author.id == 389388825274613771


class MemberID(commands.Converter):
    async def convert(self, ctx, argument):
        try:
            m = await commands.MemberConverter().convert(ctx, argument)
        except commands.BadArgument:
            try:
                return int(argument, base=10)
            except ValueError:
                raise commands.BadArgument(
                    f"{argument} is not a valid member or member ID."
                ) from None
        else:
            return m.id


class ActionReason(commands.Converter):
    async def convert(self, ctx, argument):
        ret = argument

        if len(ret) > 512:
            reason_max = 512 - len(ret) - len(argument)
            raise commands.BadArgument(
                f"reason is too long ({len(argument)}/{reason_max})"
            )
        return ret


class Moderation(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(
        name="whois",
        description="Gets info about a user",
        aliases=["userinfo", "user", "user_info"],
    )
    @commands.guild_only()
    async def whois(self, ctx, user: discord.Member = None):
        if not user:
            e = discord.Embed(
                description=":no_entry_sign: You must specify a user", colour=0xE74C3C
            )
            e.set_footer(text=footer)
            await ctx.send(embed=e)
            return

        show_roles = (
            ", ".join(
                [
                    f"<@&{x.id}>"
                    for x in sorted(user.roles, key=lambda x: x.position, reverse=True)
                    if x.id != ctx.guild.default_role.id
                ]
            )
            if len(user.roles) > 1
            else "None"
        )

        userObject = self.bot.get_user(user.id)

        e = discord.Embed(title=f"{user}", colour=0x2ECC71)

        e.add_field(name="Discord Tag", value=f"{str(user)}")
        e.add_field(
            name="Nickname", value=user.nick if hasattr(user, "nick") else "None"
        )
        e.add_field(name="User ID", value=user.id)
        e.add_field(
            name="Account Created", value=user.created_at.strftime("%d %B %Y, %H:%M")
        )
        e.add_field(
            name="Server Join Data", value=user.joined_at.strftime("%d %B %Y, %H:%M")
        )
        e.add_field(name="Is Bot?", value=str(userObject.bot))
        e.set_thumbnail(url=user.avatar_url)
        e.set_footer(text=footer)

        e.add_field(name="Roles", value=show_roles, inline=False)

        await ctx.send(embed=e)

    @commands.command(
        name="getpfp",
        description="Gets the profile picture of the user",
        aliases=["getprofilepic"],
    )
    @commands.guild_only()
    async def getpfp(self, ctx, user: discord.Member = None):
        if not user:
            e = discord.Embed(
                description=":no_entry_sign: You must specify a user", colour=0xE74C3C
            )
            e.set_footer(text=footer)
            await ctx.send(embed=e)
            return

        e = discord.Embed(title=f"{user}'s Profile Picture", colour=0x2ECC71)

        e.set_image(url=user.avatar_url)
        e.set_footer(text=footer)
        await ctx.send(embed=e)

    @commands.command(aliases=["nick"])
    @commands.guild_only()
    @permissions.has_permissions(manage_nicknames=True)
    async def nickname(self, ctx, member: discord.Member, *, name: str = None):
        """ Nicknames a user from the current server. """
        if await permissions.check_priv(ctx, member):
            return

        try:
            await member.edit(
                nick=name, reason=default.responsible(ctx.author, "Changed by command")
            )
            message = f"Changed **{member.name}'s** nickname to **{name}**"
            if name is None:
                message = f"Reset **{member.name}'s** nickname"
            await ctx.send(message)
        except Exception as e:
            await ctx.send(e)

    @commands.command()
    @commands.guild_only()
    @permissions.has_permissions(ban_members=True)
    async def ban(self, ctx, member: MemberID, *, reason: str = None):
        """ Bans a user from the current server. """
        m = ctx.guild.get_member(member)
        if m is not None and await permissions.check_priv(ctx, m):
            return

        try:
            await ctx.guild.ban(
                discord.Object(id=member),
                reason=default.responsible(ctx.author, reason),
            )
            await ctx.send(default.actionmessage("banned"))
        except Exception as e:
            await ctx.send(e)

    @commands.command()
    @commands.guild_only()
    @commands.max_concurrency(1, per=commands.BucketType.user)
    @permissions.has_permissions(ban_members=True)
    async def massban(self, ctx, reason: ActionReason, *members: MemberID):
        """ Mass bans multiple members from the server. """
        try:
            for member_id in members:
                await ctx.guild.ban(
                    discord.Object(id=member_id),
                    reason=default.responsible(ctx.author, reason),
                )
            await ctx.send(default.actionmessage("massbanned", mass=True))
        except Exception as e:
            await ctx.send(e)

    @commands.command()
    @commands.guild_only()
    @permissions.has_permissions(ban_members=True)
    async def unban(self, ctx, member: MemberID, *, reason: str = None):
        """ Unbans a user from the current server. """
        try:
            await ctx.guild.unban(
                discord.Object(id=member),
                reason=default.responsible(ctx.author, reason),
            )
            await ctx.send(default.actionmessage("unbanned"))
        except Exception as e:
            await ctx.send(e)

    @commands.command()
    @commands.guild_only()
    @permissions.has_permissions(manage_roles=True)
    async def mute(self, ctx, member: discord.Member, *, reason: str = None):
        """ Mutes a user from the current server. """
        if await permissions.check_priv(ctx, member):
            return

        muted_role = next((g for g in ctx.guild.roles if g.name == "Muted"), None)

        if not muted_role:
            return await ctx.send(
                "Are you sure you've made a role called **Muted**? Remember that it's case sensitive too..."
            )

        try:
            await member.add_roles(
                muted_role, reason=default.responsible(ctx.author, reason)
            )
            await ctx.send(default.actionmessage("muted"))
        except Exception as e:
            await ctx.send(e)

    @commands.command()
    @commands.guild_only()
    @permissions.has_permissions(manage_roles=True)
    async def unmute(self, ctx, member: discord.Member, *, reason: str = None):
        """ Unmutes a user from the current server. """
        if await permissions.check_priv(ctx, member):
            return

        muted_role = next((g for g in ctx.guild.roles if g.name == "Muted"), None)

        if not muted_role:
            return await ctx.send(
                "Are you sure you've made a role called **Muted**? Remember that it's case sensetive too..."
            )

        try:
            await member.remove_roles(
                muted_role, reason=default.responsible(ctx.author, reason)
            )
            await ctx.send(default.actionmessage("unmuted"))
        except Exception as e:
            await ctx.send(e)


def setup(bot):
    bot.add_cog(Moderation(bot))
