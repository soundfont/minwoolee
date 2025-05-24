import discord
from discord.ext import commands
import asyncio
import yt_dlp # Requires pip install yt-dlp
import traceback
from typing import Optional, Dict
import datetime # Added for datetime.datetime.now

# --- yt-dlp Options ---
YDL_OPTS = {
    'format': 'bestaudio/best',
    'noplaylist': True,
    'quiet': True,
    'default_search': 'ytsearch', 
    'source_address': '0.0.0.0',
    'extract_flat': 'discard_in_playlist', 
    'nocheckcertificate': True,
    'outtmpl': '%(extractor)s-%(id)s-%(title)s.%(ext)s',
    'restrictfilenames': True,
    'no_warnings': True,
    'ignoreerrors': True, 
    'logtostderr': False,
    'youtube_include_dash_manifest': False,
    'skip_download': True, 
    'forcejson': True,
    # 'flatplaylist': True, # Removed for now, as we want to process single items from playlist URLs if given for metadata
}

FFMPEG_OPTS = {
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
    'options': '-vn -filter:a "volume=0.25"' 
}


class Music(commands.Cog):
    """
    A cog for playing music in voice channels.
    Requires FFmpeg to be installed and yt-dlp library.
    """
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.guild_states: Dict[int, Dict] = {} 
        print("[Music DEBUG] Cog initialized.")

    def _get_guild_state(self, guild_id: int) -> Dict:
        """Gets or creates the state for a guild."""
        if guild_id not in self.guild_states:
            self.guild_states[guild_id] = {
                "voice_client": None,
                "current_song_info": None,
                "song_queue": asyncio.Queue(),
                "is_playing": False,
                "loop_current_song": False, 
                "volume": 0.25 
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
            uploader_text = song_info.get('uploader', 'N/A')
            uploader_url = song_info.get('uploader_url', '#')
            if uploader_url == '#' and 'channel_url' in song_info: # Fallback for uploader URL
                uploader_url = song_info.get('channel_url')

            embed.add_field(name="Uploader", value=f"[{uploader_text}]({uploader_url})", inline=True)
            duration_seconds = song_info.get('duration')
            if duration_seconds is not None:
                 embed.add_field(name="Duration", value=str(datetime.timedelta(seconds=int(duration_seconds))), inline=True)
            else:
                 embed.add_field(name="Duration", value="N/A", inline=True)

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
            except discord.ClientException: # Fixed call here
                await self._send_music_embed(ctx, "Connection Failed", "Already connected to a voice channel or failed to connect.", discord.Color.red())
            except Exception as e:
                await self._send_music_embed(ctx, "Connection Error", f"An error occurred: {e}", discord.Color.red())
                traceback.print_exc()


    @commands.command(name="leave", aliases=["disconnect", "dc", "stop"])
    async def leave_command(self, ctx: commands.Context):
        """Commands the bot to leave its current voice channel."""
        guild_state = self._get_guild_state(ctx.guild.id)
        voice_client: Optional[discord.VoiceClient] = guild_state.get("voice_client")

        if voice_client and voice_client.is_connected():
            if voice_client.is_playing() or voice_client.is_paused():
                voice_client.stop()
            
            channel_name = voice_client.channel.name
            await voice_client.disconnect(force=False) 
            guild_state["voice_client"] = None
            guild_state["current_song_info"] = None
            guild_state["is_playing"] = False
            guild_state["song_queue"] = asyncio.Queue() # Reset queue
            await self._send_music_embed(ctx, "Disconnected", f"Left voice channel: {channel_name}", discord.Color.orange())
        else:
            await self._send_music_embed(ctx, "Error", "I am not currently in a voice channel.", discord.Color.red())

    @commands.command(name="play", aliases=["p"])
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def play_command(self, ctx: commands.Context, *, query: str):
        """Plays a song (searches YouTube or uses URL) in your current voice channel."""
        guild_state = self._get_guild_state(ctx.guild.id)
        voice_client: Optional[discord.VoiceClient] = guild_state.get("voice_client")

        if not ctx.author.voice or not ctx.author.voice.channel:
            await self._send_music_embed(ctx, "Error", "You need to be in a voice channel to play music.", discord.Color.red())
            return
        
        user_voice_channel = ctx.author.voice.channel

        if not voice_client or not voice_client.is_connected():
            try: guild_state["voice_client"] = await user_voice_channel.connect(); voice_client = guild_state["voice_client"]
            except Exception as e: await self._send_music_embed(ctx, "Connection Error", f"Could not join your voice channel: {e}", discord.Color.red()); traceback.print_exc(); return
        elif voice_client.channel != user_voice_channel:
            try: await voice_client.move_to(user_voice_channel)
            except Exception as e: await self._send_music_embed(ctx, "Move Error", f"Could not move to your voice channel: {e}", discord.Color.red()); traceback.print_exc(); return

        if voice_client.is_playing() or voice_client.is_paused():
            voice_client.stop(); await asyncio.sleep(0.5) 

        search_status_msg = await ctx.send(f"🔎 Processing `{query}`...")

        entry_to_play = None
        is_direct_url = query.startswith(('http://', 'https://'))

        try:
            # First pass: Get info from the query (URL or search term)
            # For URLs, this will try to resolve them. For terms, it will search.
            # We use slightly different YDL_OPTS for this initial metadata fetch if it's a non-YouTube URL.
            initial_ydl_opts = YDL_OPTS.copy()
            if is_direct_url and not ('youtube.com/' in query or 'youtu.be/' in query):
                initial_ydl_opts['default_search'] = 'auto' # Let yt-dlp try to resolve the URL itself
                initial_ydl_opts.pop('flatplaylist', None) # Allow getting info from single item in playlist URL
                initial_ydl_opts['noplaylist'] = False # Make sure we can get info from a single item if URL points to one in a playlist
                print(f"[Music DEBUG] Using 'auto' search for initial metadata from URL: {query}")

            with yt_dlp.YoutubeDL(initial_ydl_opts) as ydl:
                info = await asyncio.to_thread(ydl.extract_info, query, download=False)

            if info and 'entries' in info and info['entries']: # Playlist result
                initial_entry = info['entries'][0]
            elif info and 'url' in info: # Single result
                initial_entry = info
            else:
                await search_status_msg.edit(content=f"❌ Could not find any results for `{query}`.")
                return

            extractor = initial_entry.get('extractor_key', initial_entry.get('extractor', '')).lower()
            print(f"[Music DEBUG] Initial extractor for '{query}': {extractor}")

            # If the initial query was a URL AND it's not from YouTube,
            # extract title/artist and perform a specific YouTube search.
            if is_direct_url and extractor and 'youtube' not in extractor:
                title = initial_entry.get('title', 'Unknown Title')
                artist = initial_entry.get('artist', initial_entry.get('uploader', ''))
                
                if title != 'Unknown Title':
                    youtube_search_query = f"ytsearch1:{title} {artist}".strip()
                    print(f"[Music DEBUG] Non-YouTube URL. Extracted: '{title}' by '{artist}'. New YouTube search: '{youtube_search_query}'")
                    await search_status_msg.edit(content=f"🎧 Searching YouTube for: `{title} {artist if artist else ''}`...")
                    
                    with yt_dlp.YoutubeDL(YDL_OPTS) as ydl_yt: # Use standard YDL_OPTS for YouTube search
                        yt_info = await asyncio.to_thread(ydl_yt.extract_info, youtube_search_query, download=False)
                    
                    if yt_info and 'entries' in yt_info and yt_info['entries']:
                        entry_to_play = yt_info['entries'][0]
                        print(f"[Music DEBUG] Found YouTube match: {entry_to_play.get('title')}")
                    elif yt_info and 'url' in yt_info: # Single YT result
                        entry_to_play = yt_info
                        print(f"[Music DEBUG] Found YouTube match: {entry_to_play.get('title')}")
                    else:
                        print(f"[Music DEBUG] No YouTube match for '{title}'. Will try original if possible.")
                        # If re-search fails, we might fall back to initial_entry if it has a streamable URL
                        # but this is unlikely for non-YT sources directly.
                        entry_to_play = initial_entry # Fallback, might fail later if not streamable
                else:
                    print(f"[Music DEBUG] Could not extract title from non-YouTube URL. Using original entry.")
                    entry_to_play = initial_entry # Fallback
            else: # It was a direct YouTube URL or a search term
                entry_to_play = initial_entry
            
            # --- At this point, entry_to_play should be the chosen video/song info ---
            if not entry_to_play: # Should have been caught earlier, but defensive check
                await search_status_msg.edit(content=f"❌ Could not find a playable track for `{query}`.")
                return

            stream_url = entry_to_play.get('url')
            if not stream_url: # Try to find a suitable format if 'url' is not top-level
                for f_format in entry_to_play.get('formats', []):
                    if f_format.get('vcodec') == 'none' and f_format.get('acodec') != 'none' and f_format.get('url'):
                        stream_url = f_format.get('url')
                        break
            if not stream_url: # Final check for any audio stream
                 for f_format in entry_to_play.get('formats', []):
                    if f_format.get('acodec') != 'none' and f_format.get('url'):
                        stream_url = f_format.get('url')
                        break

            if not stream_url:
                await search_status_msg.delete()
                await self._send_music_embed(ctx, "Error", "Could not find a playable audio stream for the selected track.", discord.Color.red())
                return

            song_info = {
                'title': entry_to_play.get('title', 'Unknown Title'),
                'uploader': entry_to_play.get('uploader', entry_to_play.get('channel', 'Unknown Uploader')),
                'uploader_url': entry_to_play.get('uploader_url', entry_to_play.get('channel_url')),
                'duration': entry_to_play.get('duration'),
                'webpage_url': entry_to_play.get('webpage_url', entry_to_play.get('original_url', '#')),
                'thumbnail': entry_to_play.get('thumbnail'),
                'source_url': stream_url 
            }
            guild_state["current_song_info"] = song_info
            guild_state["is_playing"] = True
            
            current_ffmpeg_opts = FFMPEG_OPTS.copy()
            current_ffmpeg_opts['options'] = f"-vn -filter:a \"volume={guild_state['volume']}\""

            voice_client.play(discord.FFmpegPCMAudio(stream_url, **current_ffmpeg_opts), 
                              after=lambda e: print(f'[Music Player] Error: {e}' if e else '[Music Player] Finished playing.'))
            
            await search_status_msg.delete() # Delete "Searching..." message
            await self._send_music_embed(ctx, "🎶 Now Playing", 
                                         f"[{song_info['title']}]({song_info['webpage_url']})",
                                         discord.Color.green(), song_info=song_info)

        except yt_dlp.utils.DownloadError as e:
            await search_status_msg.delete()
            await self._send_music_embed(ctx, "Download Error", f"Could not process the song/video: {str(e)[:1000]}", discord.Color.red())
            traceback.print_exc()
        except Exception as e:
            await search_status_msg.delete()
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
    if not discord.opus.is_loaded():
        try: print("Opus not loaded. Attempting to load...")
        except discord.DiscordException: print("ERROR: Could not load opus library. Voice will not work.")
    await bot.add_cog(Music(bot))
    print("Cog 'Music' (Enhanced Link Handling) loaded successfully.")

