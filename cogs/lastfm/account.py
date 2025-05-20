import discord
from discord.ext import commands
import datetime
import os
import traceback
from typing import Optional
import aiohttp

# Assuming lastfm_utils.py is in the same directory (cogs/lastfm/)
from . import lastfm_utils # Relative import

class LastFMAccount(commands.Cog, name="Last.fm Account"):
    """Commands for managing your Last.fm account link."""
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.api_key = os.getenv("LASTFM_API_KEY")
        self.db_params = lastfm_utils.parse_db_url(os.getenv("DATABASE_URL"))
        self.http_session = aiohttp.ClientSession()
        
        if not self.api_key:
            print("ERROR [LastFMAccount]: LASTFM_API_KEY not set.")
        if not self.db_params:
            print("ERROR [LastFMAccount]: DATABASE_URL not set or failed to parse.")
        print("[LastFMAccount DEBUG] Cog initialized.")

    async def cog_unload(self):
        await self.http_session.close()
        print("[LastFMAccount DEBUG] HTTP session closed.")

    @commands.group(name="fm", invoke_without_command=False) # Ensure fm group is defined if other cogs add subcommands to it
    async def fm_base_group(self, ctx: commands.Context):
        """Base group for Last.fm commands. Use subcommands like set, remove, np, ta, collage."""
        if ctx.invoked_subcommand is None:
            # Try to call the now playing command from the NowPlaying cog if no subcommand
            nowplaying_cog = self.bot.get_cog("Last.fm Now Playing")
            if nowplaying_cog and hasattr(nowplaying_cog, 'fm_now_playing_command'):
                await nowplaying_cog.fm_now_playing_command(ctx, member=None)
            else:
                await lastfm_utils.send_fm_embed(self.bot, ctx, "Last.fm", "Use `.fm set`, `.fm remove`, `.fm np`, `.fm ta`, or `.fm collage`.", discord.Color.blue())


    @fm_base_group.command(name="set")
    async def fm_set(self, ctx: commands.Context, lastfm_username: str):
        """Links your Discord account to your Last.fm username globally.
        Usage: .fm set YourLastfmUsername
        """
        if not self.db_params or not self.api_key:
            await lastfm_utils.send_fm_embed(self.bot, ctx, "Configuration Error", "Last.fm integration is not fully configured.", discord.Color.red())
            return

        validation_params = {"method": "user.getinfo", "user": lastfm_username}
        validation_data = await lastfm_utils.call_lastfm_api(self.http_session, self.api_key, validation_params)
        
        if not validation_data or 'user' not in validation_data:
            error_msg = validation_data.get('message', f"Could not find Last.fm user '{lastfm_username}'.") if validation_data and 'error' in validation_data else f"Could not validate Last.fm user '{lastfm_username}'."
            await lastfm_utils.send_fm_embed(self.bot, ctx, "Last.fm Username Invalid", error_msg, discord.Color.red())
            return

        success = await lastfm_utils.set_lastfm_username_in_db(self.db_params, ctx.author.id, lastfm_username, datetime.datetime.now(datetime.timezone.utc))
        if success:
            await lastfm_utils.send_fm_embed(self.bot, ctx, "Last.fm Account Set", f"Your Last.fm username has been globally set to **{lastfm_username}**.", discord.Color.green())
        else:
            await lastfm_utils.send_fm_embed(self.bot, ctx, "Database Error", "Failed to save your Last.fm username.", discord.Color.red())

    @fm_base_group.command(name="remove", aliases=["unset"])
    async def fm_remove(self, ctx: commands.Context):
        """Removes your globally linked Last.fm username."""
        if not self.db_params:
            await lastfm_utils.send_fm_embed(self.bot, ctx, "Database Error", "Database not configured.", discord.Color.red())
            return
        
        deleted_rows = await lastfm_utils.remove_lastfm_username_from_db(self.db_params, ctx.author.id)
        if deleted_rows > 0:
            await lastfm_utils.send_fm_embed(self.bot, ctx, "Last.fm Account Removed", "Your globally linked Last.fm username has been removed.", discord.Color.orange())
        else:
            await lastfm_utils.send_fm_embed(self.bot, ctx, "Last.fm Account Not Set", "You don't have a Last.fm username set with this bot.", discord.Color.blue())

    @fm_set.error
    async def fm_set_error(self, ctx, error):
        if isinstance(error, commands.MissingRequiredArgument) and error.param.name == "lastfm_username":
            await lastfm_utils.send_fm_embed(self.bot, ctx, "Missing Username", "Provide username. Usage: `.fm set YourUsername`", discord.Color.red())
        else:
            await lastfm_utils.send_fm_embed(self.bot, ctx, "Set Last.fm Error", f"Unexpected error: {error}", discord.Color.red())
            print(f"Error in fm_set: {error}"); traceback.print_exc()

async def setup(bot: commands.Bot):
    await bot.add_cog(LastFMAccount(bot))
    print("Cog 'LastFMAccount' loaded successfully.")
