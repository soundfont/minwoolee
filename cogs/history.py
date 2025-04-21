# cogs/history.py (Revised with Debugging)

import os
import psycopg2
from discord.ext import commands
import discord
import time
import math
import json
from urllib.parse import urlparse
import asyncio
import traceback # For detailed error logging

# Added DictCursor for easier row access by column name
import psycopg2.extras

class History(commands.Cog):
    """
    Cog for managing and viewing moderation history for members.
    Includes subcommands for removing and viewing specific cases.
    """
    def __init__(self, bot):
        self.bot = bot
        self.db_url = os.getenv("DATABASE_URL")
        print("DEBUG [History Init]: Initializing History Cog...") # DEBUG
        if not self.db_url:
            print("ERROR [History Init]: DATABASE_URL environment variable not set. History cog may not function.")
            self.db_params = None
        else:
            self.db_params = self._parse_db_url(self.db_url)
            # Test connection more robustly
            conn = None
            try:
                print("DEBUG [History Init]: Attempting initial DB connection test...") # DEBUG
                conn = psycopg2.connect(**self.db_params)
                conn.close()
                print("DEBUG [History Init]: Initial DB connection test successful.") # DEBUG
                self._init_db() # Ensure table exists only if connection is possible
            except psycopg2.Error as e:
                print(f"ERROR [History Init]: Initial DB connection failed: {e}")
                self.db_params = None # Disable DB functions if initial connection fails

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
        """ Establishes and returns a database connection. Raises ConnectionError on failure. """
        print("DEBUG [DB Connect]: Attempting to get DB connection...") # DEBUG
        if not self.db_params:
             print("ERROR [DB Connect]: DB params not configured.") # DEBUG
             raise ConnectionError("Database configuration is not available or failed.")
        try:
            conn = psycopg2.connect(**self.db_params)
            print("DEBUG [DB Connect]: Connection successful.") # DEBUG
            return conn
        except psycopg2.Error as e:
            print(f"ERROR [DB Connect]: Database connection failed: {e}") # DEBUG
            # Raise a specific error to be caught by command handlers
            raise ConnectionError(f"Failed to connect to the database.")

    def _init_db(self):
        """ Ensures the mod_logs table exists in the database. """
        conn = None
        print("DEBUG [DB Init]: Checking/Creating mod_logs table...") # DEBUG
        try:
            conn = self._get_db_connection() # Uses the robust connection getter
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS mod_logs (
                    id SERIAL PRIMARY KEY,
                    guild_id BIGINT NOT NULL,
                    member_id BIGINT NOT NULL,
                    action TEXT NOT NULL,
                    moderator JSONB NOT NULL,
                    timestamp DOUBLE PRECISION NOT NULL,
                    reason TEXT
                )
            """)
            conn.commit()
            cursor.close()
            print("DEBUG [DB Init]: mod_logs table checked/created successfully.") # DEBUG
        except (psycopg2.Error, ConnectionError) as e:
            # Log error, but allow cog to load. Commands will fail later if DB needed.
            print(f"ERROR [DB Init]: Database table initialization failed: {e}")
        finally:
            if conn:
                conn.close()

    def log_action(self, guild_id, member_id, action, moderator, reason=None):
        """ Logs a moderation action to the database. """
        conn = None
        print(f"DEBUG [Log Action]: Attempting to log action '{action}' for member {member_id} in guild {guild_id}") # DEBUG
        if not self.db_params:
             print("ERROR [Log Action]: Cannot log action, DB not configured.") # DEBUG
             return # Exit if DB isn't configured

        try:
            member_id = int(member_id)
            guild_id = int(guild_id)
            moderator_data = {
                "id": str(moderator.id),
                "name": moderator.name,
                "mention": moderator.mention
            }
            timestamp = time.time()

            conn = self._get_db_connection()
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO mod_logs (guild_id, member_id, action, moderator, timestamp, reason)
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (guild_id, member_id, action, json.dumps(moderator_data), timestamp, reason))
            conn.commit()
            cursor.close()
            print(f"DEBUG [Log Action]: Action logged successfully.") # DEBUG
        except (psycopg2.Error, ConnectionError, TypeError, ValueError) as e:
             print(f"ERROR [Log Action]: Failed to log action: {e}")
             traceback.print_exc() # Print full traceback for logging failure
        finally:
            if conn:
                conn.close()

    def _fetch_member_actions(self, guild_id, member_id):
        """ Fetches all moderation actions against a specific member. """
        conn = None
        actions = []
        print(f"DEBUG [Fetch Actions]: Fetching actions for member {member_id} in guild {guild_id}") # DEBUG
        if not self.db_params:
             print("ERROR [Fetch Actions]: Cannot fetch actions, DB not configured.") # DEBUG
             raise ConnectionError("Database not configured.") # Raise error to inform command

        try:
            conn = self._get_db_connection()
            cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
            print(f"DEBUG [Fetch Actions]: Executing DB query...") # DEBUG
            cursor.execute("""
                SELECT id, action, moderator, timestamp, reason
                FROM mod_logs
                WHERE guild_id = %s AND member_id = %s
                ORDER BY timestamp DESC
            """, (guild_id, member_id))
            rows = cursor.fetchall()
            cursor.close()
            print(f"DEBUG [Fetch Actions]: Query returned {len(rows)} rows.") # DEBUG

            for i, row in enumerate(rows):
                print(f"DEBUG [Fetch Actions]: Processing row {i+1}...") # DEBUG
                try:
                    moderator_json = row['moderator']
                    if isinstance(moderator_json, str):
                        moderator_data = json.loads(moderator_json)
                    else:
                         moderator_data = moderator_json

                    moderator_obj = type('PseudoModerator', (), {
                        'id': int(moderator_data.get('id', 0)),
                        'name': moderator_data.get('name', 'Unknown'),
                        'mention': moderator_data.get('mention', 'Unknown')
                    })()

                    actions.append({
                        "case_id": row['id'],
                        "action": row['action'],
                        "moderator": moderator_obj,
                        "timestamp": row['timestamp'],
                        "reason": row['reason']
                    })
                except (TypeError, KeyError, json.JSONDecodeError, ValueError) as e:
                    print(f"ERROR [Fetch Actions]: Failed processing row {i+1} ({row}): {e}")
                    continue # Skip problematic row

            print(f"DEBUG [Fetch Actions]: Finished processing rows. Returning {len(actions)} actions.") # DEBUG
            return actions
        except (psycopg2.Error, ConnectionError) as e:
            print(f"ERROR [Fetch Actions]: Database error occurred: {e}")
            # Re-raise the specific error to be handled by the command
            raise e
        finally:
            if conn:
                conn.close()

    # --- Command Group Definition ---
    @commands.group(invoke_without_command=True)
    @commands.has_permissions(manage_messages=True)
    async def history(self, ctx, member: discord.Member):
        """Views moderation history FOR a member. Use subcommands for more actions."""
        print(f"DEBUG [History Cmd]: Command invoked by {ctx.author} for member {member}") # DEBUG
        utils = self.bot.get_cog('Utils')
        if not utils:
            print("ERROR [History Cmd]: Utils cog not loaded.") # DEBUG
            await ctx.send("Error: Utils cog not loaded.")
            return

        # --- Explicit Permission Check ---
        bot_perms = ctx.channel.permissions_for(ctx.guild.me)
        if not bot_perms.send_messages:
            print(f"ERROR [History Cmd]: Missing 'Send Messages' permission in channel {ctx.channel.id}") # DEBUG
            # Cannot send error message if missing send_messages perm, just log and return
            return
        if not bot_perms.embed_links:
            print(f"WARN [History Cmd]: Missing 'Embed Links' permission in channel {ctx.channel.id}. Sending plain text.") # DEBUG
            # We can still proceed but embeds won't work - maybe send plain text later?

        try:
            guild_id = ctx.guild.id
            member_id = member.id

            print(f"DEBUG [History Cmd]: Calling _fetch_member_actions...") # DEBUG
            actions = self._fetch_member_actions(guild_id, member_id)
            print(f"DEBUG [History Cmd]: _fetch_member_actions returned {len(actions)} actions.") # DEBUG

            if not actions:
                print(f"DEBUG [History Cmd]: No actions found for member {member_id}. Sending 'No history' embed.") # DEBUG
                embed = utils.create_embed(ctx, title=f"Moderation History for {member.display_name}",
                                           description=f"No moderation history found for {member.mention}.")
                await ctx.send(embed=embed)
                print(f"DEBUG [History Cmd]: 'No history' embed sent.") # DEBUG
                return

            # --- Actions Found - Proceed with Pagination ---
            print(f"DEBUG [History Cmd]: Actions found. Setting up pagination...") # DEBUG
            actions_per_page = 5
            total_pages = math.ceil(len(actions) / actions_per_page)
            current_page = 1

            # --- Revised get_page_embed (Simplified Debugging) ---
            def get_page_embed(page_num):
                print(f"DEBUG [Get Page Embed]: Generating embed for page {page_num}/{total_pages}") # DEBUG
                start_idx = (page_num - 1) * actions_per_page
                end_idx = start_idx + actions_per_page
                page_actions = actions[start_idx:end_idx]
                print(f"DEBUG [Get Page Embed]: Actions for this page: {len(page_actions)}") # DEBUG

                description = ""
                for i, action_data in enumerate(page_actions):
                     # Basic check - already done more thoroughly in previous revision
                    if not isinstance(action_data, dict):
                         print(f"ERROR [Get Page Embed]: Item {i} is not a dict: {type(action_data)}")
                         continue

                    try:
                        case_id = action_data.get("case_id", "N/A")
                        action_val = action_data.get("action", "N/A")
                        mod_obj = action_data.get("moderator")
                        mod_mention = mod_obj.mention if mod_obj else "Unknown Mod"
                        ts_val = action_data.get("timestamp")
                        reason_val = action_data.get("reason", "No reason provided")

                        if ts_val:
                             try: formatted_timestamp = discord.utils.format_dt(int(ts_val), style="R")
                             except: formatted_timestamp = "Invalid time"
                        else: formatted_timestamp = "No time"

                        description += (f"**Case ID:** {case_id} | **Action:** {action_val} | "
                                        f"**Moderator:** {mod_mention}\n"
                                        f"**Time:** {formatted_timestamp} | **Reason:** {reason_val}\n\n")
                    except Exception as e:
                         print(f"ERROR [Get Page Embed]: Error processing action dict {action_data}: {e}")
                         description += f"Error processing Case ID {action_data.get('case_id', 'N/A')}\n\n"


                embed = utils.create_embed(ctx, title=f"Moderation History for {member.display_name}")
                embed.description = description.strip() or "No actions on this page."
                embed.set_footer(text=f"Page {page_num}/{total_pages} | Requested by {ctx.author.display_name}")
                print(f"DEBUG [Get Page Embed]: Embed created for page {page_num}.") # DEBUG
                return embed
            # --- END Revised get_page_embed ---

            print(f"DEBUG [History Cmd]: Attempting to send initial embed (Page 1)...") # DEBUG
            message = await ctx.send(embed=get_page_embed(current_page))
            print(f"DEBUG [History Cmd]: Initial embed sent successfully. Message ID: {message.id}") # DEBUG

            # --- Pagination Logic ---
            if total_pages > 1:
                print(f"DEBUG [History Cmd]: Total pages > 1 ({total_pages}). Adding reactions...") # DEBUG
                # Check permissions before adding reactions
                if bot_perms.add_reactions:
                    try:
                        await message.add_reaction("⬅️")
                        await message.add_reaction("➡️")
                        print(f"DEBUG [History Cmd]: Reactions added.") # DEBUG
                    except discord.Forbidden:
                         print(f"WARN [History Cmd]: Failed to add reactions (Forbidden).")
                    except discord.HTTPException as e:
                         print(f"WARN [History Cmd]: Failed to add reactions (HTTPException: {e}).")

                    def check(reaction, user):
                        return user == ctx.author and reaction.message.id == message.id and str(reaction.emoji) in ["⬅️", "➡️"]

                    while True:
                        can_manage_reactions = ctx.channel.permissions_for(ctx.guild.me).manage_messages
                        try:
                            print(f"DEBUG [History Cmd]: Waiting for reaction (Page {current_page})...") # DEBUG
                            reaction, user = await self.bot.wait_for('reaction_add', timeout=60.0, check=check)
                            print(f"DEBUG [History Cmd]: Reaction '{reaction.emoji}' received from {user}.") # DEBUG

                            page_changed = False
                            if str(reaction.emoji) == "⬅️" and current_page > 1:
                                current_page -= 1
                                page_changed = True
                            elif str(reaction.emoji) == "➡️" and current_page < total_pages:
                                current_page += 1
                                page_changed = True

                            if page_changed:
                                print(f"DEBUG [History Cmd]: Page changed to {current_page}. Editing message...") # DEBUG
                                await message.edit(embed=get_page_embed(current_page))
                                print(f"DEBUG [History Cmd]: Message edited.") # DEBUG

                            # Remove reaction
                            if can_manage_reactions:
                                try:
                                    await message.remove_reaction(reaction.emoji, user)
                                except (discord.Forbidden, discord.NotFound): pass # Ignore if removal fails

                        except asyncio.TimeoutError:
                            print(f"DEBUG [History Cmd]: Pagination timed out.") # DEBUG
                            if can_manage_reactions and message: # Check if message still exists
                                try: await message.clear_reactions()
                                except (discord.Forbidden, discord.NotFound, discord.HTTPException): pass
                            break # Exit loop
                        except discord.HTTPException as e:
                            print(f"ERROR [History Cmd]: HTTPException during pagination loop: {e}")
                            break
                        except Exception as e:
                             print(f"ERROR [History Cmd]: Unexpected error in pagination loop: {e}")
                             traceback.print_exc()
                             break
                else:
                     print(f"WARN [History Cmd]: Pagination skipped - Missing 'Add Reactions' permission.")

        # --- Exception Handling for Main Command ---
        except ConnectionError as e:
             print(f"ERROR [History Cmd]: Database ConnectionError: {e}") # DEBUG
             await ctx.send(f"Database error: Could not connect or query the database.")
        except psycopg2.Error as e:
             print(f"ERROR [History Cmd]: Database psycopg2.Error: {e}") # DEBUG
             await ctx.send(f"Database error: An error occurred while fetching history.")
        except discord.Forbidden as e:
            # This might catch permission errors during send/edit/reaction management
            print(f"ERROR [History Cmd]: Discord Forbidden error: {e.text} (Code: {e.code})") # DEBUG
            # Avoid sending if initial Send Messages failed
            if e.code != 50013: # 50013 is Missing Permissions for Send Messages
                 await ctx.send(f"I lack permissions for this action: {e.text}")
        except discord.HTTPException as e:
            print(f"ERROR [History Cmd]: Discord HTTPException: {e.text} (Code: {e.code}, Status: {e.status})") # DEBUG
            await ctx.send(f"An error occurred communicating with Discord: {e.text}")
        except Exception as e:
            print(f"ERROR [History Cmd]: Unexpected error in history command: {e}") # DEBUG
            traceback.print_exc() # Log the full traceback
            await ctx.send(f"An unexpected error occurred. Please check the bot logs.")

    # --- Subcommands (removeall, remove, view) ---
    # Keep the subcommand implementations from the previous revision.
    # Add similar DEBUG print statements within them if needed.

    @history.command(name="removeall")
    @commands.has_permissions(administrator=True)
    async def history_removeall(self, ctx, member: discord.Member):
        """Removes all history entries for a specific member."""
        # ... (Implementation from previous revision - add DEBUG prints) ...
        print(f"DEBUG [History RemoveAll]: Invoked by {ctx.author} for {member}")
        # ... rest of the code ...

    @history.command(name="remove")
    @commands.has_permissions(manage_messages=True)
    async def history_remove(self, ctx, member: discord.Member, case_id: int):
        """Removes a specific punishment by Case ID for a member."""
        # ... (Implementation from previous revision - add DEBUG prints) ...
        print(f"DEBUG [History Remove]: Invoked by {ctx.author} for {member}, case {case_id}")
        # ... rest of the code ...

    @history.command(name="view")
    @commands.has_permissions(manage_messages=True)
    async def history_view(self, ctx, case_id: int):
        """Views the details of a specific moderation Case ID."""
        # ... (Implementation from previous revision - add DEBUG prints) ...
        print(f"DEBUG [History View]: Invoked by {ctx.author} for case {case_id}")
        # ... rest of the code ...


    # --- Error Handlers ---
    # Keep error handlers from previous revision, maybe add more logging.

    @history_removeall.error
    async def history_removeall_error(self, ctx, error):
        print(f"ERROR [History RemoveAll Handler]: {error}")
        traceback.print_exc()
        # ... (rest of handler from previous revision) ...

    @history_remove.error
    async def history_remove_error(self, ctx, error):
        print(f"ERROR [History Remove Handler]: {error}")
        traceback.print_exc()
        # ... (rest of handler from previous revision) ...

    @history_view.error
    async def history_view_error(self, ctx, error):
        print(f"ERROR [History View Handler]: {error}")
        traceback.print_exc()
        # ... (rest of handler from previous revision) ...

    @history.error
    async def history_base_error(self, ctx, error):
        # Handles errors for the base `.history <member>` command if not caught by main try/except
        print(f"ERROR [History Base Handler]: Caught error: {error}")
        traceback.print_exc()
        if isinstance(error, commands.MissingPermissions):
             await ctx.send("You need 'Manage Messages' permission to use this command.")
        elif isinstance(error, commands.MemberNotFound):
             await ctx.send("Member not found. Please provide a valid member.")
        elif isinstance(error, commands.CommandInvokeError):
             original = error.original
             print(f"ERROR [History Base Handler]: Original error: {original}") # Log original
             # Handle specific original errors if needed
             if isinstance(original, ConnectionError):
                  await ctx.send(f"Database error: {original}")
             elif isinstance(original, discord.Forbidden):
                  await ctx.send(f"Permissions error: {original.text}")
             else:
                  await ctx.send("An internal error occurred while executing the history command.")
        else:
             # Catch other potential errors like BadArgument if member parsing fails etc.
             await ctx.send(f"An error occurred: {error}")


# Setup function to add the cog to the bot
async def setup(bot):
    # Make sure to import DictCursor if used (already imported above)
    # import psycopg2.extras
    print("DEBUG [History Setup]: Setting up History cog...") # DEBUG
    await bot.add_cog(History(bot))
    print("DEBUG [History Setup]: History cog added.") # DEBUG
