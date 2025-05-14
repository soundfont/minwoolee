import discord
from discord.ext import commands
from datetime import timedelta
import re # For parsing the duration string

class Timeout(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    def _parse_duration_str(self, duration_str: str) -> tuple[timedelta | None, str | None]:
        """
        Parses a duration string (e.g., "1w2d3h4m5s", "1d 12h") into a timedelta object
        and a human-readable string.
        Returns (None, None) if parsing fails.
        """
        duration_str = duration_str.lower()
        # Regex to find number-unit pairs like "1w", "2d", "3h", "4m", "5s"
        # Allows optional spaces between number and unit.
        pattern = re.compile(r"(\d+)\s*([wdhms])")
        matches = pattern.findall(duration_str)

        if not matches and not (duration_str.isdigit() and 's' not in duration_str and 'm' not in duration_str and 'h' not in duration_str and 'd' not in duration_str and 'w' not in duration_str): # if it's just a number, assume minutes for backward compatibility or specific intent
             # If no standard units found, try to interpret as raw minutes for simple cases like ".to @user 30"
            try:
                minutes_val = int(duration_str)
                if minutes_val > 0:
                    final_delta = timedelta(minutes=minutes_val)
                    # Create human-readable string for this case
                    parts = []
                    if minutes_val >= 60:
                        hours = minutes_val // 60
                        parts.append(f"{hours} hour{'s' if hours != 1 else ''}")
                        remaining_minutes = minutes_val % 60
                        if remaining_minutes > 0:
                            parts.append(f"{remaining_minutes} minute{'s' if remaining_minutes != 1 else ''}")
                    else:
                        parts.append(f"{minutes_val} minute{'s' if minutes_val != 1 else ''}")
                    
                    human_readable_str = " and ".join(parts) if parts else "0 seconds"
                    return final_delta, human_readable_str
                else:
                    return None, None # Non-positive raw number
            except ValueError:
                 return None, None # Not a number, and no units found

        if not matches: # If still no matches after trying raw minutes
            return None, None


        delta_args = {"weeks": 0, "days": 0, "hours": 0, "minutes": 0, "seconds": 0}
        
        for amount_str, unit_char in matches:
            try:
                amount = int(amount_str)
                if unit_char == 'w': delta_args["weeks"] += amount
                elif unit_char == 'd': delta_args["days"] += amount
                elif unit_char == 'h': delta_args["hours"] += amount
                elif unit_char == 'm': delta_args["minutes"] += amount
                elif unit_char == 's': delta_args["seconds"] += amount
            except ValueError:
                return None, None # Should not happen if regex matches \d+

        final_delta = timedelta(**delta_args)
        
        # --- Human-readable string generation ---
        if final_delta.total_seconds() <= 0:
            return timedelta(seconds=0), "0 seconds" 

        parts = []
        _total_seconds_val = int(final_delta.total_seconds())
        
        _days_component = _total_seconds_val // (24 * 3600)
        _seconds_remainder_after_days = _total_seconds_val % (24 * 3600)
        
        weeks = _days_component // 7
        days = _days_component % 7

        hours = _seconds_remainder_after_days // 3600
        _seconds_remainder_after_hours = _seconds_remainder_after_days % 3600
        minutes_val = _seconds_remainder_after_hours // 60 # Renamed to avoid conflict
        seconds_val = _seconds_remainder_after_hours % 60 # Renamed to avoid conflict

        if weeks > 0: parts.append(f"{weeks} week{'s' if weeks != 1 else ''}")
        if days > 0: parts.append(f"{days} day{'s' if days != 1 else ''}")
        if hours > 0: parts.append(f"{hours} hour{'s' if hours != 1 else ''}")
        if minutes_val > 0: parts.append(f"{minutes_val} minute{'s' if minutes_val != 1 else ''}")
        if seconds_val > 0: parts.append(f"{seconds_val} second{'s' if seconds_val != 1 else ''}")
        
        if not parts: 
             return timedelta(seconds=0), "0 seconds"

        human_readable_str = ""
        if len(parts) == 1:
            human_readable_str = parts[0]
        elif len(parts) > 1:
            # Join with ", " except for the last element which is joined with " and "
            human_readable_str = ", ".join(parts[:-1]) + f" and {parts[-1]}"
        
        return final_delta, human_readable_str

    @commands.command(aliases=['to'])
    @commands.has_permissions(moderate_members=True)
    async def timeout(self, ctx, member: discord.Member, duration_input_str: str, *, reason: str = None):
        """
        Times out a member for a specified duration.
        Duration format: e.g., "1w2d3h4m5s", "30m", "1d 12h" (quote if spaces).
        """
        try:
            parsed_timedelta, human_readable_duration = self._parse_duration_str(duration_input_str)

            if parsed_timedelta is None or human_readable_duration is None:
                await ctx.send(
                    "Invalid duration format. Please use formats like '1w2d3h4m5s', '30m', '1d', '2h 30m' (if it has spaces, quote it like \"2h 30m\").\n"
                    "Units: w (weeks), d (days), h (hours), m (minutes), s (seconds)."
                )
                return

            total_seconds = parsed_timedelta.total_seconds()

            # Discord's timeout limits: 60 seconds (1 minute) to 28 days.
            min_duration_seconds = 60 
            max_duration_seconds = timedelta(days=28).total_seconds()

            if not (min_duration_seconds <= total_seconds <= max_duration_seconds):
                await ctx.send(
                    f"Timeout duration must be between 1 minute and 28 days. "
                    f"Your input ('{duration_input_str}') resulted in {human_readable_duration}."
                )
                return

            # Check role hierarchy
            bot_member = ctx.guild.me
            # Ensure bot has a role and it's higher than the target member's top role
            if member.top_role >= bot_member.top_role and ctx.guild.owner_id != ctx.author.id : # Allow guild owner to bypass
                 # Check if the target is the guild owner, who cannot be timed out by anyone.
                if member.id == ctx.guild.owner_id:
                    await ctx.send("I cannot timeout the server owner.")
                    return
                await ctx.send("I cannot timeout this member because their role is higher than or equal to mine.")
                return
            
            # Prevent bot from timing out itself
            if member.id == self.bot.user.id:
                await ctx.send("I cannot timeout myself.")
                return

            # Apply the timeout
            await member.timeout(parsed_timedelta, reason=reason)
            # No need for debug messages in production code, but kept from original for consistency
            # await ctx.send("DEBUG: Timeout action completed.") 

            # Log the action
            history_cog = self.bot.get_cog('History') # Renamed to avoid conflict
            if history_cog:
                # await ctx.send("DEBUG: History cog found, logging action.") 
                history_cog.log_action(ctx.guild.id, member.id, f"Timed Out ({human_readable_duration})", ctx.author, reason)
            # else:
                # await ctx.send("DEBUG: History cog not found, skipping logging.")

            # Create embed using utils
            utils_cog = self.bot.get_cog('Utils') # Renamed to avoid conflict
            if not utils_cog:
                await ctx.send("Error: Utils cog not loaded. Cannot send confirmation embed.")
                # Still, the timeout was applied, so we might not want to return just yet.
                # Or, send a plain text confirmation.
                await ctx.send(f"Successfully timed out {member.mention} for {human_readable_duration}.")
                return

            embed = utils_cog.create_embed(ctx, title="Member Timed Out")
            embed.description = f"Timed out {member.mention} for {human_readable_duration}"
            if reason:
                embed.description += f"\n**Reason:** {reason}"

            await ctx.send(embed=embed)

        except discord.Forbidden:
            await ctx.send("I don't have permission to timeout members (requires 'Moderate Members') or my role is too low.")
        except discord.HTTPException as e:
            await ctx.send(f"Failed to timeout due to an API error: {str(e)}")
        except Exception as e:
            await ctx.send(f"An unexpected error occurred during timeout: {str(e)}")
            # It's good practice to log the full traceback for unexpected errors
            print(f"Unexpected error in timeout command: {e}")
            import traceback
            traceback.print_exc()
            # raise e # Re-raise for Heroku logs if that's your logging setup

    @timeout.error
    async def timeout_error(self, ctx, error):
        if isinstance(error, commands.MissingPermissions):
            await ctx.send("You need 'Moderate Members' permission to use this command.")
        elif isinstance(error, commands.MemberNotFound):
            await ctx.send(f"Member not found: `{error.argument}`. Please provide a valid member (mention, ID, or name).")
        elif isinstance(error, commands.MissingRequiredArgument):
            if error.param.name == 'member':
                 await ctx.send("You need to specify which member to timeout.\nUsage: `.timeout <@user/ID> <duration> [reason]`")
            elif error.param.name == 'duration_input_str':
                 await ctx.send("You need to specify the duration for the timeout.\nUsage: `.timeout <@user/ID> <duration (e.g., 30m, 1d2h)> [reason]`")
            else:
                 await ctx.send(f"Missing argument: {error.param.name}. Usage: `.timeout <@user/ID> <duration> [reason]`")
        elif isinstance(error, commands.BadArgument): # Catches MemberNotFound if it's not handled specifically, or other conversion errors
            await ctx.send(f"Invalid argument provided. Please check the member and duration format.\nUsage: `.timeout <@user/ID> <duration (e.g., 1d, \"2h 30m\")> [reason]`")
        elif isinstance(error, commands.CommandInvokeError):
            # Log the original error for debugging
            print(f"CommandInvokeError in timeout: {error.original}")
            import traceback
            traceback.print_exc()
            await ctx.send("An internal error occurred while executing the timeout command. Please check bot logs or contact support.")
        else:
            await ctx.send(f"An unexpected error occurred: {error}")


async def setup(bot):
    await bot.add_cog(Timeout(bot))
