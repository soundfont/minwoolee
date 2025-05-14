import discord
from discord.ext import commands
import traceback

# Configuration: The name of the role to be used for muting.
MUTE_ROLE_NAME = "Media Muted" 

class Mute(commands.Cog):
    """
    A cog to prevent specified users from sending images and adding reactions
    by assigning/removing a designated 'Media Muted' role.
    Text mutes should be handled by the server's timeout system.
    """
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def _get_or_create_mute_role(self, guild: discord.Guild) -> discord.Role | None:
        """
        Gets the mute role by name. If it doesn't exist, tries to create it
        with appropriate permissions denied.
        Permissions denied on the role:
        - Attach Files
        - Embed Links
        - Add Reactions
        - Use External Emojis (optional, but good for media mute)
        """
        mute_role = discord.utils.get(guild.roles, name=MUTE_ROLE_NAME)
        
        if mute_role:
            # Optionally, you could verify/update permissions here if the role exists
            # but for simplicity, we assume if it exists, it's configured correctly by an admin
            # or was configured by this bot previously.
            print(f"Found existing '{MUTE_ROLE_NAME}' role in guild {guild.name} (ID: {guild.id}).")
            return mute_role

        # If role doesn't exist, try to create it
        try:
            # Define permissions for the new role
            # Start with default permissions (usually all off for a new role)
            perms = discord.Permissions.none() 
            # Explicitly deny specific permissions
            perms.update(
                attach_files=False,
                embed_links=False,
                add_reactions=False,
                use_external_emojis=False # Often useful for a media/reaction mute
            )
            
            # Guild.create_role creates the role at the bottom (position 1, above @everyone)
            # The bot's highest role must be able to manage roles.
            # The new role should be moved below the bot's role if possible,
            # but for creation, this is the default.
            mute_role = await guild.create_role(
                name=MUTE_ROLE_NAME,
                permissions=perms,
                reason="Creating Media Muted role for bot functionality."
            )
            print(f"Successfully created '{MUTE_ROLE_NAME}' role in guild {guild.name} (ID: {guild.id}).")
            await guild.system_channel.send(
                f"The '{MUTE_ROLE_NAME}' role has been automatically created for media/reaction muting. "
                f"Please review its permissions and position in the role hierarchy if needed."
            ) if guild.system_channel and guild.me.permissions_in(guild.system_channel).send_messages else None
            return mute_role
        except discord.Forbidden:
            print(f"Error: Bot lacks 'Manage Roles' permission to create the '{MUTE_ROLE_NAME}' role in guild {guild.name}.")
            if guild.system_channel and guild.me.permissions_in(guild.system_channel).send_messages:
                await guild.system_channel.send(
                    f"Error: I tried to create the '{MUTE_ROLE_NAME}' role but lack the 'Manage Roles' permission. "
                    f"An administrator needs to create this role manually with 'Attach Files', 'Embed Links', and 'Add Reactions' permissions denied."
                )
            return None
        except discord.HTTPException as e:
            print(f"Error: Failed to create '{MUTE_ROLE_NAME}' role in guild {guild.name}. HTTPException: {e}")
            return None
        except Exception as e:
            print(f"An unexpected error occurred while creating mute role in {guild.name}: {e}")
            traceback.print_exc()
            return None

    # The on_message and on_reaction_add listeners are removed
    # as Discord will enforce permissions based on the assigned role.

    @commands.command(name="mute")
    @commands.has_permissions(moderate_members=True) # User permission
    @commands.bot_has_permissions(manage_roles=True)  # Bot permission
    async def mute_command(self, ctx: commands.Context, member: discord.Member, *, reason: str = "Not specified"):
        """
        Mutes a member from sending images and adding reactions by assigning the 'Media Muted' role.
        Usage: .mute <@member/ID> [reason]
        Requires a role named "Media Muted" (or will attempt to create it).
        """
        utils_cog = self.bot.get_cog('Utils')
        if not utils_cog:
            await ctx.send("Error: Utils cog not loaded. Cannot create embed.")
            return

        mute_role = await self._get_or_create_mute_role(ctx.guild)
        if not mute_role:
            # _get_or_create_mute_role would have sent a message or logged if it failed to create
            await ctx.send(embed=utils_cog.create_embed(ctx, title="Mute Failed",
                                                       description=f"The '{MUTE_ROLE_NAME}' role is not available and could not be created. Please check bot permissions or create the role manually.",
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
        
        # Check if bot can manage the mute_role itself and the target member
        if mute_role >= ctx.guild.me.top_role:
            await ctx.send(embed=utils_cog.create_embed(ctx, title="Hierarchy Error", description=f"I cannot assign the '{MUTE_ROLE_NAME}' role as it is higher than or equal to my highest role. Please adjust role positions.", color=discord.Color.red()))
            return
        if member.top_role >= ctx.guild.me.top_role and ctx.guild.owner_id != ctx.author.id: # Check if bot can manage the user at all
            await ctx.send(embed=utils_cog.create_embed(ctx, title="Hierarchy Error", description=f"I cannot mute {member.mention} because their role is higher than or equal to mine.", color=discord.Color.red()))
            return

        if mute_role in member.roles:
            embed = utils_cog.create_embed(ctx, title="Already Muted", description=f"{member.mention} already has the '{MUTE_ROLE_NAME}' role.", color=discord.Color.orange())
            await ctx.send(embed=embed)
            return

        try:
            await member.add_roles(mute_role, reason=f"Muted by {ctx.author} (ID: {ctx.author.id}) for: {reason}")
            embed = utils_cog.create_embed(ctx, title="Media/Reaction Mute Applied", 
                                           description=f"{member.mention} has been assigned the '{MUTE_ROLE_NAME}' role, restricting image sending and reactions.", 
                                           color=discord.Color.green())
            embed.add_field(name="Reason", value=reason, inline=False)
            await ctx.send(embed=embed)

            history_cog = self.bot.get_cog('History')
            if history_cog:
                history_cog.log_action(ctx.guild.id, member.id, f"Media/Reaction Muted (Role: {MUTE_ROLE_NAME})", ctx.author, reason)
        except discord.Forbidden:
            # This specific Forbidden error is less likely now due to @bot_has_permissions and hierarchy checks, but good to keep.
            print(f"Error: Bot missing 'Manage Roles' or role hierarchy issue when trying to mute {member.name} in {ctx.guild.name}.")
            await ctx.send(embed=utils_cog.create_embed(ctx, title="Permissions Error", description="I failed to assign the mute role. This might be due to a role hierarchy issue or missing 'Manage Roles' permission.", color=discord.Color.red()))
        except discord.HTTPException as e:
            print(f"Error: Failed to add mute role to {member.name}. HTTPException: {e}")
            await ctx.send(embed=utils_cog.create_embed(ctx, title="API Error", description="An error occurred while trying to assign the mute role.", color=discord.Color.red()))
        except Exception as e:
            print(f"An unexpected error occurred during mute_command for {member.name}: {e}")
            traceback.print_exc()
            await ctx.send(embed=utils_cog.create_embed(ctx, title="Unexpected Error", description="An unexpected error occurred.", color=discord.Color.red()))


    @commands.command(name="unmute")
    @commands.has_permissions(moderate_members=True)
    @commands.bot_has_permissions(manage_roles=True)
    async def un_mute_command(self, ctx: commands.Context, member: discord.Member, *, reason: str = "Not specified"):
        """
        Allows a member to send images and add reactions again by removing the 'Media Muted' role.
        Usage: .unmute <@member/ID> [reason]
        """
        utils_cog = self.bot.get_cog('Utils')
        if not utils_cog:
            await ctx.send("Error: Utils cog not loaded. Cannot create embed.")
            return

        mute_role = await self._get_or_create_mute_role(ctx.guild) # Ensures role check/creation logic is consistent
        if not mute_role:
            await ctx.send(embed=utils_cog.create_embed(ctx, title="Unmute Failed",
                                                       description=f"The '{MUTE_ROLE_NAME}' role is not available. Cannot unmute.",
                                                       color=discord.Color.red()))
            return
        
        # Check if bot can manage the mute_role itself
        if mute_role >= ctx.guild.me.top_role:
            await ctx.send(embed=utils_cog.create_embed(ctx, title="Hierarchy Error", description=f"I cannot remove the '{MUTE_ROLE_NAME}' role as it is higher than or equal to my highest role. Please adjust role positions.", color=discord.Color.red()))
            return

        if mute_role not in member.roles:
            embed = utils_cog.create_embed(ctx, title="Not Muted", description=f"{member.mention} does not have the '{MUTE_ROLE_NAME}' role.", color=discord.Color.orange())
            await ctx.send(embed=embed)
            return

        try:
            await member.remove_roles(mute_role, reason=f"Unmuted by {ctx.author} (ID: {ctx.author.id}) for: {reason}")
            embed = utils_cog.create_embed(ctx, title="Media/Reaction Mute Removed", 
                                           description=f"The '{MUTE_ROLE_NAME}' role has been removed from {member.mention}.", 
                                           color=discord.Color.green())
            embed.add_field(name="Reason", value=reason, inline=False)
            await ctx.send(embed=embed)

            history_cog = self.bot.get_cog('History')
            if history_cog:
                history_cog.log_action(ctx.guild.id, member.id, f"Media/Reaction Unmuted (Role: {MUTE_ROLE_NAME})", ctx.author, reason)
        except discord.Forbidden:
            print(f"Error: Bot missing 'Manage Roles' or role hierarchy issue when trying to unmute {member.name} in {ctx.guild.name}.")
            await ctx.send(embed=utils_cog.create_embed(ctx, title="Permissions Error", description="I failed to remove the mute role. This might be due to a role hierarchy issue or missing 'Manage Roles' permission.", color=discord.Color.red()))
        except discord.HTTPException as e:
            print(f"Error: Failed to remove mute role from {member.name}. HTTPException: {e}")
            await ctx.send(embed=utils_cog.create_embed(ctx, title="API Error", description="An error occurred while trying to remove the mute role.", color=discord.Color.red()))
        except Exception as e:
            print(f"An unexpected error occurred during un_mute_command for {member.name}: {e}")
            traceback.print_exc()
            await ctx.send(embed=utils_cog.create_embed(ctx, title="Unexpected Error", description="An unexpected error occurred.", color=discord.Color.red()))
            
    @commands.command(name="mutedlist")
    @commands.has_permissions(manage_messages=True) # Or moderate_members
    async def muted_list_command(self, ctx: commands.Context):
        """Displays a list of members who have the 'Media Muted' role."""
        utils_cog = self.bot.get_cog('Utils')
        if not utils_cog:
            await ctx.send("Error: Utils cog not loaded. Cannot create embed.")
            return

        mute_role = await self._get_or_create_mute_role(ctx.guild) # Get the role to check against
        if not mute_role:
            embed = utils_cog.create_embed(ctx, title="Muted List (Media/Reactions)", description=f"The '{MUTE_ROLE_NAME}' role does not exist in this server.")
            await ctx.send(embed=embed)
            return

        muted_members_with_role = [m for m in ctx.guild.members if mute_role in m.roles]

        if not muted_members_with_role:
            embed = utils_cog.create_embed(ctx, title="Muted List (Media/Reactions)", description=f"No members currently have the '{MUTE_ROLE_NAME}' role.")
            await ctx.send(embed=embed)
            return

        description_lines = []
        for member in muted_members_with_role:
            description_lines.append(f"- {member.mention} (ID: {member.id})")
        
        embed = utils_cog.create_embed(ctx, title=f"Members with '{MUTE_ROLE_NAME}' Role", description="\n".join(description_lines))
        await ctx.send(embed=embed)

    @mute_command.error
    async def mute_command_error(self, ctx, error):
        utils_cog = self.bot.get_cog('Utils')
        error_embed = None
        if utils_cog: error_embed = utils_cog.create_embed(ctx, title="Mute Error", color=discord.Color.red())
        
        if isinstance(error, commands.MissingPermissions):
            desc = "You need 'Moderate Members' permission to use this command."
        elif isinstance(error, commands.BotMissingPermissions):
            desc = f"I am missing the 'Manage Roles' permission to perform this action."
        elif isinstance(error, commands.MemberNotFound):
            desc = f"Member not found: `{error.argument}`. Please provide a valid member."
        elif isinstance(error, commands.MissingRequiredArgument):
            desc = f"Missing argument: `{error.param.name}`.\nUsage: `.mute <@member/ID> [reason]`"
        elif isinstance(error, commands.CommandInvokeError):
            print(f"CommandInvokeError in mute: {error.original}")
            traceback.print_exc()
            if isinstance(error.original, discord.Forbidden): # More specific Forbidden from deep within
                 desc = "I lack permissions to assign the role, likely due to role hierarchy."
            else:
                 desc = "An internal error occurred. Please check the bot logs."
        else:
            desc = f"An unexpected error occurred: {error}"
        
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

        if isinstance(error, commands.MissingPermissions):
            desc = "You need 'Moderate Members' permission to use this command."
        elif isinstance(error, commands.BotMissingPermissions):
            desc = f"I am missing the 'Manage Roles' permission to perform this action."
        elif isinstance(error, commands.MemberNotFound):
            desc = f"Member not found: `{error.argument}`. Please provide a valid member."
        elif isinstance(error, commands.MissingRequiredArgument):
            desc = f"Missing argument: `{error.param.name}`.\nUsage: `.unmute <@member/ID> [reason]`"
        elif isinstance(error, commands.CommandInvokeError):
            print(f"CommandInvokeError in unmute: {error.original}")
            traceback.print_exc()
            if isinstance(error.original, discord.Forbidden):
                 desc = "I lack permissions to remove the role, likely due to role hierarchy."
            else:
                 desc = "An internal error occurred. Please check the bot logs."
        else:
            desc = f"An unexpected error occurred: {error}"

        if error_embed:
            error_embed.description = desc
            await ctx.send(embed=error_embed)
        else:
            await ctx.send(f"Unmute Error: {desc} (Utils cog missing).")

async def setup(bot: commands.Bot):
    await bot.add_cog(Mute(bot))
    print(f"Cog 'Mute (Role-Based Media/Reactions)' loaded successfully. Ensure role '{MUTE_ROLE_NAME}' is configured.")

