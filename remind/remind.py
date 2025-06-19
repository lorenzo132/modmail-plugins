import discord
from discord.ext import commands, tasks
from discord.utils import escape_markdown
from datetime import datetime, timedelta
from bson import ObjectId
import re
from typing import Optional
import asyncio
import random
import string

class Remind(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.collection = self.bot.db["reminders"]
        self.short_term_reminders = []
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

    def generate_reminder_id(self) -> str:
        return ''.join(random.choices(string.ascii_letters + string.digits, k=6))

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

        Example: !remind 1h Take a break --dm
    """)
    async def remind(self, ctx, time: str, *, message: str = ""):
        delta = self.parse_timedelta(time)
        if not delta:
            return await ctx.send("❌ Invalid time. Use `s`, `m`, `h`, `d`, `w`, `mo`, `y`.")

        dm = False
        if "--dm" in message:
            dm = True
            message = message.replace("--dm", "").strip()

        remind_time = datetime.utcnow() + delta
        reminder_id = self.generate_reminder_id()
        message_link = ctx.message.jump_url
        content = f"{message}\n{message_link}" if message else message_link

        if delta.total_seconds() < 60:
            self.short_term_reminders.append((remind_time, ctx.author.id, ctx.channel.id, content, dm))
        else:
            await self.collection.insert_one({
                "_id": reminder_id,
                "user_id": ctx.author.id,
                "channel_id": ctx.channel.id,
                "message": content,
                "remind_at": remind_time,
                "dm": dm,
            })

        formatted_time = f"<t:{int(remind_time.replace(tzinfo=None).timestamp())}:R>"
        location = "via DM" if dm else "in this channel"
        await ctx.send(f"✅ Reminder `{reminder_id}` set {location} for {formatted_time}.")

    @commands.group(invoke_without_command=True, aliases=["reminders"], help="""
        List your active reminders.
        Shows up to 50 reminders sorted by soonest.
    """)
    async def reminder(self, ctx):
        cursor = self.collection.find({"user_id": ctx.author.id}).sort("remind_at", 1)
        reminders = await cursor.to_list(length=50)

        if not reminders:
            return await ctx.send("📭 You have no active reminders.")

        lines = []
        for r in reminders:
            rid = r.get("_id", "")
            when = f"<t:{int(r['remind_at'].replace(tzinfo=None).timestamp())}:R>"
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
        You can get the ID by running `!reminders`.
    """)
    async def cancel_reminder(self, ctx, reminder_id: str):
        query = {"_id": reminder_id, "user_id": ctx.author.id}
        result = await self.collection.delete_one(query)
        if result.deleted_count == 1:
            return await ctx.send(f"🗑️ Reminder `{reminder_id}` cancelled.")

        await ctx.send("❌ Reminder not found or not yours to delete.")

    @tasks.loop(seconds=10)
    async def check_reminders(self):
        now = datetime.utcnow()

        # Check short term reminders
        to_send = [r for r in self.short_term_reminders if r[0] <= now]
        self.short_term_reminders = [r for r in self.short_term_reminders if r[0] > now]

        for remind_time, user_id, channel_id, content, dm in to_send:
            user = self.bot.get_user(user_id)
            if not user:
                continue

            content_final = f"⏰ **Reminder**: {escape_markdown(content)}"

            if dm:
                try:
                    await user.send(content_final)
                except discord.Forbidden:
                    pass
            else:
                channel = self.bot.get_channel(channel_id)
                if channel:
                    try:
                        await channel.send(f"{user.mention} {content_final}")
                    except discord.Forbidden:
                        pass

        # Check database reminders
        reminders = await self.collection.find({"remind_at": {"$lte": now}}).to_list(length=100)

        for reminder in reminders:
            user = self.bot.get_user(reminder["user_id"])
            if not user:
                continue

            content = "⏰ **Reminder**"
            if reminder.get("message"):
                content += f": {escape_markdown(reminder['message'])}"

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

            await self.collection.delete_one({"_id": reminder["_id"]})

    @check_reminders.before_loop
    async def before_reminder_loop(self):
        await self.bot.wait_until_ready()

async def setup(bot):
    await bot.add_cog(Remind(bot))
