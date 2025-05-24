import discord
from discord.ext import commands
import asyncio
import yt_dlp # Requires pip install yt-dlp
import traceback
from typing import Optional, Dict

# --- yt-dlp Options ---
# These options are commonly used for discord music bots.
# 'format': 'bestaudio/best' selects the best audio-only format.
# 'noplaylist': True prevents downloading an entire playlist if a playlist URL is given with a video.
# 'quiet': True suppresses console output from yt-dlp.
# 'default_search': 'auto' will search on YouTube if a plain query is given.
# 'source_address': '0.0.0.0' can sometimes help with IPv6/binding issues.
YDL_OPTS = {
    'format': 'bestaudio/best',
    'noplaylist': True,
    'quiet': True,
    'default_search': 'ytsearch', # Search on YouTube by default
    'source_address': '0.0.0.0', # Bind to all IP addresses (for IPv6 resolving issues)
    'extract_flat': 'discard_in_playlist', # Don't extract playlist members if a single video from a playlist is requested
    'nocheckcertificate': True, # May be needed for some networks/SSL issues
    'outtmpl': '%(extractor)s-%(id)s-%(title)s.%(ext)s', # Output template, not strictly needed for streaming
    'restrictfilenames': True,
    'no_warnings': True,
    'ignoreerrors': True, # Ignore errors for individual videos in a playlist (if noplaylist wasn't enough)
    'logtostderr': False,
    'youtube_include_dash_manifest': False, # For DASH manifest issues
    'skip_download': True, # We only want the URL to stream from
    'forcejson': True, # Get metadata as JSON
    'flatplaylist': True, # Only get playlist metadata, not individual videos
}

FFMPEG_OPTS = {
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
    'options': '-vn -filter:a "volume=0.25"' # No video, and set volume (0.25 = 25%)
}


class Music(commands.Cog):
    """
    A cog for playing music in voice channels.
    Requires FFmpeg to be installed and yt-dlp library.
    """
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # {guild_id: {'voice_client': discord.VoiceClient, 'current_song_info': dict, 'queue': asyncio.Queue}}
        self.guild_states: Dict[int, Dict] = {} 
        print("[Music DEBUG] Cog initialized.")

    def _get_guild_state(self, guild_id: int) -> Dict:
        """Gets or creates the state for a guild."""
        if guild_id not in self.guild_states:
            self.guild_states[guild_id] = {
                "voice_client": None,
                "current_song_info": None,
                "song_queue": asyncio.Queue(), # For future queue implementation
                "is_playing": False,
                "loop_current_song": False, # For future loop feature
                "volume": 0.25 # Default volume
            }
        return self.guild_states[guild_id]

    async def _send_music_embed(self, ctx: commands.Context, title: str, description: Optional[str] = None, color: discord.Color = discord.Color.purple(), song_info: Optional[Dict] = None) -> Optional[discord.Message]:
        utils_cog = self.bot.get_cog('Utils')
        embed: discord.Embed

        if utils_cog and hasattr(utils_cog, 'create_embed'):
            embed = utils_cog.create_embed(ctx, title=title, description=description, color=color)
        else: 
            embed = discord.Embed(title=title, description=description or "", color=color, timestamp=datetime.datetime.now(datetime.timezone.utc))
            if ctx.author: embed.set_footer(text=f"Requested by {ctx.author.name}", icon_url=ctx.author.display_avatar.url if ctx.author.avatar else None)
        
        if song_info:
            embed.add_field(name="Uploader", value=f"[{song_info.get('uploader', 'N/A')}]({song_info.get('uploader_url', '#')})", inline=True)
            embed.add_field(name="Duration", value=str(datetime.timedelta(seconds=song_info.get('duration', 0))), inline=True)
            if song_info.get('thumbnail'):
                embed.set_thumbnail(url=song_info.get('thumbnail'))
        
        try:
            return await ctx.send(embed=embed)
        except Exception as e:
            print(f"Error sending music embed: {e}")
            return None

    @commands.command(name="join", aliases=["connect", "j"])
    async def join_command(self, ctx: commands.Context):
        """Commands the bot to join your current voice channel."""
        if not ctx.author.voice:
            await self._send_music_embed(ctx, "Error", "You are not connected to a voice channel.", discord.Color.red())
            return
        
        channel = ctx.author.voice.channel
        guild_state = self._get_guild_state(ctx.guild.id)
        voice_client: Optional[discord.VoiceClient] = guild_state.get("voice_client")

        if voice_client and voice_client.is_connected():
            if voice_client.channel == channel:
                await self._send_music_embed(ctx, "Already Connected", f"I am already in your voice channel: {channel.mention}", discord.Color.blue())
            else:
                await voice_client.move_to(channel)
                await self._send_music_embed(ctx, "Moved", f"Moved to your voice channel: {channel.mention}", discord.Color.green())
        else:
            try:
                guild_state["voice_client"] = await channel.connect()
                await self._send_music_embed(ctx, "Connected", f"Joined voice channel: {channel.mention}", discord.Color.green())
            except asyncio.TimeoutError:
                await self._send_music_embed(ctx, "Connection Failed", "Could not connect to the voice channel in time.", discord.Color.red())
            except discord.ClientException:
                await self._send_embed_response(ctx, "Connection Failed", "Already connected to a voice channel or failed to connect.", discord.Color.red())
            except Exception as e:
                await self._send_music_embed(ctx, "Connection Error", f"An error occurred: {e}", discord.Color.red())
                traceback.print_exc()


    @commands.command(name="leave", aliases=["disconnect", "dc", "stop"]) # Stop will just leave for now
    async def leave_command(self, ctx: commands.Context):
        """Commands the bot to leave its current voice channel."""
        guild_state = self._get_guild_state(ctx.guild.id)
        voice_client: Optional[discord.VoiceClient] = guild_state.get("voice_client")

        if voice_client and voice_client.is_connected():
            # Stop any currently playing audio
            if voice_client.is_playing() or voice_client.is_paused():
                voice_client.stop()
            
            channel_name = voice_client.channel.name
            await voice_client.disconnect(force=False) # force=False to wait for playback to finish if needed (not relevant here since we stop)
            guild_state["voice_client"] = None
            guild_state["current_song_info"] = None
            guild_state["is_playing"] = False
            # Clear queue if it existed: guild_state["song_queue"] = asyncio.Queue()
            await self._send_music_embed(ctx, "Disconnected", f"Left voice channel: {channel_name}", discord.Color.orange())
        else:
            await self._send_music_embed(ctx, "Error", "I am not currently in a voice channel.", discord.Color.red())

    @commands.command(name="play", aliases=["p"])
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def play_command(self, ctx: commands.Context, *, query: str):
        """Plays a song from YouTube (search or URL) in your current voice channel.
        Usage: .play <song name or YouTube URL>
        """
        guild_state = self._get_guild_state(ctx.guild.id)
        voice_client: Optional[discord.VoiceClient] = guild_state.get("voice_client")

        if not ctx.author.voice or not ctx.author.voice.channel:
            await self._send_music_embed(ctx, "Error", "You need to be in a voice channel to play music.", discord.Color.red())
            return
        
        user_voice_channel = ctx.author.voice.channel

        # If bot is not connected, or connected to a different channel, join/move to user's channel
        if not voice_client or not voice_client.is_connected():
            print(f"[Music DEBUG] Bot not connected, joining {user_voice_channel.name}")
            try:
                guild_state["voice_client"] = await user_voice_channel.connect()
                voice_client = guild_state["voice_client"] # Update local reference
            except Exception as e:
                await self._send_music_embed(ctx, "Connection Error", f"Could not join your voice channel: {e}", discord.Color.red())
                traceback.print_exc(); return
        elif voice_client.channel != user_voice_channel:
            print(f"[Music DEBUG] Bot in different channel, moving to {user_voice_channel.name}")
            try:
                await voice_client.move_to(user_voice_channel)
            except Exception as e:
                await self._send_music_embed(ctx, "Move Error", f"Could not move to your voice channel: {e}", discord.Color.red())
                traceback.print_exc(); return

        # If already playing, for now, we'll stop the current song and play the new one.
        # Later, this will add to a queue.
        if voice_client.is_playing() or voice_client.is_paused():
            print("[Music DEBUG] Song already playing/paused. Stopping current to play new one.")
            voice_client.stop()
            # Wait a brief moment for stop to take effect
            await asyncio.sleep(0.5) 


        await ctx.send(f"Searching for ` {query} ` <a:loading:12345> ...", delete_after=10) # Placeholder emoji

        try:
            with yt_dlp.YoutubeDL(YDL_OPTS) as ydl:
                # Search and extract info (not downloading)
                # 'ytsearch:' prefix makes it search on YouTube. If it's a URL, it will use it directly.
                search_query = query if query.startswith(('http://', 'https://')) else f"ytsearch1:{query}"
                info = await asyncio.to_thread(ydl.extract_info, search_query, download=False)

            if not info or 'entries' not in info or not info['entries']:
                # Handle cases where ytsearch might return a single video directly not in 'entries'
                if info and 'url' in info: # Direct URL or ytsearch1 found one result not in entries
                     entry = info
                else:
                    await self._send_music_embed(ctx, "Not Found", f"Could not find any results for `{query}`.", discord.Color.red())
                    return
            else: # It's a search result with entries
                entry = info['entries'][0] # Take the first result

            stream_url = entry.get('url') # This is the direct audio stream URL
            if not stream_url: # Fallback if 'url' is not present, try formats
                for f in entry.get('formats', []):
                    if f.get('vcodec') == 'none' and f.get('url'): # Audio only
                        stream_url = f.get('url')
                        break
            if not stream_url:
                await self._send_music_embed(ctx, "Error", "Could not find a playable audio stream for the selected track.", discord.Color.red())
                return

            song_info = {
                'title': entry.get('title', 'Unknown Title'),
                'uploader': entry.get('uploader', 'Unknown Uploader'),
                'uploader_url': entry.get('uploader_url'),
                'duration': entry.get('duration', 0),
                'webpage_url': entry.get('webpage_url', entry.get('original_url', '#')),
                'thumbnail': entry.get('thumbnail'),
                'source_url': stream_url # Keep the stream url
            }
            guild_state["current_song_info"] = song_info
            guild_state["is_playing"] = True
            
            # Adjust FFMPEG_OPTS to include the current volume
            current_ffmpeg_opts = FFMPEG_OPTS.copy()
            current_ffmpeg_opts['options'] = f"-vn -filter:a \"volume={guild_state['volume']}\""


            # Play the audio stream
            # discord.FFmpegPCMAudio needs the direct stream URL.
            # For some sites, yt-dlp provides this in entry['url']
            voice_client.play(discord.FFmpegPCMAudio(stream_url, **current_ffmpeg_opts), 
                              after=lambda e: print(f'Player error: {e}' if e else 'Finished playing.'))
            # The 'after' callback is for when the song finishes or an error occurs.
            # We'll use this for queueing later.

            await self._send_music_embed(ctx, "🎶 Now Playing", 
                                         f"[{song_info['title']}]({song_info['webpage_url']})",
                                         discord.Color.green(), song_info=song_info)

        except yt_dlp.utils.DownloadError as e:
            await self._send_music_embed(ctx, "Download Error", f"Could not process the song/video: {e}", discord.Color.red())
            traceback.print_exc()
        except Exception as e:
            await self._send_music_embed(ctx, "Playback Error", f"An unexpected error occurred: {e}", discord.Color.red())
            traceback.print_exc()


    # --- Error Handlers ---
    @join_command.error
    async def join_error(self, ctx, error):
        if isinstance(error, commands.CommandInvokeError) and isinstance(error.original, asyncio.TimeoutError):
            await self._send_music_embed(ctx, "Connection Failed", "Timed out trying to connect to the voice channel.", discord.Color.red())
        else:
            await self._send_music_embed(ctx, "Join Error", f"An error occurred: {error}", discord.Color.red())
            traceback.print_exc()
    
    @play_command.error
    async def play_error(self, ctx, error):
        if isinstance(error, commands.MissingRequiredArgument):
            if error.param.name == "query":
                await self._send_music_embed(ctx, "Missing Song", "You need to tell me what song to play!\nUsage: `.play <song name or URL>`", discord.Color.red())
        elif isinstance(error, commands.CommandOnCooldown):
            await self._send_music_embed(ctx, "Cooldown", f"This command is on cooldown. Try again in {error.retry_after:.2f}s.", discord.Color.orange())
        else:
            await self._send_music_embed(ctx, "Play Error", f"An unexpected error occurred: {error}", discord.Color.red())
            traceback.print_exc()


async def setup(bot: commands.Bot):
    # Ensure FFmpeg is installed and in PATH
    # Ensure yt-dlp and PyNaCl are installed
    # Ensure voice_states intent is enabled for the bot
    if not discord.opus.is_loaded():
        try:
            # Attempt to load opus if not already loaded (common on some systems)
            # You might need to specify the path to your opus library if it's not in system PATH
            # e.g., discord.opus.load_opus('/path/to/libopus.so.0')
            # This is often handled automatically if opus is installed correctly.
            print("Opus not loaded. Attempting to load...") # This might not work on all platforms without explicit path
            # discord.opus.load_opus('opus') # Example, might fail. Usually it's auto-detected.
        except discord.DiscordException:
            print("ERROR: Could not load opus library. Voice will not work.")
            # Bot will likely fail to connect to voice if opus isn't loaded.

    await bot.add_cog(Music(bot))
    print("Cog 'Music' (Basic) loaded successfully.")

