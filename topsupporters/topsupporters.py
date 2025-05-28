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
    async def topsupporters(self, ctx, *, args: str = ""):
        """Retrieves top supporters for the specified time period.
        
        **Options:**
        - `filter_by`: 'replied', 'closed', or 'both' (default: 'replied')
        - `start`: Start date (YYYY-MM-DD) (optional)
        - `end`: End date (YYYY-MM-DD) (optional)
        - `exclude`: Comma-separated user IDs or usernames to exclude (optional)
        - `dt`: Time period (e.g., 7d, 1w, 2m) (optional)
        
        **Examples:**
        - Show top supporters by replies in the last week:
          ```
          !topsupporters dt=7d filter_by=replied
          ```
        - Show top supporters by who closed tickets in June 2024:
          ```
          !topsupporters filter_by=closed start=2024-06-01 end=2024-06-30
          ```
        - Show top supporters by both replies and closes, excluding certain users:
          ```
          !topsupporters filter_by=both exclude=123456789,username
          ```
        """
        import re
        async with ctx.typing():
            # Default values
            dt = None
            filter_by = "replied"
            start = None
            end = None
            exclude = None

            # Parse args using regex for key=value pairs
            arg_pattern = re.compile(r"(\w+)=([^\s]+)")
            for match in arg_pattern.finditer(args):
                key, value = match.group(1).lower(), match.group(2)
                if key == "dt":
                    try:
                        dt = await UserFriendlyTime().convert(ctx, value)
                    except Exception:
                        return await ctx.send(f"Invalid dt value: `{value}`. Example: dt=7d")
                elif key == "filter_by":
                    filter_by = value.lower()
                elif key == "start":
                    start = value
                elif key == "end":
                    end = value
                elif key == "exclude":
                    exclude = value

            # Parse date range
            now = discord.utils.utcnow()
            if start:
                try:
                    start_date = datetime.strptime(start, "%Y-%m-%d").replace(tzinfo=timezone.utc)
                except Exception:
                    return await ctx.send("Invalid start date format. Use YYYY-MM-DD.")
            else:
                start_date = now - (dt.dt - now) if dt else now.replace(hour=0, minute=0, second=0, microsecond=0)
            if end:
                try:
                    end_date = datetime.strptime(end, "%Y-%m-%d").replace(tzinfo=timezone.utc)
                except Exception:
                    return await ctx.send("Invalid end date format. Use YYYY-MM-DD.")
            else:
                end_date = now
            if end_date < start_date:
                return await ctx.send("End date must be after start date.")

            # Parse exclude list
            exclude_ids = set()
            if exclude:
                for item in exclude.split(","):
                    item = item.strip()
                    if item.isdigit():
                        exclude_ids.add(item)
                    else:
                        # Try to resolve by name
                        user = discord.utils.get(self.bot.users, name=item)
                        if user:
                            exclude_ids.add(str(user.id))

            # Fetch logs for all closed tickets in a single request
            logs = await self.bot.api.logs.find({
                "open": False,
                "closed_at": {"$gte": start_date.isoformat(), "$lte": end_date.isoformat()}
            }).to_list(None)

            supporters = defaultdict(int)

            for l in logs:
                supporters_involved = set()
                if filter_by in ("replied", "both"):
                    for x in l['messages']:
                        if x.get('type') in ('anonymous', 'thread_message') and x['author']['mod']:
                            supporters_involved.add(x['author']['id'])
                if filter_by in ("closed", "both"):
                    closer = l.get('closer') or l.get('closer_id') or l.get('closed_by')
                    if closer:
                        supporters_involved.add(str(closer))
                for s in supporters_involved:
                    if s not in exclude_ids:
                        supporters[s] += 1

            supporters_keys = sorted(supporters.keys(), key=lambda x: supporters[x], reverse=True)

            fmt = ''
            n = 1
            for k in supporters_keys:
                u = self.bot.get_user(int(k))
                if u:
                    fmt += f'**{n}.** `{u}` - {supporters[k]}\n'
                    n += 1

            em = discord.Embed(title='Active Supporters', description=fmt or 'No supporters found.', timestamp=start_date, color=0x7588da)
            em.set_footer(text=f'Since {start_date.strftime("%Y-%m-%d")} to {end_date.strftime("%Y-%m-%d")}' if start or end else 'Since')
            await ctx.send(embed=em)


async def setup(bot):
    await bot.add_cog(TopSupporters(bot))
