from discord.ext import commands
import discord

class Untimeout(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(aliases=['uto'])
    @commands.has_permissions(moderate_members=True)
    async def untimeout(self, ctx, member: discord.Member, *, reason=None):
        try:
            # Check if the member is timed out
            if not member.is_timed_out():
                await ctx.send(f"{member.mention} is not currently timed out.")
                return

            # Remove the timeout
            await member.timeout(None, reason=reason)

            # Log the action
            history = self.bot.get_cog('History')
            if history:
                history.log_action(ctx.guild.id, member.id, "Timeout Removed", ctx.author, reason)

            # Create embed using utils
            utils = self.bot.get_cog('Utils')
            if not utils:
                await ctx.send("Error: Utils cog not loaded.")
                return

            embed = utils.create_embed(ctx, title="Timeout Removed")
            embed.description = f"Removed timeout from {member.mention}"
            if reason:
                embed.description += f"\n**Reason:** {reason}"

            # Send embed
            await ctx.send(embed=embed)

        except discord.Forbidden:
            await ctx.send("I don't have permission to remove timeouts (requires 'Moderate Members').")
        except discord.HTTPException as e:
            await ctx.send(f"Failed to remove timeout: {str(e)}")

    @untimeout.error
    async def untimeout_error(self, ctx, error):
        if isinstance(error, commands.MissingPermissions):
            await ctx.send("You need 'Moderate Members' permission to use this command.")
        elif isinstance(error, commands.MemberNotFound):
            await ctx.send("Member not found. Please provide a valid member (mention or ID).")
        elif isinstance(error, commands.CommandInvokeError):
            await ctx.send("An error occurred while executing the untimeout command.")

async def setup(bot):
    await bot.add_cog(Untimeout(bot))
