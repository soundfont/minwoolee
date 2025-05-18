import discord
from discord.ext import commands
import json
import os
import traceback
from typing import Optional

AUTOROLES_FILE = "autoroles.json"  # File to store auto-role configurations

class AutoRole(commands.Cog):
    """
    Manages automatically assigning a specified role to new members when they join.
    """
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.autoroles = {}  # {guild_id: role_id}
        self.load_autoroles()
        print("[AutoRole DEBUG] Cog initialized.")

    def _create_fallback_embed(self, title: str, description: str, color: discord.Color, ctx: Optional[commands.Context] = None) -> discord.Embed:
        """Creates a basic discord.Embed as a fallback if Utils cog is not available."""
        embed = discord.Embed(title=title, description=description, color=color, timestamp=datetime.datetime.now(datetime.timezone.utc))
        if ctx and ctx.author:
            embed.set_footer(text=f"Requested by {ctx.author.name}", icon_url=ctx.author.display_avatar.url)
        return embed

    async def _send_embed_response(self, ctx: commands.Context, title: str, description: str, color: discord.Color):
        """Helper to send embed responses, using Utils cog if available."""
        utils_cog = self.bot.get_cog('Utils')
        if utils_cog:
            embed = utils_cog.create_embed(ctx, title=title, description=description, color=color)
        else:
            embed = self._create_fallback_embed(title=title, description=description, color=color, ctx=ctx)
        await ctx.send(embed=embed)

    def load_autoroles(self):
        """Loads auto-role configurations from the JSON file."""
        if os.path.exists(AUTOROLES_FILE):
            try:
                with open(AUTOROLES_FILE, 'r') as f:
                    data = json.load(f)
                    self.autoroles = {int(k): int(v) for k, v in data.items()}
                print(f"[AutoRole DEBUG] Auto-roles loaded: {self.autoroles}")
            except (json.JSONDecodeError, TypeError, ValueError) as e:
                print(f"AutoRole: Error loading auto-roles from {AUTOROLES_FILE}: {e}")
                self.autoroles = {} 
        else:
            print(f"AutoRole: {AUTOROLES_FILE} not found. No auto-roles loaded initially.")
            self.autoroles = {}

    def _save_autoroles(self):
        """Saves the current auto-role configurations to the JSON file."""
        try:
            with open(AUTOROLES_FILE, 'w') as f:
                json.dump(self.autoroles, f, indent=4)
            print("[AutoRole DEBUG] Auto-roles saved.")
        except IOError as e:
            print(f"AutoRole: Error saving auto-roles to {AUTOROLES_FILE}: {e}")

    async def _get_autorole_obj(self, guild: discord.Guild) -> Optional[discord.Role]:
        """Gets the discord.Role object for the configured auto-role in a guild."""
        role_id = self.autoroles.get(guild.id)
        if role_id:
            role = guild.get_role(role_id)
            if role:
                return role
            else:
                print(f"[AutoRole DEBUG] Configured auto-role ID {role_id} for guild {guild.id} not found. Removing entry.")
                self.autoroles.pop(guild.id, None)
                self._save_autoroles()
        return None

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        """Automatically assigns the configured role to a new member."""
        guild = member.guild
        print(f"[AutoRole DEBUG] on_member_join: Member {member.id} joined guild {guild.id}")

        auto_role = await self._get_autorole_obj(guild)
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

            modlog_cog = self.bot.get_cog('ModLog') # Assuming you might have a ModLog cog
            if modlog_cog:
                try:
                    await modlog_cog.log_moderation_action(
                        guild=guild,
                        action_title="Auto-Role Assigned",
                        target_user=member,
                        moderator=self.bot.user, 
                        reason=f"New member join (Role: '{auto_role.name}')", # Use role name
                        color=discord.Color.teal()
                    )
                except Exception as e:
                    print(f"[AutoRole DEBUG] Failed to log auto-role assignment to ModLog: {e}")

        except discord.Forbidden:
            print(f"[AutoRole DEBUG] on_member_join: FORBIDDEN to assign auto-role '{auto_role.name}' to {member.name} in guild {guild.id}.")
        except discord.HTTPException as e:
            print(f"[AutoRole DEBUG] on_member_join: HTTPException while assigning auto-role to {member.name}: {e}")
        except Exception as e:
            print(f"[AutoRole DEBUG] on_member_join: Unexpected error assigning auto-role: {e}")
            traceback.print_exc()


    @commands.group(name="autorole", invoke_without_command=True)
    @commands.has_permissions(manage_roles=True) 
    @commands.guild_only()
    async def autorole_group(self, ctx: commands.Context):
        """Manages the auto-role for new members."""
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
        """Sets or updates the role automatically assigned to new members."""
        title = "Auto-Role Set"
        color = discord.Color.red() # Default to error color

        if role >= ctx.guild.me.top_role:
            description = f"❌ I cannot set the role '{role.name}' as the auto-role because it is higher than or equal to my highest role. Please adjust role positions."
        elif role.is_default(): 
            description = "❌ The `@everyone` role cannot be set as an auto-role."
        elif role.is_integration() or role.is_bot_managed():
            description = f"❌ The role '{role.name}' is managed by an integration or a bot and cannot be set as an auto-role by me."
        else:
            self.autoroles[ctx.guild.id] = role.id
            self._save_autoroles()
            description = f"✅ New members will now automatically be assigned the **'{role.name}'** role."
            color = discord.Color.green()
            print(f"[AutoRole DEBUG] Auto-role for guild {ctx.guild.id} set to {role.name} ({role.id})")
        
        await self._send_embed_response(ctx, title, description, color)


    @autorole_group.command(name="remove", aliases=["disable", "off"])
    @commands.has_permissions(manage_roles=True)
    @commands.guild_only()
    async def autorole_remove(self, ctx: commands.Context):
        """Disables the auto-role feature for new members."""
        title = "Auto-Role Remove"
        color = discord.Color.orange()
        if ctx.guild.id in self.autoroles:
            removed_role_id = self.autoroles.pop(ctx.guild.id)
            self._save_autoroles()
            role_obj = ctx.guild.get_role(removed_role_id)
            role_name_msg = f" (was '{role_obj.name}')" if role_obj else ""
            description = f"ℹ️ Auto-role has been disabled for new members{role_name_msg}."
            print(f"[AutoRole DEBUG] Auto-role for guild {ctx.guild.id} removed.")
        else:
            description = "ℹ️ Auto-role is not currently enabled on this server."
        await self._send_embed_response(ctx, title, description, color)

    @autorole_group.command(name="status", aliases=["view", "current"])
    @commands.has_permissions(manage_roles=True) 
    @commands.guild_only()
    async def autorole_status(self, ctx: commands.Context):
        """Shows the currently configured auto-role."""
        current_auto_role = await self._get_autorole_obj(ctx.guild)
        title = "Auto-Role Status"
        if current_auto_role:
            description = f"ℹ️ The current auto-role for new members is **'{current_auto_role.name}'**."
        else:
            description = "ℹ️ No auto-role is currently configured for new members."
        await self._send_embed_response(ctx, title, description, discord.Color.blue())

    # --- Error Handlers ---
    async def _handle_error(self, ctx: commands.Context, error_title: str, error_description: str):
        """Helper to send standardized error embeds."""
        await self._send_embed_response(ctx, error_title, f"❌ {error_description}", discord.Color.red())

    @autorole_group.error
    async def autorole_group_error(self, ctx, error):
        if isinstance(error, commands.MissingPermissions):
            await self._handle_error(ctx, "Permission Denied", "You need 'Manage Roles' permission to use auto-role commands.")
        elif isinstance(error, commands.NoPrivateMessage):
            await self._handle_error(ctx, "Command Error", "This command cannot be used in private messages.")
        else:
            await self._handle_error(ctx, "Auto-Role Error", f"An unexpected error occurred: {error}")
            print(f"Error in autorole_group: {error}"); traceback.print_exc()

    @autorole_set.error
    async def autorole_set_error(self, ctx, error):
        error_title = "Set Auto-Role Error"
        if isinstance(error, commands.MissingPermissions):
            await self._handle_error(ctx, error_title, "You need 'Manage Roles' permission to set the auto-role.")
        elif isinstance(error, commands.BotMissingPermissions):
            desc = "I am missing the 'Manage Roles' permission." if 'manage_roles' in error.missing_permissions else f"I am missing permissions: {', '.join(error.missing_permissions)}."
            await self._handle_error(ctx, error_title, desc)
        elif isinstance(error, commands.RoleNotFound):
            await self._handle_error(ctx, error_title, f"Role not found: `{error.argument}`. Please provide a valid role name, ID, or mention.")
        elif isinstance(error, commands.MissingRequiredArgument) and error.param.name == "role":
            await self._handle_error(ctx, error_title, "You need to specify a role. Usage: `.autorole set @RoleName`")
        elif isinstance(error, commands.BadArgument):
            await self._handle_error(ctx, error_title, "Invalid argument. Please provide a valid role.")
        else:
            await self._handle_error(ctx, error_title, f"An unexpected error occurred: {error}")
            print(f"Error in autorole_set: {error}"); traceback.print_exc()

    @autorole_remove.error
    async def autorole_remove_error(self, ctx, error):
        error_title = "Remove Auto-Role Error"
        if isinstance(error, commands.MissingPermissions):
            await self._handle_error(ctx, error_title, "You need 'Manage Roles' permission to remove the auto-role setting.")
        else:
            await self._handle_error(ctx, error_title, f"An unexpected error occurred: {error}")
            print(f"Error in autorole_remove: {error}"); traceback.print_exc()
            
    @autorole_status.error # Added error handler for status command
    async def autorole_status_error(self, ctx, error):
        error_title = "Auto-Role Status Error"
        if isinstance(error, commands.MissingPermissions):
            await self._handle_error(ctx, error_title, "You need 'Manage Roles' permission to view the auto-role status.")
        else:
            await self._handle_error(ctx, error_title, f"An unexpected error occurred: {error}")
            print(f"Error in autorole_status: {error}"); traceback.print_exc()


async def setup(bot: commands.Bot):
    await bot.add_cog(AutoRole(bot))
    print("Cog 'AutoRole' (Embed Responses) loaded successfully.")

