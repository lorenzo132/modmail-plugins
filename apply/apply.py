import discord

from discord.ext import commands

from core import checks
from core.models import PermissionLevel


class Appli(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db = bot.plugin_db.get_partition(self)
        self.positions = list()
        self.questions = dict()
        self.category = None
        self.categories = dict()
        self.mention = None
        self.user_active = list()
        self.active_channels = list()
        self.cache = dict()
        bot.loop.create_task(self._set_db())

    async def _set_db(self):
        config = await self.db.find_one({"_id": "config"})
        if config is None:
            await self._update_db()
            return

        self.positions = config.get("positions", self.positions)
        self.questions = config.get("questions", self.questions)
        self.category = config.get("category", self.category)
        self.categories = config.get("categories", self.categories)
        self.mention = config.get("mention", self.mention)
        self.user_active = config.get("cache_active", self.user_active)
        self.active_channels = config.get("cache_channels", self.active_channels)
        self.cache = config.get("cache", self.cache)

    async def _update_db(self):
        await self.db.find_one_and_update(
            {"_id": "config"},
            {
                "$set": {
                    "positions": self.positions,
                    "questions": self.questions,
                    "category": self.category,
                    "categories": self.categories,
                    "mention": self.mention,
                    "cache_active": self.user_active,
                    "cache_channels": self.active_channels,
                    "cache": self.cache
                }
            },
            upsert=True,
        )

    @commands.group(name="positions", invoke_without_command=True)
    @checks.has_permissions(PermissionLevel.OWNER)
    async def positions(self, ctx: commands.Context):
        """
        Configure open positions
        """

        await ctx.send_help(ctx.command)
        return

    @positions.command(name="add")
    @checks.has_permissions(PermissionLevel.OWNER)
    async def pos_add(self, ctx: commands.Context, pos: str):
        """
        Add a position to apply for.
        """

        self.positions.append(pos)
        await self._update_db()
        await ctx.send("Added")
        return

    @positions.command(name="remove")
    @checks.has_permissions(PermissionLevel.OWNER)
    async def pos_remove(self, ctx):
        """
        Remove position
        """

        def check(msg):
            return msg.author.id == ctx.author.id and msg.channel.id == ctx.channel.id

        embed = discord.Embed(description="")
        if len(self.positions) <= 0:
            await ctx.send("No Positions")
            return

        for i in range(len(self.positions)):
            embed.description += f"\n`{i}.` {self.positions[i]}"

        await ctx.send("Select one to remove / type `cancel` to cancel", embed=embed)
        res = await self.bot.wait_for("message", check=check)
        if res.content == "cancel":
            await ctx.send("Cancelled")
            return

        try:
            self.positions.pop(int(res.content))
            await self._update_db()
            await ctx.send("Done")
            return
        except Exception as e:
            await ctx.send("An error occured")
            return

    @positions.command(name="list")
    @checks.has_permissions(PermissionLevel.OWNER)
    async def pos_list(self, ctx):
        """
        list positions
        """
        embed = discord.Embed(description="")
        if len(self.positions) <= 0:
            await ctx.send("No Positions")
            return

        for i in range(len(self.positions)):
            embed.description += f"\n`{i}.` {self.positions[i]}"

        await ctx.send(embed=embed)
        return

    @commands.group(name="questions", invoke_without_command=True)
    @checks.has_permissions(PermissionLevel.OWNER)
    async def questions(self, ctx: commands.Context):
        """
        Configure questions
        """

        await ctx.send_help(ctx.command)
        return

    @questions.command(name="add")
    @checks.has_permissions(PermissionLevel.OWNER)
    async def ques_add(self, ctx, pos: str, *, question: str):
        """
        Add a question
        """

        if pos not in self.positions:
            await ctx.send(f"No Position found with name - {pos}")
            return

        if pos in self.questions:
            questions = self.questions[pos]
        else:
            questions = list()

        questions.append(question)
        self.questions[pos] = questions
        await ctx.send("Added")
        await self._update_db()
        return

    @questions.command(name="remove")
    @checks.has_permissions(PermissionLevel.OWNER)
    async def ques_remove(self, ctx, pos: str):
        """
        Remove a question
        """

        def check(msg):
            return msg.author.id == ctx.author.id and msg.channel.id == ctx.channel.id

        if pos not in self.positions:
            await ctx.send(f"No Position found with name - {pos}")
            return

        if pos not in self.questions:
            await ctx.send("No questions found")
            return

        questions = self.questions[pos]
        embed = discord.Embed(description="")

        for i in range(len(questions)):
            embed.description += f"\n`{i}.` {questions[i]}"

        await ctx.send("Select one to remove / type `cancel` to cancel", embed=embed)
        res = await self.bot.wait_for("message", check=check)
        if res.content == "cancel":
            await ctx.send("Cancelled")
            return

        try:
            questions.pop(int(res.content))
            self.questions[pos] = questions
            await self._update_db()
            await ctx.send("Done")
            return
        except Exception as e:
            await ctx.send("An error occured")
            return

    @questions.command(name="list")
    @checks.has_permissions(PermissionLevel.OWNER)
    async def ques_list(self, ctx, pos: str):
        """
        list questins
        """
        embed = discord.Embed(description="")
        if pos not in self.positions:
            await ctx.send(f"No Position found with name - {pos}")
            return

        if pos not in self.questions:
            await ctx.send("No questions found")
            return

        questions = self.questions[pos]
        for i in range(len(questions)):
            embed.description += f"\n`{i}.` {questions[i]}"

        await ctx.send(embed=embed)
        return

    @commands.command()
    @checks.has_permissions(PermissionLevel.ADMIN)
    async def set_cat(self, ctx, category: discord.CategoryChannel):
        """
        Set category
        """

        self.category = str(category.id)
        await self._update_db()
        await ctx.send("Done")
        return

    @commands.command()
    @checks.has_permissions(PermissionLevel.REGULAR)
    async def apply(self, ctx):
        """
        Apply for a position
        """

        if ctx.author.id in self.user_active:
            await ctx.send("You have already applied, please wait till it is closed")
            return

        self.user_active.append(ctx.author.id)
        if self.category is None:
            await ctx.send("This command has not been configured")
            self.user_active.remove(ctx.author.id)
            return

        category = ctx.guild.get_channel(int(self.category))
        if category is None:
            await ctx.send("Can't find category")
            self.user_active.remove(ctx.author.id)
            return

        channel = await ctx.guild.create_text_channel(
            str(ctx.author), category=category
        )

        selection_embed = discord.Embed(colour=0x26FCB1, description="")
        open_pos = list()
        self.active_channels.append(channel.id)
        self.cache[str(channel.id)] = ctx.author.id
        await self._update_db()

        for position in range(len(self.positions)):
            if self.positions[position] not in self.questions:
                continue

            selection_embed.description += f"`{self.positions[position]}`"
            open_pos.append(self.positions[position])

        await channel.send(
            f"{ctx.author.mention} Please select the position you want to apply for: ",
            embed=selection_embed,
        )

        def check(msg):
            return msg.author.id == ctx.author.id and msg.channel.id == channel.id

        has_selected = False
        posi = None

        while has_selected is not True:
            res = await self.bot.wait_for("message", check=check)

            if res.content not in open_pos:
                await channel.send(
                    embed=discord.Embed(
                        colour=0xFA2111, description="Please select the correct option."
                    )
                )
            else:
                posi = res.content
                has_selected = True

        await channel.send("**Answer the following questions __in one message__**")

        questions = self.questions[posi]
        answers = list()

        for i in range(len(questions)):
            await channel.send(
                embed=discord.Embed(colour=0x21E1FF, description=f"Q. {questions[i]}")
            )

            res = await self.bot.wait_for("message", check=check)
            answers.append(res.content)

        if self.mention:
            await channel.send(self.mention)

    @commands.command(name="apply-mention")
    @checks.has_permissions(PermissionLevel.OWNER)
    async def apply_mention(self, ctx, *, mention):
        """
        Set a mention after every successful submission
        """

        self.mention = mention
        await self._update_db()
        await ctx.send("Done")

    @commands.command(name="apply-close", aliases=["applyc"])
    @checks.has_permissions(PermissionLevel.ADMIN)
    async def apply_close(self, ctx):
        """
        close application
        """

        if ctx.channel.id not in self.active_channels:
            await ctx.send("Not in cache, can't delete")
            return

        self.user_active.remove(int(self.cache[str(ctx.channel.id)]))
        self.active_channels.remove(ctx.channel.id)
        del self.cache[str(ctx.channel.id)]
        await self._update_db()
        await ctx.channel.delete()
        return

def setup(bot):
    bot.add_cog(Appli(bot))
