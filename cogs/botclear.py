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
        Scans up to 'limit' recent messages (default 100, max usually around 100-200 for practical use).
        Usage: .bc [number_of_messages_to_scan]
        Example: .bc 50
        """
        if limit <= 0:
            await ctx.send("Please provide a positive number for the limit.")
            return
        
        # Discord's purge limit is effectively 100 messages at a time for bulk delete.
        # While history can fetch more, deleting more than 100 in one go via delete_messages isn't allowed.
        # channel.purge handles this by potentially making multiple calls if needed, but check functions are applied per message.
        # For simplicity and to avoid hitting API limits too hard, we'll keep the practical limit reasonable.
        # Let's process in chunks if limit > 100, or just cap it for this command's typical use case.
        # For now, we'll use the provided limit directly with channel.purge, which is efficient.

        await ctx.message.delete() # Delete the command message itself

        def is_bot_related(message: discord.Message) -> bool:
            # Check if the message is from the bot itself
            if message.author == self.bot.user:
                return True
            # Check if the message starts with the bot's command prefix
            if message.content.startswith(self.bot.command_prefix):
                return True
            return False

        try:
            # The purge command automatically handles messages older than 14 days (it can't delete them).
            # It also handles bulk deletion efficiently.
            deleted_messages = await ctx.channel.purge(limit=limit, check=is_bot_related, bulk=True)
            
            deleted_count = len(deleted_messages)
            confirmation_message = f"🧹 Cleared {deleted_count} bot-related message(s) from the last {limit} scanned messages."
            
            # Send confirmation and log to ModLog
            utils_cog = self.bot.get_cog('Utils')
            modlog_cog = self.bot.get_cog('ModLog')

            if utils_cog:
                embed = utils_cog.create_embed(ctx, title="Bot Messages Cleared", description=confirmation_message, color=discord.Color.light_grey())
                await ctx.send(embed=embed, delete_after=10)
            else:
                await ctx.send(confirmation_message, delete_after=10)

            if modlog_cog:
                await modlog_cog.log_moderation_action(
                    guild=ctx.guild,
                    action_title="Bot-Related Messages Cleared",
                    target_user=ctx.channel, # Target is effectively the channel
                    moderator=ctx.author,
                    reason=f"Used .bc command in {ctx.channel.mention}",
                    fields=[
                        ("Messages Scanned", str(limit)),
                        ("Messages Deleted", str(deleted_count))
                    ],
                    color=discord.Color.light_grey()
                )

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
    print("Cog 'ClearBot' loaded successfully.")
