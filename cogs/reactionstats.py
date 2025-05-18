import discord
from discord.ext import commands, tasks
import datetime
import psycopg2
import psycopg2.extras # For dictionary cursor
import os
import traceback
from typing import Optional, List, Dict, Union
from urllib.parse import urlparse
from collections import Counter

class ReactionStats(commands.Cog):
    """
    Tracks reactions and shows top reactions received by users.
    """
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        
        self.db_url = os.getenv("DATABASE_URL")
        self.db_params = None
        if self.db_url:
            self.db_params = self._parse_db_url(self.db_url)
            self._init_db()
        else:
            print("ERROR [ReactionStats Init]: DATABASE_URL environment variable not set. Cog will not function with DB.")
        
        print("[ReactionStats DEBUG] Cog initialized.")

    def _parse_db_url(self, url: str) -> Optional[dict]:
        try:
            parsed = urlparse(url)
            return {
                "dbname": parsed.path[1:], "user": parsed.username,
                "password": parsed.password, "host": parsed.hostname,
                "port": parsed.port or 5432,
                "sslmode": "require" if "sslmode=require" in url else None
            }
        except Exception as e:
            print(f"ERROR [ReactionStats _parse_db_url]: Failed to parse DATABASE_URL: {e}")
            return None

    def _get_db_connection(self):
        if not self.db_params: raise ConnectionError("DB params not configured.")
        try:
            return psycopg2.connect(**self.db_params)
        except psycopg2.Error as e:
            print(f"ERROR [ReactionStats _get_db_connection]: DB connection failed: {e}")
            raise ConnectionError(f"Failed to connect to DB: {e}")

    def _init_db(self):
        if not self.db_params: return
        conn = None
        try:
            conn = self._get_db_connection()
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS current_reactions (
                    id SERIAL PRIMARY KEY,
                    guild_id BIGINT NOT NULL,
                    channel_id BIGINT NOT NULL,
                    message_id BIGINT NOT NULL,
                    message_author_id BIGINT NOT NULL,
                    reactor_id BIGINT NOT NULL,
                    emoji_unicode TEXT,
                    emoji_custom_id BIGINT,
                    emoji_custom_name TEXT,
                    emoji_is_animated BOOLEAN,
                    reacted_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE (message_id, reactor_id, emoji_unicode, emoji_custom_id) -- Ensure unique reaction per user/emoji/message
                )
            """)
            # Index for faster queries on message_author_id and reacted_at
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_current_reactions_author_time 
                ON current_reactions (message_author_id, reacted_at);
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_current_reactions_message_id
                ON current_reactions (message_id);
            """)
            conn.commit()
            cursor.close()
            print("[ReactionStats DEBUG] 'current_reactions' table checked/created.")
        except (psycopg2.Error, ConnectionError) as e:
            print(f"ERROR [ReactionStats _init_db]: DB table init failed: {e}")
        finally:
            if conn: conn.close()

    async def _get_message_author_id(self, payload: discord.RawReactionActionEvent) -> Optional[int]:
        """Tries to get message author ID, fetching message if not in cache."""
        channel = self.bot.get_channel(payload.channel_id)
        if not channel or not isinstance(channel, discord.abc.Messageable): # Check if messageable (TextChannel, Thread, VoiceChannel)
            return None
        try:
            message = await channel.fetch_message(payload.message_id)
            return message.author.id
        except discord.NotFound:
            print(f"[ReactionStats DEBUG] Message {payload.message_id} not found (likely deleted).")
        except discord.Forbidden:
            print(f"[ReactionStats DEBUG] Forbidden to fetch message {payload.message_id} in channel {payload.channel_id}.")
        except Exception as e:
            print(f"[ReactionStats DEBUG] Error fetching message {payload.message_id}: {e}")
        return None

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent):
        if not self.db_params or not payload.guild_id or payload.user_id == self.bot.user.id:
            return

        message_author_id = await self._get_message_author_id(payload)
        if not message_author_id:
            # If we can't get the author, we can't attribute the reaction for "received" stats
            return 

        emoji = payload.emoji
        sql = """
            INSERT INTO current_reactions 
            (guild_id, channel_id, message_id, message_author_id, reactor_id, 
             emoji_unicode, emoji_custom_id, emoji_custom_name, emoji_is_animated, reacted_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (message_id, reactor_id, emoji_unicode, emoji_custom_id) DO NOTHING; 
        """ # ON CONFLICT handles if event fires multiple times or races
        
        params = (
            payload.guild_id, payload.channel_id, payload.message_id, message_author_id, payload.user_id,
            emoji.name if not emoji.is_custom_emoji() else None,
            emoji.id if emoji.is_custom_emoji() else None,
            emoji.name if emoji.is_custom_emoji() else None, # Store name for custom too
            emoji.animated if emoji.is_custom_emoji() else None,
            datetime.datetime.now(datetime.timezone.utc)
        )
        
        conn = None
        try:
            conn = self._get_db_connection()
            cursor = conn.cursor()
            cursor.execute(sql, params)
            conn.commit()
            cursor.close()
            # print(f"[ReactionStats DEBUG] Reaction ADDED: {emoji} by {payload.user_id} on msg {payload.message_id} (author {message_author_id})")
        except (psycopg2.Error, ConnectionError) as e:
            print(f"ERROR [ReactionStats on_raw_reaction_add]: DB error: {e}")
        finally:
            if conn: conn.close()

    @commands.Cog.listener()
    async def on_raw_reaction_remove(self, payload: discord.RawReactionActionEvent):
        if not self.db_params or not payload.guild_id or payload.user_id == self.bot.user.id:
            return
        
        emoji = payload.emoji
        sql = """
            DELETE FROM current_reactions 
            WHERE message_id = %s AND reactor_id = %s 
            AND ( (emoji_unicode = %s AND emoji_custom_id IS NULL) OR (emoji_custom_id = %s AND emoji_unicode IS NULL) );
        """
        # Made the WHERE clause more specific to differentiate between unicode and custom emoji
        
        params = (
            payload.message_id, payload.user_id,
            emoji.name if not emoji.is_custom_emoji() else None, 
            emoji.id if emoji.is_custom_emoji() else None       
        )
        
        conn = None
        try:
            conn = self._get_db_connection()
            cursor = conn.cursor()
            cursor.execute(sql, params)
            conn.commit()
            cursor.close()
            # print(f"[ReactionStats DEBUG] Reaction REMOVED: {emoji} by {payload.user_id} on msg {payload.message_id}")
        except (psycopg2.Error, ConnectionError) as e:
            print(f"ERROR [ReactionStats on_raw_reaction_remove]: DB error: {e}")
        finally:
            if conn: conn.close()

    @commands.Cog.listener()
    async def on_raw_message_delete(self, payload: discord.RawMessageDeleteEvent):
        """When a message is deleted, remove its reactions from our tracking table."""
        if not self.db_params or not payload.guild_id:
            return
        
        sql = "DELETE FROM current_reactions WHERE message_id = %s AND guild_id = %s;"
        conn = None
        try:
            conn = self._get_db_connection()
            cursor = conn.cursor()
            cursor.execute(sql, (payload.message_id, payload.guild_id))
            conn.commit()
            # print(f"[ReactionStats DEBUG] Reactions for deleted message {payload.message_id} cleared from DB.")
        except (psycopg2.Error, ConnectionError) as e:
            print(f"ERROR [ReactionStats on_raw_message_delete]: DB error: {e}")
        finally:
            if conn: cursor.close(); conn.close()
            
    @commands.Cog.listener()
    async def on_raw_bulk_message_delete(self, payload: discord.RawBulkMessageDeleteEvent):
        """When messages are bulk deleted, remove their reactions."""
        if not self.db_params or not payload.guild_id or not payload.message_ids:
            return

        sql = "DELETE FROM current_reactions WHERE message_id = ANY(%s) AND guild_id = %s;"
        conn = None
        try:
            conn = self._get_db_connection()
            cursor = conn.cursor()
            cursor.execute(sql, (list(payload.message_ids), payload.guild_id)) # Pass message_ids as a list
            conn.commit()
            # print(f"[ReactionStats DEBUG] Reactions for {len(payload.message_ids)} bulk deleted messages cleared.")
        except (psycopg2.Error, ConnectionError) as e:
            print(f"ERROR [ReactionStats on_raw_bulk_message_delete]: DB error: {e}")
        finally:
            if conn: cursor.close(); conn.close()


    @commands.command(name="topreactions", aliases=["topreacts", "rstats"]) # Added 'rstats' alias
    @commands.cooldown(1, 10, commands.BucketType.user)
    async def top_reactions(self, ctx: commands.Context, member: Optional[discord.Member] = None, timeframe: str = "all"):
        """
        Shows top reactions received by a user's messages.
        Timeframes: 'day', 'week', 'all' (default).
        Usage: .topreactions [@user] [day/week/all]
        Aliases: .topreacts, .rstats
        """
        if not self.db_params:
            await ctx.send("Database not configured for this command.")
            return

        target_member = member or ctx.author
        now = datetime.datetime.now(datetime.timezone.utc)
        time_filter_sql = ""
        time_start = None

        if timeframe.lower() == "day":
            time_start = now - datetime.timedelta(days=1)
            time_filter_sql = "AND reacted_at >= %s"
        elif timeframe.lower() == "week":
            time_start = now - datetime.timedelta(days=7)
            time_filter_sql = "AND reacted_at >= %s"
        elif timeframe.lower() != "all":
            await ctx.send("Invalid timeframe. Use 'day', 'week', or 'all'.")
            return

        conn = None
        try:
            conn = self._get_db_connection()
            cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
            
            query = f"""
                SELECT emoji_unicode, emoji_custom_id, emoji_custom_name, emoji_is_animated, COUNT(*) as reaction_count
                FROM current_reactions
                WHERE message_author_id = %s AND guild_id = %s {time_filter_sql}
                GROUP BY emoji_unicode, emoji_custom_id, emoji_custom_name, emoji_is_animated
                ORDER BY reaction_count DESC
                LIMIT 10; 
            """
            params = [target_member.id, ctx.guild.id]
            if time_start:
                params.append(time_start)
            
            cursor.execute(query, tuple(params))
            top_reactions_data = cursor.fetchall()
            cursor.close()

            utils_cog = self.bot.get_cog('Utils')
            embed_title = f"Top Reactions Received by {target_member.display_name}"
            if timeframe.lower() != "all":
                embed_title += f" (Last {timeframe.capitalize()})"
            
            if not top_reactions_data:
                desc = "No reactions found for this user in the specified timeframe."
                if utils_cog: embed = utils_cog.create_embed(ctx, title=embed_title, description=desc, color=discord.Color.orange())
                else: embed = discord.Embed(title=embed_title, description=desc, color=discord.Color.orange())
                await ctx.send(embed=embed)
                return

            description_lines = []
            for i, row in enumerate(top_reactions_data):
                emoji_display = ""
                if row['emoji_custom_id']:
                    custom_emoji = self.bot.get_emoji(row['emoji_custom_id'])
                    if custom_emoji:
                        emoji_display = str(custom_emoji)
                    else: # Fallback if bot can't see the emoji (e.g., from another server)
                        emoji_display = f"<:{row['emoji_custom_name']}:{row['emoji_custom_id']}>" if not row['emoji_is_animated'] else f"<a:{row['emoji_custom_name']}:{row['emoji_custom_id']}>"
                elif row['emoji_unicode']:
                    emoji_display = row['emoji_unicode']
                
                description_lines.append(f"{i+1}. {emoji_display} - **{row['reaction_count']}**")
            
            if utils_cog:
                embed = utils_cog.create_embed(ctx, title=embed_title, description="\n".join(description_lines), color=discord.Color.blue())
            else:
                embed = discord.Embed(title=embed_title, description="\n".join(description_lines), color=discord.Color.blue(), timestamp=datetime.datetime.now(datetime.timezone.utc))
                embed.set_footer(text=f"Requested by {ctx.author.name}", icon_url=ctx.author.display_avatar.url if ctx.author.avatar else None)

            await ctx.send(embed=embed)

        except (psycopg2.Error, ConnectionError) as e:
            print(f"ERROR [ReactionStats .topreactions]: DB error: {e}")
            await ctx.send("A database error occurred while fetching top reactions.")
            traceback.print_exc()
        except Exception as e:
            print(f"ERROR [ReactionStats .topreactions]: Unexpected error: {e}")
            await ctx.send("An unexpected error occurred.")
            traceback.print_exc()
        finally:
            if conn: conn.close()

    @top_reactions.error
    async def top_reactions_error(self, ctx, error):
        if isinstance(error, commands.CommandOnCooldown):
            await ctx.send(f"This command is on cooldown. Try again in {error.retry_after:.2f}s.")
        elif isinstance(error, commands.MemberNotFound):
            await ctx.send(f"Member not found: {error.argument}")
        else:
            await ctx.send("An error occurred with the top reactions command.")
            print(f"Error in top_reactions_error: {error}")
            traceback.print_exc()

async def setup(bot: commands.Bot):
    # Ensure intents.reactions = True is set in main bot file
    await bot.add_cog(ReactionStats(bot))
    print("Cog 'ReactionStats' loaded successfully.")

