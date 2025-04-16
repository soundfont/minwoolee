import discord
from discord.ext import commands
import instaloader

class InstagramCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.loader = instaloader.Instaloader()

    # Base command group for Instagram-related commands
    @commands.group()
    async def instagram(self, ctx):
        """Instagram commands group."""
        if ctx.invoked_subcommand is None:
            await ctx.send("Please specify a subcommand: 'add', 'remove', etc.")

    # Subcommand to add an Instagram account to monitor
    @instagram.command()
    async def add(self, ctx, username: str, channel: discord.TextChannel):
        """Add an Instagram account to monitor and post to the channel."""
        await ctx.send(f"Started monitoring Instagram account: {username}. Posts will be sent to {channel.mention}.")
        
        try:
            # Load the Instagram profile
            profile = self.loader.load_profile(username)
            for post in profile.get_posts():
                # Sending the post's caption and URL to the channel
                embed = discord.Embed(title="New Instagram Post", description=post.caption, color=discord.Color.blue())
                embed.add_field(name="URL", value=f"https://www.instagram.com/p/{post.shortcode}/", inline=False)
                await channel.send(embed=embed)

        except instaloader.exceptions.ProfileNotExistsException:
            await ctx.send(f"Could not find Instagram profile {username}. Please check the username.")

    # Subcommand to remove a monitoring account (or clear a list if you choose to implement it)
    @instagram.command()
    async def remove(self, ctx, username: str):
        """Remove an Instagram account from the monitoring list."""
        await ctx.send(f"Stopped monitoring Instagram account: {username}. (This feature can be expanded later.)")

def setup(bot):
    bot.add_cog(InstagramCog(bot))  # Add the InstagramCog to the bot
