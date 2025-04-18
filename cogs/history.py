from discord.ext import commands
import discord
import time
import math

class History(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.mod_logs = {}  # {guild_id: {member_id: [{"action": str, "moderator": user, "timestamp": float, "reason": str}, ...]}}
        print("DEBUG: History cog initialized, mod_logs cleared.")

    def log_action(self, guild_id, member_id, action, moderator, reason=None):
        member_id = int(member_id)
        print(f"DEBUG: Logging action - Guild: {guild_id}, Member: {member_id}, Action: {action}")
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
        print(f"DEBUG: Current mod_logs for guild {guild_id}, member {member_id}: {self.mod_logs[guild_id][member_id]}")

    @commands.command()
    @commands.has_permissions(moderate_members=True)
    async def history(self, ctx, member: discord.Member):
        try:
            guild_id = ctx.guild.id
            member_id = member.id

            if guild_id not in self.mod_logs or member_id not in self.mod_logs[guild_id] or not self.mod_logs[guild_id][member_id]:
                await ctx.send(f"No moderation history found for {member.mention}.")
                return

            actions = self.mod_logs[guild_id][member_id]
            print(f"DEBUG: Actions for member {member_id} in guild {guild_id}: {actions}")

            # Filter valid actions
            valid_actions = [
                action for action in actions
                if isinstance(action, dict) and all(key in action for key in ["action", "moderator", "timestamp"])
            ]
            invalid_actions = [action for action in actions if action not in valid_actions]
            if invalid_actions:
                print(f"DEBUG: Invalid actions found: {invalid_actions}")
                self.mod_logs[guild_id][member_id] = valid_actions
                await ctx.send("Removed invalid history entries.")
                if not valid_actions:
                    await ctx.send(f"No valid moderation history found for {member.mention}.")
                    return

            # Pagination setup
            actions_per_page = 5
            total_pages = math.ceil(len(valid_actions) / actions_per_page)
            current_page = 1

            utils = self.bot.get_cog('Utils')
            if not utils:
                await ctx.send("Error: Utils cog not loaded.")
                return

            def get_page(page_num):
                start_idx = (page_num - 1) * actions_per_page
                end_idx = start_idx + actions_per_page
                page_actions = valid_actions[start_idx:end_idx]
                print(f"DEBUG: Page actions for page {page_num}: {page_actions}")
                description = ""
                for action in page_actions:
                    print(f"DEBUG: Processing action: {action}")
                    try:
                        timestamp = discord.utils.format_dt(int(action["timestamp"]), style="R")
                    except (TypeError, ValueError) as e:
                        timestamp = "Invalid timestamp"
                        print(f"DEBUG: Invalid timestamp in action: {action}, error: {str(e)}")
                    reason = action["reason"] if action["reason"] else "No reason provided"
                    description += f"**Action:** {action['action']} | **Moderator:** {action['moderator'].mention} | **Time:** {timestamp}\n**Reason:** {reason}\n\n"
                embed = utils.create_embed(ctx, title=f"Moderation History for {member}")
                embed.description = description.strip() or "No actions to display."
                embed.set_footer(text=f"Page {page_num}/{total_pages} | Requested by {ctx.author}")
                print(f"DEBUG: Embed description length: {len(embed.description)}")
                return embed

            # Send initial embed
            embed = get_page(current_page)
            message = await ctx.send(embed=embed)

            if total_pages == 1:
                return

            # Add pagination reactions
            left_arrow = "⬅️"
            right_arrow = "➡️"
            await message.add_reaction(left_arrow)
            await message.add_reaction(right_arrow)

            def check(reaction, user):
                return user == ctx.author and reaction.message.id == message.id and str(reaction.emoji) in [left_arrow, right_arrow]

            while True:
                try:
                    reaction, user = await self.bot.wait_for('reaction_add', timeout=60.0, check=check)
                    if str(reaction.emoji) == left_arrow and current_page > 1:
                        current_page -= 1
                    elif str(reaction.emoji) == right_arrow and current_page < total_pages:
                        current_page += 1
                    embed = get_page(current_page)
                    await message.edit(embed=embed)
                    await message.remove_reaction(reaction.emoji, user)
                except asyncio.TimeoutError:
                    await message.clear_reactions()
                    break

        except discord.Forbidden:
            await ctx.send("I don't have permission to manage reactions.")
        except discord.HTTPException as e:
            await ctx.send(f"Failed to fetch history: {str(e)}")
        except Exception as e:
            await ctx.send(f"Unexpected error during history command: {str(e)}")
            raise e

    @commands.command()
    @commands.has_permissions(administrator=True)
    async def clearhistory(self, ctx):
        try:
            self.mod_logs.clear()
            await ctx.send("All moderation history has been cleared.")
            print("DEBUG: All mod_logs cleared via clearhistory command.")
        except Exception as e:
            await ctx.send(f"Failed to clear history: {str(e)}")
            print(f"DEBUG: Error clearing mod_logs: {str(e)}")

    @history.error
    async def history_error(self, ctx, error):
        if isinstance(error, commands.MissingPermissions):
            await ctx.send("You need 'Moderate Members' permission to use this command.")
        elif isinstance(error, commands.MemberNotFound):
            await ctx.send("Member not found. Please provide a valid member.")
        elif isinstance(error, commands.CommandInvokeError):
            await ctx.send("An error occurred while executing the history command. Check bot logs for details.")

async def setup(bot):
    await bot.add_cog(History(bot))
