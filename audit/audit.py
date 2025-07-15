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
from pymongo import MongoClient


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

    if delta.microsecond and delta.seconds:
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


class MongoAuditStore:
    def __init__(self, uri, db_name='modmail_audit', col_name='guild_configs'):
        self.client = MongoClient(uri)
        self.db = self.client[db_name]
        self.col = self.db[col_name]

    def get_guild(self, guild_id):
        return self.col.find_one({'guild_id': guild_id}) or {}

    def set_guild(self, guild_id, data):
        self.col.update_one({'guild_id': guild_id}, {'$set': data}, upsert=True)

    def update_guild(self, guild_id, update):
        self.col.update_one({'guild_id': guild_id}, {'$set': update}, upsert=True)

    def all_guilds(self):
        return list(self.col.find())


class Audit(commands.Cog):
    CACHE_REFRESH_SECONDS = 300  # 5 minutes

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.upload_url = f"https://api.cloudinary.com/v1_1/taku/image/upload"
        self.invite_regex = re.compile(
            r"(?:https?://)?(?:www\.)?(?:discord\.(?:gg|io|me|li)|(?:discordapp|discord)\.com/invite)/[\w]+"
        )
        self.whname = "Modmail Audit Logger"
        self.acname = "modmail-audit"
        self._webhooks = {}
        self._webhook_locks = {}
        self.all = (
            'mute', 'unmute', 'deaf', 'undeaf', 'message update', 'message delete', 'message purge',
            'member nickname', 'member roles', 'user update', 'member join', 'member leave', 'member ban',
            'member unban', 'role create', 'role update', 'role delete', 'server edited', 'server emoji',
            'channel create', 'channel update', 'channel delete', 'invites', 'invite create', 'invite delete',
            'automod action'
        )
        self.session = aiohttp.ClientSession(loop=self.bot.loop)
        # Load MongoDB URI from environment (.env) with support for CONNECTION_URI or MONGO_URI
        MONGO_URI = os.getenv('CONNECTION_URI') or os.getenv('MONGO_URI') or 'mongodb://localhost:27017/'
        self.store = MongoAuditStore(MONGO_URI)
        # Caching
        self._guild_config_cache = {}
        self._cache_lock = asyncio.Lock()
        self.bot.loop.create_task(self._periodic_cache_refresh())
        self.LOG_CATEGORY_NAME = "Audit logs"
        self.LOG_CHANNEL_NAME = "audit-log"

    async def _periodic_cache_refresh(self):
        await self.bot.wait_until_ready()
        while not self.bot.is_closed():
            async with self._cache_lock:
                for guild in self.bot.guilds:
                    self._guild_config_cache[guild.id] = self.store.get_guild(guild.id)
            await asyncio.sleep(self.CACHE_REFRESH_SECONDS)

    def _get_guild_config(self, guild_id):
        # Try cache first, fallback to DB if missing
        if guild_id in self._guild_config_cache:
            return self._guild_config_cache[guild_id]
        doc = self.store.get_guild(guild_id)
        self._guild_config_cache[guild_id] = doc
        return doc

    def get_enabled(self, guild_id):
        doc = self._get_guild_config(guild_id)
        return set(doc.get('enabled', []))

    def set_enabled(self, guild_id, enabled):
        self.store.update_guild(guild_id, {'enabled': list(enabled)})
        self._guild_config_cache[guild_id] = self.store.get_guild(guild_id)

    def get_ignored_channels(self, guild_id):
        doc = self._get_guild_config(guild_id)
        return set(doc.get('ignored_channel_ids', []))

    def set_ignored_channels(self, guild_id, ids):
        self.store.update_guild(guild_id, {'ignored_channel_ids': list(ids)})
        self._guild_config_cache[guild_id] = self.store.get_guild(guild_id)

    def get_ignored_categories(self, guild_id):
        doc = self._get_guild_config(guild_id)
        return set(doc.get('ignored_category_ids', []))

    def set_ignored_categories(self, guild_id, ids):
        self.store.update_guild(guild_id, {'ignored_category_ids': list(ids)})
        self._guild_config_cache[guild_id] = self.store.get_guild(guild_id)

    async def send_webhook(self, guild, *args, **kwargs):
        async with self.webhook_lock(guild.id):
            wh = self._webhooks.get(guild.id)
            if wh is not None:
                try:
                    return await wh.send(*args, **kwargs)
                except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                    pass
            doc = self.store.get_guild(guild.id)
            channel = None
            if doc.get('log_channel_id'):
                for cat in guild.categories:
                    channel = discord.utils.get(cat.channels, id=doc['log_channel_id'])
                    if channel:
                        break
            if not channel:
                # fallback to name-based lookup for recovery
                for cat in guild.categories:
                    if cat.id == doc.get('log_category_id'):
                        channel = discord.utils.get(cat.channels, name=self.LOG_CHANNEL_NAME)
                        break
            if not channel:
                # fallback to any channel with the right name
                channel = discord.utils.get(guild.text_channels, name=self.LOG_CHANNEL_NAME)
            if not channel:
                # fallback to any text channel
                channel = next((c for c in guild.text_channels if c.permissions_for(guild.me).send_messages), None)
            if not channel:
                raise RuntimeError("No suitable logging channel found.")
            wh = get(await channel.webhooks(), name=self.whname)
            if wh is not None:
                try:
                    self._webhooks[guild.id] = wh
                    return await wh.send(*args, **kwargs)
                except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                    pass
            wh = await channel.create_webhook(name=self.whname,
                                              avatar=await self.bot.user.display_avatar.read(),
                                              reason="Audit Webhook")
            self._webhooks[guild.id] = wh
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
            cats = self.get_ignored_categories(ctx.guild.id)
            cats.add(channel.id)
            self.set_ignored_categories(ctx.guild.id, cats)
        else:
            chans = self.get_ignored_channels(ctx.guild.id)
            chans.add(channel.id)
            self.set_ignored_channels(ctx.guild.id, chans)
        embed = discord.Embed(description="Ignored!", colour=discord.Colour.green())
        await ctx.send(embed=embed)

    @audit.command()
    async def unignore(self, ctx, *, channel: typing.Union[discord.TextChannel, discord.VoiceChannel, discord.CategoryChannel]):
        """Unignore a channel or category from audit logs."""
        try:
            if isinstance(channel, discord.CategoryChannel):
                cats = self.get_ignored_categories(ctx.guild.id)
                cats.remove(channel.id)
                self.set_ignored_categories(ctx.guild.id, cats)
            else:
                chans = self.get_ignored_channels(ctx.guild.id)
                chans.remove(channel.id)
                self.set_ignored_channels(ctx.guild.id, chans)
        except KeyError:
            embed = discord.Embed(description="Already not ignored!", colour=discord.Colour.red())
        else:
            embed = discord.Embed(description="Unignored!", colour=discord.Colour.green())
        await ctx.send(embed=embed)

    @audit.command()
    async def enable(self, ctx, *, audit_type: str.lower = None):
        """Enable a specific audit type, use 'all' to enable all."""
        enabled = self.get_enabled(ctx.guild.id)
        if audit_type is None:
            embed = discord.Embed(description="**List of all audit types:**\n\n" + '\n'.join(sorted(self.all)),
                                  colour=discord.Colour.green())
            return await ctx.send(embed=embed)

        audit_type = audit_type.replace('_', ' ')
        if audit_type == 'all':
            embed = discord.Embed(description="Enabled all audits!", colour=discord.Colour.green())
            enabled = set(self.all)
        elif audit_type not in self.all:
            embed = discord.Embed(description="Invalid audit type!", colour=discord.Colour.red())
            embed.add_field(name="Valid audit types", value=', '.join(self.all))
        elif audit_type in enabled:
            embed = discord.Embed(description="Already enabled!", colour=discord.Colour.red())
        else:
            enabled.add(audit_type)
            embed = discord.Embed(description="Enabled!", colour=discord.Colour.green())
        self.set_enabled(ctx.guild.id, enabled)
        await ctx.send(embed=embed)

    @audit.command()
    async def disable(self, ctx, *, audit_type: str.lower):
        """Disable a specific audit type, use 'all' to disable all."""
        enabled = self.get_enabled(ctx.guild.id)
        audit_type = audit_type.replace('_', ' ')
        if audit_type == 'all':
            embed = discord.Embed(description="Disabled all audits!", colour=discord.Colour.green())
            enabled = set()
        elif audit_type not in self.all:
            embed = discord.Embed(description="Invalid audit type!", colour=discord.Colour.red())
            embed.add_field(name="Valid audit types", value=', '.join(self.all))
        elif audit_type not in enabled:
            embed = discord.Embed(description="Not enabled!", colour=discord.Colour.red())
        else:
            enabled.remove(audit_type)
            embed = discord.Embed(description="Disabled!", colour=discord.Colour.green())
        self.set_enabled(ctx.guild.id, enabled)
        await ctx.send(embed=embed)

    async def cog_command_error(self, ctx, error):
        print("An error occurred in audit: " + str(error))

    def c(self, type, guild, channel=None):
        if channel is not None:
            if channel.id in self.get_ignored_channels(guild.id):
                return False
            if getattr(channel, 'category', None) is not None:
                if channel.category.id in self.get_ignored_categories(guild.id):
                    return False
        return type in self.get_enabled(guild.id)

    @staticmethod
    def user_base_embed(user, url=None, user_update=False):
        # Use display_avatar for best compatibility in dpy 2.3.2
        display_name = getattr(user, 'display_name', user.name)
        # Handle discriminator deprecation
        discriminator = getattr(user, 'discriminator', None)
        if discriminator and discriminator != '0':
            full_name = f'{user.name}#{discriminator} ({user.id})'
        else:
            full_name = f'{user.name} ({user.id})'
        avatar_url = str(getattr(user, 'display_avatar', getattr(user, 'avatar', None)))
        embed = discord.Embed()
        embed.set_author(name=full_name, url=url, icon_url=avatar_url)
        embed.timestamp = datetime.datetime.utcnow()
        if user_update:
            embed.set_footer(text=f"User ID: {user.id}")
            embed.set_thumbnail(url=avatar_url)
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
            embed.description = f"**:envelope_with_arrow: {message.author.mention} ({message.author.id}) sent an invite in #{message.channel}**\n\n"
        else:
            embed.description = f"**:envelope_with_arrow: {message.author.mention} ({message.author.id}) sent multiple invites in #{message.channel}**\n\n"
        embed.description += '\n'.join(invites)
        await self.send_webhook(message.guild, embed=embed)

    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        # mute, unmute, deaf, undeaf
        async def send_embed(text, status_on):
            embed = self.user_base_embed(member)
            if status_on:
                embed.description = f"**:loud_sound: {member.mention} ({member.id}) was {text}**"
                embed.colour = discord.Colour.green()
            else:
                embed.description = f"**:mute: {member.mention} ({member.id}) was {text}**"
                embed.colour = discord.Colour.red()
            return await self.send_webhook(member.guild, embed=embed)

        if self.c('mute', member.guild):
            if not before.mute and after.mute:
                await send_embed('muted', False)
        if self.c('unmute', member.guild):
            if before.mute and not after.mute:
                await send_embed('unmuted', True)
        if self.c('deaf', member.guild):
            if not before.deaf and after.deaf:
                await send_embed('deafened', False)
        if self.c('undeaf', member.guild):
            if before.deaf and not after.deaf:
                await send_embed('undeafened', True)

    @commands.Cog.listener()
    async def on_raw_message_edit(self, payload):
        # message update
        channel = self.bot.get_channel(payload.channel_id)
        if channel is None or not hasattr(channel, 'guild'):
            return
        if not self.c('message update', channel.guild, channel):
            return

        try:
            message = await channel.fetch_message(payload.message_id)
        except discord.NotFound:
            return
        if message.author.bot:
            return

        cached_message = payload.cached_message

        embed = self.user_base_embed(message.author, message.jump_url)
        embed.set_footer(text=f"Message ID: {payload.message_id} | Channel ID: {payload.channel_id}")
        embed.timestamp = message.edited_at or datetime.datetime.utcnow()
        files = []
        embed2 = None
        send_embed = False
        send_embed2 = False

        if cached_message:
            embed2 = embed.copy()
            if cached_message.content != message.content:
                send_embed = send_embed2 = True
                embed.description = cached_message.content or "Message has no content."
                embed2.description = message.content or "Message has no content."
            diff_attachments = [att for att in cached_message.attachments if not get(message.attachments, id=att.id)]
            if diff_attachments:
                send_embed = True
                diff_text = ''
                for att in diff_attachments:
                    diff_text += f"[{att.filename}]({att.url}) [**`Alt Link`**]({att.proxy_url})\n"
                    f = BytesIO()
                    try:
                        await att.save(f, use_cached=True)
                    except (discord.HTTPException, discord.NotFound):
                        f.close()
                    else:
                        files += [discord.File(f, att.filename)]
                embed.set_image(url=diff_attachments[0].url)
                embed.add_field(name="✘ Deleted attachments", value=diff_text)
            diff_attachments = [att for att in message.attachments if not get(cached_message.attachments, id=att.id)]
            if diff_attachments:
                send_embed2 = True
                diff_text = ''
                for att in diff_attachments:
                    diff_text += f"[{att.filename}]({att.url}) [**`Alt Link`**]({att.proxy_url})\n"
                embed2.set_image(url=diff_attachments[0].url)
                embed2.add_field(name="✓ Added attachments", value=diff_text)
            if cached_message.mention_everyone and not message.mention_everyone:
                send_embed = True
                embed.add_field(name="Mentions everyone", value="`true` -> `false`")
            if not cached_message.mention_everyone and message.mention_everyone:
                send_embed = True
                embed.add_field(name="Mentions everyone", value="`false` -> `true`")
            if not cached_message.pinned and message.pinned:
                send_embed = True
                embed.add_field(name="Pinned", value="`false` -> `true`")
            if cached_message.pinned and not message.pinned:
                send_embed = True
                embed.add_field(name="Pinned", value="`true` -> `false`")
        else:
            if payload.data.get('content') is not None:
                send_embed = True
                if not payload.data['content']:
                    embed.description = "Message has no content."
                else:
                    embed.description = payload.data['content']
            if payload.data.get('attachments') is not None:
                send_embed = True
                if not payload.data['attachments']:
                    embed.add_field(name="Attachments", value="No attachments.")
                else:
                    diff_text = ''
                    for att in payload.data['attachments']:
                        att = discord.Attachment(data=att, state=message._state)
                        diff_text += f"[{att.filename}]({att.url}) [**`Alt Link`**]({att.proxy_url})\n"
                    embed.set_image(url=payload.data['attachments'][0]['url'])
                    embed.add_field(name="Attachments", value=diff_text)
            if payload.data.get('mention_everyone') is not None:
                send_embed = True
                if payload.data['mention_everyone']:
                    embed.add_field(name="Mentions everyone", value="`true`")
                else:
                    embed.add_field(name="Mentions everyone", value="`false`")
            if payload.data.get('pinned') is not None:
                send_embed = True
                if payload.data['pinned']:
                    embed.add_field(name="Pinned", value="`true`")
                else:
                    embed.add_field(name="Pinned", value="`false`")

        if send_embed2:
            embed.colour = discord.Colour.light_grey()
            embed2.colour = discord.Colour.dark_grey()
            embed.description = f"**:pencil: Message updated in {channel.mention} (__before__):**\n\n" + \
                                (embed.description if len(embed.description) else '')
            embed2.description = f"**:pencil: Message updated in {channel.mention} (__after__):**\n\n" + \
                                 (embed2.description if len(embed2.description) else '')
        elif send_embed:
            embed.colour = discord.Colour.gold()
            embed.description = f"**:pencil: Message updated in {channel.mention}:**\n\n" + \
                                (embed.description if len(embed.description) else '')
        else:
            embed.colour = discord.Colour.gold()
            embed.description = f"**:pencil: Message updated in {channel.mention}: *No change detected*.**"

        if send_embed2:
            await self.send_webhook(channel.guild, embeds=[embed, embed2], files=files)
        else:
            await self.send_webhook(channel.guild, embed=embed, files=files)

        for file in files:
            file.fp.close()

    @commands.Cog.listener()
    async def on_message_delete(self, message):
        if message.author.bot or not message.guild:
            return

        # message delete
        if not self.c('message delete', message.guild, message.channel):
            return

        embed = self.user_base_embed(message.author)
        embed.set_footer(text=f"Message ID: {message.id} & sent on")
        embed.timestamp = message.created_at
        embed.colour = discord.Colour.red()
        embed.description = f"**:scissors: Message deleted from {message.channel.mention}:**\n\n"
        embed.description += message.content or "Message has no content."
        files = []
        if message.attachments:
            diff_text = ''
            for att in message.attachments:
                diff_text += f"[{att.filename}]({att.url}) [**`Alt Link`**]({att.proxy_url})\n"
                f = BytesIO()
                try:
                    await att.save(f, use_cached=True)
                except (discord.HTTPException, discord.NotFound):
                    f.close()
                else:
                    files += [discord.File(f, att.filename)]
            embed.set_image(url=message.attachments[0].url)
            embed.add_field(name="Attachments", value=diff_text)

        if message.mention_everyone:
            embed.add_field(name="Mentions everyone", value="`true`")
        else:
            embed.add_field(name="Mentions everyone", value="`false`")
        if message.pinned:
            embed.add_field(name="Pinned", value="`true`")
        else:
            embed.add_field(name="Pinned", value="`false`")

        if len(embed.description) >= 2048:
            embed.description = "**:scissors: Message deleted:**\n\n"
            embed.description += message.content or "Message has no content."
            embed.add_field(name="Channel", value=message.channel.mention)

        embed2 = discord.Embed()
        embed2.timestamp = datetime.datetime.utcnow()
        embed2.set_footer(text=f"Channel ID: {message.channel.id} & deleted on")
        embed2.colour = discord.Colour.red()
        await self.send_webhook(message.guild, embeds=[embed, embed2], files=files)

    @commands.Cog.listener()
    async def on_raw_bulk_message_delete(self, payload):
        channel = self.bot.get_channel(payload.channel_id)
        if not channel or not hasattr(channel, 'guild'):
            return

        # message purge
        if not self.c('message purge', channel.guild, channel):
            return

        messages = sorted(payload.cached_messages, key=lambda msg: msg.created_at)
        message_ids = payload.message_ids
        pl = '' if len(message_ids) == 1 else 's'
        pl_be_past = 'was' if len(message_ids) == 1 else 'were'
        upload_text = f'The following message{pl} {pl_be_past} deleted:\n\n'

        if not messages:
            upload_text += 'There are no known messages.\n'
            upload_text += f'Unknown message ID{pl}: ' + ', '.join(map(str, message_ids)) + '.'
        else:
            known_message_ids = set()
            for message in messages:
                known_message_ids.add(message.id)
                try:
                    time = message.created_at.strftime('%b %-d at %-I:%M %p')
                except ValueError:
                    time = message.created_at.strftime('%b %d at %I:%M %p')
                upload_text += f'> {time} {message.id} | {message.author.name}#{message.author.discriminator}:\n'
                upload_text += f'\tContent: {message.content or "Message has no content."}\n'
                for i, e in enumerate(message.embeds):
                    if len(e.description):
                        upload_text += f'\tEmbed #{i}: {e.description}\n'
                if message.attachments:
                    upload_text += f'\tAttachments: {", ".join(att.proxy_url for att in message.attachments)}\n'
                if message.mention_everyone:
                    upload_text += f'\tMentions everyone: true\n'
                if message.pinned:
                    upload_text += f'\tPinned: true\n'
                upload_text += '\n'
            unknown_message_ids = message_ids ^ known_message_ids
            if unknown_message_ids:
                pl_unknown = '' if len(unknown_message_ids) == 1 else 's'
                upload_text += f'Unknown message ID{pl_unknown}: ' + ', '.join(map(str, unknown_message_ids)) + '.'

        embed = discord.Embed()
        embed.description = f"**:scissors: Messages purged from {channel.mention}:**" \
                            f"\n\nTotal deleted messages: {len(message_ids)}."
        embed.colour = discord.Colour.red()
        embed.set_footer(text=f"Channel ID: {payload.channel_id}")
        embed.timestamp = datetime.datetime.utcnow()

        try:
            async with self.session.post('https://hastebin.cc/documents', data=upload_text) as resp:
                key = (await resp.json())["key"]
                embed.add_field(name="Recovered URL", value=f"https://hastebin.cc/{key}.txt")
        except (JSONDecodeError, ClientResponseError, IndexError):
            pass

        await self.send_webhook(channel.guild, embed=embed)

    @commands.Cog.listener()
    async def on_member_update(self, before, after):
        def get_embed(desc):
            e = self.user_base_embed(after, user_update=True)
            e.colour = discord.Colour.gold()
            e.description = desc
            return e

        if self.c('member nickname', after.guild):
            if before.nick != after.nick:
                embed = get_embed(f"**:pencil: {after.mention} ({after.id}) nickname edited**")
                embed.add_field(name='Old nickname', value=f"`{before.nick}`")
                embed.add_field(name='New nickname', value=f"`{after.nick}`")
                await self.send_webhook(after.guild, embed=embed)

        if self.c('member roles', after.guild):
            removed_roles = sorted(set(before.roles) - set(after.roles), key=lambda r: r.position, reverse=True)
            added_roles = sorted(set(after.roles) - set(before.roles), key=lambda r: r.position, reverse=True)

            if added_roles or removed_roles:
                embed = get_embed(f"**:crossed_swords: {after.mention} ({after.id}) roles have changed**")
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
        embed.description = f"**:crossed_swords: {after.mention} ({after.id}) updated their profile**"

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

    @commands.Cog.listener()
    async def on_member_join(self, member):
        if not self.c('member join', member.guild):
            return
        embed = self.user_base_embed(member, user_update=True)
        embed.colour = discord.Colour.green()
        embed.description = f"**:inbox_tray: {member.mention} ({member.id}) joined the server**"
        embed.add_field(name="Account creation", value=human_timedelta(member.created_at))
        await self.send_webhook(member.guild, embed=embed)

    @commands.Cog.listener()
    async def on_member_leave(self, member):
        if not self.c('member leave', member.guild):
            return
        embed = self.user_base_embed(member, user_update=True)
        embed.colour = discord.Colour.red()
        embed.add_field(name="Joined server", value=human_timedelta(member.joined_at))
        embed.description = f"**:outbox_tray: {member.mention} ({member.id}) left the server**"
        await self.send_webhook(member.guild, embed=embed)

    @commands.Cog.listener()
    async def on_member_ban(self, guild, user):
        if not self.c('member ban', guild):
            return
        embed = self.user_base_embed(user, user_update=True)
        embed.colour = discord.Colour.red()
        embed.description = f"**:man_police_officer: :lock: {user.mention} ({user.id}) was banned**"
        await self.send_webhook(guild, embed=embed)

    @commands.Cog.listener()
    async def on_member_unban(self, guild, user):
        if not self.c('member unban', guild):
            return
        embed = self.user_base_embed(user, user_update=True)
        embed.colour = discord.Colour.green()
        embed.description = f"**:man_police_officer: :unlock: {user.mention} ({user.id}) was unbanned**"
        await self.send_webhook(guild, embed=embed)

    @commands.Cog.listener()
    async def on_guild_role_create(self, role):
        if not self.c('role create', role.guild):
            return
        embed = discord.Embed()
        embed.description = f"**:crossed_swords: Role created: {role.name}**"
        embed.colour = discord.Colour.green()
        embed.timestamp = role.created_at
        embed.set_footer(text=f"ID: {role.id}")
        if role.permissions.value == 0b0:
            embed.add_field(name='Permissions', value='No permissions granted.', inline=False)
        elif role.permissions.value == 0b01111111111111111111111111111111:
            embed.add_field(name='Permissions', value='All permissions granted.', inline=False)
        else:
            embed.add_field(name='Permissions', value=', '.join(
                sorted(p.replace('_', ' ').replace('administrator', '**administrator**')
                       for p, v in (role.permissions
                                    if not role.permissions.administrator else discord.Permissions.all()) if v)
            ), inline=False)
        await self.send_webhook(role.guild, embed=embed)

    @commands.Cog.listener()
    async def on_guild_role_update(self, before, after):
        if not self.c('role update', after.guild):
            return
        embed = discord.Embed()
        if after.is_default():
            embed.description = f"**:pencil: Role updated: @everyone**"
        else:
            embed.description = f"**:pencil: Role updated: {after.mention}**"
            embed.set_footer(text=f"ID: {after.id}")

        embed.colour = discord.Colour.gold()
        embed.timestamp = datetime.datetime.utcnow()
        if before.name != after.name:
            embed.add_field(name="Name", value=f"`{before.name}` -> `{after.name}`", inline=False)
        if before.colour != after.colour:
            embed.add_field(name="Colour",
                            value=f"[#{before.colour.value:0>6x}](https://www.color-hex.com/color/{before.colour.value:0>6x}) -> [#{after.colour.value:0>6x}](https://www.color-hex.com/color/{after.colour.value:0>6x})", inline=False)
        if before.hoist != after.hoist:
            embed.add_field(name="Hoisted", value=f"`{'Yes' if before.hoist else 'No'}` -> "
                                                  f"`{'Yes' if after.hoist else 'No'}`", inline=False)
        if before.mentionable != after.mentionable:
            embed.add_field(name="Mentionable", value=f"`{'Yes' if before.mentionable else 'No'}` -> "
                                                      f"`{'Yes' if after.mentionable else 'No'}`", inline=False)

        added_perms = set()
        removed_perms = set()
        for p, v in before.permissions:
            if not v and getattr(after.permissions, p):
                added_perms.add(p)
            elif v and not getattr(after.permissions, p):
                removed_perms.add(p)

        if added_perms:
            embed.add_field(name='✓ Allowed permissions', value=', '.join(
                sorted(p.replace('_', ' ').replace('administrator', '**administrator**') for p in added_perms)
            ), inline=False)
        if removed_perms:
            embed.add_field(name='✘ Denied permissions', value=', '.join(
                sorted(p.replace('_', ' ').replace('administrator', '**administrator**') for p in removed_perms)
            ), inline=False)
        if len(embed.fields) == 0:
            return
        await self.send_webhook(after.guild, embed=embed)

    @commands.Cog.listener()
    async def on_guild_role_delete(self, role):
        if not self.c('role delete', role.guild):
            return

        embed = discord.Embed()
        embed.description = f"**:wastebasket: Role deleted: {role.name}**"
        embed.colour = discord.Colour.red()
        embed.timestamp = datetime.datetime.utcnow()
        embed.set_footer(text=f"ID: {role.id}")
        embed.add_field(name="Colour", value=f"[#{role.colour.value:0>6x}](https://www.color-hex.com/color/{role.colour.value:0>6x})")
        embed.add_field(name="Hoisted", value=f"`{'Yes' if role.hoist else 'No'}`")
        embed.add_field(name="Mentionable", value=f"`{'Yes' if role.mentionable else 'No'}`")

        if role.permissions.value == 0b0:
            embed.add_field(name='Permissions', value='No permissions granted.', inline=False)
        elif role.permissions.value == 0b01111111111111111111111111111111:
            embed.add_field(name='Permissions', value='All permissions granted.', inline=False)
        else:
            embed.add_field(name='Permissions', value=', '.join(
                sorted(p.replace('_', ' ').replace('administrator', '**administrator**')
                       for p, v in role.permissions if v)
            ), inline=False)

        await self.send_webhook(role.guild, embed=embed)

    def get_region_flag(self, name):
        if isinstance(name, str):
            return name
        if name == discord.VoiceRegion.amsterdam:
            return ':flag_nl: ' + str(name)
        if name == discord.VoiceRegion.brazil:
            return ':flag_br: ' + str(name)
        if name == discord.VoiceRegion.dubai:
            return ':flag_ae: ' + str(name)
        if name in {discord.VoiceRegion.eu_central, discord.VoiceRegion.eu_west, discord.VoiceRegion.europe}:
            return ':flag_eu: ' + str(name)
        if name == discord.VoiceRegion.frankfurt:
            return ':flag_de: ' + str(name)
        if name == discord.VoiceRegion.hongkong:
            return ':flag_hk: ' + str(name)
        if name == discord.VoiceRegion.india:
            return ':flag_in: ' + str(name)
        if name == discord.VoiceRegion.japan:
            return ':flag_jp: ' + str(name)
        if name in {discord.VoiceRegion.london, discord.VoiceRegion.vip_amsterdam}:
            return ':flag_gb: ' + str(name)
        if name == discord.VoiceRegion.russia:
            return ':flag_ru: ' + str(name)
        if name == discord.VoiceRegion.singapore:
            return ':flag_sg: ' + str(name)
        if name == discord.VoiceRegion.southafrica:
            return ':flag_za: ' + str(name)
        if name == discord.VoiceRegion.sydney:
            return ':flag_au: ' + str(name)
        if name in {discord.VoiceRegion.us_central, discord.VoiceRegion.us_east, discord.VoiceRegion.us_south, discord.VoiceRegion.us_west, discord.VoiceRegion.vip_us_east, discord.VoiceRegion.vip_us_west}:
            return ':flag_us: ' + str(name)

    @commands.Cog.listener()
    async def on_guild_update(self, before, after):
        if not self.c('server edited', after):
            return
        embed = discord.Embed()
        embed.description = f"**:pencil: Server information updated!**"
        embed.colour = discord.Colour.gold()
        embed.timestamp = datetime.datetime.utcnow()

        if before.name != after.name:
            embed.add_field(name="Name", value=f"{before.name} -> {after.name}", inline=False)
        if before.afk_timeout != after.afk_timeout:
            before_text_afk_timeout = str(before.afk_timeout/60) + ' minute' + 's' if before.afk_timeout//60 != 1 else ''
            after_text_afk_timeout = str(after.afk_timeout/60) + ' minute' + 's' if after.afk_timeout//60 != 1 else ''
            embed.add_field(name="Afk timeout", value=f"{before_text_afk_timeout} -> {after_text_afk_timeout}", inline=False)
        if before.afk_channel != after.afk_channel:
            embed.add_field(name="Afk channel", value=f"`{'#' if before.afk_channel else ''}{before.afk_channel}` -> `{'#' if after.afk_channel else ''}{after.afk_channel}`", inline=False)
        if before.system_channel != after.system_channel:
            embed.add_field(name="System messages channel", value=f"`{before.system_channel}` -> `{after.system_channel}`", inline=False)

        # The region attribute is removed in Discord API v10 and dpy 2.x
        # if before.region != after.region:
        #     embed.add_field(name="Region", value=f"{self.get_region_flag(before.region)} -> "
        #                                      f"{self.get_region_flag(after.region)}", inline=False)

        if before.icon != after.icon:
            if before.icon:
                icon_url = before.icon.url if hasattr(before.icon, "url") else before.icon
                before_url = await self.upload_img(after.id, 'icon', icon_url)
                if before_url:
                    before_url = f'[[before]]({before_url})'
                else:
                    before_url = f'[[before]]({icon_url})'
            else:
                before_url = "None"
            if after.icon:
                after_icon_url = after.icon.url if hasattr(after.icon, "url") else after.icon
                embed.set_thumbnail(url=after_icon_url)
                after_url = f"[[after]]({after_icon_url})"
            else:
                after_url = "None"
            embed.add_field(name="Icon", value=f"{before_url} -> {after_url}", inline=False)

        if before.banner != after.banner:
            if before.banner:
                banner_url = before.banner.url if hasattr(before.banner, "url") else before.banner
                before_url = await self.upload_img(after.id, 'banner', banner_url)
                if before_url:
                    before_url = f'[[before]]({before_url})'
                else:
                    before_url = f'[[before]]({banner_url})'
            else:
                before_url = "None"
            if after.banner:
                after_banner_url = after.banner.url if hasattr(after.banner, "url") else after.banner
                embed.set_image(url=after_banner_url)
                after_url = f"[[after]]({after_banner_url})"
            else:
                after_url = "None"
            embed.add_field(name="Banner", value=f"{before_url} -> {after_url}", inline=False)

        if before.splash != after.splash:
            if before.splash:
                splash_url = before.splash.url if hasattr(before.splash, "url") else before.splash
                before_url = await self.upload_img(after.id, 'splash', splash_url)
                if before_url:
                    before_url = f'[[before]]({before_url})'
                else:
                    before_url = f'[[before]]({splash_url})'
            else:
                before_url = "None"
            if after.splash:
                after_splash_url = after.splash.url if hasattr(after.splash, "url") else after.splash
                embed.set_image(url=after_splash_url)
                after_url = f"[[after]]({after_splash_url})"
            else:
                after_url = "None"
            embed.add_field(name="Invite Splash", value=f"{before_url} -> {after_url}", inline=False)

        if before.verification_level != after.verification_level:
            embed.add_field(name="Verification level", value=f"{before.verification_level} -> {after.verification_level}", inline=False)

        if before.explicit_content_filter != after.explicit_content_filter:
            embed.add_field(name="Explicit content filter", value=f"{before.explicit_content_filter} -> {after.explicit_content_filter}", inline=False)

        if before.mfa_level != after.mfa_level:
            embed.add_field(name="Requires 2FA for admins", value=f"`{'Yes' if after.mfa_level else 'No'}`")
        if len(embed.fields) == 0:
            return

        await self.send_webhook(after, embed=embed)

    @commands.Cog.listener()
    async def on_guild_emojis_update(self, guild, before, after):
        if not self.c('server emoji', guild):
            return

        removed_emojis = set(before) - set(after)
        added_emojis = set(after) - set(before)

        embed = discord.Embed()
        embed.description = f"**:pencil: Server's emojis updated!**"
        embed.colour = discord.Colour.gold()
        embed.timestamp = datetime.datetime.utcnow()

        if added_emojis:
            emoji_text = ''
            for emoji in added_emojis:
                if emoji.animated:
                    emoji_text += f'<a:{emoji.name}:{emoji.id}> `:{emoji.name}:`\n'
                else:
                    emoji_text += f'<:{emoji.name}:{emoji.id}> `:{emoji.name}:`\n'
            embed.add_field(name="Added emojis", value=emoji_text)
        if removed_emojis:
            emoji_text = ''
            for emoji in removed_emojis:
                url = await self.upload_img(emoji.id, 'emoji', emoji.url)
                if url:
                    emoji_text += f'[emoji]({url}) `:{emoji.name}:`\n'
                else:
                    emoji_text += f'`:{emoji.name}:`\n'
            embed.add_field(name="Removed emojis", value=emoji_text)

        if len(embed.fields) == 0:
            return

        await self.send_webhook(guild, embed=embed)

    @commands.Cog.listener()
    async def on_guild_channel_create(self, channel):
        if not self.c('channel create', channel.guild, channel):
            return
        embed = discord.Embed()
        embed.colour = discord.Colour.green()
        embed.timestamp = channel.created_at

        if isinstance(channel, discord.TextChannel):
            embed.description = f"**:pencil2: Text channel created: {channel.mention}**"
            if channel.topic:
                embed.add_field(name="Topic", value=f"{channel.topic}")
        elif isinstance(channel, discord.VoiceChannel):
            embed.description = f"**:pencil2: Voice channel created: `{channel.name}`**"

        if isinstance(channel, discord.CategoryChannel):
            embed.description = f"**:pencil2: Category created: `{channel.name}`**"
            embed.set_footer(text=f'Category ID: {channel.id}')
        else:
            if channel.category:
                embed.add_field(name="Category", value=f"`{channel.category.name}`")
                embed.set_footer(text=f'Channel ID: {channel.id} | Category ID: {channel.category.id}')
            else:
                embed.set_footer(text=f'Channel ID: {channel.id}')

        await self.send_webhook(channel.guild, embed=embed)

        if channel.overwrites and not channel.permissions_synced:
            await self.on_guild_channel_perms_update(None, channel)

    @commands.Cog.listener()
    async def on_guild_channel_update(self, before, after):
        if not self.c('channel update', after.guild, after):
            return

        embed = discord.Embed()
        embed.colour = discord.Colour.gold()
        embed.timestamp = datetime.datetime.utcnow()

        if before.name != after.name:
            embed.add_field(name="Channel renamed", value=f"`{before.name}` -> `{after.name}`", inline=False)

        if isinstance(before, discord.TextChannel):
            embed.description = f"**:pencil: Text channel updated: {before.mention}**"
            if before.topic != after.topic:
                embed.add_field(name="Topic", value=f"{before.topic} -> {after.topic}", inline=False)
            if before.slowmode_delay != after.slowmode_delay:
                if before.slowmode_delay == 0:
                    bsm = 'off'
                elif before.slowmode_delay == 1:
                    bsm = f"{before.slowmode_delay} second"
                else:
                    bsm = f"{before.slowmode_delay} seconds"
                if after.slowmode_delay == 0:
                    asm = 'off'
                elif after.slowmode_delay == 1:
                    asm = f"{after.slowmode_delay} second"
                else:
                    asm = f"{after.slowmode_delay} seconds"
                embed.add_field(name="Slowmode delay", value=f"{bsm} -> {asm}", inline=False)
            if before.is_nsfw() != after.is_nsfw():
                embed.add_field(name="NSFW", value=f"{'Yes' if before.is_nsfw() else 'No'} -> {'Yes' if after.is_nsfw() else 'No'}", inline=False)
            if before.is_news() != after.is_news():
                embed.add_field(name="News", value=f"{'Yes' if before.is_news() else 'No'} -> {'Yes' if after.is_news() else 'No'}", inline=False)

        elif isinstance(before, discord.VoiceChannel):
            embed.description = f"**:pencil: Voice channel updated: `{before.name}`**"
            if before.bitrate != after.bitrate:
                embed.add_field(name="Bitrate", value=f"`{before.bitrate//1000} kbps` -> `{after.bitrate//1000} kbps`", inline=False)
            if before.user_limit != after.user_limit:
                embed.add_field(name="User limit", value=f"`{before.user_limit or 'unlimited'}` -> `{after.user_limit or 'unlimited'}`", inline=False)

        if before.category != after.category:
            embed.add_field(name="Category", value=f"`{before.category}` -> `{after.category}`", inline=False)

        if isinstance(before, discord.CategoryChannel):
            embed.description = f"**:pencil: Category updated: `{before.name}`**"
            embed.set_footer(text=f'Category ID: {after.id}')
            if before.is_nsfw() != after.is_nsfw():
                embed.add_field(name="NSFW",
                                value=f"{'Yes' if before.is_nsfw() else 'No'} -> {'Yes' if after.is_nsfw() else 'No'}",
                                inline=False)
        else:
            embed.set_footer(text=f'Channel ID: {after.id}')

        if len(embed.fields) > 0:
            await self.send_webhook(after.guild, embed=embed)

        await self.on_guild_channel_perms_update(before, after)

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel):
        if not self.c('channel delete', channel.guild, channel):
            return

        embed = discord.Embed()
        embed.colour = discord.Colour.red()
        embed.timestamp = datetime.datetime.utcnow()

        embed.add_field(name="Name", value=channel.name)

        if isinstance(channel, discord.TextChannel):
            embed.description = f"**:wastebasket: Text channel deleted: `#{channel.name}`**"
            if channel.topic:
                embed.add_field(name="Topic", value=f"{channel.topic}")
        elif isinstance(channel, discord.VoiceChannel):
            embed.description = f"**:wastebasket: Voice channel deleted: `{channel.name}`**"

        if isinstance(channel, discord.CategoryChannel):
            embed.description = f"**:wastebasket: Category deleted: `{channel.name}`**"
            embed.set_footer(text=f'Category ID: {channel.id}')
        else:
            if channel.category:
                embed.add_field(name="Category", value=f"`{channel.category.name}`")
                embed.set_footer(text=f'Channel ID: {channel.id} | Category ID: {channel.category.id}')
            else:
                embed.set_footer(text=f'Channel ID: {channel.id}')

        await self.send_webhook(channel.guild, embed=embed)

    @commands.Cog.listener()
    async def on_invite_create(self, invite):
        if invite.guild is None:
            return

        if not self.c('invite create', invite.guild, invite.channel):
            return

        embed = self.user_base_embed(invite.inviter)
        embed.colour = discord.Colour.green()
        embed.timestamp = invite.created_at
        embed.description = f"**:envelope_with_arrow: An invite has been created**"
        embed.add_field(name="Code", value=f"[**{invite.code}**]({invite.url})")
        if hasattr(invite.channel, 'mention'):
            embed.add_field(name="Channel", value=f"{invite.channel.mention}")
            embed.set_footer(text=f"Inviter ID: {invite.inviter.id} | Channel ID: {invite.channel.id}")
        else:
            embed.set_footer(text=f"Inviter ID: {invite.inviter.id}")
        if invite.max_age == 0:
            inv_text = 'Never'
        else:
            inv_text = human_timedelta(relativedelta(seconds=invite.max_age))
        embed.add_field(name="Expires after", value=inv_text)
        embed.add_field(name="Max uses", value="Unlimited" if invite.max_age == 0 else str(invite.max_age))
        if invite.temporary:
            embed.add_field(name="Temporary membership", value=f"`Yes`")

        await self.send_webhook(invite.guild, embed=embed)

    @commands.Cog.listener()
    async def on_invite_delete(self, invite):
        if invite.guild is None:
            return

        if not self.c('invite delete', invite.guild, invite.channel):
            return
        if invite.inviter:
            embed = self.user_base_embed(invite.inviter)
            embed.set_footer(text=f"Inviter ID: {invite.inviter.id}")
        else:
            embed = discord.Embed()
        embed.colour = discord.Colour.red()
        embed.timestamp = datetime.datetime.utcnow()
        embed.description = f"**:wastebasket: An invite has been deleted**"
        embed.add_field(name="Code", value=f"[**{invite.code}**]({invite.url})")
        await self.send_webhook(invite.guild, embed=embed)

    @commands.Cog.listener()
    async def on_guild_member_join(self, member):
        if not self.c('member join', member.guild):
            return
        embed = self.user_base_embed(member, user_update=True)
        embed.colour = discord.Colour.green()
        embed.description = f"**:inbox_tray: {member.mention} ({member.id}) joined the server**"
        embed.add_field(name="Account creation", value=human_timedelta(member.created_at))
        await self.send_webhook(member.guild, embed=embed)

    @commands.Cog.listener()
    async def on_guild_member_leave(self, member):
        if not self.c('member leave', member.guild):
            return
        embed = self.user_base_embed(member, user_update=True)
        embed.colour = discord.Colour.red()
        embed.add_field(name="Joined server", value=human_timedelta(member.joined_at))
        embed.description = f"**:outbox_tray: {member.mention} ({member.id}) left the server**"
        await self.send_webhook(member.guild, embed=embed)

    @commands.Cog.listener()
    async def on_guild_member_ban(self, guild, user):
        if not self.c('member ban', guild):
            return
        embed = self.user_base_embed(user, user_update=True)
        embed.colour = discord.Colour.red()
        embed.description = f"**:man_police_officer: :lock: {user.mention} ({user.id}) was banned**"
        await self.send_webhook(guild, embed=embed)

    @commands.Cog.listener()
    async def on_guild_member_unban(self, guild, user):
        if not self.c('member unban', guild):
            return
        embed = self.user_base_embed(user, user_update=True)
        embed.colour = discord.Colour.green()
        embed.description = f"**:man_police_officer: :unlock: {user.mention} ({user.id}) was unbanned**"
        await self.send_webhook(guild, embed=embed)

    @commands.Cog.listener()
    async def on_guild_role_create(self, role):
        if not self.c('role create', role.guild):
            return
        embed = discord.Embed()
        embed.description = f"**:crossed_swords: Role created: {role.name}**"
        embed.colour = discord.Colour.green()
        embed.timestamp = role.created_at
        embed.set_footer(text=f"ID: {role.id}")
        if role.permissions.value == 0b0:
            embed.add_field(name='Permissions', value='No permissions granted.', inline=False)
        elif role.permissions.value == 0b01111111111111111111111111111111:
            embed.add_field(name='Permissions', value='All permissions granted.', inline=False)
        else:
            embed.add_field(name='Permissions', value=', '.join(
                sorted(p.replace('_', ' ').replace('administrator', '**administrator**')
                       for p, v in (role.permissions
                                    if not role.permissions.administrator else discord.Permissions.all()) if v)
            ), inline=False)
        await self.send_webhook(role.guild, embed=embed)

    @commands.Cog.listener()
    async def on_guild_role_update(self, before, after):
        if not self.c('role update', after.guild):
            return
        embed = discord.Embed()
        if after.is_default():
            embed.description = f"**:pencil: Role updated: @everyone**"
        else:
            embed.description = f"**:pencil: Role updated: {after.mention}**"
            embed.set_footer(text=f"ID: {after.id}")

        embed.colour = discord.Colour.gold()
        embed.timestamp = datetime.datetime.utcnow()
        if before.name != after.name:
            embed.add_field(name="Name", value=f"`{before.name}` -> `{after.name}`", inline=False)
        if before.colour != after.colour:
            embed.add_field(name="Colour",
                            value=f"[#{before.colour.value:0>6x}](https://www.color-hex.com/color/{before.colour.value:0>6x}) -> [#{after.colour.value:0>6x}](https://www.color-hex.com/color/{after.colour.value:0>6x})", inline=False)
        if before.hoist != after.hoist:
            embed.add_field(name="Hoisted", value=f"`{'Yes' if before.hoist else 'No'}` -> "
                                                  f"`{'Yes' if after.hoist else 'No'}`", inline=False)
        if before.mentionable != after.mentionable:
            embed.add_field(name="Mentionable", value=f"`{'Yes' if before.mentionable else 'No'}` -> "
                                                      f"`{'Yes' if after.mentionable else 'No'}`", inline=False)

        added_perms = set()
        removed_perms = set()
        for p, v in before.permissions:
            if not v and getattr(after.permissions, p):
                added_perms.add(p)
            elif v and not getattr(after.permissions, p):
                removed_perms.add(p)

        if added_perms:
            embed.add_field(name='✓ Allowed permissions', value=', '.join(
                sorted(p.replace('_', ' ').replace('administrator', '**administrator**') for p in added_perms)
            ), inline=False)
        if removed_perms:
            embed.add_field(name='✘ Denied permissions', value=', '.join(
                sorted(p.replace('_', ' ').replace('administrator', '**administrator**') for p in removed_perms)
            ), inline=False)
        if len(embed.fields) == 0:
            return
        await self.send_webhook(after.guild, embed=embed)

    @commands.Cog.listener()
    async def on_guild_role_delete(self, role):
        if not self.c('role delete', role.guild):
            return

        embed = discord.Embed()
        embed.description = f"**:wastebasket: Role deleted: {role.name}**"
        embed.colour = discord.Colour.red()
        embed.timestamp = datetime.datetime.utcnow()
        embed.set_footer(text=f"ID: {role.id}")
        embed.add_field(name="Colour", value=f"[#{role.colour.value:0>6x}](https://www.color-hex.com/color/{role.colour.value:0>6x})")
        embed.add_field(name="Hoisted", value=f"`{'Yes' if role.hoist else 'No'}`")
        embed.add_field(name="Mentionable", value=f"`{'Yes' if role.mentionable else 'No'}`")

        if role.permissions.value == 0b0:
            embed.add_field(name='Permissions', value='No permissions granted.', inline=False)
        elif role.permissions.value == 0b01111111111111111111111111111111:
            embed.add_field(name='Permissions', value='All permissions granted.', inline=False)
        else:
            embed.add_field(name='Permissions', value=', '.join(
                sorted(p.replace('_', ' ').replace('administrator', '**administrator**')
                       for p, v in role.permissions if v)
            ), inline=False)

        await self.send_webhook(role.guild, embed=embed)

    def get_region_flag(self, name):
        if isinstance(name, str):
            return name
        if name == discord.VoiceRegion.amsterdam:
            return ':flag_nl: ' + str(name)
        if name == discord.VoiceRegion.brazil:
            return ':flag_br: ' + str(name)
        if name == discord.VoiceRegion.dubai:
            return ':flag_ae: ' + str(name)
        if name in {discord.VoiceRegion.eu_central, discord.VoiceRegion.eu_west, discord.VoiceRegion.europe}:
            return ':flag_eu: ' + str(name)
        if name == discord.VoiceRegion.frankfurt:
            return ':flag_de: ' + str(name)
        if name == discord.VoiceRegion.hongkong:
            return ':flag_hk: ' + str(name)
        if name == discord.VoiceRegion.india:
            return ':flag_in: ' + str(name)
        if name == discord.VoiceRegion.japan:
            return ':flag_jp: ' + str(name)
        if name in {discord.VoiceRegion.london, discord.VoiceRegion.vip_amsterdam}:
            return ':flag_gb: ' + str(name)
        if name == discord.VoiceRegion.russia:
            return ':flag_ru: ' + str(name)
        if name == discord.VoiceRegion.singapore:
            return ':flag_sg: ' + str(name)
        if name == discord.VoiceRegion.southafrica:
            return ':flag_za: ' + str(name)
        if name == discord.VoiceRegion.sydney:
            return ':flag_au: ' + str(name)
        if name in {discord.VoiceRegion.us_central, discord.VoiceRegion.us_east, discord.VoiceRegion.us_south, discord.VoiceRegion.us_west, discord.VoiceRegion.vip_us_east, discord.VoiceRegion.vip_us_west}:
            return ':flag_us: ' + str(name)

    @commands.Cog.listener()
    async def on_guild_update(self, before, after):
        if not self.c('server edited', after):
            return
        embed = discord.Embed()
        embed.description = f"**:pencil: Server information updated!**"
        embed.colour = discord.Colour.gold()
        embed.timestamp = datetime.datetime.utcnow()

        if before.name != after.name:
            embed.add_field(name="Name", value=f"{before.name} -> {after.name}", inline=False)
        if before.afk_timeout != after.afk_timeout:
            before_text_afk_timeout = str(before.afk_timeout/60) + ' minute' + 's' if before.afk_timeout//60 != 1 else ''
            after_text_afk_timeout = str(after.afk_timeout/60) + ' minute' + 's' if after.afk_timeout//60 != 1 else ''
            embed.add_field(name="Afk timeout", value=f"{before_text_afk_timeout} -> {after_text_afk_timeout}", inline=False)
        if before.afk_channel != after.afk_channel:
            embed.add_field(name="Afk channel", value=f"`{'#' if before.afk_channel else ''}{before.afk_channel}` -> `{'#' if after.afk_channel else ''}{after.afk_channel}`", inline=False)
        if before.system_channel != after.system_channel:
            embed.add_field(name="System messages channel", value=f"`{before.system_channel}` -> `{after.system_channel}`", inline=False)

        # The region attribute is removed in Discord API v10 and dpy 2.x
        # if before.region != after.region:
        #     embed.add_field(name="Region", value=f"{self.get_region_flag(before.region)} -> "
        #                                      f"{self.get_region_flag(after.region)}", inline=False)

        if before.icon != after.icon:
            if before.icon:
                icon_url = before.icon.url if hasattr(before.icon, "url") else before.icon
                before_url = await self.upload_img(after.id, 'icon', icon_url)
                if before_url:
                    before_url = f'[[before]]({before_url})'
                else:
                    before_url = f'[[before]]({icon_url})'
            else:
                before_url = "None"
            if after.icon:
                after_icon_url = after.icon.url if hasattr(after.icon, "url") else after.icon
                embed.set_thumbnail(url=after_icon_url)
                after_url = f"[[after]]({after_icon_url})"
            else:
                after_url = "None"
            embed.add_field(name="Icon", value=f"{before_url} -> {after_url}", inline=False)

        if before.banner != after.banner:
            if before.banner:
                banner_url = before.banner.url if hasattr(before.banner, "url") else before.banner
                before_url = await self.upload_img(after.id, 'banner', banner_url)
                if before_url:
                    before_url = f'[[before]]({before_url})'
                else:
                    before_url = f'[[before]]({banner_url})'
            else:
                before_url = "None"
            if after.banner:
                after_banner_url = after.banner.url if hasattr(after.banner, "url") else after.banner
                embed.set_image(url=after_banner_url)
                after_url = f"[[after]]({after_banner_url})"
            else:
                after_url = "None"
            embed.add_field(name="Banner", value=f"{before_url} -> {after_url}", inline=False)

        if before.splash != after.splash:
            if before.splash:
                splash_url = before.splash.url if hasattr(before.splash, "url") else before.splash
                before_url = await self.upload_img(after.id, 'splash', splash_url)
                if before_url:
                    before_url = f'[[before]]({before_url})'
                else:
                    before_url = f'[[before]]({splash_url})'
            else:
                before_url = "None"
            if after.splash:
                after_splash_url = after.splash.url if hasattr(after.splash, "url") else after.splash
                embed.set_image(url=after_splash_url)
                after_url = f"[[after]]({after_splash_url})"
            else:
                after_url = "None"
            embed.add_field(name="Invite Splash", value=f"{before_url} -> {after_url}", inline=False)

        if before.verification_level != after.verification_level:
            embed.add_field(name="Verification level", value=f"{before.verification_level} -> {after.verification_level}", inline=False)

        if before.explicit_content_filter != after.explicit_content_filter:
            embed.add_field(name="Explicit content filter", value=f"{before.explicit_content_filter} -> {after.explicit_content_filter}", inline=False)

        if before.mfa_level != after.mfa_level:
            embed.add_field(name="Requires 2FA for admins", value=f"`{'Yes' if after.mfa_level else 'No'}`")
        if len(embed.fields) == 0:
            return

        await self.send_webhook(after, embed=embed)

    @commands.Cog.listener()
    async def on_guild_emojis_update(self, guild, before, after):
        if not self.c('server emoji', guild):
            return

        removed_emojis = set(before) - set(after)
        added_emojis = set(after) - set(before)

        embed = discord.Embed()
        embed.description = f"**:pencil: Server's emojis updated!**"
        embed.colour = discord.Colour.gold()
        embed.timestamp = datetime.datetime.utcnow()

        if added_emojis:
            emoji_text = ''
            for emoji in added_emojis:
                if emoji.animated:
                    emoji_text += f'<a:{emoji.name}:{emoji.id}> `:{emoji.name}:`\n'
                else:
                    emoji_text += f'<:{emoji.name}:{emoji.id}> `:{emoji.name}:`\n'
            embed.add_field(name="Added emojis", value=emoji_text)
        if removed_emojis:
            emoji_text = ''
            for emoji in removed_emojis:
                url = await self.upload_img(emoji.id, 'emoji', emoji.url)
                if url:
                    emoji_text += f'[emoji]({url}) `:{emoji.name}:`\n'
                else:
                    emoji_text += f'`:{emoji.name}:`\n'
            embed.add_field(name="Removed emojis", value=emoji_text)

        if len(embed.fields) == 0:
            return

        await self.send_webhook(guild, embed=embed)

    @commands.Cog.listener()
    async def on_guild_channel_create(self, channel):
        if not self.c('channel create', channel.guild, channel):
            return
        embed = discord.Embed()
        embed.colour = discord.Colour.green()
        embed.timestamp = channel.created_at

        if isinstance(channel, discord.TextChannel):
            embed.description = f"**:pencil2: Text channel created: {channel.mention}**"
            if channel.topic:
                embed.add_field(name="Topic", value=f"{channel.topic}")
        elif isinstance(channel, discord.VoiceChannel):
            embed.description = f"**:pencil2: Voice channel created: `{channel.name}`**"

        if isinstance(channel, discord.CategoryChannel):
            embed.description = f"**:pencil2: Category created: `{channel.name}`**"
            embed.set_footer(text=f'Category ID: {channel.id}')
        else:
            if channel.category:
                embed.add_field(name="Category", value=f"`{channel.category.name}`")
                embed.set_footer(text=f'Channel ID: {channel.id} | Category ID: {channel.category.id}')
            else:
                embed.set_footer(text=f'Channel ID: {channel.id}')

        await self.send_webhook(channel.guild, embed=embed)

        if channel.overwrites and not channel.permissions_synced:
            await self.on_guild_channel_perms_update(None, channel)

    @commands.Cog.listener()
    async def on_guild_channel_update(self, before, after):
        if not self.c('channel update', after.guild, after):
            return

        embed = discord.Embed()
        embed.colour = discord.Colour.gold()
        embed.timestamp = datetime.datetime.utcnow()

        if before.name != after.name:
            embed.add_field(name="Channel renamed", value=f"`{before.name}` -> `{after.name}`", inline=False)

        if isinstance(before, discord.TextChannel):
            embed.description = f"**:pencil: Text channel updated: {before.mention}**"
            if before.topic != after.topic:
                embed.add_field(name="Topic", value=f"{before.topic} -> {after.topic}", inline=False)
            if before.slowmode_delay != after.slowmode_delay:
                if before.slowmode_delay == 0:
                    bsm = 'off'
                elif before.slowmode_delay == 1:
                    bsm = f"{before.slowmode_delay} second"
                else:
                    bsm = f"{before.slowmode_delay} seconds"
                if after.slowmode_delay == 0:
                    asm = 'off'
                elif after.slowmode_delay == 1:
                    asm = f"{after.slowmode_delay} second"
                else:
                    asm = f"{after.slowmode_delay} seconds"
                embed.add_field(name="Slowmode delay", value=f"{bsm} -> {asm}", inline=False)
            if before.is_nsfw() != after.is_nsfw():
                embed.add_field(name="NSFW", value=f"{'Yes' if before.is_nsfw() else 'No'} -> {'Yes' if after.is_nsfw() else 'No'}", inline=False)
            if before.is_news() != after.is_news():
                embed.add_field(name="News", value=f"{'Yes' if before.is_news() else 'No'} -> {'Yes' if after.is_news() else 'No'}", inline=False)

        elif isinstance(before, discord.VoiceChannel):
            embed.description = f"**:pencil: Voice channel updated: `{before.name}`**"
            if before.bitrate != after.bitrate:
                embed.add_field(name="Bitrate", value=f"`{before.bitrate//1000} kbps` -> `{after.bitrate//1000} kbps`", inline=False)
            if before.user_limit != after.user_limit:
                embed.add_field(name="User limit", value=f"`{before.user_limit or 'unlimited'}` -> `{after.user_limit or 'unlimited'}`", inline=False)

        if before.category != after.category:
            embed.add_field(name="Category", value=f"`{before.category}` -> `{after.category}`", inline=False)

        if isinstance(before, discord.CategoryChannel):
            embed.description = f"**:pencil: Category updated: `{before.name}`**"
            embed.set_footer(text=f'Category ID: {after.id}')
            if before.is_nsfw() != after.is_nsfw():
                embed.add_field(name="NSFW",
                                value=f"{'Yes' if before.is_nsfw() else 'No'} -> {'Yes' if after.is_nsfw() else 'No'}",
                                inline=False)
        else:
            embed.set_footer(text=f'Channel ID: {after.id}')

        if len(embed.fields) > 0:
            await self.send_webhook(after.guild, embed=embed)

        await self.on_guild_channel_perms_update(before, after)

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel):
        if not self.c('channel delete', channel.guild, channel):
            return

        embed = discord.Embed()
        embed.colour = discord.Colour.red()
        embed.timestamp = datetime.datetime.utcnow()

        embed.add_field(name="Name", value=channel.name)

        if isinstance(channel, discord.TextChannel):
            embed.description = f"**:wastebasket: Text channel deleted: `#{channel.name}`**"
            if channel.topic:
                embed.add_field(name="Topic", value=f"{channel.topic}")
        elif isinstance(channel, discord.VoiceChannel):
            embed.description = f"**:wastebasket: Voice channel deleted: `{channel.name}`**"

        if isinstance(channel, discord.CategoryChannel):
            embed.description = f"**:wastebasket: Category deleted: `{channel.name}`**"
            embed.set_footer(text=f'Category ID: {channel.id}')
        else:
            if channel.category:
                embed.add_field(name="Category", value=f"`{channel.category.name}`")
                embed.set_footer(text=f'Channel ID: {channel.id} | Category ID: {channel.category.id}')
            else:
                embed.set_footer(text=f'Channel ID: {channel.id}')

        await self.send_webhook(channel.guild, embed=embed)

    @commands.Cog.listener()
    async def on_invite_create(self, invite):
        if invite.guild is None:
            return

        if not self.c('invite create', invite.guild, invite.channel):
            return

        embed = self.user_base_embed(invite.inviter)
        embed.colour = discord.Colour.green()
        embed.timestamp = invite.created_at
        embed.description = f"**:envelope_with_arrow: An invite has been created**"
        embed.add_field(name="Code", value=f"[**{invite.code}**]({invite.url})")
        if hasattr(invite.channel, 'mention'):
            embed.add_field(name="Channel", value=f"{invite.channel.mention}")
            embed.set_footer(text=f"Inviter ID: {invite.inviter.id} | Channel ID: {invite.channel.id}")
        else:
            embed.set_footer(text=f"Inviter ID: {invite.inviter.id}")
        if invite.max_age == 0:
            inv_text = 'Never'
        else:
            inv_text = human_timedelta(relativedelta(seconds=invite.max_age))
        embed.add_field(name="Expires after", value=inv_text)
        embed.add_field(name="Max uses", value="Unlimited" if invite.max_age == 0 else str(invite.max_age))
        if invite.temporary:
            embed.add_field(name="Temporary membership", value=f"`Yes`")

        await self.send_webhook(invite.guild, embed=embed)

    @commands.Cog.listener()
    async def on_invite_delete(self, invite):
        if invite.guild is None:
            return

        if not self.c('invite delete', invite.guild, invite.channel):
            return
        if invite.inviter:
            embed = self.user_base_embed(invite.inviter)
            embed.set_footer(text=f"Inviter ID: {invite.inviter.id}")
        else:
            embed = discord.Embed()
        embed.colour = discord.Colour.red()
        embed.timestamp = datetime.datetime.utcnow()
        embed.description = f"**:wastebasket: An invite has been deleted**"
        embed.add_field(name="Code", value=f"[**{invite.code}**]({invite.url})")
        await self.send_webhook(invite.guild, embed=embed)

    @audit.command(name='setup_logging')
    @commands.has_guild_permissions(administrator=True)
    async def setup_logging(self, ctx):
        """Setup the Audit logs category and logging channels."""
        guild = ctx.guild
        # Try to get by stored ID first
        doc = self.store.get_guild(guild.id)
        category = None
        if doc.get('log_category_id'):
            category = discord.utils.get(guild.categories, id=doc['log_category_id'])
        if not category:
            category = discord.utils.get(guild.categories, name=self.LOG_CATEGORY_NAME)
        if not category:
            category = await guild.create_category(self.LOG_CATEGORY_NAME, reason="Setup audit logging category")
        channel = None
        if doc.get('log_channel_id'):
            channel = discord.utils.get(category.channels, id=doc['log_channel_id'])
        if not channel:
            channel = discord.utils.get(category.channels, name=self.LOG_CHANNEL_NAME)
        if not channel:
            overwrites = {
                guild.default_role: discord.PermissionOverwrite(read_messages=False),
                guild.me: discord.PermissionOverwrite(read_messages=True)
            }
            channel = await guild.create_text_channel(self.LOG_CHANNEL_NAME, category=category, overwrites=overwrites, reason="Setup audit logging channel")
        # Save category and channel IDs in MongoDB
        self.store.update_guild(guild.id, {'log_category_id': category.id, 'log_channel_id': channel.id})
        await ctx.send(embed=discord.Embed(description=f"Setup complete! Category: {category.mention}, Channel: {channel.mention}", colour=discord.Colour.green()))

    @audit.command(name='show_config')
    async def show_config(self, ctx):
        doc = self.store.get_guild(ctx.guild.id)
        desc = f"**Enabled types:** {', '.join(doc.get('enabled', []))}\n"
        desc += f"**Ignored channels:** {', '.join(str(cid) for cid in doc.get('ignored_channel_ids', []))}\n"
        desc += f"**Ignored categories:** {', '.join(str(cid) for cid in doc.get('ignored_category_ids', []))}\n"
        desc += f"**Log category ID:** {doc.get('log_category_id', 'Not set')}\n"
        desc += f"**Log channel ID:** {doc.get('log_channel_id', 'Not set')}"
        await ctx.send(embed=discord.Embed(description=desc, colour=discord.Colour.blue()))

    @audit.command(name='reset_config')
    @commands.has_guild_permissions(administrator=True)
    async def reset_config(self, ctx):
        self.store.set_guild(ctx.guild.id, {'enabled': [], 'ignored_channel_ids': [], 'ignored_category_ids': []})
        await ctx.send(embed=discord.Embed(description="Audit config reset!", colour=discord.Colour.red()))

    @audit.command(name='list_ignored')
    async def list_ignored(self, ctx):
        doc = self.store.get_guild(ctx.guild.id)
        channels = doc.get('ignored_channel_ids', [])
        categories = doc.get('ignored_category_ids', [])
        desc = f"**Ignored channels:** {', '.join(str(cid) for cid in channels)}\n"
        desc += f"**Ignored categories:** {', '.join(str(cid) for cid in categories)}"
        await ctx.send(embed=discord.Embed(description=desc, colour=discord.Colour.orange()))

    @commands.Cog.listener()
    async def on_auto_moderation_action_execution(self, execution: discord.AutoModActionExecution):
        # See: https://discordpy.readthedocs.io/en/stable/api.html#discord.on_auto_moderation_action_execution
        if not self.c('automod action', execution.guild):
            return
        embed = discord.Embed()
        embed.colour = discord.Colour.orange()
        embed.timestamp = datetime.datetime.utcnow()
        embed.title = ':shield: AutoMod Action Executed'
        # Action type
        embed.add_field(name='Action Type', value=str(getattr(execution.action, 'type', 'Unknown')), inline=True)
        # Rule ID and Trigger Type
        embed.add_field(name='Rule ID', value=str(getattr(execution, 'rule_id', 'Unknown')), inline=True)
        embed.add_field(name='Rule Trigger Type', value=str(getattr(execution, 'rule_trigger_type', 'Unknown')), inline=True)
        # User
        user = getattr(execution, 'user', None)
        if user:
            embed.add_field(name='User', value=f'{user.mention} ({user.id})', inline=True)
        else:
            user_id = getattr(execution, 'user_id', None)
            if user_id:
                embed.add_field(name='User ID', value=str(user_id), inline=True)
        # Channel
        channel = getattr(execution, 'channel', None)
        if channel:
            embed.add_field(name='Channel', value=channel.mention, inline=True)
        else:
            channel_id = getattr(execution, 'channel_id', None)
            if channel_id:
                embed.add_field(name='Channel ID', value=str(channel_id), inline=True)
        # Message
        message = getattr(execution, 'message', None)
        if message:
            embed.add_field(name='Message', value=f'[Jump to Message]({message.jump_url})', inline=False)
        else:
            message_id = getattr(execution, 'message_id', None)
            if message_id:
                embed.add_field(name='Message ID', value=str(message_id), inline=False)
        # Alert Message
        alert_message = getattr(execution, 'alert_message', None)
        if alert_message:
            embed.add_field(name='Alert Message', value=f'[Jump to Alert]({alert_message.jump_url})', inline=False)
        else:
            alert_message_id = getattr(execution, 'alert_message_id', None)
            if alert_message_id:
                embed.add_field(name='Alert Message ID', value=str(alert_message_id), inline=False)
        # Content
        content = getattr(execution, 'content', None)
        if content:
            embed.add_field(name='Content', value=content[:1024], inline=False)
        # Matched Keyword/Content
        matched_keyword = getattr(execution, 'matched_keyword', None)
        if matched_keyword:
            embed.add_field(name='Matched Keyword', value=str(matched_keyword), inline=True)
        matched_content = getattr(execution, 'matched_content', None)
        if matched_content:
            embed.add_field(name='Matched Content', value=str(matched_content)[:1024], inline=False)
        await self.send_webhook(execution.guild, embed=embed)


async def setup(bot):
    """Setup function for the Audit cog."""
    await bot.add_cog(Audit(bot))

def class_docstring_patch():
    pass

Audit.__doc__ = """Audit logging and moderation events for this server. Logs message edits, deletions, member updates, automod actions, and more. Use the audit command group for configuration."""

# 3. Ensure @audit group and all commands have docstrings
# (Most commands already have docstrings, but ensure @audit group does)
Audit.audit.__doc__ = """Audit log configuration and management commands. Use subcommands to enable, disable, ignore, or setup logging."""

# 4. Add a docstring to setup_logging if missing
Audit.setup_logging.__doc__ = """Setup the Audit logs category and logging channels."""
