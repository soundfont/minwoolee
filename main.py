import discord
from discord.ext import commands
import os

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix='.', intents=intents)

@bot.event
async def on_ready():
    print(f"{bot.user} is online and ready.")
    bot.load_extension("instagram")
    bot.load_extension("membercount")

# get your token from environment variable (safer than hardcoding)
token = os.getenv("DISCORD_BOT_TOKEN")

if __name__ == "__main__":
    bot.run(token)
