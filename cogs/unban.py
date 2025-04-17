from discord.ext import commands
import discord

class Unban(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command()
    @commands.has_permissions(ban_members=True)
    async def unban(self, ctx, user: discord.User, *, reason=None):
        try:
            # Check if the user is actually banned
            ban_entry = None
            async for ban in ctx.guild.bans():
                if ban.user.id == user.id:
                    ban_entry = ban
                    break

            if not ban_entry:
                await ctx.send(f"{user} is not banned from this server.")
                return

            # Unban the user
            await ctx.guild.unban(user, reason=reason)

            # Log the action
            history = self.bot.get_cog('History')
            if history:
                history.log_action(ctx.guild.id, user.id, "Unbanned", ctx.author, reason)

            # Create embed using utils
            utils = self.bot.get_cog('Utils')
            if not utils:
                await ctx.send("Error: Utils cog not loaded.")
                return

            embed = utils.create_embed(ctx, title="User Unbanned")
            embed.description = f"Unbanned {user.mention}"
            if reason:
                embed.description += f"\n**Reason:** {reason}"

            await ctx.send(embed=embed)

        except discord.Forbidden:
            await ctx.send("I don't have permission to unban members (requires 'Ban Members').")
        except discord.HTTPException as e:
            await ctx.send(f"Failed to unban: {str(e)}")

    @unban.error
    async def unban_error(self, ctx, error):
        if isinstance(error, commands.MissingPermissions):
            await ctx.send("You need 'Ban Members' permission to use this command.")
        elif isinstance(error, commands.UserNotFound):
            await ctx.send("User not found. Please provide a valid user (ID, mention, or username#discriminator).")
        elif isinstance(error, commands.CommandInvokeError):
            await ctx.send("An error occurred while executing the unban command.")

async def setup(bot):
    await bot.add_cog(Unban(bot))
