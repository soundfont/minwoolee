import discord
from discord.ext import commands
import datetime
import psycopg2
import psycopg2.extras # For dictionary cursor
import os
import traceback
from typing import Optional, Dict, Any, List
from urllib.parse import urlparse, quote_plus # For URL encoding
import aiohttp # For making API requests
import asyncio # For adding reactions with a small delay

# --- Last.fm API Configuration ---
LASTFM_API_BASE_URL = "http://ws.audioscrobbler.com/2.0/"

class LastFM(commands.Cog):
    """
    Integrates Last.fm to show what users are listening to, their top artists, etc.
    Last.fm accounts are linked globally per Discord user.
    Requires a LASTFM_API_KEY environment variable.
    """
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.api_key = os.getenv("LASTFM_API_KEY")
        if not self.api_key:
            print("ERROR [LastFM Init]: LASTFM_API_KEY environment variable not set. Last.fm cog will be non-functional.")
        
        self.db_url = os.getenv("DATABASE_URL")
        self.db_params = None
        if self.db_url:
            self.db_params = self._parse_db_url(self.db_url)
            self._init_db() 
        else:
            print("ERROR [LastFM Init]: DATABASE_URL environment variable not set. Last.fm cog cannot store usernames.")
        
        self.http_session = aiohttp.ClientSession()
        print("[LastFM DEBUG] Cog initialized (Global Linking, Top Artists, Updated Timeframes, Robust Artist/Album Parse).")

    async def cog_unload(self):
        """Clean up the aiohttp session when the cog is unloaded."""
        await self.http_session.close()
        print("[LastFM DEBUG] HTTP session closed.")

    def _parse_db_url(self, url: str) -> Optional[dict]:
        try:
            parsed = urlparse(url)
            return {
                "dbname": parsed.path[1:], "user": parsed.username,
                "password": parsed.password, "host": parsed.hostname,
                "port": parsed.port or 5432,
                "sslmode": "require" if "sslmode=require" in url else None
            }
        except Exception as e:
            print(f"ERROR [LastFM _parse_db_url]: Failed to parse DATABASE_URL: {e}")
            return None

    def _get_db_connection(self):
        if not self.db_params: raise ConnectionError("DB params not configured for Last.fm cog.")
        try:
            return psycopg2.connect(**self.db_params)
        except psycopg2.Error as e:
            print(f"ERROR [LastFM _get_db_connection]: DB connection failed: {e}")
            raise ConnectionError(f"Failed to connect to DB: {e}")

    def _init_db(self):
        """Ensures the lastfm_global_users table exists in the database."""
        if not self.db_params: return
        conn = None
        try:
            conn = self._get_db_connection()
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS lastfm_global_users (
                    user_id BIGINT PRIMARY KEY,
                    lastfm_username TEXT NOT NULL,
                    linked_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.commit()
            cursor.close()
            print("[LastFM DEBUG] 'lastfm_global_users' table checked/created.")
        except (psycopg2.Error, ConnectionError) as e:
            print(f"ERROR [LastFM _init_db]: DB table init failed: {e}")
        finally:
            if conn: conn.close()

    async def _call_lastfm_api(self, params: Dict[str, str]) -> Optional[Dict[str, Any]]:
        if not self.api_key:
            print("[LastFM DEBUG] API key not set, cannot call API.")
            return None
        params['api_key'] = self.api_key
        params['format'] = 'json'
        request_url = LASTFM_API_BASE_URL
        try:
            async with self.http_session.get(request_url, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    if 'error' in data:
                        print(f"ERROR [LastFM API Call]: {data.get('message', 'Unknown API error')} (Code: {data.get('error')}) for params {params.get('user', 'N/A')}")
                        return data 
                    return data
                else:
                    print(f"ERROR [LastFM API Call]: HTTP Status {response.status} for params {params}. Response: {await response.text()}")
                    return None
        except aiohttp.ClientConnectorError as e:
            print(f"ERROR [LastFM API Call]: Connection error: {e}")
            return None
        except Exception as e:
            print(f"ERROR [LastFM API Call]: Unexpected error: {e}"); traceback.print_exc()
            return None
            
    def _create_fallback_embed(self, title: str, description: str, color: discord.Color, ctx: Optional[commands.Context] = None) -> discord.Embed:
        embed = discord.Embed(title=title, description=description, color=color, timestamp=datetime.datetime.now(datetime.timezone.utc))
        return embed

    async def _send_embed_response(self, ctx: commands.Context, title: str, description: str, color: discord.Color, image_url_for_thumbnail: Optional[str] = None, author_for_embed: Optional[discord.User | discord.Member] = None, fields: Optional[List[Tuple[str,str]]] = None) -> Optional[discord.Message]:
        utils_cog = self.bot.get_cog('Utils')
        embed: discord.Embed

        if utils_cog and hasattr(utils_cog, 'create_embed'):
            embed = utils_cog.create_embed(ctx, title=title, description=description, color=color)
            if author_for_embed: 
                display_avatar_url = author_for_embed.display_avatar.url if author_for_embed.avatar else None
                embed.set_author(name=str(author_for_embed.display_name), icon_url=display_avatar_url)
        else: 
            embed = self._create_fallback_embed(title=title, description=description, color=color, ctx=ctx)
            if author_for_embed:
                display_avatar_url = author_for_embed.display_avatar.url if author_for_embed.avatar else None
                embed.set_author(name=str(author_for_embed.display_name), icon_url=display_avatar_url)
            if ctx.author: 
                 embed.set_footer(text=f"Requested by {ctx.author.name}", icon_url=ctx.author.display_avatar.url if ctx.author.avatar else None)

        if image_url_for_thumbnail:
            embed.set_thumbnail(url=image_url_for_thumbnail)
        
        if fields:
            for name, value in fields:
                embed.add_field(name=name, value=value, inline=False)
        
        try:
            sent_message = await ctx.send(embed=embed)
            return sent_message
        except discord.HTTPException as e:
            print(f"Error sending embed in _send_embed_response: {e}")
            return None

    async def _get_lastfm_username(self, user_id: int) -> Optional[str]:
        """Helper to get Last.fm username from DB."""
        if not self.db_params: return None
        conn = None
        try:
            conn = self._get_db_connection()
            cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
            cursor.execute("SELECT lastfm_username FROM lastfm_global_users WHERE user_id = %s", (user_id,))
            row = cursor.fetchone()
            return row['lastfm_username'] if row else None
        except (psycopg2.Error, ConnectionError) as e:
            print(f"ERROR [LastFM _get_lastfm_username DB]: {e}")
            return None
        finally:
            if conn: cursor.close(); conn.close()

    def _parse_lastfm_period(self, period_input: str) -> Tuple[Optional[str], Optional[str]]:
        period_input_lower = period_input.lower()
        if period_input_lower == "overall": return "overall", "Overall"
        if period_input_lower in ["1d", "day", "24h"]: return "7day", "Last 7 Days (defaulted from 1 Day)"
        if period_input_lower in ["7d", "week", "7day"]: return "7day", "Last 7 Days"
        if period_input_lower in ["30d", "1m", "month", "1month"]: return "1month", "Last Month"
        if period_input_lower in ["3m", "3months", "3month"]: return "3month", "Last 3 Months"
        if period_input_lower in ["6m", "6months", "6month"]: return "6month", "Last 6 Months"
        if period_input_lower in ["1y", "year", "12m", "12months", "12month"]: return "12month", "Last 12 Months"
        return None, None

    @commands.group(name="fm", invoke_without_command=True)
    @commands.cooldown(1, 3, commands.BucketType.user)
    async def fm_group(self, ctx: commands.Context, *, member: Optional[discord.Member] = None):
        if not self.api_key or not self.db_params:
            await self._send_embed_response(ctx, "Last.fm Error", "Last.fm integration is not fully configured on the bot's side.", discord.Color.red())
            return

        target_user = member or ctx.author
        lastfm_username = await self._get_lastfm_username(target_user.id)

        if not lastfm_username:
            is_self = target_user == ctx.author
            msg = f"You need to set your Last.fm username first using `.fm set <your_lastfm_username>`." if is_self \
                  else f"{target_user.display_name} has not set their Last.fm username with this bot."
            await self._send_embed_response(ctx, "Last.fm Account Not Set", msg, discord.Color.orange())
            return

        params = {"method": "user.getrecenttracks", "user": lastfm_username, "limit": 1, "extended": "1"}
        data = await self._call_lastfm_api(params)

        if not data or 'recenttracks' not in data or not data['recenttracks'].get('track'):
            error_msg = data.get('message', f"Could not fetch recent tracks for '{lastfm_username}' from Last.fm.") if data and 'error' in data else f"Could not fetch recent tracks for '{lastfm_username}' from Last.fm."
            await self._send_embed_response(ctx, "Last.fm Error", error_msg, discord.Color.red())
            return

        track_info = data['recenttracks']['track'][0]
        
        track_name = track_info.get('name', "Unknown Track")
        
        # --- More Robust Artist Name Parsing ---
        artist_name = "Unknown Artist" # Default
        artist_data_raw = track_info.get('artist')
        if isinstance(artist_data_raw, dict):
            artist_name = artist_data_raw.get('#text', artist_name) # Use default if #text is missing
            if artist_name == "Unknown Artist" and '#text' not in artist_data_raw:
                 print(f"[LastFM DEBUG fm_group] Artist data for track '{track_name}' was a dict but missing '#text': {artist_data_raw}")
        elif isinstance(artist_data_raw, str) and artist_data_raw.strip(): # If it's just a string name
            artist_name = artist_data_raw
        else: # artist_data is None or some other unexpected type
            print(f"[LastFM DEBUG fm_group] Artist data for track '{track_name}' was not a dict or string: {type(artist_data_raw)} - {artist_data_raw}")
        # --- End Robust Artist Name Parsing ---
        
        # --- More Robust Album Name Parsing ---
        album_name = "Unknown Album" # Default
        album_data_raw = track_info.get('album')
        if isinstance(album_data_raw, dict):
            album_name = album_data_raw.get('#text', album_name)
            if album_name == "Unknown Album" and '#text' not in album_data_raw:
                print(f"[LastFM DEBUG fm_group] Album data for track '{track_name}' was a dict but missing '#text': {album_data_raw}")
        elif isinstance(album_data_raw, str) and album_data_raw.strip():
            album_name = album_data_raw
        else:
            print(f"[LastFM DEBUG fm_group] Album data for track '{track_name}' was not a dict or string: {type(album_data_raw)} - {album_data_raw}")
        # --- End Robust Album Name Parsing ---
        
        image_url = None 
        for img in track_info.get('image', []): 
            if isinstance(img, dict) and img.get('size') == 'extralarge' and img.get('#text'): image_url = img['#text']; break
            elif isinstance(img, dict) and img.get('size') == 'large' and img.get('#text'): image_url = img['#text'] 
        if not image_url and track_info.get('image'): 
            largest_image = None; size_order = ['mega', 'extralarge', 'large', 'medium', 'small', ''] 
            for size_key in size_order:
                for img in track_info.get('image', []):
                    if isinstance(img, dict) and img.get('size') == size_key and img.get('#text'): largest_image = img['#text']; break
                if largest_image: break
            image_url = largest_image

        is_now_playing = track_info.get('@attr', {}).get('nowplaying') == 'true'
        embed_title = f"🎧 Last.fm for {lastfm_username}"
        description = f"**Track:** [{track_name}]({track_info.get('url', '#')})\n" \
                      f"**Artist:** {artist_name}\n" # Uses the robustly parsed artist_name
        if album_name and album_name != "Unknown Album": 
            description += f"**Album:** {album_name}\n" # Uses the robustly parsed album_name
        
        if is_now_playing: description += f"\n*Scrobbled: just now*"
        else:
            scrobble_date_uts = track_info.get('date', {}).get('uts')
            if scrobble_date_uts:
                try:
                    scrobble_datetime = datetime.datetime.fromtimestamp(int(scrobble_date_uts), tz=datetime.timezone.utc)
                    description += f"\n*Scrobbled: {discord.utils.format_dt(scrobble_datetime, style='R')}*"
                except ValueError: description += f"\n*Scrobbled: Invalid date from API*"
            else: description += "\n*Scrobble time not available*"

        sent_message = await self._send_embed_response(
            ctx, title=embed_title, description=description, color=discord.Color.red(), 
            image_url_for_thumbnail=image_url, author_for_embed=target_user
        )
        if sent_message:
            try:
                await sent_message.add_reaction("⬆️"); await asyncio.sleep(0.1); await sent_message.add_reaction("⬇️")
            except discord.Forbidden: print(f"[LastFM DEBUG] Bot missing 'Add Reactions' in {ctx.channel.name}.")
            except Exception as e: print(f"[LastFM DEBUG] Error adding reactions: {e}")

    @fm_group.command(name="set")
    async def fm_set(self, ctx: commands.Context, lastfm_username: str):
        if not self.db_params or not self.api_key:
            await self._send_embed_response(ctx, "Configuration Error", "Last.fm integration is not fully configured.", discord.Color.red())
            return

        validation_params = {"method": "user.getinfo", "user": lastfm_username}
        validation_data = await self._call_lastfm_api(validation_params)
        if not validation_data or 'user' not in validation_data:
            error_msg = validation_data.get('message', f"Could not find Last.fm user '{lastfm_username}'.") if validation_data and 'error' in validation_data else f"Could not validate Last.fm user '{lastfm_username}'."
            await self._send_embed_response(ctx, "Last.fm Username Invalid", error_msg, discord.Color.red())
            return

        conn = None
        try:
            conn = self._get_db_connection()
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO lastfm_global_users (user_id, lastfm_username, linked_at)
                VALUES (%s, %s, %s)
                ON CONFLICT (user_id) DO UPDATE SET lastfm_username = EXCLUDED.lastfm_username, linked_at = EXCLUDED.linked_at
            """, (ctx.author.id, lastfm_username, datetime.datetime.now(datetime.timezone.utc)))
            conn.commit(); cursor.close()
            await self._send_embed_response(ctx, "Last.fm Account Set", f"Your Last.fm username has been globally set to **{lastfm_username}**.", discord.Color.green())
        except (psycopg2.Error, ConnectionError) as e:
            await self._send_embed_response(ctx, "Database Error", "Failed to save your Last.fm username.", discord.Color.red())
            print(f"ERROR [LastFM fm_set DB]: {e}")
        finally:
            if conn: conn.close()

    @fm_group.command(name="remove", aliases=["unset"])
    async def fm_remove(self, ctx: commands.Context):
        if not self.db_params:
            await self._send_embed_response(ctx, "Database Error", "Database not configured.", discord.Color.red())
            return
        conn = None
        try:
            conn = self._get_db_connection()
            cursor = conn.cursor()
            cursor.execute("DELETE FROM lastfm_global_users WHERE user_id = %s", (ctx.author.id,))
            deleted_rows = cursor.rowcount; conn.commit(); cursor.close()
            if deleted_rows > 0: await self._send_embed_response(ctx, "Last.fm Account Removed", "Your globally linked Last.fm username has been removed.", discord.Color.orange())
            else: await self._send_embed_response(ctx, "Last.fm Account Not Set", "You don't have a Last.fm username set.", discord.Color.blue())
        except (psycopg2.Error, ConnectionError) as e:
            await self._send_embed_response(ctx, "Database Error", "Failed to remove your Last.fm username.", discord.Color.red())
            print(f"ERROR [LastFM fm_remove DB]: {e}")
        finally:
            if conn: conn.close()

    @fm_group.command(name="topartists", aliases=["ta", "tar"])
    @commands.cooldown(1, 10, commands.BucketType.user)
    async def fm_top_artists(self, ctx: commands.Context, member: Optional[discord.Member] = None, period_input: str = "overall", limit: int = 5):
        if not self.api_key or not self.db_params:
            await self._send_embed_response(ctx, "Last.fm Error", "Last.fm integration not fully configured.", discord.Color.red())
            return

        target_user = member or ctx.author
        lastfm_username = await self._get_lastfm_username(target_user.id)

        if not lastfm_username:
            is_self = target_user == ctx.author
            msg = f"You need to set your Last.fm username first with `.fm set <username>`." if is_self \
                  else f"{target_user.display_name} has not set their Last.fm username."
            await self._send_embed_response(ctx, "Last.fm Account Not Set", msg, discord.Color.orange())
            return

        api_period, display_period_name = self._parse_lastfm_period(period_input)
        if not api_period:
            valid_periods_display = "overall, 1d/day/24h, 7d/week, 1m/30d/month, 3m, 6m, 1y/12m/year"
            await self._send_embed_response(ctx, "Invalid Period", f"Invalid period. Valid periods are: {valid_periods_display}.", discord.Color.red())
            return
        
        if not (1 <= limit <= 15): 
            await self._send_embed_response(ctx, "Invalid Limit", "Limit must be between 1 and 15.", discord.Color.red())
            return

        params = {"method": "user.gettopartists", "user": lastfm_username, "period": api_period, "limit": limit}
        data = await self._call_lastfm_api(params)

        if not data or 'topartists' not in data or not data['topartists'].get('artist'):
            error_msg = data.get('message', f"Could not fetch top artists for '{lastfm_username}' (period: {display_period_name}).") if data and 'error' in data else f"Could not fetch top artists for '{lastfm_username}' (period: {display_period_name})."
            await self._send_embed_response(ctx, "Last.fm Error", error_msg, discord.Color.red())
            return
        
        artists_data = data['topartists']['artist']
        if not isinstance(artists_data, list): artists_data = [artists_data] if artists_data else []

        embed_title = f"Top Artists for {lastfm_username} ({display_period_name})"
        description_lines = []
        if artists_data:
            for i, artist_info in enumerate(artists_data):
                if not isinstance(artist_info, dict): continue 
                artist_name_val = artist_info.get('name', 'Unknown Artist') # Use .get() for safety
                play_count = artist_info.get('playcount', 'N/A')
                artist_url = artist_info.get('url', '#')
                description_lines.append(f"{i+1}. [{artist_name_val}]({artist_url}) - **{play_count}** plays")
        
        description = "\n".join(description_lines) if description_lines else "No top artists found for this period."
        await self._send_embed_response(ctx, embed_title, description, discord.Color.blue(), author_for_embed=target_user)

    @fm_group.error
    async def fm_group_error(self, ctx, error):
        if isinstance(error, commands.CommandOnCooldown): await self._send_embed_response(ctx, "Cooldown", f"Command on cooldown. Try again in {error.retry_after:.2f}s.", discord.Color.orange())
        elif isinstance(error, commands.MemberNotFound): await self._send_embed_response(ctx, "User Not Found", f"Could not find user: {error.argument}", discord.Color.red())
        elif isinstance(error, commands.CommandInvokeError) and isinstance(error.original, KeyError): 
            await self._send_embed_response(ctx, "Last.fm Data Error", "Could not parse track information from Last.fm. The data might be incomplete for this track.", discord.Color.orange())
            print(f"KeyError in fm_group: {error.original}"); traceback.print_exc()
        else: await self._send_embed_response(ctx, "Last.fm Error", f"Unexpected error: {error}", discord.Color.red()); print(f"Error in fm_group: {error}"); traceback.print_exc()

    @fm_set.error
    async def fm_set_error(self, ctx, error):
        if isinstance(error, commands.MissingRequiredArgument) and error.param.name == "lastfm_username":
            await self._send_embed_response(ctx, "Missing Username", "Provide username. Usage: `.fm set YourUsername`", discord.Color.red())
        else: await self._send_embed_response(ctx, "Set Last.fm Error", f"Unexpected error: {error}", discord.Color.red()); print(f"Error in fm_set: {error}"); traceback.print_exc()

    @fm_top_artists.error
    async def fm_top_artists_error(self, ctx, error):
        if isinstance(error, commands.CommandOnCooldown): await self._send_embed_response(ctx, "Cooldown", f"Command on cooldown. Try again in {error.retry_after:.2f}s.", discord.Color.orange())
        elif isinstance(error, commands.MemberNotFound): await self._send_embed_response(ctx, "User Not Found", f"Could not find user: {error.argument}", discord.Color.red())
        elif isinstance(error, commands.BadArgument): await self._send_embed_response(ctx, "Invalid Argument", "Please provide a valid number for the limit, or a valid period.", discord.Color.red())
        elif isinstance(error, commands.CommandInvokeError) and isinstance(error.original, ConnectionError):
            await self._send_embed_response(ctx, "Database Error", "Could not connect to the database.", discord.Color.red())
        else: await self._send_embed_response(ctx, "Top Artists Error", f"An unexpected error occurred: {error}", discord.Color.red()); print(f"Error in fm_top_artists: {error}"); traceback.print_exc()

async def setup(bot: commands.Bot):
    await bot.add_cog(LastFM(bot))
    print("Cog 'LastFM' (with Top Artists & updated timeframes & robust parsing) loaded successfully.")

