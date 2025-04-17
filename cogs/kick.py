from discord.ext import commands
import discord

class Kick(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command()
    @commands.has_permissions(kick_members=True)
    async def kick(self, ctx, member: discord.Member, *, reason=None):
        try:
            # Kick the member
            await member.kick(reason=reason)

            # Log the action
            history = self.bot.get_cog('History')
            if history:
                history.log_action(ctx.guild.id, member.id, "Kicked", ctx.author, reason)

            # Create embed using utils
            utils = self.bot.get_cog('Utils')
            if not utils:
                await ctx.send("Error: Utils cog not loaded.")
                return

            embed = utils.create_embed(ctx, title="Member Kicked")
            embed.description = f"Kicked {member.mention}"
            if reason:
                embed.description += f"\n**Reason:** {reason}"

            await ctx.send(embed=embed)

        except discord.Forbidden:
            await ctx.send("I don't have permission to kick members (requires 'Kick Members').")
        except discord.HTTPException as e:
            await ctx.send(f"Failed to kick: {str(e)}")

    @kick.error
    async def kick_error(self, ctx, error):
        if isinstance(error, commands.MissingPermissions):
            await ctx.send("You need 'Kick Members' permission to use this command.")
        elif isinstance(error, commands.MemberNotFound):
            await ctx.send("Member not found. Please provide a valid member (mention or ID).")
        elif isinstance(error, commands.CommandInvokeError):
            await ctx.send("An error occurred while executing the kick command.")

async def setup(bot):
    await bot.add_cog(Kick(bot))
