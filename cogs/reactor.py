import discord
from discord.ext import commands
import asyncio

class ContextualReactor(commands.Cog):
    """
    A cog that reacts to messages containing "y/n" or "v/s".
    It only reacts to the *last* occurrence of either phrase found in the message.
    It also requires additional text beyond just the trigger phrase itself.
    - "y/n" gets Up/Down arrows.
    - "v/s" gets Left/Right arrows.
    """
    def __init__(self, bot: commands.Bot):
        """
        Initializes the ContextualReactor cog.

        Args:
            bot: The instance of the Discord bot.
        """
        self.bot = bot
        self.triggers = {
            "y/n": ("⬆️", "⬇️"),  # Trigger phrase and its reactions
            "v/s": ("⬅️", "➡️")
        }

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """
        Listens for new messages and reacts based on the last found trigger phrase.

        Args:
            message: The discord.Message object representing the new message.
        """
        # Ignore messages sent by bots
        if message.author.bot:
            return

        lower_content = message.content.lower()
        
        last_trigger_info = None # To store (index, phrase_key)

        # Find the last occurrence of any known trigger phrase
        for phrase_key in self.triggers.keys():
            try:
                # rfind gives the last occurrence's index
                index = lower_content.rfind(phrase_key)
                if index != -1: # If found
                    # If this phrase is later than the currently stored last one, update it
                    if last_trigger_info is None or index > last_trigger_info[0]:
                        last_trigger_info = (index, phrase_key)
            except Exception as e:
                print(f"Error finding phrase '{phrase_key}': {e}") # Should not happen with rfind
                continue

        # If a trigger phrase was found as the last one
        if last_trigger_info:
            active_phrase_key = last_trigger_info[1] # e.g., "y/n" or "v/s"

            # Condition: Message content stripped of whitespace must not be *identical* to the trigger phrase
            if lower_content.strip() != active_phrase_key:
                reactions_to_add = self.triggers[active_phrase_key]
                
                try:
                    # Add the first reaction
                    await message.add_reaction(reactions_to_add[0])
                    
                    # Small delay
                    await asyncio.sleep(0.1) 
                    
                    # Add the second reaction
                    await message.add_reaction(reactions_to_add[1])
                    
                    print(f"Reacted to message ID {message.id} from {message.author.name} for last phrase '{active_phrase_key}'.")

                except discord.Forbidden:
                    print(f"Error: Could not add reactions to message {message.id}. Reason: Missing 'Add Reactions' permission.")
                except discord.HTTPException as e:
                    print(f"Error: Failed to add reactions to message {message.id}. Reason: {e}")
                except Exception as e:
                    print(f"An unexpected error occurred while reacting to message {message.id}: {e}")

async def setup(bot: commands.Bot):
    """
    The setup function to load the cog.
    """
    await bot.add_cog(ContextualReactor(bot))
    print("Cog 'ContextualReactor' loaded successfully.")

