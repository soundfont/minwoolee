from discord.ext import commands
import discord
import datetime

class Timeout(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(aliases=['to'])
    @commands.has_permissions(moderate_members=True)
    async def timeout(self, ctx, member: discord.Member, duration: int, *, reason=None):
        try:
            # Convert duration (minutes) to timedelta
            if duration < 1 or duration > 40320:  # 40320 minutes = 28 days
                await ctx.send("Duration must be between 1 and 40320 minutes (28 days).")
                return
            timeout_until = discord.utils.utcnow() + datetime.timedelta(minutes=duration)
            await member.timeout(timeout_until, reason=reason)
            await ctx.send(f"Timed out {member.mention} for {duration} minutes. Reason: {reason or 'No reason provided'}")
        except discord.Forbidden:
            await ctx.send("I don't have permission to timeout this member.")
        except discord.HTTPException as e:
            await ctx.send(f"Failed to timeout: {str(e)}")

    @timeout.error
    async def timeout_error(self, ctx, error):
        if isinstance(error, commands.MissingPermissions):
            await ctx.send("You need 'Moderate Members' permission to use this command.")
        elif isinstance(error, commands.MissingRequiredArgument):
            await ctx.send("Please specify a member and duration (e.g., .timeout @user 5 reason).")
        elif isinstance(error, commands.BadArgument):
            await ctx.send("Invalid member or duration. Use .timeout @user [minutes] [reason].")

async def setup(bot):
    await bot.add_cog(Timeout(bot))
