from discord.ext import commands
import discord

class Bans(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command()
    @commands.has_permissions(ban_members=True)
    async def bans(self, ctx):
        try:
            # Fetch banned users
            banned_users = []
            async for ban_entry in ctx.guild.bans():
                banned_users.append(ban_entry.user)

            if not banned_users:
                await ctx.send("No users are currently banned from this server.")
                return

            # Limit to 10 users for readability (can expand with pagination later)
            display_users = banned_users[:10]
            description = "\n".join([f"{user.mention} (ID: {user.id})" for user in display_users])

            if len(banned_users) > 10:
                description += "\n*Note: Only the first 10 banned users are shown. Use pagination in future updates.*"

            # Create embed using utils
            utils = self.bot.get_cog('Utils')
            if not utils:
                await ctx.send("Error: Utils cog not loaded.")
                return

            embed = utils.create_embed(ctx, title="Banned Users")
            embed.description = description

            # Send embed
            await ctx.send(embed=embed)

        except discord.Forbidden:
            await ctx.send("I don't have permission to view banned users (requires 'Ban Members').")
        except discord.HTTPException as e:
            await ctx.send(f"Failed to fetch banned users: {str(e)}")

    @bans.error
    async def bans_error(self, ctx, error):
        if isinstance(error, commands.MissingPermissions):
            await ctx.send("You need 'Ban Members' permission to use this command.")
        elif isinstance(error, commands.CommandInvokeError):
            await ctx.send("An error occurred while executing the bans command.")

async def setup(bot):
    await bot.add_cog(Bans(bot))
