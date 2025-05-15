import discord
from discord.ext import commands
import traceback

# Configuration: The name of the role to be used for muting.
# This role will restrict sending images/embeds and adding reactions.
MUTE_ROLE_NAME = "Muted"

class Mute(commands.Cog):
    """
    A cog to prevent specified users from sending images and adding reactions
    by assigning/removing a designated 'Muted' role.
    Text mutes should be handled by the server's timeout system.
    """
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def _apply_channel_overwrites(self, guild: discord.Guild, mute_role: discord.Role):
        """
        Applies specific permission overwrites for the mute_role in all text channels.
        """
        overwrite = discord.PermissionOverwrite(
            attach_files=False,
            embed_links=False,
            add_reactions=False,
            use_external_emojis=False # Also deny external emojis for good measure
        )
        for channel in guild.text_channels:
            try:
                # Check if bot has permissions to manage permissions in this channel
                if channel.permissions_for(guild.me).manage_roles:
                    await channel.set_permissions(mute_role, overwrite=overwrite, reason="Applying Muted role restrictions")
                    print(f"Applied Muted role overwrites to channel: {channel.name} in guild {guild.name}")
                else:
                    print(f"Skipping channel {channel.name}: Missing 'Manage Roles/Permissions' for channel overwrite.")
            except discord.Forbidden:
                print(f"Forbidden: Could not set permission overwrites for Muted role in channel {channel.name} in guild {guild.name}.")
            except discord.HTTPException as e:
                print(f"HTTPException: Failed to set permission overwrites for Muted role in channel {channel.name}: {e}")
            except Exception as e:
                print(f"Unexpected error applying channel overwrites in {channel.name}: {e}")
                traceback.print_exc()


    async def _get_or_create_mute_role(self, guild: discord.Guild) -> discord.Role | None:
        """
        Gets the mute role by name. If it doesn't exist, creates it
        with appropriate permissions denied.
        If it exists, ensures its permissions are correct.
        Applies channel overwrites for the role.
        Permissions denied:
        - Attach Files
        - Embed Links
        - Add Reactions
        - Use External Emojis
        """
        mute_role = discord.utils.get(guild.roles, name=MUTE_ROLE_NAME)
        desired_perms = discord.Permissions.none()
        desired_perms.update(
            attach_files=False,
            embed_links=False,
            add_reactions=False,
            use_external_emojis=False
        )

        if mute_role:
            print(f"Found existing '{MUTE_ROLE_NAME}' role in guild {guild.name} (ID: {guild.id}).")
            # Ensure existing role has correct server-level permissions
            if mute_role.permissions != desired_perms:
                print(f"Existing '{MUTE_ROLE_NAME}' role has incorrect permissions. Attempting to update...")
                try:
                    await mute_role.edit(permissions=desired_perms, reason="Ensuring Muted role has correct server permissions.")
                    print(f"Successfully updated server permissions for '{MUTE_ROLE_NAME}' role in guild {guild.name}.")
                except discord.Forbidden:
                    print(f"Error: Bot lacks 'Manage Roles' permission to update the '{MUTE_ROLE_NAME}' role's server permissions in guild {guild.name}.")
                    # If we can't edit it, we might have issues, but proceed with channel overwrites
                except discord.HTTPException as e:
                    print(f"Error: Failed to update '{MUTE_ROLE_NAME}' role's server permissions in guild {guild.name}. HTTPException: {e}")
                except Exception as e:
                    print(f"An unexpected error occurred while updating mute role server permissions in {guild.name}: {e}")
                    traceback.print_exc()
        else:
            # If role doesn't exist, try to create it
            print(f"'{MUTE_ROLE_NAME}' role not found in {guild.name}. Attempting to create...")
            try:
                mute_role = await guild.create_role(
                    name=MUTE_ROLE_NAME,
                    permissions=desired_perms,
                    reason=f"Creating '{MUTE_ROLE_NAME}' role for bot's mute functionality."
                )
                print(f"Successfully created '{MUTE_ROLE_NAME}' role in guild {guild.name} (ID: {guild.id}).")

                # Notify in system channel if possible
                if guild.system_channel and guild.me.permissions_in(guild.system_channel).send_messages:
                    try:
                        await guild.system_channel.send(
                            f"The '{MUTE_ROLE_NAME}' role has been automatically created for restricting images and reactions. "
                            f"Please review its permissions and ensure it's positioned correctly in your role hierarchy (below my role, but effective for muting users)."
                        )
                    except discord.Forbidden:
                        print(f"Could not send role creation notification to system channel in {guild.name} due to permissions.")
            except discord.Forbidden:
                print(f"Error: Bot lacks 'Manage Roles' permission to create the '{MUTE_ROLE_NAME}' role in guild {guild.name}.")
                return None
            except discord.HTTPException as e:
                print(f"Error: Failed to create '{MUTE_ROLE_NAME}' role in guild {guild.name}. HTTPException: {e}")
                return None
            except Exception as e:
                print(f"An unexpected error occurred while creating mute role in {guild.name}: {e}")
                traceback.print_exc()
                return None

        # If role was found or successfully created, apply/check channel overwrites
        if mute_role:
            print(f"Applying channel overwrites for '{MUTE_ROLE_NAME}' role in guild {guild.name}...")
            await self._apply_channel_overwrites(guild, mute_role)
            return mute_role
        
        return None # Should only be reached if creation failed and wasn't caught earlier

    @commands.command(name="mute")
    @commands.has_permissions(moderate_members=True)
    @commands.bot_has_permissions(manage_roles=True, manage_channels=True) # Added manage_channels for overwrites
    async def mute_command(self, ctx: commands.Context, member: discord.Member, *, reason: str = "Not specified"):
        """
        Mutes a member (restricts images/reactions) by assigning the 'Muted' role.
        Usage: .mute <@member/ID> [reason]
        """
        utils_cog = self.bot.get_cog('Utils') # Assumes you have a Utils cog for embeds
        if not utils_cog:
            await ctx.send("Error: Utils cog not loaded. Cannot create embed.")
            return

        mute_role = await self._get_or_create_mute_role(ctx.guild)
        if not mute_role:
            await ctx.send(embed=utils_cog.create_embed(ctx, title="Mute Failed",
                                                       description=f"The '{MUTE_ROLE_NAME}' role is not available and could not be created/configured. "
                                                                   f"Please ensure I have 'Manage Roles' and 'Manage Channels' permissions, and my role is positioned high enough. "
                                                                   f"Alternatively, create the role manually with 'Attach Files', 'Embed Links', and 'Add Reactions' denied at server level and in channel overwrites.",
                                                       color=discord.Color.red()))
            return

        if member.id == ctx.author.id and ctx.guild.owner_id != ctx.author.id:
            await ctx.send(embed=utils_cog.create_embed(ctx, title="Error", description="You cannot mute yourself.", color=discord.Color.red()))
            return
        
        if member.bot:
            await ctx.send(embed=utils_cog.create_embed(ctx, title="Error", description="You cannot mute a bot.", color=discord.Color.red()))
            return

        if member.top_role >= ctx.author.top_role and ctx.guild.owner_id != ctx.author.id:
            await ctx.send(embed=utils_cog.create_embed(ctx, title="Permission Denied", description="You cannot mute a member with a role higher than or equal to yours.", color=discord.Color.red()))
            return
        
        if mute_role >= ctx.guild.me.top_role:
            await ctx.send(embed=utils_cog.create_embed(ctx, title="Hierarchy Error", description=f"I cannot assign or manage the '{MUTE_ROLE_NAME}' role as it is higher than or equal to my highest role. Please adjust role positions.", color=discord.Color.red()))
            return
        if member.top_role >= ctx.guild.me.top_role and ctx.guild.owner_id != ctx.author.id:
            await ctx.send(embed=utils_cog.create_embed(ctx, title="Hierarchy Error", description=f"I cannot mute {member.mention} because their role is higher than or equal to mine.", color=discord.Color.red()))
            return

        if mute_role in member.roles:
            embed = utils_cog.create_embed(ctx, title="Already Muted", description=f"{member.mention} already has the '{MUTE_ROLE_NAME}' role.", color=discord.Color.orange())
            await ctx.send(embed=embed)
            return

        try:
            await member.add_roles(mute_role, reason=f"Muted by {ctx.author} (ID: {ctx.author.id}) for: {reason}")
            # Re-apply channel overwrites just in case, though _get_or_create_mute_role should handle it.
            # This can be a bit redundant but adds an extra layer of certainty if role was just created/fixed.
            await self._apply_channel_overwrites(ctx.guild, mute_role) 

            embed = utils_cog.create_embed(ctx, title="Mute Applied", 
                                           description=f"{member.mention} has been assigned the '{MUTE_ROLE_NAME}' role, restricting image sending and reactions.", 
                                           color=discord.Color.green())
            embed.add_field(name="Reason", value=reason, inline=False)
            await ctx.send(embed=embed)

            history_cog = self.bot.get_cog('History')
            if history_cog:
                history_cog.log_action(ctx.guild.id, member.id, f"Muted (Role: {MUTE_ROLE_NAME})", ctx.author, reason)
        except discord.Forbidden:
            await ctx.send(embed=utils_cog.create_embed(ctx, title="Permissions Error", description="I failed to assign the mute role or apply its permissions. This is likely due to a role hierarchy issue or missing 'Manage Roles'/'Manage Channels' permission.", color=discord.Color.red()))
        except discord.HTTPException as e:
            await ctx.send(embed=utils_cog.create_embed(ctx, title="API Error", description=f"An error occurred while trying to assign the mute role: {e}", color=discord.Color.red()))
        except Exception as e:
            traceback.print_exc()
            await ctx.send(embed=utils_cog.create_embed(ctx, title="Unexpected Error", description="An unexpected error occurred during mute.", color=discord.Color.red()))

    @commands.command(name="unmute")
    @commands.has_permissions(moderate_members=True)
    @commands.bot_has_permissions(manage_roles=True) # Manage_channels not strictly needed for unmute role removal
    async def un_mute_command(self, ctx: commands.Context, member: discord.Member, *, reason: str = "Not specified"):
        """
        Unmutes a member by removing the 'Muted' role.
        Usage: .unmute <@member/ID> [reason]
        """
        utils_cog = self.bot.get_cog('Utils')
        if not utils_cog:
            await ctx.send("Error: Utils cog not loaded. Cannot create embed.")
            return

        mute_role = discord.utils.get(ctx.guild.roles, name=MUTE_ROLE_NAME) # Just get, don't try to create/fix on unmute
        if not mute_role: 
            await ctx.send(embed=utils_cog.create_embed(ctx, title="Unmute Failed",
                                                       description=f"The '{MUTE_ROLE_NAME}' role is not available in this server. Cannot unmute.",
                                                       color=discord.Color.red()))
            return
        
        if mute_role >= ctx.guild.me.top_role: # Bot must be able to manage the mute role
            await ctx.send(embed=utils_cog.create_embed(ctx, title="Hierarchy Error", description=f"I cannot remove the '{MUTE_ROLE_NAME}' role as it is higher than or equal to my highest role.", color=discord.Color.red()))
            return

        if mute_role not in member.roles:
            embed = utils_cog.create_embed(ctx, title="Not Muted", description=f"{member.mention} does not have the '{MUTE_ROLE_NAME}' role.", color=discord.Color.orange())
            await ctx.send(embed=embed)
            return

        try:
            await member.remove_roles(mute_role, reason=f"Unmuted by {ctx.author} (ID: {ctx.author.id}) for: {reason}")
            embed = utils_cog.create_embed(ctx, title="Mute Removed", 
                                           description=f"The '{MUTE_ROLE_NAME}' role has been removed from {member.mention}.", 
                                           color=discord.Color.green())
            embed.add_field(name="Reason", value=reason, inline=False)
            await ctx.send(embed=embed)

            history_cog = self.bot.get_cog('History')
            if history_cog:
                history_cog.log_action(ctx.guild.id, member.id, f"Unmuted (Role: {MUTE_ROLE_NAME})", ctx.author, reason)
        except discord.Forbidden:
            await ctx.send(embed=utils_cog.create_embed(ctx, title="Permissions Error", description="I failed to remove the mute role. This might be due to a role hierarchy issue or missing 'Manage Roles' permission.", color=discord.Color.red()))
        except discord.HTTPException as e:
            await ctx.send(embed=utils_cog.create_embed(ctx, title="API Error", description=f"An error occurred while trying to remove the mute role: {e}", color=discord.Color.red()))
        except Exception as e:
            traceback.print_exc()
            await ctx.send(embed=utils_cog.create_embed(ctx, title="Unexpected Error", description="An unexpected error occurred during unmute.", color=discord.Color.red()))
            
    @commands.command(name="mutedlist")
    @commands.has_permissions(manage_messages=True) 
    async def muted_list_command(self, ctx: commands.Context):
        """Displays a list of members who have the 'Muted' role."""
        utils_cog = self.bot.get_cog('Utils')
        if not utils_cog:
            await ctx.send("Error: Utils cog not loaded. Cannot create embed.")
            return

        mute_role = discord.utils.get(ctx.guild.roles, name=MUTE_ROLE_NAME) 
        if not mute_role:
            embed = utils_cog.create_embed(ctx, title="Muted List", description=f"The '{MUTE_ROLE_NAME}' role does not exist in this server.")
            await ctx.send(embed=embed)
            return

        muted_members_with_role = [m for m in ctx.guild.members if mute_role in m.roles]

        if not muted_members_with_role:
            embed = utils_cog.create_embed(ctx, title="Muted List", description=f"No members currently have the '{MUTE_ROLE_NAME}' role.")
            await ctx.send(embed=embed)
            return

        description_lines = []
        for member_obj in muted_members_with_role: 
            description_lines.append(f"- {member_obj.mention} (ID: {member_obj.id})")
        
        embed = utils_cog.create_embed(ctx, title=f"Members with '{MUTE_ROLE_NAME}' Role", description="\n".join(description_lines))
        await ctx.send(embed=embed)

    @mute_command.error
    async def mute_command_error(self, ctx, error):
        utils_cog = self.bot.get_cog('Utils')
        error_embed = None
        if utils_cog: error_embed = utils_cog.create_embed(ctx, title="Mute Error", color=discord.Color.red())
        
        desc = f"An unexpected error occurred: {error}" 
        if isinstance(error, commands.MissingPermissions):
            desc = "You need 'Moderate Members' permission to use this command."
        elif isinstance(error, commands.BotMissingPermissions):
            missing_perms_str = ", ".join(error.missing_permissions)
            if 'manage_roles' in error.missing_permissions or 'manage_channels' in error.missing_permissions:
                desc = f"I am missing crucial permissions ('Manage Roles' and/or 'Manage Channels'). Please grant them so I can manage the mute role and its channel overwrites. Missing: `{missing_perms_str}`"
            else:
                desc = f"I am missing the following permissions: `{missing_perms_str}`."
        elif isinstance(error, commands.MemberNotFound):
            desc = f"Member not found: `{error.argument}`. Please provide a valid member."
        elif isinstance(error, commands.MissingRequiredArgument):
            desc = f"Missing argument: `{error.param.name}`.\nUsage: `.mute <@member/ID> [reason]`"
        elif isinstance(error, commands.CommandInvokeError):
            print(f"CommandInvokeError in mute: {error.original}") 
            traceback.print_exc()
            if isinstance(error.original, discord.Forbidden):
                 desc = "I lack permissions to assign the role or modify channel permissions. This is likely due to role hierarchy or missing 'Manage Roles'/'Manage Channels'."
            else:
                 desc = "An internal error occurred. Please check the bot logs."
        
        if error_embed:
            error_embed.description = desc
            await ctx.send(embed=error_embed)
        else:
            await ctx.send(f"Mute Error: {desc} (Utils cog missing).")

    @un_mute_command.error
    async def unmute_command_error(self, ctx, error):
        utils_cog = self.bot.get_cog('Utils')
        error_embed = None
        if utils_cog: error_embed = utils_cog.create_embed(ctx, title="Unmute Error", color=discord.Color.red())

        desc = f"An unexpected error occurred: {error}" 
        if isinstance(error, commands.MissingPermissions):
            desc = "You need 'Moderate Members' permission to use this command."
        elif isinstance(error, commands.BotMissingPermissions):
            missing_perms_str = ", ".join(error.missing_permissions)
            if 'manage_roles' in error.missing_permissions:
                desc = f"I am missing the 'Manage Roles' permission. Please grant it to me so I can manage the mute role. Missing: `{missing_perms_str}`"
            else:
                desc = f"I am missing the following permissions: `{missing_perms_str}`."
        elif isinstance(error, commands.MemberNotFound):
            desc = f"Member not found: `{error.argument}`. Please provide a valid member."
        elif isinstance(error, commands.MissingRequiredArgument):
            desc = f"Missing argument: `{error.param.name}`.\nUsage: `.unmute <@member/ID> [reason]`"
        elif isinstance(error, commands.CommandInvokeError):
            print(f"CommandInvokeError in unmute: {error.original}")
            traceback.print_exc()
            if isinstance(error.original, discord.Forbidden):
                 desc = "I lack permissions to remove the role. This is likely due to role hierarchy (my role is too low)."
            else:
                 desc = "An internal error occurred. Please check the bot logs."

        if error_embed:
            error_embed.description = desc
            await ctx.send(embed=error_embed)
        else:
            await ctx.send(f"Unmute Error: {desc} (Utils cog missing).")

async def setup(bot: commands.Bot):
    await bot.add_cog(Mute(bot))
    print(f"Cog 'Mute (Role-Based)' loaded successfully. Ensure role '{MUTE_ROLE_NAME}' is configured or can be created/managed by the bot.")
