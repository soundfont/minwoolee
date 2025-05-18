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
        print("[ClearBot DEBUG] Cog initialized.")

    @commands.command(name="bc", aliases=["botclear"])
    @commands.has_permissions(manage_messages=True)
    @commands.bot_has_permissions(manage_messages=True, read_message_history=True)
    async def clear_bot_messages_command(self, ctx: commands.Context, limit: int = 100): # Renamed method
        """
        Clears bot commands and bot messages from the current channel.
        Scans up to 'limit' recent messages (default 100).
        Usage: .bc [number_of_messages_to_scan]
        Example: .bc 50
        """
        print(f"[ClearBot DEBUG] '.bc' command invoked by {ctx.author} in #{ctx.channel.name} (Guild: {ctx.guild.id}). Limit: {limit}")

        if limit <= 0:
            await ctx.send("Please provide a positive number for the limit.")
            print(f"[ClearBot DEBUG] Invalid limit: {limit}")
            return
        
        if limit > 200: 
            limit = 200
            print(f"[ClearBot DEBUG] Limit capped at 200.")
            await ctx.send("Scanning limit capped at 200 messages for performance.", delete_after=10)

        try:
            await ctx.message.delete()
            print(f"[ClearBot DEBUG] Command message deleted successfully.")
        except discord.Forbidden:
            print(f"[ClearBot DEBUG] Could not delete command message in #{ctx.channel.name} - Missing Permissions.")
        except discord.HTTPException as e:
            print(f"[ClearBot DEBUG] Failed to delete command message in #{ctx.channel.name} - HTTPException: {e}")
        except Exception as e:
            print(f"[ClearBot DEBUG] Error deleting command message: {e}")

        def is_bot_related(message: discord.Message) -> bool:
            is_related = False
            if message.author.id == self.bot.user.id:
                print(f"[ClearBot DEBUG] is_bot_related: Message {message.id} IS from bot ({message.author.name}).")
                is_related = True
            elif isinstance(self.bot.command_prefix, str):
                if message.content.startswith(self.bot.command_prefix):
                    print(f"[ClearBot DEBUG] is_bot_related: Message {message.id} from {message.author.name} starts with prefix '{self.bot.command_prefix}'. Content: '{message.content[:50]}...'")
                    is_related = True
            elif callable(self.bot.command_prefix):
                print(f"[ClearBot DEBUG] is_bot_related: Command prefix is callable. This check might not catch all command invocations for message {message.id}.")
                pass 
            else: 
                for prefix in self.bot.command_prefix:
                    if message.content.startswith(prefix):
                        print(f"[ClearBot DEBUG] is_bot_related: Message {message.id} from {message.author.name} starts with prefix '{prefix}'. Content: '{message.content[:50]}...'")
                        is_related = True
                        break 
            return is_related

        try:
            print(f"[ClearBot DEBUG] Attempting to purge up to {limit} messages in #{ctx.channel.name}...")
            deleted_messages = await ctx.channel.purge(limit=limit, check=is_bot_related, bulk=True)
            
            deleted_count = len(deleted_messages)
            print(f"[ClearBot DEBUG] Purged {deleted_count} messages.")
            confirmation_message_text = f"🧹 Cleared {deleted_count} bot-related message(s) from the last {limit} scanned messages."
            
            utils_cog = self.bot.get_cog('Utils') 

            if utils_cog:
                embed = utils_cog.create_embed(ctx, title="Bot Messages Cleared", description=confirmation_message_text, color=discord.Color.light_grey())
                await ctx.send(embed=embed, delete_after=10)
            else: 
                await ctx.send(confirmation_message_text, delete_after=10)

        except discord.Forbidden as e:
            print(f"[ClearBot DEBUG] FORBIDDEN error during purge: {e}")
            await ctx.send("I don't have the required 'Manage Messages' permission to clear messages here.")
        except discord.HTTPException as e:
            print(f"[ClearBot DEBUG] HTTPException during purge: {e}")
            await ctx.send(f"An API error occurred: {e}")
        except Exception as e:
            print(f"[ClearBot DEBUG] UNEXPECTED error during purge: {e}")
            await ctx.send(f"An unexpected error occurred: {e}")
            traceback.print_exc()

    @clear_bot_messages_command.error # Updated error handler decorator
    async def clear_bot_messages_command_error(self, ctx, error): # Renamed error handler method for consistency
        print(f"[ClearBot DEBUG] Error handler triggered for .bc: {type(error).__name__} - {error}")
        if isinstance(error, commands.MissingPermissions):
            await ctx.send("You need 'Manage Messages' permission to use this command.")
        elif isinstance(error, commands.BotMissingPermissions):
            missing_perms = ", ".join(error.missing_permissions)
            await ctx.send(f"I am missing the following permissions to do that: `{missing_perms}`.")
        elif isinstance(error, commands.BadArgument):
            await ctx.send("Invalid limit provided. Please enter a number (e.g., `.bc 50`).")
        else:
            await ctx.send(f"An error occurred with the .bc command. Please check the console.")
            traceback.print_exc() 

async def setup(bot: commands.Bot):
    await bot.add_cog(ClearBot(bot))
    print("Cog 'ClearBot' (Fixed Naming, No ModLog) loaded successfully.")

