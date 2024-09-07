import discord
from discord.ext import commands
import lavalink
import random
import re

url_rx = re.compile(r'https?://(?:www\.)?.+')

class Music(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

        # If you don't use an AutoShardedBot, use this instead: lavalink.Client(bot.user.id)
        self.bot.lavalink = lavalink.Client(bot.user.id)
        self.bot.lavalink.add_node(
            host='localhost',     # Replace with your Lavalink host
            port=2333,            # Replace with your Lavalink port
            password='youshallnotpass',  # Replace with your Lavalink password
            region='us_central'   # Replace with your region
        )
        self.bot.add_listener(self.track_hook, 'on_socket_response')

        # Registers the event hooks
        lavalink.add_event_hook(self.track_hook)

    @commands.Cog.listener()
    async def on_ready(self):
        print(f'Bot is ready and logged in as {self.bot.user.name} ({self.bot.user.id})')

    async def track_hook(self, event):
        """Event Hook for lavalink events."""
        if isinstance(event, lavalink.events.TrackEndEvent):
            # Handle track end, like playing the next song in the queue
            guild_id = int(event.guild_id)
            player = self.bot.lavalink.player_manager.get(guild_id)
            if not player.queue:
                return
            
            # Play the next song in the queue
            next_track = player.queue.pop(0)
            await player.play(next_track)

    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        if not member.bot and before.channel is None and after.channel:
            # If a user joins a voice channel and the bot is not connected, connect it
            if not member.guild.voice_client:
                await self.connect_to(after.channel)

    async def connect_to(self, channel: discord.VoiceChannel):
        """Connect to a voice channel."""
        vc = channel.guild.voice_client

        if not vc:
            player = self.bot.lavalink.player_manager.create(channel.guild.id)
            player.store('channel', channel)
            await channel.connect(cls=lavalink.DefaultPlayer)

    @commands.command(name='play', aliases=['p'])
    async def play(self, ctx, *, query: str):
        """Plays a song or adds it to the queue."""
        # Ensure the bot is connected to a voice channel
        player = self.bot.lavalink.player_manager.create(ctx.guild.id)
        query = query.strip('<>')

        # Search for tracks using the given query
        if not url_rx.match(query):
            query = f'ytsearch:{query}'

        results = await player.node.get_tracks(query)

        if not results or not results['tracks']:
            return await ctx.send('No results found.')

        track = results['tracks'][0]

        # Add the track to the queue
        player.add(requester=ctx.author.id, track=track)

        if not player.is_playing:
            await player.play()

        await ctx.send(f'Now playing: {track["info"]["title"]}')

    @commands.command(name='pause')
    async def pause(self, ctx):
        """Pauses the currently playing song."""
        player = self.bot.lavalink.player_manager.get(ctx.guild.id)
        await player.set_pause(True)
        await ctx.send('Playback paused.')

    @commands.command(name='resume')
    async def resume(self, ctx):
        """Resumes the currently paused song."""
        player = self.bot.lavalink.player_manager.get(ctx.guild.id)
        await player.set_pause(False)
        await ctx.send('Playback resumed.')

    @commands.command(name='skip')
    async def skip(self, ctx):
        """Skips the currently playing song."""
        player = self.bot.lavalink.player_manager.get(ctx.guild.id)
        await player.skip()
        await ctx.send('Skipped the current song.')

    @commands.command(name='stop')
    async def stop(self, ctx):
        """Stops playing and clears the queue."""
        player = self.bot.lavalink.player_manager.get(ctx.guild.id)
        await player.stop()
        player.queue.clear()
        await ctx.send('Playback stopped and queue cleared.')

    @commands.command(name='queue')
    async def queue_(self, ctx):
        """Shows the current song queue."""
        player = self.bot.lavalink.player_manager.get(ctx.guild.id)
        if player.queue:
            queue_list = "\n".join([track['info']['title'] for track in player.queue])
            await ctx.send(f"Current Queue:\n{queue_list}")
        else:
            await ctx.send("The queue is currently empty.")

    @commands.command(name='volume')
    async def volume(self, ctx, volume: int):
        """Changes the player's volume."""
        player = self.bot.lavalink.player_manager.get(ctx.guild.id)
        await player.set_volume(volume)
        await ctx.send(f'Volume set to {volume}%')

    @commands.command(name='nowplaying', aliases=['np'])
    async def nowplaying(self, ctx):
        """Displays the currently playing song."""
        player = self.bot.lavalink.player_manager.get(ctx.guild.id)
        if player.is_playing:
            current_track = player.current
            await ctx.send(f'Now playing: {current_track["info"]["title"]}')
        else:
            await ctx.send('No song is currently playing.')

async def setup(bot):
    await bot.add_cog(Music(bot))
