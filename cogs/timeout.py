from discord.ext import commands
import discord
from datetime import timedelta

class Timeout(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(aliases=['to'])
    @commands.has_permissions(moderate_members=True)
    async def timeout(self, ctx, member: discord.Member, minutes: int, *, reason=None):
        try:
            # Validate minutes (max 28 days = 40320 minutes)
            if minutes <= 0 or minutes > 40320:
                await ctx.send("Timeout duration must be between 1 minute and 28 days (40320 minutes).")
                return

            # Check role hierarchy
            bot_member = ctx.guild.me
            if not bot_member.top_role > member.top_role:
                await ctx.send("I cannot timeout this member because my role is not higher than theirs.")
                return

            # Apply the timeout
            duration = timedelta(minutes=minutes)
            await member.timeout(duration, reason=reason)
            await ctx.send("DEBUG: Timeout action completed.")  # Debug message

            # Log the action
            history = self.bot.get_cog('History')
            if history:
                await ctx.send("DEBUG: History cog found, logging action.")  # Debug message
                history.log_action(ctx.guild.id, member.id, f"Timed Out ({minutes} minutes)", ctx.author, reason)
            else:
                await ctx.send("DEBUG: History cog not found, skipping logging.")  # Debug message

            # Create embed using utils
            utils = self.bot.get_cog('Utils')
            if not utils:
                await ctx.send("Error: Utils cog not loaded.")
                return

            embed = utils.create_embed(ctx, title="Member Timed Out")
            embed.description = f"Timed out {member.mention} for {minutes} minutes"
            if reason:
                embed.description += f"\n**Reason:** {reason}"

            await ctx.send(embed=embed)

        except discord.Forbidden:
            await ctx.send("I don't have permission to timeout members (requires 'Moderate Members') or my role is too low.")
        except discord.HTTPException as e:
            await ctx.send(f"Failed to timeout due to an API error: {str(e)}")
        except Exception as e:
            await ctx.send(f"Unexpected error during timeout: {str(e)}")
            raise e  # Re-raise for Heroku logs

    @timeout.error
    async def timeout_error(self, ctx, error):
        if isinstance(error, commands.MissingPermissions):
            await ctx.send("You need 'Moderate Members' permission to use this command.")
        elif isinstance(error, commands.MemberNotFound):
            await ctx.send("Member not found. Please provide a valid member (mention or ID).")
        elif isinstance(error, commands.MissingRequiredArgument):
            await ctx.send("Usage: `.timeout <@user> <minutes> [reason]`")
        elif isinstance(error, commands.BadArgument):
            await ctx.send("Please provide a valid member and number of minutes.")
        elif isinstance(error, commands.CommandInvokeError):
            await ctx.send("An error occurred while executing the timeout command. Check bot logs for details.")

async def setup(bot):
    await bot.add_cog(Timeout(bot))
