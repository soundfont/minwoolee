import discord
from discord.ext import commands
import asyncio # For adding delays

class YesNoReactor(commands.Cog):
    """
    A cog that reacts to messages containing "y/n" with up and down arrows,
    only if there is other text in the message.
    Ensures the up arrow is processed first.
    """
    def __init__(self, bot: commands.Bot):
        """
        Initializes the YesNoReactor cog.

        Args:
            bot: The instance of the Discord bot.
        """
        self.bot = bot

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """
        Listens for new messages and reacts if they contain "y/n"
        and additional text. Adds an up arrow, then a small delay,
        then a down arrow.

        Args:
            message: The discord.Message object representing the new message.
        """
        # Ignore messages sent by bots (including this one) to prevent loops
        if message.author.bot:
            return

        trigger_phrase = "y/n"
        lower_content = message.content.lower() # Convert to lowercase once for efficiency

        # Check if "y/n" is present in the message content
        if trigger_phrase in lower_content:
            # Also check that the message is not *just* "y/n" (ignoring leading/trailing spaces)
            if lower_content.strip() != trigger_phrase:
                # Define the emojis to react with
                up_arrow = "⬆️"  # Unicode: \U00002B06
                down_arrow = "⬇️" # Unicode: \U00002B07

                try:
                    # Add the up arrow reaction
                    await message.add_reaction(up_arrow)
                    
                    # Add a very small delay to help ensure Discord processes them in order
                    await asyncio.sleep(0.1) # 100 milliseconds delay
                    
                    # Add the down arrow reaction
                    await message.add_reaction(down_arrow)
                    
                    print(f"Reacted to message ID {message.id} from {message.author.name} containing '{trigger_phrase}' with other text.")

                except discord.Forbidden:
                    print(f"Error: Could not add reactions to message {message.id} in channel {message.channel.id}. "
                          "Reason: Missing 'Add Reactions' permission.")
                except discord.HTTPException as e:
                    print(f"Error: Failed to add reactions to message {message.id}. Reason: {e}")
                except Exception as e:
                    print(f"An unexpected error occurred while trying to react to message {message.id}: {e}")

async def setup(bot: commands.Bot):
    """
    The setup function to load the cog.
    This is called by discord.py when the extension is loaded.

    Args:
        bot: The instance of the Discord bot.
    """
    await bot.add_cog(YesNoReactor(bot))
    print("Cog 'YesNoReactor' loaded successfully (updated with additional text check).")
