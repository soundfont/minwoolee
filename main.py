import discord
from discord.ext import commands
import os
import asyncio

# Initialize bot with . prefix and intents
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='.', intents=intents)

# Load cogs
async def load_cogs():
    for filename in os.listdir('./cogs'):
        if filename.endswith('.py'):
            await bot.load_extension(f'cogs.{filename[:-3]}')
            print(f'Loaded cog: {filename[:-3]}')

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
