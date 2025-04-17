from discord.ext import commands
import discord

class MemberCount(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(aliases=['mc'])
    async def membercount(self, ctx):
        try:
            # Get member counts
            guild = ctx.guild
            total_members = guild.member_count
            bot_count = sum(1 for member in guild.members if member.bot)
            human_count = total_members - bot_count

            # Create embed
            embed = discord.Embed(
                title=f"{guild.name} Member Count",
                color=discord.Color.blue(),
                timestamp=discord.utils.utcnow()
            )
            embed.add_field(name="Humans", value=human_count, inline=True)
            embed.add_field(name="Bots", value=bot_count, inline=True)
            embed.add_field(name="Total", value=total_members, inline=True)
            embed.set_footer(text=f"Requested by {ctx.author}", icon_url=ctx.author.avatar.url if ctx.author.avatar else None)

            # Send embed
            await ctx.send(embed=embed)
        except discord.Forbidden:
            await ctx.send("I don't have permission to send embeds in this channel.")
        except discord.HTTPException as e:
            await ctx.send(f"Failed to send member count: {str(e)}")

    @membercount.error
    async def membercount_error(self, ctx, error):
        if isinstance(error, commands.MissingPermissions):
            await ctx.send("You need 'Send Messages' permission to use this command.")
        elif isinstance(error, commands.CommandInvokeError):
            await ctx.send("An error occurred while fetching the member count.")

async def setup(bot):
    await bot.add_cog(MemberCount(bot))
