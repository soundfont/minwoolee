import os
import discord
from discord.ext import commands

# set the command prefix
bot = commands.Bot(command_prefix='.', intents=discord.Intents.default())

@bot.event
async def on_ready():
    print(f'logged in as {bot.user}')

# simple command: .ping
@bot.command()
async def ping(ctx):
    await ctx.send('pong')

token = os.getenv('DISCORD_BOT_TOKEN')
bot.run(token)
