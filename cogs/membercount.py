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

            # Create embed using utils
            utils = self.bot.get_cog('Utils')
            if not utils:
                await ctx.send("Error: Utils cog not loaded.")
                return
            embed = utils.create_embed(ctx, title=f"{guild.name} statistics")

            # Add fields
            embed.add_field(name="Humans", value=human_count, inline=True)
            embed.add_field(name="Bots", value=bot_count, inline=True)
            embed.add_field(name="Total", value=total_members, inline=True)

            # Send embed
            await ctx.send(embed=embed)
        except discord.Forbidden:
            await ctx.send("I don't have permission to send embeds in this channel.")
        except discord.HTTPException as e:
            await ctx.send(f"Failed to send statistics: {str(e)}")

    @membercount.error
    async def membercount_error(self, ctx, error):
        if isinstance(error, commands.MissingPermissions):
            await ctx.send("You need 'Send Messages' permission to use this command.")
        elif isinstance(error, commands.CommandInvokeError):
            await ctx.send("An error occurred while fetching the statistics.")

async def setup(bot):
    await bot.add_cog(MemberCount(bot))
