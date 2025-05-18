import discord
from discord.ext import commands
import psycopg2 # For PostgreSQL interaction
import psycopg2.extras # For dictionary cursor
import os
import traceback
from typing import Optional
from urllib.parse import urlparse # For parsing DATABASE_URL

# AUTOROLES_FILE = "autoroles.json" # No longer needed

class AutoRole(commands.Cog):
    """
    Manages automatically assigning a specified role to new members when they join.
    Uses PostgreSQL for storing configurations.
    """
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.autoroles = {}  # {guild_id: role_id} - In-memory cache, loaded from DB
        
        self.db_url = os.getenv("DATABASE_URL")
        self.db_params = None
        if self.db_url:
            self.db_params = self._parse_db_url(self.db_url)
            self._init_db() # Ensure table exists
            self.load_autoroles_from_db() # Load existing settings
        else:
            print("ERROR [AutoRole Init]: DATABASE_URL environment variable not set. AutoRole cog will not use database.")
        
        print("[AutoRole DEBUG] Cog initialized.")

    def _parse_db_url(self, url: str) -> Optional[dict]:
        """ Parses the DATABASE_URL into connection parameters. """
        try:
            parsed = urlparse(url)
            return {
                "dbname": parsed.path[1:],
                "user": parsed.username,
                "password": parsed.password,
                "host": parsed.hostname,
                "port": parsed.port or 5432, # Default PG port
                "sslmode": "require" if "sslmode=require" in url else None # Basic Heroku SSL check
            }
        except Exception as e:
            print(f"ERROR [AutoRole _parse_db_url]: Failed to parse DATABASE_URL: {e}")
            return None

    def _get_db_connection(self):
        """ Establishes and returns a database connection. Raises ConnectionError on failure. """
        if not self.db_params:
            raise ConnectionError("Database parameters are not configured.")
        try:
            conn = psycopg2.connect(**self.db_params)
            return conn
        except psycopg2.Error as e:
            print(f"ERROR [AutoRole _get_db_connection]: Database connection failed: {e}")
            raise ConnectionError(f"Failed to connect to the database: {e}")

    def _init_db(self):
        """ Ensures the autorole_settings table exists in the database. """
        if not self.db_params:
            print("WARN [AutoRole _init_db]: Database not configured. Skipping table initialization.")
            return
        
        conn = None
        try:
            conn = self._get_db_connection()
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS autorole_settings (
                    guild_id BIGINT PRIMARY KEY,
                    role_id BIGINT NOT NULL
                )
            """)
            conn.commit()
            cursor.close()
            print("[AutoRole DEBUG] 'autorole_settings' table checked/created successfully.")
        except (psycopg2.Error, ConnectionError) as e:
            print(f"ERROR [AutoRole _init_db]: Database table initialization failed: {e}")
        finally:
            if conn:
                conn.close()

    def load_autoroles_from_db(self):
        """Loads auto-role configurations from the PostgreSQL database into memory."""
        if not self.db_params:
            print("[AutoRole DEBUG] Database not configured. Cannot load auto-roles from DB.")
            return

        conn = None
        temp_autoroles = {}
        try:
            conn = self._get_db_connection()
            # Use DictCursor to get rows as dictionary-like objects
            cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
            cursor.execute("SELECT guild_id, role_id FROM autorole_settings")
            rows = cursor.fetchall()
            cursor.close()
            for row in rows:
                temp_autoroles[row['guild_id']] = row['role_id']
            self.autoroles = temp_autoroles
            print(f"[AutoRole DEBUG] Auto-roles loaded from DB: {self.autoroles}")
        except (psycopg2.Error, ConnectionError) as e:
            print(f"ERROR [AutoRole load_autoroles_from_db]: Failed to load auto-roles: {e}")
        finally:
            if conn:
                conn.close()

    def _set_autorole_in_db(self, guild_id: int, role_id: int):
        """Saves or updates an auto-role setting in the database."""
        if not self.db_params:
            print("ERROR [AutoRole _set_autorole_in_db]: Database not configured. Cannot save.")
            return False # Indicate failure

        conn = None
        try:
            conn = self._get_db_connection()
            cursor = conn.cursor()
            # Use UPSERT to insert or update if guild_id already exists
            cursor.execute("""
                INSERT INTO autorole_settings (guild_id, role_id)
                VALUES (%s, %s)
                ON CONFLICT (guild_id) DO UPDATE SET role_id = EXCLUDED.role_id
            """, (guild_id, role_id))
            conn.commit()
            cursor.close()
            self.autoroles[guild_id] = role_id # Update in-memory cache
            print(f"[AutoRole DEBUG] Auto-role for guild {guild_id} set to {role_id} in DB.")
            return True # Indicate success
        except (psycopg2.Error, ConnectionError) as e:
            print(f"ERROR [AutoRole _set_autorole_in_db]: Failed to save auto-role: {e}")
            return False
        finally:
            if conn:
                conn.close()

    def _remove_autorole_from_db(self, guild_id: int):
        """Removes an auto-role setting from the database."""
        if not self.db_params:
            print("ERROR [AutoRole _remove_autorole_from_db]: Database not configured. Cannot remove.")
            return False

        conn = None
        try:
            conn = self._get_db_connection()
            cursor = conn.cursor()
            cursor.execute("DELETE FROM autorole_settings WHERE guild_id = %s", (guild_id,))
            conn.commit()
            cursor.close()
            if guild_id in self.autoroles: # Remove from in-memory cache
                del self.autoroles[guild_id]
            print(f"[AutoRole DEBUG] Auto-role for guild {guild_id} removed from DB.")
            return True
        except (psycopg2.Error, ConnectionError) as e:
            print(f"ERROR [AutoRole _remove_autorole_from_db]: Failed to remove auto-role: {e}")
            return False
        finally:
            if conn:
                conn.close()

    async def _get_autorole_obj(self, guild: discord.Guild) -> Optional[discord.Role]:
        """Gets the discord.Role object for the configured auto-role in a guild from in-memory cache."""
        role_id = self.autoroles.get(guild.id) # Use cached value
        if role_id:
            role = guild.get_role(role_id)
            if role:
                return role
            else:
                # Role ID was configured but role not found (deleted?) - remove from DB and cache
                print(f"[AutoRole DEBUG] Configured auto-role ID {role_id} for guild {guild.id} not found. Removing entry.")
                self._remove_autorole_from_db(guild.id) # This will also update self.autoroles
        return None

    # --- Embed Helper ---
    def _create_fallback_embed(self, title: str, description: str, color: discord.Color, ctx: Optional[commands.Context] = None) -> discord.Embed:
        embed = discord.Embed(title=title, description=description, color=color, timestamp=datetime.datetime.now(datetime.timezone.utc))
        if ctx and ctx.author:
            embed.set_footer(text=f"Requested by {ctx.author.name}", icon_url=ctx.author.display_avatar.url if ctx.author.avatar else None)
        return embed

    async def _send_embed_response(self, ctx: commands.Context, title: str, description: str, color: discord.Color):
        utils_cog = self.bot.get_cog('Utils')
        if utils_cog:
            embed = utils_cog.create_embed(ctx, title=title, description=description, color=color)
        else:
            embed = self._create_fallback_embed(title=title, description=description, color=color, ctx=ctx)
        await ctx.send(embed=embed)

    # --- Event Listener ---
    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        guild = member.guild
        print(f"[AutoRole DEBUG] on_member_join: Member {member.id} joined guild {guild.id}")

        auto_role = await self._get_autorole_obj(guild) # Uses in-memory cache
        if not auto_role:
            print(f"[AutoRole DEBUG] on_member_join: No auto-role configured or found for guild {guild.id}.")
            return

        if not guild.me.guild_permissions.manage_roles:
            print(f"[AutoRole DEBUG] on_member_join: Bot missing 'Manage Roles' permission in guild {guild.id}.")
            return
        
        if auto_role >= guild.me.top_role:
            print(f"[AutoRole DEBUG] on_member_join: Auto-role '{auto_role.name}' is higher than or equal to my top role in guild {guild.id}. Cannot assign.")
            return

        try:
            await member.add_roles(auto_role, reason="Auto-role on join")
            print(f"[AutoRole DEBUG] Successfully assigned '{auto_role.name}' to {member.name} in guild {guild.id}.")

            modlog_cog = self.bot.get_cog('ModLog')
            if modlog_cog: # If you have a ModLog cog
                try:
                    await modlog_cog.log_moderation_action(
                        guild=guild, action_title="Auto-Role Assigned", target_user=member,
                        moderator=self.bot.user, reason=f"New member join (Role: '{auto_role.name}')",
                        color=discord.Color.teal()
                    )
                except Exception as e:
                    print(f"[AutoRole DEBUG] Failed to log auto-role assignment to ModLog: {e}")
        except Exception as e:
            print(f"[AutoRole DEBUG] on_member_join: Unexpected error assigning auto-role: {e}")
            traceback.print_exc()

    # --- Commands ---
    @commands.group(name="autorole", invoke_without_command=True)
    @commands.has_permissions(manage_roles=True) 
    @commands.guild_only()
    async def autorole_group(self, ctx: commands.Context):
        if ctx.invoked_subcommand is None:
            current_auto_role = await self._get_autorole_obj(ctx.guild)
            title = "Auto-Role Status"
            if current_auto_role:
                description = f"ℹ️ The current auto-role for new members is **'{current_auto_role.name}'**."
            else:
                description = "ℹ️ No auto-role is currently configured for new members.\n" \
                              "Use `.autorole set @RoleName` to set one."
            await self._send_embed_response(ctx, title, description, discord.Color.blue())

    @autorole_group.command(name="set")
    @commands.has_permissions(manage_roles=True)
    @commands.bot_has_permissions(manage_roles=True) 
    @commands.guild_only()
    async def autorole_set(self, ctx: commands.Context, role: discord.Role):
        title = "Auto-Role Set"
        color = discord.Color.red()

        if not self.db_params:
            await self._send_embed_response(ctx, title, "Database is not configured for the bot. Cannot set auto-role.", color)
            return

        if role >= ctx.guild.me.top_role:
            description = f"❌ I cannot set the role '{role.name}' as the auto-role because it is higher than or equal to my highest role. Please adjust role positions."
        elif role.is_default(): 
            description = "❌ The `@everyone` role cannot be set as an auto-role."
        elif role.is_integration() or role.is_bot_managed():
            description = f"❌ The role '{role.name}' is managed by an integration or a bot and cannot be set as an auto-role by me."
        else:
            if self._set_autorole_in_db(ctx.guild.id, role.id):
                description = f"✅ New members will now automatically be assigned the **'{role.name}'** role."
                color = discord.Color.green()
            else:
                description = f"❌ Failed to save auto-role setting to the database. Please check bot logs."
        
        await self._send_embed_response(ctx, title, description, color)

    @autorole_group.command(name="remove", aliases=["disable", "off"])
    @commands.has_permissions(manage_roles=True)
    @commands.guild_only()
    async def autorole_remove(self, ctx: commands.Context):
        title = "Auto-Role Remove"
        color = discord.Color.orange()

        if not self.db_params:
            await self._send_embed_response(ctx, title, "Database is not configured for the bot. Cannot remove auto-role.", color)
            return

        if ctx.guild.id in self.autoroles: # Check in-memory cache first
            role_id_to_remove = self.autoroles.get(ctx.guild.id)
            role_obj = ctx.guild.get_role(role_id_to_remove) if role_id_to_remove else None
            role_name_msg = f" (was '{role_obj.name}')" if role_obj else ""

            if self._remove_autorole_from_db(ctx.guild.id):
                description = f"ℹ️ Auto-role has been disabled for new members{role_name_msg}."
            else:
                description = f"❌ Failed to remove auto-role setting from the database. Please check bot logs."
                color = discord.Color.red()
        else:
            description = "ℹ️ Auto-role is not currently enabled on this server."
        await self._send_embed_response(ctx, title, description, color)

    @autorole_group.command(name="status", aliases=["view", "current"])
    @commands.has_permissions(manage_roles=True)
    @commands.guild_only()
    async def autorole_status(self, ctx: commands.Context):
        current_auto_role = await self._get_autorole_obj(ctx.guild)
        title = "Auto-Role Status"
        if current_auto_role:
            description = f"ℹ️ The current auto-role for new members is **'{current_auto_role.name}'**."
        else:
            description = "ℹ️ No auto-role is currently configured for new members."
        await self._send_embed_response(ctx, title, description, discord.Color.blue())

    # --- Error Handlers ---
    async def _handle_error(self, ctx: commands.Context, error_title: str, error_description: str):
        await self._send_embed_response(ctx, error_title, f"❌ {error_description}", discord.Color.red())

    @autorole_group.error
    async def autorole_group_error(self, ctx, error):
        if isinstance(error, commands.MissingPermissions): await self._handle_error(ctx, "Permission Denied", "You need 'Manage Roles' permission.")
        elif isinstance(error, commands.NoPrivateMessage): await self._handle_error(ctx, "Command Error", "This command cannot be used in DMs.")
        else: await self._handle_error(ctx, "Auto-Role Error", f"Unexpected error: {error}"); print(f"Error in autorole_group: {error}"); traceback.print_exc()

    @autorole_set.error
    async def autorole_set_error(self, ctx, error):
        title = "Set Auto-Role Error"
        if isinstance(error, commands.MissingPermissions): await self._handle_error(ctx, title, "You need 'Manage Roles' permission.")
        elif isinstance(error, commands.BotMissingPermissions):
            desc = "I am missing 'Manage Roles' permission." if 'manage_roles' in error.missing_permissions else f"I am missing permissions: {', '.join(error.missing_permissions)}."
            await self._handle_error(ctx, title, desc)
        elif isinstance(error, commands.RoleNotFound): await self._handle_error(ctx, title, f"Role not found: `{error.argument}`.")
        elif isinstance(error, commands.MissingRequiredArgument) and error.param.name == "role": await self._handle_error(ctx, title, "Specify a role. Usage: `.autorole set @RoleName`")
        elif isinstance(error, commands.BadArgument): await self._handle_error(ctx, title, "Invalid role provided.")
        else: await self._handle_error(ctx, title, f"Unexpected error: {error}"); print(f"Error in autorole_set: {error}"); traceback.print_exc()

    @autorole_remove.error
    async def autorole_remove_error(self, ctx, error):
        title = "Remove Auto-Role Error"
        if isinstance(error, commands.MissingPermissions): await self._handle_error(ctx, title, "You need 'Manage Roles' permission.")
        else: await self._handle_error(ctx, title, f"Unexpected error: {error}"); print(f"Error in autorole_remove: {error}"); traceback.print_exc()
            
    @autorole_status.error
    async def autorole_status_error(self, ctx, error):
        title = "Auto-Role Status Error"
        if isinstance(error, commands.MissingPermissions): await self._handle_error(ctx, title, "You need 'Manage Roles' permission to view status.")
        else: await self._handle_error(ctx, title, f"Unexpected error: {error}"); print(f"Error in autorole_status: {error}"); traceback.print_exc()

async def setup(bot: commands.Bot):
    await bot.add_cog(AutoRole(bot))
    print("Cog 'AutoRole' (PostgreSQL) loaded successfully.")

