import discord
from discord.ext import commands
import os
import asyncio
import traceback

# Initialize bot with . prefix, intents, and no default help command
intents = discord.Intents.default()
intents.message_content = True
intents.members = True         # For Last.fm, AutoRole, etc.
intents.reactions = True       # For ReactionStats
intents.voice_states = True    # For VoiceMaster

bot = commands.Bot(command_prefix='.', intents=intents, help_command=None)

# Updated Load cogs function
async def load_cogs():
    print("Starting to load cogs...")
    cogs_path = './cogs'
    for item in os.listdir(cogs_path):
        item_path = os.path.join(cogs_path, item)
        if os.path.isfile(item_path) and item.endswith('.py'):
            # Load cogs directly in the ./cogs directory
            if item != "__init__.py": # Avoid trying to load __init__.py as a cog
                try:
                    await bot.load_extension(f'cogs.{item[:-3]}')
                    print(f'Successfully loaded cog: cogs.{item[:-3]}')
                except Exception as e:
                    print(f'Failed to load cog cogs.{item[:-3]}: {str(e)}')
                    traceback.print_exc()
        elif os.path.isdir(item_path):
            # Load cogs from subdirectories (like cogs/lastfm/)
            for sub_item in os.listdir(item_path):
                if sub_item.endswith('.py') and sub_item != "__init__.py":
                    try:
                        extension_path = f'cogs.{item}.{sub_item[:-3]}'
                        await bot.load_extension(extension_path)
                        print(f'Successfully loaded cog: {extension_path}')
                    except Exception as e:
                        print(f'Failed to load cog {extension_path}: {str(e)}')
                        traceback.print_exc()

# Bot ready event
@bot.event
async def on_ready():
    print(f'Logged in as {bot.user.name} (ID: {bot.user.id})')
    print(f'Discord.py Version: {discord.__version__}')
    await load_cogs() # Call the updated load_cogs

# Run bot
async def main():
    # from dotenv import load_dotenv # If using dotenv for local dev
    # load_dotenv()
    token = os.getenv('DISCORD_BOT_TOKEN')
    if not token:
        print("ERROR: DISCORD_BOT_TOKEN environment variable not set.")
        return
    
    try:
        await bot.start(token)
    except discord.LoginFailure:
        print("ERROR: Failed to log in. Check your bot token.")
    except Exception as e:
        print(f"ERROR: An unexpected error occurred during bot startup: {e}")
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())
