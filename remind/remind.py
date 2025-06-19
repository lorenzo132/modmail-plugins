import discord
from discord.ext import commands, tasks
from discord.utils import escape_markdown, escape_mentions
from datetime import datetime, timedelta, timezone
import re
from typing import Optional
from bson import ObjectId

class Remind(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.collection = self.bot.db["reminders"]
        self.in_memory_reminders = []
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

    @commands.command()
    async def remind(self, ctx, time: str, *, message: str = ""):
        """
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
        """
        delta = self.parse_timedelta(time)
        if not delta:
            return await ctx.send("❌ Invalid time. Use: `s`, `m`, `h`, `d`, `w`, `mo`, `y`.")

        dm = "--dm" in message
        message = message.replace("--dm", "").strip()
        reminder_time = datetime.now(timezone.utc) + delta

        reminder_data = {
            "user_id": ctx.author.id,
            "channel_id": ctx.channel.id,
            "message": message + f"\n[Jump to message]({ctx.message.jump_url})",
            "remind_at": reminder_time,
            "dm": dm
        }

        if delta.total_seconds() < 60:
            reminder_data["id"] = str(ObjectId())
            self.in_memory_reminders.append(reminder_data)
            reminder_id = reminder_data["id"][:6]
        else:
            result = await self.collection.insert_one(reminder_data)
            reminder_id = str(result.inserted_id)[:6]

        location = "via DM" if dm else "in this channel"
        await ctx.send(
            f"✅ Reminder `{reminder_id}` set {location} for <t:{int(reminder_time.timestamp())}:R>."
        )

    @commands.group(invoke_without_command=True, aliases=["reminders"])
    async def reminder(self, ctx):
        """
        List your active reminders.
        """
        db_cursor = self.collection.find({"user_id": ctx.author.id}).sort("remind_at", 1)
        db_reminders = await db_cursor.to_list(length=50)
        mem_reminders = [r for r in self.in_memory_reminders if r["user_id"] == ctx.author.id]
        all_reminders = db_reminders + mem_reminders

        if not all_reminders:
            return await ctx.send("📭 You have no active reminders.")

        lines = []
        for r in all_reminders:
            rid = r.get("id", str(r["_id"]))[:6]
            timestamp = int(r["remind_at"].timestamp())
            where = "DM" if r.get("dm") else "Channel"
            msg = f"`{rid}` - <t:{timestamp}:R> ({where})"
            if r.get("message"):
                clean_msg = escape_mentions(escape_markdown(r["message"]))
                msg += f": {clean_msg}"
            lines.append(msg)

        embed = discord.Embed(
            title="📌 Your Reminders",
            description="\n".join(lines),
            color=discord.Color.green()
        )
        await ctx.send(embed=embed)

    @reminder.command(name="cancel")
    async def cancel_reminder(self, ctx, reminder_id: str):
        """
        Cancel a reminder by its ID.
        """
        # Try in-memory first
        for r in self.in_memory_reminders:
            if r["id"].startswith(reminder_id) and r["user_id"] == ctx.author.id:
                self.in_memory_reminders.remove(r)
                return await ctx.send(f"🗑️ Reminder `{reminder_id}` cancelled.")

        # Then DB
        query = {"user_id": ctx.author.id}
        reminders = await self.collection.find(query).to_list(length=50)
        for r in reminders:
            if str(r["_id"]).startswith(reminder_id):
                await self.collection.delete_one({"_id": r["_id"]})
                return await ctx.send(f"🗑️ Reminder `{reminder_id}` cancelled.")

        await ctx.send("❌ Reminder not found or not yours.")

    @tasks.loop(seconds=5)
    async def check_reminders(self):
        now = datetime.now(timezone.utc)

        # In-memory
        due = [r for r in self.in_memory_reminders if r["remind_at"] <= now]
        for reminder in due:
            await self.dispatch_reminder(reminder)
            self.in_memory_reminders.remove(reminder)

        # DB
        db_reminders = await self.collection.find({"remind_at": {"$lte": now}}).to_list(length=100)
        for reminder in db_reminders:
            await self.dispatch_reminder(reminder)
            await self.collection.delete_one({"_id": reminder["_id"]})

    async def dispatch_reminder(self, reminder):
        user = self.bot.get_user(reminder["user_id"])
        if not user:
            return

        content = "⏰ **Reminder**"
        if reminder.get("message"):
            clean_msg = escape_mentions(escape_markdown(reminder["message"]))
            content += f": {clean_msg}"

        if reminder.get("dm"):
            try:
                await user.send(content)
            except discord.Forbidden:
                pass
        else:
            channel = self.bot.get_channel(reminder["channel_id"])
            if channel:
                try:
                    await channel.send(f"{user.mention} {content}", allowed_mentions=discord.AllowedMentions.none())
                except discord.Forbidden:
                    pass

    @check_reminders.before_loop
    async def before_reminder_loop(self):
        await self.bot.wait_until_ready()

async def setup(bot):
    await bot.add_cog(Remind(bot))
