from discord.ext import commands
import discord
import time
import math

class History(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.mod_logs = {}  # {guild_id: {member_id: [{"action": str, "moderator": user, "timestamp": float, "reason": str}, ...]}}

    def log_action(self, guild_id, member_id, action, moderator, reason=None):
        if guild_id not in self.mod_logs:
            self.mod_logs[guild_id] = {}
        if member_id not in self.mod_logs[guild_id]:
            self.mod_logs[guild_id][member_id] = []
        
        action_entry = {
            "action": action,
            "moderator": moderator,
            "timestamp": time.time(),
            "reason": reason
        }
        self.mod_logs[guild_id][member_id].append(action_entry)

    @commands.command()
    @commands.has_permissions(moderate_members=True)
    async def history(self, ctx, member: discord.Member):
        try:
            guild_id = ctx.guild.id
            member_id = member.id

            # Check if the member has any moderation history
            if guild_id not in self.mod_logs or member_id not in self.mod_logs[guild_id] or not self.mod_logs[guild_id][member_id]:
                await ctx.send(f"No moderation history found for {member.mention}.")
                return

            actions = self.mod_logs[guild_id][member_id]

            # Pagination setup
            actions_per_page = 5
            total_pages = math.ceil(len(actions) / actions_per_page)
            current_page = 1

            # Create embed using utils
            utils = self.bot.get_cog('Utils')
            if not utils:
                await ctx.send("Error: Utils cog not loaded.")
                return

            def get_page(page_num):
                start_idx = (page_num - 1) * actions_per_page
                end_idx = start_idx + actions_per_page
                page_actions = actions[start_idx:end_idx]
                description = ""
                for action in page_actions:
                    timestamp = discord.utils.format_dt(int(action["timestamp"]), style="R")
                    reason = action["reason"] if action["reason"] else "No reason provided"
                    description += f"**Action:** {action['action']} | **Moderator:** {action['moderator'].mention} | **Time:** {timestamp}\n**Reason:** {reason}\n\n"
                embed = utils.create_embed(ctx, title=f"Moderation History for {member}")
                embed.description = description.strip()
                embed.set_footer(text=f"Page {page_num}/{total_pages} | Requested by {ctx.author}")
                return embed

            # Send initial embed
            embed = get_page(current_page)
            message = await ctx.send(embed=embed)

            # If only one page, no need for pagination
            if total_pages == 1:
                return

            # Add pagination reactions
            left_arrow = "⬅️"
            right_arrow = "➡️"
            await message.add_reaction(left_arrow)
            await message.add_reaction(right_arrow)

            def check(reaction, user):
                return user == ctx.author and reaction.message.id == message.id and str(reaction.emoji) in [left_arrow, right_arrow]

            # Pagination loop
            while True:
                try:
                    reaction, user = await self.bot.wait_for('reaction_add', timeout=60.0, check=check)

                    # Update page based on reaction
                    if str(reaction.emoji) == left_arrow and current_page > 1:
                        current_page -= 1
                    elif str(reaction.emoji) == right_arrow and current_page < total_pages:
                        current_page += 1

                    # Update embed
                    embed = get_page(current_page)
                    await message.edit(embed=embed)

                    # Remove the user's reaction to allow further navigation
                    await message.remove_reaction(reaction.emoji, user)

                except asyncio.TimeoutError:
                    # Timeout after 60 seconds, remove reactions
                    await message.clear_reactions()
                    break

        except discord.Forbidden:
            await ctx.send("I don't have permission to manage reactions (requires 'Add Reactions', 'Manage Messages').")
        except discord.HTTPException as e:
            await ctx.send(f"Failed to fetch history: {str(e)}")

    @history.error
    async def history_error(self, ctx, error):
        if isinstance(error, commands.MissingPermissions):
            await ctx.send("You need 'Moderate Members' permission to use this command.")
        elif isinstance(error, commands.MemberNotFound):
            await ctx.send("Member not found. Please provide a valid member (mention or ID).")
        elif isinstance(error, commands.CommandInvokeError):
            await ctx.send("An error occurred while executing the history command.")

async def setup(bot):
    await bot.add_cog(History(bot))
