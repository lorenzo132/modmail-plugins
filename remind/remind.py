import discord
from discord.ext import commands, tasks
from discord.utils import escape_markdown
from datetime import datetime, timedelta
import re
import asyncio
import secrets
from typing import Optional

class Remind(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.collection = self.bot.db["reminders"]
        self.short_term_reminders = {}  # {id: task}
        self.check_reminders.start()

    def cog_unload(self):
        self.check_reminders.cancel()
        for task in self.short_term_reminders.values():
            task.cancel()

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
            return await ctx.send("❌ Invalid time. Use `s`, `m`, `h`, `d`, `w`, `mo`, `y`.")

        dm = "--dm" in message
        message = message.replace("--dm", "").strip()

        reminder_id = self.generate_reminder_id()
        remind_time = datetime.utcnow() + delta
        escaped_msg = escape_markdown(message)
        location = "via DM" if dm else "in this channel"
        formatted_time = f"<t:{int(remind_time.timestamp())}:R>"
        link = f"https://discord.com/channels/{ctx.guild.id if ctx.guild else '@me'}/{ctx.channel.id}/{ctx.message.id}"

        if delta.total_seconds() < 60:
            # Keep in memory
            async def short_reminder():
                await asyncio.sleep(delta.total_seconds())
                content = f"⏰ **Reminder**"
                if escaped_msg:
                    content += f": {escaped_msg}"

                if dm:
                    try:
                        await ctx.author.send(content)
                    except discord.Forbidden:
                        pass
                else:
                    try:
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
            f"✅ Reminder `{reminder_id}` set {location} for {formatted_time}.\n[Jump to command]({link})"
        )

    @commands.group(invoke_without_command=True, aliases=["reminders"], help="""
List your active reminders.
Displays up to 50 upcoming reminders.
""")
    async def reminder(self, ctx):
        cursor = self.collection.find({"user_id": ctx.author.id}).sort("remind_at", 1)
        reminders = await cursor.to_list(length=50)

        # Include short-term reminders
        for rid in self.short_term_reminders:
            reminders.append({
                "reminder_id": rid,
                "remind_at": datetime.utcnow(),  # now-ish
                "dm": False,
                "message": "(short-term)"
            })

        if not reminders:
            return await ctx.send("📭 You have no active reminders.")

        lines = []
        for r in reminders:
            rid = r.get("reminder_id", str(r.get("_id"))[:6])
            when = f"<t:{int(r['remind_at'].timestamp())}:R>"
            where = "DM" if r.get("dm") else "Channel"
            msg = f"`{rid}` - {when} ({where})"
            if r.get("message"):
                msg += f": {r['message']}"
            lines.append(msg)

        embed = discord.Embed(
            title="📌 Your Reminders",
            description="\n".join(lines),
            color=discord.Color.green()
        )
        await ctx.send(embed=embed)

    @reminder.command(name="cancel", help="""
Cancel a reminder by its ID.
You can get the ID using the reminder list command.

Example: ?reminder cancel 123abc
""")
    async def cancel_reminder(self, ctx, reminder_id: str):
        # Cancel short-term memory-based reminders
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
        await ctx.send("❌ Reminder not found or does not belong to you.")

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
                content += f": {reminder['message']}"

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
