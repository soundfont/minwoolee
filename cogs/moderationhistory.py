# cogs/moderationhistory.py

import os
import psycopg2
import discord
from discord.ext import commands
import time
import math
import json
from urllib.parse import urlparse
import asyncio # Added for pagination timeout

class ModerationHistory(commands.Cog):
    """
    Cog for viewing moderation actions performed BY a specific moderator.
    """
    def __init__(self, bot):
        self.bot = bot
        self.db_url = os.getenv("DATABASE_URL")
        if not self.db_url:
            # In a real scenario, handle this more gracefully, maybe disable the cog
            print("ERROR: DATABASE_URL environment variable not set. ModerationHistory cog may not function.")
            self.conn = None # Indicate DB is not available
        else:
            self.db_params = self._parse_db_url(self.db_url)
            # Test connection on init (optional, but good practice)
            try:
                conn = psycopg2.connect(**self.db_params)
                conn.close()
                print("DEBUG: ModerationHistory cog initialized, database connection successful.")
            except psycopg2.Error as e:
                print(f"ERROR: Failed to connect to database for ModerationHistory cog: {e}")
                self.conn = None # Indicate DB is not available

    def _parse_db_url(self, url):
        """ Parses the DATABASE_URL into connection parameters. """
        parsed = urlparse(url)
        return {
            "dbname": parsed.path[1:],
            "user": parsed.username,
            "password": parsed.password,
            "host": parsed.hostname,
            "port": parsed.port,
            "sslmode": "require" # Assuming Heroku-like environment
        }

    def _get_db_connection(self):
        """ Establishes and returns a database connection. """
        if not hasattr(self, 'db_params') or not self.db_params:
             raise ConnectionError("Database configuration is not available.")
        try:
            conn = psycopg2.connect(**self.db_params)
            return conn
        except psycopg2.Error as e:
            print(f"ERROR: Database connection failed: {e}")
            raise ConnectionError(f"Failed to connect to the database: {e}") # Raise specific error

    def _fetch_moderator_actions(self, guild_id, moderator_id):
        """ Fetches all actions performed by a specific moderator in a guild. """
        conn = None # Ensure conn is defined
        try:
            conn = self._get_db_connection()
            cursor = conn.cursor()
            # Query using JSONB operator ->> to extract text value of 'id'
            cursor.execute("""
                SELECT id, member_id, action, timestamp, reason
                FROM mod_logs
                WHERE guild_id = %s AND moderator ->> 'id' = %s
                ORDER BY timestamp DESC
            """, (guild_id, str(moderator_id))) # Ensure moderator_id is string for JSONB comparison
            rows = cursor.fetchall()
            cursor.close()

            actions = []
            for row in rows:
                case_id, member_id, action, timestamp, reason = row
                # Attempt to fetch the member object for better display name
                member = self.bot.get_user(member_id) or f"ID: {member_id}" # Fallback to ID
                actions.append({
                    "case_id": case_id,
                    "member": member,
                    "action": action,
                    "timestamp": timestamp,
                    "reason": reason
                })
            return actions
        except (psycopg2.Error, ConnectionError) as e:
            print(f"ERROR: Failed to fetch moderator actions: {e}")
            # Propagate the error or return empty list with error logged
            return [] # Return empty list on DB error
        finally:
            if conn:
                conn.close()

    @commands.command()
    @commands.has_permissions(manage_messages=True)
    async def moderationhistory(self, ctx, *, member: discord.Member):
        """Views moderation actions performed BY the specified staff member."""
        utils = self.bot.get_cog('Utils')
        if not utils:
            await ctx.send("Error: Utils cog not loaded. Cannot create embed.")
            return

        try:
            guild_id = ctx.guild.id
            moderator_id = member.id

            actions = self._fetch_moderator_actions(guild_id, moderator_id)

            if not actions:
                embed = utils.create_embed(ctx, title=f"Moderation History for {member.display_name}",
                                           description=f"No moderation actions found performed by {member.mention}.")
                await ctx.send(embed=embed)
                return

            actions_per_page = 5
            total_pages = math.ceil(len(actions) / actions_per_page)
            current_page = 1

            def get_page_embed(page_num):
                """ Creates an embed for the specified page number. """
                start_idx = (page_num - 1) * actions_per_page
                end_idx = start_idx + actions_per_page
                page_actions = actions[start_idx:end_idx]

                description = ""
                for action_data in page_actions:
                    try:
                        # Format timestamp using discord utils
                        formatted_timestamp = discord.utils.format_dt(int(action_data["timestamp"]), style="R")
                    except (TypeError, ValueError):
                        formatted_timestamp = "Invalid timestamp"

                    reason = action_data["reason"] if action_data["reason"] else "No reason provided"
                    target_member_display = action_data['member'].mention if isinstance(action_data['member'], discord.User) else action_data['member']

                    description += (f"**Case ID:** {action_data['case_id']} | **Action:** {action_data['action']} | "
                                    f"**Target:** {target_member_display}\n"
                                    f"**Time:** {formatted_timestamp} | **Reason:** {reason}\n\n")

                embed = utils.create_embed(ctx, title=f"Moderation Actions by {member.display_name}")
                embed.description = description.strip() or "No actions on this page."
                embed.set_footer(text=f"Page {page_num}/{total_pages} | Requested by {ctx.author.display_name}")
                return embed

            # Initial message send
            message = await ctx.send(embed=get_page_embed(current_page))

            # Add pagination reactions if more than one page
            if total_pages > 1:
                await message.add_reaction("⬅️")
                await message.add_reaction("➡️")

                def check(reaction, user):
                    return user == ctx.author and reaction.message.id == message.id and str(reaction.emoji) in ["⬅️", "➡️"]

                # Pagination loop
                while True:
                    try:
                        reaction, user = await self.bot.wait_for('reaction_add', timeout=60.0, check=check)

                        if str(reaction.emoji) == "⬅️" and current_page > 1:
                            current_page -= 1
                        elif str(reaction.emoji) == "➡️" and current_page < total_pages:
                            current_page += 1
                        else:
                            # If reaction is not valid or page doesn't change, remove reaction and continue
                            try:
                                await message.remove_reaction(reaction.emoji, user)
                            except discord.Forbidden:
                                pass # Ignore if reaction removal fails
                            continue # Skip embed update if no page change

                        # Edit message with new page embed
                        await message.edit(embed=get_page_embed(current_page))

                        # Remove the user's reaction
                        try:
                            await message.remove_reaction(reaction.emoji, user)
                        except discord.Forbidden:
                            pass # Ignore if reaction removal fails

                    except asyncio.TimeoutError:
                        # Stop listening for reactions after timeout
                        try:
                            await message.clear_reactions()
                        except discord.Forbidden:
                            pass # Ignore if clearing reactions fails
                        break
                    except discord.HTTPException as e:
                        print(f"ERROR: HTTPException during pagination: {e}")
                        break # Exit loop on HTTP error

        except discord.Forbidden:
            # Handle cases where bot lacks permissions for reactions or sending messages
            await ctx.send("I lack the necessary permissions to manage reactions or send messages.")
        except discord.HTTPException as e:
            # Handle potential Discord API errors
            await ctx.send(f"An error occurred while communicating with Discord: {e}")
        except ConnectionError as e:
             # Handle database connection errors specifically
             await ctx.send(f"Database error: {e}")
        except Exception as e:
            # Catch any other unexpected errors
            await ctx.send(f"An unexpected error occurred: {e}")
            print(f"ERROR: Unexpected error in moderationhistory command: {e}")
            traceback.print_exc() # Print traceback for debugging

    @moderationhistory.error
    async def moderationhistory_error(self, ctx, error):
        """ Error handler for the moderationhistory command. """
        if isinstance(error, commands.MissingPermissions):
            await ctx.send("You need the 'Manage Messages' permission to use this command.")
        elif isinstance(error, commands.MemberNotFound):
            await ctx.send(f"Member not found. Please provide a valid member mention or ID.")
        elif isinstance(error, commands.CommandInvokeError):
            # More specific error reporting based on the original error
            original_error = error.original
            if isinstance(original_error, ConnectionError):
                 await ctx.send(f"Database connection error: {original_error}")
            elif isinstance(original_error, discord.Forbidden):
                 await ctx.send("I lack permissions for this action (e.g., managing reactions).")
            else:
                await ctx.send("An internal error occurred while executing the command.")
                print(f"ERROR: CommandInvokeError in moderationhistory: {original_error}")
                traceback.print_exc() # Log the original error
        else:
             await ctx.send(f"An error occurred: {error}")


# Setup function to add the cog to the bot
async def setup(bot):
    await bot.add_cog(ModerationHistory(bot))