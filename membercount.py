class membercount(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="membercount")
    @commands.command(name="mc")  # This allows both .membercount and .mc
    async def member_count(self, ctx):
        """Shows the member count of the server."""
        guild = ctx.guild
        total_members = guild.member_count
        humans = sum(1 for member in guild.members if not member.bot)
        bots = total_members - humans

        embed = discord.Embed(
            title=f"Member Count for {guild.name}",
            color=discord.Color.blue()
        )
        embed.add_field(name="Total Members", value=str(total_members), inline=False)
        embed.add_field(name="Humans", value=str(humans), inline=False)
        embed.add_field(name="Bots", value=str(bots), inline=False)

        await ctx.send(embed=embed)
