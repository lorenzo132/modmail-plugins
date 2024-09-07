import discord
from discord.ext import commands
import lavalink

class Music(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.loop = False
        self.lavalink = None

    @commands.Cog.listener()
    async def on_ready(self):
        # Connect to Lavalink server when the bot is ready
        await self.bot.wait_until_ready()
        # Initialize Lavalink client
        self.lavalink = lavalink.Client(self.bot.user.id)
        # Add Lavalink node with IP, port, and password
        self.lavalink.add_node('localhost', 2333, 'youshallnotpass', 'na', 60)
        self.bot.add_listener(self.lavalink.voice_update_handler, 'on_socket_response')
    
    @commands.command(name='join', help='Tells the bot to join the voice channel')
    async def join(self, ctx):
        if not ctx.author.voice:
            return await ctx.send("You are not connected to a voice channel.")
        channel = ctx.author.voice.channel

        if ctx.voice_client is not None:
            return await ctx.voice_client.move_to(channel)

        await channel.connect()

    @commands.command(name='play', help='Play a song')
    async def play(self, ctx, *, search: str):
        if not ctx.voice_client:
            await ctx.invoke(self.join)

        node = self.lavalink.nodes[0]  # Assuming you only have one node
        query = f"ytsearch:{search}"
        results = await node.get_tracks(query)

        if not results:
            return await ctx.send("No results found.")

        track = results[0]
        await ctx.voice_client.play(track)
        await ctx.send(f'Now playing: {track.title}')

    @commands.command(name='pause', help='Pauses the song')
    async def pause(self, ctx):
        if ctx.voice_client and ctx.voice_client.is_playing():
            await ctx.voice_client.pause()
            await ctx.send("Paused the song!")
        else:
            await ctx.send("No audio is playing.")

    @commands.command(name='resume', help='Resumes the song')
    async def resume(self, ctx):
        if ctx.voice_client and ctx.voice_client.is_paused():
            await ctx.voice_client.resume()
            await ctx.send("Resumed the song!")
        else:
            await ctx.send("The audio is not paused.")

    @commands.command(name='stop', help='Stops the song')
    async def stop(self, ctx):
        if ctx.voice_client:
            await ctx.voice_client.disconnect()

    @commands.command(name='volume', help='Changes the player\'s volume')
    async def volume(self, ctx, volume: int):
        if ctx.voice_client is None:
            return await ctx.send("Not connected to a voice channel.")

        ctx.voice_client.volume = volume / 100
        await ctx.send(f"Changed volume to {volume}%")

    @commands.command(name='seek', help='Seek to a specific time in the song')
    async def seek(self, ctx, seconds: int):
        if not ctx.voice_client or not ctx.voice_client.is_playing():
            return await ctx.send("No song is currently playing.")
        
        ctx.voice_client.position = seconds * 1000
        await ctx.send(f"Seeked to {seconds} seconds in the song.")

    @commands.command(name='loop', help='Loops the current song')
    async def loop(self, ctx):
        self.loop = not self.loop
        await ctx.send(f"Looping is now {'enabled' if self.loop else 'disabled'}.")

    @commands.command(name='search', help='Search for a song and select a result to play')
    async def search(self, ctx, *, query):
        node = self.lavalink.nodes[0]  # Assuming you only have one node
        results = await node.get_tracks(f"ytsearch:5 {query}")

        result_text = "\n".join(f"{i+1}. {track.title}" for i, track in enumerate(results))
        await ctx.send(f"Search results:\n{result_text}")

        def check(msg):
            return msg.author == ctx.author and msg.channel == ctx.channel and msg.content.isdigit()

        try:
            choice = await self.bot.wait_for('message', check=check, timeout=30.0)
            index = int(choice.content) - 1
            if 0 <= index < len(results):
                await self.play(ctx, search=results[index].uri)
            else:
                await ctx.send("Invalid selection.")
        except asyncio.TimeoutError:
            await ctx.send("You took too long to respond!")

    @commands.command(name='download', help='Downloads the current playing song and sends it as an mp3')
    async def download(self, ctx):
        await ctx.send("Downloading is not supported with Lavalink.")

    @commands.command(name='nowplaying', help='Shows information about the currently playing track')
    async def nowplaying(self, ctx):
        if ctx.voice_client and ctx.voice_client.is_playing():
            track = ctx.voice_client.source
            await ctx.send(f"Now playing: {track.title}\nURL: {track.uri}")
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
