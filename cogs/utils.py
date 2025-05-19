import discord
from discord.ext import commands
import datetime 
from typing import Optional, Union # For type hinting

class Utils(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        print("[Utils DEBUG] Cog initialized.")

    def create_embed(self, 
                     ctx: Optional[Union[commands.Context, discord.Message]], 
                     title: str, 
                     description: Optional[str] = None, 
                     color: discord.Color = discord.Color.blue()) -> discord.Embed:
        """
        Create a standardized embed.
        Sets the server icon (if available) as the author icon at the top-left.
        Sets the footer with the requester's name and avatar.
        Timestamp is set to current UTC time.

        Args:
            ctx: The command context (discord.ext.commands.Context), a discord.Message object,
                 or None. If None, guild-specific and author-specific parts will be omitted.
            title: The title of the embed.
            description: The description of the embed (optional).
            color: The color of the embed (default: discord.Color.blue()).

        Returns:
            A discord.Embed object.
        """
        print(f"[Utils DEBUG] create_embed called. Title: '{title}', ctx type: {type(ctx)}")
        
        current_guild: Optional[discord.Guild] = None
        requester: Optional[Union[discord.User, discord.Member]] = None # Corrected type hint

        if ctx:
            if isinstance(ctx, commands.Context):
                current_guild = ctx.guild
                requester = ctx.author
                print(f"[Utils DEBUG] ctx is commands.Context. Guild: {current_guild.name if current_guild else 'None'}. Requester: {requester.name if requester else 'None'}.")
            elif isinstance(ctx, discord.Message): 
                current_guild = ctx.guild
                requester = ctx.author
                print(f"[Utils DEBUG] ctx is discord.Message. Guild: {current_guild.name if current_guild else 'None'}. Requester: {requester.name if requester else 'None'}.")
            else:
                print(f"[Utils DEBUG] ctx is provided but not Context or Message. Type: {type(ctx)}")
        else:
            print("[Utils DEBUG] ctx is None. Guild and Requester info will be omitted from author/footer.")

        embed = discord.Embed(
            title=title,
            description=description,
            color=color,
            timestamp=datetime.datetime.now(datetime.timezone.utc)
        )

        # Set server icon and name as the author field (top-left small circle)
        if current_guild:
            print(f"[Utils DEBUG] current_guild is '{current_guild.name}'. Checking for icon.")
            if current_guild.icon:
                print(f"[Utils DEBUG] Guild icon found: {current_guild.icon.url}")
                embed.set_author(name=current_guild.name, icon_url=current_guild.icon.url)
            else:
                print("[Utils DEBUG] Guild has no icon. Setting author name only.")
                embed.set_author(name=current_guild.name)
        else:
            print("[Utils DEBUG] current_guild is None. Skipping embed.set_author for server.")


        # Set footer with requester's name and avatar, if requester info is available
        if requester:
            print(f"[Utils DEBUG] Requester is '{requester.name}'. Setting footer.")
            footer_text = f"Requested by {requester.name}"
            avatar_url = requester.display_avatar.url 
            embed.set_footer(
                text=footer_text,
                icon_url=avatar_url
            )
        else:
            print("[Utils DEBUG] Requester is None. Skipping embed.set_footer.")
        
        print(f"[Utils DEBUG] Embed created. Author set: {bool(embed.author)}. Footer set: {bool(embed.footer)}.")
        return embed

async def setup(bot: commands.Bot):
    await bot.add_cog(Utils(bot))
    print("Cog 'Utils' (with enhanced debugging for server icon as author) loaded successfully.")

