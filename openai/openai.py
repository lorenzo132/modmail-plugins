import aiohttp
import logging

from discord.ext import commands
from .config import Config

logger = logging.getLogger(__name__)

class OpenAIResponder(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.api_key = Config.OPENAI_API_KEY
        logger.info("OpenAIResponder plugin initialized with API Key %s", self.api_key)

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot:
            return

        logger.info(f"Received a message: {message.content}")

        prompt = f"User: {message.content}\nAI:"
        response = await self.get_openai_response(prompt)
        if response:
            await message.channel.send(response)

    async def get_openai_response(self, prompt):
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        data = {
            "model": "text-davinci-003",
            "prompt": prompt,
            "max_tokens": 150,
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post('https://api.openai.com/v1/completions', headers=headers, json=data) as resp:
                    if resp.status == 200:
                        response_data = await resp.json()
                        logger.info(f"OpenAI API response: {response_data}")
                        return response_data['choices'][0]['text'].strip()
                    else:
                        logger.error(f"OpenAI API request failed with status {resp.status}")
                        return None
        except Exception as e:
            logger.error(f"Exception occurred while calling OpenAI API: {e}")
            return None

async def setup(bot):
    await bot.add_cog(OpenAIResponder(bot))
    logger.info("OpenAIResponder Cog added to bot")