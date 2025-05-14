# cogs/history.py (Revised with Timestamp Fix)

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
import datetime # <--- IMPORT DATETIME MODULE

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
            raise ConnectionError(f"Failed to connect to the database.")

    def _init_db(self):
        """ Ensures the mod_logs table exists in the database. """
        conn = None
        print("DEBUG [DB Init]: Checking/Creating mod_logs table...") # DEBUG
        try:
            conn = self._get_db_connection() 
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
            return 

        try:
            member_id = int(member_id) # Ensure member_id is an integer
            guild_id = int(guild_id)   # Ensure guild_id is an integer
            moderator_data = {
                "id": str(moderator.id), # Ensure moderator ID is a string for JSON
                "name": moderator.name,
                "mention": moderator.mention
            }
            timestamp = time.time() # This is a float (Unix timestamp)

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
            traceback.print_exc() 
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
            raise ConnectionError("Database not configured.")

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
                    if isinstance(moderator_json, str): # Handle if moderator data is a JSON string
                        moderator_data = json.loads(moderator_json)
                    else: # Assume it's already a dict (if psycopg2 handles JSONB to dict directly)
                        moderator_data = moderator_json

                    # Create a simple object-like structure for moderator for easier access
                    # This avoids errors if a moderator is no longer fetchable from Discord
                    moderator_obj = type('PseudoModerator', (), {
                        'id': int(moderator_data.get('id', 0)),
                        'name': moderator_data.get('name', 'Unknown Mod'),
                        'mention': moderator_data.get('mention', f"<@{moderator_data.get('id', 0)}>") # Fallback mention
                    })()
                    
                    actions.append({
                        "case_id": row['id'],
                        "action": row['action'],
                        "moderator": moderator_obj,
                        "timestamp": row['timestamp'], # This is a float (Unix timestamp)
                        "reason": row['reason']
                    })
                except (TypeError, KeyError, json.JSONDecodeError, ValueError) as e:
                    print(f"ERROR [Fetch Actions]: Failed processing row {i+1} ({row}): {e}")
                    traceback.print_exc()
                    continue 

            print(f"DEBUG [Fetch Actions]: Finished processing rows. Returning {len(actions)} actions.") # DEBUG
            return actions
        except (psycopg2.Error, ConnectionError) as e:
            print(f"ERROR [Fetch Actions]: Database error occurred: {e}")
            raise e
        finally:
            if conn:
                conn.close()

    @commands.group(invoke_without_command=True)
    @commands.has_permissions(manage_messages=True)
    async def history(self, ctx, member: discord.Member):
        """Views moderation history FOR a member. Use subcommands for more actions."""
        print(f"DEBUG [History Cmd]: Command invoked by {ctx.author} for member {member}") 
        utils = self.bot.get_cog('Utils')
        if not utils:
            print("ERROR [History Cmd]: Utils cog not loaded.") 
            await ctx.send("Error: Utils cog not loaded. Cannot create embed.")
            return

        bot_perms = ctx.channel.permissions_for(ctx.guild.me)
        if not bot_perms.send_messages:
            print(f"ERROR [History Cmd]: Missing 'Send Messages' permission in channel {ctx.channel.id}")
            return
        if not bot_perms.embed_links:
            print(f"WARN [History Cmd]: Missing 'Embed Links' permission in channel {ctx.channel.id}.")
            # Consider sending plain text or notifying user if embeds can't be sent.

        try:
            guild_id = ctx.guild.id
            member_id = member.id

            print(f"DEBUG [History Cmd]: Calling _fetch_member_actions...") 
            actions = self._fetch_member_actions(guild_id, member_id)
            print(f"DEBUG [History Cmd]: _fetch_member_actions returned {len(actions)} actions.")

            if not actions:
                print(f"DEBUG [History Cmd]: No actions found for member {member_id}. Sending 'No history' embed.")
                embed = utils.create_embed(ctx, title=f"Moderation History for {member.display_name}",
                                           description=f"No moderation history found for {member.mention}.")
                await ctx.send(embed=embed)
                print(f"DEBUG [History Cmd]: 'No history' embed sent.")
                return

            print(f"DEBUG [History Cmd]: Actions found. Setting up pagination...")
            actions_per_page = 5
            total_pages = math.ceil(len(actions) / actions_per_page)
            current_page = 1

            def get_page_embed(page_num):
                print(f"DEBUG [Get Page Embed]: Generating embed for page {page_num}/{total_pages}")
                start_idx = (page_num - 1) * actions_per_page
                end_idx = start_idx + actions_per_page
                page_actions = actions[start_idx:end_idx]
                print(f"DEBUG [Get Page Embed]: Actions for this page: {len(page_actions)}")

                description = ""
                for i, action_data in enumerate(page_actions):
                    if not isinstance(action_data, dict):
                        print(f"ERROR [Get Page Embed]: Item {i} is not a dict: {type(action_data)}")
                        description += f"Error processing action at index {start_idx + i} (Invalid Data Type)\n\n"
                        continue

                    try:
                        case_id = action_data.get("case_id", "N/A")
                        action_val = action_data.get("action", "N/A")
                        mod_obj = action_data.get("moderator") 
                        mod_mention = mod_obj.mention if mod_obj else "Unknown Mod"
                        ts_val = action_data.get("timestamp") # This is a float
                        reason_val = action_data.get("reason", "No reason provided")

                        formatted_timestamp = "No time" # Default
                        if ts_val is not None:
                            try:
                                # Convert float Unix timestamp to datetime object (UTC)
                                dt_object = datetime.datetime.fromtimestamp(float(ts_val), tz=datetime.timezone.utc)
                                # Format the datetime object
                                formatted_timestamp = discord.utils.format_dt(dt_object, style="R")
                            except (TypeError, ValueError, OSError) as ts_e: # Catch potential errors
                                print(f"DEBUG [Get Page Embed]: Invalid timestamp value '{ts_val}' for case {case_id}. Error: {ts_e}")
                                formatted_timestamp = "Invalid time" 
                        
                        description += (f"**Case ID:** {case_id} | **Action:** {action_val} | "
                                        f"**Moderator:** {mod_mention}\n"
                                        f"**Time:** {formatted_timestamp} | **Reason:** {reason_val}\n\n")
                    except Exception as e:
                        print(f"ERROR [Get Page Embed]: Error processing action dict {action_data}: {e}")
                        traceback.print_exc()
                        description += f"Error processing Case ID {action_data.get('case_id', 'N/A')}\n\n"
                
                embed_title = f"Moderation History for {member.display_name}"
                # Check if member object is available for display name, otherwise use ID
                if not member and member_id: # If member couldn't be fetched
                    embed_title = f"Moderation History for User ID: {member_id}"

                embed = utils.create_embed(ctx, title=embed_title)
                embed.description = description.strip() or "No actions on this page."
                embed.set_footer(text=f"Page {page_num}/{total_pages} | Requested by {ctx.author.display_name}")
                print(f"DEBUG [Get Page Embed]: Embed created for page {page_num}.")
                return embed

            print(f"DEBUG [History Cmd]: Attempting to send initial embed (Page 1)...")
            message = await ctx.send(embed=get_page_embed(current_page))
            print(f"DEBUG [History Cmd]: Initial embed sent successfully. Message ID: {message.id}")

            if total_pages > 1:
                print(f"DEBUG [History Cmd]: Total pages > 1 ({total_pages}). Adding reactions...")
                if bot_perms.add_reactions:
                    try:
                        await message.add_reaction("⬅️")
                        await message.add_reaction("➡️")
                        print(f"DEBUG [History Cmd]: Reactions added.")
                    except discord.Forbidden:
                        print(f"WARN [History Cmd]: Failed to add reactions (Forbidden).")
                    except discord.HTTPException as e:
                        print(f"WARN [History Cmd]: Failed to add reactions (HTTPException: {e}).")

                    def check(reaction, user):
                        return user == ctx.author and reaction.message.id == message.id and str(reaction.emoji) in ["⬅️", "➡️"]

                    while True:
                        can_manage_reactions = ctx.channel.permissions_for(ctx.guild.me).manage_messages
                        try:
                            print(f"DEBUG [History Cmd]: Waiting for reaction (Page {current_page})...")
                            reaction, user = await self.bot.wait_for('reaction_add', timeout=60.0, check=check)
                            print(f"DEBUG [History Cmd]: Reaction '{reaction.emoji}' received from {user}.")

                            page_changed = False
                            if str(reaction.emoji) == "⬅️" and current_page > 1:
                                current_page -= 1
                                page_changed = True
                            elif str(reaction.emoji) == "➡️" and current_page < total_pages:
                                current_page += 1
                                page_changed = True

                            if page_changed:
                                print(f"DEBUG [History Cmd]: Page changed to {current_page}. Editing message...")
                                await message.edit(embed=get_page_embed(current_page))
                                print(f"DEBUG [History Cmd]: Message edited.")

                            if can_manage_reactions:
                                try:
                                    await message.remove_reaction(reaction.emoji, user)
                                except (discord.Forbidden, discord.NotFound): pass 

                        except asyncio.TimeoutError:
                            print(f"DEBUG [History Cmd]: Pagination timed out.")
                            if can_manage_reactions and message and not message.channel.is_nsfw(): # Check message exists and channel type
                                try: 
                                    await message.clear_reactions()
                                except (discord.Forbidden, discord.NotFound, discord.HTTPException): pass
                            break 
                        except discord.HTTPException as e:
                            print(f"ERROR [History Cmd]: HTTPException during pagination loop: {e}")
                            break
                        except Exception as e:
                            print(f"ERROR [History Cmd]: Unexpected error in pagination loop: {e}")
                            traceback.print_exc()
                            break
                else:
                    print(f"WARN [History Cmd]: Pagination skipped - Missing 'Add Reactions' permission.")

        except ConnectionError as e:
            print(f"ERROR [History Cmd]: Database ConnectionError: {e}") 
            await ctx.send(f"Database error: Could not connect or query the database.")
        except psycopg2.Error as e:
            print(f"ERROR [History Cmd]: Database psycopg2.Error: {e}") 
            await ctx.send(f"Database error: An error occurred while fetching history.")
        except discord.Forbidden as e:
            print(f"ERROR [History Cmd]: Discord Forbidden error: {e.text} (Code: {e.code})") 
            if e.code != 50013: 
                await ctx.send(f"I lack permissions for this action: {e.text}")
        except discord.HTTPException as e:
            print(f"ERROR [History Cmd]: Discord HTTPException: {e.text} (Code: {e.code}, Status: {e.status})") 
            await ctx.send(f"An error occurred communicating with Discord: {e.text}")
        except Exception as e:
            print(f"ERROR [History Cmd]: Unexpected error in history command: {e}") 
            traceback.print_exc() 
            await ctx.send(f"An unexpected error occurred. Please check the bot logs.")

    # --- Subcommands (removeall, remove, view) ---
    # (Ensure these subcommands also handle ConnectionError and psycopg2.Error if they interact with the DB)

    @history.command(name="removeall")
    @commands.has_permissions(administrator=True)
    async def history_removeall(self, ctx, member: discord.Member):
        """Removes all history entries for a specific member."""
        print(f"DEBUG [History RemoveAll]: Invoked by {ctx.author} for {member}")
        utils = self.bot.get_cog('Utils')
        if not utils:
            await ctx.send("Error: Utils cog not loaded.")
            return
        if not self.db_params:
            await ctx.send("Database not configured. Cannot remove history.")
            return

        conn = None
        try:
            conn = self._get_db_connection()
            cursor = conn.cursor()
            cursor.execute("DELETE FROM mod_logs WHERE guild_id = %s AND member_id = %s", (ctx.guild.id, member.id))
            count = cursor.rowcount
            conn.commit()
            cursor.close()

            if count > 0:
                embed = utils.create_embed(ctx, title="History Cleared", description=f"Successfully removed all {count} history entries for {member.mention}.")
            else:
                embed = utils.create_embed(ctx, title="History Clear", description=f"No history entries found to remove for {member.mention}.")
            await ctx.send(embed=embed)

        except (psycopg2.Error, ConnectionError) as e:
            print(f"ERROR [History RemoveAll]: Database error: {e}")
            await ctx.send("A database error occurred while trying to remove all history entries.")
        except Exception as e:
            print(f"ERROR [History RemoveAll]: Unexpected error: {e}")
            traceback.print_exc()
            await ctx.send("An unexpected error occurred.")
        finally:
            if conn:
                conn.close()


    @history.command(name="remove")
    @commands.has_permissions(manage_messages=True) # Or a more appropriate permission like 'manage_guild' or 'administrator'
    async def history_remove(self, ctx, member: discord.Member, case_id: int):
        """Removes a specific punishment by Case ID for a member."""
        print(f"DEBUG [History Remove]: Invoked by {ctx.author} for {member}, case {case_id}")
        utils = self.bot.get_cog('Utils')
        if not utils:
            await ctx.send("Error: Utils cog not loaded.")
            return
        if not self.db_params:
            await ctx.send("Database not configured. Cannot remove history entry.")
            return
            
        conn = None
        try:
            conn = self._get_db_connection()
            cursor = conn.cursor()
            # Ensure the case_id belongs to the specified member and guild for security
            cursor.execute("DELETE FROM mod_logs WHERE id = %s AND guild_id = %s AND member_id = %s", 
                           (case_id, ctx.guild.id, member.id))
            count = cursor.rowcount
            conn.commit()
            cursor.close()

            if count > 0:
                embed = utils.create_embed(ctx, title="History Entry Removed", 
                                           description=f"Successfully removed Case ID {case_id} for {member.mention}.")
            else:
                embed = utils.create_embed(ctx, title="History Entry Not Found", 
                                           description=f"Could not find Case ID {case_id} for {member.mention}, or it does not belong to them.")
            await ctx.send(embed=embed)

        except (psycopg2.Error, ConnectionError) as e:
            print(f"ERROR [History Remove]: Database error: {e}")
            await ctx.send("A database error occurred while trying to remove the history entry.")
        except Exception as e:
            print(f"ERROR [History Remove]: Unexpected error: {e}")
            traceback.print_exc()
            await ctx.send("An unexpected error occurred.")
        finally:
            if conn:
                conn.close()


    @history.command(name="view")
    @commands.has_permissions(manage_messages=True)
    async def history_view(self, ctx, case_id: int):
        """Views the details of a specific moderation Case ID."""
        print(f"DEBUG [History View]: Invoked by {ctx.author} for case {case_id}")
        utils = self.bot.get_cog('Utils')
        if not utils:
            await ctx.send("Error: Utils cog not loaded.")
            return
        if not self.db_params:
            await ctx.send("Database not configured. Cannot view history entry.")
            return

        conn = None
        try:
            conn = self._get_db_connection()
            cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
            # Fetch specific case from the current guild
            cursor.execute("SELECT * FROM mod_logs WHERE id = %s AND guild_id = %s", (case_id, ctx.guild.id))
            action_data_row = cursor.fetchone()
            cursor.close()

            if action_data_row:
                moderator_json = action_data_row['moderator']
                if isinstance(moderator_json, str):
                    moderator_data = json.loads(moderator_json)
                else:
                    moderator_data = moderator_json
                
                mod_mention = f"<@{moderator_data.get('id', 'Unknown')}>"
                
                ts_val = action_data_row['timestamp']
                formatted_timestamp = "No time"
                if ts_val is not None:
                    try:
                        dt_object = datetime.datetime.fromtimestamp(float(ts_val), tz=datetime.timezone.utc)
                        formatted_timestamp = discord.utils.format_dt(dt_object, style="F") # Full date and time
                    except:
                        formatted_timestamp = "Invalid time"

                target_member_id = action_data_row['member_id']
                target_member = ctx.guild.get_member(target_member_id) or f"User ID: {target_member_id}"


                description = (
                    f"**Action:** {action_data_row['action']}\n"
                    f"**Target:** {target_member.mention if isinstance(target_member, discord.Member) else target_member}\n"
                    f"**Moderator:** {mod_mention}\n"
                    f"**Time:** {formatted_timestamp}\n"
                    f"**Reason:** {action_data_row.get('reason', 'No reason provided')}"
                )
                embed = utils.create_embed(ctx, title=f"Moderation Case ID: {case_id}", description=description)
            else:
                embed = utils.create_embed(ctx, title="Case Not Found", description=f"Could not find Case ID {case_id} in this server.")
            await ctx.send(embed=embed)

        except (psycopg2.Error, ConnectionError) as e:
            print(f"ERROR [History View]: Database error: {e}")
            await ctx.send("A database error occurred while trying to view the history entry.")
        except Exception as e:
            print(f"ERROR [History View]: Unexpected error: {e}")
            traceback.print_exc()
            await ctx.send("An unexpected error occurred.")
        finally:
            if conn:
                conn.close()

    # --- Error Handlers ---
    @history_removeall.error
    async def history_removeall_error(self, ctx, error):
        print(f"ERROR [History RemoveAll Handler]: {error}")
        if isinstance(error, commands.MissingPermissions):
            await ctx.send("You need 'Administrator' permission to use this command.")
        elif isinstance(error, commands.CommandInvokeError) and isinstance(error.original, (ConnectionError, psycopg2.Error)):
            await ctx.send("A database error occurred.")
        else:
            await ctx.send(f"An error occurred: {error}")
        traceback.print_exc()

    @history_remove.error
    async def history_remove_error(self, ctx, error):
        print(f"ERROR [History Remove Handler]: {error}")
        if isinstance(error, commands.MissingPermissions):
            await ctx.send("You need 'Manage Messages' permission (or higher) to use this command.")
        elif isinstance(error, commands.MemberNotFound):
            await ctx.send(f"Member not found: `{error.argument}`.")
        elif isinstance(error, commands.BadArgument):
             await ctx.send(f"Invalid case ID: `{error.argument}`. Please provide a number.")
        elif isinstance(error, commands.CommandInvokeError) and isinstance(error.original, (ConnectionError, psycopg2.Error)):
            await ctx.send("A database error occurred.")
        else:
            await ctx.send(f"An error occurred: {error}")
        traceback.print_exc()

    @history_view.error
    async def history_view_error(self, ctx, error):
        print(f"ERROR [History View Handler]: {error}")
        if isinstance(error, commands.MissingPermissions):
            await ctx.send("You need 'Manage Messages' permission to use this command.")
        elif isinstance(error, commands.BadArgument):
             await ctx.send(f"Invalid case ID: `{error.argument}`. Please provide a number.")
        elif isinstance(error, commands.CommandInvokeError) and isinstance(error.original, (ConnectionError, psycopg2.Error)):
            await ctx.send("A database error occurred.")
        else:
            await ctx.send(f"An error occurred: {error}")
        traceback.print_exc()

    @history.error
    async def history_base_error(self, ctx, error):
        print(f"ERROR [History Base Handler]: Caught error: {error}")
        traceback.print_exc()
        if isinstance(error, commands.MissingPermissions):
            await ctx.send("You need 'Manage Messages' permission to use this command.")
        elif isinstance(error, commands.MemberNotFound):
            await ctx.send(f"Member not found: `{error.argument}`. Please provide a valid member.")
        elif isinstance(error, commands.CommandInvokeError):
            original = error.original
            print(f"ERROR [History Base Handler]: Original error: {original}")
            if isinstance(original, ConnectionError):
                await ctx.send(f"Database error: {original}")
            elif isinstance(original, discord.Forbidden):
                await ctx.send(f"Permissions error: {original.text}")
            else:
                await ctx.send("An internal error occurred while executing the history command.")
        else:
            await ctx.send(f"An error occurred: {error}")


async def setup(bot):
    print("DEBUG [History Setup]: Setting up History cog...")
    # Ensure datetime is imported if not already at the top of the file
    # import datetime 
    await bot.add_cog(History(bot))
    print("DEBUG [History Setup]: History cog added.")

