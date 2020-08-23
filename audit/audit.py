"""
BSD 3-Clause License

Copyright (c) 2020, taku#0621 (Discord)
All rights reserved.

Redistribution and use in source and binary forms, with or without
modification, are permitted provided that the following conditions are met:

1. Redistributions of source code must retain the above copyright notice, this
   list of conditions and the following disclaimer.

2. Redistributions in binary form must reproduce the above copyright notice,
   this list of conditions and the following disclaimer in the documentation
   and/or other materials provided with the distribution.

3. Neither the name of the copyright holder nor the names of its
   contributors may be used to endorse or promote products derived from
   this software without specific prior written permission.

THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE
FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL
DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR
SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER
CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY,
OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.

"""


import datetime
from io import BytesIO
from json import JSONDecodeError
from urllib.parse import urlparse
import re
import typing
from collections import defaultdict
import pickle
import os

import discord
from discord.ext import commands, tasks
from discord.utils import get

import asyncio
import aiohttp
from aiohttp import ClientResponseError
from dateutil.relativedelta import relativedelta


def human_timedelta(dt, *, source=None):
    if isinstance(dt, relativedelta):
        delta = relativedelta
        suffix = ""
    else:
        now = source or datetime.datetime.utcnow()
        if dt >= now:
            delta = relativedelta(dt, now)
            suffix = ""
        else:
            delta = relativedelta(now, dt)
            suffix = " ago"

    if delta.microseconds and delta.seconds:
        delta = delta + relativedelta(seconds=+1)

    attrs = ["years", "months", "days", "hours", "minutes", "seconds"]

    output = []
    for attr in attrs:
        elem = getattr(delta, attr)
        if not elem:
            continue

        if elem > 1:
            output.append(f"{elem} {attr}")
        else:
            output.append(f"{elem} {attr[:-1]}")

    if not output:
        return "now"
    if len(output) == 1:
        return output[0] + suffix
    if len(output) == 2:
        return f"{output[0]} and {output[1]}{suffix}"
    return f"{output[0]}, {output[1]} and {output[2]}{suffix}"


class Audit(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.upload_url = f"https://api.cloudinary.com/v1_1/taku/image/upload"
        self.invite_regex = re.compile(
            r"(?:https?://)?(?:www\.)?(?:discord\.(?:gg|io|me|li)|(?:discordapp|discord)\.com/invite)/[\w]+"
        )
        self.whname = "Modmail Audit Logger"
        self.acname = "dyno-logs"
        self._webhooks = {}
        self._webhook_locks = {}

        self.all = (
            'mute',
            'unmute',
            'deaf',
            'undeaf',
            'message update',
            'message delete',
            'message purge',
            'member nickname',
            'member roles',
            'user update',
            'member join',
            'member leave',
            'member ban',
            'member unban',
            'role create',
            'role update',
            'role delete',
            'server edited',
            'server emoji',
            'channel create',
            'channel update',
            'channel delete',
            'invites',
            'invite create',
            'invite delete'
        )

        self.session = aiohttp.ClientSession(loop=self.bot.loop)
        self.store_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'store.pkl')
        if os.path.exists(self.store_path):
            with open(self.store_path, 'rb') as f:
                try:
                    self.enabled, self.ignored_channel_ids, self.ignored_category_ids = pickle.load(f)
                except pickle.UnpicklingError:
                    self.ignored_channel_ids = defaultdict(set)
                    self.ignored_category_ids = defaultdict(set)
                    self.enabled = defaultdict(set)
        else:
            self.ignored_channel_ids = defaultdict(set)
            self.ignored_category_ids = defaultdict(set)
            self.enabled = defaultdict(set)
        self.save_pickle.start()

    async def send_webhook(self, guild, *args, **kwargs):
        async with self.webhook_lock(guild.id):
            wh = self._webhooks.get(guild.id)
            if wh is not None:
                try:
                    return await wh.send(*args, **kwargs)
                except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                    print(f'Invalid webhook for {guild.name}')
            wh = get(await guild.webhooks(), name=self.whname)
            if wh is not None:
                try:
                    return await wh.send(*args, **kwargs)
                except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                    print(f'Invalid webhook for {guild.name}')

            channel = get(guild.channels, name=self.acname)
            if not channel:
                o = {r: discord.PermissionOverwrite(read_messages=True)
                     for r in guild.roles if r.permissions.view_audit_log}
                o.update(
                    {
                        guild.default_role: discord.PermissionOverwrite(read_messages=False,
                                                                        manage_messages=False),
                        guild.me: discord.PermissionOverwrite(read_messages=True)
                    }
                )
                channel = await guild.create_text_channel(
                    self.acname, overwrites=o, reason="Audit Channel"
                )
            wh = await channel.create_webhook(name=self.whname,
                                              avatar=await self.bot.user.avatar_url.read(),
                                              reason="Audit Webhook")
            try:
                return await wh.send(*args, **kwargs)
            except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                print(f'Failed to send webhook for {guild.name}')

    def webhook_lock(self, guild_id):
        lock = self._webhook_locks.get(guild_id)
        if lock is None:
            self._webhook_locks[guild_id] = lock = asyncio.Lock()
        return lock

    def _save_pickle(self):
        print('saving pickle')
        with open(self.store_path, 'wb') as f:
            try:
                pickle.dump((self.enabled, self.ignored_channel_ids, self.ignored_category_ids), f)
            except pickle.PickleError:
                print('Failed to save pickle')

    def cog_unload(self):
        self._save_pickle()
        self.save_pickle.cancel()

    @tasks.loop(minutes=15)
    async def save_pickle(self):
        self._save_pickle()

    @commands.group()
    async def audit(self, ctx):
        """Audit logs, copied from mee6."""

    @audit.command()
    async def ignore(self, ctx, *, channel: typing.Union[discord.TextChannel, discord.VoiceChannel, discord.CategoryChannel]):
        """Ignore a channel or category from audit logs."""
        if isinstance(channel, discord.CategoryChannel):
            self.ignored_category_ids[ctx.guild.id].add(channel.id)
        else:
            self.ignored_channel_ids[ctx.guild.id].add(channel.id)
        embed = discord.Embed(description="Ignored!", colour=discord.Colour.green())
        await ctx.send(embed=embed)

    @audit.command()
    async def unignore(self, ctx, *,
                       channel: typing.Union[discord.TextChannel, discord.VoiceChannel, discord.CategoryChannel]):
        """Unignore a channel or category from audit logs."""
        try:
            if isinstance(channel, discord.CategoryChannel):
                self.ignored_category_ids[ctx.guild.id].remove(channel.id)
            else:
                self.ignored_channel_ids[ctx.guild.id].remove(channel.id)
        except KeyError:
            embed = discord.Embed(description="Already not ignored!", colour=discord.Colour.red())
        else:
            embed = discord.Embed(description="Unignored!", colour=discord.Colour.green())
        await ctx.send(embed=embed)

    @audit.command()
    async def enable(self, ctx, *, audit_type: str.lower = None):
        """Enable a specific audit type, use "all" to enable all."""
        if audit_type is None:
            embed = discord.Embed(description="**List of all audit types:**\n\n" + '\n'.join(sorted(self.all)),
                                  colour=discord.Colour.green())
            return await ctx.send(embed=embed)

        audit_type = audit_type.replace('_', ' ')
        if audit_type == 'all':
            embed = discord.Embed(description="Enabled all audits!", colour=discord.Colour.green())
            self.enabled[ctx.guild.id] = set(self.all)
        elif audit_type not in self.all:
            embed = discord.Embed(description="Invalid audit type!", colour=discord.Colour.red())
            embed.add_field(name="Valid audit types", value=', '.join(self.all))
        elif audit_type in self.enabled:
            embed = discord.Embed(description="Already enabled!", colour=discord.Colour.red())
        else:
            self.enabled[ctx.guild.id].add(audit_type)
            embed = discord.Embed(description="Enabled!", colour=discord.Colour.green())
        await ctx.send(embed=embed)

    @audit.command()
    async def disable(self, ctx, *, audit_type: str.lower):
        """Disable a specific audit type, use "all" to disable all."""
        audit_type = audit_type.replace('_', ' ')
        if audit_type == 'all':
            embed = discord.Embed(description="Disabled all audits!", colour=discord.Colour.green())
            self.enabled[ctx.guild.id] = set()
        elif audit_type not in self.all:
            embed = discord.Embed(description="Invalid audit type!", colour=discord.Colour.red())
            embed.add_field(name="Valid audit types", value=', '.join(self.all))
        elif audit_type not in self.enabled:
            embed = discord.Embed(description="Not enabled!", colour=discord.Colour.red())
        else:
            self.enabled[ctx.guild.id].remove(audit_type)
            embed = discord.Embed(description="Disabled!", colour=discord.Colour.green())
        await ctx.send(embed=embed)

    async def cog_command_error(self, ctx, error):
        print("An error occurred in audit: " + str(error))

    def c(self, type, guild, channel=None):
        if channel is not None:
            if channel.id in self.ignored_channel_ids[guild.id]:
                return False
            if getattr(channel, 'category', None) is not None:
                if channel.category.id in self.ignored_category_ids[guild.id]:
                    return False
        return type in self.enabled[guild.id]

    @staticmethod
    def user_base_embed(user, url=discord.embeds.EmptyEmbed, user_update=False):
        embed = discord.Embed()
        embed.set_author(name=f'{user.name}#{user.discriminator}', url=url, icon_url=str(user.avatar_url))
        embed.timestamp = datetime.datetime.utcnow()
        if user_update:
            embed.set_footer(text=f"User ID: {user.id}")
            embed.set_thumbnail(url=str(user.avatar_url))
        return embed

    async def upload_img(self, id, type, url):
        url = str(url)
        filename = urlparse(url).path.rsplit('/', maxsplit=1)[-1].split('.', maxsplit=1)[0]
        content = {
            'file': url,
            'upload_preset': 'audits',
            'public_id': f'audits/uwu/{self.bot.user.id}/{type}/{id}/{filename}'
        }
        try:
            async with self.session.post(self.upload_url, json=content, raise_for_status=True) as r:
                return (await r.json())['secure_url']
        except (JSONDecodeError, ClientResponseError, KeyError):
            return None

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot or not message.guild:
            return
        if not self.c('invites', message.guild, message.channel):
            return

        invites = self.invite_regex.findall(message.content)
        for embed in message.embeds:
            if len(embed.description):
                invites.extend(self.invite_regex.findall(embed.description))
            for field in embed.fields:
                invites.extend(self.invite_regex.findall(field.value))
        if not invites:
            return
        embed = self.user_base_embed(message.author, url=message.jump_url)
        embed.colour = discord.Colour.red()
        embed.set_footer(text=f"Message ID: {message.id} | User ID: {message.author.id}")
        if len(invites) == 1:
            embed.description = f"**:envelope_with_arrow: {message.author.mention} sent an invite in #{message.channel}**\n\n"
        else:
            embed.description = f"**:envelope_with_arrow: {message.author.mention} sent multiple invites in #{message.channel}**\n\n"
        embed.description += '\n'.join(invites)
        await self.send_webhook(message.guild, embed=embed)

    @commands.Cog.listener()
    async def on_member_update(self, before, after):
        def get_embed(desc):
            e = self.user_base_embed(after, user_update=True)
            e.colour = discord.Colour.gold()
            e.description = desc
            return e

        if self.c('member nickname', after.guild):
            if before.nick != after.nick:
                embed = get_embed(f"**:pencil: {after.mention} nickname edited**")
                embed.add_field(name='Old nickname', value=f"`{before.nick}`")
                embed.add_field(name='New nickname', value=f"`{after.nick}`")
                await self.send_webhook(after.guild, embed=embed)

        if self.c('member roles', after.guild):
            removed_roles = sorted(set(before.roles) - set(after.roles), key=lambda r: r.position, reverse=True)
            added_roles = sorted(set(after.roles) - set(before.roles), key=lambda r: r.position, reverse=True)

            if added_roles or removed_roles:
                embed = get_embed(f"**:crossed_swords: {after.mention} roles have changed**")
                if added_roles:
                    embed.add_field(name='Added roles', value=f"{' '.join('``' + r.name + '``' for r in added_roles)}", inline=False)
                if removed_roles:
                    embed.add_field(name='Removed roles', value=f"{' '.join('``' + r.name + '``' for r in removed_roles)}", inline=False)
                await self.send_webhook(after.guild, embed=embed)

    async def _user_update(self, guild, before, after):
        if not self.c('user update', guild):
            return

        embed = self.user_base_embed(after, user_update=True)
        embed.colour = discord.Colour.gold()
        embed.description = f"**:crossed_swords: {after.mention} updated their profile**"

        if before.avatar != after.avatar:
            before_url = await self.upload_img(after.id, 'avatar', before.avatar_url)
            if not before_url:
                before_url = str(before.avatar_url)
            embed._author['icon_url'] = before_url
            embed.add_field(name="Avatar", value=f"[[before]]({before_url}) -> [[after]]({after.avatar_url})")

        if before.discriminator != after.discriminator:
            embed.add_field(name="Discriminator", value=f"`#{before.discriminator}` -> `#{after.discriminator}`")

        if before.name != after.name:
            embed.add_field(name="Name", value=f"`{before.name}` -> `{after.name}`")
        await self.send_webhook(guild, embed=embed)

    @commands.Cog.listener()
    async def on_user_update(self, before, after):
        for guild in self.bot.guilds:
            if guild.get_member(after.id):
                await self._user_update(guild, before, after)

    
def setup(bot):
    bot.add_cog(Audit(bot))
