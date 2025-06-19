import discord
from discord.ext import commands, tasks
from discord.utils import escape_markdown
from datetime import datetime, timedelta, timezone
from bson import ObjectId
import re
import secrets
from typing import Optional

class Remind(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.collection = self.bot.db["reminders"]
        self.short_term = {}
        self.check_reminders.start()

    def cog_unload(self):
        self.check_reminders.cancel()

    def parse_timedelta(self, time_str: str) -> Optional[timedelta]:
        match = re.fullmatch(r"(\d+)(s|m|h|d|w|mo|y)", time_str.strip().lower())
        if not match:
            return None

        num, unit = match.groups()
        num = int(num)
        match unit:
            case "s": return timedelta(seconds=num)
            case "m": return timedelta(minutes=num)
            case "h": return timedelta(hours=num)
            case "d": return timedelta(days=num)
            case "w": return timedelta(weeks=num)
            case "mo": return timedelta(days=30 * num)
            case "y": return timedelta(days=365 * num)

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
Example:
  ?remind 1h Take a break --dm
""")
    async def remind(self, ctx, time: str, *, message: str = ""):
        delta = self.parse_timedelta(time)
        if not delta:
            return await ctx.send("❌ Invalid time. Use `s`, `m`, `h`, `d`, `w`, `mo`, `y`.")

        dm = "--dm" in message
        if dm:
            message = message.replace("--dm", "").strip()

        remind_time = datetime.now(timezone.utc) + delta

        reminder_id = secrets.token_hex(3)

        jump_link = ctx.message.jump_url
        stored_data = {
            "_id": reminder_id,
            "user_id": ctx.author.id,
            "channel_id": ctx.channel.id,
            "message": message,
            "remind_at": remind_time,
            "dm": dm,
            "jump_url": jump_link
        }

        if delta.total_seconds() < 60:
            self.short_term[reminder_id] = stored_data
        else:
            await self.collection.insert_one(stored_data)

        formatted_time = f"<t:{int(remind_time.timestamp())}:R>"
        location = "via DM" if dm else "in this channel"
        await ctx.send(f"✅ Reminder `{reminder_id}` set {location} for {formatted_time}.")

    @commands.group(invoke_without_command=True, aliases=["reminders"], help="""
List your active reminders.
""")
    async def reminder(self, ctx):
        db_reminders = await self.collection.find({"user_id": ctx.author.id}).sort("remind_at", 1).to_list(length=100)
        memory_reminders = [r for r in self.short_term.values() if r["user_id"] == ctx.author.id]
        reminders = db_reminders + memory_reminders

        if not reminders:
            return await ctx.send("📭 You have no active reminders.")

        lines = []
        for r in reminders:
            rid = r["_id"]
            when = f"<t:{int(r['remind_at'].timestamp())}:R>"
            where = "DM" if r.get("dm") else "Channel"
            msg = f"`{rid}` - {when} ({where})"
            if r.get("message"):
                msg += f": {escape_markdown(r['message'])}"
            lines.append(msg)

        embed = discord.Embed(
            title="📌 Your Reminders",
            description="\n".join(lines),
            color=discord.Color.green()
        )
        await ctx.send(embed=embed)

    @reminder.command(name="cancel", help="""
Cancel a reminder by its ID.
Only your own reminders can be cancelled.
Usage: ?reminder cancel <ID>
""")
    async def cancel_reminder(self, ctx, reminder_id: str):
        if reminder_id in self.short_term:
            if self.short_term[reminder_id]["user_id"] != ctx.author.id:
                return await ctx.send("❌ You can only cancel your own reminders.")
            del self.short_term[reminder_id]
            return await ctx.send(f"🗑️ Reminder `{reminder_id}` cancelled.")

        r = await self.collection.find_one({"_id": reminder_id})
        if not r:
            return await ctx.send("❌ Reminder not found.")
        if r["user_id"] != ctx.author.id:
            return await ctx.send("❌ You can only cancel your own reminders.")

        await self.collection.delete_one({"_id": reminder_id})
        await ctx.send(f"🗑️ Reminder `{reminder_id}` cancelled.")

    @tasks.loop(seconds=5)
    async def check_reminders(self):
        now = datetime.now(timezone.utc)

        # Handle short-term memory reminders
        for rid, reminder in list(self.short_term.items()):
            if reminder["remind_at"] <= now:
                await self.send_reminder(reminder)
                del self.short_term[rid]

        # Handle DB reminders
        reminders = await self.collection.find({"remind_at": {"$lte": now}}).to_list(length=100)
        for reminder in reminders:
            await self.send_reminder(reminder)
            await self.collection.delete_one({"_id": reminder["_id"]})

    async def send_reminder(self, reminder):
        user = self.bot.get_user(reminder["user_id"])
        if not user:
            return

        content = "⏰ **Reminder**"
        if reminder.get("message"):
            content += f": {escape_markdown(reminder['message'])}"

        jump = reminder.get("jump_url")
        if jump:
            content += f"\n[Jump to message]({jump})"

        if reminder.get("dm"):
            try:
                await user.send(content)
            except discord.Forbidden:
                pass
        else:
            channel = self.bot.get_channel(reminder["channel_id"])
            if channel:
                try:
                    await channel.send(f"{user.mention} {content}")
                except discord.Forbidden:
                    pass

    @check_reminders.before_loop
    async def before_reminder_loop(self):
        await self.bot.wait_until_ready()

async def setup(bot):
    await bot.add_cog(Remind(bot))
