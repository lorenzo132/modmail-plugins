from discord.ext import commands as commands
from core import checks
import discord
from core.models import PermissionLevel


class screenshot(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self._last_result = None

    @commands.command()
    @checks.has_permissions(PermissionLevel.ADMINISTRATOR)
    async def screenshot(ctx, args):
 urln = args.lower()
 url = f'{urln}'

 driver = webdriver.Firefox()
 driver.get(url)
 time.sleep(3)
 height = driver.execute_script("return Math.max( document.body.scrollHeight, document.body.offsetHeight, document.documentElement.clientHeight, document.documentElement.scrollHeight, document.documentElement.offsetHeight )")
 print(height)
 driver.close()

 firefox_options = Options()
 firefox_options.add_argument("--headless")
 firefox_options.add_argument(f"--window-size=1920,{height}")
 firefox_options.add_argument("--hide-scrollbars")
 driver = webdriver.Firefox(options=firefox_options)

 driver.get(url)
 time.sleep(3)
 driver.save_screenshot('screen_shot.png')
 driver.close()
 await ctx.send(file=discord.File
 ('screen_shot.png'))
 os.remove("screen_shot.png")

def setup(bot):
    bot.add_cog(screenshot(bot))
