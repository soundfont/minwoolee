import discord
from discord.ext import commands
import datetime
import psycopg2
import psycopg2.extras # For dictionary cursor
import os
import traceback
from typing import Optional, Dict, Any
from urllib.parse import urlparse, quote_plus # For URL encoding
import aiohttp # For making API requests
import asyncio # For adding reactions with a small delay

# --- Last.fm API Configuration ---
LASTFM_API_BASE_URL = "http://ws.audioscrobbler.com/2.0/"

class LastFM(commands.Cog):
    """
    Integrates Last.fm to show what users are listening to.
    Last.fm accounts are linked globally per Discord user.
    Requires a LASTFM_API_KEY environment variable.
    The bot will react to its own .fm messages with up/down arrows.
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
        print("[LastFM DEBUG] Cog initialized (Global Linking, Embed Updates).")

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

    async def _send_embed_response(self, ctx: commands.Context, title: str, description: str, color: discord.Color, image_url_for_thumbnail: Optional[str] = None, author_for_embed: Optional[discord.User | discord.Member] = None) -> Optional[discord.Message]:
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
        
        try:
            sent_message = await ctx.send(embed=embed)
            return sent_message
        except discord.HTTPException as e:
            print(f"Error sending embed in _send_embed_response: {e}")
            return None

    @commands.group(name="fm", invoke_without_command=True)
    @commands.cooldown(1, 3, commands.BucketType.user)
    async def fm_group(self, ctx: commands.Context, *, member: Optional[discord.Member] = None):
        if not self.api_key or not self.db_params:
            await self._send_embed_response(ctx, "Last.fm Error", "Last.fm integration is not fully configured on the bot's side.", discord.Color.red())
            return

        target_user = member or ctx.author
        lastfm_username = None
        conn = None
        try:
            conn = self._get_db_connection()
            cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
            cursor.execute("SELECT lastfm_username FROM lastfm_global_users WHERE user_id = %s", (target_user.id,))
            row = cursor.fetchone()
            if row: lastfm_username = row['lastfm_username']
            cursor.close()
        except (psycopg2.Error, ConnectionError) as e:
            await self._send_embed_response(ctx, "Database Error", "Could not retrieve Last.fm username.", discord.Color.red())
            print(f"ERROR [LastFM fm_group DB]: {e}"); return
        finally:
            if conn: conn.close()

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
        
        # --- Robust parsing for track details ---
        track_name = track_info.get('name', "Unknown Track")
        
        artist_data = track_info.get('artist', {})
        if isinstance(artist_data, dict):
            artist_name = artist_data.get('#text', "Unknown Artist")
        elif isinstance(artist_data, str): # Should not happen with recenttracks but defensive
            artist_name = artist_data
        else:
            artist_name = "Unknown Artist"

        album_data = track_info.get('album', {})
        if isinstance(album_data, dict):
            album_name = album_data.get('#text', "Unknown Album")
        elif isinstance(album_data, str): # Should not happen
            album_name = album_data
        else:
            album_name = "Unknown Album"
        # --- End robust parsing ---
        
        image_url = None 
        for img in track_info.get('image', []):
            if img.get('size') == 'extralarge' and img.get('#text'): image_url = img['#text']; break
            elif img.get('size') == 'large' and img.get('#text'): image_url = img['#text'] 
        if not image_url and track_info.get('image'): 
            # Find largest available image if specific ones not found
            largest_image = None
            size_order = ['mega', 'extralarge', 'large', 'medium', 'small', ''] # From largest to smallest
            for size_key in size_order:
                for img in track_info.get('image', []):
                    if img.get('size') == size_key and img.get('#text'):
                        largest_image = img['#text']
                        break
                if largest_image: break
            image_url = largest_image

        is_now_playing = track_info.get('@attr', {}).get('nowplaying') == 'true'
        embed_title = f"🎧 Now Playing for {lastfm_username}" if is_now_playing else f"🎧 Last Scrobbled by {lastfm_username}"
        
        description = f"**Track:** [{track_name}]({track_info.get('url', '#')})\n" \
                      f"**Artist:** {artist_name}\n"
        if album_name and album_name != "Unknown Album": # Only show album if known
            description += f"**Album:** {album_name}\n"
        
        if is_now_playing: description += "\n*Currently Listening...*"
        else:
            scrobble_date_uts = track_info.get('date', {}).get('uts')
            if scrobble_date_uts:
                try:
                    scrobble_datetime = datetime.datetime.fromtimestamp(int(scrobble_date_uts), tz=datetime.timezone.utc)
                    description += f"\n*Scrobbled: {discord.utils.format_dt(scrobble_datetime, style='R')}*"
                except ValueError:
                    description += f"\n*Scrobbled: Invalid date from API*"


        sent_message = await self._send_embed_response(
            ctx, title=embed_title, description=description, 
            color=discord.Color.red(), 
            image_url_for_thumbnail=image_url, 
            author_for_embed=target_user
        )
            
        if sent_message:
            try:
                await sent_message.add_reaction("👍")
                await asyncio.sleep(0.1) 
                await sent_message.add_reaction("👎")
            except discord.Forbidden:
                print(f"[LastFM DEBUG] Bot missing 'Add Reactions' permission in channel {ctx.channel.name} to react to its own message.")
            except Exception as e:
                print(f"[LastFM DEBUG] Error adding reactions to own message: {e}")

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
            conn.commit()
            cursor.close()
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
            deleted_rows = cursor.rowcount
            conn.commit()
            cursor.close()
            if deleted_rows > 0:
                await self._send_embed_response(ctx, "Last.fm Account Removed", "Your globally linked Last.fm username has been removed.", discord.Color.orange())
            else:
                await self._send_embed_response(ctx, "Last.fm Account Not Set", "You don't have a Last.fm username set with this bot.", discord.Color.blue())
        except (psycopg2.Error, ConnectionError) as e:
            await self._send_embed_response(ctx, "Database Error", "Failed to remove your Last.fm username.", discord.Color.red())
            print(f"ERROR [LastFM fm_remove DB]: {e}")
        finally:
            if conn: conn.close()

    @fm_group.error
    async def fm_group_error(self, ctx, error):
        if isinstance(error, commands.CommandOnCooldown): await self._send_embed_response(ctx, "Cooldown", f"Command on cooldown. Try again in {error.retry_after:.2f}s.", discord.Color.orange())
        elif isinstance(error, commands.MemberNotFound): await self._send_embed_response(ctx, "User Not Found", f"Could not find user: {error.argument}", discord.Color.red())
        elif isinstance(error, commands.CommandInvokeError) and isinstance(error.original, KeyError): # Catch the specific KeyError
            await self._send_embed_response(ctx, "Last.fm Data Error", "Could not parse track information from Last.fm. The data structure might have changed or is incomplete for this track.", discord.Color.orange())
            print(f"KeyError in fm_group: {error.original}"); traceback.print_exc()
        else: await self._send_embed_response(ctx, "Last.fm Error", f"Unexpected error: {error}", discord.Color.red()); print(f"Error in fm_group: {error}"); traceback.print_exc()

    @fm_set.error
    async def fm_set_error(self, ctx, error):
        if isinstance(error, commands.MissingRequiredArgument) and error.param.name == "lastfm_username":
            await self._send_embed_response(ctx, "Missing Username", "Provide username. Usage: `.fm set YourUsername`", discord.Color.red())
        else: await self._send_embed_response(ctx, "Set Last.fm Error", f"Unexpected error: {error}", discord.Color.red()); print(f"Error in fm_set: {error}"); traceback.print_exc()

async def setup(bot: commands.Bot):
    await bot.add_cog(LastFM(bot))
    print("Cog 'LastFM' (Global Linking, Embed Updates, Self-React, KeyError Fix) loaded successfully.")

