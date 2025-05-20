import discord
from discord.ext import commands
import datetime
import psycopg2
import psycopg2.extras # For dictionary cursor
import os
import traceback
from typing import Optional, Dict, Any, List, Tuple
from urllib.parse import urlparse, quote_plus # For URL encoding
import aiohttp # For making API requests
import asyncio # For adding reactions with a small delay
import json
import io # For image manipulation in memory

# Attempt to import Pillow and set a flag
try:
    from PIL import Image, ImageDraw, UnidentifiedImageError
    PILLOW_AVAILABLE = True
except ImportError:
    PILLOW_AVAILABLE = False
    print("WARNING [LastFM]: Pillow library not found. Album collage feature will be disabled.")

# --- Last.fm API Configuration ---
LASTFM_API_BASE_URL = "http://ws.audioscrobbler.com/2.0/"

class LastFM(commands.Cog, name="Last.fm"):
    """
    Integrates Last.fm to show listening habits, top artists, and album collages.
    Last.fm accounts are linked globally per Discord user.
    Requires a LASTFM_API_KEY environment variable.
    Album collage feature requires the Pillow library.
    """
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.api_key = os.getenv("LASTFM_API_KEY")
        print(f"[LastFM DEBUG __init__] API Key Loaded: {'Yes' if self.api_key else 'NO - COMMANDS WILL FAIL'}")
        
        self.db_url = os.getenv("DATABASE_URL")
        self.db_params = None
        if self.db_url:
            self.db_params = self._parse_db_url(self.db_url)
            if self.db_params:
                self._init_db() 
            else:
                print("ERROR [LastFM Init]: DATABASE_URL parsing failed. DB features disabled.")
        else:
            print("ERROR [LastFM Init]: DATABASE_URL environment variable not set. Last.fm cog cannot store usernames.")
        
        self.http_session = aiohttp.ClientSession()
        self.user_placeholder_album_art = "https://placehold.co/300x300?text=(No+album+art)" 
        print(f"[LastFM DEBUG __init__] Cog initialized. Pillow available: {PILLOW_AVAILABLE}. Placeholder: {self.user_placeholder_album_art}")

    async def cog_unload(self):
        await self.http_session.close()
        print("[LastFM DEBUG cog_unload] HTTP session closed.")

    def _parse_db_url(self, url: str) -> Optional[dict]:
        try:
            parsed = urlparse(url)
            return {"dbname": parsed.path[1:], "user": parsed.username, "password": parsed.password, 
                    "host": parsed.hostname, "port": parsed.port or 5432,
                    "sslmode": "require" if "sslmode=require" in url else None}
        except Exception as e: print(f"ERROR [LastFM _parse_db_url]: {e}"); return None

    def _get_db_connection(self):
        if not self.db_params: raise ConnectionError("DB params not configured.")
        try: return psycopg2.connect(**self.db_params)
        except psycopg2.Error as e: print(f"ERROR [LastFM _get_db_connection]: {e}"); raise ConnectionError(f"Failed to connect: {e}")

    def _init_db(self):
        if not self.db_params: return
        try:
            with self._get_db_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute("""
                        CREATE TABLE IF NOT EXISTS lastfm_global_users (
                            user_id BIGINT PRIMARY KEY,
                            lastfm_username TEXT NOT NULL,
                            linked_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
                        )""")
                    conn.commit()
            print("[LastFM DEBUG _init_db] 'lastfm_global_users' table checked/created.")
        except (psycopg2.Error, ConnectionError) as e:
            print(f"ERROR [LastFM _init_db]: DB table init failed: {e}")

    async def _call_lastfm_api(self, params: Dict[str, str]) -> Optional[Dict[str, Any]]:
        if not self.api_key: print("[LastFM DEBUG _call_lastfm_api] API key not set."); return None
        params.update({'api_key': self.api_key, 'format': 'json'})
        # print(f"[LastFM DEBUG _call_lastfm_api] Calling API: {LASTFM_API_BASE_URL} with params: {params}") # Can be very verbose
        try:
            async with self.http_session.get(LASTFM_API_BASE_URL, params=params) as response:
                # print(f"[LastFM DEBUG _call_lastfm_api] Response status: {response.status}")
                if response.status == 200:
                    data = await response.json()
                    if 'error' in data: print(f"ERROR [LastFM API Call]: {data.get('message')} (Code: {data.get('error')}) User: {params.get('user')}"); return data
                    return data
                else: print(f"ERROR [LastFM API Call]: HTTP {response.status}. Response: {await response.text()}"); return None
        except Exception as e: print(f"ERROR [LastFM API Call]: Unexpected: {e}"); traceback.print_exc(); return None
            
    async def _send_fm_embed(self, ctx: commands.Context, title: str, description: Optional[str] = None, color: discord.Color = discord.Color.blue(), image_url_for_thumbnail: Optional[str] = None, author_for_embed: Optional[discord.User | discord.Member] = None, fields: Optional[List[Tuple[str,str]]] = None, file_to_send: Optional[discord.File] = None) -> Optional[discord.Message]:
        utils_cog = self.bot.get_cog('Utils')
        embed: discord.Embed
        if utils_cog and hasattr(utils_cog, 'create_embed'):
            embed = utils_cog.create_embed(ctx, title=title, description=description, color=color)
            if author_for_embed: embed.set_author(name=str(author_for_embed.display_name), icon_url=author_for_embed.display_avatar.url if author_for_embed.avatar else None)
        else: 
            embed = discord.Embed(title=title, description=description or "", color=color, timestamp=datetime.datetime.now(datetime.timezone.utc))
            if author_for_embed: embed.set_author(name=str(author_for_embed.display_name), icon_url=author_for_embed.display_avatar.url if author_for_embed.avatar else None)
            if ctx.author: embed.set_footer(text=f"Requested by {ctx.author.name}", icon_url=ctx.author.display_avatar.url if ctx.author.avatar else None)
        if image_url_for_thumbnail and not file_to_send: embed.set_thumbnail(url=image_url_for_thumbnail)
        if file_to_send and embed: embed.set_image(url=f"attachment://{file_to_send.filename}")
        if fields:
            for name, value in fields: embed.add_field(name=name, value=value, inline=False)
        try: return await ctx.send(embed=embed, file=file_to_send if file_to_send else discord.utils.MISSING)
        except Exception as e: print(f"Error sending Last.fm embed: {e}"); return None

    async def _get_lastfm_username_from_db(self, user_id: int) -> Optional[str]:
        if not self.db_params: return None
        try:
            with self._get_db_connection() as conn:
                with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cursor:
                    cursor.execute("SELECT lastfm_username FROM lastfm_global_users WHERE user_id = %s", (user_id,))
                    row = cursor.fetchone()
            return row['lastfm_username'] if row else None
        except (psycopg2.Error, ConnectionError) as e: print(f"ERROR [LastFM _get_lastfm_username_from_db]: {e}"); return None

    def _parse_lastfm_api_period(self, period_input: str) -> Tuple[Optional[str], Optional[str]]:
        period_input_lower = period_input.lower()
        if period_input_lower == "overall": return "overall", "Overall"
        if period_input_lower in ["1d", "day", "24h"]: return "7day", "Last 7 Days (defaulted from 1 Day)"
        if period_input_lower in ["7d", "week", "7day"]: return "7day", "Last 7 Days"
        if period_input_lower in ["30d", "1m", "month", "1month"]: return "1month", "Last Month"
        if period_input_lower in ["3m", "3months", "3month"]: return "3month", "Last 3 Months"
        if period_input_lower in ["6m", "6months", "6month"]: return "6month", "Last 6 Months"
        if period_input_lower in ["1y", "year", "12m", "12months", "12month"]: return "12month", "Last 12 Months"
        return None, None

    async def _create_collage_image(self, image_urls: List[str], grid_dims: Tuple[int, int], cell_size: int = 300) -> Optional[io.BytesIO]:
        if not PILLOW_AVAILABLE:
            print("[LastFM Collage] Pillow library not available. Cannot create collage.")
            return None
        rows, cols = grid_dims
        collage_width = cols * cell_size; collage_height = rows * cell_size
        collage = Image.new('RGB', (collage_width, collage_height), (47, 49, 54))
        images_processed = 0
        for i, url in enumerate(image_urls):
            if images_processed >= rows * cols: break
            img_to_paste = None
            try:
                if not url or not url.startswith("http"): url = self.user_placeholder_album_art
                async with self.http_session.get(url) as response:
                    if response.status == 200: img_to_paste = Image.open(io.BytesIO(await response.read()))
                    else: 
                        async with self.http_session.get(self.user_placeholder_album_art) as ph_response:
                            if ph_response.status == 200: img_to_paste = Image.open(io.BytesIO(await ph_response.read()))
            except Exception: 
                try:
                    async with self.http_session.get(self.user_placeholder_album_art) as ph_response:
                        if ph_response.status == 200: img_to_paste = Image.open(io.BytesIO(await ph_response.read()))
                except Exception: pass
            if not img_to_paste: continue
            if img_to_paste.mode in ['RGBA', 'P']: img_to_paste = img_to_paste.convert('RGB')
            img_width, img_height = img_to_paste.size
            if img_width == 0 or img_height == 0: continue
            if img_width / img_height > 1: new_height = cell_size; new_width = int(img_width * (new_height / img_height))
            else: new_width = cell_size; new_height = int(img_height * (new_width / img_width))
            img_to_paste = img_to_paste.resize((new_width, new_height), Image.Resampling.LANCZOS)
            left = (new_width - cell_size) / 2; top = (new_height - cell_size) / 2
            right = (new_width + cell_size) / 2; bottom = (new_height + cell_size) / 2
            img_to_paste = img_to_paste.crop((left, top, right, bottom))
            row_idx, col_idx = divmod(images_processed, cols)
            collage.paste(img_to_paste, (col_idx * cell_size, row_idx * cell_size))
            images_processed += 1
        if images_processed == 0: return None
        img_byte_arr = io.BytesIO(); collage.save(img_byte_arr, format='PNG'); img_byte_arr.seek(0)
        return img_byte_arr

    # --- Main Command Group ---
    @commands.group(name="fm", aliases=["lfm"], invoke_without_command=True)
    @commands.cooldown(1, 3, commands.BucketType.user)
    async def fm_group(self, ctx: commands.Context, *, member: Optional[discord.Member] = None):
        """Shows your or another user's currently playing/last scrobbled track on Last.fm.
        Use subcommands like .fm set, .fm topartists, .fm collage.
        Usage: .fm [@user]
        """
        if ctx.invoked_subcommand is None: # Default action: show now playing
            print(f"[LastFM DEBUG fm_group - NowPlaying] Invoked by {ctx.author.name} for {member.name if member else ctx.author.name}.")
            if not self.api_key or not self.db_params:
                await self._send_fm_embed(ctx, "Last.fm Error", "Integration not fully configured.", discord.Color.red()); return

            target_user = member or ctx.author
            lastfm_username = await self._get_lastfm_username_from_db(target_user.id)

            if not lastfm_username:
                msg = "Set your Last.fm username with `.fm set <username>`." if target_user == ctx.author else f"{target_user.display_name} hasn't set their username."
                await self._send_fm_embed(ctx, "Last.fm Account Not Set", msg, discord.Color.orange()); return
            
            params = {"method": "user.getrecenttracks", "user": lastfm_username, "limit": 1, "extended": "1"}
            data = await self._call_lastfm_api(params)

            if not data or 'recenttracks' not in data or not data['recenttracks'].get('track'):
                err_msg = data.get('message', "Could not fetch recent tracks.") if data and 'error' in data else "Could not fetch recent tracks."
                await self._send_fm_embed(ctx, "Last.fm Error", err_msg, discord.Color.red()); return

            track_info_list = data['recenttracks']['track']
            if not isinstance(track_info_list, list) or not track_info_list:
                await self._send_fm_embed(ctx, "Last.fm Error", "No track information found.", discord.Color.red()); return
                
            track_info = track_info_list[0] 
            print(f"[LastFM DEBUG fm_group - NowPlaying] Full track_info: {json.dumps(track_info, indent=2)}") 
            
            track_name = track_info.get('name', "Unknown Track")
            if not track_name or not str(track_name).strip(): track_name = "Unknown Track"
            
            artist_name = "Unknown Artist" 
            artist_data_raw = track_info.get('artist')
            # print(f"[LastFM DEBUG fm_group] Raw artist data for '{track_name}': {artist_data_raw} (type: {type(artist_data_raw)})")
            if isinstance(artist_data_raw, dict):
                artist_name_candidate = artist_data_raw.get('name') 
                if isinstance(artist_name_candidate, str) and artist_name_candidate.strip(): artist_name = artist_name_candidate
            elif isinstance(artist_data_raw, str) and artist_data_raw.strip(): artist_name = artist_data_raw
            elif isinstance(artist_data_raw, list) and artist_data_raw: 
                first_artist_entry = artist_data_raw[0]
                if isinstance(first_artist_entry, dict): artist_name_candidate = first_artist_entry.get('name'); artist_name = artist_name_candidate if isinstance(artist_name_candidate, str) and artist_name_candidate.strip() else artist_name
                elif isinstance(first_artist_entry, str) and first_artist_entry.strip(): artist_name = first_artist_entry
            # print(f"[LastFM DEBUG fm_group] Final artist_name for '{track_name}': '{artist_name}'")
            
            album_name = "Unknown Album" 
            album_data_raw = track_info.get('album')
            if isinstance(album_data_raw, dict): album_name_candidate = album_data_raw.get('#text'); album_name = album_name_candidate if isinstance(album_name_candidate, str) and album_name_candidate.strip() else album_name
            elif isinstance(album_data_raw, str) and album_data_raw.strip(): album_name = album_data_raw
            
            image_url = None 
            for img in track_info.get('image', []): 
                if isinstance(img, dict) and img.get('size') == 'extralarge' and img.get('#text'): image_url = img['#text']; break
                elif isinstance(img, dict) and img.get('size') == 'large' and img.get('#text'): image_url = img['#text'] 
            if not image_url and track_info.get('image'): 
                largest_image = None; size_order = ['mega', 'extralarge', 'large', 'medium', 'small', ''] 
                for size_key in size_order:
                    for img_data in track_info.get('image', []): 
                        if isinstance(img_data, dict) and img_data.get('size') == size_key and img_data.get('#text'): largest_image = img_data['#text']; break
                    if largest_image: break; image_url = largest_image
            final_thumbnail_url = image_url if image_url else self.user_placeholder_album_art
            if not image_url: print(f"[LastFM DEBUG fm_group] No album art. Using placeholder: {final_thumbnail_url}")

            is_now_playing = track_info.get('@attr', {}).get('nowplaying') == 'true'
            embed_title = f"🎧 Last.fm for {lastfm_username}"
            description = f"**Track:** [{track_name}]({track_info.get('url', '#')})\n**Artist:** {artist_name}\n"
            if album_name and album_name != "Unknown Album": description += f"**Album:** {album_name}\n"
            if is_now_playing: description += f"\n*Scrobbled: just now*"
            else:
                scrobble_date_uts = track_info.get('date', {}).get('uts')
                if scrobble_date_uts:
                    try: scrobble_datetime = datetime.datetime.fromtimestamp(int(scrobble_date_uts), tz=datetime.timezone.utc); description += f"\n*Scrobbled: {discord.utils.format_dt(scrobble_datetime, style='R')}*"
                    except ValueError: description += f"\n*Scrobbled: Invalid date*"
                else: description += "\n*Scrobble time not available*"
            
            sent_message = await self._send_fm_embed(ctx, title=embed_title, description=description, color=discord.Color.red(), image_url_for_thumbnail=final_thumbnail_url, author_for_embed=target_user)
            if sent_message:
                try: await sent_message.add_reaction("⬆️"); await asyncio.sleep(0.1); await sent_message.add_reaction("⬇️")
                except Exception as e: print(f"[LastFM DEBUG] Error adding reactions: {e}")
        # If a subcommand was invoked, the group itself doesn't send the default help.
        elif ctx.invoked_subcommand is None : # Should already be handled by invoke_without_command=True default logic
             await ctx.send_help(ctx.command)


    @fm_group.command(name="set")
    async def fm_set(self, ctx: commands.Context, lastfm_username: str):
        if not self.db_params or not self.api_key: await self._send_fm_embed(ctx, "Config Error", "Integration not configured.", discord.Color.red()); return
        validation_params = {"method": "user.getinfo", "user": lastfm_username}
        validation_data = await self._call_lastfm_api(validation_params)
        if not validation_data or 'user' not in validation_data:
            err_msg = validation_data.get('message', f"User '{lastfm_username}' not found.") if validation_data and 'error' in validation_data else f"Could not validate user '{lastfm_username}'."
            await self._send_fm_embed(ctx, "Last.fm User Invalid", err_msg, discord.Color.red()); return
        try:
            with self._get_db_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute("INSERT INTO lastfm_global_users (user_id, lastfm_username, linked_at) VALUES (%s, %s, %s) ON CONFLICT (user_id) DO UPDATE SET lastfm_username = EXCLUDED.lastfm_username, linked_at = EXCLUDED.linked_at", (ctx.author.id, lastfm_username, datetime.datetime.now(datetime.timezone.utc)))
                    conn.commit()
            await self._send_fm_embed(ctx, "Last.fm Account Set", f"Username globally set to **{lastfm_username}**.", discord.Color.green())
        except (psycopg2.Error, ConnectionError) as e: await self._send_fm_embed(ctx, "DB Error", "Failed to save username.", discord.Color.red()); print(f"ERROR [LastFM fm_set DB]: {e}")

    @fm_group.command(name="remove", aliases=["unset"])
    async def fm_remove(self, ctx: commands.Context):
        if not self.db_params: await self._send_fm_embed(ctx, "DB Error", "Database not configured.", discord.Color.red()); return
        try:
            with self._get_db_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute("DELETE FROM lastfm_global_users WHERE user_id = %s", (ctx.author.id,))
                    deleted_rows = cursor.rowcount
                    conn.commit()
            if deleted_rows > 0: await self._send_fm_embed(ctx, "Last.fm Account Removed", "Global username removed.", discord.Color.orange())
            else: await self._send_fm_embed(ctx, "Last.fm Account Not Set", "No username set.", discord.Color.blue())
        except (psycopg2.Error, ConnectionError) as e: await self._send_fm_embed(ctx, "DB Error", "Failed to remove username.", discord.Color.red()); print(f"ERROR [LastFM fm_remove DB]: {e}")

    @fm_group.command(name="topartists", aliases=["ta", "tar"])
    @commands.cooldown(1, 10, commands.BucketType.user)
    async def fm_top_artists(self, ctx: commands.Context, member: Optional[discord.Member] = None, period_input: str = "overall", limit: int = 5):
        if not self.api_key or not self.db_params: await self._send_fm_embed(ctx, "Last.fm Error", "Integration not configured.", discord.Color.red()); return
        target_user = member or ctx.author
        lastfm_username = await self._get_lastfm_username_from_db(target_user.id)
        if not lastfm_username:
            msg = "Set your Last.fm username with `.fm set <username>`." if target_user == ctx.author else f"{target_user.display_name} hasn't set their username."
            await self._send_fm_embed(ctx, "Last.fm Account Not Set", msg, discord.Color.orange()); return
        api_period, display_period_name = self._parse_lastfm_api_period(period_input)
        if not api_period: await self._send_fm_embed(ctx, "Invalid Period", "Valid: overall, 1d, 7d, 1m, 3m, 6m, 1y.", discord.Color.red()); return
        if not (1 <= limit <= 15): await self._send_fm_embed(ctx, "Invalid Limit", "Limit: 1-15.", discord.Color.red()); return
        
        params = {"method": "user.gettopartists", "user": lastfm_username, "period": api_period, "limit": limit}
        data = await self._call_lastfm_api(params)
        if not data or 'topartists' not in data or not data['topartists'].get('artist'):
            err_msg = data.get('message', f"Could not fetch top artists.") if data and 'error' in data else f"Could not fetch top artists."
            await self._send_fm_embed(ctx, "Last.fm Error", err_msg, discord.Color.red()); return
        
        artists_data = data['topartists']['artist']
        if not isinstance(artists_data, list): artists_data = [artists_data] if artists_data else []
        
        embed_title = f"Top Artists for {lastfm_username} ({display_period_name})"
        desc_lines = [f"{i+1}. [{a_info.get('name','?')}](https://www.last.fm/music/{quote_plus(a_info.get('name',''))}) - **{a_info.get('playcount','?')}** plays" for i, a_info in enumerate(artists_data) if isinstance(a_info, dict)] if artists_data else ["No top artists found."]
        await self._send_fm_embed(ctx, embed_title, "\n".join(desc_lines), discord.Color.blue(), author_for_embed=target_user)

    @fm_group.command(name="collage", aliases=["col"])
    @commands.cooldown(1, 30, commands.BucketType.user)
    async def fm_collage(self, ctx: commands.Context, member: Optional[discord.Member] = None, period_input: str = "overall", grid_size_str: str = "3x3"):
        if not PILLOW_AVAILABLE:
            await self._send_fm_embed(self.bot, ctx, "Feature Disabled", "The Pillow image library is not installed on the bot. Album collage feature is unavailable.", discord.Color.red())
            return
        if not self.api_key or not self.db_params:
            await self._send_fm_embed(ctx, "Last.fm Error", "Integration not configured.", discord.Color.red()); return

        target_user = member or ctx.author
        lastfm_username = await self._get_lastfm_username_from_db(target_user.id)
        if not lastfm_username:
            msg = "Set your Last.fm username with `.fm set <username>`." if target_user == ctx.author else f"{target_user.display_name} hasn't set username."
            await self._send_fm_embed(ctx, "Last.fm Account Not Set", msg, discord.Color.orange()); return

        api_period, display_period_name = self._parse_lastfm_api_period(period_input)
        if not api_period: await self._send_fm_embed(ctx, "Invalid Period", "Valid: overall, 1d, 7d, 1m, 3m, 6m, 1y.", discord.Color.red()); return
        
        try:
            cols, rows = map(int, grid_size_str.lower().split('x'))
            if not (1 <= cols <= 5 and 1 <= rows <= 5): raise ValueError("Grid size out of bounds 1-5.")
        except ValueError: await self._send_fm_embed(ctx, "Invalid Grid Size", "Grid: NxN (e.g., 3x3). Max 5x5.", discord.Color.red()); return
        
        num_albums = rows * cols
        await ctx.send(f"⏳ Generating {cols}x{rows} collage for {lastfm_username} ({display_period_name})...", delete_after=15)

        params = {"method": "user.gettopalbums", "user": lastfm_username, "period": api_period, "limit": num_albums}
        data = await self._call_lastfm_api(params)

        if not data or 'topalbums' not in data or not data['topalbums'].get('album'):
            err = data.get('message', "Could not fetch top albums.") if data and 'error' in data else "Could not fetch top albums."
            await self._send_fm_embed(ctx, "Last.fm Error", err, discord.Color.red()); return
        
        albums_data = data['topalbums']['album']
        if not isinstance(albums_data, list): albums_data = [albums_data] if albums_data else []
        if not albums_data: await self._send_fm_embed(ctx, "No Albums", f"No top albums found for '{display_period_name}'.", discord.Color.orange()); return

        image_urls = []
        for album_info in albums_data[:num_albums]: # Ensure we only process up to num_albums
            if not isinstance(album_info, dict): continue
            art_url = None
            for img_dict in reversed(album_info.get('image', [])): # largest first
                if isinstance(img_dict, dict) and img_dict.get('#text'): art_url = img_dict['#text']; break
            image_urls.append(art_url if art_url and art_url.strip() else self.user_placeholder_album_art)
        
        collage_bytes_io = await self._create_collage_image(image_urls, (rows, cols))
        if collage_bytes_io:
            collage_file = discord.File(fp=collage_bytes_io, filename=f"fm_collage_{lastfm_username}_{api_period}_{rows}x{cols}.png")
            title = f"Top Albums Collage for {lastfm_username} ({display_period_name} | {rows}x{cols})"
            await self._send_fm_embed(ctx, title=title, file_to_send=collage_file, color=discord.Color.purple(), author_for_embed=target_user)
        else: await self._send_fm_embed(ctx, "Collage Error", "Failed to generate collage.", discord.Color.red())


    # --- Error Handlers ---
    @fm_group.error
    async def fm_group_error(self, ctx, error):
        print(f"[LastFM DEBUG fm_group_error] Error handler triggered: {type(error).__name__} - {error}")
        if isinstance(error, commands.CommandOnCooldown): await self._send_fm_embed(ctx, "Cooldown", f"Command on cooldown. Try again in {error.retry_after:.2f}s.", discord.Color.orange())
        elif isinstance(error, commands.MemberNotFound): await self._send_fm_embed(ctx, "User Not Found", f"Could not find user: {error.argument}", discord.Color.red())
        elif isinstance(error, commands.CommandInvokeError) and isinstance(error.original, KeyError): 
            await self._send_fm_embed(ctx, "Last.fm Data Error", "Could not parse track information from Last.fm. The data might be incomplete for this track.", discord.Color.orange())
            print(f"KeyError in fm_group: {error.original}"); traceback.print_exc()
        elif isinstance(error, commands.CommandInvokeError) and isinstance(error.original, NameError) and "name 'json' is not defined" in str(error.original): 
            await self._send_fm_embed(ctx, "Bot Error", "A required module (json) is missing. Please report this.", discord.Color.red())
            print(f"NameError for 'json' in fm_group: {error.original}"); traceback.print_exc()
        else: await self._send_fm_embed(ctx, "Last.fm Error", f"Unexpected error: {error}", discord.Color.red()); print(f"Error in fm_group: {error}"); traceback.print_exc()

    @fm_set.error
    async def fm_set_error(self, ctx, error):
        print(f"[LastFM DEBUG fm_set_error] Error handler triggered: {type(error).__name__} - {error}")
        if isinstance(error, commands.MissingRequiredArgument) and error.param.name == "lastfm_username":
            await self._send_fm_embed(ctx, "Missing Username", "Provide username. Usage: `.fm set YourUsername`", discord.Color.red())
        else: await self._send_fm_embed(ctx, "Set Last.fm Error", f"Unexpected error: {error}", discord.Color.red()); print(f"Error in fm_set: {error}"); traceback.print_exc()

    @fm_top_artists.error
    async def fm_top_artists_error(self, ctx, error):
        print(f"[LastFM DEBUG fm_top_artists_error] Error handler triggered: {type(error).__name__} - {error}")
        if isinstance(error, commands.CommandOnCooldown): await self._send_fm_embed(ctx, "Cooldown", f"Command on cooldown. Try again in {error.retry_after:.2f}s.", discord.Color.orange())
        elif isinstance(error, commands.MemberNotFound): await self._send_fm_embed(ctx, "User Not Found", f"Could not find user: {error.argument}", discord.Color.red())
        elif isinstance(error, commands.BadArgument): await self._send_fm_embed(ctx, "Invalid Argument", "Please provide a valid number for the limit, or a valid period.", discord.Color.red())
        elif isinstance(error, commands.CommandInvokeError) and isinstance(error.original, ConnectionError):
            await self._send_fm_embed(ctx, "Database Error", "Could not connect to the database.", discord.Color.red())
        else: await self._send_fm_embed(ctx, "Top Artists Error", f"An unexpected error occurred: {error}", discord.Color.red()); print(f"Error in fm_top_artists: {error}"); traceback.print_exc()
        
    @fm_collage.error
    async def fm_collage_error(self, ctx, error):
        print(f"[LastFM DEBUG fm_collage_error] Error handler triggered: {type(error).__name__} - {error}")
        if isinstance(error, commands.CommandOnCooldown): await self._send_fm_embed(ctx, "Cooldown", f"Collage command on cooldown. Try again in {error.retry_after:.2f}s.", discord.Color.orange())
        elif isinstance(error, commands.MemberNotFound): await self._send_fm_embed(ctx, "User Not Found", f"Could not find user: {error.argument}", discord.Color.red())
        else: await self._send_fm_embed(ctx, "Collage Error", f"An unexpected error occurred: {error}", discord.Color.red()); print(f"Error in fm_collage: {error}"); traceback.print_exc()


async def setup(bot: commands.Bot):
    # Ensure Pillow is imported if PILLOW_AVAILABLE is True, or handle its absence for collage
    if PILLOW_AVAILABLE:
        print("Pillow library found, collage command will be available.")
    else:
        print("Pillow library NOT found, collage command will be disabled/notify user.")
    await bot.add_cog(LastFM(bot))
    print("Cog 'LastFM' (Consolidated & All Features) loaded successfully.")

