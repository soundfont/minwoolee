from discord.ext import commands
import discord

class Kick(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command()
    @commands.has_permissions(kick_members=True)
    async def kick(self, ctx, member: discord.Member, *, reason=None):
        try:
            await member.kick(reason=reason)
            await ctx.send(f"Kicked {member.mention} for: {reason or 'No reason provided'}")
        except discord.Forbidden:
            await ctx.send("I don't have permission to kick this member.")
        except discord.HTTPException as e:
            await ctx.send(f"Failed to kick: {str(e)}")

    @kick.error
    async def kick_error(self, ctx, error):
        if isinstance(error, commands.MissingPermissions):
            await ctx.send("You need 'Kick Members' permission to use this command.")
        elif isinstance(error, commands.MissingRequiredArgument):
            await ctx.send("Please specify a member to kick (e.g., .kick @user reason).")
        elif isinstance(error, commands.BadArgument):
            await ctx.send("Invalid member specified. Use .kick @user [reason].")

async def setup(bot):
    await bot.add_cog(Kick(bot))
