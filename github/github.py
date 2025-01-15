from __future__ import annotations

import re
import discord
from discord.ext import commands
from typing import TYPE_CHECKING, Union

if TYPE_CHECKING:
    from bot import ModmailBot

class GithubPlugin(commands.Cog):
    """GitHub Integration for parsing and displaying pull requests and issues."""

    def __init__(self, bot: ModmailBot):
        self.bot = bot
        self.colors = {
            "pr": {
                "open": 0x2CBE4E,
                "closed": discord.Embed.Empty,
                "merged": discord.Embed.Empty,
            },
            "issues": {"open": 0xE68D60, "closed": discord.Embed.Empty},
        }
        self.regex = r"(\S+)#(\d+)"

    @commands.Cog.listener()
    async def on_message(self, msg: discord.Message):
        if msg.author.bot:
            return

        match = re.search(self.regex, msg.content)
        if not match:
            return

        repo, num = match.groups()

        # Map shorthand to full repository names
        repo_mapping = {
            "modmail": "modmail-dev/modmail",
            "logviewer": "modmail-dev/logviewer",
        }
        repo = repo_mapping.get(repo, repo)

        pr_data = await self.fetch_github_data(f"https://api.github.com/repos/{repo}/pulls/{num}")
        if pr_data and "message" not in pr_data:
            embed = await self.handle_pr(pr_data, repo)
            await msg.channel.send(embed=embed)
            return

        issue_data = await self.fetch_github_data(f"https://api.github.com/repos/{repo}/issues/{num}")
        if issue_data and "message" not in issue_data:
            embed = await self.handle_issue(issue_data, repo)
            await msg.channel.send(embed=embed)

    async def fetch_github_data(self, url: str) -> Union[dict, None]:
        """Fetch data from the GitHub API."""
        try:
            async with self.bot.session.get(url) as response:
                if response.status == 200:
                    return await response.json()
                elif response.status == 404:
                    return None
                else:
                    response_text = await response.text()
                    raise Exception(f"GitHub API returned status {response.status}: {response_text}")
        except Exception as e:
            self.bot.logger.error(f"Failed to fetch GitHub data from {url}: {e}")
            return None

    async def handle_pr(self, data: dict, repo: str) -> discord.Embed:
        """Handle pull request data and return an embed."""
        state = "merged" if data.get("state") == "closed" and data.get("merged") else data["state"]
        embed = self._base_embed(data, repo, is_issue=False)
        embed.colour = self.colors["pr"].get(state, discord.Embed.Empty)
        embed.add_field(name="Additions", value=data["additions"])
        embed.add_field(name="Deletions", value=data["deletions"])
        embed.add_field(name="Commits", value=data["commits"])
        embed.set_footer(text=f"Pull Request #{data['number']}")
        return embed

    async def handle_issue(self, data: dict, repo: str) -> discord.Embed:
        """Handle issue data and return an embed."""
        embed = self._base_embed(data, repo, is_issue=True)
        embed.colour = self.colors["issues"].get(data["state"], discord.Embed.Empty)
        embed.set_footer(text=f"Issue #{data['number']}")
        return embed

    def _base_embed(self, data: dict, repo: str, is_issue: bool = True) -> discord.Embed:
        """Generate a base embed for issues and pull requests."""
        description = (data.get("body", "")[:2045] + "...") if len(data.get("body", "")) > 2048 else data.get("body", "")
        _type = "Issue" if is_issue else "Pull Request"
        title = f"[{repo}] {_type}: #{data['number']} {data['title']}"
        title = (title[:253] + "...") if len(title) > 256 else title

        embed = discord.Embed(title=title, url=data["html_url"], description=description)
        embed.set_thumbnail(url="https://i.imgur.com/J2uqqol.gif")
        embed.set_author(
            name=data["user"]["login"],
            icon_url=data["user"]["avatar_url"],
            url=data["user"]["html_url"],
        )
        embed.add_field(name="Status", value=data["state"].capitalize(), inline=True)

        if data.get("labels"):
            labels = ", ".join(label["name"] for label in data["labels"])
            embed.add_field(name="Labels", value=labels, inline=True)

        return embed

async def setup(bot: ModmailBot) -> None:
    await bot.add_cog(GithubPlugin(bot))
