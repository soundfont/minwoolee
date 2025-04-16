import discord
from discord.ext import commands, tasks
import instaloader
import asyncio

INSTAGRAM_USERNAMES = {}
LAST_POST_TIMES = {}

class InstagramCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.loader = instaloader.Instaloader()
        self.check_instagram.start()

    def cog_unload(self):
        self.check_instagram.cancel()

    async def cog_load(self):
        await self.bot.wait_until_ready()

    @tasks.loop(minutes=15)
    async def check_instagram(self):
        if not INSTAGRAM_USERNAMES:
            return

        for username, channel_id in INSTAGRAM_USERNAMES.items():
            channel = self.bot.get_channel(channel_id)
            if not channel:
                continue

            try:
                profile = instaloader.Profile.from_username(self.loader.context, username)
                posts = profile.get_posts()
                new_post = next(posts, None)

                if new_post:
                    post_time = new_post.date_utc.timestamp()
                    last_time = LAST_POST_TIMES.get(username, 0)

                    if post_time > last_time:
                        LAST_POST_TIMES[username] = post_time
                        await channel.send(f"new post from **{username}**:\nhttps://www.instagram.com/p/{new_post.shortcode}/")

                # stories
                stories = self.loader.get_stories(userids=[profile.userid])
                for story in stories:
                    for item in story.get_items():
                        await channel.send(f"new story from **{username}**:\n{item.url}")

            except Exception:
                pass  # skip errors silently

    @commands.group(name="instagram", invoke_without_command=True)
    async def instagram(self, ctx):
        await ctx.send("use `.instagram add <username> <channel_id>` to track an IG user and channel.")

    @instagram.command(name="add")
    async def add(self, ctx, username: str, channel_id: int):
        if username not in INSTAGRAM_USERNAMES:
            INSTAGRAM_USERNAMES[username] = channel_id
            await ctx.send(f"tracking `{username}` and sending updates to <#{channel_id}>.")
        else:
            await ctx.send(f"`{username}` is already being tracked.")

    @instagram.command(name="remove")
    async def remove(self, ctx, username: str):
        if username in INSTAGRAM_USERNAMES:
            del INSTAGRAM_USERNAMES[username]
            await ctx.send(f"stopped tracking `{username}`.")
        else:
            await ctx.send(f"`{username}` is not being tracked.")

    @instagram.command(name="list")
    async def list(self, ctx):
        if INSTAGRAM_USERNAMES:
            await ctx.send("tracking users and their channels:\n" + "\n".join(f"- `{u}`: <#{ch}>" for u, ch in INSTAGRAM_USERNAMES.items()))
        else:
            await ctx.send("no users tracked yet.")
