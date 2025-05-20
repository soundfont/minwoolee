import discord
from discord.ext import commands
import datetime
import os
import traceback
from typing import Optional
import aiohttp
import asyncio

from . import lastfm_utils # Relative import

class LastFMNowPlaying(commands.Cog, name="Last.fm Now Playing"):
    """Handles the .fm (now playing) command."""
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.api_key = os.getenv("LASTFM_API_KEY")
        self.db_params = lastfm_utils.parse_db_url(os.getenv("DATABASE_URL"))
        self.http_session = aiohttp.ClientSession()
        self.placeholder_album_art = lastfm_utils.USER_PLACEHOLDER_ALBUM_ART
        print("[LastFMNowPlaying DEBUG] Cog initialized.")

    async def cog_unload(self):
        await self.http_session.close()
        print("[LastFMNowPlaying DEBUG] HTTP session closed.")

    # The main .fm command, could also be an alias like .np
    @commands.command(name="fm", aliases=["np"]) # Making .fm the primary here. If account.py defines fm group, this needs to be part of it.
                                             # For now, let's assume this is the main .fm command if no other subcommand is hit.
                                             # This will be adjusted if fm_base_group is used.
    @commands.cooldown(1, 3, commands.BucketType.user)
    async def fm_now_playing_command(self, ctx: commands.Context, *, member: Optional[discord.Member] = None):
        """Shows your or another user's currently playing/last scrobbled track on Last.fm.
        Usage: .fm [@user]
        """
        if not self.api_key or not self.db_params:
            await lastfm_utils.send_fm_embed(self.bot, ctx, "Last.fm Error", "Last.fm integration is not fully configured.", discord.Color.red())
            return

        target_user = member or ctx.author
        lastfm_username = await lastfm_utils.get_lastfm_username_from_db(self.db_params, target_user.id)

        if not lastfm_username:
            is_self = target_user == ctx.author
            msg = f"You need to set your Last.fm username first using `.fm set <your_lastfm_username>`." if is_self \
                  else f"{target_user.display_name} has not set their Last.fm username."
            await lastfm_utils.send_fm_embed(self.bot, ctx, "Last.fm Account Not Set", msg, discord.Color.orange())
            return
        
        params = {"method": "user.getrecenttracks", "user": lastfm_username, "limit": 1, "extended": "1"}
        data = await lastfm_utils.call_lastfm_api(self.http_session, self.api_key, params)

        if not data or 'recenttracks' not in data or not data['recenttracks'].get('track'):
            error_msg = data.get('message', f"Could not fetch recent tracks for '{lastfm_username}'.") if data and 'error' in data else f"Could not fetch recent tracks for '{lastfm_username}'."
            await lastfm_utils.send_fm_embed(self.bot, ctx, "Last.fm Error", error_msg, discord.Color.red())
            return

        track_info_list = data['recenttracks']['track']
        if not isinstance(track_info_list, list) or not track_info_list:
            await lastfm_utils.send_fm_embed(self.bot, ctx, "Last.fm Error", f"No track information found for '{lastfm_username}'.", discord.Color.red())
            return
            
        track_info = track_info_list[0] 
        track_name = track_info.get('name', "Unknown Track")
        if not track_name or not str(track_name).strip(): track_name = "Unknown Track"
        
        artist_name = "Unknown Artist" 
        artist_data_raw = track_info.get('artist')
        if isinstance(artist_data_raw, dict): artist_name_candidate = artist_data_raw.get('name'); artist_name = artist_name_candidate if isinstance(artist_name_candidate, str) and artist_name_candidate.strip() else artist_name
        elif isinstance(artist_data_raw, str) and artist_data_raw.strip(): artist_name = artist_data_raw
        elif isinstance(artist_data_raw, list) and artist_data_raw: 
            first_artist_entry = artist_data_raw[0]
            if isinstance(first_artist_entry, dict): artist_name_candidate = first_artist_entry.get('name'); artist_name = artist_name_candidate if isinstance(artist_name_candidate, str) and artist_name_candidate.strip() else artist_name
            elif isinstance(first_artist_entry, str) and first_artist_entry.strip(): artist_name = first_artist_entry
        
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
        final_thumbnail_url = image_url if image_url else self.placeholder_album_art

        is_now_playing = track_info.get('@attr', {}).get('nowplaying') == 'true'
        embed_title = f"🎧 Last.fm for {lastfm_username}"
        description = f"**Track:** [{track_name}]({track_info.get('url', '#')})\n**Artist:** {artist_name}\n"
        if album_name and album_name != "Unknown Album": description += f"**Album:** {album_name}\n"
        if is_now_playing: description += f"\n*Scrobbled: just now*"
        else:
            scrobble_date_uts = track_info.get('date', {}).get('uts')
            if scrobble_date_uts:
                try: scrobble_datetime = datetime.datetime.fromtimestamp(int(scrobble_date_uts), tz=datetime.timezone.utc); description += f"\n*Scrobbled: {discord.utils.format_dt(scrobble_datetime, style='R')}*"
                except ValueError: description += f"\n*Scrobbled: Invalid date from API*"
            else: description += "\n*Scrobble time not available*"
        
        sent_message = await lastfm_utils.send_fm_embed(self.bot, ctx, title=embed_title, description=description, color=discord.Color.red(), image_url_for_thumbnail=final_thumbnail_url, author_for_embed=target_user)
        if sent_message:
            try: await sent_message.add_reaction("⬆️"); await asyncio.sleep(0.1); await sent_message.add_reaction("⬇️")
            except Exception: pass 

    @fm_now_playing_command.error
    async def fm_now_playing_error(self, ctx, error):
        if isinstance(error, commands.CommandOnCooldown): await lastfm_utils.send_fm_embed(self.bot, ctx, "Cooldown", f"Command on cooldown. Try again in {error.retry_after:.2f}s.", discord.Color.orange())
        elif isinstance(error, commands.MemberNotFound): await lastfm_utils.send_fm_embed(self.bot, ctx, "User Not Found", f"Could not find user: {error.argument}", discord.Color.red())
        elif isinstance(error, commands.CommandInvokeError) and isinstance(error.original, KeyError): 
            await lastfm_utils.send_fm_embed(self.bot, ctx, "Last.fm Data Error", "Could not parse track information from Last.fm.", discord.Color.orange())
            print(f"KeyError in fm_now_playing: {error.original}"); traceback.print_exc()
        else: await lastfm_utils.send_fm_embed(self.bot, ctx, "Last.fm Error", f"Unexpected error: {error}", discord.Color.red()); print(f"Error in fm_now_playing: {error}"); traceback.print_exc()


async def setup(bot: commands.Bot):
    await bot.add_cog(LastFMNowPlaying(bot))
    print("Cog 'LastFMNowPlaying' loaded successfully.")
