import discord
from discord.ext import commands
import traceback

# --- Configuration ---
MEDIA_MUTE_ROLE_NAME = "Media Muted"
# Permissions to DENY for the Media Muted role (both server-level and in channel overwrites)
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
    and reactions. It ensures the 'Media Muted' role has the correct server permissions
    and applies channel-specific overwrites for maximum effectiveness.
    """
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def _ensure_media_mute_role_setup(self, guild: discord.Guild) -> discord.Role | None:
        """
        Ensures the 'Media Muted' role exists, has correct server-level permissions,
        and applies necessary channel overwrites.
        Returns the 'Media Muted' role object, or None if setup fails.
        """
        media_mute_role = discord.utils.get(guild.roles, name=MEDIA_MUTE_ROLE_NAME)

        desired_server_permissions = guild.default_role.permissions
        desired_server_permissions.update(**PERMISSIONS_TO_DENY)

        # role_created_now = False # Flag not strictly needed with current logic flow

        if media_mute_role:
            if media_mute_role.permissions != desired_server_permissions:
                print(f"'{MEDIA_MUTE_ROLE_NAME}' in '{guild.name}': Server permissions differ. Updating...")
                try:
                    await media_mute_role.edit(
                        permissions=desired_server_permissions,
                        reason=f"Ensuring '{MEDIA_MUTE_ROLE_NAME}' has correct server-level permissions."
                    )
                    print(f"'{MEDIA_MUTE_ROLE_NAME}' in '{guild.name}': Server permissions updated.")
                except discord.Forbidden:
                    print(f"'{MEDIA_MUTE_ROLE_NAME}' in '{guild.name}': Bot lacks permission to edit role (server perms).")
                except discord.HTTPException as e:
                    print(f"'{MEDIA_MUTE_ROLE_NAME}' in '{guild.name}': HTTP error updating server permissions: {e}")
                except Exception as e:
                    print(f"'{MEDIA_MUTE_ROLE_NAME}' in '{guild.name}': Unexpected error updating server permissions: {e}")
                    traceback.print_exc()
        else:
            print(f"'{MEDIA_MUTE_ROLE_NAME}' not found in '{guild.name}'. Attempting to create...")
            try:
                media_mute_role = await guild.create_role(
                    name=MEDIA_MUTE_ROLE_NAME,
                    permissions=desired_server_permissions,
                    reason=f"Creating '{MEDIA_MUTE_ROLE_NAME}' for media/reaction restrictions."
                )
                print(f"'{MEDIA_MUTE_ROLE_NAME}' created in '{guild.name}'.")
                # role_created_now = True

                # --- CORRECTED SYSTEM CHANNEL CHECK ---
                if guild.system_channel: # Check if system_channel exists first
                    # Then check if bot can send messages there
                    if guild.system_channel.permissions_for(guild.me).send_messages:
                        try:
                            await guild.system_channel.send(
                                f"The '{MEDIA_MUTE_ROLE_NAME}' role has been automatically created/configured. "
                                "Please review its position in the role hierarchy."
                            )
                        except discord.Forbidden:
                            print(f"Could not send role creation notification to system channel in '{guild.name}' (Forbidden).")
                        except discord.HTTPException as e:
                            print(f"Could not send role creation notification to system channel in '{guild.name}' (HTTPException: {e}).")
                    else:
                        print(f"Bot lacks send_messages permission in system channel for '{guild.name}'.")
                else:
                    print(f"No system channel configured in '{guild.name}' to send role creation notification.")
                # --- END OF CORRECTION ---

            except discord.Forbidden:
                print(f"'{MEDIA_MUTE_ROLE_NAME}' in '{guild.name}': Bot lacks 'Manage Roles' to create role.")
                return None
            except discord.HTTPException as e:
                print(f"'{MEDIA_MUTE_ROLE_NAME}' in '{guild.name}': HTTP error creating role: {e}")
                return None
            except Exception as e:
                print(f"'{MEDIA_MUTE_ROLE_NAME}' in '{guild.name}': Unexpected error creating role: {e}")
                traceback.print_exc()
                return None

        if not media_mute_role: # If role still None after trying to find or create
            return None

        # Apply/Verify channel-specific overwrites
        overwrite_for_channels = discord.PermissionOverwrite(**PERMISSIONS_TO_DENY)
        
        print(f"'{MEDIA_MUTE_ROLE_NAME}' in '{guild.name}': Applying/verifying channel overwrites...")
        processed_channels = 0
        skipped_channels = 0
        failed_channels = 0

        for channel in guild.text_channels:
            try:
                if channel.permissions_for(guild.me).manage_roles:
                    current_channel_overwrite = channel.overwrites_for(media_mute_role)
                    needs_update = any(getattr(current_channel_overwrite, perm_name) != perm_value for perm_name, perm_value in PERMISSIONS_TO_DENY.items())
                    
                    if needs_update:
                        await channel.set_permissions(
                            media_mute_role,
                            overwrite=overwrite_for_channels,
                            reason=f"Enforcing '{MEDIA_MUTE_ROLE_NAME}' restrictions in channel."
                        )
                    processed_channels += 1 # Count as processed if no update needed or update succeeded
                else:
                    print(f"Skipping channel #{channel.name} for '{MEDIA_MUTE_ROLE_NAME}' overwrites: Bot lacks Manage Roles permission there.")
                    skipped_channels +=1
            except discord.Forbidden:
                print(f"Forbidden to set overwrites for '{MEDIA_MUTE_ROLE_NAME}' in channel #{channel.name}.")
                failed_channels +=1
            except discord.HTTPException as e:
                print(f"HTTP error setting overwrites for '{MEDIA_MUTE_ROLE_NAME}' in #{channel.name}: {e}")
                failed_channels +=1
            except Exception as e:
                print(f"Unexpected error with channel overwrites for '{MEDIA_MUTE_ROLE_NAME}' in #{channel.name}: {e}")
                traceback.print_exc()
                failed_channels +=1
        
        print(f"'{MEDIA_MUTE_ROLE_NAME}' in '{guild.name}': Channel overwrite process completed. Processed: {processed_channels}, Skipped: {skipped_channels}, Failed: {failed_channels}.")
        return media_mute_role

    @commands.command(name="mute") # Consider renaming to "mediamute" if desired
    @commands.has_permissions(moderate_members=True)
    @commands.bot_has_permissions(manage_roles=True) 
    async def mute_command(self, ctx: commands.Context, member: discord.Member, *, reason: str = "Not specified"):
        """
        Mutes a member by restricting media/reactions using the 'Media Muted' role.
        Usage: .mute <@member/ID> [reason]
        """
        utils_cog = self.bot.get_cog('Utils') 
        if not utils_cog:
            await ctx.send("Error: Utils cog is not loaded, cannot create embeds.")
            return

        media_mute_role = await self._ensure_media_mute_role_setup(ctx.guild)
        if not media_mute_role:
            await ctx.send(embed=utils_cog.create_embed(ctx, title="Mute Failed",
                                                       description=f"The '{MEDIA_MUTE_ROLE_NAME}' role could not be properly configured. "
                                                                   "Check bot permissions ('Manage Roles' server-wide and for channels) "
                                                                   "and console logs for details.",
                                                       color=discord.Color.red()))
            return

        # Standard Checks
        if member.id == ctx.guild.owner_id:
            await ctx.send(embed=utils_cog.create_embed(ctx, title="Error", description="The server owner cannot be muted.", color=discord.Color.red()))
            return
        if member.id == ctx.author.id and ctx.guild.owner_id != ctx.author.id:
            await ctx.send(embed=utils_cog.create_embed(ctx, title="Error", description="You cannot mute yourself.", color=discord.Color.red()))
            return
        if member.bot:
            await ctx.send(embed=utils_cog.create_embed(ctx, title="Error", description="Bots cannot be muted with this command.", color=discord.Color.red()))
            return
        if member.top_role >= ctx.author.top_role and ctx.guild.owner_id != ctx.author.id:
            await ctx.send(embed=utils_cog.create_embed(ctx, title="Hierarchy Error", description="You cannot mute a member with a role equal to or higher than yours.", color=discord.Color.red()))
            return
        if media_mute_role >= ctx.guild.me.top_role:
            await ctx.send(embed=utils_cog.create_embed(ctx, title="Hierarchy Error", description=f"My role is not high enough to assign or manage the '{MEDIA_MUTE_ROLE_NAME}' role.", color=discord.Color.red()))
            return
        if member.top_role >= ctx.guild.me.top_role:
            await ctx.send(embed=utils_cog.create_embed(ctx, title="Hierarchy Error", description=f"I cannot mute {member.mention} as their highest role is equal to or higher than mine.", color=discord.Color.red()))
            return

        if media_mute_role in member.roles:
            print(f"User {member.display_name} already has '{MEDIA_MUTE_ROLE_NAME}'. Re-verifying role/channel setup.")
            await self._ensure_media_mute_role_setup(ctx.guild) 
            await ctx.send(embed=utils_cog.create_embed(ctx, title="Already Media Muted", description=f"{member.mention} already has the '{MEDIA_MUTE_ROLE_NAME}' role. Permissions re-verified.", color=discord.Color.orange()))
            return

        try:
            await member.add_roles(media_mute_role, reason=f"Media Muted by {ctx.author.display_name} for: {reason}")
            
            embed = utils_cog.create_embed(ctx, title="Member Media Muted",
                                           description=f"{member.mention} has been '{MEDIA_MUTE_ROLE_NAME}', restricting media and reactions.",
                                           color=discord.Color.green())
            embed.add_field(name="Reason", value=reason, inline=False)
            await ctx.send(embed=embed)

            history_cog = self.bot.get_cog('History')
            if history_cog:
                history_cog.log_action(ctx.guild.id, member.id, f"Media Muted (Role: {MEDIA_MUTE_ROLE_NAME})", ctx.author, reason)

        except discord.Forbidden:
            await ctx.send(embed=utils_cog.create_embed(ctx, title="Permissions Error", description=f"Failed to assign the '{MEDIA_MUTE_ROLE_NAME}' role.", color=discord.Color.red()))
        except discord.HTTPException as e:
            await ctx.send(embed=utils_cog.create_embed(ctx, title="API Error", description=f"An error occurred while applying media mute: {e}", color=discord.Color.red()))
        except Exception as e:
            traceback.print_exc()
            await ctx.send(embed=utils_cog.create_embed(ctx, title="Unexpected Mute Error", description=f"An unexpected error occurred: {e}", color=discord.Color.red()))

    @commands.command(name="unmute") # Consider renaming to "unmediamute"
    @commands.has_permissions(moderate_members=True)
    @commands.bot_has_permissions(manage_roles=True)
    async def un_mute_command(self, ctx: commands.Context, member: discord.Member, *, reason: str = "Not specified"):
        """
        Unmutes a member by removing the 'Media Muted' role.
        Usage: .unmute <@member/ID> [reason]
        """
        utils_cog = self.bot.get_cog('Utils')
        if not utils_cog:
            await ctx.send("Error: Utils cog is not loaded.")
            return

        media_mute_role = discord.utils.get(ctx.guild.roles, name=MEDIA_MUTE_ROLE_NAME)
        if not media_mute_role:
            await ctx.send(embed=utils_cog.create_embed(ctx, title="Unmute Failed", description=f"The '{MEDIA_MUTE_ROLE_NAME}' role doesn't exist.", color=discord.Color.red()))
            return
        
        if media_mute_role not in member.roles:
            await ctx.send(embed=utils_cog.create_embed(ctx, title="Not Media Muted", description=f"{member.mention} does not have the '{MEDIA_MUTE_ROLE_NAME}' role.", color=discord.Color.orange()))
            return

        if media_mute_role >= ctx.guild.me.top_role:
            await ctx.send(embed=utils_cog.create_embed(ctx, title="Hierarchy Error", description=f"My role is not high enough to remove the '{MEDIA_MUTE_ROLE_NAME}' role.", color=discord.Color.red()))
            return
            
        try:
            await member.remove_roles(media_mute_role, reason=f"Media Unmuted by {ctx.author.display_name} for: {reason}")
            embed = utils_cog.create_embed(ctx, title="Member Media Unmuted",
                                           description=f"{member.mention}'s media/reaction restrictions have been lifted.",
                                           color=discord.Color.green())
            embed.add_field(name="Reason", value=reason, inline=False)
            await ctx.send(embed=embed)

            history_cog = self.bot.get_cog('History')
            if history_cog:
                history_cog.log_action(ctx.guild.id, member.id, f"Media Unmuted (Role: {MEDIA_MUTE_ROLE_NAME})", ctx.author, reason)

        except discord.Forbidden:
            await ctx.send(embed=utils_cog.create_embed(ctx, title="Permissions Error", description=f"Failed to remove the '{MEDIA_MUTE_ROLE_NAME}' role.", color=discord.Color.red()))
        except discord.HTTPException as e:
            await ctx.send(embed=utils_cog.create_embed(ctx, title="API Error", description=f"An error occurred while unmuting: {e}", color=discord.Color.red()))
        except Exception as e:
            traceback.print_exc()
            await ctx.send(embed=utils_cog.create_embed(ctx, title="Unexpected Unmute Error", description=f"An unexpected error occurred: {e}", color=discord.Color.red()))

    @commands.command(name="mutedlist") # Or "mediamutedlist"
    @commands.has_permissions(manage_messages=True)
    async def muted_list_command(self, ctx: commands.Context):
        """Displays a list of members who currently have the 'Media Muted' role."""
        utils_cog = self.bot.get_cog('Utils')
        if not utils_cog: await ctx.send("Error: Utils cog not loaded."); return

        media_mute_role = discord.utils.get(ctx.guild.roles, name=MEDIA_MUTE_ROLE_NAME)
        if not media_mute_role:
            await ctx.send(embed=utils_cog.create_embed(ctx, title="Media Muted List", description=f"The '{MEDIA_MUTE_ROLE_NAME}' role does not exist."))
            return

        muted_members = [m for m in ctx.guild.members if media_mute_role in m.roles]

        if not muted_members:
            await ctx.send(embed=utils_cog.create_embed(ctx, title="Media Muted List", description=f"No members currently have the '{MEDIA_MUTE_ROLE_NAME}' role."))
            return

        description = "\n".join([f"- {member.mention} ({member.id})" for member in muted_members])
        embed = utils_cog.create_embed(ctx, title=f"Members with '{MEDIA_MUTE_ROLE_NAME}' Role ({len(muted_members)})", description=description)
        await ctx.send(embed=embed)

    # --- Error Handlers ---
    @mute_command.error
    async def mute_command_error(self, ctx, error):
        utils_cog = self.bot.get_cog('Utils')
        embed = utils_cog.create_embed(ctx, title="Media Mute Command Error", color=discord.Color.red()) if utils_cog else None
        
        desc = f"An unexpected error occurred: {error}" # Default
        if isinstance(error, commands.MissingPermissions): desc = "You need 'Moderate Members' permission."
        elif isinstance(error, commands.BotMissingPermissions): desc = f"I'm missing 'Manage Roles' permission. (Missing: {', '.join(error.missing_permissions)})"
        elif isinstance(error, commands.MemberNotFound): desc = f"Member '{error.argument}' not found."
        elif isinstance(error, commands.MissingRequiredArgument): desc = f"Missing argument: {error.param.name}."
        elif isinstance(error, commands.CommandInvokeError):
            print(f"Error in mute_command: {error.original}"); traceback.print_exc()
            if isinstance(error.original, discord.Forbidden):
                desc = "Permissions error during media mute. Check my 'Manage Roles' permission and role hierarchy."
            elif isinstance(error.original, discord.HTTPException):
                 desc = f"Network error during media mute: {error.original}"
            else:
                desc = "Internal error during media mute. Check console."
        
        if embed: embed.description = desc; await ctx.send(embed=embed)
        else: await ctx.send(f"Media Mute Command Error: {desc}")

    @un_mute_command.error
    async def un_mute_command_error(self, ctx, error):
        utils_cog = self.bot.get_cog('Utils')
        embed = utils_cog.create_embed(ctx, title="Media Unmute Command Error", color=discord.Color.red()) if utils_cog else None

        desc = f"An unexpected error occurred: {error}" # Default
        if isinstance(error, commands.MissingPermissions): desc = "You need 'Moderate Members' permission."
        elif isinstance(error, commands.BotMissingPermissions): desc = f"I'm missing 'Manage Roles' permission. (Missing: {', '.join(error.missing_permissions)})"
        elif isinstance(error, commands.MemberNotFound): desc = f"Member '{error.argument}' not found."
        elif isinstance(error, commands.MissingRequiredArgument): desc = f"Missing argument: {error.param.name}."
        elif isinstance(error, commands.CommandInvokeError):
            print(f"Error in un_mute_command: {error.original}"); traceback.print_exc()
            if isinstance(error.original, discord.Forbidden):
                desc = "Permissions error during media unmute. Check my 'Manage Roles' permission and role hierarchy."
            elif isinstance(error.original, discord.HTTPException):
                desc = f"Network error during media unmute: {error.original}"
            else:
                desc = "Internal error during media unmute. Check console."
            
        if embed: embed.description = desc; await ctx.send(embed=embed)
        else: await ctx.send(f"Media Unmute Command Error: {desc}")

async def setup(bot: commands.Bot):
    await bot.add_cog(Mute(bot))
    print(f"Cog 'Mute (using {MEDIA_MUTE_ROLE_NAME} role, corrected system channel logic)' loaded.")
