import os
import psycopg2
from discord.ext import commands
import discord
import time
import math
import json
from urllib.parse import urlparse

class History(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db_url = os.getenv("DATABASE_URL")
        if not self.db_url:
            raise ValueError("DATABASE_URL environment variable not set")
        # Heroku Postgres requires SSL
        self.db_params = self._parse_db_url(self.db_url)
        self._init_db()
        print("DEBUG: History cog initialized, Postgres database set up.")

    def _parse_db_url(self, url):
        """Parse the Heroku DATABASE_URL into psycopg2 connection parameters."""
        parsed = urlparse(url)
        return {
            "dbname": parsed.path[1:],  # Remove leading '/'
            "user": parsed.username,
            "password": parsed.password,
            "host": parsed.hostname,
            "port": parsed.port,
            "sslmode": "require"  # Heroku Postgres requires SSL
        }

    def _init_db(self):
        """Initialize the Postgres database and create the mod_logs table if it doesn't exist."""
        conn = psycopg2.connect(**self.db_params)
        cursor = conn.cursor()
        # Create table: id (auto-increment), guild_id, member_id, action, moderator (JSONB), timestamp, reason
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS mod_logs (
                id SERIAL PRIMARY KEY,
                guild_id BIGINT NOT NULL,
                member_id BIGINT NOT NULL,
                action TEXT NOT NULL,
                moderator JSONB NOT NULL,  -- Store as JSONB
                timestamp DOUBLE PRECISION NOT NULL,
                reason TEXT
            )
        """)
        conn.commit()
        cursor.close()
        conn.close()
        print("DEBUG: mod_logs table created or already exists in Postgres.")

    def log_action(self, guild_id, member_id, action, moderator, reason=None):
        """Log a moderation action to the Postgres database."""
        member_id = int(member_id)
        guild_id = int(guild_id)
        # Serialize moderator (discord.Member object) to JSON
        moderator_data = {
            "id": moderator.id,
            "name": moderator.name,
            "mention": moderator.mention
        }
        moderator_json = json.dumps(moderator_data)
        timestamp = time.time()
        
        print(f"DEBUG: Logging action to Postgres - Guild: {guild_id}, Member: {member_id}, Action: {action}")
        
        conn = psycopg2.connect(**self.db_params)
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO mod_logs (guild_id, member_id, action, moderator, timestamp, reason)
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (guild_id, member_id, action, moderator_json, timestamp, reason))
        conn.commit()
        cursor.close()
        conn.close()
        
        print(f"DEBUG: Action logged to Postgres: {action} for member {member_id} in guild {guild_id}")

    def _fetch_actions(self, guild_id, member_id):
        """Fetch all actions for a member in a guild from the Postgres database."""
        conn = psycopg2.connect(**self.db_params)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT action, moderator, timestamp, reason
            FROM mod_logs
            WHERE guild_id = %s AND member_id = %s
            ORDER BY timestamp DESC
        """, (guild_id, member_id))
        rows = cursor.fetchall()
        cursor.close()
        conn.close()
        
        # Convert rows to action dictionaries
        actions = []
        for row in rows:
            action, moderator_json, timestamp, reason = row
            try:
                moderator_data = moderator_json  # Already a dict since Postgres JSONB returns a Python dict
                # Reconstruct a pseudo-moderator object
                moderator = type('PseudoMember', (), {
                    'id': moderator_data['id'],
                    'name': moderator_data['name'],
                    'mention': moderator_data['mention']
                })()
                actions.append({
                    "action": action,
                    "moderator": moderator,
                    "timestamp": timestamp,
                    "reason": reason
                })
            except (TypeError, KeyError) as e:
                print(f"DEBUG: Failed to process moderator data: {moderator_json}, error: {str(e)}")
                continue
        
        print(f"DEBUG: Fetched actions for member {member_id} in guild {guild_id} (length: {len(actions)}): {actions}")
        return actions

    @commands.command()
    @commands.has_permissions(moderate_members=True)
    async def history(self, ctx, member: discord.Member):
        try:
            guild_id = ctx.guild.id
            member_id = member.id

            # Fetch actions from the database
            actions = self._fetch_actions(guild_id, member_id)
            
            if not actions:
                await ctx.send(f"No moderation history found for {member.mention}.")
                return

            # Pagination setup
            actions_per_page = 5
            total_pages = math.ceil(len(actions) / actions_per_page)
            current_page = 1

            utils = self.bot.get_cog('Utils')
            if not utils:
                await ctx.send("Error: Utils cog not loaded.")
                return

            def get_page(page_num):
                start_idx = (page_num - 1) * actions_per_page
                end_idx = start_idx + actions_per_page
                page_actions = actions[start_idx:end_idx]
                print(f"DEBUG: Page actions for page {page_num} (length: {len(page_actions)}): {page_actions}")
                description = ""
                for idx, action in enumerate(page_actions):
                    print(f"DEBUG: Processing action at index {idx}: {action}")
                    try:
                        timestamp = discord.utils.format_dt(int(action["timestamp"]), style="R")
                    except (TypeError, ValueError) as e:
                        timestamp = "Invalid timestamp"
                        print(f"DEBUG: Invalid timestamp in action: {action}, error: {str(e)}")
                    reason = action["reason"] if action["reason"] else "No reason provided"
                    description += f"**Action:** {action['action']} | **Moderator:** {action['moderator'].mention} | **Time:** {timestamp}\n**Reason:** {reason}\n\n"
                embed = utils.create_embed(ctx, title=f"Moderation History for {member}")
                embed.description = description.strip() or "No actions to display."
                embed.set_footer(text=f"Page {page_num}/{total_pages} | Requested by {ctx.author}")
                print(f"DEBUG: Embed description length: {len(embed.description)}")
                return embed

            # Send initial embed
            embed = get_page(current_page)
            message = await ctx.send(embed=embed)

            if total_pages == 1:
                return

            # Add pagination reactions
            left_arrow = "⬅️"
            right_arrow = "➡️"
            await message.add_reaction(left_arrow)
            await message.add_reaction(right_arrow)

            def check(reaction, user):
                return user == ctx.author and reaction.message.id == message.id and str(reaction.emoji) in [left_arrow, right_arrow]

            while True:
                try:
                    reaction, user = await self.bot.wait_for('reaction_add', timeout=60.0, check=check)
                    if str(reaction.emoji) == left_arrow and current_page > 1:
                        current_page -= 1
                    elif str(reaction.emoji) == right_arrow and current_page < total_pages:
                        current_page += 1
                    embed = get_page(current_page)
                    await message.edit(embed=embed)
                    await message.remove_reaction(reaction.emoji, user)
                except asyncio.TimeoutError:
                    await message.clear_reactions()
                    break

        except discord.Forbidden:
            await ctx.send("I don't have permission to manage reactions.")
        except discord.HTTPException as e:
            await ctx.send(f"Failed to fetch history: {str(e)}")
        except Exception as e:
            await ctx.send(f"Unexpected error during history command: {str(e)}")
            raise e

    @commands.command()
    @commands.has_permissions(administrator=True)
    async def clearhistory(self, ctx):
        """Clear all moderation history from the Postgres database."""
        try:
            conn = psycopg2.connect(**self.db_params)
            cursor = conn.cursor()
            cursor.execute("TRUNCATE TABLE mod_logs")
            conn.commit()
            cursor.close()
            conn.close()
            await ctx.send("All moderation history has been cleared.")
            print("DEBUG: All mod_logs cleared via clearhistory command.")
        except Exception as e:
            await ctx.send(f"Failed to clear history: {str(e)}")
            print(f"DEBUG: Error clearing mod_logs: {str(e)}")

    @history.error
    async def history_error(self, ctx, error):
        if isinstance(error, commands.MissingPermissions):
            await ctx.send("You need 'Moderate Members' permission to use this command.")
        elif isinstance(error, commands.MemberNotFound):
            await ctx.send("Member not found. Please provide a valid member.")
        elif isinstance(error, commands.CommandInvokeError):
            await ctx.send("An error occurred while executing the history command. Check bot logs for details.")

async def setup(bot):
    await bot.add_cog(History(bot))
