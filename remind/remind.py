import discord
from discord.ext import commands, tasks
from discord.utils import escape_markdown
from datetime import datetime, timedelta, timezone
import re
import asyncio
import secrets
from typing import Optional

class Remind(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.collection = self.bot.db["reminders"]
        self.short_term_reminders = {}  # {id: asyncio.Task}
        self.check_reminders.start()

    def cog_unload(self):
        self.check_reminders.cancel()
        for task in self.short_term_reminders.values():
            task.cancel()

    def parse_timedelta(self, time_str: str) -> Optional[timedelta]:
        match = re.fullmatch(r"(\d+)(s|m|h|d|w|mo|y)", time_str.strip().lower())
        if not match:
            return None
        num, unit = match.groups()
        num = int(num)
        return {
            "s": timedelta(seconds=num),
            "m": timedelta(minutes=num),
            "h": timedelta(hours=num),
            "d": timedelta(days=num),
            "w": timedelta(weeks=num),
            "mo": timedelta(days=30 * num),
            "y": timedelta(days=365 * num),
        }.get(unit)

    def generate_reminder_id(self):
        return secrets.token_hex(3)

    @commands.command(help="""
Set a reminder.

Time units:
  - s (seconds)
  - m (minutes)
  - h (hours)
  - d (days)
  - w (weeks)
  - mo (months)
  - y (years)

Flags:
  --dm → Sends the reminder in DMs instead of the channel.

Example: ?remind 1h Take a break --dm
""")
    async def remind(self, ctx, time: str, *, message: str = ""):
        delta = self.parse_timedelta(time)
        if not delta:
            return await ctx.send("❌ Invalid time format. Try `10m`, `1h`, `2d`, etc.")

        dm = "--dm" in message
        message = message.replace("--dm", "").strip()
        escaped_msg = escape_markdown(message)
        reminder_id = self.generate_reminder_id()
        now = datetime.now(timezone.utc)
        remind_time = now + delta
        timestamp = f"<t:{int(remind_time.timestamp())}:R>"
        link = f"https://discord.com/channels/{ctx.guild.id if ctx.guild else '@me'}/{ctx.channel.id}/{ctx.message.id}"

        if delta.total_seconds() < 60:
            async def short_reminder():
                await asyncio.sleep(delta.total_seconds())
                content = "⏰ **Reminder**"
                if escaped_msg:
                    content += f": {escaped_msg}"
                try:
                    if dm:
                        await ctx.author.send(content)
                    else:
                        await ctx.channel.send(f"{ctx.author.mention} {content}")
                except discord.Forbidden:
                    pass
            task = asyncio.create_task(short_reminder())
            self.short_term_reminders[reminder_id] = task
        else:
            await self.collection.insert_one({
                "user_id": ctx.author.id,
                "channel_id": ctx.channel.id,
                "guild_id": ctx.guild.id if ctx.guild else None,
                "message": escaped_msg,
                "remind_at": remind_time,
                "dm": dm,
                "reminder_id": reminder_id
            })

        await ctx.send(
            f"✅ Reminder `{reminder_id}` set {'via DM' if dm else 'in this channel'} for {timestamp}.\n[Jump to command]({link})"
        )

    @commands.group(invoke_without_command=True, aliases=["reminders"], help="""
List your active reminders.
Displays up to 50 upcoming reminders.
""")
    async def reminder(self, ctx):
        now = datetime.now(timezone.utc)
        cursor = self.collection.find({"user_id": ctx.author.id}).sort("remind_at", 1)
        reminders = await cursor.to_list(length=50)

        for rid in self.short_term_reminders:
            reminders.append({
                "reminder_id": rid,
                "remind_at": now + timedelta(seconds=1),
                "dm": False,
                "message": "(short-term)"
            })

        if not reminders:
            return await ctx.send("📭 You have no active reminders.")

        lines = []
        for r in reminders:
            rid = r.get("reminder_id", str(r.get("_id"))[:6])
            remind_at = r["remind_at"]
            if isinstance(remind_at, datetime) and remind_at.tzinfo is None:
                remind_at = remind_at.replace(tzinfo=timezone.utc)
            timestamp = f"<t:{int(remind_at.timestamp())}:R>"
            where = "DM" if r.get("dm") else "Channel"
            line = f"`{rid}` - {timestamp} ({where})"
            if r.get("message"):
                line += f": {r['message']}"
            lines.append(line)

        embed = discord.Embed(
            title="📌 Your Reminders",
            description="\n".join(lines),
            color=discord.Color.green()
        )
        await ctx.send(embed=embed)

    @reminder.command(name="cancel", help="""
Cancel a reminder by its ID.
You can get the ID using the reminder list command.

Example: ?reminder cancel a1b2c3
""")
    async def cancel_reminder(self, ctx, reminder_id: str):
        if reminder_id in self.short_term_reminders:
            self.short_term_reminders[reminder_id].cancel()
            del self.short_term_reminders[reminder_id]
            return await ctx.send(f"🗑️ Reminder `{reminder_id}` cancelled.")

        query = {
            "user_id": ctx.author.id,
            "reminder_id": reminder_id
        }
        result = await self.collection.delete_one(query)
        if result.deleted_count:
            return await ctx.send(f"🗑️ Reminder `{reminder_id}` cancelled.")
        await ctx.send("❌ Reminder not found or doesn't belong to you.")

    @tasks.loop(seconds=60)
    async def check_reminders(self):
        now = datetime.now(timezone.utc)
        reminders = await self.collection.find({"remind_at": {"$lte": now}}).to_list(length=100)

        for r in reminders:
            user = self.bot.get_user(r["user_id"])
            if not user:
                continue

            content = "⏰ **Reminder**"
            if r.get("message"):
                content += f": {r['message']}"

            if r.get("dm"):
                try:
                    await user.send(content)
                except discord.Forbidden:
                    pass
            else:
                channel = self.bot.get_channel(r["channel_id"])
                if channel:
                    try:
                        await channel.send(f"{user.mention} {content}")
                    except discord.Forbidden:
                        pass

            await self.collection.delete_one({"_id": r["_id"]})

    @check_reminders.before_loop
    async def before_reminder_loop(self):
        await self.bot.wait_until_ready()

async def setup(bot):
    await bot.add_cog(Remind(bot))
