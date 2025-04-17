from discord.ext import commands
import discord

class Utils(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    def create_embed(self, ctx, title, description=None, color=discord.Color.blue()):
        """
        Create a standardized embed with server icon thumbnail, footer, and timestamp.
        Args:
            ctx: Command context
            title: Embed title
            description: Embed description (optional)
            color: Embed color (default: blue)
        Returns:
            discord.Embed object
        """
        embed = discord.Embed(
            title=title,
            description=description,
            color=color,
            timestamp=discord.utils.utcnow()
        )
        # Set server icon as thumbnail if available
        if ctx.guild and ctx.guild.icon:
            embed.set_thumbnail(url=ctx.guild.icon.url)
        # Set footer with requester's name and avatar
        embed.set_footer(
            text=f"Requested by {ctx.author}",
            icon_url=ctx.author.avatar.url if ctx.author.avatar else None
        )
        return embed

async def setup(bot):
    await bot.add_cog(Utils(bot))
