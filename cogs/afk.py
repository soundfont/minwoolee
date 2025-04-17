from discord.ext import commands
import discord
import time

class AFK(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.afk_users = {}  # {user_id: (reason, timestamp)}

    @commands.command()
    async def afk(self, ctx, *, reason="AFK"):
        try:
            user = ctx.author

            # Check if turning off AFK
            if reason.lower() == "off":
                if user.id in self.afk_users:
                    reason, start_time = self.afk_users.pop(user.id)
                    duration = int(time.time() - start_time)

                    # Create embed using utils
                    utils = self.bot.get_cog('Utils')
                    if not utils:
                        await ctx.send("Error: Utils cog not loaded.")
                        return

                    embed = utils.create_embed(ctx, title="AFK")
                    embed.description = f"Welcome back {user.mention}, you were away for {duration} seconds"

                    await ctx.send(embed=embed)
                else:
                    await ctx.send("You are not currently AFK.")
                return

            # Set AFK status
            self.afk_users[user.id] = (reason, time.time())

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

        user = message.author
        # Check if the user is AFK and sent a message (remove AFK)
        if user.id in self.afk_users:
            # Ignore if the message is the afk command itself
            if message.content.startswith('.afk'):
                return

            reason, start_time = self.afk_users.pop(user.id)
            duration = int(time.time() - start_time)

            # Create embed using utils
            utils = self.bot.get_cog('Utils')
            if not utils:
                await message.channel.send("Error: Utils cog not loaded.")
                return

            embed = utils.create_embed(message)
            embed.description = f"Welcome back {user.mention}, you were away for {duration} seconds"

            # Send welcome back embed
            try:
                await message.channel.send(embed=embed)
            except discord.Forbidden:
                await message.channel.send("I don't have permission to send embeds in this channel.")
            except discord.HTTPException as e:
                await message.channel.send(f"Failed to send welcome back message: {str(e)}")
            return

        # Check if any mentioned users are AFK
        for mentioned_user in message.mentions:
            if mentioned_user.id in self.afk_users:
                reason, start_time = self.afk_users[mentioned_user.id]
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
