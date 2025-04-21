# cogs/moderationhistory.py (Pre-formatting Fix)

# ... (Keep all imports and the rest of the class definition the same) ...
# ... (Keep __init__, _parse_db_url, _get_db_connection, _fetch_moderator_actions) ...
# ... (Keep the main moderationhistory command structure up to the point where get_page_embed is defined) ...

            # --- REVISED get_page_embed ---
            def get_page_embed(page_num):
                """ Creates an embed for the specified page number with pre-formatting. """
                start_idx = (page_num - 1) * actions_per_page
                end_idx = start_idx + actions_per_page
                start_idx = max(0, start_idx)
                end_idx = min(len(actions), end_idx)
                page_actions = actions[start_idx:end_idx]

                description = ""
                for i, action_data in enumerate(page_actions):
                    # Basic check
                    if not isinstance(action_data, dict):
                        print(f"DEBUG: Skipping invalid action_data at index {start_idx + i}. Expected dict, got {type(action_data)}: {action_data}")
                        description += f"Error processing action at index {start_idx + i} (Invalid Data Type)\n\n"
                        continue

                    # --- Pre-format and validate each piece ---
                    case_id_str = "N/A"
                    action_str = "N/A"
                    target_mention_str = "N/A"
                    timestamp_str = "N/A"
                    reason_str = "N/A"
                    error_occurred = False
                    error_details = ""

                    try:
                        # Process Case ID
                        case_id_val = action_data.get("case_id")
                        case_id_str = str(case_id_val) if case_id_val is not None else "N/A"

                        # Process Action
                        action_val = action_data.get("action")
                        action_str = str(action_val) if action_val is not None else "N/A"

                        # Process Target Mention
                        target_mention_val = action_data.get("member_mention")
                        target_mention_str = str(target_mention_val) if target_mention_val is not None else "N/A"

                        # Process Timestamp
                        timestamp_val = action_data.get("timestamp")
                        if timestamp_val is not None:
                            try:
                                timestamp_str = discord.utils.format_dt(int(float(timestamp_val)), style="R")
                            except (TypeError, ValueError):
                                print(f"DEBUG: Invalid timestamp value {timestamp_val} for case {case_id_str}")
                                timestamp_str = "Invalid time"
                        else:
                            timestamp_str = "No time recorded"

                        # Process Reason
                        reason_val = action_data.get("reason", "No reason provided") # Default already handled by get
                        # Ensure reason is string, handle None explicitly just in case
                        reason_str = str(reason_val) if reason_val is not None else "No reason provided"

                    except Exception as e:
                        # Catch errors during individual processing steps
                        error_type = type(e).__name__
                        error_details = f" ({error_type})"
                        print(f"ERROR: Error pre-processing action_data dict: {action_data}. Error: {e}")
                        traceback.print_exc()
                        error_occurred = True

                    # --- Build description entry ---
                    if error_occurred:
                        description += f"Error processing case ID {case_id_str}{error_details}\n\n"
                    else:
                        # Combine the pre-formatted strings
                        description += (f"**Case ID:** {case_id_str} | **Action:** {action_str} | "
                                        f"**Target:** {target_mention_str}\n"
                                        f"**Time:** {timestamp_str} | **Reason:** {reason_str}\n\n")

                # --- Create Embed ---
                embed = utils.create_embed(ctx, title=f"Moderation Actions by {member.display_name}")
                embed.description = description.strip() or "No actions on this page."
                embed.set_footer(text=f"Page {page_num}/{total_pages} | Requested by {ctx.author.display_name}")
                return embed
            # --- END REVISED get_page_embed ---

            # --- Rest of the command (Initial send, Pagination Logic) ---
            # ... (Keep the rest of the moderationhistory command the same) ...
            # Initial message send
            message = await ctx.send(embed=get_page_embed(current_page))

            # Add pagination reactions if more than one page
            if total_pages > 1:
                # ... (Keep pagination logic the same as previous revision) ...


        # --- Exception Handling (Keep the same as previous revision) ---
        except discord.Forbidden as e:
            await ctx.send(f"I lack permissions for this command. Error: {e.text}")
        # ... (Keep other except blocks) ...
        except Exception as e:
            await ctx.send(f"An unexpected error occurred. Check logs for details.")
            print(f"ERROR: Unexpected error in moderationhistory command: {e}")
            traceback.print_exc()

    # --- Error Handler (Keep the same as previous revision) ---
    @moderationhistory.error
    async def moderationhistory_error(self, ctx, error):
        """ Error handler for the moderationhistory command. """
        # ... (Keep the same as previous revision) ...


# Setup function (Keep the same as previous revision)
async def setup(bot):
    await bot.add_cog(ModerationHistory(bot))
