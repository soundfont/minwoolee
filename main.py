import discord
from discord.ext import commands

intents = discord.Intents.default()
intents.message_content = True  # this is crucial

bot = commands.Bot(command_prefix='.', intents=intents)

@bot.event
async def on_ready():
    print(f'logged in as {bot.user}')

@bot.command()
async def ping(ctx):
    await ctx.send('pong!')

import os
token = os.getenv('DISCORD_BOT_TOKEN')
bot.run(token)
