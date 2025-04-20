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

class History(commands.Cog):
    """
    Cog for managing and viewing moderation history for members.
    Includes subcommands for removing and viewing specific cases.
    """
    def __init__(self, bot):
        self.bot = bot
        self.db_url = os.getenv("DATABASE_URL")
        if not self.db_url:
            print("ERROR: DATABASE_URL environment variable not set. History cog may not function.")
            self.conn = None
        else:
            self.db_params = self._parse_db_url(self.db_url)
            self._init_db() # Ensure table exists
            print("DEBUG: History cog initialized, Postgres database checked/set up.")

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
            raise ConnectionError(f"Failed to connect to the database: {e}")

    def _init_db(self):
        """ Ensures the mod_logs table exists in the database. """
        conn = None
        try:
            conn = self._get_db_connection()
            cursor = conn.cursor()
            # Create table if it doesn't exist
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
            print("DEBUG: mod_logs table checked/created successfully.")
        except (psycopg2.Error, ConnectionError) as e:
            print(f"ERROR: Database initialization failed: {e}")
            # Depending on severity, might want to raise or disable cog
        finally:
            if conn:
                conn.close()

    def log_action(self, guild_id, member_id, action, moderator, reason=None):
        """ Logs a moderation action to the database. """
        conn = None
        try:
            # Ensure IDs are integers
            member_id = int(member_id)
            guild_id = int(guild_id)

            # Prepare moderator data as JSON
            moderator_data = {
                "id": str(moderator.id), # Store moderator ID as string in JSON
                "name": moderator.name,
                "mention": moderator.mention
            }
            # psycopg2 can automatically handle dict -> jsonb conversion
            # moderator_json = json.dumps(moderator_data) # No longer needed if column is JSONB

            timestamp = time.time()

            print(f"DEBUG: Logging action to Postgres - Guild: {guild_id}, Member: {member_id}, Action: {action}")

            conn = self._get_db_connection()
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO mod_logs (guild_id, member_id, action, moderator, timestamp, reason)
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (guild_id, member_id, action, json.dumps(moderator_data), timestamp, reason)) # Pass dict directly if using jsonb, else dumps
            conn.commit()
            cursor.close()

            print(f"DEBUG: Action logged to Postgres: {action} for member {member_id} in guild {guild_id}")
        except (psycopg2.Error, ConnectionError, TypeError, ValueError) as e:
             print(f"ERROR: Failed to log action: {e}")
             # Consider notifying admin or logging failure more formally
        finally:
            if conn:
                conn.close()

    def _fetch_member_actions(self, guild_id, member_id):
        """ Fetches all moderation actions against a specific member. """
        conn = None
        try:
            conn = self._get_db_connection()
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, action, moderator, timestamp, reason
                FROM mod_logs
                WHERE guild_id = %s AND member_id = %s
                ORDER BY timestamp DESC
            """, (guild_id, member_id))
            rows = cursor.fetchall()
            cursor.close()

            actions = []
            for row in rows:
                case_id, action, moderator_json, timestamp, reason = row
                try:
                    # Moderator data is already stored as JSONB (or JSON text)
                    # psycopg2 might return it as dict if JSONB, or str if JSON
                    if isinstance(moderator_json, str):
                        moderator_data = json.loads(moderator_json)
                    else: # Assume it's already a dict (psycopg2 handles JSONB nicely)
                         moderator_data = moderator_json

                    # Create a pseudo-object for moderator info for consistency
                    moderator_obj = type('PseudoModerator', (), {
                        'id': int(moderator_data.get('id', 0)), # Handle potential missing keys
                        'name': moderator_data.get('name', 'Unknown'),
                        'mention': moderator_data.get('mention', 'Unknown')
                    })()

                    actions.append({
                        "case_id": case_id,
                        "action": action,
                        "moderator": moderator_obj,
                        "timestamp": timestamp,
                        "reason": reason
                    })
                except (TypeError, KeyError, json.JSONDecodeError) as e:
                    print(f"DEBUG: Failed to process moderator data for case {case_id}: {moderator_json}, error: {e}")
                    # Append with placeholder or skip? Skipping for now.
                    continue

            print(f"DEBUG: Fetched actions for member {member_id} in guild {guild_id} (count: {len(actions)})")
            return actions
        except (psycopg2.Error, ConnectionError) as e:
            print(f"ERROR: Failed to fetch member actions: {e}")
            return [] # Return empty list on error
        finally:
            if conn:
                conn.close()

    # --- Command Group Definition ---
    @commands.group(invoke_without_command=True)
    @commands.has_permissions(manage_messages=True)
    async def history(self, ctx, member: discord.Member):
        """Views moderation history FOR a member. Use subcommands for more actions."""
        # This function now handles the default `.history <member>` invocation
        utils = self.bot.get_cog('Utils')
        if not utils:
            await ctx.send("Error: Utils cog not loaded.")
            return

        try:
            guild_id = ctx.guild.id
            member_id = member.id

            actions = self._fetch_member_actions(guild_id, member_id)

            if not actions:
                embed = utils.create_embed(ctx, title=f"Moderation History for {member.display_name}",
                                           description=f"No moderation history found for {member.mention}.")
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
                        formatted_timestamp = discord.utils.format_dt(int(action_data["timestamp"]), style="R")
                    except (TypeError, ValueError) as e:
                        formatted_timestamp = "Invalid timestamp"
                        print(f"DEBUG: Invalid timestamp in action data: {action_data}, error: {e}")

                    reason = action_data["reason"] if action_data["reason"] else "No reason provided"
                    # Use moderator object's mention attribute
                    moderator_mention = action_data['moderator'].mention

                    description += (f"**Case ID:** {action_data['case_id']} | **Action:** {action_data['action']} | "
                                    f"**Moderator:** {moderator_mention}\n"
                                    f"**Time:** {formatted_timestamp} | **Reason:** {reason}\n\n")

                embed = utils.create_embed(ctx, title=f"Moderation History for {member.display_name}")
                embed.description = description.strip() or "No actions on this page."
                embed.set_footer(text=f"Page {page_num}/{total_pages} | Requested by {ctx.author.display_name}")
                return embed

            # Send initial message
            message = await ctx.send(embed=get_page_embed(current_page))

            # Add pagination if needed
            if total_pages > 1:
                await message.add_reaction("⬅️")
                await message.add_reaction("➡️")

                def check(reaction, user):
                    return user == ctx.author and reaction.message.id == message.id and str(reaction.emoji) in ["⬅️", "➡️"]

                while True:
                    try:
                        reaction, user = await self.bot.wait_for('reaction_add', timeout=60.0, check=check)
                        if str(reaction.emoji) == "⬅️" and current_page > 1:
                            current_page -= 1
                        elif str(reaction.emoji) == "➡️" and current_page < total_pages:
                            current_page += 1
                        else:
                            try:
                                await message.remove_reaction(reaction.emoji, user)
                            except discord.Forbidden: pass
                            continue

                        await message.edit(embed=get_page_embed(current_page))
                        try:
                            await message.remove_reaction(reaction.emoji, user)
                        except discord.Forbidden: pass
                    except asyncio.TimeoutError:
                        try: await message.clear_reactions()
                        except discord.Forbidden: pass
                        break
                    except discord.HTTPException as e:
                        print(f"ERROR: HTTPException during pagination: {e}")
                        break

        except discord.Forbidden:
            await ctx.send("I lack permissions to manage reactions or send messages.")
        except discord.HTTPException as e:
            await ctx.send(f"An error occurred communicating with Discord: {e}")
        except ConnectionError as e:
             await ctx.send(f"Database error: {e}")
        except Exception as e:
            await ctx.send(f"An unexpected error occurred: {e}")
            print(f"ERROR: Unexpected error in history command: {e}")
            traceback.print_exc()

    # --- Subcommand: history removeall ---
    @history.command(name="removeall")
    @commands.has_permissions(administrator=True)
    async def history_removeall(self, ctx, member: discord.Member):
        """Removes all history entries for a specific member."""
        utils = self.bot.get_cog('Utils')
        if not utils:
            await ctx.send("Error: Utils cog not loaded.")
            return

        conn = None
        try:
            guild_id = ctx.guild.id
            member_id = member.id

            # Confirmation step (optional but recommended)
            confirm_msg = await ctx.send(f"Are you sure you want to delete **ALL** history entries for {member.mention}? React with ✅ to confirm or ❌ to cancel.")
            await confirm_msg.add_reaction("✅")
            await confirm_msg.add_reaction("❌")

            def confirm_check(reaction, user):
                return user == ctx.author and reaction.message.id == confirm_msg.id and str(reaction.emoji) in ["✅", "❌"]

            try:
                reaction, user = await self.bot.wait_for('reaction_add', timeout=30.0, check=confirm_check)
                if str(reaction.emoji) == "❌":
                    await confirm_msg.edit(content="Action cancelled.", delete_after=10)
                    try: await confirm_msg.clear_reactions()
                    except discord.Forbidden: pass
                    return
                # Proceed if ✅
                await confirm_msg.edit(content="Confirmed. Deleting entries...", delete_after=5)

            except asyncio.TimeoutError:
                await confirm_msg.edit(content="Confirmation timed out. Action cancelled.", delete_after=10)
                try: await confirm_msg.clear_reactions()
                except discord.Forbidden: pass
                return

            # Perform deletion
            conn = self._get_db_connection()
            cursor = conn.cursor()
            cursor.execute("""
                DELETE FROM mod_logs
                WHERE guild_id = %s AND member_id = %s
            """, (guild_id, member_id))
            deleted_count = cursor.rowcount # Get number of deleted rows
            conn.commit()
            cursor.close()

            embed = utils.create_embed(ctx, title="History Cleared",
                                       description=f"Successfully removed {deleted_count} history entries for {member.mention}.")
            await ctx.send(embed=embed)
            print(f"DEBUG: Cleared {deleted_count} history entries for member {member_id} in guild {guild_id} by {ctx.author}")

        except discord.Forbidden:
            await ctx.send("I lack permissions to manage reactions or send messages.")
        except discord.HTTPException as e:
            await ctx.send(f"An error occurred communicating with Discord: {e}")
        except ConnectionError as e:
             await ctx.send(f"Database error: {e}")
        except Exception as e:
            await ctx.send(f"An unexpected error occurred: {e}")
            print(f"ERROR: Unexpected error in history removeall: {e}")
            traceback.print_exc()
        finally:
            if conn:
                conn.close()

    # --- Subcommand: history remove ---
    @history.command(name="remove")
    @commands.has_permissions(manage_messages=True)
    async def history_remove(self, ctx, member: discord.Member, case_id: int):
        """Removes a specific punishment by Case ID for a member."""
        utils = self.bot.get_cog('Utils')
        if not utils:
            await ctx.send("Error: Utils cog not loaded.")
            return

        conn = None
        try:
            guild_id = ctx.guild.id
            member_id = member.id

            conn = self._get_db_connection()
            cursor = conn.cursor()
            # Ensure the case belongs to the specified member in the guild before deleting
            cursor.execute("""
                DELETE FROM mod_logs
                WHERE id = %s AND member_id = %s AND guild_id = %s
            """, (case_id, member_id, guild_id))
            deleted_count = cursor.rowcount
            conn.commit()
            cursor.close()

            if deleted_count > 0:
                embed = utils.create_embed(ctx, title="History Entry Removed",
                                           description=f"Successfully removed Case ID `{case_id}` for {member.mention}.")
                await ctx.send(embed=embed)
                print(f"DEBUG: Removed Case ID {case_id} for member {member_id} in guild {guild_id} by {ctx.author}")
            else:
                embed = utils.create_embed(ctx, title="Error", color=discord.Color.red(),
                                           description=f"Could not find Case ID `{case_id}` associated with {member.mention} in this server.")
                await ctx.send(embed=embed)

        except discord.Forbidden:
            await ctx.send("I lack permissions to send messages.")
        except discord.HTTPException as e:
            await ctx.send(f"An error occurred communicating with Discord: {e}")
        except ConnectionError as e:
             await ctx.send(f"Database error: {e}")
        except Exception as e:
            await ctx.send(f"An unexpected error occurred: {e}")
            print(f"ERROR: Unexpected error in history remove: {e}")
            traceback.print_exc()
        finally:
            if conn:
                conn.close()

    # --- Subcommand: history view ---
    @history.command(name="view")
    @commands.has_permissions(manage_messages=True)
    async def history_view(self, ctx, case_id: int):
        """Views the details of a specific moderation Case ID."""
        utils = self.bot.get_cog('Utils')
        if not utils:
            await ctx.send("Error: Utils cog not loaded.")
            return

        conn = None
        try:
            guild_id = ctx.guild.id

            conn = self._get_db_connection()
            cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor) # Use DictCursor for easy column access
            cursor.execute("""
                SELECT id, member_id, action, moderator, timestamp, reason
                FROM mod_logs
                WHERE id = %s AND guild_id = %s
            """, (case_id, guild_id))
            log_entry = cursor.fetchone()
            cursor.close()

            if log_entry:
                # Process the fetched data
                member = await self.bot.fetch_user(log_entry['member_id']) # Fetch user for up-to-date info
                member_mention = member.mention if member else f"ID: {log_entry['member_id']}"

                moderator_data = log_entry['moderator'] # Already a dict if JSONB
                moderator = await self.bot.fetch_user(int(moderator_data.get('id', 0)))
                moderator_mention = moderator.mention if moderator else moderator_data.get('name', 'Unknown')

                try:
                    formatted_timestamp = discord.utils.format_dt(int(log_entry['timestamp']), style="F") # Full date/time
                    relative_timestamp = discord.utils.format_dt(int(log_entry['timestamp']), style="R") # Relative time
                except (TypeError, ValueError):
                    formatted_timestamp = "Invalid timestamp"
                    relative_timestamp = ""

                reason = log_entry['reason'] if log_entry['reason'] else "No reason provided"

                # Create embed
                embed = utils.create_embed(ctx, title=f"Moderation Case Details: ID {log_entry['id']}")
                embed.add_field(name="Member", value=member_mention, inline=True)
                embed.add_field(name="Action", value=log_entry['action'], inline=True)
                embed.add_field(name="Moderator", value=moderator_mention, inline=True)
                embed.add_field(name="Timestamp", value=f"{formatted_timestamp} ({relative_timestamp})", inline=False)
                embed.add_field(name="Reason", value=reason, inline=False)

                await ctx.send(embed=embed)

            else:
                embed = utils.create_embed(ctx, title="Error", color=discord.Color.red(),
                                           description=f"Could not find Case ID `{case_id}` in this server.")
                await ctx.send(embed=embed)

        except discord.NotFound:
             await ctx.send("Could not fetch user information for the case details.")
        except discord.Forbidden:
            await ctx.send("I lack permissions to send messages or fetch user data.")
        except discord.HTTPException as e:
            await ctx.send(f"An error occurred communicating with Discord: {e}")
        except ConnectionError as e:
             await ctx.send(f"Database error: {e}")
        except Exception as e:
            await ctx.send(f"An unexpected error occurred: {e}")
            print(f"ERROR: Unexpected error in history view: {e}")
            traceback.print_exc()
        finally:
            if conn:
                conn.close()

    # --- Error Handlers for Subcommands ---
    # It's good practice to have specific error handlers if needed,
    # or a general handler for the group.

    @history_removeall.error
    async def history_removeall_error(self, ctx, error):
        if isinstance(error, commands.MissingPermissions):
            await ctx.send("You need 'Administrator' permission to use this command.")
        elif isinstance(error, commands.MemberNotFound):
            await ctx.send("Member not found. Please provide a valid member.")
        elif isinstance(error, commands.CommandInvokeError):
            await ctx.send(f"An internal error occurred: {error.original}")
            print(f"ERROR: CommandInvokeError in history removeall: {error.original}")
            traceback.print_exc()
        else:
            await ctx.send(f"An error occurred: {error}")

    @history_remove.error
    async def history_remove_error(self, ctx, error):
        if isinstance(error, commands.MissingPermissions):
            await ctx.send("You need 'Manage Messages' permission to use this command.")
        elif isinstance(error, commands.MemberNotFound):
            await ctx.send("Member not found. Please provide a valid member.")
        elif isinstance(error, commands.BadArgument):
             await ctx.send("Invalid arguments. Usage: `.history remove <@member> <case_id>` (case_id must be a number).")
        elif isinstance(error, commands.MissingRequiredArgument):
             await ctx.send(f"Missing argument: `{error.param.name}`. Usage: `.history remove <@member> <case_id>`")
        elif isinstance(error, commands.CommandInvokeError):
            await ctx.send(f"An internal error occurred: {error.original}")
            print(f"ERROR: CommandInvokeError in history remove: {error.original}")
            traceback.print_exc()
        else:
            await ctx.send(f"An error occurred: {error}")

    @history_view.error
    async def history_view_error(self, ctx, error):
        if isinstance(error, commands.MissingPermissions):
            await ctx.send("You need 'Manage Messages' permission to use this command.")
        elif isinstance(error, commands.BadArgument):
             await ctx.send("Invalid argument. Usage: `.history view <case_id>` (case_id must be a number).")
        elif isinstance(error, commands.MissingRequiredArgument):
             await ctx.send(f"Missing argument: `{error.param.name}`. Usage: `.history view <case_id>`")
        elif isinstance(error, commands.CommandInvokeError):
            await ctx.send(f"An internal error occurred: {error.original}")
            print(f"ERROR: CommandInvokeError in history view: {error.original}")
            traceback.print_exc()
        else:
            await ctx.send(f"An error occurred: {error}")

    # General error handler for the base history command (if invoked without subcommand)
    @history.error
    async def history_base_error(self, ctx, error):
         if isinstance(error, commands.MissingPermissions):
             await ctx.send("You need 'Manage Messages' permission to use this command.")
         elif isinstance(error, commands.MemberNotFound):
             await ctx.send("Member not found. Please provide a valid member.")
         elif isinstance(error, commands.CommandInvokeError) and not isinstance(error.original, (commands.MissingPermissions, commands.MemberNotFound, commands.BadArgument)):
             # Avoid duplicating subcommand errors if they bubble up
             await ctx.send(f"An internal error occurred while executing the history command: {error.original}")
             print(f"ERROR: CommandInvokeError in history base: {error.original}")
             traceback.print_exc()
         # Let subcommand errors be handled by their specific handlers if possible


# Setup function to add the cog to the bot
async def setup(bot):
    # Make sure to import DictCursor if used
    import psycopg2.extras
    await bot.add_cog(History(bot))
    await bot.add_cog(History(bot))
