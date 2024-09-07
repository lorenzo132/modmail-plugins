import discord
from discord.ext import commands
import yt_dlp as youtube_dl
from async_timeout import timeout
from functools import partial
import asyncio
import random
import ipaddress

# Suppress noise about console usage from yt-dlp
youtube_dl.utils.bug_reports_message = lambda: ''

# Function to generate a random IPv6 address from a given CIDR block
def random_ipv6_from_range(cidr_block):
    network = ipaddress.IPv6Network(cidr_block)
    random_ip_int = random.randint(int(network.network_address), int(network.broadcast_address))
    return str(ipaddress.IPv6Address(random_ip_int))

# Example IPv6 range for random IP generation (adjust to your own range)
ipv6_cidr_block = '2001:db8::/64'

# Configure yt-dlp options with random IPv6 rotation
ytdl_format_options = {
    'format': 'bestaudio/best',
    'outtmpl': '%(extractor)s-%(id)s-%(title)s.%(ext)s',
    'restrictfilenames': True,
    'noplaylist': True,
    'nocheckcertificate': True,
    'ignoreerrors': False,
    'logtostderr': False,
    'quiet': True,
    'no_warnings': True,
    'default_search': 'auto',
    'source_address': random_ipv6_from_range(ipv6_cidr_block)  # Use a random IPv6 address
}

ffmpeg_options = {
    'options': '-vn'
}

ytdl = youtube_dl.YoutubeDL(ytdl_format_options)

class YTDLSource(discord.PCMVolumeTransformer):
    def __init__(self, source, *, data, volume=0.5):
        super().__init__(source, volume)
        self.data = data
        self.title = data.get('title')
        self.url = data.get('url')

    @classmethod
    async def from_url(cls, url, *, loop=None, stream=False):
        # Update source address to a new random IPv6 before each request
        ytdl.params['source_address'] = random_ipv6_from_range(ipv6_cidr_block)
        loop = loop or asyncio.get_event_loop()
        data = await loop.run_in_executor(None, lambda: ytdl.extract_info(url, download=not stream))

        if 'entries' in data:
            # Take the first item from a playlist
            data = data['entries'][0]

        filename = data['url'] if stream else ytdl.prepare_filename(data)
        return cls(discord.FFmpegPCMAudio(filename, **ffmpeg_options), data=data)


class Music(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.queue = {}
        self.current = {}
        self.loop = {}

    async def ensure_voice(self, ctx):
        if not ctx.voice_client:
            if ctx.author.voice:
                await ctx.author.voice.channel.connect()
            else:
                await ctx.send("You are not connected to a voice channel.")
                raise commands.CommandError("Author not connected to a voice channel.")
        elif ctx.voice_client.is_playing():
            ctx.voice_client.stop()

    @commands.command(name="play", aliases=["p"])
    async def play(self, ctx, *, url):
        """Plays a song or adds it to the queue."""
        await self.ensure_voice(ctx)

        async with ctx.typing():
            try:
                player = await YTDLSource.from_url(url, loop=self.bot.loop, stream=True)
                ctx.voice_client.play(player, after=lambda e: self.next(ctx))
                self.current[ctx.guild.id] = player
                await ctx.send(f'Now playing: {player.title}')
            except Exception as e:
                await ctx.send(f"An error occurred: {e}")

    def next(self, ctx):
        if ctx.guild.id in self.queue and len(self.queue[ctx.guild.id]) > 0:
            next_song = self.queue[ctx.guild.id].pop(0)
            self.bot.loop.create_task(self.play(ctx, url=next_song))
        else:
            self.current.pop(ctx.guild.id, None)

    @commands.command(name="pause")
    async def pause(self, ctx):
        """Pauses the currently playing song."""
        if ctx.voice_client.is_playing():
            ctx.voice_client.pause()
            await ctx.send("Playback paused.")

    @commands.command(name="resume")
    async def resume(self, ctx):
        """Resumes the currently paused song."""
        if ctx.voice_client.is_paused():
            ctx.voice_client.resume()
            await ctx.send("Playback resumed.")

    @commands.command(name="skip")
    async def skip(self, ctx):
        """Skips the currently playing song."""
        if ctx.voice_client.is_playing():
            ctx.voice_client.stop()
            await ctx.send("Song skipped.")

    @commands.command(name="stop")
    async def stop(self, ctx):
        """Stops playing and clears the queue."""
        if ctx.voice_client:
            ctx.voice_client.stop()
            self.queue[ctx.guild.id] = []
            await ctx.send("Playback stopped and queue cleared.")

    @commands.command(name="queue")
    async def queue_(self, ctx):
        """Shows the current song queue."""
        if ctx.guild.id in self.queue and self.queue[ctx.guild.id]:
            await ctx.send("\n".join(self.queue[ctx.guild.id]))
        else:
            await ctx.send("The queue is currently empty.")

    @commands.command(name="loop")
    async def loop_(self, ctx):
        """Toggles looping of the currently playing song."""
        self.loop[ctx.guild.id] = not self.loop.get(ctx.guild.id, False)
        await ctx.send(f"Looping is now {'enabled' if self.loop[ctx.guild.id] else 'disabled'}.")

    @commands.command(name="shuffle")
    async def shuffle(self, ctx):
        """Shuffles the queue."""
        if ctx.guild.id in self.queue and len(self.queue[ctx.guild.id]) > 1:
            random.shuffle(self.queue[ctx.guild.id])
            await ctx.send("Queue shuffled.")
        else:
            await ctx.send("Not enough songs in the queue to shuffle.")

    @commands.command(name="seek")
    async def seek(self, ctx, *, position: int):
        """Seeks to a specific point in the song."""
        ctx.voice_client.stop()
        await ctx.send(f"Seeking to {position} seconds not yet implemented.")

    @commands.command(name="volume")
    async def volume(self, ctx, volume: int):
        """Changes the player's volume."""
        if ctx.voice_client and ctx.voice_client.source:
            ctx.voice_client.source.volume = volume / 100
            await ctx.send(f"Volume set to {volume}%")

    @commands.command(name="nowplaying", aliases=["np"])
    async def nowplaying(self, ctx):
        """Displays the currently playing song."""
        if ctx.guild.id in self.current and self.current[ctx.guild.id]:
            await ctx.send(f"Now playing: {self.current[ctx.guild.id].title}")
        else:
            await ctx.send("No song is currently playing.")

    @play.before_invoke
    @stop.before_invoke
    @pause.before_invoke
    @resume.before_invoke
    @skip.before_invoke
    async def ensure_voice_state(self, ctx):
        if not ctx.author.voice or not ctx.author.voice.channel:
            await ctx.send("You are not connected to a voice channel.")
            raise commands.CommandError("Author not connected to a voice channel.")

    @commands.Cog.listener()
    async def on_ready(self):
        print(f'Bot is ready and logged in as {self.bot.user.name} ({self.bot.user.id})')


async def setup(bot):
    await bot.add_cog(Music(bot))
