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
    Requires a LASTFM_API_KEY environment variable.
    """
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.api_key = os.getenv("LASTFM_API_KEY")
        if not self.api_key:
            print("ERROR [LastFM Init]: LASTFM_API_KEY environment variable not set. Last.fm cog will be non-functional.")
            # You might want to raise an error or disable the cog more formally here
        
        self.db_url = os.getenv("DATABASE_URL")
        self.db_params = None
        if self.db_url:
            self.db_params = self._parse_db_url(self.db_url)
            self._init_db() # Ensure table exists
            # No in-memory cache for Last.fm usernames needed for now, direct DB access is fine for set/get
        else:
            print("ERROR [LastFM Init]: DATABASE_URL environment variable not set. Last.fm cog cannot store usernames.")
        
        # Create an aiohttp session for API calls
        self.http_session = aiohttp.ClientSession()
        print("[LastFM DEBUG] Cog initialized.")

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
        if not self.db_params: return
        conn = None
        try:
            conn = self._get_db_connection()
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS lastfm_users (
                    guild_id BIGINT NOT NULL,
                    user_id BIGINT NOT NULL,
                    lastfm_username TEXT NOT NULL,
                    PRIMARY KEY (guild_id, user_id) 
                )
            """)
            # Index for faster lookups by user_id (though primary key already covers it for user_id within a guild)
            # cursor.execute("CREATE INDEX IF NOT EXISTS idx_lastfm_users_user_id ON lastfm_users (user_id);")
            conn.commit()
            cursor.close()
            print("[LastFM DEBUG] 'lastfm_users' table checked/created.")
        except (psycopg2.Error, ConnectionError) as e:
            print(f"ERROR [LastFM _init_db]: DB table init failed: {e}")
        finally:
            if conn: conn.close()

    async def _call_lastfm_api(self, params: Dict[str, str]) -> Optional[Dict[str, Any]]:
        """Helper function to make calls to the Last.fm API."""
        if not self.api_key:
            print("[LastFM DEBUG] API key not set, cannot call API.")
            return None

        # Add common parameters
        params['api_key'] = self.api_key
        params['format'] = 'json'
        
        request_url = LASTFM_API_BASE_URL
        print(f"[LastFM DEBUG] Calling API: {request_url} with params: {params}")

        try:
            async with self.http_session.get(request_url, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    # print(f"[LastFM DEBUG] API Response: {data}") # Can be very verbose
                    if 'error' in data:
                        print(f"ERROR [LastFM API Call]: {data.get('message', 'Unknown API error')} (Code: {data.get('error')})")
                        return data # Return error data for handling
                    return data
                else:
                    print(f"ERROR [LastFM API Call]: HTTP Status {response.status} for params {params}. Response: {await response.text()}")
                    return None
        except aiohttp.ClientConnectorError as e:
            print(f"ERROR [LastFM API Call]: Connection error: {e}")
            return None
        except Exception as e:
            print(f"ERROR [LastFM API Call]: Unexpected error: {e}")
            traceback.print_exc()
            return None
            
    # --- Embed Helper (copied from your AutoRole for consistency) ---
    def _create_fallback_embed(self, title: str, description: str, color: discord.Color, ctx: Optional[commands.Context] = None) -> discord.Embed:
        embed = discord.Embed(title=title, description=description, color=color, timestamp=datetime.datetime.now(datetime.timezone.utc))
        if ctx and ctx.author:
            embed.set_footer(text=f"Requested by {ctx.author.name}", icon_url=ctx.author.display_avatar.url if ctx.author.avatar else None)
        return embed

    async def _send_embed_response(self, ctx: commands.Context, title: str, description: str, color: discord.Color):
        utils_cog = self.bot.get_cog('Utils')
        if utils_cog and hasattr(utils_cog, 'create_embed'): # Check if create_embed exists
            embed = utils_cog.create_embed(ctx, title=title, description=description, color=color)
        else:
            embed = self._create_fallback_embed(title=title, description=description, color=color, ctx=ctx)
        await ctx.send(embed=embed)

    # --- Commands ---
    @commands.group(name="fm", invoke_without_command=True)
    @commands.cooldown(1, 5, commands.BucketType.user)
    async def fm_group(self, ctx: commands.Context, *, member: Optional[discord.Member] = None):
        """Shows your or another user's currently playing/last scrobbled track on Last.fm.
        Use '.fm set <username>' to link your Last.fm account.
        Usage: .fm [@user]
        """
        if not self.api_key or not self.db_params:
            await self._send_embed_response(ctx, "Last.fm Error", "Last.fm integration is not fully configured on the bot's side (API key or DB missing).", discord.Color.red())
            return

        target_user = member or ctx.author
        lastfm_username = None
        conn = None
        try:
            conn = self._get_db_connection()
            cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
            cursor.execute("SELECT lastfm_username FROM lastfm_users WHERE guild_id = %s AND user_id = %s", (ctx.guild.id, target_user.id))
            row = cursor.fetchone()
            if row:
                lastfm_username = row['lastfm_username']
            cursor.close()
        except (psycopg2.Error, ConnectionError) as e:
            await self._send_embed_response(ctx, "Database Error", "Could not retrieve Last.fm username.", discord.Color.red())
            print(f"ERROR [LastFM fm_group DB]: {e}")
            return
        finally:
            if conn: conn.close()

        if not lastfm_username:
            is_self = target_user == ctx.author
            msg = f"You need to set your Last.fm username first using `.fm set <your_lastfm_username>`." if is_self \
                  else f"{target_user.display_name} has not set their Last.fm username with this bot in this server."
            await self._send_embed_response(ctx, "Last.fm Account Not Set", msg, discord.Color.orange())
            return

        # Fetch recent tracks
        params = {
            "method": "user.getrecenttracks",
            "user": lastfm_username,
            "limit": 1 # We only need the most recent one
        }
        data = await self._call_lastfm_api(params)

        if not data or 'recenttracks' not in data or not data['recenttracks'].get('track'):
            error_msg = data.get('message', 'Could not fetch recent tracks from Last.fm.') if data and 'error' in data else 'Could not fetch recent tracks from Last.fm.'
            await self._send_embed_response(ctx, "Last.fm Error", error_msg, discord.Color.red())
            return

        track_info = data['recenttracks']['track'][0] # Get the first (most recent) track
        
        artist_name = track_info['artist']['#text']
        track_name = track_info['name']
        album_name = track_info['album']['#text']
        image_url = None
        # Last.fm returns images in different sizes. Try to get the 'extralarge' or 'large'.
        for img in track_info.get('image', []):
            if img['size'] == 'extralarge':
                image_url = img['#text']
                break
            elif img['size'] == 'large':
                image_url = img['#text'] # Fallback to large if extralarge not found
        
        is_now_playing = track_info.get('@attr', {}).get('nowplaying') == 'true'
        
        embed_title = f"Now Playing on Last.fm for {lastfm_username}" if is_now_playing else f"Last Scrobbled by {lastfm_username}"
        
        description = f"**Track:** [{track_name}]({track_info.get('url', '#')})\n" \
                      f"**Artist:** {artist_name}\n"
        if album_name: # Album might not always be present
            description += f"**Album:** {album_name}\n"
        
        if is_now_playing:
            description += "\n*Currently Listening...*"
        else:
            # If not now playing, Last.fm provides a 'date' field for when it was scrobbled
            scrobble_date_uts = track_info.get('date', {}).get('uts')
            if scrobble_date_uts:
                scrobble_datetime = datetime.datetime.fromtimestamp(int(scrobble_date_uts), tz=datetime.timezone.utc)
                description += f"\n*Scrobbled: {discord.utils.format_dt(scrobble_datetime, style='R')}*"


        utils_cog = self.bot.get_cog('Utils')
        if utils_cog and hasattr(utils_cog, 'create_embed'):
            embed = utils_cog.create_embed(ctx, title=embed_title, description=description, color=discord.Color.red()) # Last.fm red
            if target_user.avatar: embed.set_author(name=target_user.display_name, icon_url=target_user.display_avatar.url)
            else: embed.set_author(name=target_user.display_name)
        else: # Fallback
            embed = discord.Embed(title=embed_title, description=description, color=discord.Color.red(), timestamp=datetime.datetime.now(datetime.timezone.utc))
            if target_user.avatar: embed.set_author(name=target_user.display_name, icon_url=target_user.display_avatar.url)
            else: embed.set_author(name=target_user.display_name)
            embed.set_footer(text=f"Requested by {ctx.author.name}")

        if image_url:
            embed.set_thumbnail(url=image_url)
            
        await ctx.send(embed=embed)


    @fm_group.command(name="set")
    async def fm_set(self, ctx: commands.Context, lastfm_username: str):
        """Links your Discord account to your Last.fm username for this server.
        Usage: .fm set YourLastfmUsername
        """
        if not self.db_params:
            await self._send_embed_response(ctx, "Database Error", "Cannot save Last.fm username, database not configured.", discord.Color.red())
            return
        if not self.api_key: # Also check API key as a sanity check for the feature being usable
            await self._send_embed_response(ctx, "Configuration Error", "Last.fm API Key not configured by bot owner.", discord.Color.red())
            return

        # Optional: Validate username by making a quick API call
        validation_params = {"method": "user.getinfo", "user": lastfm_username}
        validation_data = await self._call_lastfm_api(validation_params)
        if not validation_data or 'user' not in validation_data:
            error_msg = validation_data.get('message', f"Could not find Last.fm user '{lastfm_username}'. Please check the username.") if validation_data and 'error' in validation_data else f"Could not validate Last.fm user '{lastfm_username}'. Please check the username or try again later."
            await self._send_embed_response(ctx, "Last.fm Username Invalid", error_msg, discord.Color.red())
            return

        conn = None
        try:
            conn = self._get_db_connection()
            cursor = conn.cursor()
            # UPSERT: Insert or update if the user already has a username set for this guild
            cursor.execute("""
                INSERT INTO lastfm_users (guild_id, user_id, lastfm_username)
                VALUES (%s, %s, %s)
                ON CONFLICT (guild_id, user_id) DO UPDATE SET lastfm_username = EXCLUDED.lastfm_username
            """, (ctx.guild.id, ctx.author.id, lastfm_username))
            conn.commit()
            cursor.close()
            await self._send_embed_response(ctx, "Last.fm Account Set", f"Your Last.fm username has been set to **{lastfm_username}** for this server.", discord.Color.green())
            print(f"[LastFM DEBUG] User {ctx.author.id} in guild {ctx.guild.id} set Last.fm username to {lastfm_username}")
        except (psycopg2.Error, ConnectionError) as e:
            await self._send_embed_response(ctx, "Database Error", "Failed to save your Last.fm username.", discord.Color.red())
            print(f"ERROR [LastFM fm_set DB]: {e}")
        finally:
            if conn: conn.close()

    @fm_group.command(name="remove", aliases=["unset"])
    async def fm_remove(self, ctx: commands.Context):
        """Removes your linked Last.fm username for this server."""
        if not self.db_params:
            await self._send_embed_response(ctx, "Database Error", "Cannot remove Last.fm username, database not configured.", discord.Color.red())
            return
        
        conn = None
        try:
            conn = self._get_db_connection()
            cursor = conn.cursor()
            cursor.execute("DELETE FROM lastfm_users WHERE guild_id = %s AND user_id = %s", (ctx.guild.id, ctx.author.id))
            deleted_rows = cursor.rowcount # Check if a row was actually deleted
            conn.commit()
            cursor.close()
            if deleted_rows > 0:
                await self._send_embed_response(ctx, "Last.fm Account Removed", "Your Last.fm username has been removed for this server.", discord.Color.orange())
                print(f"[LastFM DEBUG] User {ctx.author.id} in guild {ctx.guild.id} removed Last.fm username.")
            else:
                await self._send_embed_response(ctx, "Last.fm Account Not Set", "You don't have a Last.fm username set with this bot in this server.", discord.Color.blue())
        except (psycopg2.Error, ConnectionError) as e:
            await self._send_embed_response(ctx, "Database Error", "Failed to remove your Last.fm username.", discord.Color.red())
            print(f"ERROR [LastFM fm_remove DB]: {e}")
        finally:
            if conn: conn.close()

    # --- Error Handlers for the group ---
    @fm_group.error
    async def fm_group_error(self, ctx, error):
        if isinstance(error, commands.CommandOnCooldown):
            await self._send_embed_response(ctx, "Cooldown", f"This command is on cooldown. Try again in {error.retry_after:.2f}s.", discord.Color.orange())
        elif isinstance(error, commands.MemberNotFound): # For the optional member argument in the main fm command
             await self._send_embed_response(ctx, "User Not Found", f"Could not find user: {error.argument}", discord.Color.red())
        else:
            await self._send_embed_response(ctx, "Last.fm Error", f"An unexpected error occurred: {error}", discord.Color.red())
            print(f"Error in fm_group: {error}"); traceback.print_exc()

    @fm_set.error
    async def fm_set_error(self, ctx, error):
        if isinstance(error, commands.MissingRequiredArgument):
            if error.param.name == "lastfm_username":
                await self._send_embed_response(ctx, "Missing Username", "You need to provide your Last.fm username.\nUsage: `.fm set YourLastfmUsername`", discord.Color.red())
        else:
            await self._send_embed_response(ctx, "Set Last.fm Error", f"An unexpected error occurred: {error}", discord.Color.red())
            print(f"Error in fm_set: {error}"); traceback.print_exc()


async def setup(bot: commands.Bot):
    # Ensure aiohttp is in requirements.txt
    # Ensure LASTFM_API_KEY and DATABASE_URL are set as environment variables
    await bot.add_cog(LastFM(bot))
    print("Cog 'LastFM' loaded successfully.")

