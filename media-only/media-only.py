import asyncio
import discord
from discord.ext import commands
from pymongo import ReturnDocument

from core import checks
from core.models import PermissionLevel


class Mediaonly(commands.Cog):
    """Sets up media channel in discord."""

    def __init__(self, bot):
        self.bot = bot
        self.db = bot.plugin_db.get_partition(self)
        bot.loop.create_task(self.load_variables())

    async def load_variables(self):
        self.config = await self.db.find_one({'_id': 'config'}) or {}

    async def delete(self, message, warning):
        if warning:
            await message.channel.send(warning, delete_after=5)
        try:
            await message.delete()
        except discord.NotFound:
            pass

    @commands.Cog.listener()
    async def on_message(self, message):
        if self.config.get('status', True) and message.channel.id in self.config.get('channel_ids', []):
            if message.author.bot:
                await asyncio.sleep(5)
                await self.delete(message, warning=None)
            elif len(message.attachments):
                if len(message.attachments) > 1:
                    await self.delete(message, warning=f'{message.author.mention}, send 1 emoji at a time.')
                elif not (message.attachments[0].filename.endswith('.png') or message.attachments[0].filename.endswith('.gif') or message.attachments[0].filename.endswith('.jpeg') or message.attachments[0].filename.endswith('.jpg') or message.attachments[0].filename.endswith('.mp4')):
                    await self.delete(message, warning=f'{message.author.mention}, only png, gif, jpg, jpeg and mp4 files are allowed here 📷')

            else:
                await self.delete(message, warning=f'{message.author.mention}, only images + captions are allowed. If you wish to add a caption, edit your original message.')


    @checks.has_permissions(PermissionLevel.ADMINISTRATOR)
    @commands.group(invoke_without_command=True)
    async def mediachannels(self, ctx):
        """Configure media only Channels, accepted media files are png, gif, jpg, jpeg and mp4"""
        await ctx.send_help(ctx.command)

    @checks.has_permissions(PermissionLevel.ADMINISTRATOR)
    @mediachannels.command(aliases=['channel'])
    async def channels(self, ctx, *channels_: discord.TextChannel):
        """Configure media Channel(s)"""
        self.config = await self.db.find_one_and_update(
            {'_id': 'config'}, {'$set': {'channel_ids': [i.id for i in channels_]}},
            return_document=ReturnDocument.AFTER,
            upsert=True
        )
        await ctx.send('Config set.')
        
    @checks.has_permissions(PermissionLevel.ADMINISTRATOR)
    @mediachannels.command()
    async def toggle(self, ctx):
        """Toggles status of the plugin"""
        self.config = await self.db.find_one_and_update(
            {'_id': 'config'}, {'$set': {'status': not self.config.get('status', True)}},
            return_document=ReturnDocument.AFTER,
            upsert=True
        )
        await ctx.send(f'Config set: Status {self.config.get("status", True)}.')


def setup(bot):
    bot.add_cog(Mediaonly(bot))
