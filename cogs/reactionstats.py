import discord
from discord.ext import commands, tasks
import datetime
import psycopg2
import psycopg2.extras # For dictionary cursor
import os
import traceback
from typing import Optional, List, Dict, Union, Tuple
from urllib.parse import urlparse
from collections import Counter

class ReactionStats(commands.Cog):
    """
    Tracks reactions and shows top reactions received by users
    and leaderboards for specific emojis.
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
                    UNIQUE (message_id, reactor_id, emoji_unicode, emoji_custom_id)
                )
            """)
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_current_reactions_author_time ON current_reactions (message_author_id, reacted_at);")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_current_reactions_message_id ON current_reactions (message_id);")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_current_reactions_emoji ON current_reactions (emoji_unicode, emoji_custom_id);")
            conn.commit()
            cursor.close()
            print("[ReactionStats DEBUG] 'current_reactions' table checked/created.")
        except (psycopg2.Error, ConnectionError) as e:
            print(f"ERROR [ReactionStats _init_db]: DB table init failed: {e}")
        finally:
            if conn: conn.close()

    async def _get_message_author_id(self, payload: discord.RawReactionActionEvent) -> Optional[int]:
        channel = self.bot.get_channel(payload.channel_id)
        if not channel or not isinstance(channel, discord.abc.Messageable): return None
        try:
            message = await channel.fetch_message(payload.message_id)
            return message.author.id
        except (discord.NotFound, discord.Forbidden): pass
        except Exception as e: print(f"[ReactionStats DEBUG] Error fetching message {payload.message_id}: {e}")
        return None

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent):
        if not self.db_params or not payload.guild_id or payload.user_id == self.bot.user.id: return
        message_author_id = await self._get_message_author_id(payload)
        if not message_author_id: return 

        emoji = payload.emoji
        sql = """
            INSERT INTO current_reactions 
            (guild_id, channel_id, message_id, message_author_id, reactor_id, 
             emoji_unicode, emoji_custom_id, emoji_custom_name, emoji_is_animated, reacted_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (message_id, reactor_id, emoji_unicode, emoji_custom_id) DO NOTHING; 
        """
        params = (
            payload.guild_id, payload.channel_id, payload.message_id, message_author_id, payload.user_id,
            emoji.name if not emoji.is_custom_emoji() else None,
            emoji.id if emoji.is_custom_emoji() else None,
            emoji.name if emoji.is_custom_emoji() else None,
            emoji.animated if emoji.is_custom_emoji() else None,
            datetime.datetime.now(datetime.timezone.utc)
        )
        conn = None
        try:
            conn = self._get_db_connection()
            cursor = conn.cursor(); cursor.execute(sql, params); conn.commit(); cursor.close()
        except (psycopg2.Error, ConnectionError) as e: print(f"ERROR [ReactionStats on_raw_reaction_add]: DB error: {e}")
        finally:
            if conn: conn.close()

    @commands.Cog.listener()
    async def on_raw_reaction_remove(self, payload: discord.RawReactionActionEvent):
        if not self.db_params or not payload.guild_id or payload.user_id == self.bot.user.id: return
        emoji = payload.emoji
        sql = """
            DELETE FROM current_reactions 
            WHERE message_id = %s AND reactor_id = %s 
            AND ( (emoji_unicode = %s AND emoji_custom_id IS NULL) OR (emoji_custom_id = %s AND emoji_unicode IS NULL) );
        """
        params = (
            payload.message_id, payload.user_id,
            emoji.name if not emoji.is_custom_emoji() else None, 
            emoji.id if emoji.is_custom_emoji() else None       
        )
        conn = None
        try:
            conn = self._get_db_connection()
            cursor = conn.cursor(); cursor.execute(sql, params); conn.commit(); cursor.close()
        except (psycopg2.Error, ConnectionError) as e: print(f"ERROR [ReactionStats on_raw_reaction_remove]: DB error: {e}")
        finally:
            if conn: conn.close()

    @commands.Cog.listener()
    async def on_raw_message_delete(self, payload: discord.RawMessageDeleteEvent):
        if not self.db_params or not payload.guild_id: return
        sql = "DELETE FROM current_reactions WHERE message_id = %s AND guild_id = %s;"
        conn = None
        try:
            conn = self._get_db_connection()
            cursor = conn.cursor(); cursor.execute(sql, (payload.message_id, payload.guild_id)); conn.commit()
        except (psycopg2.Error, ConnectionError) as e: print(f"ERROR [ReactionStats on_raw_message_delete]: DB error: {e}")
        finally:
            if conn: cursor.close(); conn.close()
            
    @commands.Cog.listener()
    async def on_raw_bulk_message_delete(self, payload: discord.RawBulkMessageDeleteEvent):
        if not self.db_params or not payload.guild_id or not payload.message_ids: return
        sql = "DELETE FROM current_reactions WHERE message_id = ANY(%s) AND guild_id = %s;"
        conn = None
        try:
            conn = self._get_db_connection()
            cursor = conn.cursor(); cursor.execute(sql, (list(payload.message_ids), payload.guild_id)); conn.commit()
        except (psycopg2.Error, ConnectionError) as e: print(f"ERROR [ReactionStats on_raw_bulk_message_delete]: DB error: {e}")
        finally:
            if conn: cursor.close(); conn.close()

    async def _fetch_top_reactions_for_user_period(self, guild_id: int, member_id: int, start_time: Optional[datetime.datetime]) -> List[Dict]:
        if not self.db_params: return []
        time_filter_sql = "AND reacted_at >= %s" if start_time else ""
        conn = None
        try:
            conn = self._get_db_connection()
            cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
            query = f"""
                SELECT emoji_unicode, emoji_custom_id, emoji_custom_name, emoji_is_animated, COUNT(*) as reaction_count
                FROM current_reactions
                WHERE message_author_id = %s AND guild_id = %s {time_filter_sql}
                GROUP BY emoji_unicode, emoji_custom_id, emoji_custom_name, emoji_is_animated
                ORDER BY reaction_count DESC LIMIT 3; 
            """
            params = [member_id, guild_id]
            if start_time: params.append(start_time)
            cursor.execute(query, tuple(params)); return cursor.fetchall()
        except (psycopg2.Error, ConnectionError) as e: print(f"ERROR [ReactionStats _fetch_top_reactions_for_user_period]: DB error: {e}"); return []
        finally:
            if conn: cursor.close(); conn.close()

    def _format_reactions_list_for_embed_field(self, reactions_data: List[Dict]) -> str:
        if not reactions_data: return "No reactions found in this period."
        lines = []
        for i, row in enumerate(reactions_data):
            emoji_display = ""
            if row['emoji_custom_id']:
                custom_emoji = self.bot.get_emoji(row['emoji_custom_id'])
                if custom_emoji: emoji_display = str(custom_emoji)
                else: emoji_display = f"<:{row['emoji_custom_name']}:{row['emoji_custom_id']}>" if not row['emoji_is_animated'] else f"<a:{row['emoji_custom_name']}:{row['emoji_custom_id']}>"
            elif row['emoji_unicode']: emoji_display = row['emoji_unicode']
            lines.append(f"{i+1}. {emoji_display} - **{row['reaction_count']}**")
        return "\n".join(lines)

    async def _fetch_emoji_leaderboard_for_period(self, guild_id: int, emoji_unicode: Optional[str], emoji_custom_id: Optional[int], start_time: Optional[datetime.datetime]) -> List[Dict]:
        if not self.db_params: return []
        time_filter_sql = "AND reacted_at >= %s" if start_time else ""
        # Ensure only one of emoji_unicode or emoji_custom_id is used for filtering
        if emoji_unicode and emoji_custom_id: # Should not happen with current parsing logic
            print("[ReactionStats DEBUG] Both unicode and custom_id provided to _fetch_emoji_leaderboard. Prioritizing unicode.")
            emoji_custom_id = None
        
        emoji_filter_sql = "AND emoji_unicode = %s AND emoji_custom_id IS NULL" if emoji_unicode else "AND emoji_custom_id = %s AND emoji_unicode IS NULL"
        
        conn = None
        try:
            conn = self._get_db_connection()
            cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
            query = f"""
                SELECT message_author_id, COUNT(*) as reaction_count
                FROM current_reactions
                WHERE guild_id = %s {emoji_filter_sql} {time_filter_sql}
                GROUP BY message_author_id
                ORDER BY reaction_count DESC
                LIMIT 3;
            """
            params = [guild_id]
            if emoji_unicode: params.append(emoji_unicode)
            elif emoji_custom_id: params.append(emoji_custom_id)
            else: return [] # No valid emoji identifier provided
            
            if start_time: params.append(start_time)
            
            cursor.execute(query, tuple(params))
            return cursor.fetchall() 
        except (psycopg2.Error, ConnectionError) as e: print(f"ERROR [ReactionStats _fetch_emoji_leaderboard_for_period]: DB error: {e}"); return []
        finally:
            if conn: cursor.close(); conn.close()

    def _format_leaderboard_for_embed_field(self, leaderboard_data: List[Dict], guild: discord.Guild) -> str:
        if not leaderboard_data: return "No users found for this emoji in this period."
        lines = []
        for i, row in enumerate(leaderboard_data):
            user = guild.get_member(row['message_author_id']) 
            user_display = user.mention if user else f"User ID: {row['message_author_id']}"
            lines.append(f"{i+1}. {user_display} - **{row['reaction_count']}** times")
        return "\n".join(lines)

    @commands.group(name="topreactions", aliases=["topreacts", "rstats"], invoke_without_command=True)
    @commands.cooldown(1, 10, commands.BucketType.user)
    async def topreactions_group(self, ctx: commands.Context, member: Optional[discord.Member] = None):
        if ctx.invoked_subcommand is None:
            await self.user_top_reactions(ctx, member=member)

    @topreactions_group.command(name="user")
    @commands.cooldown(1, 10, commands.BucketType.user)
    async def user_top_reactions(self, ctx: commands.Context, member: Optional[discord.Member] = None):
        if not self.db_params: await ctx.send("Database not configured."); return
        target_member = member or ctx.author
        now = datetime.datetime.now(datetime.timezone.utc)
        timeframes = {
            "Last 24 Hours": now - datetime.timedelta(days=1),
            "Last 7 Days": now - datetime.timedelta(days=7),
            "All Time": None
        }
        utils_cog = self.bot.get_cog('Utils')
        embed_title = f"Top Reactions Received by {target_member.display_name}"
        embed = utils_cog.create_embed(ctx, title=embed_title, description="", color=discord.Color.purple()) if utils_cog \
                else discord.Embed(title=embed_title, description="", color=discord.Color.purple(), timestamp=now)
        if not utils_cog: embed.set_footer(text=f"Requested by {ctx.author.name}", icon_url=ctx.author.display_avatar.url if ctx.author.avatar else None)

        any_data_found = False
        for period_name, start_time_obj in timeframes.items():
            reactions_data = await self._fetch_top_reactions_for_user_period(ctx.guild.id, target_member.id, start_time_obj)
            if reactions_data: any_data_found = True
            field_value = self._format_reactions_list_for_embed_field(reactions_data)
            embed.add_field(name=f"{period_name}", value=field_value, inline=False)
        if not any_data_found and not embed.fields: embed.description = "No reactions found for this user."
        await ctx.send(embed=embed)

    @topreactions_group.command(name="leaderboard")
    @commands.cooldown(1, 10, commands.BucketType.user)
    async def emoji_leaderboard(self, ctx: commands.Context, *, emoji_input: str): # Changed to take raw string
        """
        Shows a leaderboard for a specific emoji.
        Usage: .rstats leaderboard <emoji>
        """
        if not self.db_params: await ctx.send("Database not configured."); return

        emoji_input_stripped = emoji_input.strip()
        target_emoji_display: str = emoji_input_stripped 
        emoji_unicode_arg: Optional[str] = None
        emoji_custom_id_arg: Optional[int] = None

        try:
            # Try to convert using PartialEmojiConverter first.
            # This handles custom emojis like <:name:id> and also standard Unicode emojis.
            partial_emoji_obj = await commands.PartialEmojiConverter().convert(ctx, emoji_input_stripped)
            target_emoji_display = str(partial_emoji_obj) # Use its string representation
            if partial_emoji_obj.is_unicode_emoji(): # Same as not partial_emoji_obj.id
                emoji_unicode_arg = partial_emoji_obj.name
            else: # Custom emoji
                emoji_custom_id_arg = partial_emoji_obj.id
            print(f"[ReactionStats DEBUG] Parsed emoji via PartialEmojiConverter: {target_emoji_display}, Unicode: {emoji_unicode_arg}, Custom ID: {emoji_custom_id_arg}")
        except commands.PartialEmojiConversionFailure:
            # If PartialEmojiConverter fails, it might be a malformed custom emoji string
            # or a Unicode emoji that it struggled with (though it should generally work).
            # As a fallback, if it's a short string, assume it's a direct Unicode emoji.
            if 0 < len(emoji_input_stripped) <= 7: # Max length for complex Unicode emojis with ZWJ/modifiers
                emoji_unicode_arg = emoji_input_stripped
                target_emoji_display = emoji_input_stripped # Use the raw input as display
                print(f"[ReactionStats DEBUG] PartialEmojiConverter failed. Treating as direct Unicode string: {target_emoji_display}")
            else:
                await ctx.send(f"Could not interpret '{emoji_input_stripped}' as a valid emoji. Please use a standard Unicode emoji or a custom emoji from a server I'm in.")
                return
        
        if not emoji_unicode_arg and not emoji_custom_id_arg:
            await ctx.send(f"Failed to identify the emoji: '{emoji_input_stripped}'. Please use a valid emoji.")
            return

        now = datetime.datetime.now(datetime.timezone.utc)
        timeframes = {
            "Last 24 Hours": now - datetime.timedelta(days=1),
            "Last 7 Days": now - datetime.timedelta(days=7),
            "All Time": None
        }
        utils_cog = self.bot.get_cog('Utils')
        
        embed_title = f"Leaderboard for {target_emoji_display} Reaction"
        embed = utils_cog.create_embed(ctx, title=embed_title, description="", color=discord.Color.gold()) if utils_cog \
                else discord.Embed(title=embed_title, description="", color=discord.Color.gold(), timestamp=now)
        if not utils_cog: embed.set_footer(text=f"Requested by {ctx.author.name}", icon_url=ctx.author.display_avatar.url if ctx.author.avatar else None)

        any_data_found = False
        for period_name, start_time_obj in timeframes.items():
            leaderboard_data = await self._fetch_emoji_leaderboard_for_period(ctx.guild.id, emoji_unicode_arg, emoji_custom_id_arg, start_time_obj)
            if leaderboard_data: any_data_found = True
            field_value = self._format_leaderboard_for_embed_field(leaderboard_data, ctx.guild)
            embed.add_field(name=f"{period_name}", value=field_value, inline=False)
        
        if not any_data_found and not embed.fields: 
            embed.description = f"No one has received the {target_emoji_display} reaction in any tracked timeframe."
        
        await ctx.send(embed=embed)

    @topreactions_group.error
    async def topreactions_group_error(self, ctx, error):
        if isinstance(error, commands.CommandOnCooldown): await ctx.send(f"This command group is on cooldown. Try again in {error.retry_after:.2f}s.")
        else: print(f"Error in topreactions_group: {error}"); traceback.print_exc()

    @user_top_reactions.error
    async def user_top_reactions_error(self, ctx, error):
        if isinstance(error, commands.CommandOnCooldown): await ctx.send(f"This command is on cooldown. Try again in {error.retry_after:.2f}s.")
        elif isinstance(error, commands.MemberNotFound): await ctx.send(f"Member not found: {error.argument}")
        elif isinstance(error, commands.CommandInvokeError) and isinstance(error.original, ConnectionError): await ctx.send("DB connection error for reaction stats.")
        else: await ctx.send("An error occurred with user top reactions."); print(f"Error in user_top_reactions_error: {error}"); traceback.print_exc()

    @emoji_leaderboard.error
    async def emoji_leaderboard_error(self, ctx, error):
        if isinstance(error, commands.CommandOnCooldown): await ctx.send(f"This command is on cooldown. Try again in {error.retry_after:.2f}s.")
        elif isinstance(error, commands.MissingRequiredArgument) and error.param.name == "emoji_input": 
            await ctx.send("You need to specify an emoji for the leaderboard. Usage: `.rstats leaderboard <emoji>`")
        # The PartialEmojiConversionFailure might still be caught if the converter is used explicitly and fails in an unhandled way
        elif isinstance(error, commands.PartialEmojiConversionFailure): 
             await ctx.send(f"Could not interpret '{error.argument}' as a valid emoji. Please use a standard Unicode emoji or a custom emoji from a server the bot is in.")
        elif isinstance(error, commands.CommandInvokeError) and isinstance(error.original, ConnectionError): await ctx.send("DB connection error for emoji leaderboard.")
        else: await ctx.send("An error occurred with the emoji leaderboard command."); print(f"Error in emoji_leaderboard_error: {error}"); traceback.print_exc()

async def setup(bot: commands.Bot):
    await bot.add_cog(ReactionStats(bot))
    print("Cog 'ReactionStats' loaded successfully.")

