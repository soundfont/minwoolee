# cogs/moderationhistory.py (Timestamp Fix)

import os
import psycopg2
import discord
from discord.ext import commands
import time
import math
import json
from urllib.parse import urlparse
import asyncio
import traceback
import datetime # <--- IMPORT DATETIME MODULE

import psycopg2.extras

class ModerationHistory(commands.Cog):
    """
    Cog for viewing moderation actions performed BY a specific moderator.
    """
    # ... (Keep __init__, _parse_db_url, _get_db_connection, _fetch_moderator_actions the same) ...
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
                         member_display = member.display_name # Use display name as fallback if needed
                         member_mention = member.mention # Use mention if we have the user object

                    # Append data as a dictionary
                    actions.append({
                        "case_id": row['id'],
                        "member_id": member_id, # Store ID for potential later fetching
                        "member_display": str(member_display), # Ensure string
                        "member_mention": str(member_mention), # Ensure string
                        "action": row['action'],
                        "timestamp": row['timestamp'], # Keep as float/numeric from DB
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


    @commands.command(name="moderationhistory", aliases=["modhist"])
    @commands.has_permissions(manage_messages=True)
    async def moderationhistory(self, ctx, *, member: discord.Member):
        """Views moderation actions performed BY the specified staff member."""
        # ... (Keep the start of the command the same) ...
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
                """ Creates an embed for the specified page number using datetime objects. """
                start_idx = (page_num - 1) * actions_per_page
                end_idx = start_idx + actions_per_page
                start_idx = max(0, start_idx)
                end_idx = min(len(actions), end_idx)
                page_actions = actions[start_idx:end_idx]

                description = ""
                for i, action_data in enumerate(page_actions):
                    if not isinstance(action_data, dict):
                        print(f"DEBUG: Skipping invalid action_data at index {start_idx + i}. Expected dict, got {type(action_data)}: {action_data}")
                        description += f"Error processing action at index {start_idx + i} (Invalid Data Type)\n\n"
                        continue

                    case_id_str = "N/A"
                    action_str = "N/A"
                    target_mention_str = "N/A"
                    timestamp_str = "N/A"
                    reason_str = "N/A"
                    error_occurred = False
                    error_details = ""

                    try:
                        # Process Case ID, Action, Target, Reason (as before)
                        case_id_val = action_data.get("case_id")
                        case_id_str = str(case_id_val) if case_id_val is not None else "N/A"

                        action_val = action_data.get("action")
                        action_str = str(action_val) if action_val is not None else "N/A"

                        target_mention_val = action_data.get("member_mention")
                        target_mention_str = str(target_mention_val) if target_mention_val is not None else "N/A"

                        reason_val = action_data.get("reason", "No reason provided")
                        reason_str = str(reason_val) if reason_val is not None else "No reason provided"

                        # --- Process Timestamp ---
                        timestamp_val = action_data.get("timestamp")
                        if timestamp_val is not None:
                            try:
                                # 1. Convert DB timestamp (float/int) to datetime object
                                dt_object = datetime.datetime.fromtimestamp(float(timestamp_val), tz=datetime.timezone.utc)
                                # 2. Pass datetime object to format_dt
                                timestamp_str = discord.utils.format_dt(dt_object, style="R")
                            except (TypeError, ValueError, OSError) as ts_e: # Catch potential errors during conversion/formatting
                                print(f"DEBUG: Invalid timestamp value {timestamp_val} for case {case_id_str}. Error: {ts_e}")
                                timestamp_str = "Invalid time"
                        else:
                            timestamp_str = "No time recorded"
                        # --- End Timestamp Processing ---

                    except Exception as e:
                        # Catch errors during other processing steps
                        error_type = type(e).__name__
                        error_details = f" ({error_type})"
                        print(f"ERROR: Error pre-processing action_data dict: {action_data}. Error: {e}")
                        traceback.print_exc()
                        error_occurred = True

                    # Build description entry
                    if error_occurred:
                        description += f"Error processing case ID {case_id_str}{error_details}\n\n"
                    else:
                        # Combine the processed strings
                        description += (f"**Case ID:** {case_id_str} | **Action:** {action_str} | "
                                        f"**Target:** {target_mention_str}\n"
                                        f"**Time:** {timestamp_str} | **Reason:** {reason_str}\n\n")

                # Create Embed
                embed = utils.create_embed(ctx, title=f"Moderation Actions by {member.display_name}")
                embed.description = description.strip() or "No actions on this page."
                embed.set_footer(text=f"Page {page_num}/{total_pages} | Requested by {ctx.author.display_name}")
                return embed
            # --- END REVISED get_page_embed ---

            # --- Rest of the command (Initial send, Pagination Logic) ---
            # ... (Keep the rest of the moderationhistory command the same) ...
            message = await ctx.send(embed=get_page_embed(current_page))
            # ... (Keep pagination logic the same) ...


        # --- Exception Handling (Keep the same) ---
        # ... (Keep except blocks the same) ...

    # --- Error Handler (Keep the same) ---
    @moderationhistory.error
    async def moderationhistory_error(self, ctx, error):
        # ... (Keep the same) ...


# Setup function (Keep the same)
async def setup(bot):
    await bot.add_cog(ModerationHistory(bot))
