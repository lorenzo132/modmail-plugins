from collections import defaultdict
from datetime import datetime, timezone

import discord
from discord.ext import commands

from core import checks
from core.models import PermissionLevel
from core.time import UserFriendlyTime


class TopSupporters(commands.Cog):
    """Sets up top supporters command in Modmail discord"""
    def __init__(self, bot):
        self.bot = bot

    @checks.has_permissions(PermissionLevel.ADMINISTRATOR)
    @commands.command()
    async def topsupporters(self, ctx, *, dt: UserFriendlyTime):
        """Retrieves top supporters for the specified time period"""
        async with ctx.typing():
            # Calculate the date boundary
            date = discord.utils.utcnow() - (dt.dt - discord.utils.utcnow())

            # Retrieve logs where tickets are closed
            logs = await self.bot.api.logs.find({"open": False}).to_list(None)
            logs = filter(lambda x: isinstance(x['closed_at'], str) and datetime.fromisoformat(x['closed_at']) > date, logs)

            # Dictionary to store supporter counts
            supporters = defaultdict(int)

            for log in logs:
                supporters_involved = set()
                for message in log['messages']:
                    # Check if the message was sent by a mod and is either anonymous or a thread message
                    if message.get('type') in ('anonymous', 'thread_message') and message['author'].get('mod', False):
                        supporters_involved.add(message['author']['id'])
                # Count supporters
                for supporter in supporters_involved:
                    supporters[supporter] += 1

            # Sort supporters by count in descending order
            supporters_keys = sorted(supporters.keys(), key=lambda x: supporters[x], reverse=True)

            # Build the embed description
            fmt = ''
            n = 1
            for supporter_id in supporters_keys:
                user = self.bot.get_user(supporter_id)
                if user:
                    fmt += f'**{n}.** `{user}` - {supporters[supporter_id]}\n'
                    n += 1

            # Create embed message
            embed = discord.Embed(
                title='Top Supporters',
                description=fmt or "No supporters found for the specified time period.",
                timestamp=datetime.utcnow(),
                color=0x7588da
            )
            embed.set_footer(text=f'Since {date.strftime("%Y-%m-%d %H:%M:%S")}')
            await ctx.send(embed=embed)


async def setup(bot):
    await bot.add_cog(TopSupporters(bot))
