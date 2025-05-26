import discord
from discord.ext import commands
from discord import app_commands # Kept from original
import typing # Required for typing.Union and typing.Optional

class Purge(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(
        name="purge",
        aliases=['clear'], # Optional: you can add aliases like 'clear'
        help="Purges messages with flexible syntax.\n\n"
             "▶ Purge messages from a specific user:\n"
             "   `.purge @user <amount>`\n"
             "   Example: `.purge @TestUser 50`\n\n"
             "▶ Purge messages from anyone in the channel:\n"
             "   `.purge <amount>`\n"
             "   Example: `.purge 25`\n\n"
             "Amount should be between 1 and 100."
    )
    @commands.has_permissions(manage_messages=True)
    async def purge(self, ctx, target: typing.Union[discord.Member, int], amount_for_user: typing.Optional[int] = None):
        user_to_purge: typing.Optional[discord.Member] = None
        num_to_delete: int = 0

        if isinstance(target, discord.Member):
            # This is the `.purge @user <amount>` case
            user_to_purge = target
            if amount_for_user is None:
                await ctx.send(f"Please specify how many messages to delete from {user_to_purge.mention}.\n"
                               f"Usage: `{ctx.prefix}purge {user_to_purge.mention} <amount>`")
                return
            # The converter for Optional[int] handles if amount_for_user is not a valid int when provided.
            # If it's not provided, it's None. If it's provided but not an int, BadArgument is raised.
            num_to_delete = amount_for_user
        elif isinstance(target, int):
            # This is the `.purge <amount>` case
            if amount_for_user is not None:
                # This means user typed something like ".purge 10 20"
                # (If they typed ".purge 10 @user", amount_for_user would likely fail conversion to int by discord.py, raising BadArgument)
                await ctx.send(f"Invalid syntax. To purge messages from anyone, use `{ctx.prefix}purge <amount>` (e.g., `{ctx.prefix}purge 50`).\n"
                               f"To purge from a user, use `{ctx.prefix}purge @user <amount>`.")
                return
            num_to_delete = target
            user_to_purge = None # Explicitly set user to None for general purge
        else:
            # This state should ideally not be reached if discord.py's Union converter and argument parsing work as expected.
            # A BadArgument error for 'target' would likely have been raised by discord.py already.
            # We can rely on the purge_error handler to inform the user.
            return

        if not (1 <= num_to_delete <= 100):
            await ctx.send("Please specify an amount to delete between 1 and 100.")
            return

        try:
            await ctx.message.delete() # Delete the command message
            deleted_count = 0

            if user_to_purge:
                # Personalized purge
                def check_user(message):
                    return message.author == user_to_purge
                
                deleted_messages = await ctx.channel.purge(limit=num_to_delete, check=check_user)
                deleted_count = len(deleted_messages)
                await ctx.send(f"Purged {deleted_count} of {user_to_purge.mention}'s messages.", delete_after=5)
            else:
                # General purge
                deleted_messages = await ctx.channel.purge(limit=num_to_delete)
                deleted_count = len(deleted_messages)
                await ctx.send(f"Purged {deleted_count} messages.", delete_after=5)

        except discord.Forbidden:
            await ctx.send("I lack the necessary permissions to delete messages. Please ensure I have 'Manage Messages'.")
        except discord.HTTPException as e:
            await ctx.send(f"An API error occurred while trying to purge messages: {e}")
        except Exception as e: # Catch any other unexpected errors during purge logic
            await ctx.send(f"An unexpected error occurred during the purge operation: {e}")
            print(f"Unexpected error in purge command logic: {e}")


    @purge.error
    async def purge_error(self, ctx, error):
        if isinstance(error, commands.MissingPermissions):
            await ctx.send("You need the 'Manage Messages' permission to use this command.")
        elif isinstance(error, commands.MissingRequiredArgument):
            if error.param.name == 'target': # This is the first argument (user or amount)
                await ctx.send(f"You're missing some arguments. Please specify a user and amount, or just an amount.\n"
                               f"Usage 1: `{ctx.prefix}purge @user <amount>`\n"
                               f"Usage 2: `{ctx.prefix}purge <amount>`")
            else: # Should not typically happen with this command structure
                await ctx.send(f"Missing argument: {error.param.name}. Use `{ctx.prefix}help purge` for info.")
        
        elif isinstance(error, commands.BadArgument):
            # param.name can help identify which argument failed
            param_name = getattr(error, 'param', None)
            if param_name and param_name.name == 'target':
                await ctx.send(f"Invalid first argument. It must be a @user (or user ID) or an amount (a number).\n"
                               f"Example 1: `{ctx.prefix}purge @SomeUser 50`\n"
                               f"Example 2: `{ctx.prefix}purge 25`")
            elif param_name and param_name.name == 'amount_for_user':
                 await ctx.send(f"The amount provided for the user must be a number (1-100).\n"
                                f"Example: `{ctx.prefix}purge @SomeUser 50`")
            else: # More generic if specific parameter can't be identified
                 await ctx.send(f"Invalid argument: {error}. Please check the command syntax.\n"
                                f"Usage 1: `{ctx.prefix}purge @user <amount>`\n"
                                f"Usage 2: `{ctx.prefix}purge <amount>`")

        elif isinstance(error, commands.CommandInvokeError):
            original_error = error.original
            if isinstance(original_error, discord.Forbidden):
                await ctx.send("I lack permissions to perform this action (e.g., 'Manage Messages' or role hierarchy issues).")
            elif isinstance(original_error, discord.HTTPException):
                # This can happen for various reasons, e.g., trying to bulk delete messages older than 14 days.
                await ctx.send(f"An API error occurred: {original_error.text if hasattr(original_error, 'text') else 'Could not complete the action.'}")
            else:
                print(f"An unhandled error occurred in purge command (Invoke): {original_error}")
                await ctx.send("An unexpected error occurred during command execution.")
        else:
            print(f"An unhandled error occurred in purge command: {error}")
            await ctx.send("An unexpected error occurred. Please check the logs.")

async def setup(bot):
    await bot.add_cog(Purge(bot))
