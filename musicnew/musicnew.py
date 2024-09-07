import discord
from discord.ext import commands
import wavelink
import random
import os
from dotenv import load_dotenv

# Load the environment variables from .env file
load_dotenv()

# Fetch the Lavalink configuration from environment variables
LAVALINK_HOST = os.getenv('LAVALINK_HOST')
LAVALINK_PORT = int(os.getenv('LAVALINK_PORT'))
LAVALINK_PASSWORD = os.getenv('LAVALINK_PASSWORD')

class Music(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.music_queue = []
        self.loop = False  # To track if looping is enabled

    @commands.Cog.listener()
    async def on_ready(self):
        """Connect to Lavalink when the bot is ready."""
        await wavelink.NodePool.create_node(bot=self.bot,
                                            host=LAVALINK_HOST,
                                            port=LAVALINK_PORT,
                                            password=LAVALINK_PASSWORD,
                                            region="us_central")

    async def connect_to_voice(self, ctx):
        """Connects to a voice channel."""
        if not ctx.author.voice:
            await ctx.send("Please join a voice channel first.")
            return None

        player = ctx.voice_client
        if not player:
            player = await ctx.author.voice.channel.connect(cls=wavelink.Player)
        else:
            if ctx.author.voice.channel.id != player.channel.id:
                await player.move_to(ctx.author.voice.channel)

        return player

    @commands.command(name="join", help="Joins the voice channel")
    async def join(self, ctx):
        player = await self.connect_to_voice(ctx)
        if player:
            await ctx.send(f"Connected to {ctx.author.voice.channel}")

    @commands.command(name="play", help="Plays a selected song from YouTube")
    async def play(self, ctx, *, search: str):
        player = await self.connect_to_voice(ctx)
        if not player:
            return

        query = f'ytsearch:{search}'
        tracks = await wavelink.YouTubeTrack.search(query)

        if not tracks:
            await ctx.send("No tracks found.")
            return

        track = tracks[0]

        self.music_queue.append(track)
        await ctx.send(f"Added {track.title} to the queue.")

        if not player.is_playing():
            await self.start_playback(ctx, player)

    async def start_playback(self, ctx, player):
        if self.music_queue:
            track = self.music_queue[0]

            await player.play(track)
            await ctx.send(f"Now playing: {track.title}")

            if not self.loop:
                self.music_queue.pop(0)
        else:
            await ctx.send("The queue is empty.")

    @commands.command(name="pause", help="Pauses the current song")
    async def pause(self, ctx):
        player = ctx.voice_client
        if player and player.is_playing():
            await player.pause()
            await ctx.send("Paused the current track.")
        else:
            await ctx.send("No music is playing to pause.")

    @commands.command(name="resume", help="Resumes the current song")
    async def resume(self, ctx):
        player = ctx.voice_client
        if player and player.is_paused():
            await player.resume()
            await ctx.send("Resumed the track.")
        else:
            await ctx.send("The music is not paused or nothing is playing.")

    @commands.command(name="skip", help="Skips the current song")
    async def skip(self, ctx):
        player = ctx.voice_client
        if player and player.is_playing():
            await player.stop()
            await self.start_playback(ctx, player)
            await ctx.send("Skipped the current song.")
        else:
            await ctx.send("No music is playing to skip.")

    @commands.command(name="queue", help="Displays the current queue")
    async def queue(self, ctx):
        if not self.music_queue:
            await ctx.send("The queue is currently empty.")
            return

        queue_list = "\n".join([f"{i+1}. {track.title}" for i, track in enumerate(self.music_queue)])
        await ctx.send(f"Current queue:\n{queue_list}")

    @commands.command(name="nowplaying", help="Shows the current playing song")
    async def nowplaying(self, ctx):
        player = ctx.voice_client
        if player and player.is_playing():
            await ctx.send(f"Now playing: {player.track.title}")
        else:
            await ctx.send("Nothing is playing right now.")

    @commands.command(name="volume", help="Change the volume of the music")
    async def volume(self, ctx, volume: int):
        player = ctx.voice_client
        if not player:
            await ctx.send("Bot is not connected to a voice channel.")
            return

        if volume < 0 or volume > 100:
            await ctx.send("Volume must be between 0 and 100.")
        else:
            await player.set_volume(volume)
            await ctx.send(f"Volume set to {volume}%")

    @commands.command(name="search", help="Search for a song and select the one to play")
    async def search(self, ctx, *, search: str):
        tracks = await wavelink.YouTubeTrack.search(query=search)
        if not tracks:
            await ctx.send("No tracks found.")
            return

        # Display search results
        embed = discord.Embed(title="Search Results", description="\n".join([f"{i + 1}. {track.title}" for i, track in enumerate(tracks[:5])]), color=discord.Color.blue())
        await ctx.send(embed=embed)

        def check(msg):
            return msg.author == ctx.author and msg.channel == ctx.channel and msg.content.isdigit()

        try:
            response = await self.bot.wait_for("message", check=check, timeout=30.0)
            choice = int(response.content)
            if 1 <= choice <= 5:
                chosen_track = tracks[choice - 1]
                self.music_queue.append(chosen_track)
                await ctx.send(f"Added {chosen_track.title} to the queue.")
            else:
                await ctx.send("Invalid choice. Please select a number between 1 and 5.")
        except asyncio.TimeoutError:
            await ctx.send("You took too long to respond.")

    @commands.command(name="shuffle", help="Shuffles the queue")
    async def shuffle(self, ctx):
        random.shuffle(self.music_queue)
        await ctx.send("Shuffled the queue.")

    @commands.command(name="seek", help="Seeks to a specific position in the current track (in seconds)")
    async def seek(self, ctx, position: int):
        player = ctx.voice_client
        if player and player.is_playing():
            await player.seek(position * 1000)  # Seek in milliseconds
            await ctx.send(f"Seeked to {position} seconds.")
        else:
            await ctx.send("No music is playing to seek.")

    @commands.command(name="loop", help="Loops the current track or queue")
    async def loop(self, ctx):
        self.loop = not self.loop
        if self.loop:
            await ctx.send("Looping enabled.")
        else:
            await ctx.send("Looping disabled.")

    @commands.command(name="remove", help="Removes a song from the queue by its position")
    async def remove(self, ctx, position: int):
        """Removes a song from the queue by its position in the list."""
        if 1 <= position <= len(self.music_queue):
            removed_track = self.music_queue.pop(position - 1)
            await ctx.send(f"Removed {removed_track.title} from the queue.")
        else:
            await ctx.send(f"Invalid position. Please provide a number between 1 and {len(self.music_queue)}.")

    @commands.command(name="disconnect", help="Disconnects the bot from the voice channel")
    async def disconnect(self, ctx):
        player = ctx.voice_client
        if player:
            await player.disconnect()
            await ctx.send("Disconnected from the voice channel.")
        else:
            await ctx.send("The bot is not connected to a voice channel.")

async def setup(bot):
    await bot.add_cog(Music(bot))
