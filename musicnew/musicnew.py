import discord
from discord.ext import commands
from discord import FFmpegPCMAudio
import youtube_dl
import asyncio
import os

youtube_dl.utils.bug_reports_message = lambda: ''

# Configure YouTube downloader options
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
    'source_address': '0.0.0.0'  # Bind to ipv4
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
        loop = loop or asyncio.get_event_loop()
        data = await loop.run_in_executor(None, lambda: ytdl.extract_info(url, download=not stream))

        if 'entries' in data:
            # Take first item from a playlist
            data = data['entries'][0]

        filename = data['url'] if stream else ytdl.prepare_filename(data)
        return cls(FFmpegPCMAudio(filename, **ffmpeg_options), data=data)


class Music(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.current_player = None
        self.loop = False

    @commands.command(name='join', help='Tells the bot to join the voice channel')
    async def join(self, ctx):
        if not ctx.message.author.voice:
            await ctx.send("You are not connected to a voice channel.")
            return
        else:
            channel = ctx.message.author.voice.channel

        if ctx.voice_client is not None:
            return await ctx.voice_client.move_to(channel)

        await channel.connect()

    @commands.command(name='play', help='To play song')
    async def play(self, ctx, *, search: str):
        async with ctx.typing():
            player = await YTDLSource.from_url(search, loop=self.bot.loop, stream=True)
            ctx.voice_client.play(player, after=lambda e: self.play_next(ctx) if self.loop else None)
            self.current_player = player

        await ctx.send(f'Now playing: {player.title}')

    def play_next(self, ctx):
        if self.loop and self.current_player:
            ctx.voice_client.play(self.current_player, after=lambda e: self.play_next(ctx) if self.loop else None)

    @commands.command(name='pause', help='Pauses the song')
    async def pause(self, ctx):
        if ctx.voice_client.is_playing():
            ctx.voice_client.pause()
            await ctx.send("Paused the song!")
        else:
            await ctx.send("No audio is playing.")

    @commands.command(name='resume', help='Resumes the song')
    async def resume(self, ctx):
        if ctx.voice_client.is_paused():
            ctx.voice_client.resume()
            await ctx.send("Resumed the song!")
        else:
            await ctx.send("The audio is not paused.")

    @commands.command(name='stop', help='Stops the song')
    async def stop(self, ctx):
        await ctx.voice_client.disconnect()

    @commands.command(name='volume', help='Changes the player\'s volume')
    async def volume(self, ctx, volume: int):
        if ctx.voice_client is None:
            return await ctx.send("Not connected to a voice channel.")

        ctx.voice_client.source.volume = volume / 100
        await ctx.send(f"Changed volume to {volume}%")

    @commands.command(name='seek', help='Seek to a specific time in the song')
    async def seek(self, ctx, seconds: int):
        if not ctx.voice_client or not ctx.voice_client.is_playing():
            return await ctx.send("No song is currently playing.")
        
        ctx.voice_client.stop()  # Stop the current playback

        player = FFmpegPCMAudio(self.current_player.url, before_options=f'-ss {seconds}', **ffmpeg_options)
        ctx.voice_client.play(player, after=lambda e: self.play_next(ctx) if self.loop else None)

        await ctx.send(f"Seeked to {seconds} seconds in the song.")

    @commands.command(name='loop', help='Loops the current song')
    async def loop(self, ctx):
        self.loop = not self.loop
        await ctx.send(f"Looping is now {'enabled' if self.loop else 'disabled'}.")

    @commands.command(name='search', help='Search for a song and select a result to play')
    async def search(self, ctx, *, query):
        async with ctx.typing():
            info = ytdl.extract_info(f"ytsearch5:{query}", download=False)['entries']
            result_text = "\n".join(f"{i+1}. {entry['title']}" for i, entry in enumerate(info))
            await ctx.send(f"Search results:\n{result_text}")

        def check(msg):
            return msg.author == ctx.author and msg.channel == ctx.channel and msg.content.isdigit()

        try:
            choice = await self.bot.wait_for('message', check=check, timeout=30.0)
            index = int(choice.content) - 1
            if 0 <= index < len(info):
                await self.play(ctx, search=info[index]['webpage_url'])
            else:
                await ctx.send("Invalid selection.")
        except asyncio.TimeoutError:
            await ctx.send("You took too long to respond!")

    @commands.command(name='download', help='Downloads the current playing song and sends it as an mp3')
    async def download(self, ctx):
        if self.current_player is None:
            return await ctx.send("No song is currently playing.")

        async with ctx.typing():
            filename = ytdl.prepare_filename(ytdl.extract_info(self.current_player.url, download=True))
            await ctx.send(file=discord.File(filename))
            os.remove(filename)  # Remove the file after sending

    @commands.command(name='nowplaying', help='Shows information about the currently playing track')
    async def nowplaying(self, ctx):
        if self.current_player:
            await ctx.send(f"Now playing: {self.current_player.title}\nURL: {self.current_player.url}")
        else:
            await ctx.send("No song is currently playing.")

    @join.before_invoke
    @play.before_invoke
    async def ensure_voice(self, ctx):
        if ctx.voice_client is None:
            if ctx.author.voice:
                await ctx.author.voice.channel.connect()
            else:
                await ctx.send("You are not connected to a voice channel.")
                raise commands.CommandError("Author not connected to a voice channel.")
        elif ctx.voice_client.is_playing():
            ctx.voice_client.stop()


async def setup(bot):
    await bot.add_cog(Music(bot))
