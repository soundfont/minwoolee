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

    def load_autoroles(self):
        """Loads auto-role configurations from the JSON file."""
        if os.path.exists(AUTOROLES_FILE):
            try:
                with open(AUTOROLES_FILE, 'r') as f:
                    data = json.load(f)
                    # Ensure keys (guild_id) and values (role_id) are integers
                    self.autoroles = {int(k): int(v) for k, v in data.items()}
                print(f"[AutoRole DEBUG] Auto-roles loaded: {self.autoroles}")
            except (json.JSONDecodeError, TypeError, ValueError) as e:
                print(f"AutoRole: Error loading auto-roles from {AUTOROLES_FILE}: {e}")
                self.autoroles = {} # Reset to empty if file is corrupt or has invalid data
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
                # Role ID was configured but role not found (deleted?)
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

        # Check bot permissions and role hierarchy
        if not guild.me.guild_permissions.manage_roles:
            print(f"[AutoRole DEBUG] on_member_join: Bot missing 'Manage Roles' permission in guild {guild.id}.")
            # Optionally, notify an admin channel if this happens consistently
            return
        
        if auto_role >= guild.me.top_role:
            print(f"[AutoRole DEBUG] on_member_join: Auto-role '{auto_role.name}' is higher than or equal to my top role in guild {guild.id}. Cannot assign.")
            # Optionally, notify an admin channel
            return

        try:
            await member.add_roles(auto_role, reason="Auto-role on join")
            print(f"[AutoRole DEBUG] Successfully assigned '{auto_role.name}' to {member.name} in guild {guild.id}.")

            # Optional: Log this action to your ModLog cog if you have one and want to log auto-role assignments
            modlog_cog = self.bot.get_cog('ModLog')
            if modlog_cog:
                try:
                    await modlog_cog.log_moderation_action(
                        guild=guild,
                        action_title="Auto-Role Assigned",
                        target_user=member,
                        moderator=self.bot.user, # Action performed by the bot
                        reason=f"New member join (Role: {auto_role.name})",
                        color=discord.Color.teal()
                    )
                except Exception as e:
                    print(f"[AutoRole DEBUG] Failed to log auto-role assignment to ModLog: {e}")

        except discord.Forbidden:
            print(f"[AutoRole DEBUG] on_member_join: FORBIDDEN to assign auto-role '{auto_role.name}' to {member.name} in guild {guild.id}. (Likely hierarchy or specific override)")
        except discord.HTTPException as e:
            print(f"[AutoRole DEBUG] on_member_join: HTTPException while assigning auto-role to {member.name}: {e}")
        except Exception as e:
            print(f"[AutoRole DEBUG] on_member_join: Unexpected error assigning auto-role: {e}")
            traceback.print_exc()


    @commands.group(name="autorole", invoke_without_command=True)
    @commands.has_permissions(manage_roles=True) # User needs Manage Roles to configure
    @commands.guild_only()
    async def autorole_group(self, ctx: commands.Context):
        """Manages the auto-role for new members.
        Use `.autorole set @RoleName`, `.autorole remove`, or `.autorole status`.
        """
        if ctx.invoked_subcommand is None:
            current_auto_role = await self._get_autorole_obj(ctx.guild)
            if current_auto_role:
                await ctx.send(f"ℹ️ The current auto-role for new members is {current_auto_role.mention}.")
            else:
                await ctx.send("ℹ️ No auto-role is currently configured for new members.\n"
                               "Use `.autorole set @RoleName` to set one.")

    @autorole_group.command(name="set")
    @commands.has_permissions(manage_roles=True)
    @commands.bot_has_permissions(manage_roles=True) # Bot needs this to verify it can assign
    @commands.guild_only()
    async def autorole_set(self, ctx: commands.Context, role: discord.Role):
        """Sets or updates the role automatically assigned to new members.
        Usage: .autorole set @RoleName
        """
        # Hierarchy check: Bot's top role must be higher than the role to be auto-assigned.
        if role >= ctx.guild.me.top_role:
            await ctx.send(f"❌ I cannot set {role.mention} as the auto-role because it is higher than or equal to my highest role. Please adjust role positions.")
            return
        
        # Check if the role is @everyone or an integration-managed role (like bot roles)
        if role.is_default(): # @everyone
            await ctx.send("❌ The `@everyone` role cannot be set as an auto-role.")
            return
        if role.is_integration() or role.is_bot_managed():
            await ctx.send(f"❌ The role {role.mention} is managed by an integration or a bot and cannot be set as an auto-role by me.")
            return


        self.autoroles[ctx.guild.id] = role.id
        self._save_autoroles()
        await ctx.send(f"✅ New members will now automatically be assigned the {role.mention} role.")
        print(f"[AutoRole DEBUG] Auto-role for guild {ctx.guild.id} set to {role.name} ({role.id})")

    @autorole_group.command(name="remove", aliases=["disable", "off"])
    @commands.has_permissions(manage_roles=True)
    @commands.guild_only()
    async def autorole_remove(self, ctx: commands.Context):
        """Disables the auto-role feature for new members."""
        if ctx.guild.id in self.autoroles:
            removed_role_id = self.autoroles.pop(ctx.guild.id)
            self._save_autoroles()
            # Try to get role name for user feedback
            role_obj = ctx.guild.get_role(removed_role_id)
            role_name_msg = f" (was {role_obj.mention})" if role_obj else ""
            await ctx.send(f"ℹ️ Auto-role has been disabled for new members{role_name_msg}.")
            print(f"[AutoRole DEBUG] Auto-role for guild {ctx.guild.id} removed.")
        else:
            await ctx.send("ℹ️ Auto-role is not currently enabled on this server.")

    @autorole_group.command(name="status", aliases=["view", "current"])
    @commands.has_permissions(manage_roles=True) # Or no specific perm if just viewing is fine
    @commands.guild_only()
    async def autorole_status(self, ctx: commands.Context):
        """Shows the currently configured auto-role."""
        current_auto_role = await self._get_autorole_obj(ctx.guild)
        if current_auto_role:
            await ctx.send(f"ℹ️ The current auto-role for new members is {current_auto_role.mention}.")
        else:
            await ctx.send("ℹ️ No auto-role is currently configured for new members.")

    # --- Error Handlers ---
    @autorole_group.error
    async def autorole_group_error(self, ctx, error):
        if isinstance(error, commands.MissingPermissions):
            await ctx.send("❌ You need 'Manage Roles' permission to use auto-role commands.")
        elif isinstance(error, commands.NoPrivateMessage):
            await ctx.send("❌ This command cannot be used in private messages.")
        else:
            await ctx.send(f"An error occurred with the autorole command: {error}")
            print(f"Error in autorole_group: {error}")
            traceback.print_exc()

    @autorole_set.error
    async def autorole_set_error(self, ctx, error):
        if isinstance(error, commands.MissingPermissions):
            await ctx.send("❌ You need 'Manage Roles' permission to set the auto-role.")
        elif isinstance(error, commands.BotMissingPermissions):
            if 'manage_roles' in error.missing_permissions:
                 await ctx.send("❌ I am missing the 'Manage Roles' permission. I need it to verify I can assign the role.")
            else:
                 await ctx.send(f"❌ I am missing the following permissions: {', '.join(error.missing_permissions)}.")
        elif isinstance(error, commands.RoleNotFound):
            await ctx.send(f"❌ Role not found: `{error.argument}`. Please provide a valid role name, ID, or mention.")
        elif isinstance(error, commands.MissingRequiredArgument):
            if error.param.name == "role":
                 await ctx.send("❌ You need to specify a role. Usage: `.autorole set @RoleName`")
        elif isinstance(error, commands.BadArgument): # Catches if not a Role
             await ctx.send(f"❌ Invalid argument. Please provide a valid role.")
        else:
            await ctx.send(f"An error occurred while setting the auto-role: {error}")
            print(f"Error in autorole_set: {error}")
            traceback.print_exc()

    @autorole_remove.error
    async def autorole_remove_error(self, ctx, error):
        if isinstance(error, commands.MissingPermissions):
            await ctx.send("❌ You need 'Manage Roles' permission to remove the auto-role setting.")
        else:
            await ctx.send(f"An error occurred while removing the auto-role: {error}")
            print(f"Error in autorole_remove: {error}")
            traceback.print_exc()

async def setup(bot: commands.Bot):
    # Ensure necessary intents are enabled in your main bot file:
    # intents = discord.Intents.default()
    # intents.members = True # Crucial for on_member_join
    await bot.add_cog(AutoRole(bot))
    print("Cog 'AutoRole' loaded successfully.")

