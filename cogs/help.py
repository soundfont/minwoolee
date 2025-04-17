from discord.ext import commands

class Help(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command()
    async def help(self, ctx):
        await ctx.send("minwoolee's documentation can be found [here.](<https://github.com/soundfont/minwoolee-public/blob/main/README.md>)")

async def setup(bot):
    await bot.add_cog(Help(bot))
