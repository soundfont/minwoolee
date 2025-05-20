import discord
from discord.ext import commands
import datetime
import psycopg2
import psycopg2.extras
import os
import traceback
from typing import Optional, Dict, Any, List, Tuple
from urllib.parse import urlparse
import aiohttp

# --- Last.fm API Configuration ---
LASTFM_API_BASE_URL = "http://ws.audioscrobbler.com/2.0/"
# --- Placeholder for Album Art ---
# User provided: "https://placehold.co/300x300?text=(No+album+art)"
USER_PLACEHOLDER_ALBUM_ART = "https://placehold.co/300x300?text=(No+album+art)"

# --- Database Helper Functions ---
def parse_db_url(url: str) -> Optional[dict]:
    try:
        parsed = urlparse(url)
        return {
            "dbname": parsed.path[1:], "user": parsed.username,
            "password": parsed.password, "host": parsed.hostname,
            "port": parsed.port or 5432,
            "sslmode": "require" if "sslmode=require" in url else None
        }
    except Exception as e:
        print(f"ERROR [LastFM Utils _parse_db_url]: Failed to parse DATABASE_URL: {e}")
        return None

def get_db_connection(db_params: Optional[Dict]):
    if not db_params: raise ConnectionError("DB params not configured for Last.fm cog.")
    try:
        return psycopg2.connect(**db_params)
    except psycopg2.Error as e:
        print(f"ERROR [LastFM Utils _get_db_connection]: DB connection failed: {e}")
        raise ConnectionError(f"Failed to connect to DB: {e}")

def init_lastfm_db(db_params: Optional[Dict]):
    if not db_params: 
        print("WARN [LastFM Utils init_lastfm_db]: Database not configured. Skipping table initialization.")
        return
    conn = None
    try:
        conn = get_db_connection(db_params)
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
        print("[LastFM Utils DEBUG] 'lastfm_global_users' table checked/created.")
    except (psycopg2.Error, ConnectionError) as e:
        print(f"ERROR [LastFM Utils init_lastfm_db]: DB table init failed: {e}")
    finally:
        if conn: conn.close()

async def get_lastfm_username_from_db(db_params: Optional[Dict], user_id: int) -> Optional[str]:
    if not db_params: return None
    conn = None
    try:
        conn = get_db_connection(db_params)
        cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        cursor.execute("SELECT lastfm_username FROM lastfm_global_users WHERE user_id = %s", (user_id,))
        row = cursor.fetchone()
        return row['lastfm_username'] if row else None
    except (psycopg2.Error, ConnectionError) as e:
        print(f"ERROR [LastFM Utils get_lastfm_username_from_db]: {e}")
        return None
    finally:
        if conn: cursor.close(); conn.close()

async def set_lastfm_username_in_db(db_params: Optional[Dict], user_id: int, lastfm_username: str, linked_at: datetime.datetime) -> bool:
    if not db_params: return False
    conn = None
    try:
        conn = get_db_connection(db_params)
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO lastfm_global_users (user_id, lastfm_username, linked_at)
            VALUES (%s, %s, %s)
            ON CONFLICT (user_id) DO UPDATE SET lastfm_username = EXCLUDED.lastfm_username, linked_at = EXCLUDED.linked_at
        """, (user_id, lastfm_username, linked_at))
        conn.commit(); cursor.close()
        return True
    except (psycopg2.Error, ConnectionError) as e:
        print(f"ERROR [LastFM Utils set_lastfm_username_in_db]: {e}")
        return False
    finally:
        if conn: conn.close()

async def remove_lastfm_username_from_db(db_params: Optional[Dict], user_id: int) -> int:
    if not db_params: return 0
    conn = None
    deleted_rows = 0
    try:
        conn = get_db_connection(db_params)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM lastfm_global_users WHERE user_id = %s", (user_id,))
        deleted_rows = cursor.rowcount
        conn.commit(); cursor.close()
    except (psycopg2.Error, ConnectionError) as e:
        print(f"ERROR [LastFM Utils remove_lastfm_username_from_db]: {e}")
    finally:
        if conn: conn.close()
    return deleted_rows


# --- Last.fm API Helper ---
async def call_lastfm_api(http_session: aiohttp.ClientSession, api_key: Optional[str], params: Dict[str, str]) -> Optional[Dict[str, Any]]:
    if not api_key:
        print("[LastFM Utils DEBUG] API key not set, cannot call API.")
        return None
    params['api_key'] = api_key
    params['format'] = 'json'
    
    print(f"[LastFM Utils DEBUG] Calling API: {LASTFM_API_BASE_URL} with params: {params}")
    try:
        async with http_session.get(LASTFM_API_BASE_URL, params=params) as response:
            print(f"[LastFM Utils DEBUG] API Response status: {response.status}")
            if response.status == 200:
                data = await response.json()
                if 'error' in data:
                    print(f"ERROR [LastFM Utils API Call]: {data.get('message', 'Unknown API error')} (Code: {data.get('error')}) for user {params.get('user', 'N/A')}")
                    return data 
                return data
            else:
                print(f"ERROR [LastFM Utils API Call]: HTTP Status {response.status} for params {params}. Response: {await response.text()}")
                return None
    except aiohttp.ClientConnectorError as e:
        print(f"ERROR [LastFM Utils API Call]: Connection error: {e}")
        return None
    except Exception as e:
        print(f"ERROR [LastFM Utils API Call]: Unexpected error: {e}"); traceback.print_exc()
        return None

# --- Period Parsing Helper ---
def parse_lastfm_period_for_api(period_input: str) -> Tuple[Optional[str], Optional[str]]:
    period_input_lower = period_input.lower()
    if period_input_lower == "overall": return "overall", "Overall"
    if period_input_lower in ["1d", "day", "24h"]: return "7day", "Last 7 Days (defaulted from 1 Day)"
    if period_input_lower in ["7d", "week", "7day"]: return "7day", "Last 7 Days"
    if period_input_lower in ["30d", "1m", "month", "1month"]: return "1month", "Last Month"
    if period_input_lower in ["3m", "3months", "3month"]: return "3month", "Last 3 Months"
    if period_input_lower in ["6m", "6months", "6month"]: return "6month", "Last 6 Months"
    if period_input_lower in ["1y", "year", "12m", "12months", "12month"]: return "12month", "Last 12 Months"
    return None, None

# --- Embed Helper (wrapper around main Utils cog) ---
async def send_fm_embed(
    bot: commands.Bot, 
    ctx: commands.Context, 
    title: str, 
    description: Optional[str] = None, 
    color: discord.Color = discord.Color.blue(), 
    image_url_for_thumbnail: Optional[str] = None, 
    author_for_embed: Optional[discord.User | discord.Member] = None, 
    fields: Optional[List[Tuple[str,str]]] = None,
    file_to_send: Optional[discord.File] = None
) -> Optional[discord.Message]:
    
    utils_cog = bot.get_cog('Utils')
    embed: discord.Embed

    if utils_cog and hasattr(utils_cog, 'create_embed'):
        embed = utils_cog.create_embed(ctx, title=title, description=description, color=color)
        if author_for_embed: 
            display_avatar_url = author_for_embed.display_avatar.url if author_for_embed.avatar else None
            embed.set_author(name=str(author_for_embed.display_name), icon_url=display_avatar_url)
    else: 
        embed = discord.Embed(title=title, description=description or "", color=color, timestamp=datetime.datetime.now(datetime.timezone.utc))
        if author_for_embed:
            display_avatar_url = author_for_embed.display_avatar.url if author_for_embed.avatar else None
            embed.set_author(name=str(author_for_embed.display_name), icon_url=display_avatar_url)
        if ctx.author: 
             embed.set_footer(text=f"Requested by {ctx.author.name}", icon_url=ctx.author.display_avatar.url if ctx.author.avatar else None)

    if image_url_for_thumbnail and not file_to_send:
        embed.set_thumbnail(url=image_url_for_thumbnail)
    
    if file_to_send and embed: 
        embed.set_image(url=f"attachment://{file_to_send.filename}")

    if fields:
        for name, value in fields:
            embed.add_field(name=name, value=value, inline=False)
    
    try:
        sent_message = await ctx.send(embed=embed, file=file_to_send if file_to_send else discord.utils.MISSING)
        return sent_message
    except discord.HTTPException as e: print(f"Error sending embed via lastfm_utils: {e}")
    except Exception as e_send: print(f"Unexpected error sending embed via lastfm_utils: {e_send}"); traceback.print_exc()
    return None
