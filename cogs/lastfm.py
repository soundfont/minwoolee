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

# --- Last.fm API Configuration ---
LASTFM_API_BASE_URL = "http://ws.audioscrobbler.com/2.0/"

class LastFM(commands.Cog):
    """
    Integrates Last.fm to show what users are listening to.
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
        print("[LastFM DEBUG] Cog initialized (Global Linking).")

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
            # Table name changed to reflect global nature, user_id is now PRIMARY KEY
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
        if ctx and ctx.author:
            embed.set_footer(text=f"Requested by {ctx.author.name}", icon_url=ctx.author.display_avatar.url if ctx.author.avatar else None)
        return embed

    async def _send_embed_response(self, ctx: commands.Context, title: str, description: str, color: discord.Color):
        utils_cog = self.bot.get_cog('Utils')
        if utils_cog and hasattr(utils_cog, 'create_embed'):
            embed = utils_cog.create_embed(ctx, title=title, description=description, color=color)
        else:
            embed = self._create_fallback_embed(title=title, description=description, color=color, ctx=ctx)
        await ctx.send(embed=embed)

    @commands.group(name="fm", invoke_without_command=True)
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def fm_group(self, ctx: commands.Context, *, member: Optional[discord.Member] = None):
        """Shows your or another user's currently playing/last scrobbled track on Last.fm.
        Use '.fm set <username>' to link your Last.fm account globally.
        Usage: .fm [@user]
        """
        if not self.api_key or not self.db_params:
            await self._send_embed_response(ctx, "Last.fm Error", "Last.fm integration is not fully configured on the bot's side.", discord.Color.red())
            return

        target_user = member or ctx.author
        lastfm_username = None
        conn = None
        try:
            conn = self._get_db_connection()
            cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
            # Query based on user_id only
            cursor.execute("SELECT lastfm_username FROM lastfm_global_users WHERE user_id = %s", (target_user.id,))
            row = cursor.fetchone()
            if row:
                lastfm_username = row['lastfm_username']
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

        params = {"method": "user.getrecenttracks", "user": lastfm_username, "limit": 1}
        data = await self._call_lastfm_api(params)

        if not data or 'recenttracks' not in data or not data['recenttracks'].get('track'):
            error_msg = data.get('message', f"Could not fetch recent tracks for '{lastfm_username}' from Last.fm.") if data and 'error' in data else f"Could not fetch recent tracks for '{lastfm_username}' from Last.fm."
            await self._send_embed_response(ctx, "Last.fm Error", error_msg, discord.Color.red())
            return

        track_info = data['recenttracks']['track'][0]
        artist_name = track_info['artist']['#text']
        track_name = track_info['name']
        album_name = track_info['album']['#text']
        image_url = next((img['#text'] for img in track_info.get('image', []) if img['size'] == 'extralarge'), 
                         next((img['#text'] for img in track_info.get('image', []) if img['size'] == 'large'), None))
        
        is_now_playing = track_info.get('@attr', {}).get('nowplaying') == 'true'
        embed_title = f"Now Playing for {lastfm_username}" if is_now_playing else f"Last Scrobbled by {lastfm_username}"
        description = f"**Track:** [{track_name}]({track_info.get('url', '#')})\n" \
                      f"**Artist:** {artist_name}\n"
        if album_name: description += f"**Album:** {album_name}\n"
        
        if is_now_playing: description += "\n*Currently Listening...*"
        else:
            scrobble_date_uts = track_info.get('date', {}).get('uts')
            if scrobble_date_uts:
                scrobble_datetime = datetime.datetime.fromtimestamp(int(scrobble_date_uts), tz=datetime.timezone.utc)
                description += f"\n*Scrobbled: {discord.utils.format_dt(scrobble_datetime, style='R')}*"

        utils_cog = self.bot.get_cog('Utils')
        if utils_cog and hasattr(utils_cog, 'create_embed'):
            embed = utils_cog.create_embed(ctx, title=embed_title, description=description, color=discord.Color.red())
            if target_user.avatar: embed.set_author(name=target_user.display_name, icon_url=target_user.display_avatar.url)
            else: embed.set_author(name=target_user.display_name)
        else: 
            embed = discord.Embed(title=embed_title, description=description, color=discord.Color.red(), timestamp=datetime.datetime.now(datetime.timezone.utc))
            if target_user.avatar: embed.set_author(name=target_user.display_name, icon_url=target_user.display_avatar.url)
            else: embed.set_author(name=target_user.display_name)
            embed.set_footer(text=f"Requested by {ctx.author.name}")
        if image_url: embed.set_thumbnail(url=image_url)
        await ctx.send(embed=embed)

    @fm_group.command(name="set")
    async def fm_set(self, ctx: commands.Context, lastfm_username: str):
        """Links your Discord account to your Last.fm username globally.
        Usage: .fm set YourLastfmUsername
        """
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
            # UPSERT on user_id only
            cursor.execute("""
                INSERT INTO lastfm_global_users (user_id, lastfm_username, linked_at)
                VALUES (%s, %s, %s)
                ON CONFLICT (user_id) DO UPDATE SET lastfm_username = EXCLUDED.lastfm_username, linked_at = EXCLUDED.linked_at
            """, (ctx.author.id, lastfm_username, datetime.datetime.now(datetime.timezone.utc)))
            conn.commit()
            cursor.close()
            await self._send_embed_response(ctx, "Last.fm Account Set", f"Your Last.fm username has been globally set to **{lastfm_username}**.", discord.Color.green())
            print(f"[LastFM DEBUG] User {ctx.author.id} globally set Last.fm username to {lastfm_username}")
        except (psycopg2.Error, ConnectionError) as e:
            await self._send_embed_response(ctx, "Database Error", "Failed to save your Last.fm username.", discord.Color.red())
            print(f"ERROR [LastFM fm_set DB]: {e}")
        finally:
            if conn: conn.close()

    @fm_group.command(name="remove", aliases=["unset"])
    async def fm_remove(self, ctx: commands.Context):
        """Removes your globally linked Last.fm username."""
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
                print(f"[LastFM DEBUG] User {ctx.author.id} removed global Last.fm username.")
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
        else: await self._send_embed_response(ctx, "Last.fm Error", f"Unexpected error: {error}", discord.Color.red()); print(f"Error in fm_group: {error}"); traceback.print_exc()

    @fm_set.error
    async def fm_set_error(self, ctx, error):
        if isinstance(error, commands.MissingRequiredArgument) and error.param.name == "lastfm_username":
            await self._send_embed_response(ctx, "Missing Username", "Provide username. Usage: `.fm set YourUsername`", discord.Color.red())
        else: await self._send_embed_response(ctx, "Set Last.fm Error", f"Unexpected error: {error}", discord.Color.red()); print(f"Error in fm_set: {error}"); traceback.print_exc()

async def setup(bot: commands.Bot):
    await bot.add_cog(LastFM(bot))
    print("Cog 'LastFM' (Global Linking) loaded successfully.")

