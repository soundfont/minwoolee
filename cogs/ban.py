import discord
from discord.ext import commands
import traceback # For detailed error logging

class Ban(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def _send_ban_error_embed(self, ctx, title: str, description: str):
        """Helper to send standardized error embeds for the ban command."""
        utils_cog = self.bot.get_cog('Utils')
        if utils_cog and hasattr(utils_cog, 'create_embed'):
            embed = utils_cog.create_embed(ctx, title=title, description=description, color=discord.Color.red())
        else: # Fallback basic embed
            embed = discord.Embed(title=title, description=description, color=discord.Color.red(), timestamp=datetime.datetime.now(datetime.timezone.utc))
            embed.set_footer(text=f"Command by {ctx.author.name}", icon_url=ctx.author.display_avatar.url if ctx.author.avatar else None)
        await ctx.send(embed=embed)

    @commands.command(name="ban")
    @commands.has_permissions(ban_members=True) # User needs Ban Members permission
    @commands.bot_has_permissions(ban_members=True) # Bot needs Ban Members permission
    async def ban_command(self, ctx: commands.Context, member: discord.Member, *, reason: str = None):
        """
        Bans a member from the server.
        Checks:
        - Invoker cannot ban themselves.
        - Invoker cannot ban someone with a role higher than or equal to their own (unless invoker is server owner).
        - Bot cannot ban someone with a role higher than or equal to its own.
        """
        
        # 1. Prevent self-ban
        if member == ctx.author:
            await self._send_ban_error_embed(ctx, "Ban Error", "You cannot ban yourself.")
            return
        
        # 2. Prevent banning the bot itself
        if member == ctx.guild.me:
            await self._send_ban_error_embed(ctx, "Ban Error", "I cannot ban myself.")
            return

        # 3. Invoker's role hierarchy check (ctx.author vs member)
        # Server owner can bypass this check.
        if ctx.author.id != ctx.guild.owner_id:
            if member.top_role >= ctx.author.top_role:
                await self._send_ban_error_embed(ctx, "Permission Denied", "You cannot ban a member who has a role higher than or equal to your highest role.")
                return
        
        # 4. Bot's role hierarchy check (bot vs member)
        # Bot cannot ban someone if its highest role is not above the target's highest role.
        if member.top_role >= ctx.guild.me.top_role:
            await self._send_ban_error_embed(ctx, "Hierarchy Error", f"I cannot ban {member.mention} because their role is higher than or equal to my highest role. Please adjust role positions.")
            return

        # 5. Prevent banning the server owner
        if member.id == ctx.guild.owner_id:
            await self._send_ban_error_embed(ctx, "Action Not Allowed", "The server owner cannot be banned.")
            return

        try:
            # Perform the ban
            # delete_message_days=0 means no messages from the user will be deleted upon ban.
            # Common values are 0 (none) or 1 (last 24 hours) up to 7.
            await member.ban(reason=reason, delete_message_days=0) 
            
            # Confirmation embed to the command channel
            utils_cog = self.bot.get_cog('Utils')
            if utils_cog and hasattr(utils_cog, 'create_embed'):
                # Using a generic ban hammer emoji as a placeholder. Replace if you have a custom one.
                embed = utils_cog.create_embed(ctx, title="<:banhammer:1234567890> Member Banned", color=discord.Color.red()) 
                embed.description = f"Banned {member.mention} ({member.id})"
                if reason:
                    embed.description += f"\n**Reason:** {reason}"
                await ctx.send(embed=embed)
            else: # Fallback plain text response
                await ctx.send(f"Successfully banned {member.mention}. Reason: {reason or 'Not specified'}")

            # Log to ModLog channel (if ModLog cog exists and is configured)
            modlog_cog = self.bot.get_cog('ModLog')
            if modlog_cog and hasattr(modlog_cog, 'log_moderation_action'):
                await modlog_cog.log_moderation_action(
                    guild=ctx.guild,
                    action_title="Member Banned",
                    target_user=member,
                    moderator=ctx.author,
                    reason=reason,
                    color=discord.Color.red()
                )
            # Also log to History cog (database) if it exists
            history_cog = self.bot.get_cog('History')
            if history_cog and hasattr(history_cog, 'log_action'):
                history_cog.log_action(ctx.guild.id, member.id, "Banned", ctx.author, reason)


        except discord.Forbidden: # Should be caught by @bot_has_permissions or hierarchy checks now
            await self._send_ban_error_embed(ctx, "Permissions Error", "I don't have permission to ban members, or I encountered a role hierarchy issue I couldn't pre-check.")
        except discord.HTTPException as e:
            await self._send_ban_error_embed(ctx, "API Error", f"Failed to ban due to an API error: {str(e)}")
        except Exception as e:
            await self._send_ban_error_embed(ctx, "Unexpected Error", f"An unexpected error occurred during ban: {str(e)}")
            print(f"Unexpected error in ban_command: {e}")
            traceback.print_exc()

    @ban_command.error # Ensure this decorator points to the correct command method name
    async def ban_command_error(self, ctx, error):
        error_title = "Ban Command Error"
        if isinstance(error, commands.MissingPermissions):
            await self._send_ban_error_embed(ctx, error_title, "You need 'Ban Members' permission to use this command.")
        elif isinstance(error, commands.BotMissingPermissions):
            missing_perms_str = ", ".join(error.missing_permissions)
            await self._send_ban_error_embed(ctx, error_title, f"I am missing the required permission(s) to ban members: `{missing_perms_str}`.")
        elif isinstance(error, commands.MemberNotFound):
            await self._send_ban_error_embed(ctx, error_title, f"Member not found: `{error.argument}`. Please provide a valid member (mention, ID, or name).")
        elif isinstance(error, commands.MissingRequiredArgument):
            if error.param.name == "member":
                await self._send_ban_error_embed(ctx, error_title, "You need to specify which member to ban.\nUsage: `.ban <@user/ID> [reason]`")
        elif isinstance(error, commands.CommandInvokeError):
            # This will catch errors that happen inside the command itself, like our manual hierarchy checks failing
            # or the discord.Forbidden if it somehow wasn't caught by the hierarchy checks.
            original_error_text = str(error.original) if hasattr(error.original, 'text') else str(error.original)
            await self._send_ban_error_embed(ctx, error_title, f"An error occurred while trying to ban: {original_error_text}")
            print(f"CommandInvokeError in ban_command: {error.original}")
            traceback.print_exc()
        else:
            await self._send_ban_error_embed(ctx, error_title, f"An unexpected error occurred: {error}")
            print(f"Unhandled error in ban_command_error: {error}")
            traceback.print_exc()

async def setup(bot):
    await bot.add_cog(Ban(bot))
