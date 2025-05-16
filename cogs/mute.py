import discord
from discord.ext import commands
import traceback

# --- Configuration ---
MUTE_ROLE_NAME = "Muted"
# Permissions to DENY for the Muted role (both server-level and in channel overwrites)
PERMISSIONS_TO_DENY = {
    "attach_files": False,
    "embed_links": False,
    "add_reactions": False,
    "use_external_emojis": False,
    # Consider also denying message sending if you want a full text + media mute.
    # "send_messages": False,
    # "send_messages_in_threads": False,
}

class Mute(commands.Cog):
    """
    Manages a role-based mute specifically for restricting media (images, embeds)
    and reactions. It ensures the Muted role has the correct server permissions
    and applies channel-specific overwrites for maximum effectiveness.
    """
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def _ensure_mute_role_setup(self, guild: discord.Guild) -> discord.Role | None:
        """
        Ensures the Muted role exists, has correct server-level permissions,
        and applies necessary channel overwrites.
        Returns the Muted role object, or None if setup fails.
        """
        mute_role = discord.utils.get(guild.roles, name=MUTE_ROLE_NAME)

        # 1. Define desired server-level permissions for the Muted role
        desired_server_permissions = guild.default_role.permissions # Start with @everyone perms
        desired_server_permissions.update(**PERMISSIONS_TO_DENY)

        if mute_role:
            # 1a. If role exists, check and update its server-level permissions if needed
            if mute_role.permissions != desired_server_permissions:
                print(f"'{MUTE_ROLE_NAME}' in '{guild.name}': Server permissions differ. Updating...")
                try:
                    await mute_role.edit(
                        permissions=desired_server_permissions,
                        reason=f"Ensuring '{MUTE_ROLE_NAME}' has correct server-level permissions."
                    )
                    print(f"'{MUTE_ROLE_NAME}' in '{guild.name}': Server permissions updated.")
                except discord.Forbidden:
                    print(f"'{MUTE_ROLE_NAME}' in '{guild.name}': Bot lacks permission to edit role (server perms).")
                    # Continue, channel overwrites are more critical.
                except discord.HTTPException as e:
                    print(f"'{MUTE_ROLE_NAME}' in '{guild.name}': HTTP error updating server permissions: {e}")
                except Exception as e:
                    print(f"'{MUTE_ROLE_NAME}' in '{guild.name}': Unexpected error updating server permissions: {e}")
                    traceback.print_exc()
        else:
            # 1b. If role doesn't exist, create it with desired server-level permissions
            print(f"'{MUTE_ROLE_NAME}' not found in '{guild.name}'. Attempting to create...")
            try:
                mute_role = await guild.create_role(
                    name=MUTE_ROLE_NAME,
                    permissions=desired_server_permissions,
                    reason=f"Creating '{MUTE_ROLE_NAME}' for media/reaction restrictions."
                )
                print(f"'{MUTE_ROLE_NAME}' created in '{guild.name}'.")
                # Optional: Notify in system channel
                if guild.system_channel and guild.me.permissions_in(guild.system_channel).send_messages:
                    await guild.system_channel.send(
                        f"The '{MUTE_ROLE_NAME}' role has been automatically created/configured. "
                        "Please review its position in the role hierarchy."
                    )
            except discord.Forbidden:
                print(f"'{MUTE_ROLE_NAME}' in '{guild.name}': Bot lacks 'Manage Roles' to create role.")
                return None
            except discord.HTTPException as e:
                print(f"'{MUTE_ROLE_NAME}' in '{guild.name}': HTTP error creating role: {e}")
                return None
            except Exception as e:
                print(f"'{MUTE_ROLE_NAME}' in '{guild.name}': Unexpected error creating role: {e}")
                traceback.print_exc()
                return None

        if not mute_role: # If creation failed
            return None

        # 2. Apply/Verify channel-specific overwrites for the Muted role
        # This is the most critical part for overriding conflicting role permissions.
        overwrite_for_channels = discord.PermissionOverwrite(**PERMISSIONS_TO_DENY)
        
        print(f"'{MUTE_ROLE_NAME}' in '{guild.name}': Applying/verifying channel overwrites...")
        processed_channels = 0
        for channel in guild.text_channels: # Or guild.channels if you want to include voice later
            try:
                # Bot needs manage_roles permission in the channel (inherited or explicit) to set role overwrites
                if channel.permissions_for(guild.me).manage_roles:
                    current_channel_overwrite = channel.overwrites_for(mute_role)
                    
                    needs_update = False
                    for perm_name, perm_value in PERMISSIONS_TO_DENY.items():
                        if getattr(current_channel_overwrite, perm_name) != perm_value:
                            needs_update = True
                            break
                    
                    if needs_update:
                        await channel.set_permissions(
                            mute_role,
                            overwrite=overwrite_for_channels,
                            reason=f"Enforcing '{MUTE_ROLE_NAME}' restrictions in channel."
                        )
                        # print(f"Applied/Updated overwrites for '{MUTE_ROLE_NAME}' in channel #{channel.name}")
                    processed_channels += 1
                else:
                    print(f"Skipping channel #{channel.name} for '{MUTE_ROLE_NAME}' overwrites: Bot lacks Manage Roles permission there.")
            except discord.Forbidden:
                print(f"Forbidden to set overwrites for '{MUTE_ROLE_NAME}' in channel #{channel.name}.")
            except discord.HTTPException as e:
                print(f"HTTP error setting overwrites for '{MUTE_ROLE_NAME}' in #{channel.name}: {e}")
            except Exception as e:
                print(f"Unexpected error with channel overwrites for '{MUTE_ROLE_NAME}' in #{channel.name}: {e}")
                traceback.print_exc()
        
        print(f"'{MUTE_ROLE_NAME}' in '{guild.name}': Channel overwrite process completed for {processed_channels} text channels.")
        return mute_role

    @commands.command(name="mute")
    @commands.has_permissions(moderate_members=True)
    @commands.bot_has_permissions(manage_roles=True) # manage_roles is needed for role assignment AND channel overwrites
    async def mute_command(self, ctx: commands.Context, member: discord.Member, *, reason: str = "Not specified"):
        """
        Mutes a member by restricting media/reactions using the Muted role and channel overwrites.
        Usage: .mute <@member/ID> [reason]
        """
        utils_cog = self.bot.get_cog('Utils') # Assumes 'Utils' cog for embeds
        if not utils_cog:
            await ctx.send("Error: Utils cog is not loaded, cannot create embeds.")
            return

        # Ensure the Muted role is correctly set up server-wide and in channels
        mute_role = await self._ensure_mute_role_setup(ctx.guild)
        if not mute_role:
            await ctx.send(embed=utils_cog.create_embed(ctx, title="Mute Failed",
                                                       description=f"The '{MUTE_ROLE_NAME}' role could not be properly configured. "
                                                                   "Check bot permissions ('Manage Roles' server-wide and for channels) "
                                                                   "and console logs for details.",
                                                       color=discord.Color.red()))
            return

        # --- Standard Checks ---
        if member.id == ctx.guild.owner_id:
            await ctx.send(embed=utils_cog.create_embed(ctx, title="Error", description="The server owner cannot be muted.", color=discord.Color.red()))
            return
        if member.id == ctx.author.id and ctx.guild.owner_id != ctx.author.id : # Prevent self-mute unless owner is muting self (edge case)
            await ctx.send(embed=utils_cog.create_embed(ctx, title="Error", description="You cannot mute yourself.", color=discord.Color.red()))
            return
        if member.bot:
            await ctx.send(embed=utils_cog.create_embed(ctx, title="Error", description="Bots cannot be muted with this command.", color=discord.Color.red()))
            return
        if member.top_role >= ctx.author.top_role and ctx.guild.owner_id != ctx.author.id:
            await ctx.send(embed=utils_cog.create_embed(ctx, title="Hierarchy Error", description="You cannot mute a member with a role equal to or higher than yours.", color=discord.Color.red()))
            return
        if mute_role >= ctx.guild.me.top_role:
            await ctx.send(embed=utils_cog.create_embed(ctx, title="Hierarchy Error", description=f"My role is not high enough to assign or manage the '{MUTE_ROLE_NAME}' role. Please adjust role positions.", color=discord.Color.red()))
            return
        if member.top_role >= ctx.guild.me.top_role:
            await ctx.send(embed=utils_cog.create_embed(ctx, title="Hierarchy Error", description=f"I cannot mute {member.mention} as their highest role is equal to or higher than mine.", color=discord.Color.red()))
            return

        if mute_role in member.roles:
            # If already has the role, re-run setup to ensure channel overwrites are still correct
            print(f"User {member.display_name} already has '{MUTE_ROLE_NAME}'. Re-verifying role/channel setup.")
            await self._ensure_mute_role_setup(ctx.guild) 
            await ctx.send(embed=utils_cog.create_embed(ctx, title="Already Muted", description=f"{member.mention} already has the '{MUTE_ROLE_NAME}' role. Permissions re-verified.", color=discord.Color.orange()))
            return

        try:
            await member.add_roles(mute_role, reason=f"Muted by {ctx.author.display_name} for: {reason}")
            # _ensure_mute_role_setup was called before, so channel overwrites should be in place.

            embed = utils_cog.create_embed(ctx, title="Member Muted (Media/Reactions)",
                                           description=f"{member.mention} has been muted, restricting media and reactions.",
                                           color=discord.Color.green())
            embed.add_field(name="Reason", value=reason, inline=False)
            await ctx.send(embed=embed)

            history_cog = self.bot.get_cog('History') # Assumes 'History' cog
            if history_cog:
                history_cog.log_action(ctx.guild.id, member.id, f"Muted (Media/Reactions - Role: {MUTE_ROLE_NAME})", ctx.author, reason)

        except discord.Forbidden:
            await ctx.send(embed=utils_cog.create_embed(ctx, title="Permissions Error", description=f"Failed to assign the '{MUTE_ROLE_NAME}' role. Check my 'Manage Roles' permission and role hierarchy.", color=discord.Color.red()))
        except discord.HTTPException as e:
            await ctx.send(embed=utils_cog.create_embed(ctx, title="API Error", description=f"An error occurred while muting: {e}", color=discord.Color.red()))
        except Exception as e:
            traceback.print_exc()
            await ctx.send(embed=utils_cog.create_embed(ctx, title="Unexpected Mute Error", description=f"An unexpected error occurred: {e}", color=discord.Color.red()))

    @commands.command(name="unmute")
    @commands.has_permissions(moderate_members=True)
    @commands.bot_has_permissions(manage_roles=True)
    async def un_mute_command(self, ctx: commands.Context, member: discord.Member, *, reason: str = "Not specified"):
        """
        Unmutes a member by removing the Muted role for media/reactions.
        Usage: .unmute <@member/ID> [reason]
        """
        utils_cog = self.bot.get_cog('Utils')
        if not utils_cog:
            await ctx.send("Error: Utils cog is not loaded.")
            return

        mute_role = discord.utils.get(ctx.guild.roles, name=MUTE_ROLE_NAME)
        if not mute_role:
            await ctx.send(embed=utils_cog.create_embed(ctx, title="Unmute Failed", description=f"The '{MUTE_ROLE_NAME}' role doesn't exist in this server.", color=discord.Color.red()))
            return
        
        if mute_role not in member.roles:
            await ctx.send(embed=utils_cog.create_embed(ctx, title="Not Muted", description=f"{member.mention} does not currently have the '{MUTE_ROLE_NAME}' role.", color=discord.Color.orange()))
            return

        if mute_role >= ctx.guild.me.top_role: # Bot must be able to manage Muted role
            await ctx.send(embed=utils_cog.create_embed(ctx, title="Hierarchy Error", description=f"My role is not high enough to remove the '{MUTE_ROLE_NAME}' role.", color=discord.Color.red()))
            return
            
        try:
            await member.remove_roles(mute_role, reason=f"Unmuted by {ctx.author.display_name} for: {reason}")
            # Channel overwrites for the Muted role remain on the role itself; they don't apply to the user once the role is removed.
            embed = utils_cog.create_embed(ctx, title="Member Unmuted (Media/Reactions)",
                                           description=f"{member.mention} has been unmuted from media/reaction restrictions.",
                                           color=discord.Color.green())
            embed.add_field(name="Reason", value=reason, inline=False)
            await ctx.send(embed=embed)

            history_cog = self.bot.get_cog('History')
            if history_cog:
                history_cog.log_action(ctx.guild.id, member.id, f"Unmuted (Media/Reactions - Role: {MUTE_ROLE_NAME})", ctx.author, reason)

        except discord.Forbidden:
            await ctx.send(embed=utils_cog.create_embed(ctx, title="Permissions Error", description=f"Failed to remove the '{MUTE_ROLE_NAME}' role. Check my 'Manage Roles' permission and role hierarchy.", color=discord.Color.red()))
        except discord.HTTPException as e:
            await ctx.send(embed=utils_cog.create_embed(ctx, title="API Error", description=f"An error occurred while unmuting: {e}", color=discord.Color.red()))
        except Exception as e:
            traceback.print_exc()
            await ctx.send(embed=utils_cog.create_embed(ctx, title="Unexpected Unmute Error", description=f"An unexpected error occurred: {e}", color=discord.Color.red()))

    @commands.command(name="mutedlist")
    @commands.has_permissions(manage_messages=True) # Or appropriate moderation permission
    async def muted_list_command(self, ctx: commands.Context):
        """Displays a list of members who currently have the Muted role."""
        utils_cog = self.bot.get_cog('Utils')
        if not utils_cog: await ctx.send("Error: Utils cog not loaded."); return

        mute_role = discord.utils.get(ctx.guild.roles, name=MUTE_ROLE_NAME)
        if not mute_role:
            await ctx.send(embed=utils_cog.create_embed(ctx, title="Muted List", description=f"The '{MUTE_ROLE_NAME}' role does not exist in this server."))
            return

        muted_members = [m for m in ctx.guild.members if mute_role in m.roles]

        if not muted_members:
            await ctx.send(embed=utils_cog.create_embed(ctx, title="Muted List", description=f"No members currently have the '{MUTE_ROLE_NAME}' role."))
            return

        description = "\n".join([f"- {member.mention} ({member.id})" for member in muted_members])
        embed = utils_cog.create_embed(ctx, title=f"Members with '{MUTE_ROLE_NAME}' Role ({len(muted_members)})", description=description)
        await ctx.send(embed=embed)

    # --- Error Handlers ---
    @mute_command.error
    async def mute_command_error(self, ctx, error):
        utils_cog = self.bot.get_cog('Utils')
        embed = utils_cog.create_embed(ctx, title="Mute Command Error", color=discord.Color.red()) if utils_cog else None
        
        if isinstance(error, commands.MissingPermissions):
            desc = "You need 'Moderate Members' permission to use this."
        elif isinstance(error, commands.BotMissingPermissions):
            desc = f"I'm missing 'Manage Roles' permission. I need it to manage the mute role and channel permissions. (Missing: {', '.join(error.missing_permissions)})"
        elif isinstance(error, commands.MemberNotFound):
            desc = f"Member '{error.argument}' not found."
        elif isinstance(error, commands.MissingRequiredArgument):
            desc = f"You missed an argument: {error.param.name}. Usage: `.mute <member> [reason]`"
        elif isinstance(error, commands.CommandInvokeError):
            print(f"Error in mute_command: {error.original}")
            traceback.print_exc()
            desc = "An internal error occurred while trying to mute. Please check my console."
        else:
            desc = f"An unexpected error occurred: {error}"

        if embed:
            embed.description = desc
            await ctx.send(embed=embed)
        else:
            await ctx.send(f"Mute Command Error: {desc}")

    @un_mute_command.error
    async def un_mute_command_error(self, ctx, error):
        utils_cog = self.bot.get_cog('Utils')
        embed = utils_cog.create_embed(ctx, title="Unmute Command Error", color=discord.Color.red()) if utils_cog else None

        if isinstance(error, commands.MissingPermissions):
            desc = "You need 'Moderate Members' permission to use this."
        elif isinstance(error, commands.BotMissingPermissions):
            desc = f"I'm missing 'Manage Roles' permission. (Missing: {', '.join(error.missing_permissions)})"
        elif isinstance(error, commands.MemberNotFound):
            desc = f"Member '{error.argument}' not found."
        elif isinstance(error, commands.MissingRequiredArgument):
            desc = f"You missed an argument: {error.param.name}. Usage: `.unmute <member> [reason]`"
        elif isinstance(error, commands.CommandInvokeError):
            print(f"Error in un_mute_command: {error.original}")
            traceback.print_exc()
            desc = "An internal error occurred while trying to unmute. Please check my console."
        else:
            desc = f"An unexpected error occurred: {error}"
            
        if embed:
            embed.description = desc
            await ctx.send(embed=embed)
        else:
            await ctx.send(f"Unmute Command Error: {desc}")

async def setup(bot: commands.Bot):
    await bot.add_cog(Mute(bot))
    print(f"Cog 'Mute (New Version)' loaded. It will manage '{MUTE_ROLE_NAME}'.")
