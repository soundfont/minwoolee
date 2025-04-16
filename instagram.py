import discord
from discord.ext import commands
import json
import os

DATA_FILE = "instagram_data.json"

def load_data():
    if not os.path.exists(DATA_FILE):
        with open(DATA_FILE, "w") as f:
            json.dump({}, f)
    with open(DATA_FILE, "r") as f:
        return json.load(f)

def save_data(data):
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=4)

class InstagramCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.data = load_data()

    @commands.group()
    async def instagram(self, ctx):
        """Base command for managing Instagram subscriptions."""
        if ctx.invoked_subcommand is None:
            await ctx.send("invalid subcommand. try `.instagram add (user) #channel`, `.remove`, or `.view`")

    @instagram.command()
    async def add(self, ctx, username: str, channel: discord.TextChannel):
        """Subscribe to an Instagram user and set a drop channel."""
        user_id = str(ctx.author.id)
        new_sub = {"username": username.lower(), "channel_id": channel.id}

        if user_id not in self.data:
            self.data[user_id] = []

        # check for duplicates
        if new_sub in self.data[user_id]:
            await ctx.send(f"already subscribed to `{username}` in {channel.mention}")
            return

        self.data[user_id].append(new_sub)
        save_data(self.data)
        await ctx.send(f"subscribed to `{username}` — posts will drop in {channel.mention}")

    @instagram.command()
    async def remove(self, ctx, username: str, channel: discord.TextChannel):
        """Unsubscribe from an Instagram user in a channel."""
        user_id = str(ctx.author.id)
        if user_id not in self.data:
            await ctx.send("you have no subscriptions.")
            return

        before = len(self.data[user_id])
        self.data[user_id] = [sub for sub in self.data[user_id]
                              if not (sub["username"] == username.lower() and sub["channel_id"] == channel.id)]
        after = len(self.data[user_id])

        if before == after:
            await ctx.send(f"no subscription found for `{username}` in {channel.mention}")
        else:
            save_data(self.data)
            await ctx.send(f"unsubscribed from `{username}` in {channel.mention}")

    @instagram.command()
    async def view(self, ctx):
        """View all your Instagram subscriptions."""
        user_id = str(ctx.author.id)
        if user_id not in self.data or not self.data[user_id]:
            await ctx.send("you haven’t subscribed to anyone yet.")
            return

        msg = "**your instagram subscriptions:**\n"
        for sub in self.data[user_id]:
            channel = self.bot.get_channel(sub["channel_id"])
            if channel:
                msg += f"`{sub['username']}` → {channel.mention}\n"
            else:
                msg += f"`{sub['username']}` → *(channel not found)*\n"

        await ctx.send(msg)

def setup(bot):
    bot.add_cog(InstagramCog(bot))
