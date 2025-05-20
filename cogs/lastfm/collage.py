import discord
from discord.ext import commands
import datetime
import os
import traceback
from typing import Optional, List, Dict, Any, Tuple
import aiohttp
import io

# Attempt to import Pillow and set a flag
try:
    from PIL import Image, ImageDraw, UnidentifiedImageError
    PILLOW_AVAILABLE = True
except ImportError:
    PILLOW_AVAILABLE = False
    print("WARNING [LastFMCollage]: Pillow library not found. Album collage feature will be disabled.")

from . import lastfm_utils # Relative import

class LastFMCollage(commands.Cog, name="Last.fm Collage"):
    """Handles the .fm collage command."""
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.api_key = os.getenv("LASTFM_API_KEY")
        self.db_params = lastfm_utils.parse_db_url(os.getenv("DATABASE_URL"))
        self.http_session = aiohttp.ClientSession()
        self.placeholder_album_art = lastfm_utils.USER_PLACEHOLDER_ALBUM_ART
        
        if not PILLOW_AVAILABLE:
            print("ERROR [LastFMCollage]: Pillow library not installed. Collage command will not work.")
        print("[LastFMCollage DEBUG] Cog initialized.")

    async def cog_unload(self):
        await self.http_session.close()
        print("[LastFMCollage DEBUG] HTTP session closed.")

    async def _create_collage_image(self, image_urls: List[str], grid_dims: Tuple[int, int], cell_size: int = 300) -> Optional[io.BytesIO]:
        if not PILLOW_AVAILABLE:
            print("[LastFMCollage _create_collage_image] Pillow library not available.")
            return None
        
        rows, cols = grid_dims
        collage_width = cols * cell_size
        collage_height = rows * cell_size
        
        collage = Image.new('RGB', (collage_width, collage_height), (47, 49, 54)) # Discord dark theme bg
        
        images_processed = 0
        for i, url in enumerate(image_urls):
            if images_processed >= rows * cols: break

            img_to_paste = None
            try:
                if not url or not url.startswith("http"): # Check for valid URL
                    print(f"[LastFMCollage] Invalid or missing image URL: '{url}'. Using placeholder.")
                    url = self.placeholder_album_art # Fallback to placeholder

                async with self.http_session.get(url) as response:
                    if response.status == 200:
                        image_bytes = await response.read()
                        img_to_paste = Image.open(io.BytesIO(image_bytes))
                    else:
                        print(f"[LastFMCollage] Failed to download image {url}, status: {response.status}. Using placeholder.")
                        async with self.http_session.get(self.placeholder_album_art) as ph_response:
                            if ph_response.status == 200: img_to_paste = Image.open(io.BytesIO(await ph_response.read()))
            except (aiohttp.ClientError, UnidentifiedImageError, Exception) as e:
                print(f"[LastFMCollage] Error processing image {url}: {e}. Using placeholder.")
                try:
                    async with self.http_session.get(self.placeholder_album_art) as ph_response:
                        if ph_response.status == 200: img_to_paste = Image.open(io.BytesIO(await ph_response.read()))
                except Exception as ph_e: print(f"[LastFMCollage] Error fetching placeholder: {ph_e}")

            if not img_to_paste: continue # Skip if image (and placeholder) failed

            if img_to_paste.mode == 'RGBA' or img_to_paste.mode == 'P':
                img_to_paste = img_to_paste.convert('RGB')

            img_width, img_height = img_to_paste.size
            if img_width == 0 or img_height == 0: continue

            if img_width / img_height > 1: # Wider
                new_height = cell_size; new_width = int(img_width * (new_height / img_height))
            else: # Taller or square
                new_width = cell_size; new_height = int(img_height * (new_width / img_width))
            
            img_to_paste = img_to_paste.resize((new_width, new_height), Image.Resampling.LANCZOS)
            left = (new_width - cell_size) / 2; top = (new_height - cell_size) / 2
            right = (new_width + cell_size) / 2; bottom = (new_height + cell_size) / 2
            img_to_paste = img_to_paste.crop((left, top, right, bottom))

            row_idx = images_processed // cols; col_idx = images_processed % cols
            x_offset = col_idx * cell_size; y_offset = row_idx * cell_size
            
            collage.paste(img_to_paste, (x_offset, y_offset))
            images_processed += 1

        if images_processed == 0: return None
        img_byte_arr = io.BytesIO(); collage.save(img_byte_arr, format='PNG'); img_byte_arr.seek(0)
        return img_byte_arr

    @commands.command(name="collage", aliases=["col"])
    @commands.cooldown(1, 30, commands.BucketType.user) # Longer cooldown for image generation
    async def fm_collage(self, ctx: commands.Context, member: Optional[discord.Member] = None, period_input: str = "overall", grid_size_str: str = "3x3"):
        """
        Generates an album art collage for a user's top albums.
        Periods: 1d/day (defaults to 7day), 7d/week, 1m/month, 3m, 6m, 1y/year, overall (default)
        Grid: NxN (e.g., 2x2, 3x3 (default), 4x4, 5x5)
        Usage: .fm collage [@user] [period] [grid_size]
        Example: .fm col @User 1m 4x4
        """
        if not PILLOW_AVAILABLE:
            await lastfm_utils.send_fm_embed(self.bot, ctx, "Feature Disabled", "The Pillow image library is not installed on the bot. Album collage feature is unavailable.", discord.Color.red())
            return
        if not self.api_key or not self.db_params:
            await lastfm_utils.send_fm_embed(self.bot, ctx, "Last.fm Error", "Last.fm integration not fully configured.", discord.Color.red())
            return

        target_user = member or ctx.author
        lastfm_username = await lastfm_utils.get_lastfm_username_from_db(self.db_params, target_user.id)

        if not lastfm_username:
            msg = f"You need to set your Last.fm username first with `.fm set <username>`." if target_user == ctx.author \
                  else f"{target_user.display_name} has not set their Last.fm username."
            await lastfm_utils.send_fm_embed(self.bot, ctx, "Last.fm Account Not Set", msg, discord.Color.orange())
            return

        api_period, display_period_name = lastfm_utils.parse_lastfm_period_for_api(period_input)
        if not api_period:
            await lastfm_utils.send_fm_embed(self.bot, ctx, "Invalid Period", "Valid periods: overall, 1d, 7d, 1m, 3m, 6m, 1y.", discord.Color.red())
            return
        
        try:
            cols, rows = map(int, grid_size_str.lower().split('x'))
            if not (1 <= cols <= 5 and 1 <= rows <= 5): raise ValueError("Grid size out of bounds")
        except ValueError:
            await lastfm_utils.send_fm_embed(self.bot, ctx, "Invalid Grid Size", "Grid size must be NxN (e.g., 3x3). Max 5x5, Min 1x1.", discord.Color.red())
            return
        
        num_albums_to_fetch = rows * cols
        
        await ctx.send(f"⏳ Generating {cols}x{rows} collage for {lastfm_username} ({display_period_name})... This might take a moment.")

        params = {"method": "user.gettopalbums", "user": lastfm_username, "period": api_period, "limit": num_albums_to_fetch}
        data = await lastfm_utils.call_lastfm_api(self.http_session, self.api_key, params)

        if not data or 'topalbums' not in data or not data['topalbums'].get('album'):
            error_msg = data.get('message', f"Could not fetch top albums for '{lastfm_username}'.") if data and 'error' in data else f"Could not fetch top albums for '{lastfm_username}'."
            await lastfm_utils.send_fm_embed(self.bot, ctx, "Last.fm Error", error_msg, discord.Color.red())
            return

        albums_data = data['topalbums']['album']
        if not isinstance(albums_data, list): albums_data = [albums_data] if albums_data else []

        if not albums_data:
            await lastfm_utils.send_fm_embed(self.bot, ctx, "No Albums Found", f"No top albums found for '{lastfm_username}' in the period '{display_period_name}'.", discord.Color.orange())
            return

        image_urls = []
        for album_info in albums_data:
            if not isinstance(album_info, dict): continue
            # Get largest available image, default to placeholder if none
            art_url = None
            for img_dict in reversed(album_info.get('image', [])): # Iterate from largest to smallest
                if isinstance(img_dict, dict) and img_dict.get('#text'):
                    art_url = img_dict['#text']
                    break
            image_urls.append(art_url if art_url and art_url.strip() else self.placeholder_album_art) 
            if len(image_urls) >= num_albums_to_fetch: break
        
        # Fill remaining slots with placeholders if not enough albums found
        while len(image_urls) < num_albums_to_fetch:
            image_urls.append(self.placeholder_album_art)

        collage_bytes_io = await self._create_collage_image(image_urls, (rows, cols))

        if collage_bytes_io:
            collage_file = discord.File(fp=collage_bytes_io, filename=f"fm_collage_{lastfm_username}_{api_period}_{rows}x{cols}.png")
            embed_title = f"Top Albums Collage for {lastfm_username} ({display_period_name} | {rows}x{cols})"
            await lastfm_utils.send_fm_embed(self.bot, ctx, title=embed_title, description=None, color=discord.Color.purple(), file_to_send=collage_file, author_for_embed=target_user)
        else:
            await lastfm_utils.send_fm_embed(self.bot, ctx, "Collage Error", "Failed to generate the album collage.", discord.Color.red())

    @fm_collage.error
    async def fm_collage_error(self, ctx, error):
        if isinstance(error, commands.CommandOnCooldown): await lastfm_utils.send_fm_embed(self.bot, ctx, "Cooldown", f"Collage command is on cooldown. Try again in {error.retry_after:.2f}s.", discord.Color.orange())
        elif isinstance(error, commands.MemberNotFound): await lastfm_utils.send_fm_embed(self.bot, ctx, "User Not Found", f"Could not find user: {error.argument}", discord.Color.red())
        elif isinstance(error, commands.MissingRequiredArgument): await lastfm_utils.send_fm_embed(self.bot, ctx, "Missing Argument", f"Missing argument: {error.param.name}. Usage: `.fm collage [@user] [period] [grid]`", discord.Color.red())
        else: await lastfm_utils.send_fm_embed(self.bot, ctx, "Collage Error", f"An unexpected error occurred: {error}", discord.Color.red()); print(f"Error in fm_collage: {error}"); traceback.print_exc()


async def setup(bot: commands.Bot):
    await bot.add_cog(LastFMCollage(bot))
    print("Cog 'LastFMCollage' loaded successfully.")

