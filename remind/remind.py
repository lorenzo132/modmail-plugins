import discord
import datetime
import asyncio
import uuid
from discord.ext import commands, tasks
from modmail.ext.utils import parse_timedelta

class DismissButton(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=60)

    @discord.ui.button(label="Dismiss", style=discord.ButtonStyle.secondary)
    async def dismiss(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.message.delete()
        await interaction.response.send_message("✅ Reminder dismissed.", ephemeral=True)


class Remind(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db = bot.db["plugins.Remind"]
        self.check_reminders.start()

    def cog_unload(self):
        self.check_reminders.cancel()

    @tasks.loop(seconds=60)
    async def check_reminders(self):
        now = datetime.datetime.utcnow().timestamp()
        async for reminder in self.db.find({"remind_at": {"$lte": now}}):
            await self.send_reminder(reminder)
            await self.db.delete_one({"_id": reminder["_id"]})

    async def send_reminder(self, r):
        content = f"🔔 <@{r['user_id']}> Reminder: {r.get('message') or 'No message'}"
        view = DismissButton()
        user = self.bot.get_user(r["user_id"]) or await self.bot.fetch_user(r["user_id"])
        try:
            if r["dm"]:
                await user.send(content, view=view)
            else:
                channel = self.bot.get_channel(r["channel_id"])
                await channel.send(content, view=view)
        except discord.Forbidden:
            if not r["dm"]:
                channel = self.bot.get_channel(r["channel_id"])
                await channel.send(f"<@{r['user_id']}> I couldn't DM you your reminder.")

    @commands.group(invoke_without_command=True)
    async def remind(self, ctx, time: str = None, *, message: str = ""):
        """Set a reminder. Optional message and --dm flag for DM delivery."""
        if not time:
            return await ctx.send("Usage: `[p]remind <time> [message] [--dm]`")

        delta = parse_timedelta(time)
        if not delta or delta.total_seconds() <= 0:
            return await ctx.send("❌ Invalid time format.")

        dm = False
        if message.endswith("--dm"):
            dm = True
            message = message.rsplit("--dm", 1)[0].strip()

        remind_at = datetime.datetime.utcnow().timestamp() + delta.total_seconds()
        reminder_id = str(uuid.uuid4())[:8]

        await self.db.insert_one({
            "_id": reminder_id,
            "user_id": ctx.author.id,
            "channel_id": ctx.channel.id,
            "remind_at": remind_at,
            "message": message,
            "dm": dm
        })

        dt = discord.utils.format_dt(discord.utils.snowflake_time(int(remind_at)), style="R")
        await ctx.send(f"⏰ Reminder set for {dt}.\nID: `{reminder_id}`")

    @remind.command(name="list")
    async def list_reminders(self, ctx):
        """List your active reminders."""
        cursor = self.db.find({"user_id": ctx.author.id})
        reminders = await cursor.to_list(length=100)

        if not reminders:
            return await ctx.send("🔕 No active reminders.")

        embed = discord.Embed(title="Your Reminders", color=discord.Color.blue())
        for r in reminders:
            dt = discord.utils.format_dt(discord.utils.snowflake_time(int(r["remind_at"])), style="R")
            embed.add_field(
                name=f"ID: `{r['_id']}`",
                value=f"{r.get('message', 'No message')}\n⏰ {dt} | {'DM' if r['dm'] else 'Channel'}",
                inline=False
            )

        await ctx.send(embed=embed)

    @remind.command(name="cancel")
    async def cancel_reminder(self, ctx, reminder_id: str):
        """Cancel a reminder by ID."""
        result = await self.db.delete_one({
            "_id": reminder_id,
            "user_id": ctx.author.id
        })
        if result.deleted_count:
            await ctx.send(f"❌ Reminder `{reminder_id}` canceled.")
        else:
            await ctx.send("⚠️ Reminder not found or not yours.")

async def setup(bot):
    await bot.add_cog(Remind(bot))
