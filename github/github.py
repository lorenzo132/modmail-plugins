import re
import discord
from discord.ext import commands


class GithubPlugin(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.colors = {
            "pr": {
                "open": 0x2CBE4E,
                "closed": None,  # Use None instead of discord.Embed.Empty
                "merged": None,  # Use None instead of discord.Embed.Empty
            },
            "issues": {
                "open": 0xE68D60,
                "closed": None,  # Use None instead of discord.Embed.Empty
            },
        }
        self.regex = r"(\S+)#(\d+)"  # Regex to match GitHub repo references

    @commands.Cog.listener()
    async def on_message(self, msg: discord.Message):
        # Ignore bot messages
        if msg.author.bot:
            return

        match = re.search(self.regex, msg.content)
        if not match:
            return

        repo, num = match.groups()

        # Map short repo names to full repo paths
        if repo == "modmail":
            repo = "modmail-dev/modmail"
        elif repo == "logviewer":
            repo = "modmail-dev/logviewer"

        # Try fetching the pull request (PR) or issue data
        async with self.bot.session.get(
            f"https://api.github.com/repos/{repo}/pulls/{num}"
        ) as pr_response:
            pr_data = await pr_response.json()

            if "message" not in pr_data:
                embed = await self.handle_pr(pr_data, repo)
                await msg.channel.send(embed=embed)
                return

        async with self.bot.session.get(
            f"https://api.github.com/repos/{repo}/issues/{num}"
        ) as issue_response:
            issue_data = await issue_response.json()

            if "message" not in issue_data:
                embed = await self.handle_issue(issue_data, repo)
                await msg.channel.send(embed=embed)

    async def handle_pr(self, data: dict, repo: str) -> discord.Embed:
        # Determine the state of the PR
        state = (
            "merged"
            if data["state"] == "closed" and data.get("merged", False)
            else data["state"]
        )
        embed = self._base(data, repo, is_issue=False)
        embed.colour = self.colors["pr"].get(state)
        embed.add_field(name="Additions", value=data["additions"], inline=True)
        embed.add_field(name="Deletions", value=data["deletions"], inline=True)
        embed.add_field(name="Commits", value=data["commits"], inline=True)
        embed.set_footer(text=f"Pull Request #{data['number']}")
        return embed

    async def handle_issue(self, data: dict, repo: str) -> discord.Embed:
        embed = self._base(data, repo)
        embed.colour = self.colors["issues"].get(data["state"])
        embed.set_footer(text=f"Issue #{data['number']}")
        return embed

    def _base(self, data: dict, repo: str, is_issue: bool = True) -> discord.Embed:
        # Truncate the body if it's too long
        description = (
            f"{data['body'][:2045]}..." if len(data["body"]) > 2048 else data["body"]
        )

        # Determine the type (Issue or Pull Request)
        _type = "Issue" if is_issue else "Pull Request"
        title = f"[{repo}] {_type}: #{data['number']} {data['title']}"
        title = f"{title[:253]}..." if len(title) > 256 else title

        embed = discord.Embed(title=title, url=data["html_url"], description=description)
        embed.set_thumbnail(url="https://i.imgur.com/J2uqqol.gif")
        embed.set_author(
            name=data["user"]["login"],
            icon_url=data["user"]["avatar_url"],
            url=data["user"]["html_url"],
        )
        embed.add_field(name="Status", value=data["state"], inline=True)

        # Add labels if present
        if data.get("labels"):
            labels = ", ".join(label["name"] for label in data["labels"])
            embed.add_field(name="Labels", value=labels, inline=False)

        return embed


async def setup(bot: commands.Bot):
    await bot.add_cog(GithubPlugin(bot))
