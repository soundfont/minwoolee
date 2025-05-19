import discord
from discord.ext import commands
import datetime # Added for utcnow if not already present from discord.utils

class Utils(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    def create_embed(self, ctx: commands.Context, title: str, description: Optional[str] = None, color: discord.Color = discord.Color.blue()) -> discord.Embed:
        """
        Create a standardized embed.
        Sets the server icon (if available) as the author icon at the top-left.
        Sets the footer with the requester's name and avatar.
        Timestamp is set to current UTC time.

        Args:
            ctx: The command context (discord.ext.commands.Context) or a discord.Message object.
                 If None, guild-specific and author-specific parts will be omitted.
            title: The title of the embed.
            description: The description of the embed (optional).
            color: The color of the embed (default: discord.Color.blue()).

        Returns:
            A discord.Embed object.
        """
        
        # Determine guild and author from ctx, which could be Context or Message
        current_guild: Optional[discord.Guild] = None
        requester: Optional[discord.User | discord.Member] = None

        if ctx: # If ctx is provided
            if isinstance(ctx, commands.Context):
                current_guild = ctx.guild
                requester = ctx.author
            elif isinstance(ctx, discord.Message): # If a message object is passed
                current_guild = ctx.guild
                requester = ctx.author
            # If ctx is something else or None, current_guild and requester remain None

        embed = discord.Embed(
            title=title,
            description=description,
            color=color,
            timestamp=datetime.datetime.now(datetime.timezone.utc) # Use datetime.now(datetime.timezone.utc)
        )

        # Set server icon and name as the author field (top-left small circle)
        if current_guild and current_guild.icon:
            embed.set_author(name=current_guild.name, icon_url=current_guild.icon.url)
        elif current_guild: # Guild exists but no icon
             embed.set_author(name=current_guild.name)


        # Remove the old thumbnail setting for server icon:
        # if current_guild and current_guild.icon:
        #     embed.set_thumbnail(url=current_guild.icon.url) # This line is removed

        # Set footer with requester's name and avatar, if requester info is available
        if requester:
            footer_text = f"Requested by {requester.name}"
            avatar_url = requester.display_avatar.url # display_avatar handles default if no custom avatar
            embed.set_footer(
                text=footer_text,
                icon_url=avatar_url
            )
        
        return embed

async def setup(bot: commands.Bot):
    await bot.add_cog(Utils(bot))
    print("Cog 'Utils' (with server icon as author) loaded successfully.")

