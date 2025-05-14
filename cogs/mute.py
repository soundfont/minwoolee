import discord
from discord.ext import commands
import traceback

class Mute(commands.Cog):
    """
    A cog to prevent specified users from sending images and adding reactions.
    Text mutes are handled by the timeout system.
    """
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # {guild_id: {user_id1, user_id2, ...}}
        self.media_reaction_muted_users = {} 
        # For persistence, consider loading from/saving to a file or database.

    def _is_user_muted(self, guild_id: int, user_id: int) -> bool:
        """Checks if a user is media/reaction muted in a specific guild."""
        return guild_id in self.media_reaction_muted_users and \
               user_id in self.media_reaction_muted_users[guild_id]

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """
        Listens for messages and deletes them if they are from a muted user
        and contain image attachments or image embeds.
        """
        if message.author.bot or not message.guild:
            return # Ignore bots and DMs

        if not self._is_user_muted(message.guild.id, message.author.id):
            return

        contains_image = False
        # 1. Check attachments
        if message.attachments:
            for attachment in message.attachments:
                if attachment.content_type and attachment.content_type.startswith('image/'):
                    contains_image = True
                    break
                if attachment.filename.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.webp', '.bmp')):
                    contains_image = True
                    break
        
        # 2. Check embeds (Discord often auto-embeds image links)
        if not contains_image and message.embeds:
            for embed in message.embeds:
                if embed.type == 'image' or (embed.image and embed.image.url):
                    contains_image = True
                    break

        if contains_image:
            try:
                await message.delete()
                print(f"Deleted message from media-muted user {message.author} (ID: {message.author.id}) in guild {message.guild.id} due to image content.")
                
                history_cog = self.bot.get_cog('History')
                if history_cog:
                    history_cog.log_action(
                        message.guild.id, 
                        message.author.id, 
                        "Image Deleted (Media Mute)", 
                        self.bot.user, 
                        "User is media/reaction muted and sent an image."
                    )
            except discord.Forbidden:
                print(f"Error: Could not delete message from {message.author} in {message.guild.name}. Missing 'Manage Messages' permission.")
            except discord.HTTPException as e:
                print(f"Error: Failed to delete message from {message.author}. HTTPException: {e}")
            except Exception as e:
                print(f"An unexpected error occurred while deleting a media-muted user's message: {e}")
                traceback.print_exc()

    @commands.Cog.listener()
    async def on_reaction_add(self, reaction: discord.Reaction, user: discord.User | discord.Member):
        """
        Listens for reactions and removes them if they are from a muted user.
        """
        if user.bot or not reaction.message.guild:
            return # Ignore bots and DMs

        if self._is_user_muted(reaction.message.guild.id, user.id):
            try:
                await reaction.remove(user)
                print(f"Removed reaction from media-muted user {user} (ID: {user.id}) in guild {reaction.message.guild.id}.")

                history_cog = self.bot.get_cog('History')
                if history_cog:
                    history_cog.log_action(
                        reaction.message.guild.id,
                        user.id,
                        f"Reaction Removed ('{reaction.emoji}') (Media Mute)",
                        self.bot.user, # Action performed by the bot
                        "User is media/reaction muted and added a reaction."
                    )
            except discord.Forbidden:
                print(f"Error: Could not remove reaction from {user} in {reaction.message.guild.name}. Missing 'Manage Messages' or 'Manage Emojis' permission.")
            except discord.HTTPException as e:
                print(f"Error: Failed to remove reaction from {user}. HTTPException: {e}")
            except Exception as e:
                print(f"An unexpected error occurred while removing a media-muted user's reaction: {e}")
                traceback.print_exc()

    @commands.command(name="mute")
    @commands.has_permissions(moderate_members=True)
    async def media_mute_command(self, ctx: commands.Context, member: discord.Member, *, reason: str = "Not specified"):
        """
        Prevents a member from sending images and adding reactions.
        Usage: .mute <@member/ID> [reason]
        """
        utils_cog = self.bot.get_cog('Utils')
        if not utils_cog:
            await ctx.send("Error: Utils cog not loaded. Cannot create embed.")
            return

        if member.id == ctx.author.id and ctx.guild.owner_id != ctx.author.id:
            await ctx.send(embed=utils_cog.create_embed(ctx, title="Error", description="You cannot mute yourself.", color=discord.Color.red()))
            return
        
        if member.bot:
            await ctx.send(embed=utils_cog.create_embed(ctx, title="Error", description="You cannot mute a bot.", color=discord.Color.red()))
            return

        if member.top_role >= ctx.author.top_role and ctx.guild.owner_id != ctx.author.id :
            await ctx.send(embed=utils_cog.create_embed(ctx, title="Permission Denied", description="You cannot mute a member with a role higher than or equal to yours.", color=discord.Color.red()))
            return
        
        if member.top_role >= ctx.guild.me.top_role and ctx.guild.owner_id != ctx.author.id:
            await ctx.send(embed=utils_cog.create_embed(ctx, title="Error", description=f"I cannot mute {member.mention} because their role is higher than or equal to mine.", color=discord.Color.red()))
            return

        guild_id = ctx.guild.id
        if guild_id not in self.media_reaction_muted_users:
            self.media_reaction_muted_users[guild_id] = set()

        if member.id in self.media_reaction_muted_users[guild_id]:
            embed = utils_cog.create_embed(ctx, title="Already Muted", description=f"{member.mention} is already muted (images/reactions).", color=discord.Color.orange())
            await ctx.send(embed=embed)
            return

        self.media_reaction_muted_users[guild_id].add(member.id)
        
        embed = utils_cog.create_embed(ctx, title="Media/Reaction Mute Applied", 
                                       description=f"{member.mention} has been muted from sending images and adding reactions.", 
                                       color=discord.Color.green())
        embed.add_field(name="Reason", value=reason, inline=False)
        await ctx.send(embed=embed)

        history_cog = self.bot.get_cog('History')
        if history_cog:
            history_cog.log_action(guild_id, member.id, "Media/Reaction Muted", ctx.author, reason)

    @commands.command(name="unmute")
    @commands.has_permissions(moderate_members=True)
    async def un_media_mute_command(self, ctx: commands.Context, member: discord.Member, *, reason: str = "Not specified"):
        """
        Allows a member to send images and add reactions again.
        Usage: .unmute <@member/ID> [reason]
        """
        utils_cog = self.bot.get_cog('Utils')
        if not utils_cog:
            await ctx.send("Error: Utils cog not loaded. Cannot create embed.")
            return

        guild_id = ctx.guild.id
        if not self._is_user_muted(guild_id, member.id):
            embed = utils_cog.create_embed(ctx, title="Not Muted", description=f"{member.mention} is not currently media/reaction muted.", color=discord.Color.orange())
            await ctx.send(embed=embed)
            return

        self.media_reaction_muted_users[guild_id].remove(member.id)
        if not self.media_reaction_muted_users[guild_id]:
            del self.media_reaction_muted_users[guild_id]

        embed = utils_cog.create_embed(ctx, title="Media/Reaction Mute Removed", 
                                       description=f"{member.mention} is no longer media/reaction muted.", 
                                       color=discord.Color.green())
        embed.add_field(name="Reason", value=reason, inline=False)
        await ctx.send(embed=embed)

        history_cog = self.bot.get_cog('History')
        if history_cog:
            history_cog.log_action(guild_id, member.id, "Media/Reaction Unmuted", ctx.author, reason)
            
    @commands.command(name="mutedlist")
    @commands.has_permissions(manage_messages=True)
    async def media_muted_list_command(self, ctx: commands.Context):
        """Displays a list of members currently media/reaction muted in this server."""
        utils_cog = self.bot.get_cog('Utils')
        if not utils_cog:
            await ctx.send("Error: Utils cog not loaded. Cannot create embed.")
            return

        guild_id = ctx.guild.id
        if guild_id not in self.media_reaction_muted_users or not self.media_reaction_muted_users[guild_id]:
            embed = utils_cog.create_embed(ctx, title="Muted List (Images/Reactions)", description="No members are currently media/reaction muted in this server.")
            await ctx.send(embed=embed)
            return

        muted_user_ids = self.media_reaction_muted_users[guild_id]
        description_lines = []
        for user_id in muted_user_ids:
            user = ctx.guild.get_member(user_id) # Attempt to get member object
            if user:
                description_lines.append(f"- {user.mention} (ID: {user.id})")
            else: # Fallback if user left or not in cache
                description_lines.append(f"- User ID: {user_id} (User not found in server cache)")
        
        embed = utils_cog.create_embed(ctx, title="Media/Reaction Muted Members", description="\n".join(description_lines))
        await ctx.send(embed=embed)

    @media_mute_command.error
    async def mute_command_error(self, ctx, error):
        utils_cog = self.bot.get_cog('Utils')
        error_embed = None
        if utils_cog: error_embed = utils_cog.create_embed(ctx, title="Mute Error", color=discord.Color.red())
        
        if isinstance(error, commands.MissingPermissions):
            desc = "You need 'Moderate Members' permission to use this command."
        elif isinstance(error, commands.MemberNotFound):
            desc = f"Member not found: `{error.argument}`. Please provide a valid member."
        elif isinstance(error, commands.MissingRequiredArgument):
            desc = f"Missing argument: `{error.param.name}`.\nUsage: `.mute <@member/ID> [reason]`"
        elif isinstance(error, commands.CommandInvokeError):
            print(f"CommandInvokeError in mute: {error.original}")
            traceback.print_exc()
            desc = "An internal error occurred. Please check the bot logs."
        else:
            desc = f"An unexpected error occurred: {error}"
        
        if error_embed:
            error_embed.description = desc
            await ctx.send(embed=error_embed)
        else:
            await ctx.send(f"Mute Error: {desc} (Utils cog missing).")

    @un_media_mute_command.error
    async def unmute_command_error(self, ctx, error):
        utils_cog = self.bot.get_cog('Utils')
        error_embed = None
        if utils_cog: error_embed = utils_cog.create_embed(ctx, title="Unmute Error", color=discord.Color.red())

        if isinstance(error, commands.MissingPermissions):
            desc = "You need 'Moderate Members' permission to use this command."
        elif isinstance(error, commands.MemberNotFound):
            desc = f"Member not found: `{error.argument}`. Please provide a valid member."
        elif isinstance(error, commands.MissingRequiredArgument):
            desc = f"Missing argument: `{error.param.name}`.\nUsage: `.unmute <@member/ID> [reason]`"
        elif isinstance(error, commands.CommandInvokeError):
            print(f"CommandInvokeError in unmute: {error.original}")
            traceback.print_exc()
            desc = "An internal error occurred. Please check the bot logs."
        else:
            desc = f"An unexpected error occurred: {error}"

        if error_embed:
            error_embed.description = desc
            await ctx.send(embed=error_embed)
        else:
            await ctx.send(f"Unmute Error: {desc} (Utils cog missing).")

async def setup(bot: commands.Bot):
    await bot.add_cog(Mute(bot))
    print("Cog 'Mute (Media/Reactions)' loaded successfully.")

