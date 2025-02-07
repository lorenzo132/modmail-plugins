from __future__ import annotations

import asyncio
import copy
from datetime import datetime
from typing import TYPE_CHECKING, Union, Optional, cast

import discord
from discord.channel import CategoryChannel
from discord.ext import commands

from core import checks
from core.models import DummyMessage, PermissionLevel, getLogger

if TYPE_CHECKING:
    from bot import ModmailBot
    from core.thread import Thread

logger = getLogger(__name__)

class Questions(commands.Cog):
    """Reaction-based menu for threads"""

    def __init__(self, bot: ModmailBot):
        self.bot = bot
        self.db = self.bot.plugin_db.get_partition(self)

    async def wait_for_channel_response(self, channel: discord.TextChannel,
                                        member: discord.Member, *, timeout: int = 15) -> Optional[discord.Message]:
        try:
            return await self.bot.wait_for(
                'message',
                check=lambda m: m.channel == channel and m.author == member,
                timeout=timeout
            )
        except asyncio.TimeoutError:
            return None

    async def wait_for_dm_response(self, user: discord.User, *, timeout: int = 15) -> Optional[discord.Message]:
        try:
            return await self.bot.wait_for(
                'message',
                check=lambda m: isinstance(m.channel, discord.DMChannel) and m.author == user,
                timeout=timeout
            )
        except asyncio.TimeoutError:
            return None

    @commands.Cog.listener()
    async def on_thread_ready(self, thread: Thread,
                              creator: Union[discord.Member, discord.User, None],
                              category: Optional[discord.CategoryChannel],
                              initial_message: Optional[discord.Message]):
        """Handles the thread readiness event and initiates the question process."""
        config = await self.db.find_one({'_id': 'config'}) or {}
        if not config.get('questions'):
            logger.info("No questions configured.")
            return

        responses = {}
        q_message = cast(discord.Message, DummyMessage(copy.copy(initial_message)))
        q_message.author = self.bot.modmail_guild.me

        # Get the timeout value from config or use the default of 15 minutes
        timeout = int(config.get('timeout', 15 * 60))  # default to 15 minutes (900 seconds)

        for question in config['questions']:
            q_message.content = question
            await thread.reply(q_message)

            m = await self.wait_for_dm_response(thread.recipient, timeout=timeout)
            if not m:
                await thread.close(
                    closer=self.bot.modmail_guild.me,
                    message='Closed due to inactivity and not responding to questions.'
                )
                return

            answer = m.content.strip() if m.content.strip() else "<No Message Content>"
            if m.attachments:
                attachment_details = "\n".join(
                    f"`{attachment.filename}`: {attachment.url}" for attachment in m.attachments
                )
                answer += f"\n{attachment_details}"

            responses[question] = answer

        embed = discord.Embed(color=self.bot.main_color, timestamp=datetime.utcnow())
        for question, answer in responses.items():
            embed.add_field(name=question, value=answer, inline=False)
        embed.set_author(name=thread.recipient.name, icon_url=thread.recipient.avatar.url)

        message = await thread.channel.send(embed=embed)
        await message.pin()

        # Get the review message from config or use the default
        review_message = config.get('review_message', 
            'Your appeal will now be reviewed by our moderation team. '
            'If you have new information to share about this case, please reply to this message.'
        )
        
        q_message.content = review_message
        await thread.reply(q_message)

        move_to = self.bot.get_channel(int(config['move_to']))
        if not move_to:
            logger.warning("Move-to category does not exist. Not moving.")
        else:
            try:
                await thread.channel.edit(category=move_to, sync_permissions=True)
            except discord.HTTPException as e:
                logger.error(f"Failed to move thread: {e}")

    @checks.has_permissions(PermissionLevel.MODERATOR)
    @commands.command()
    async def configquestions(self, ctx, *, move_to: CategoryChannel):
        """Configures the questions plugin."""
        questions = []
        await ctx.send('How many questions do you have?')

        m = await self.wait_for_channel_response(ctx.channel, ctx.author)
        if not m:
            return await ctx.send('Timed out.')

        try:
            count = int(m.content)
        except ValueError:
            return await ctx.send('Invalid input. Please enter a number.')

        for i in range(1, count + 1):
            await ctx.send(f"What's question #{i}?")
            m = await self.wait_for_channel_response(ctx.channel, ctx.author)
            if not m:
                return await ctx.send('Timed out.')
            if not m.content.strip():
                return await ctx.send('Question must be text-only.')
            questions.append(m.content.strip())

        await ctx.send('What is the timeout for responses (in minutes)?')
        m = await self.wait_for_channel_response(ctx.channel, ctx.author)
        if not m:
            return await ctx.send('Timed out.')
        
        try:
            timeout_minutes = int(m.content)
            if timeout_minutes <= 0:
                return await ctx.send('Timeout must be a positive number.')
            timeout_seconds = timeout_minutes * 60
        except ValueError:
            return await ctx.send('Invalid input. Please enter a valid number.')

        await ctx.send('What should the review message say?')
        m = await self.wait_for_channel_response(ctx.channel, ctx.author)
        if not m:
            return await ctx.send('Timed out.')
        review_message = m.content.strip() or 'Your appeal will now be reviewed by our moderation team. If you have new information to share about this case, please reply to this message.'

        await self.db.find_one_and_update(
            {'_id': 'config'},
            {'$set': {'questions': questions, 'move_to': str(move_to.id), 'timeout': timeout_seconds, 'review_message': review_message}},
            upsert=True
        )
        await ctx.send('Configuration saved successfully.')

async def setup(bot: ModmailBot) -> None:
    await bot.add_cog(Questions(bot))
