import discord
from discord.ext import commands
import datetime
import traceback
from typing import List

class ClearBot(commands.Cog):
    """
    A cog that provides a command to clear bot commands and bot messages from a channel.
    """
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.command(name="bc", aliases=["botclear"])
    @commands.has_permissions(manage_messages=True)
    @commands.bot_has_permissions(manage_messages=True, read_message_history=True)
    async def bot_clear(self, ctx: commands.Context, limit: int = 100):
        """
        Clears bot commands and bot messages from the current channel.
        Scans up to 'limit' recent messages (default 100).
        Usage: .bc [number_of_messages_to_scan]
        Example: .bc 50
        """
        if limit <= 0:
            await ctx.send("Please provide a positive number for the limit.")
            return
        
        # Attempt to delete the command message itself first
        try:
            await ctx.message.delete()
        except discord.Forbidden:
            print(f"ClearBot: Could not delete command message in {ctx.channel.name} - Missing Permissions.")
        except discord.HTTPException as e:
            print(f"ClearBot: Failed to delete command message in {ctx.channel.name} - HTTPException: {e}")


        def is_bot_related(message: discord.Message) -> bool:
            # Check if the message is from the bot itself
            if message.author == self.bot.user:
                return True
            # Check if the message starts with any of the bot's command prefixes
            # self.bot.command_prefix can be a string or an iterable of strings
            if isinstance(self.bot.command_prefix, str):
                if message.content.startswith(self.bot.command_prefix):
                    return True
            elif callable(self.bot.command_prefix):
                # If command_prefix is a callable, this check becomes more complex
                # For simplicity, we'll assume it's a string or list/tuple for this check.
                # A more robust solution would involve trying to get the prefix for the message.
                pass # Cannot easily check callable prefix here without more context
            else: # It's an iterable of prefixes
                for prefix in self.bot.command_prefix:
                    if message.content.startswith(prefix):
                        return True
            return False

        try:
            deleted_messages = await ctx.channel.purge(limit=limit, check=is_bot_related, bulk=True)
            
            deleted_count = len(deleted_messages)
            confirmation_message_text = f"🧹 Cleared {deleted_count} bot-related message(s) from the last {limit} scanned messages."
            
            # Send confirmation
            utils_cog = self.bot.get_cog('Utils') # Assumes you have a Utils cog for embeds

            if utils_cog:
                embed = utils_cog.create_embed(ctx, title="Bot Messages Cleared", description=confirmation_message_text, color=discord.Color.light_grey())
                await ctx.send(embed=embed, delete_after=10)
            else: # Fallback if Utils cog is not available
                await ctx.send(confirmation_message_text, delete_after=10)

            # Logging to ModLog has been removed as per request.

        except discord.Forbidden:
            await ctx.send("I don't have the required 'Manage Messages' permission to clear messages here.")
        except discord.HTTPException as e:
            await ctx.send(f"An API error occurred: {e}")
        except Exception as e:
            await ctx.send(f"An unexpected error occurred: {e}")
            print(f"Error in bot_clear command: {e}")
            traceback.print_exc()

    @bot_clear.error
    async def bot_clear_error(self, ctx, error):
        if isinstance(error, commands.MissingPermissions):
            await ctx.send("You need 'Manage Messages' permission to use this command.")
        elif isinstance(error, commands.BotMissingPermissions):
            missing_perms = ", ".join(error.missing_permissions)
            await ctx.send(f"I am missing the following permissions to do that: `{missing_perms}`.")
        elif isinstance(error, commands.BadArgument):
            await ctx.send("Invalid limit provided. Please enter a number (e.g., `.bc 50`).")
        else:
            await ctx.send(f"An error occurred: {error}")
            print(f"Error in bot_clear_error handler: {error}")
            traceback.print_exc()

async def setup(bot: commands.Bot):
    await bot.add_cog(ClearBot(bot))
    print("Cog 'ClearBot' (without ModLog) loaded successfully.")

