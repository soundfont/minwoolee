import discord
from discord.ext import commands
import asyncio
import yt_dlp
import traceback
from typing import Optional, Dict
import datetime

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
    'geo_bypass': True, # Added for testing
    # 'cookiefile': '/app/youtube_cookies.txt', # Example if you were to use cookies
}

FFMPEG_OPTS = {
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
    'options': '-vn -filter:a "volume=0.25"'
}

class Music(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.guild_states: Dict[int, Dict] = {}
        print("[Music DEBUG] Cog initialized (Link Debugging).")

    def _get_guild_state(self, guild_id: int) -> Dict:
        if guild_id not in self.guild_states:
            self.guild_states[guild_id] = {
                "voice_client": None, "current_song_info": None,
                "song_queue": asyncio.Queue(), "is_playing": False,
                "loop_current_song": False, "volume": 0.25
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
            uploader_url = song_info.get('uploader_url', song_info.get('channel_url', '#')) # Fallback for uploader URL
            print(f"[Music DEBUG _send_music_embed] Uploader: '{uploader_text}', URL: '{uploader_url}'")
            embed.add_field(name="Uploader", value=f"[{uploader_text}]({uploader_url})", inline=True)
            
            duration_seconds = song_info.get('duration')
            if duration_seconds is not None:
                 try:
                     embed.add_field(name="Duration", value=str(datetime.timedelta(seconds=int(duration_seconds))), inline=True)
                 except ValueError: # If duration is not a valid number
                     embed.add_field(name="Duration", value="N/A (invalid)", inline=True)
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
        if not ctx.author.voice:
            await self._send_music_embed(ctx, "Error", "You are not connected to a voice channel.", discord.Color.red()); return
        channel = ctx.author.voice.channel
        guild_state = self._get_guild_state(ctx.guild.id)
        voice_client: Optional[discord.VoiceClient] = guild_state.get("voice_client")
        if voice_client and voice_client.is_connected():
            if voice_client.channel == channel: await self._send_music_embed(ctx, "Already Connected", f"I am already in: {channel.mention}", discord.Color.blue())
            else: await voice_client.move_to(channel); await self._send_music_embed(ctx, "Moved", f"Moved to: {channel.mention}", discord.Color.green())
        else:
            try: guild_state["voice_client"] = await channel.connect(); await self._send_music_embed(ctx, "Connected", f"Joined: {channel.mention}", discord.Color.green())
            except Exception as e: await self._send_music_embed(ctx, "Connection Error", f"Could not join: {e}", discord.Color.red()); traceback.print_exc()

    @commands.command(name="leave", aliases=["disconnect", "dc", "stop"])
    async def leave_command(self, ctx: commands.Context):
        guild_state = self._get_guild_state(ctx.guild.id)
        voice_client: Optional[discord.VoiceClient] = guild_state.get("voice_client")
        if voice_client and voice_client.is_connected():
            if voice_client.is_playing() or voice_client.is_paused(): voice_client.stop()
            channel_name = voice_client.channel.name
            await voice_client.disconnect(force=False) 
            guild_state.update({"voice_client": None, "current_song_info": None, "is_playing": False, "song_queue": asyncio.Queue()})
            await self._send_music_embed(ctx, "Disconnected", f"Left voice channel: {channel_name}", discord.Color.orange())
        else: await self._send_music_embed(ctx, "Error", "I am not in a voice channel.", discord.Color.red())

    @commands.command(name="play", aliases=["p"])
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def play_command(self, ctx: commands.Context, *, query: str):
        guild_state = self._get_guild_state(ctx.guild.id)
        voice_client: Optional[discord.VoiceClient] = guild_state.get("voice_client")

        if not ctx.author.voice or not ctx.author.voice.channel:
            await self._send_music_embed(ctx, "Error", "You need to be in a voice channel.", discord.Color.red()); return
        
        user_voice_channel = ctx.author.voice.channel
        if not voice_client or not voice_client.is_connected():
            try: guild_state["voice_client"] = await user_voice_channel.connect(); voice_client = guild_state["voice_client"]
            except Exception as e: await self._send_music_embed(ctx, "Connection Error", f"Could not join your VC: {e}", discord.Color.red()); traceback.print_exc(); return
        elif voice_client.channel != user_voice_channel:
            try: await voice_client.move_to(user_voice_channel)
            except Exception as e: await self._send_music_embed(ctx, "Move Error", f"Could not move to your VC: {e}", discord.Color.red()); traceback.print_exc(); return

        if voice_client.is_playing() or voice_client.is_paused():
            voice_client.stop(); await asyncio.sleep(0.5) 

        search_status_msg = await ctx.send(f"🔎 Processing `{query}`...")
        entry_to_play = None; is_direct_url = query.startswith(('http://', 'https://'))

        try:
            current_ydl_opts = YDL_OPTS.copy()
            if is_direct_url and not ('youtube.com/' in query or 'youtu.be/' in query):
                current_ydl_opts['default_search'] = 'auto'
                current_ydl_opts.pop('flatplaylist', None)
                current_ydl_opts['noplaylist'] = False
            
            with yt_dlp.YoutubeDL(current_ydl_opts) as ydl:
                info = await asyncio.to_thread(ydl.extract_info, query, download=False, process=not is_direct_url) # Process if it's a search term

            initial_entry = info['entries'][0] if info and 'entries' in info and info['entries'] else info if info and 'url' in info else None
            if not initial_entry: await search_status_msg.edit(content=f"❌ No results for `{query}`."); return

            extractor = initial_entry.get('extractor_key', initial_entry.get('extractor', '')).lower()
            print(f"[Music DEBUG] Initial extractor for '{query}': {extractor}. Entry title: {initial_entry.get('title')}")

            if is_direct_url and extractor and 'youtube' not in extractor:
                title = initial_entry.get('title', '')
                artist = initial_entry.get('artist', initial_entry.get('uploader', ''))
                if title:
                    yt_query = f"ytsearch1:{title} {artist}".strip()
                    await search_status_msg.edit(content=f"🎧 Searching YouTube for: `{title} {artist if artist else ''}`...")
                    with yt_dlp.YoutubeDL(YDL_OPTS) as ydl_yt: # Standard YDL_OPTS for YT search
                        yt_info = await asyncio.to_thread(ydl_yt.extract_info, yt_query, download=False)
                    entry_to_play = yt_info['entries'][0] if yt_info and 'entries' in yt_info and yt_info['entries'] else yt_info if yt_info and 'url' in yt_info else initial_entry
                else: entry_to_play = initial_entry
            else: entry_to_play = initial_entry
            
            if not entry_to_play: await search_status_msg.edit(content=f"❌ Could not find playable track for `{query}`."); return

            stream_url = entry_to_play.get('url')
            if not stream_url: # Try formats
                for f in entry_to_play.get('formats', []):
                    if f.get('vcodec') == 'none' and f.get('acodec') != 'none' and f.get('url'): stream_url = f.get('url'); break
                if not stream_url: # Last resort for any audio
                    for f in entry_to_play.get('formats', []):
                         if f.get('acodec') != 'none' and f.get('url'): stream_url = f.get('url'); break
            
            if not stream_url:
                await search_status_msg.delete(); await self._send_music_embed(ctx, "Error", "No playable audio stream found.", discord.Color.red()); return

            song_info = {
                'title': entry_to_play.get('title', 'Unknown Title'),
                'uploader': entry_to_play.get('uploader', entry_to_play.get('channel', 'Unknown Uploader')),
                'uploader_url': entry_to_play.get('uploader_url', entry_to_play.get('channel_url')),
                'duration': entry_to_play.get('duration'),
                'webpage_url': entry_to_play.get('webpage_url', entry_to_play.get('original_url', '#')),
                'thumbnail': entry_to_play.get('thumbnail'),
                'source_url': stream_url 
            }
            print(f"[Music DEBUG] song_info for embed: {song_info}") # Print song_info for hyperlink debugging
            guild_state.update({"current_song_info": song_info, "is_playing": True})
            
            ffmpeg_options_with_volume = FFMPEG_OPTS.copy()
            ffmpeg_options_with_volume['options'] = f"-vn -filter:a \"volume={guild_state['volume']}\""

            voice_client.play(discord.FFmpegPCMAudio(stream_url, **ffmpeg_options_with_volume), 
                              after=lambda e: print(f'[Music Player] Error: {e}' if e else '[Music Player] Finished.'))
            
            await search_status_msg.delete()
            await self._send_music_embed(ctx, "🎶 Now Playing", f"[{song_info['title']}]({song_info['webpage_url']})", discord.Color.green(), song_info=song_info)

        except yt_dlp.utils.DownloadError as e:
            await search_status_msg.delete()
            await self._send_music_embed(ctx, "Download Error", f"Could not process song/video: {str(e)[:1000]}", discord.Color.red()); traceback.print_exc()
        except Exception as e:
            await search_status_msg.delete()
            await self._send_music_embed(ctx, "Playback Error", f"An unexpected error occurred: {e}", discord.Color.red()); traceback.print_exc()

    # --- Error Handlers ---
    @join_command.error
    async def join_error(self, ctx, error):
        # ... (same as before) ...
        if isinstance(error, commands.CommandInvokeError) and isinstance(error.original, asyncio.TimeoutError):
            await self._send_music_embed(ctx, "Connection Failed", "Timed out trying to connect to the voice channel.", discord.Color.red())
        else:
            await self._send_music_embed(ctx, "Join Error", f"An error occurred: {error}", discord.Color.red())
            traceback.print_exc()
    
    @play_command.error
    async def play_error(self, ctx, error):
        # ... (same as before) ...
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
        try: print("Opus not loaded. This might cause issues if not auto-detected.")
        except discord.DiscordException: print("ERROR: Could not load opus library. Voice will not work.")
    await bot.add_cog(Music(bot))
    print("Cog 'Music' (Enhanced Link Handling & Debugging) loaded successfully.")
