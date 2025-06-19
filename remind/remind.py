import discord
from discord.ext import commands, tasks
from discord.utils import escape_markdown
from datetime import datetime, timedelta
import re
import random
import string
from typing import Optional

class Remind(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.collection = self.bot.db["reminders"]
        self.check_reminders.start()
        self.short_term = []  # In-memory reminders (<60s)

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
        return ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))

    @commands.command(
        name="remind",
        brief="Set a reminder. Example: ?remind 1h Take a break --dm",
        help="""
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
  ?remind 10m Stretch your legs --dm
  ?remind 2h Call mom
        """)
    async def remind(self, ctx, time: str, *, message: str = ""):
        delta = self.parse_timedelta(time)
        if not delta:
            return await ctx.send("❌ Invalid time. Use `s`, `m`, `h`, `d`, `w`, `mo`, `y`.")

        dm = False
        if "--dm" in message:
            dm = True
            message = message.replace("--dm", "").strip()

        message = escape_markdown(message)
        remind_time = datetime.utcnow() + delta
        reminder_id = self.generate_reminder_id()
        origin_link = ctx.message.jump_url

        if delta.total_seconds() < 60:
            self.short_term.append({
                "id": reminder_id,
                "user_id": ctx.author.id,
                "channel_id": ctx.channel.id,
                "message": message,
                "remind_at": remind_time,
                "dm": dm,
                "origin": origin_link
            })
        else:
            await self.collection.insert_one({
                "id": reminder_id,
                "user_id": ctx.author.id,
                "channel_id": ctx.channel.id,
                "message": message,
                "remind_at": remind_time,
                "dm": dm,
                "origin": origin_link
            })

        formatted_time = f"<t:{int(remind_time.timestamp())}:R>"
        location = "via DM" if dm else "in this channel"
        await ctx.send(f"✅ Reminder `{reminder_id}` set {location} for {formatted_time}.\n[Jump to command]({origin_link})")

    @commands.group(
        invoke_without_command=True,
        aliases=["reminders"],
        brief="View your active reminders.",
        help="Lists all your current active reminders, including their ID and when they'll trigger."
    )
    async def reminder(self, ctx):
        cursor = self.collection.find({"user_id": ctx.author.id}).sort("remind_at", 1)
        db_reminders = await cursor.to_list(length=50)
        mem_reminders = [r for r in self.short_term if r["user_id"] == ctx.author.id]

        if not db_reminders and not mem_reminders:
            return await ctx.send("📭 You have no active reminders.")

        lines = []
        for r in db_reminders + mem_reminders:
            rid = r["id"]
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

    @reminder.command(
        name="cancel",
        brief="Cancel a reminder by ID.",
        help="Cancels one of your own reminders using its ID. Use `?reminder` to find IDs."
    )
    async def cancel_reminder(self, ctx, reminder_id: str):
        # Cancel from DB
        query = {"user_id": ctx.author.id, "id": reminder_id}
        deleted = await self.collection.delete_one(query)

        # Cancel from memory
        mem_deleted = False
        for r in self.short_term:
            if r["user_id"] == ctx.author.id and r["id"] == reminder_id:
                self.short_term.remove(r)
                mem_deleted = True
                break

        if deleted.deleted_count > 0 or mem_deleted:
            return await ctx.send(f"🗑️ Reminder `{reminder_id}` cancelled.")
        await ctx.send("❌ Reminder not found or you do not own it.")

    @tasks.loop(seconds=5)
    async def check_reminders(self):
        now = datetime.utcnow()

        # Handle in-memory short-term reminders
        for reminder in self.short_term[:]:
            if reminder["remind_at"] <= now:
                user = self.bot.get_user(reminder["user_id"])
                if user:
                    content = "⏰ **Reminder**"
                    if reminder.get("message"):
                        content += f": {reminder['message']}\n[Command]({reminder['origin']})"

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
                self.short_term.remove(reminder)

        # Handle DB reminders
        reminders = await self.collection.find({"remind_at": {"$lte": now}}).to_list(length=100)

        for reminder in reminders:
            user = self.bot.get_user(reminder["user_id"])
            if not user:
                continue

            content = "⏰ **Reminder**"
            if reminder.get("message"):
                content += f": {reminder['message']}\n[Command]({reminder.get('origin', '')})"

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
