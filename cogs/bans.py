from discord.ext import commands
import discord
import math

class Bans(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command()
    @commands.has_permissions(ban_members=True)
    async def bans(self, ctx):
        try:
            # Fetch banned users
            banned_users = []
            async for ban_entry in ctx.guild.bans():
                banned_users.append(ban_entry.user)

            if not banned_users:
                await ctx.send("No users are currently banned from this server.")
                return

            # Pagination setup
            users_per_page = 10
            total_pages = math.ceil(len(banned_users) / users_per_page)
            current_page = 1

            # Create embed using utils
            utils = self.bot.get_cog('Utils')
            if not utils:
                await ctx.send("Error: Utils cog not loaded.")
                return

            def get_page(page_num):
                start_idx = (page_num - 1) * users_per_page
                end_idx = start_idx + users_per_page
                page_users = banned_users[start_idx:end_idx]
                description = "\n".join([f"{user.mention} (ID: {user.id})" for user in page_users])
                embed = utils.create_embed(ctx, title="Banned Users")
                embed.description = description
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
            await ctx.send("I don't have permission to view banned users or manage reactions (requires 'Ban Members', 'Add Reactions', 'Manage Messages').")
        except discord.HTTPException as e:
            await ctx.send(f"Failed to fetch banned users: {str(e)}")

    @bans.error
    async def bans_error(self, ctx, error):
        if isinstance(error, commands.MissingPermissions):
            await ctx.send("You need 'Ban Members' permission to use this command.")
        elif isinstance(error, commands.CommandInvokeError):
            await ctx.send("An error occurred while executing the bans command.")

async def setup(bot):
    await bot.add_cog(Bans(bot))
