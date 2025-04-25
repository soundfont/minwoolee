from discord.ext import commands
import discord
import time

class AFK(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.afk_users = {}  # {guild_id: {user_id: (reason, timestamp)}}

    def format_duration(self, seconds: int) -> str:
        days, remainder = divmod(seconds, 86400)
        hours, remainder = divmod(remainder, 3600)
        minutes, seconds = divmod(remainder, 60)

        parts = []
        if days: parts.append(f"{days}d")
        if hours: parts.append(f"{hours}h")
        if minutes: parts.append(f"{minutes}m")
        if seconds or not parts: parts.append(f"{seconds}s")

        return ' '.join(parts)

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
                if user.id in self.afk_users[guild_id]:
                    reason, start_time = self.afk_users[guild_id].pop(user.id)
                    duration = int(time.time() - start_time)

                    if not self.afk_users[guild_id]:
                        del self.afk_users[guild_id]

                    utils = self.bot.get_cog('Utils')
                    if not utils:
                        await ctx.send("Error: Utils cog not loaded.")
                        return

                    embed = utils.create_embed(ctx, title="Welcome Back")
                    embed.description = f"{user.mention}, you were away for {self.format_duration(duration)}"

                    await ctx.send(embed=embed, delete_after=5)
                else:
                    await ctx.send("You are not currently AFK in this server.", delete_after=5)
                return

            self.afk_users[guild_id][user.id] = (reason, time.time())

            utils = self.bot.get_cog('Utils')
            if not utils:
                await ctx.send("Error: Utils cog not loaded.")
                return

            embed = utils.create_embed(ctx, title="AFK")
            embed.description = f"{user.mention} | Set your AFK status to: {reason}"

            await ctx.send(embed=embed, delete_after=5)
        except discord.Forbidden:
            await ctx.send("I don't have permission to send embeds in this channel.", delete_after=5)
        except discord.HTTPException as e:
            await ctx.send(f"Failed to set AFK: {str(e)}", delete_after=5)
        except Exception as e:
            await ctx.send(f"An error occurred while setting AFK: {str(e)}", delete_after=5)

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot:
            return

        if not message.guild:
            return

        guild_id = message.guild.id
        user = message.author

        if guild_id in self.afk_users and user.id in self.afk_users[guild_id]:
            if not message.content.startswith('.afk'):
                reason, start_time = self.afk_users[guild_id].pop(user.id)
                duration = int(time.time() - start_time)

                if not self.afk_users[guild_id]:
                    del self.afk_users[guild_id]

                utils = self.bot.get_cog('Utils')
                if not utils:
                    await message.channel.send("Error: Utils cog not loaded.", delete_after=5)
                    return

                embed = utils.create_embed(message, title="Welcome Back")
                embed.description = f"{user.mention}, you were away for {self.format_duration(duration)}"

                try:
                    await message.channel.send(embed=embed, delete_after=5)
                except discord.Forbidden:
                    await message.channel.send("I don't have permission to send embeds in this channel.", delete_after=5)
                except discord.HTTPException as e:
                    await message.channel.send(f"Failed to send welcome back message: {str(e)}", delete_after=5)

        for mentioned_user in message.mentions:
            if guild_id in self.afk_users and mentioned_user.id in self.afk_users[guild_id]:
                reason, start_time = self.afk_users[guild_id][mentioned_user.id]
                duration = int(time.time() - start_time)

                utils = self.bot.get_cog('Utils')
                if not utils:
                    await message.channel.send("Error: Utils cog not loaded.", delete_after=5)
                    return

                embed = utils.create_embed(message, title="User is AFK")
                embed.description = f"{mentioned_user.display_name} is AFK: {reason} - for {self.format_duration(duration)}"

                try:
                    await message.channel.send(embed=embed, delete_after=5)
                except discord.Forbidden:
                    await message.channel.send("I don't have permission to send embeds in this channel.", delete_after=5)
                except discord.HTTPException as e:
                    await message.channel.send(f"Failed to send AFK notification: {str(e)}", delete_after=5)

async def setup(bot):
    await bot.add_cog(AFK(bot))
