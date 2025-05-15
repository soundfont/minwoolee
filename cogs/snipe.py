import discord
from discord.ext import commands, tasks
import datetime
import asyncio
from collections import deque # Efficient for storing recent items

# Define a simple structure to hold sniped message data
class SnipedMessage:
    def __init__(self, content, author, channel_id, guild_id, deleted_at, attachments=None, embeds=None):
        self.content = content
        self.author = author # Store author object or at least name and ID
        self.channel_id = channel_id
        self.guild_id = guild_id
        self.deleted_at = deleted_at # Store as datetime object (UTC)
        self.attachments = attachments if attachments else [] # List of attachment URLs or discord.Attachment objects
        self.embeds = embeds if embeds else [] # List of discord.Embed objects

class Snipe(commands.Cog):
    """
    A cog that allows users to snipe recently deleted messages.
    """
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # {channel_id: deque([SnipedMessage, ...])}
        # Using deque for efficient appends and pops from either end.
        # We'll store a limited number of messages per channel or manage by time.
        self.sniped_messages = {} 
        self.max_snipe_age_seconds = 2 * 60 * 60  # 2 hours in seconds
        self.max_messages_per_channel = 10 # Store up to 10 deleted messages per channel for sniping history

        self.cleanup_sniped_messages.start() # Start the cleanup task

    def cog_unload(self):
        self.cleanup_sniped_messages.cancel() # Cancel the task when cog is unloaded

    @tasks.loop(minutes=30) # Run cleanup periodically
    async def cleanup_sniped_messages(self):
        """Periodically cleans up sniped messages older than the max snipe age."""
        now_utc = datetime.datetime.now(datetime.timezone.utc)
        print(f"Running periodic snipe cleanup at {now_utc.isoformat()}...")
        channels_to_clean = list(self.sniped_messages.keys()) # Iterate over a copy of keys

        for channel_id in channels_to_clean:
            if channel_id not in self.sniped_messages: # Check if channel still exists in dict
                continue

            valid_messages = deque(maxlen=self.max_messages_per_channel)
            
            # Iterate safely while potentially modifying the original deque
            # by creating a new deque with valid messages
            temp_list = list(self.sniped_messages[channel_id]) # Convert to list for safe iteration
            for msg_data in temp_list:
                if (now_utc - msg_data.deleted_at).total_seconds() < self.max_snipe_age_seconds:
                    valid_messages.append(msg_data)
            
            if valid_messages:
                self.sniped_messages[channel_id] = valid_messages
            else:
                # If no valid messages left, remove the channel entry
                try:
                    del self.sniped_messages[channel_id]
                    print(f"Cleaned up all sniped messages for channel {channel_id}.")
                except KeyError:
                    pass # Already deleted by another operation

    @cleanup_sniped_messages.before_loop
    async def before_cleanup(self):
        await self.bot.wait_until_ready() # Wait for the bot to be ready before starting the task

    @commands.Cog.listener()
    async def on_message_delete(self, message: discord.Message):
        """
        Stores information about a deleted message.
        """
        if message.author.bot: # Ignore messages from bots
            return
        if not message.guild: # Ignore DMs for snipe
            return
        # Ignore if message content is empty and no attachments (e.g. system messages, failed embeds)
        if not message.content and not message.attachments and not message.embeds:
            return

        # Store basic author info in case the member object becomes unavailable
        author_info = {
            "name": str(message.author), # name#discriminator
            "id": message.author.id,
            "avatar_url": str(message.author.display_avatar.url) if message.author.display_avatar else None
        }
        
        # Store attachment URLs (if any)
        attachment_urls = [att.url for att in message.attachments if att.url]
        
        # Store embeds (discord.py stores them as a list of Embed objects)
        
        sniped_data = SnipedMessage(
            content=message.content,
            author=author_info, # Store the dict
            channel_id=message.channel.id,
            guild_id=message.guild.id,
            deleted_at=datetime.datetime.now(datetime.timezone.utc), # Store deletion time as UTC
            attachments=attachment_urls,
            embeds=message.embeds # Stores a list of discord.Embed objects
        )

        if message.channel.id not in self.sniped_messages:
            self.sniped_messages[message.channel.id] = deque(maxlen=self.max_messages_per_channel)
        
        self.sniped_messages[message.channel.id].append(sniped_data)
        # The deque will automatically handle maxlen if set. Time-based cleanup is separate.
        print(f"Stored deleted message from {message.author} in channel {message.channel.id}")

    @commands.command(name="snipe", aliases=['s']) # Added alias 's'
    @commands.cooldown(1, 5, commands.BucketType.user) # Cooldown to prevent spam
    async def snipe_command(self, ctx: commands.Context, index: int = 1):
        """
        Shows the last deleted message in this channel within the last 2 hours.
        Usage: .snipe [index] (e.g., .snipe or .snipe 2 for the 2nd to last)
        Alias: .s [index]
        """
        utils_cog = self.bot.get_cog('Utils') # Assumes you have a Utils cog for embeds
        if not utils_cog:
            await ctx.send("Error: Utils cog not loaded. Cannot create embed.")
            return

        if index <= 0:
            await ctx.send(embed=utils_cog.create_embed(ctx, title="Snipe Error", description="Index must be a positive number (1 for the latest).", color=discord.Color.red()))
            return

        channel_id = ctx.channel.id
        if channel_id not in self.sniped_messages or not self.sniped_messages[channel_id]:
            await ctx.send(embed=utils_cog.create_embed(ctx, title="Nothing to Snipe", description="No recently deleted messages found in this channel.", color=discord.Color.orange()))
            return

        # Get messages for the channel, already ordered by deletion time (most recent is last in deque)
        channel_snipes = self.sniped_messages[channel_id]
        
        # Filter by time (2 hours) and get the requested index from the end
        now_utc = datetime.datetime.now(datetime.timezone.utc)
        valid_snipes_for_channel = [
            msg for msg in reversed(channel_snipes) # Iterate from most recent
            if (now_utc - msg.deleted_at).total_seconds() < self.max_snipe_age_seconds
        ]

        if not valid_snipes_for_channel:
            await ctx.send(embed=utils_cog.create_embed(ctx, title="Nothing to Snipe", description="No messages deleted within the last 2 hours found in this channel.", color=discord.Color.orange()))
            return

        if index > len(valid_snipes_for_channel):
            await ctx.send(embed=utils_cog.create_embed(ctx, title="Snipe Error", 
                                                       description=f"Only {len(valid_snipes_for_channel)} snipeable message(s) found. Please choose an index between 1 and {len(valid_snipes_for_channel)}.", 
                                                       color=discord.Color.red()))
            return

        # Get the message by index (1-based for user, so index-1 for list)
        sniped_msg_data = valid_snipes_for_channel[index - 1]

        # Create the embed
        author_info = sniped_msg_data.author # This is the dict we stored
        author_name = author_info.get("name", "Unknown User")
        author_avatar_url = author_info.get("avatar_url")

        embed_title = f"Sniped Message from {author_name}"
        embed = utils_cog.create_embed(ctx, title=embed_title, color=discord.Color.blue())
        
        if author_avatar_url:
            embed.set_author(name=author_name, icon_url=author_avatar_url)
        else:
            embed.set_author(name=author_name)

        # Add message content
        if sniped_msg_data.content:
            embed.description = sniped_msg_data.content
        else:
            embed.description = "*No text content*"
            
        # Add timestamp of deletion (relative)
        time_deleted_ago = discord.utils.format_dt(sniped_msg_data.deleted_at, style='R')
        embed.add_field(name="Deleted", value=time_deleted_ago, inline=False)

        # Add attachments if any
        if sniped_msg_data.attachments:
            attachment_links = "\n".join([f"[Attachment {i+1}]({url})" for i, url in enumerate(sniped_msg_data.attachments)])
            embed.add_field(name="Attachments", value=attachment_links, inline=False)

        await ctx.send(embed=embed)

        # If the original message had embeds, send them as separate embeds
        if sniped_msg_data.embeds:
            valid_original_embeds = [e for e in sniped_msg_data.embeds if isinstance(e, discord.Embed)]
            if valid_original_embeds:
                if len(valid_original_embeds) > 0:
                    try:
                        await ctx.send(content="Original embed(s) from the sniped message:", embeds=valid_original_embeds[:10]) 
                    except discord.HTTPException as e:
                        print(f"Snipe: Failed to send original embeds: {e}")
                        await ctx.send("*Could not re-send original embed(s) due to an error.*")


    @snipe_command.error
    async def snipe_command_error(self, ctx, error):
        utils_cog = self.bot.get_cog('Utils')
        if isinstance(error, commands.CommandOnCooldown):
            if utils_cog:
                await ctx.send(embed=utils_cog.create_embed(ctx, title="Cooldown", description=f"This command is on cooldown. Try again in {error.retry_after:.2f}s.", color=discord.Color.orange()))
            else:
                await ctx.send(f"This command is on cooldown. Try again in {error.retry_after:.2f}s.")
        elif isinstance(error, commands.BadArgument):
            if utils_cog:
                await ctx.send(embed=utils_cog.create_embed(ctx, title="Snipe Error", description="Invalid index provided. Please use a number (e.g., `.snipe 1`).", color=discord.Color.red()))
            else:
                await ctx.send("Invalid index provided for snipe.")
        else:
            print(f"An error occurred with the snipe command: {error}")
            traceback.print_exc()
            if utils_cog:
                await ctx.send(embed=utils_cog.create_embed(ctx, title="Error", description="An unexpected error occurred with the snipe command.", color=discord.Color.red()))
            else:
                await ctx.send("An unexpected error occurred with the snipe command.")


async def setup(bot: commands.Bot):
    await bot.add_cog(Snipe(bot))
    print("Cog 'Snipe' loaded successfully.")

