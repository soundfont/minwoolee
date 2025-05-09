import discord
from discord.ext import commands
import os
import asyncio
import traceback
from custom_context import EmbedContext  # import the custom context

# Initialize bot with . prefix, intents, and no default help command
intents = discord.Intents.default()
intents.message_content = True
intents.members = True

# Use the custom EmbedContext class
bot = commands.Bot(command_prefix='.', intents=intents, help_command=None, context_class=EmbedContext)

# Load cogs
async def load_cogs():
    print("Starting to load cogs...")
    for filename in os.listdir('./cogs'):
        if filename.endswith('.py'):
            try:
                await bot.load_extension(f'cogs.{filename[:-3]}')
                print(f'Successfully loaded cog: {filename[:-3]}')
            except Exception as e:
                print(f'Failed to load cog {filename[:-3]}: {str(e)}')
                traceback.print_exc()

# Bot ready event
@bot.event
async def on_ready():
    print(f'Logged in as {bot.user.name}')
    await load_cogs()

# Run bot using Heroku config var
async def main():
    token = os.getenv('DISCORD_BOT_TOKEN')
    if not token:
        raise ValueError("DISCORD_TOKEN environment variable not set")
    await bot.start(token)

if __name__ == "__main__":
    asyncio.run(main())
