import os
import discord
from discord.ext import commands
from dotenv import load_dotenv

TOKEN = os.getenv('DISCORD_BOT_TOKEN')

# Create the bot object with a command prefix
intents = discord.Intents.default()
bot = commands.Bot(command_prefix=".", intents=intents)

# Event when the bot is ready
@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")
    bot.load_extension("instagram")
    bot.load_extension("membercount")

# Run the bot with your token (this is where the token is used)
bot.run(TOKEN)  # Your token goes here!
