import discord
from discord.ext import commands
import wavelink
import random

class Music(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.bot.loop.create_task(self.start_nodes())
        self.queue = {}
        self.loop = {}

    async def start_nodes(self):
        """Connects to Lavalink nodes."""
        await self.bot.wait_until_ready()
        # Configure Lavalink node(s)
        await wavelink.NodePool.create_node(
            bot=self.bot,
            host='localhost',  # Replace with your Lavalink server host
            port=2333,         # Replace with your Lavalink server port
            password='youshallnotpass',  # Replace with your Lavalink server password
            region='us_central'
        )

    async def ensure_voice(self, ctx):
        """Ensures the bot joins the voice channel if it isn't already."""
        if not ctx.author.voice:
            await ctx.send("You are not connected to a voice channel.")
            raise commands.CommandError("Author not connected to a voice channel.")
        elif not ctx.voice_client:
            vc: wavelink.Player = await ctx.author.voice.channel.connect(cls=wavelink.Player)
        else:
            vc: wavelink.Player = ctx.voice_client

        return vc

    @commands.command(name="play", aliases=["p"])
    async def play(self, ctx, *, search: str):
        """Plays a song or adds it to the queue."""
        vc: wavelink.Player = await self.ensure_voice(ctx)

        # Search for the song
        tracks = await wavelink.YouTubeTrack.search(query=search, return_first=True)

        if not tracks:
            return await ctx.send("Could not find any songs with that search term.")

        # Queue the track or play immediately if nothing is playing
        if not vc.is_playing():
            await vc.play(tracks)
            await ctx.send(f"Now playing: {tracks.title}")
        else:
            self.queue.setdefault(ctx.guild.id, []).append(tracks)
            await ctx.send(f"Added to queue: {tracks.title}")

    @commands.command(name="pause")
    async def pause(self, ctx):
        """Pauses the currently playing song."""
        vc: wavelink.Player = ctx.voice_client

        if vc.is_playing():
            await vc.pause()
            await ctx.send("Playback paused.")

    @commands.command(name="resume")
    async def resume(self, ctx):
        """Resumes the currently paused song."""
        vc: wavelink.Player = ctx.voice_client

        if vc.is_paused():
            await vc.resume()
            await ctx.send("Playback resumed.")

    @commands.command(name="skip")
    async def skip(self, ctx):
        """Skips the currently playing song."""
        vc: wavelink.Player = ctx.voice_client

        if vc.is_playing():
            await vc.stop()
            await ctx.send("Song skipped.")

    @commands.command(name="stop")
    async def stop(self, ctx):
        """Stops playing and clears the queue."""
        vc: wavelink.Player = ctx.voice_client

        if vc.is_playing():
            await vc.stop()
            self.queue[ctx.guild.id] = []
            await ctx.send("Playback stopped and queue cleared.")

    @commands.command(name="queue")
    async def queue_(self, ctx):
        """Shows the current song queue."""
        guild_id = ctx.guild.id
        if guild_id in self.queue and self.queue[guild_id]:
            queue_list = "\n".join([track.title for track in self.queue[guild_id]])
            await ctx.send(f"Current Queue:\n{queue_list}")
        else:
            await ctx.send("The queue is currently empty.")

    @commands.command(name="loop")
    async def loop_(self, ctx):
        """Toggles looping of the currently playing song."""
        guild_id = ctx.guild.id
        self.loop[guild_id] = not self.loop.get(guild_id, False)
        await ctx.send(f"Looping is now {'enabled' if self.loop[guild_id] else 'disabled'}.")

    @commands.command(name="shuffle")
    async def shuffle(self, ctx):
        """Shuffles the queue."""
        guild_id = ctx.guild.id
        if guild_id in self.queue and len(self.queue[guild_id]) > 1:
            random.shuffle(self.queue[guild_id])
            await ctx.send("Queue shuffled.")
        else:
            await ctx.send("Not enough songs in the queue to shuffle.")

    @commands.command(name="volume")
    async def volume(self, ctx, volume: int):
        """Changes the player's volume."""
        vc: wavelink.Player = ctx.voice_client

        if vc.is_playing():
            await vc.set_volume(volume)
            await ctx.send(f"Volume set to {volume}%")

    @commands.command(name="nowplaying", aliases=["np"])
    async def nowplaying(self, ctx):
        """Displays the currently playing song."""
        vc: wavelink.Player = ctx.voice_client

        if vc.is_playing():
            await ctx.send(f"Now playing: {vc.track.title}")
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
