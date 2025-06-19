import discord
from discord.ext import commands, tasks
from discord.utils import escape_markdown
from datetime import datetime, timedelta
import re
from typing import Optional

class Remind(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.collection = self.bot.db["reminders"]
        self.check_reminders.start()

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

    @commands.command()
    async def remind(self, ctx, time: str, *, message: str = ""):
        """Set a reminder. Example: [p]remind 1h Take a break --dm"""
        delta = self.parse_timedelta(time)
        if not delta:
            return await ctx.send("❌ Invalid time. Use `s`, `m`, `h`, `d`, `w`, `mo`, `y`.")

        dm = False
        if "--dm" in message:
            dm = True
            message = message.replace("--dm", "").strip()

        remind_time = datetime.utcnow() + delta
        result = await self.collection.insert_one({
            "user_id": ctx.author.id,
            "channel_id": ctx.channel.id,
            "message": message,
            "remind_at": remind_time,
            "dm": dm,
        })

        reminder_id = str(result.inserted_id)[:6]
        formatted_time = f"<t:{int(remind_time.timestamp())}:R>"
        location = "via DM" if dm else "in this channel"
        await ctx.send(f"✅ Reminder `{reminder_id}` set {location} for {formatted_time}.")

    @commands.group(invoke_without_command=True, aliases=["reminders"])
    async def reminder(self, ctx):
        """List your active reminders."""
        cursor = self.collection.find({"user_id": ctx.author.id}).sort("remind_at", 1)
        reminders = await cursor.to_list(length=50)

        if not reminders:
            return await ctx.send("📭 You have no active reminders.")

        lines = []
        for r in reminders:
            rid = str(r["_id"])[:6]
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
        query = {"user_id": ctx.author.id}
        reminders = await self.collection.find(query).to_list(length=50)
        for r in reminders:
            if str(r["_id"]).startswith(reminder_id):
                await self.collection.delete_one({"_id": r["_id"]})
                return await ctx.send(f"🗑️ Reminder `{reminder_id}` cancelled.")

        await ctx.send("❌ Reminder not found.")

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
