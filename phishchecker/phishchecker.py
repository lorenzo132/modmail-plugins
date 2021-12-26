import datetime
import json
import re
from typing import Any, Dict

import aiohttp
import discord
from core.models import getLogger  # type: ignore
from discord.ext import commands

log = getLogger(__name__)

# https://github.com/Cog-Creators/Red-DiscordBot/blob/7abc9bdcf16c9d844978f7743aa86d664deeabef/redbot/core/utils/common_filters.py#L17
URL_RE = re.compile(r"(https?|s?ftp)://(\S+)", re.I)

# https://github.com/Cog-Creators/Red-DiscordBot/blob/7abc9bdcf16c9d844978f7743aa86d664deeabef/redbot/core/utils/chat_formatting.py#L106
def box(text: str, lang: str = "") -> str:
    """Get the given text in a code block."""
    ret = "```{}\n{}\n```".format(lang, text)
    return ret


class PhishingDeleter(commands.Cog):
    """A cog which checks for scam links in messages and deletes them if its one.\n**Author:** kato#0666 & sora#0666"""

    __version__ = "1.2.0"
    # https://github.com/Jerrie-Aries/modmail-plugins/blob/d61e8918f293c83f32e6e3f4c2fa4e079a14d452/invites/invites.py#L29
    _id = "config"
    default_config = {
        "enabled": False,
        "channel": None,
        "action": None,
    }

    def __init__(self, bot):
        self.bot = bot
        self._config_cache: Dict[str, Any] = {}
        self.db = bot.api.get_plugin_partition(self)
        self.bot.loop.create_task(self.populate_config_cache())
        self.session = aiohttp.ClientSession(json_serialize=json.dumps)

    def cog_unload(self):
        self.bot.loop.create_task(self.session.close())

    def _format_log_embed(
        self, user: discord.Member, message: discord.Message, response: str
    ):
        """Format an embed to be sent into log channels."""
        embed = discord.Embed(color=discord.Color.red())
        embed.set_author(name=str(user), icon_url=user.avatar_url)
        embed.timestamp = datetime.datetime.now(datetime.timezone.utc)
        embed.description = f"Message from {user.mention} deleted in {message.channel.mention}.\nIt was sent on <t:{int(message.created_at.replace(tzinfo=datetime.timezone.utc).timestamp())}:F>."
        embed.add_field(name="Message Content", value=message.content, inline=False)
        embed.add_field(name="Suspicious Links", value=box(response[:1024], "json"), inline=False)
        embed.set_footer(text=f"User ID: {user.id}\nScamChecker: v{self.__version__}")
        return embed

    # https://github.com/Jerrie-Aries/modmail-plugins/blob/d61e8918f293c83f32e6e3f4c2fa4e079a14d452/invites/invites.py#L76https://github.com/Jerrie-Aries/modmail-plugins/blob/d61e8918f293c83f32e6e3f4c2fa4e079a14d452/invites/invites.py#L76
    def guild_config(self, guild_id: str):
        config = self._config_cache.get(guild_id)
        if config is None:
            config = {k: v for k, v in self.default_config.items()}
            self._config_cache[guild_id] = config

        return config

    async def config_update(self):
        """Update db maybe."""
        await self.db.find_one_and_update(
            {"_id": self._id},
            {"$set": self._config_cache},
            upsert=True,
        )

    # https://github.com/Jerrie-Aries/modmail-plugins/blob/d61e8918f293c83f32e6e3f4c2fa4e079a14d452/invites/invites.py#L57
    async def populate_config_cache(self):
        """
        Populates the config cache with data from database.
        """
        db_config = await self.db.find_one({"_id": self._id})
        if db_config is None:
            db_config = {}  # empty dict, so we can use `.get` method without error

        to_update = False
        for guild in self.bot.guilds:
            config = db_config.get(str(guild.id))
            if config is None:
                config = {k: v for k, v in self.default_config.items()}
                to_update = True
            self._config_cache[str(guild.id)] = config

        if to_update:
            await self.config_update()

    async def _scam_link_check(self, content: str) -> bool:
        """
        Checks if a message contains a scam link.
        """
        async with self.session.get(
            f"https://anti-fish.harmony.rocks/?url={content}"
        ) as resp:
            if resp.status != 200:
                return False, []
            try:
                data = await resp.json()
                if data["match"]:
                    return data["match"], data["matches"]
                return False, []
            except Exception:
                return False, []  # it returned an unkown response so idk man

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:

        if message.guild is None:
            return

        if message.author.bot:
            return

        guild_config = self.guild_config(str(message.guild.id))

        if not guild_config["enabled"]:
            return

        _check = URL_RE.search(message.content)
        
        if not _check:
            return  # doesn't contain a link
        scam = _check.group(0)
        match, matches = await self._scam_link_check(scam)
        if not match:
            return
        try:
            await message.delete()
        except Exception as e:
            log.error(f"Failed to delete message: {e}")
            return
        log_chan = (
            None
            if not guild_config["channel"]
            else message.guild.get_channel(int(guild_config["channel"]))
        )
        if log_chan:
            await log_chan.send(
                embed=self._format_log_embed(message.author, message, json.dumps(matches, indent=4))
            )
        action = guild_config["action"]
        if not action:
            return
        if action == "kick":
            try:
                await message.author.kick(
                    reason=f"ScamChecker: sent a suspicious link in #{message.channel.name} | {message.channel.id}"
                )
            except Exception as e:
                if log_chan:
                    await log_chan.send(
                        embed=discord.Embed(
                            title="Kick - Error",
                            description=f"Couldn't kick {message.author.mention} - {message.author.id}\nError: {e}",
                            color=discord.Color.red(),
                        )
                    )
                log.error(f"Failed to kick user: {e}")
                return
            if log_chan:
                await log_chan.send(
                    embed=discord.Embed(
                        title="Kick",
                        description=f"{message.author.mention} - `{message.author.id}` has been kicked for sending suspicious links.",
                        color=discord.Color.red(),
                    )
                )
        else:
            try:
                await message.author.ban(
                    reason=f"ScamChecker: sent a suspicious link in #{message.channel.name} | {message.channel.id}"
                )
            except Exception as e:
                if log_chan:
                    await log_chan.send(
                        embed=discord.Embed(
                            title="Ban - Error",
                            description=f"Couldn't ban {message.author.mention} - {message.author.id}\nError: {e}",
                            color=discord.Color.red(),
                        )
                    )
                log.error(f"Failed to ban user: {e}")
                return

            if log_chan:
                await log_chan.send(
                    embed=discord.Embed(
                        title="Ban",
                        description=f"{message.author.mention} - `{message.author.id}` has been banned for sending suspicious links.",
                        color=discord.Color.red(),
                    )
                )

    @commands.group()
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    @commands.bot_has_permissions(manage_messages=True)
    async def scamchecker(self, ctx: commands.Context):
        """Manage the scam checker cog."""

    @scamchecker.command()
    async def toggle(self, ctx: commands.Context):
        """Toggle the scam checker."""

        config = self.guild_config(str(ctx.guild.id))
        new_config = dict(enabled=True)
        config.update(new_config)
        await self.config_update()
        await ctx.send("Scam checker is now enabled.")

    @scamchecker.command()
    async def logchannel(self, ctx: commands.Context, channel: discord.TextChannel):
        """Set the log channel for scam links. It is optional to do so, only need to toggle with `[p]scamchecker toggle` for it to work."""
        config = self.guild_config(str(ctx.guild.id))
        new_config = dict(channel=str(channel.id))
        config.update(new_config)
        await self.config_update()
        await ctx.send(f"Log channel set to {channel.mention}.")

    @scamchecker.command()
    @commands.bot_has_permissions(kick_members=True, ban_members=True)
    async def action(self, ctx: commands.Context, action: str):
        """Set the action for scam links. It is optional to do so, only need to toggle with `[p]scamchecker toggle` for it to work."""
        if action not in ["kick", "ban"]:
            await ctx.send("Invalid action. Valid actions are `kick` and `ban`.")
            return
        config = self.guild_config(str(ctx.guild.id))
        new_config = dict(action=action)
        config.update(new_config)
        await self.config_update()
        await ctx.send(f"Action set to {action}.")

    @commands.command()
    @commands.has_permissions(manage_messages=True)
    async def scamcheck(
        self, ctx: commands.Context, *, link: str
    ):
        """Check if a link is phishy!"""
        links = URL_RE.search(link)
        if not links:
            return await ctx.send("Message doesn't contain any links.")
        match, matches = await self._scam_link_check(links.group(0))
        if not match:
            return await ctx.send("Message doesn't contain any links which maybe be phish or scam.")
        await ctx.send(
            f"The message contains a suspicious link.\n**Content:** {box(json.dumps(matches, indent=4), 'json')}"
        )


def setup(bot):
    cog = PhishingDeleter(bot)
    bot.add_cog(cog)
