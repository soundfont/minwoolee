import discord
from discord.ext import commands, tasks
import psycopg2
import os
import instaloader
import json
import asyncio

# PostgreSQL connection
DATABASE_URL = os.getenv('DATABASE_URL')
conn = psycopg2.connect(DATABASE_URL, sslmode='require')
cur = conn.cursor()

# Set up instaloader
DATA_FILE = "instagram_data.json"
CACHE_FILE = "instagram_cache.json"

def load_cache():
    if not os.path.exists(CACHE_FILE):
        with open(CACHE_FILE, "w") as f:
            json.dump({}, f)
    with open(CACHE_FILE, "r") as f:
        return json.load(f)

def save_cache(data):
    with open(CACHE_FILE, "w") as f:
        json.dump(data, f, indent=4)

class InstagramCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.cache = load_cache()
        self.loader = instaloader.Instaloader(download_stories=False, quiet=True)
        self.check_instagram.start()

    def cog_unload(self):
        self.check_instagram.cancel()

    @tasks.loop(minutes=15)
    async def check_instagram(self):
        print("[IG] checking for new content...")
        cur.execute("SELECT * FROM subscriptions")
        rows = cur.fetchall()
        for row in rows:
            user_id, username, channel_id = row
            channel = self.bot.get_channel(channel_id)
            if not channel:
                continue

            try:
                profile = instaloader.Profile.from_username(self.loader.context, username)

                # handle POSTS
                post_id = str(profile.mediacount)
                cached = self.cache.get(username, {})
                if cached.get("last_post") != post_id:
                    post = next(profile.get_posts())
                    await channel.send(f"📸 new post from `{username}`:\n{post.url}")
                    self.cache.setdefault(username, {})["last_post"] = post_id
                    save_cache(self.cache)

                # handle STORIES
                stories = list(self.loader.get_stories(userids=[profile.userid]))
                for story in stories:
                    for item in story.get_items():
                        story_id = str(item.mediaid)
                        if story_id not in cached.get("stories", []):
                            await channel.send(f"🕒 new story from `{username}`:\n{item.url}")
                            self.cache.setdefault(username, {}).setdefault("stories", []).append(story_id)
                            save_cache(self.cache)

            except Exception as e:
                print(f"[IG ERROR] {username}: {e}")

    @check_instagram.before_loop
    async def before_check(self):
        await self.bot.wait_until_ready()

    @commands.group()
    async def instagram(self, ctx):
        if ctx.invoked_subcommand is None:
            await ctx.send("invalid subcommand. try `.instagram add (user) #channel`, `.remove`, or `.view`")

    @instagram.command()
    async def add(self, ctx, username: str, channel: discord.TextChannel):
        """Subscribe to an Instagram user and set a drop channel."""
        user_id = str(ctx.author.id)

        # Insert subscription into the database
        try:
            cur.execute("INSERT INTO subscriptions (user_id, username, channel_id) VALUES (%s, %s, %s) ON CONFLICT DO NOTHING", 
                        (user_id, username.lower(), channel.id))
            conn.commit()
            await ctx.send(f"✅ successfully subscribed to `{username}` — drops in {channel.mention}")
        except Exception as e:
            await ctx.send(f"❌ error subscribing to `{username}`: {e}")

    @instagram.command()
    async def remove(self, ctx, username: str, channel: discord.TextChannel):
        """Unsubscribe from an Instagram user in a channel."""
        user_id = str(ctx.author.id)

        # Remove subscription from the database
        try:
            cur.execute("DELETE FROM subscriptions WHERE user_id = %s AND username = %s AND channel_id = %s", 
                        (user_id, username.lower(), channel.id))
            conn.commit()
            await ctx.send(f"✅ successfully unsubscribed from `{username}` in {channel.mention}")
        except Exception as e:
            await ctx.send(f"❌ error unsubscribing from `{username}`: {e}")

    @instagram.command()
    async def view(self, ctx):
        """View all your Instagram subscriptions."""
        user_id = str(ctx.author.id)
        try:
            cur.execute("SELECT * FROM subscriptions WHERE user_id = %s", (user_id,))
            rows = cur.fetchall()

            if not rows:
                await ctx.send("❌ you haven’t subscribed to anyone yet.")
                return

            msg = "**your instagram subscriptions:**\n"
            for row in rows:
                username, channel_id = row[1], row[2]
                channel = self.bot.get_channel(channel_id)
                mention = channel.mention if channel else "*channel gone*"
                msg += f"`{username}` → {mention}\n"

            await ctx.send(msg)
        except Exception as e:
            await ctx.send(f"❌ error fetching your subscriptions: {e}")

def setup(bot):
    bot.add_cog(InstagramCog(bot))
