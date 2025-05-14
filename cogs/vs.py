import discord
from discord.ext import commands
import asyncio # For adding delays

class VersusReactor(commands.Cog):
    """
    A cog that reacts to messages containing "v/s" with left and right arrows,
    only if there is other text in the message.
    Ensures the left arrow is processed first.
    """
    def __init__(self, bot: commands.Bot):
        """
        Initializes the VersusReactor cog.

        Args:
            bot: The instance of the Discord bot.
        """
        self.bot = bot

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """
        Listens for new messages and reacts if they contain "v/s"
        and additional text. Adds a left arrow, then a small delay,
        then a right arrow.

        Args:
            message: The discord.Message object representing the new message.
        """
        # Ignore messages sent by bots (including this one) to prevent loops
        if message.author.bot:
            return

        trigger_phrase = "v/s"
        lower_content = message.content.lower() # Convert to lowercase once for efficiency

        # Check if "v/s" is present in the message content
        if trigger_phrase in lower_content:
            # Also check that the message is not *just* "v/s" (ignoring leading/trailing spaces)
            if lower_content.strip() != trigger_phrase:
                # Define the emojis to react with
                left_arrow = "⬅️"  # Unicode: \U00002B05
                right_arrow = "➡️" # Unicode: \U000027A1

                try:
                    # Add the left arrow reaction
                    await message.add_reaction(left_arrow)
                    
                    # Add a very small delay to help ensure Discord processes them in order
                    await asyncio.sleep(0.1) # 100 milliseconds delay
                    
                    # Add the right arrow reaction
                    await message.add_reaction(right_arrow)
                    
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
    await bot.add_cog(VersusReactor(bot))
    print("Cog 'VersusReactor' loaded successfully (updated with additional text check).")
