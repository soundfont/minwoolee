from discord.ext import commands
import discord
import time

class AFK(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.afk_users = {}  # {guild_id: {user_id: (reason, timestamp)}}

    @commands.command()
    async def afk(self, ctx, *, reason="AFK"):
        try:
            user = ctx.author
            guild_id = ctx.guild.id

            # Initialize guild dictionary if not exists
            if guild_id not in self.afk_users:
                self.afk_users[guild_id] = {}

            # Check if turning off AFK
            if reason.lower() == "off":
                if guild_id in self.afk_users and user.id in self.afk_users[guild_id]:
                    reason, start_time = self.afk_users[guild_id].pop(user.id)
                    duration = int(time.time() - start_time)

                    # Clean up empty guild dictionary
                    if not self.afk_users[guild_id]:
                        del self.afk_users[guild_id]

                    # Create embed using utils
                    utils = self.bot.get_cog('Utils')
                    if not utils:
                        await ctx.send("Error: Utils cog not loaded.")
                        return

                    embed = utils.create_embed(ctx, title="Welcome Back")
                    embed.description = f"{user.mention}, you were away for {duration} seconds"

                    await ctx.send(embed=embed)
                else:
                    await ctx.send("You are not currently AFK in this server.")
                return

            # Set AFK status for this guild
            self.afk_users[guild_id][user.id] = (reason, time.time())

            # Create embed using utils
            utils = self.bot.get_cog('Utils')
            if not utils:
                await ctx.send("Error: Utils cog not loaded.")
                return

            embed = utils.create_embed(ctx, title="AFK")
            embed.description = f"{user.mention} | Set your AFK status to: {reason}"

            # Send embed
            await ctx.send(embed=embed)
        except discord.Forbidden:
            await ctx.send("I don't have permission to send embeds in this channel.")
        except discord.HTTPException as e:
            await ctx.send(f"Failed to set AFK: {str(e)}")
        except Exception as e:
            await ctx.send(f"An error occurred while setting AFK: {str(e)}")

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot:
            return

        # Ignore DMs (no guild context)
        if not message.guild:
            return

        guild_id = message.guild.id
        user = message.author

        # Check if the user is AFK in this guild and sent a message (remove AFK)
        if guild_id in self.afk_users and user.id in self.afk_users[guild_id]:
            # Ignore if the message is the afk command itself
            if message.content.startswith('.afk'):
                pass
            else:
                reason, start_time = self.afk_users[guild_id].pop(user.id)
                duration = int(time.time() - start_time)

                # Clean up empty guild dictionary
                if not self.afk_users[guild_id]:
                    del self.afk_users[guild_id]

                # Create embed using utils
                utils = self.bot.get_cog('Utils')
                if not utils:
                    await message.channel.send("Error: Utils cog not loaded.")
                    return

                embed = utils.create_embed(message, title="Welcome Back")
                embed.description = f"{user.mention}, you were away for {duration} seconds"

                # Send welcome back embed
                try:
                    await message.channel.send(embed=embed)
                except discord.Forbidden:
                    await message.channel.send("I don't have permission to send embeds in this channel.")
                except discord.HTTPException as e:
                    await message.channel.send(f"Failed to send welcome back message: {str(e)}")

        # Check if any mentioned users are AFK in this guild
        for mentioned_user in message.mentions:
            if guild_id in self.afk_users and mentioned_user.id in self.afk_users[guild_id]:
                reason, start_time = self.afk_users[guild_id][mentioned_user.id]
                duration = int(time.time() - start_time)

                # Create embed using utils
                utils = self.bot.get_cog('Utils')
                if not utils:
                    await message.channel.send("Error: Utils cog not loaded.")
                    return

                embed = utils.create_embed(message, title="User is AFK")
                embed.description = f"{mentioned_user.display_name} is AFK: {reason} - in {duration} seconds"

                # Send AFK notification embed
                try:
                    await message.channel.send(embed=embed)
                except discord.Forbidden:
                    await message.channel.send("I don't have permission to send embeds in this channel.")
                except discord.HTTPException as e:
                    await message.channel.send(f"Failed to send AFK notification: {str(e)}")

async def setup(bot):
    await bot.add_cog(AFK(bot))
