from discord.ext import commands
import discord

class Ban(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command()
    @commands.has_permissions(ban_members=True)
    async def ban(self, ctx, member: discord.Member, *, reason=None):
        try:
            await member.ban(reason=reason)
            await ctx.send(f"Banned {member.mention} for: {reason or 'No reason provided'}")
        except discord.Forbidden:
            await ctx.send("I don't have permission to ban this member.")
        except discord.HTTPException as e:
            await ctx.send(f"Failed to ban: {str(e)}")

    @ban.error
    async def ban_error(self, ctx, error):
        if isinstance(error, commands.MissingPermissions):
            await ctx.send("You need 'Ban Members' permission to use this command.")
        elif isinstance(error, commands.MissingRequiredArgument):
            await ctx.send("Please specify a member to ban (e.g., .ban @user reason).")
        elif isinstance(error, commands.BadArgument):
            await ctx.send("Invalid member specified. Use .ban @user [reason].")

async def setup(bot):
    await bot.add_cog(Ban(bot))
