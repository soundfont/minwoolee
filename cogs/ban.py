from discord.ext import commands
import discord

class Ban(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command()
    @commands.has_permissions(ban_members=True)
    async def ban(self, ctx, member: discord.Member, *, reason=None):
        try:
            # Ban the member
            await member.ban(reason=reason)

            # Log the action
            history = self.bot.get_cog('History')
            if history:
                history.log_action(ctx.guild.id, member.id, "Banned", ctx.author, reason)

            # Create embed using utils
            utils = self.bot.get_cog('Utils')
            if not utils:
                await ctx.send("Error: Utils cog not loaded.")
                return

            embed = utils.create_embed(ctx, title="Member Banned")
            embed.description = f"Banned {member.mention}"
            if reason:
                embed.description += f"\n**Reason:** {reason}"

            await ctx.send(embed=embed)

        except discord.Forbidden:
            await ctx.send("I don't have permission to ban members (requires 'Ban Members').")
        except discord.HTTPException as e:
            await ctx.send(f"Failed to ban: {str(e)}")

    @ban.error
    async def ban_error(self, ctx, error):
        if isinstance(error, commands.MissingPermissions):
            await ctx.send("You need 'Ban Members' permission to use this command.")
        elif isinstance(error, commands.MemberNotFound):
            await ctx.send("Member not found. Please provide a valid member (mention or ID).")
        elif isinstance(error, commands.CommandInvokeError):
            await ctx.send("An error occurred while executing the ban command.")

async def setup(bot):
    await bot.add_cog(Ban(bot))
