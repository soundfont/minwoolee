# cogs/moderationhistory.py (Improved Error Reporting)

import os
import psycopg2
import discord
from discord.ext import commands
import time
import math
import json
from urllib.parse import urlparse
import asyncio
import traceback # Import traceback for detailed error logging

# Added DictCursor for easier row access by column name
import psycopg2.extras

class ModerationHistory(commands.Cog):
    """
    Cog for viewing moderation actions performed BY a specific moderator.
    """
    def __init__(self, bot):
        self.bot = bot
        self.db_url = os.getenv("DATABASE_URL")
        if not self.db_url:
            print("ERROR: DATABASE_URL environment variable not set. ModerationHistory cog may not function.")
            self.db_params = None # Explicitly set db_params to None
        else:
            self.db_params = self._parse_db_url(self.db_url)
            # Test connection on init (optional, but good practice)
            conn = None # Initialize conn
            try:
                conn = psycopg2.connect(**self.db_params)
                print("DEBUG: ModerationHistory cog initialized, database connection successful.")
            except psycopg2.Error as e:
                print(f"ERROR: Failed to connect to database for ModerationHistory cog: {e}")
                self.db_params = None # Set db_params to None on connection error
            finally:
                 if conn:
                      conn.close()

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
        if not self.db_params: # Check if db_params is None or empty
             raise ConnectionError("Database configuration is not available or failed.")
        try:
            # Use DictCursor factory for easier row access
            conn = psycopg2.connect(**self.db_params)
            return conn
        except psycopg2.Error as e:
            print(f"ERROR: Database connection failed: {e}")
            raise ConnectionError(f"Failed to connect to the database: {e}") # Raise specific error

    def _fetch_moderator_actions(self, guild_id, moderator_id):
        """ Fetches all actions performed by a specific moderator in a guild. """
        conn = None # Ensure conn is defined
        actions = [] # Initialize actions list
        try:
            conn = self._get_db_connection()
            # Use DictCursor to get rows as dictionary-like objects
            cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
            # Query using JSONB operator ->> to extract text value of 'id'
            cursor.execute("""
                SELECT id, member_id, action, timestamp, reason
                FROM mod_logs
                WHERE guild_id = %s AND moderator ->> 'id' = %s
                ORDER BY timestamp DESC
            """, (guild_id, str(moderator_id))) # Ensure moderator_id is string for JSONB comparison
            rows = cursor.fetchall()
            cursor.close()

            print(f"DEBUG: Fetched {len(rows)} rows for moderator {moderator_id} in guild {guild_id}")

            for row in rows:
                try:
                    # Row is now a DictRow object, access columns by name
                    member_id = row['member_id']
                    # Attempt to fetch the member object for better display name
                    # Use get_user first (cache lookup), fallback to fetch_user (API call) if needed
                    member = self.bot.get_user(member_id)
                    if member is None:
                         # Try fetching via API if not in cache - can be slow/rate-limited
                         # member = await self.bot.fetch_user(member_id) # This needs to be async, cannot do here
                         # For sync context, just use ID as fallback
                         member_display = f"ID: {member_id}"
                         member_mention = member_display # No mention available
                    else:
                         member_display = member.mention # Use display name or name if needed
                         member_mention = member.mention # Use mention if we have the user object

                    # Append data as a dictionary
                    actions.append({
                        "case_id": row['id'],
                        "member_id": member_id, # Store ID for potential later fetching
                        "member_display": member_display, # Store display string
                        "member_mention": member_mention, # Store mention string
                        "action": row['action'],
                        "timestamp": row['timestamp'],
                        "reason": row['reason']
                    })
                except Exception as e:
                     print(f"ERROR: Failed processing row {row}: {e}")
                     # Optionally skip this row or add placeholder data
                     continue # Skip problematic row

            return actions
        except (psycopg2.Error, ConnectionError) as e:
            print(f"ERROR: Failed to fetch moderator actions: {e}")
            # Propagate the error or return empty list with error logged
            return [] # Return empty list on DB error
        finally:
            if conn:
                conn.close()

    @commands.command(name="moderationhistory", aliases=["modhist"]) # Added alias
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

            await ctx.send(f"Fetching history for moderator {member.mention}...", delete_after=5) # User feedback
            actions = self._fetch_moderator_actions(guild_id, moderator_id) # This is synchronous

            if not actions:
                embed = utils.create_embed(ctx, title=f"Moderation History by {member.display_name}",
                                           description=f"No moderation actions found performed by {member.mention}.")
                await ctx.send(embed=embed)
                return

            actions_per_page = 5
            total_pages = math.ceil(len(actions) / actions_per_page)
            current_page = 1

            # --- REVISED get_page_embed ---
            def get_page_embed(page_num):
                """ Creates an embed for the specified page number. """
                start_idx = (page_num - 1) * actions_per_page
                end_idx = start_idx + actions_per_page
                # Ensure slice indices are valid
                start_idx = max(0, start_idx)
                end_idx = min(len(actions), end_idx)
                page_actions = actions[start_idx:end_idx]

                description = ""
                for i, action_data in enumerate(page_actions):
                    # Basic check
                    if not isinstance(action_data, dict):
                        print(f"DEBUG: Skipping invalid action_data at index {start_idx + i}. Expected dict, got {type(action_data)}: {action_data}")
                        description += f"Error processing action at index {start_idx + i} (Invalid Data Type)\n\n"
                        continue # Skip this item

                    try:
                        # Safely get values using .get() with default values
                        case_id = action_data.get("case_id", "N/A")
                        action = action_data.get("action", "N/A")
                        timestamp_val = action_data.get("timestamp")
                        reason = action_data.get("reason", "No reason provided")
                        target_member_mention = action_data.get("member_mention", "N/A") # Use pre-fetched mention

                        # Format timestamp
                        if timestamp_val is not None:
                            try:
                                formatted_timestamp = discord.utils.format_dt(int(float(timestamp_val)), style="R") # Ensure it's float before int
                            except (TypeError, ValueError):
                                print(f"DEBUG: Invalid timestamp value {timestamp_val} for case {case_id}")
                                formatted_timestamp = "Invalid time"
                        else:
                            formatted_timestamp = "No time recorded"

                        # Build description entry
                        description += (f"**Case ID:** {case_id} | **Action:** {action} | "
                                        f"**Target:** {target_member_mention}\n"
                                        f"**Time:** {formatted_timestamp} | **Reason:** {reason}\n\n")

                    except Exception as e:
                        # Catch any unexpected error during processing of a specific action_data dict
                        error_type = type(e).__name__ # Get the name of the exception type
                        print(f"ERROR: Unexpected error processing action_data dict: {action_data}. Error Type: {error_type}, Message: {e}")
                        traceback.print_exc()
                        # **** MODIFIED LINE **** Include error type in the embed message
                        description += f"Error processing case ID {action_data.get('case_id', 'N/A')} ({error_type})\n\n"
                        continue # Skip to next action

                embed = utils.create_embed(ctx, title=f"Moderation Actions by {member.display_name}")
                embed.description = description.strip() or "No actions on this page."
                embed.set_footer(text=f"Page {page_num}/{total_pages} | Requested by {ctx.author.display_name}")
                return embed
            # --- END REVISED get_page_embed ---

            # Initial message send
            message = await ctx.send(embed=get_page_embed(current_page))

            # Add pagination reactions if more than one page
            if total_pages > 1:
                # Ensure bot has permissions before adding reactions
                if ctx.guild.me.permissions_in(ctx.channel).add_reactions:
                    await message.add_reaction("⬅️")
                    await message.add_reaction("➡️")
                else:
                    print("WARN: Bot lacks Add Reactions permission for pagination.")

                def check(reaction, user):
                    return user == ctx.author and reaction.message.id == message.id and str(reaction.emoji) in ["⬅️", "➡️"]

                # Pagination loop
                while True:
                    # Check if bot can still manage reactions (permissions might change)
                    can_manage_reactions = ctx.guild.me.permissions_in(ctx.channel).manage_messages

                    try:
                        reaction, user = await self.bot.wait_for('reaction_add', timeout=60.0, check=check)

                        page_changed = False
                        if str(reaction.emoji) == "⬅️" and current_page > 1:
                            current_page -= 1
                            page_changed = True
                        elif str(reaction.emoji) == "➡️" and current_page < total_pages:
                            current_page += 1
                            page_changed = True

                        if page_changed:
                            await message.edit(embed=get_page_embed(current_page))

                        # Remove the user's reaction if possible
                        if can_manage_reactions:
                             try:
                                 await message.remove_reaction(reaction.emoji, user)
                             except (discord.Forbidden, discord.NotFound): pass # Ignore if removal fails

                    except asyncio.TimeoutError:
                        # Stop listening for reactions after timeout
                        if can_manage_reactions and message: # Check message exists
                            try: await message.clear_reactions()
                            except (discord.Forbidden, discord.NotFound, discord.HTTPException): pass
                        break # Exit pagination loop
                    except discord.HTTPException as e:
                        print(f"ERROR: HTTPException during pagination: {e}")
                        break # Exit loop on HTTP error
                    except Exception as e: # Catch broader errors during wait_for/edit
                         print(f"ERROR: Unexpected error in pagination loop: {e}")
                         traceback.print_exc()
                         break


        except discord.Forbidden as e:
            await ctx.send(f"I lack permissions for this command. Error: {e.text}")
        except discord.HTTPException as e:
            await ctx.send(f"An error occurred while communicating with Discord: {e}")
        except ConnectionError as e:
             await ctx.send(f"Database error: {e}")
        except Exception as e:
            await ctx.send(f"An unexpected error occurred. Check logs for details.") # User-friendly message
            print(f"ERROR: Unexpected error in moderationhistory command: {e}")
            traceback.print_exc() # Log detailed error

    @moderationhistory.error
    async def moderationhistory_error(self, ctx, error):
        """ Error handler for the moderationhistory command. """
        if isinstance(error, commands.MissingPermissions):
            await ctx.send("You need the 'Manage Messages' permission to use this command.")
        elif isinstance(error, commands.MemberNotFound):
            await ctx.send(f"Member not found. Please provide a valid member mention or ID.")
        elif isinstance(error, commands.CommandInvokeError):
            original_error = error.original
            print(f"ERROR: CommandInvokeError in moderationhistory: {original_error}") # Log original error
            traceback.print_exc() # Print full traceback for debugging
            if isinstance(original_error, ConnectionError):
                 await ctx.send(f"Database connection error: {original_error}")
            elif isinstance(original_error, discord.Forbidden):
                 # Give more specific feedback if possible from original_error.text
                 await ctx.send(f"I lack permissions for a required action: {original_error.text}")
            else:
                # Generic message for other internal errors
                await ctx.send("An internal error occurred while executing the command. Please check the bot logs.")
        else:
             # Handle other potential errors like BadArgument etc.
             await ctx.send(f"An error occurred: {error}")


# Setup function to add the cog to the bot
async def setup(bot):
    await bot.add_cog(ModerationHistory(bot))

