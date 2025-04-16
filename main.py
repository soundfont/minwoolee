import discord
from discord.ext import commands
import asyncio

bot = commands.Bot(command_prefix=".")

async def load():
    await bot.load_extension("instagram")  # Load Instagram cog
    await bot.load_extension("membercount")  # Load BasicCommands cog

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")

if __name__ == "__main__":
    asyncio.run(load())  # Run the load function to properly load the cogs
    bot.run("YOUR_TOKEN")  # Replace with your bot token
