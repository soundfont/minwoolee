from discord.ext import commands
from discord import app_commands

class Purge(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command()
    @commands.has_permissions(manage_messages=True)
    async def purge(self, ctx, amount: int):
        if amount < 1 or amount > 100:
            await ctx.send("Please specify an amount between 1 and 100.")
            return
        await ctx.channel.purge(limit=amount + 1)
        await ctx.send(f"Cleared {amount} messages.", delete_after=5)

    @clear.error
    async def clear_error(self, ctx, error):
        if isinstance(error, commands.MissingPermissions):
            await ctx.send("You need 'Manage Messages' permission to use this command.")
        elif isinstance(error, commands.MissingRequiredArgument):
            await ctx.send("Please specify the number of messages to purge (e.g., .purge 10).")

async def setup(bot):
    await bot.add_cog(Purge(bot))
