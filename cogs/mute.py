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
    This version robustly applies channel-level DENY overwrites for the Muted role
    to counteract other roles (like a 'Trusted' role) that might grant these permissions.
    """
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def _apply_channel_overwrites(self, guild: discord.Guild, mute_role: discord.Role):
        """
        Applies specific permission overwrites for the mute_role in all text channels.
        This is crucial for overriding other roles that might grant these permissions.
        """
        # Permissions to explicitly DENY in channels for the Muted role
        overwrite_settings = {
            "attach_files": False,
            "embed_links": False,
            "add_reactions": False,
            "use_external_emojis": False
        }
        overwrite = discord.PermissionOverwrite(**overwrite_settings)

        successful_overwrites = 0
        failed_overwrites = 0
        skipped_channels = 0

        print(f"Starting to apply/verify channel overwrites for '{MUTE_ROLE_NAME}' in guild '{guild.name}'...")
        for channel in guild.text_channels: # Iterate through all text channels
            try:
                bot_channel_permissions = channel.permissions_for(guild.me)
                
                # Bot needs 'Manage Roles' (which implies manage permissions for roles) in the channel
                if bot_channel_permissions.manage_roles:
                    current_overwrite = channel.overwrites_for(mute_role)
                    
                    # Check if an update is actually needed
                    needs_update = False
                    for perm, value in overwrite_settings.items():
                        if getattr(current_overwrite, perm) != value:
                            needs_update = True
                            break
                    
                    if needs_update:
                        await channel.set_permissions(
                            mute_role, 
                            overwrite=overwrite, 
                            reason=f"Enforcing '{MUTE_ROLE_NAME}' role restrictions"
                        )
                        print(f"Applied/Updated '{MUTE_ROLE_NAME}' overwrites for channel: #{channel.name}")
                        successful_overwrites +=1
                    else:
                        # print(f"'{MUTE_ROLE_NAME}' overwrites already correct for channel: #{channel.name}")
                        successful_overwrites +=1 # Count as success if already correct
                else:
                    print(f"Skipping channel #{channel.name}: Bot lacks 'Manage Roles' permission in this channel.")
                    skipped_channels += 1
            except discord.Forbidden:
                print(f"Forbidden: Could not set permission overwrites for '{MUTE_ROLE_NAME}' in channel #{channel.name}.")
                failed_overwrites += 1
            except discord.HTTPException as e:
                print(f"HTTPException: Failed to set permission overwrites for '{MUTE_ROLE_NAME}' in channel #{channel.name}: {e}")
                failed_overwrites += 1
            except Exception as e:
                print(f"Unexpected error applying channel overwrites in #{channel.name} for guild '{guild.name}': {e}")
                traceback.print_exc()
                failed_overwrites += 1
        
        print(f"'{MUTE_ROLE_NAME}' channel overwrite summary for guild '{guild.name}': "
              f"{successful_overwrites} processed (applied/verified), {failed_overwrites} failed, {skipped_channels} skipped.")

    async def _get_or_create_mute_role(self, guild: discord.Guild) -> discord.Role | None:
        """
        Gets the mute role by name. If it doesn't exist, creates it
        with appropriate server-level permissions denied.
        If it exists, ensures its server-level permissions are correct.
        Then, applies necessary channel overwrites.
        """
        mute_role = discord.utils.get(guild.roles, name=MUTE_ROLE_NAME)
        
        desired_server_perms = discord.Permissions.none()
        desired_server_perms.update(
            attach_files=False,
            embed_links=False,
            add_reactions=False,
            use_external_emojis=False
        )

        if mute_role:
            print(f"Found existing '{MUTE_ROLE_NAME}' role in guild '{guild.name}' (ID: {guild.id}).")
            if mute_role.permissions != desired_server_perms:
                print(f"Existing '{MUTE_ROLE_NAME}' role has different server permissions. Attempting to update...")
                try:
                    await mute_role.edit(
                        permissions=desired_server_perms, 
                        reason=f"Ensuring '{MUTE_ROLE_NAME}' role has correct server permissions."
                    )
                    print(f"Successfully updated server permissions for '{MUTE_ROLE_NAME}' role.")
                except discord.Forbidden:
                    print(f"Error: Bot lacks 'Manage Roles' permission to update the '{MUTE_ROLE_NAME}' role's server permissions.")
                except discord.HTTPException as e:
                    print(f"Error: Failed to update '{MUTE_ROLE_NAME}' role's server permissions. HTTPException: {e}")
                except Exception as e:
                    print(f"An unexpected error occurred while updating mute role server permissions: {e}")
                    traceback.print_exc()
        else:
            print(f"'{MUTE_ROLE_NAME}' role not found in '{guild.name}'. Attempting to create...")
            try:
                mute_role = await guild.create_role(
                    name=MUTE_ROLE_NAME,
                    permissions=desired_server_perms,
                    reason=f"Creating '{MUTE_ROLE_NAME}' role for media/reaction mute functionality."
                )
                print(f"Successfully created '{MUTE_ROLE_NAME}' role (ID: {mute_role.id}).")
                if guild.system_channel and guild.me.permissions_in(guild.system_channel).send_messages:
                    try:
                        await guild.system_channel.send(
                            f"The '{MUTE_ROLE_NAME}' role has been automatically created/configured for restricting images and reactions. "
                            f"Please ensure it's positioned correctly in your role hierarchy."
                        )
                    except discord.Forbidden:
                        print(f"Could not send role creation notification to system channel in '{guild.name}'.")
            except discord.Forbidden:
                print(f"Error: Bot lacks 'Manage Roles' permission to create the '{MUTE_ROLE_NAME}' role.")
                return None
            except discord.HTTPException as e:
                print(f"Error: Failed to create '{MUTE_ROLE_NAME}' role. HTTPException: {e}")
                return None
            except Exception as e:
                print(f"An unexpected error occurred while creating mute role: {e}")
                traceback.print_exc()
                return None

        if mute_role:
            await self._apply_channel_overwrites(guild, mute_role)
            return mute_role
        
        return None

    @commands.command(name="mute")
    @commands.has_permissions(moderate_members=True)
    @commands.bot_has_permissions(manage_roles=True) # manage_roles is sufficient for channel.set_permissions on a role
    async def mute_command(self, ctx: commands.Context, member: discord.Member, *, reason: str = "Not specified"):
        utils_cog = self.bot.get_cog('Utils')
        if not utils_cog:
            # It's better to use the custom context's send if available
            await ctx.send("Error: Utils cog not loaded. Cannot create embed.")
            return

        mute_role = await self._get_or_create_mute_role(ctx.guild)
        if not mute_role:
            await ctx.send(embed=utils_cog.create_embed(ctx, title="Mute Failed",
                                                       description=(
                                                           f"The '{MUTE_ROLE_NAME}' role is not available and could not be created/configured. "
                                                           "Please ensure I have 'Manage Roles' permission server-wide and in relevant channels, "
                                                           "and my role is positioned high enough."
                                                        ),
                                                       color=discord.Color.red()))
            return

        # Standard checks (self-mute, bot mute, hierarchy)
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
        if member.id != ctx.guild.owner_id and member.top_role >= ctx.guild.me.top_role : # Can't mute owner, and can't mute if their role is higher/equal to bot's
            await ctx.send(embed=utils_cog.create_embed(ctx, title="Hierarchy Error", description=f"I cannot mute {member.mention} because their role is higher than or equal to mine.", color=discord.Color.red()))
            return
        if member.id == ctx.guild.owner_id: # Explicitly prevent muting the owner
             await ctx.send(embed=utils_cog.create_embed(ctx, title="Error", description="The server owner cannot be muted.", color=discord.Color.red()))
             return


        if mute_role in member.roles:
            print(f"User {member.display_name} already has '{MUTE_ROLE_NAME}'. Re-verifying channel overwrites.")
            await self._apply_channel_overwrites(ctx.guild, mute_role) # Re-verify just in case
            embed = utils_cog.create_embed(ctx, title="Already Muted", 
                                           description=f"{member.mention} already has the '{MUTE_ROLE_NAME}' role. Channel permissions re-verified.", 
                                           color=discord.Color.orange())
            await ctx.send(embed=embed)
            return

        try:
            await member.add_roles(mute_role, reason=f"Muted by {ctx.author} (ID: {ctx.author.id}) for: {reason}")
            # _get_or_create_mute_role already calls _apply_channel_overwrites.
            # No need to call it again here unless debugging a specific timing issue.

            embed = utils_cog.create_embed(ctx, title="Mute Applied", 
                                           description=f"{member.mention} has been assigned the '{MUTE_ROLE_NAME}' role, restricting image sending and reactions.", 
                                           color=discord.Color.green())
            embed.add_field(name="Reason", value=reason, inline=False)
            await ctx.send(embed=embed)

            history_cog = self.bot.get_cog('History')
            if history_cog:
                history_cog.log_action(ctx.guild.id, member.id, f"Muted (Role: {MUTE_ROLE_NAME})", ctx.author, reason)
        except discord.Forbidden:
            await ctx.send(embed=utils_cog.create_embed(ctx, title="Permissions Error", description="I failed to assign the mute role. This is likely due to a role hierarchy issue or missing 'Manage Roles' permission.", color=discord.Color.red()))
        except discord.HTTPException as e:
            await ctx.send(embed=utils_cog.create_embed(ctx, title="API Error", description=f"An error occurred while trying to assign the mute role: {e}", color=discord.Color.red()))
        except Exception as e:
            traceback.print_exc()
            await ctx.send(embed=utils_cog.create_embed(ctx, title="Unexpected Error", description="An unexpected error occurred during mute.", color=discord.Color.red()))

    @commands.command(name="unmute")
    @commands.has_permissions(moderate_members=True)
    @commands.bot_has_permissions(manage_roles=True)
    async def un_mute_command(self, ctx: commands.Context, member: discord.Member, *, reason: str = "Not specified"):
        utils_cog = self.bot.get_cog('Utils')
        if not utils_cog:
            await ctx.send("Error: Utils cog not loaded. Cannot create embed.")
            return

        mute_role = discord.utils.get(ctx.guild.roles, name=MUTE_ROLE_NAME)
        if not mute_role: 
            await ctx.send(embed=utils_cog.create_embed(ctx, title="Unmute Failed",
                                                       description=f"The '{MUTE_ROLE_NAME}' role is not available in this server. Cannot unmute.",
                                                       color=discord.Color.red()))
            return
        
        if mute_role >= ctx.guild.me.top_role:
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
        
        embed = utils_cog.create_embed(ctx, title=f"Members with '{MUTE_ROLE_NAME}' Role ({len(muted_members_with_role)})", description="\n".join(description_lines))
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
            if 'manage_roles' in error.missing_permissions :
                desc = f"I am missing 'Manage Roles' permission server-wide or in specific channels. This is crucial for the mute command. Missing: `{missing_perms_str}`"
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
                 desc = "I lack permissions to assign the role or modify channel permissions. This is likely due to role hierarchy or missing 'Manage Roles' server-wide or in specific channels."
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
    print(f"Cog 'Mute (Role-Based with Enhanced Channel Overwrites)' loaded successfully.")
