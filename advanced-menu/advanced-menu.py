from copy import copy
import traceback
import discord
from discord.ext import commands
from discord.ext.commands.view import StringView
import json

from core import checks
from core.models import DummyMessage, PermissionLevel
from core.utils import normalize_alias

async def invoke_commands(alias, bot, thread, message):
    ctxs = []
    if alias is not None:
        ctxs = []
        aliases = normalize_alias(alias)
        for alias in aliases:
            view = StringView(bot.prefix + alias)
            ctx_ = commands.Context(prefix=bot.prefix, view=view, bot=bot, message=message)
            ctx_.thread = thread
            discord.utils.find(view.skip_string, await bot.get_prefix())
            ctx_.invoked_with = view.get_word().lower()
            ctx_.command = bot.all_commands.get(ctx_.invoked_with)
            ctxs += [ctx_]

    for ctx in ctxs:
        if ctx.command:
            old_checks = copy(ctx.command.checks)
            ctx.command.checks = [checks.has_permissions(PermissionLevel.INVALID)]

            await bot.invoke(ctx)

            ctx.command.checks = old_checks
            continue

class Dropdown(discord.ui.Select):
    def __init__(self, bot, msg, thread, config: dict, data: dict, is_home: bool):
        self.bot = bot
        self.msg = msg
        self.thread = thread
        self.config = config
        self.data = data
        self.is_home = is_home
        options = [
            discord.SelectOption(label=line["label"], description=line["description"], emoji=line["emoji"]) for line in data.values()
        ]
        if not is_home:
            options.append(discord.SelectOption(label="Main menu", description="Go back to the main menu", emoji="🏠"))
        super().__init__(placeholder=self.config["dropdown_placeholder"], min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        try:
            # await interaction.response.send_message("You selected {}".format(self.values[0]))
            await interaction.response.defer()
            await self.view.done()
            if  self.values[0] == "Main menu":
                await self.msg.edit(view=DropdownView(self.bot, self.msg, self.thread, self.config, self.config["options"], True))
            elif self.data[self.values[0]]["type"] == "command":
                await invoke_commands(self.data[self.values[0]]["callback"], self.bot, self.thread, DummyMessage(copy(self.thread._genesis_message)))
            else:
                await self.msg.edit(view=DropdownView(self.bot, self.msg, self.thread, self.config, self.config["submenus"][self.data[self.values[0]]["callback"]], False))
        except Exception as e:
                print(traceback.format_exc())

class DropdownView(discord.ui.View):
    def __init__(self, bot, msg: discord.Message, thread, config: dict, options: dict, is_home: bool):
        self.bot = bot
        self.msg = msg
        self.thread = thread
        self.config = config
        super().__init__(timeout=self.config["timeout"])
        self.add_item(Dropdown(bot, msg, thread, config, options, is_home))

    async def on_timeout(self):
        await self.msg.edit(view=None)
        await self.msg.channel.send("Timed out")
        if self.config["delete_on_timeout"]:
            await self.thread.close(closer=self.bot.guild.me)

    async def done(self):
        self.stop()
        await self.msg.edit(view=None)

class AdvancedMenu(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db = self.bot.plugin_db.get_partition(self)
        self.config = None
        self.default_config = {"enabled": False, "options": {}, "submenus": {}, "timeout": 20, "delete_on_timeout": False, "embed_text": "Please select an option.", "dropdown_placeholder": "Select an option to contact the staff team."}

    async def cog_load(self):
        self.config = await self.db.find_one({"_id": "advanced-menu"})
        if self.config is None:
            self.config = self.default_config
            await self.update_config()

    async def update_config(self):
        await self.db.find_one_and_update(
            {"_id": "advanced-menu"},
            {"$set": self.config},
            upsert=True,
        )

    @commands.Cog.listener()
    async def on_thread_ready(self, thread, creator, category, initial_message):
        if self.config["enabled"] and self.config["options"] != {}:
            dummyMessage = DummyMessage(copy(initial_message))
            dummyMessage.author = self.bot.modmail_guild.me
            dummyMessage.content = self.config["embed_text"]

            # clear message of residual attributes from the copy
            dummyMessage.attachments = []
            dummyMessage.components = []
            dummyMessage.embeds = []
            dummyMessage.stickers = []

            msgs, _ = await thread.reply(dummyMessage)
            main_recipient_msg = None

            for m in msgs:
                if m.channel.recipient == thread.recipient:
                    main_recipient_msg = m
                    break

            await main_recipient_msg.edit(view=DropdownView(self.bot, main_recipient_msg, thread, self.config, self.config["options"], True))

    @checks.has_permissions(PermissionLevel.ADMINISTRATOR)
    @commands.group(invoke_without_command=True)
    async def advancedmenu(self, ctx):
        """Advanced menu settings."""
        await ctx.send_help(ctx.command)

    @checks.has_permissions(PermissionLevel.ADMINISTRATOR)
    @advancedmenu.group(name="config", invoke_without_command=True)
    async def advancedmenu_config(self, ctx):
        """Advanced menu config settings."""
        await ctx.send_help(ctx.command)

    @checks.has_permissions(PermissionLevel.ADMINISTRATOR)
    @advancedmenu_config.command(name="get")
    async def advancedmenu_config_get(self, ctx):
        """Get the current config."""
        embed = discord.Embed(title="Advanced menu config", description="The current config for the advanced menu.", color=discord.Color.blurple())
        embed.add_field(name="Enabled", value=self.config["enabled"])
        embed.add_field(name="Timeout", value=self.config["timeout"])
        embed.add_field(name="Delete on timeout", value=self.config["delete_on_timeout"])
        embed.add_field(name="Embed text", value=self.config["embed_text"])
        embed.add_field(name="Dropdown placeholder", value=self.config["dropdown_placeholder"])
        await ctx.send(embed=embed)

    @checks.has_permissions(PermissionLevel.ADMINISTRATOR)
    @advancedmenu_config.command(name="timeout")
    async def advancedmenu_config_timeout(self, ctx, timeout: int):
        """Set the timeout for the dropdown menu."""
        if timeout < 1:
            return await ctx.send("Timeout must be greater than 1.")
        self.config["timeout"] = timeout
        await self.update_config()
        await ctx.send("Timeout set.")

    @checks.has_permissions(PermissionLevel.ADMINISTRATOR)
    @advancedmenu_config.command(name="delete_on_timeout")
    async def advancedmenu_config_delete_on_timeout(self, ctx, delete_on_timeout: bool):
        """Set whether to delete the menu on timeout."""
        self.config["delete_on_timeout"] = delete_on_timeout
        await self.update_config()
        await ctx.send("Done.")

    @checks.has_permissions(PermissionLevel.ADMINISTRATOR)
    @advancedmenu_config.command(name="embed_text")
    async def advancedmenu_config_embed_text(self, ctx, *, embed_text: str):
        """Set the embed text."""
        self.config["embed_text"] = embed_text
        await self.update_config()
        await ctx.send("Done.")

    @checks.has_permissions(PermissionLevel.ADMINISTRATOR)
    @advancedmenu_config.command(name="dropdown_placeholder")
    async def advancedmenu_config_dropdown_placeholder(self, ctx, *, dropdown_placeholder: str):
        """Set the dropdown placeholder text."""
        self.config["dropdown_placeholder"] = dropdown_placeholder
        await self.update_config()
        await ctx.send("Done.")

    @checks.has_permissions(PermissionLevel.ADMINISTRATOR)
    @advancedmenu.command(name="toggle")
    async def advancedmenu_toggle(self, ctx):
        """Toggle the advanced menu."""
        self.config["enabled"] = not self.config["enabled"]
        await self.update_config()
        await ctx.send(f"Advanced menu is now {'enabled' if self.config['enabled'] else 'disabled'}.")

    @checks.has_permissions(PermissionLevel.ADMINISTRATOR)
    @advancedmenu.command(name="show")
    async def advancedmenu_show(self, ctx):
        """Show the current options of the main menu"""
        if self.config["options"] == {}:
            return await ctx.send("There are no options in the main menu.")
        embed = discord.Embed(title="Main menu", color=discord.Color.blurple())
        for k, v in self.config["options"].items():
            embed.add_field(name=v["label"], value=v["description"], inline=False)
        await ctx.send(embed=embed)

    @checks.has_permissions(PermissionLevel.ADMINISTRATOR)
    @advancedmenu.group(name="option", invoke_without_command=True)
    async def advancedmenu_option(self, ctx):
        """Advanced menu option settings."""
        await ctx.send_help(ctx.command)

    @checks.has_permissions(PermissionLevel.ADMINISTRATOR)
    @advancedmenu_option.command(name="show")
    async def advancedmenu_option_show(self, ctx, *, option: str):
        """Show the details of an option in the main menu"""
        if option not in self.config["options"]:
            return await ctx.send("That option does not exist.")
        embed = discord.Embed(title=self.config["options"][option]["label"], color=discord.Color.blurple())
        embed.add_field(name="Description", value=self.config["options"][option]["description"], inline=False)
        embed.add_field(name="Emoji", value=self.config["options"][option]["emoji"], inline=False)
        embed.add_field(name="Type", value=self.config["options"][option]["type"], inline=False)
        embed.add_field(name="Command" if self.config["options"][option]["type"] == "command" else "Submenu", value=self.config["options"][option]["callback"], inline=False)
        await ctx.send(embed=embed)

    @checks.has_permissions(PermissionLevel.ADMINISTRATOR)
    @advancedmenu_option.command(name="add")
    async def advancedmenu_option_add(self, ctx):
        """Add an option to the advanced menu."""
        def check(m):
            return m.author == ctx.author and m.channel == ctx.channel

        def typecheck(m):
            return m.author == ctx.author and m.channel == ctx.channel and m.content.lower() in ["command", "submenu"]

        if len(self.config["options"]) >= 25:
            return await ctx.send("You can only have a maximum of 25 options due to discord limitations.")

        await ctx.send("You can type `cancel` at any time to cancel the process.")
        await ctx.send("What is the label of the option?")
        label = (await self.bot.wait_for("message", check=check)).content

        if label.lower() == "cancel":
            return await ctx.send("Cancelled.")

        if label in self.config["options"]:
            await ctx.send("That option already exists. Use `advancedmenu edit` to edit it.")
            return

        await ctx.send("What is the description of the option?")
        description = (await self.bot.wait_for("message", check=check)).content

        if description.lower() == "cancel":
            return await ctx.send("Cancelled.")

        if len(description) > 100:
            return await ctx.send("The description must be less than 100 characters due to discord limitations.")

        await ctx.send("What is the emoji of the option?")
        emoji = (await self.bot.wait_for("message", check=check)).content

        if emoji.lower() == "cancel":
            return await ctx.send("Cancelled.")

        await ctx.send("What is the type of the option? (command/submenu)")
        type = (await self.bot.wait_for("message", check=typecheck)).content.lower()

        if type == "cancel":
            return await ctx.send("Cancelled.")

        if type == "command":
            await ctx.send("What is the command to run for the option?")
        else:
            await ctx.send("What is the label of the submenu for the option?")
        callback = (await self.bot.wait_for("message", check=check)).content

        if callback.lower() == "cancel":
            return await ctx.send("Cancelled.")

        if type == "submenu" and callback not in self.config["submenus"]:
            return await ctx.send("That submenu does not exist. Use `advancedmenu submenu create` to add it.")

        self.config["options"][label] = {
            "label": label,
            "description": description,
            "emoji": emoji,
            "type": type,
            "callback": callback
        }
        await self.update_config()
        await ctx.send("Option added.")

    @checks.has_permissions(PermissionLevel.ADMINISTRATOR)
    @advancedmenu_option.command(name="remove")
    async def advancedmenu_option_remove(self, ctx, *, label):
        """Remove an option from the advanced menu."""
        if label not in self.config["options"]:
            return await ctx.send("That option does not exist.")

        del self.config["options"][label]
        await self.update_config()
        await ctx.send("Option removed.")

    @checks.has_permissions(PermissionLevel.ADMINISTRATOR)
    @advancedmenu_option.command(name="edit")
    async def advancedmenu_option_edit(self, ctx, *, label):
        """Edit an option from the advanced menu."""
        if label not in self.config["options"]:
            return await ctx.send("That option does not exist.")

        def check(m):
            return m.author == ctx.author and m.channel == ctx.channel

        def typecheck(m):
            return m.author == ctx.author and m.channel == ctx.channel and m.content.lower() in ["command", "submenu"]

        await ctx.send("You can send `cancel` at any time to cancel the process.")
        await ctx.send("What is the new description of the option?")
        description = (await self.bot.wait_for("message", check=check)).content

        if description.lower() == "cancel":
            return await ctx.send("Cancelled.")

        if len(description) > 100:
            return await ctx.send("The description must be less than 100 characters due to discord limitations.")

        await ctx.send("What is the new emoji of the option?")
        emoji = (await self.bot.wait_for("message", check=check)).content

        if emoji.lower() == "cancel":
            return await ctx.send("Cancelled.")

        await ctx.send("What is the new type of the option? (command/submenu)")
        type = (await self.bot.wait_for("message", check=typecheck)).content.lower()

        if type == "cancel":
            return await ctx.send("Cancelled.")

        if type == "command":
            await ctx.send("What is the new command to run for the option?")
        else:
            await ctx.send("What is the new label of the new submenu for the option?")
        callback = (await self.bot.wait_for("message", check=check)).content

        if callback.lower() == "cancel":
            return await ctx.send("Cancelled.")

        if type == "submenu" and callback not in self.config["submenus"]:
            return await ctx.send("That submenu does not exist. Use `advancedmenu submenu create` to add it.")

        self.config["options"][label] = {
            "label": label,
            "description": description,
            "emoji": emoji,
            "type": type,
            "callback": callback
        }

        await self.update_config()
        await ctx.send("Option edited.")

    @checks.has_permissions(PermissionLevel.ADMINISTRATOR)
    @advancedmenu.group(name="submenu", invoke_without_command=True)
    async def advancedmenu_submenu(self, ctx):
        """Advanced menu submenu settings."""
        await ctx.send_help(ctx.command)

    @checks.has_permissions(PermissionLevel.ADMINISTRATOR)
    @advancedmenu_submenu.command(name="create")
    async def advancedmenu_submenu_create(self, ctx, *, label):
        """Create a submenu for the advanced menu."""
        if label in self.config["submenus"]:
            return await ctx.send("That submenu already exists. Please use a unique label or use `advancedmenu submenu delete` to delete it.")

        self.config["submenus"][label] = {}
        await self.update_config()
        await ctx.send("Submenu created.")

    @checks.has_permissions(PermissionLevel.ADMINISTRATOR)
    @advancedmenu_submenu.command(name="delete")
    async def advancedmenu_submenu_delete(self, ctx, *, label):
        """Delete a submenu for the advanced menu."""
        if label not in self.config["submenus"]:
            return await ctx.send("That submenu does not exist.")

        del self.config["submenus"][label]
        await self.update_config()
        await ctx.send("Submenu deleted.")

    @checks.has_permissions(PermissionLevel.ADMINISTRATOR)
    @advancedmenu_submenu.command(name="list")
    async def advancedmenu_submenu_list(self, ctx):
        """List all submenus for the advanced menu."""
        if not self.config["submenus"]:
            return await ctx.send("There are no submenus.")

        submenu_list = "Submenus:\n" + ('\n'.join(self.config['submenus'].keys()))

        if len(submenu_list) > 2000:
            submenu_list = submenu_list[:1997] + "..."

        await ctx.send(submenu_list)

    @checks.has_permissions(PermissionLevel.ADMINISTRATOR)
    @advancedmenu_submenu.command(name="show")
    async def advancedmenu_submenu_show(self, ctx, *, label):
        """Show the options of a submenu."""
        if label not in self.config["submenus"]:
            return await ctx.send("That submenu does not exist. Use `advancedmenu submenu create` to add it.")

        if self.config["submenus"][label] == {}:
            return await ctx.send(f"There are no options in {label}")
        embed = discord.Embed(title=label, color=discord.Color.blurple())
        for v in self.config["submenus"][label].values():
            embed.add_field(name=v["label"], value=v["description"], inline=False)
        await ctx.send(embed=embed)

    @checks.has_permissions(PermissionLevel.ADMINISTRATOR)
    @advancedmenu_submenu.group(name="option", invoke_without_command=True)
    async def advancedmenu_submenu_option(self, ctx):
        """Advanced menu submenu option settings."""
        await ctx.send_help(ctx.command)

    @checks.has_permissions(PermissionLevel.ADMINISTRATOR)
    @advancedmenu_submenu_option.command(name="show")
    async def advancedmenu_submenu_option_show(self, ctx, *, label):
        """Show the details of an option in the submenu"""
        if label not in self.config["submenus"]:
            return await ctx.send("That submenu does not exist. Use `advancedmenu submenu create` to add it.")

        def check(m):
            return m.author == ctx.author and m.channel == ctx.channel

        await ctx.send("You can send `cancel` at any time to cancel the process.")
        await ctx.send("What is the label of the option?")
        option = (await self.bot.wait_for("message", check=check)).content

        if option.lower() == "cancel":
            return await ctx.send("Cancelled.")

        if option not in self.config["submenus"][label]:
            return await ctx.send("That option does not exist.")
        embed = discord.Embed(title=self.config["submenus"][label][option]["label"], color=discord.Color.blurple())
        embed.add_field(name="Description", value=self.config["submenus"][label][option]["description"], inline=False)
        embed.add_field(name="Emoji", value=self.config["submenus"][label][option]["emoji"], inline=False)
        embed.add_field(name="Type", value=self.config["submenus"][label][option]["type"], inline=False)
        embed.add_field(name="Command" if self.config["submenus"][label][option]["type"] == "command" else "Submenu", value=self.config["submenus"][label][option]["callback"], inline=False)
        await ctx.send(embed=embed)

    @checks.has_permissions(PermissionLevel.ADMINISTRATOR)
    @advancedmenu_submenu_option.command(name="add")
    async def advancedmenu_submenu_option_add(self, ctx, *, submenu: str):
        """Add an option to the advanced submenu."""
        def check(m):
            return m.author == ctx.author and m.channel == ctx.channel

        def typecheck(m):
            return m.author == ctx.author and m.channel == ctx.channel and m.content.lower() in ["command", "submenu"]

        if submenu not in self.config["submenus"]:
            return await ctx.send("That submenu does not exist.")

        if len(self.config["submenus"][submenu]) >= 24:
            return await ctx.send("You can only have a maximum of 24 options due to discord limitations.")

        await ctx.send("You can send `cancel` at any time to cancel the process.")
        await ctx.send("What is the label of the option?")
        label = (await self.bot.wait_for("message", check=check)).content

        if label.lower() == "cancel":
            return await ctx.send("Cancelled.")

        if label == "Main menu":
            return await ctx.send("You cannot use that label.")

        if label in self.config["submenus"][submenu]:
            await ctx.send("That option already exists. Use `advancedmenu submenu edit` to edit it.")
            return

        await ctx.send("What is the description of the option?")
        description = (await self.bot.wait_for("message", check=check)).content

        if description.lower() == "cancel":
            return await ctx.send("Cancelled.")

        if len(description) > 100:
            return await ctx.send("The description must be less than 100 characters due to discord limitations.")

        await ctx.send("What is the emoji of the option?")
        emoji = (await self.bot.wait_for("message", check=check)).content

        if emoji.lower() == "cancel":
            return await ctx.send("Cancelled.")

        await ctx.send("What is the type for the option? (command/submenu)")
        type = (await self.bot.wait_for("message", check=typecheck)).content.lower()

        if type == "cancel":
            return await ctx.send("Cancelled.")

        if type == "command":
            await ctx.send("What is the command to run for the option?")
        else:
            await ctx.send("What is the label of the submenu for the option?")
        callback = (await self.bot.wait_for("message", check=check)).content

        if type == "submenu" and callback not in self.config["submenus"]:
            return await ctx.send("That submenu does not exist. Use `advancedmenu submenu create` to add it.")

        self.config["submenus"][submenu][label] = {
            "label": label,
            "description": description,
            "emoji": emoji,
            "type": type,
            "callback": callback
        }
        await self.update_config()
        await ctx.send("Option added.")

    @checks.has_permissions(PermissionLevel.ADMINISTRATOR)
    @advancedmenu_submenu_option.command(name="remove")
    async def advancedmenu_submenu_option_remove(self, ctx, *, submenu: str):
        """Remove an option from the advanced submenu."""
        def check(m):
            return m.author == ctx.author and m.channel == ctx.channel

        await ctx.send("You can send `cancel` at any time to cancel the process.")
        await ctx.send("What is the label of the option to remove?")
        label = (await self.bot.wait_for("message", check=check)).content

        if label.lower() == "cancel":
            return await ctx.send("Cancelled.")

        if label not in self.config["submenus"][submenu]:
            return await ctx.send("That option does not exist.")

        del self.config["submenus"][submenu][label]
        await self.update_config()
        await ctx.send("Option removed.")

    @checks.has_permissions(PermissionLevel.ADMINISTRATOR)
    @advancedmenu_submenu_option.command(name="edit")
    async def advancedmenu_submenu_option_edit(self, ctx, *, submenu: str):
        """Edit an option from the advanced submenu."""
        def check(m):
            return m.author == ctx.author and m.channel == ctx.channel

        def typecheck(m):
            return m.author == ctx.author and m.channel == ctx.channel and m.content.lower() in ["command", "submenu"]

        if submenu not in self.config["submenus"]:
            return await ctx.send("That submenu does not exist. Use `advancedmenu submenu create` to add it.")

        await ctx.send("You can send `cancel` at any time to cancel the process.")
        await ctx.send("What is the label of the option to edit?")
        label = (await self.bot.wait_for("message", check=check)).content

        if label.lower() == "cancel":
            return await ctx.send("Cancelled.")

        if label not in self.config["submenus"][submenu]:
            return await ctx.send("That label does not exist.")

        await ctx.send("What is the new description of the option?")
        description = (await self.bot.wait_for("message", check=check)).content

        if description.lower() == "cancel":
            return await ctx.send("Cancelled.")

        if len(description) > 100:
            return await ctx.send("The description must be less than 100 characters due to discord limitations.")

        await ctx.send("What is the new emoji of the option?")
        emoji = (await self.bot.wait_for("message", check=check)).content

        if emoji.lower() == "cancel":
            return await ctx.send("Cancelled.")

        await ctx.send("What is the new type for the option? (command/submenu)")
        type = (await self.bot.wait_for("message", check=typecheck)).content.lower()

        if type == "cancel":
            return await ctx.send("Cancelled.")

        if type == "command":
            await ctx.send("What is the command to run for the option?")
        else:
            await ctx.send("What is the label of the submenu for the option?")
        callback = (await self.bot.wait_for("message", check=check)).content

        if callback.lower() == "cancel":
            return await ctx.send("Cancelled.")

        if type == "submenu" and callback not in self.config["submenus"]:
            return await ctx.send("That submenu does not exist.")

        self.config["submenus"][submenu][label]["description"] = description
        self.config["submenus"][submenu][label]["emoji"] = emoji
        self.config["submenus"][submenu][label]["type"] = type
        self.config["submenus"][submenu][label]["callback"] = callback

        await self.update_config()
        await ctx.send("Option edited.")

    @checks.has_permissions(PermissionLevel.ADMINISTRATOR)
    @advancedmenu.command(name="update_config")
    async def advancedmenu_update_config(self, ctx):
        """Force an update of the config format"""

        missing = []
        for key in self.default_config.keys():
            if key not in self.config:
                missing.append(key)

        if missing:
            await ctx.send("The following keys are missing from the config: " + ", ".join(missing))
            for key in missing:
                self.config[key] = self.default_config[key]

        await self.update_config()

    @checks.has_permissions(PermissionLevel.ADMINISTRATOR)
    @advancedmenu.command(name="dump_config")
    async def advancedmenu_dump_config(self, ctx):
        """Dump the config to chat"""

        with open("config.json", "w") as f:
            json.dump(self.config, f, indent=4)

        await ctx.send(file=discord.File("config.json"))

async def setup(bot):
    await bot.add_cog(AdvancedMenu(bot))