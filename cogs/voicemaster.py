import discord
from discord.ext import commands, tasks
import json
import os
import traceback
from typing import Optional, Dict

VOICEMASTER_CONFIG_FILE = "voicemaster_config.json"

class VoiceMaster(commands.Cog):
    """
    Manages 'Join to Create' voice channel functionality.
    """
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # {guild_id: {"trigger_channel_id": int, "target_category_id": int, "name_template": str}}
        self.configs = {}
        # {guild_id: {temp_channel_id: owner_id}}
        self.managed_channels = {} 
        self.load_configs()
        print("[VoiceMaster DEBUG] Cog initialized.")

    def load_configs(self):
        if os.path.exists(VOICEMASTER_CONFIG_FILE):
            try:
                with open(VOICEMASTER_CONFIG_FILE, 'r') as f:
                    loaded_data = json.load(f)
                    # Ensure guild_ids are integers
                    self.configs = {int(k): v for k, v in loaded_data.items()}
                print(f"[VoiceMaster DEBUG] Configs loaded: {self.configs}")
            except (json.JSONDecodeError, TypeError, ValueError) as e:
                print(f"VoiceMaster: Error loading configs from {VOICEMASTER_CONFIG_FILE}: {e}")
                self.configs = {}
        else:
            print(f"VoiceMaster: {VOICEMASTER_CONFIG_FILE} not found. No configs loaded.")
            self.configs = {}

    def _save_configs(self):
        try:
            with open(VOICEMASTER_CONFIG_FILE, 'w') as f:
                # Ensure keys are strings for JSON compatibility
                json.dump({str(k): v for k, v in self.configs.items()}, f, indent=4)
            print("[VoiceMaster DEBUG] Configs saved.")
        except IOError as e:
            print(f"VoiceMaster: Error saving configs to {VOICEMASTER_CONFIG_FILE}: {e}")

    async def _create_user_channel(self, member: discord.Member, guild_config: dict):
        guild = member.guild
        category = guild.get_channel(guild_config.get("target_category_id"))
        if not category or not isinstance(category, discord.CategoryChannel):
            print(f"[VoiceMaster DEBUG] Target category ID {guild_config.get('target_category_id')} not found or invalid for guild {guild.id}.")
            # Optionally notify admin or user
            return

        # Ensure bot has permissions in the category
        if not category.permissions_for(guild.me).manage_channels or \
           not category.permissions_for(guild.me).move_members:
            print(f"[VoiceMaster DEBUG] Bot missing Manage Channels or Move Members permission in category '{category.name}' for guild {guild.id}.")
            return

        name_template = guild_config.get("name_template", "{member}'s Channel")
        channel_name = name_template.replace("{member}", member.display_name)
        
        # Define permissions for the new channel owner
        owner_overwrites = discord.PermissionOverwrite(
            manage_channels=True,    # Rename, set user limit, bitrate for THIS channel
            manage_permissions=True, # Manage permissions for THIS channel (e.g., for others)
            move_members=True,       # Move members within THIS channel
            mute_members=True,
            deafen_members=True,
            priority_speaker=True,
            stream=True,
            connect=True,
            speak=True,
            view_channel=True
        )
        # Default permissions for @everyone in the new channel
        everyone_overwrites = discord.PermissionOverwrite(
            connect=True,
            speak=True,
            view_channel=True
        )

        try:
            # Create the new voice channel
            new_channel = await category.create_voice_channel(
                name=channel_name,
                overwrites={
                    guild.default_role: everyone_overwrites, # @everyone
                    member: owner_overwrites # Channel creator/owner
                },
                reason=f"VoiceMaster: Temporary channel for {member.display_name}"
            )
            print(f"[VoiceMaster DEBUG] Created channel '{new_channel.name}' (ID: {new_channel.id}) for {member.name} in guild {guild.id}.")

            # Move the member to their new channel
            await member.move_to(new_channel, reason="VoiceMaster: Moved to own temporary channel.")
            print(f"[VoiceMaster DEBUG] Moved {member.name} to '{new_channel.name}'.")

            # Track the managed channel
            if guild.id not in self.managed_channels:
                self.managed_channels[guild.id] = {}
            self.managed_channels[guild.id][new_channel.id] = member.id

        except discord.Forbidden:
            print(f"[VoiceMaster DEBUG] FORBIDDEN to create channel or move member in guild {guild.id}.")
        except discord.HTTPException as e:
            print(f"[VoiceMaster DEBUG] HTTPException during channel creation/move for {member.name}: {e}")
        except Exception as e:
            print(f"[VoiceMaster DEBUG] Unexpected error in _create_user_channel for {member.name}: {e}")
            traceback.print_exc()

    async def _delete_if_empty_managed_channel(self, channel: discord.VoiceChannel):
        if not channel: return
        guild = channel.guild
        if guild.id in self.managed_channels and channel.id in self.managed_channels[guild.id]:
            if not channel.members: # Channel is empty
                try:
                    await channel.delete(reason="VoiceMaster: Temporary channel empty.")
                    print(f"[VoiceMaster DEBUG] Deleted empty managed channel '{channel.name}' (ID: {channel.id}) in guild {guild.id}.")
                except discord.Forbidden:
                    print(f"[VoiceMaster DEBUG] FORBIDDEN to delete channel '{channel.name}' in guild {guild.id}.")
                except discord.HTTPException as e:
                    print(f"[VoiceMaster DEBUG] HTTPException deleting channel '{channel.name}': {e}")
                except Exception as e:
                    print(f"[VoiceMaster DEBUG] Unexpected error deleting channel '{channel.name}': {e}")
                    traceback.print_exc()
                finally:
                    # Always remove from tracking if we attempt deletion
                    if channel.id in self.managed_channels[guild.id]:
                        del self.managed_channels[guild.id][channel.id]
                    if not self.managed_channels[guild.id]: # If guild has no more managed channels
                        del self.managed_channels[guild.id]

    @commands.Cog.listener()
    async def on_voice_state_update(self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
        guild = member.guild
        guild_config = self.configs.get(guild.id)

        if not guild_config: # VoiceMaster not configured for this guild
            return

        trigger_channel_id = guild_config.get("trigger_channel_id")

        # User joined the "Join to Create" channel
        if after.channel and after.channel.id == trigger_channel_id:
            print(f"[VoiceMaster DEBUG] {member.name} joined trigger channel '{after.channel.name}' in guild {guild.id}.")
            # Prevent creating multiple channels if user quickly re-joins
            # Check if user already owns a temp channel (simple check, might need refinement for edge cases)
            is_owning_temp_channel = False
            if guild.id in self.managed_channels:
                for owner_id in self.managed_channels[guild.id].values():
                    if owner_id == member.id:
                        is_owning_temp_channel = True
                        break
            if not is_owning_temp_channel:
                 await self._create_user_channel(member, guild_config)
            else:
                print(f"[VoiceMaster DEBUG] {member.name} already owns a temporary channel. Not creating a new one.")


        # User left a channel or moved from one
        if before.channel:
            # Check if the channel they left was a managed one and if it's now empty
            await self._delete_if_empty_managed_channel(before.channel)
            
        # If user moved to a different channel, also check their previous channel
        # This is covered by the above `if before.channel:` block.

    # --- Configuration Commands ---
    @commands.group(name="voicemaster", aliases=["vm"], invoke_without_command=True)
    @commands.has_permissions(manage_guild=True)
    @commands.guild_only()
    async def voicemaster_group(self, ctx: commands.Context):
        """Manages VoiceMaster 'Join to Create' settings."""
        if ctx.invoked_subcommand is None:
            config = self.configs.get(ctx.guild.id)
            title = "VoiceMaster Status"
            if config:
                trigger_ch = ctx.guild.get_channel(config.get("trigger_channel_id", 0))
                category_ch = ctx.guild.get_channel(config.get("target_category_id", 0))
                template = config.get("name_template", "{member}'s Channel")
                description = (
                    f"**Trigger Channel:** {trigger_ch.mention if trigger_ch else 'Not Set or Invalid'}\n"
                    f"**Target Category:** {category_ch.name if category_ch else 'Not Set or Invalid'}\n"
                    f"**Channel Name Template:** `{template}`"
                )
            else:
                description = "VoiceMaster is not yet configured for this server.\n" \
                              "Use `.vm setup` to begin."
            await self._send_embed_response(ctx, title, description, discord.Color.blue())


    @voicemaster_group.command(name="setup")
    @commands.has_permissions(manage_guild=True)
    @commands.bot_has_permissions(manage_channels=True, move_members=True) # For initial setup checks
    async def vm_setup(self, ctx: commands.Context, trigger_channel: discord.VoiceChannel, target_category: discord.CategoryChannel, *, name_template: str = "{member}'s Channel"):
        """
        Sets up VoiceMaster: the trigger channel, target category, and channel name template.
        Example: .vm setup #JoinToCreate "Temporary VCs" "{member}'s Hangout"
        (Ensure category name is quoted if it has spaces)
        """
        if not trigger_channel.permissions_for(ctx.guild.me).connect:
             await self._send_embed_response(ctx, "Setup Error", f"I need 'Connect' permission for the trigger channel {trigger_channel.mention}.", discord.Color.red())
             return
        if not target_category.permissions_for(ctx.guild.me).manage_channels or \
           not target_category.permissions_for(ctx.guild.me).move_members:
            await self._send_embed_response(ctx, "Setup Error", f"I need 'Manage Channels' and 'Move Members' permissions in the category '{target_category.name}'.", discord.Color.red())
            return

        self.configs[ctx.guild.id] = {
            "trigger_channel_id": trigger_channel.id,
            "target_category_id": target_category.id,
            "name_template": name_template
        }
        self._save_configs()
        description = (
            f"✅ VoiceMaster setup complete!\n"
            f"**Trigger Channel:** {trigger_channel.mention}\n"
            f"**Target Category:** {target_category.name}\n"
            f"**Channel Name Template:** `{name_template}`"
        )
        await self._send_embed_response(ctx, "VoiceMaster Setup", description, discord.Color.green())
        print(f"[VoiceMaster DEBUG] Config for guild {ctx.guild.id} updated: {self.configs[ctx.guild.id]}")

    @voicemaster_group.command(name="disable")
    @commands.has_permissions(manage_guild=True)
    async def vm_disable(self, ctx: commands.Context):
        """Disables VoiceMaster for this server."""
        if ctx.guild.id in self.configs:
            del self.configs[ctx.guild.id]
            # Also clear any managed channels for this guild from memory
            if ctx.guild.id in self.managed_channels:
                del self.managed_channels[ctx.guild.id]
            self._save_configs()
            await self._send_embed_response(ctx, "VoiceMaster Disabled", "ℹ️ VoiceMaster functionality has been disabled for this server.", discord.Color.orange())
            print(f"[VoiceMaster DEBUG] Config for guild {ctx.guild.id} disabled.")
        else:
            await self._send_embed_response(ctx, "VoiceMaster Info", "ℹ️ VoiceMaster is not currently configured on this server.", discord.Color.blue())
            
    # --- Helper for sending embeds ---
    async def _send_embed_response(self, ctx: commands.Context, title: str, description: str, color: discord.Color):
        """Helper to send embed responses, using Utils cog if available."""
        utils_cog = self.bot.get_cog('Utils')
        if utils_cog:
            embed = utils_cog.create_embed(ctx, title=title, description=description, color=color)
        else: # Fallback embed creation
            embed = discord.Embed(title=title, description=description, color=color, timestamp=datetime.datetime.now(datetime.timezone.utc))
            if ctx and ctx.author:
                embed.set_footer(text=f"Requested by {ctx.author.name}", icon_url=ctx.author.display_avatar.url if ctx.author.avatar else None)
        await ctx.send(embed=embed)

    # --- Error Handlers ---
    @voicemaster_group.error
    async def vm_group_error(self, ctx, error):
        if isinstance(error, commands.MissingPermissions):
            await self._send_embed_response(ctx, "Permission Denied", "You need 'Manage Guild' permission to use VoiceMaster commands.", discord.Color.red())
        elif isinstance(error, commands.NoPrivateMessage):
            await self._send_embed_response(ctx, "Command Error", "This command cannot be used in private messages.", discord.Color.red())
        else:
            await self._send_embed_response(ctx, "VoiceMaster Error", f"An unexpected error occurred: {error}", discord.Color.red())
            print(f"Error in voicemaster_group: {error}"); traceback.print_exc()

    @vm_setup.error
    async def vm_setup_error(self, ctx, error):
        title = "VoiceMaster Setup Error"
        if isinstance(error, commands.MissingPermissions):
            await self._send_embed_response(ctx, title, "You need 'Manage Guild' permission.", discord.Color.red())
        elif isinstance(error, commands.BotMissingPermissions):
            missing_perms = ", ".join(error.missing_permissions)
            await self._send_embed_response(ctx, title, f"I am missing required permissions: `{missing_perms}`.", discord.Color.red())
        elif isinstance(error, commands.ChannelNotFound):
            await self._send_embed_response(ctx, title, f"Channel/Category not found: `{error.argument}`.", discord.Color.red())
        elif isinstance(error, commands.BadArgument):
            await self._send_embed_response(ctx, title, f"Invalid argument. Ensure you provide a valid Voice Channel and Category.\nUsage: `.vm setup #JoinToCreate \"Category Name\" \"{{member}}'s Room\"`", discord.Color.red())
        elif isinstance(error, commands.MissingRequiredArgument):
            await self._send_embed_response(ctx, title, f"Missing argument: `{error.param.name}`.\nUsage: `.vm setup #JoinToCreate \"Category Name\" \"{{member}}'s Room\"`", discord.Color.red())
        else:
            await self._send_embed_response(ctx, title, f"An unexpected error occurred: {error}", discord.Color.red())
            print(f"Error in vm_setup: {error}"); traceback.print_exc()
            
    @vm_disable.error
    async def vm_disable_error(self, ctx, error):
        if isinstance(error, commands.MissingPermissions):
            await self._send_embed_response(ctx, "Permission Denied", "You need 'Manage Guild' permission.", discord.Color.red())
        else:
            await self._send_embed_response(ctx, "VoiceMaster Disable Error", f"An unexpected error occurred: {error}", discord.Color.red())
            print(f"Error in vm_disable: {error}"); traceback.print_exc()


async def setup(bot: commands.Bot):
    # Ensure necessary intents (members, voice_states) are enabled in your main bot file
    await bot.add_cog(VoiceMaster(bot))
    print("Cog 'VoiceMaster' loaded successfully.")

