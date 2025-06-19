import discord
from discord.ext import commands, tasks
from discord.utils import escape_markdown
from datetime import datetime, timedelta
import asyncio
import re
import secrets
from typing import Optional

class Remind(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.collection = self.bot.db["reminders"]
        self.check_reminders.start()
        self.memory_reminders = {}

    def cog_unload(self):
        self.check_reminders.cancel()

    def parse_timedelta(self, time_str: str) -> Optional[timedelta]:
        """Convert a duration string into timedelta."""
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

    def escape_mentions(self, message: str) -> str:
        """Escape mentions so they can't notify."""
        return re.sub(r"<(@!?|@&|@)(\d+)>|@everyone|@here", lambda m: escape_markdown(m.group(0)), message)

    @commands.command()
    async def remind(self, ctx, time: str, *, message: str = ""):
        """Set a reminder. Example: [p]remind 1h Take a break --dm"""
        delta = self.parse_timedelta(time)
        if not delta:
            return await ctx.send("❌ Invalid time. Use `s`, `m`, `h`, `d`, `w`, `mo`, `y`.")

        dm = "--dm" in message
        if dm:
            message = message.replace("--dm", "").strip()

        reminder_id = secrets.token_hex(3)  # Unique 6-character ID
        message = self.escape_mentions(message)
        remind_time = datetime.utcnow() + delta
        message_link = f"https://discord.com/channels/{ctx.guild.id if ctx.guild else '@me'}/{ctx.channel.id}/{ctx.message.id}"

        if delta.total_seconds() < 60:
            self.memory_reminders[reminder_id] = {
                "user_id": ctx.author.id,
                "message": message,
                "dm": dm,
                "channel_id": ctx.channel.id,
                "message_link": message_link,
                "when": remind_time
            }
            asyncio.create_task(self.short_reminder(reminder_id))
        else:
            await self.collection.insert_one({
                "_id": reminder_id,
                "user_id": ctx.author.id,
                "channel_id": ctx.channel.id,
                "message": message,
                "remind_at": remind_time,
                "dm": dm,
                "message_link": message_link,
            })

        formatted_time = f"<t:{int(remind_time.timestamp())}:R>"
        location = "via DM" if dm else "in this channel"
        await ctx.send(f"✅ Reminder `{reminder_id}` set {location} for {formatted_time}.")

    async def short_reminder(self, reminder_id):
        data = self.memory_reminders[reminder_id]
        delay = (data["when"] - datetime.utcnow()).total_seconds()
        await asyncio.sleep(delay)

        user = self.bot.get_user(data["user_id"])
        if not user:
            return

        content = f"⏰ **Reminder**"
        if data["message"]:
            content += f": {escape_markdown(data['message'])}\n🔗 {data['message_link']}"

        try:
            if data["dm"]:
                await user.send(content)
            else:
                channel = self.bot.get_channel(data["channel_id"])
                if channel:
                    await channel.send(f"{user.mention} {content}")
        except discord.Forbidden:
            pass
        finally:
            self.memory_reminders.pop(reminder_id, None)

    @commands.group(invoke_without_command=True, aliases=["reminders"])
    async def reminder(self, ctx):
        """List your active reminders."""
        cursor = self.collection.find({"user_id": ctx.author.id}).sort("remind_at", 1)
        reminders = await cursor.to_list(length=50)
        mem_reminders = [
            {
                "_id": rid,
                "remind_at": r["when"],
                "dm": r["dm"],
                "message": r["message"]
            }
            for rid, r in self.memory_reminders.items()
            if r["user_id"] == ctx.author.id
        ]
        all_reminders = mem_reminders + reminders

        if not all_reminders:
            return await ctx.send("📭 You have no active reminders.")

        lines = []
        for r in all_reminders:
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

    @reminder.command(name="cancel")
    async def cancel_reminder(self, ctx, reminder_id: str):
        """Cancel a reminder by its ID (from [p]reminders)."""

        # Cancel from memory
        if reminder_id in self.memory_reminders:
            if self.memory_reminders[reminder_id]["user_id"] != ctx.author.id:
                return await ctx.send("❌ You can only cancel your own reminders.")
            self.memory_reminders.pop(reminder_id, None)
            return await ctx.send(f"🗑️ Reminder `{reminder_id}` cancelled.")

        # Cancel from DB
        doc = await self.collection.find_one({"_id": reminder_id})
        if not doc:
            return await ctx.send("❌ Reminder not found.")
        if doc["user_id"] != ctx.author.id:
            return await ctx.send("❌ You can only cancel your own reminders.")

        await self.collection.delete_one({"_id": reminder_id})
        await ctx.send(f"🗑️ Reminder `{reminder_id}` cancelled.")

    @tasks.loop(seconds=60)
    async def check_reminders(self):
        now = datetime.utcnow()
        reminders = await self.collection.find({"remind_at": {"$lte": now}}).to_list(length=100)

        for reminder in reminders:
            user = self.bot.get_user(reminder["user_id"])
            if not user:
                continue

            content = "⏰ **Reminder**"
            if reminder.get("message"):
                content += f": {escape_markdown(reminder['message'])}\n🔗 {reminder.get('message_link', '')}"

            try:
                if reminder.get("dm"):
                    await user.send(content)
                else:
                    channel = self.bot.get_channel(reminder["channel_id"])
                    if channel:
                        await channel.send(f"{user.mention} {content}")
            except discord.Forbidden:
                pass
            finally:
                await self.collection.delete_one({"_id": reminder["_id"]})

    @check_reminders.before_loop
    async def before_reminder_loop(self):
        await self.bot.wait_until_ready()

async def setup(bot):
    await bot.add_cog(Remind(bot))
