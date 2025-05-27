import discord
from discord.ext import commands
import sqlite3
import asyncio

# --- Database Schema (for minwoolee_voice.db) ---
# This cog will attempt to create these tables if they don't exist.
#
# CREATE TABLE IF NOT EXISTS guild (
#     guildID INTEGER PRIMARY KEY,    /* Discord Guild ID */
#     ownerID INTEGER,                /* Discord User ID of the Guild Owner who set it up */
#     voiceChannelID INTEGER,         /* ID of the "Join to Create" voice channel */
#     voiceCategoryID INTEGER         /* ID of the Category where new VCs are made */
# );
#
# CREATE TABLE IF NOT EXISTS voiceChannel ( /* Tracks active user-owned temporary VCs */
#     userID INTEGER,                 /* Discord User ID of the channel owner */
#     voiceID INTEGER PRIMARY KEY     /* The ID of the temporary VC created by the user */
# );
#
# CREATE TABLE IF NOT EXISTS userSettings ( /* User's preferred default name/limit for their VCs */
#     userID INTEGER PRIMARY KEY,     /* Discord User ID */
#     channelName TEXT,               /* Preferred channel name template */
#     channelLimit INTEGER            /* Preferred user limit (0 for unlimited) */
# );
#
# CREATE TABLE IF NOT EXISTS guildSettings ( /* Guild-wide default limit for VCs */
#     guildID INTEGER PRIMARY KEY,    /* Discord Guild ID */
#     defaultTemplateName TEXT,       /* In original, stored "{owner_name}'s channel" - somewhat unused */
#     channelLimit INTEGER            /* Default user limit for channels in this guild (0 for unlimited) */
# );
# --- End Database Schema ---

class MinwooLeeVoiceCog(commands.Cog, name="VoiceMaster (MinwooLee)"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.db_name = "minwoolee_voice.db" # Database file will be created where bot runs
        self._init_db()

    def _init_db(self):
        """Initializes the database and tables if they don't exist."""
        try:
            conn = sqlite3.connect(self.db_name)
            c = conn.cursor()
            c.execute('''CREATE TABLE IF NOT EXISTS guild (
                            guildID INTEGER PRIMARY KEY,
                            ownerID INTEGER,
                            voiceChannelID INTEGER,
                            voiceCategoryID INTEGER
                        )''')
            c.execute('''CREATE TABLE IF NOT EXISTS voiceChannel (
                            userID INTEGER,
                            voiceID INTEGER PRIMARY KEY
                        )''')
            c.execute('''CREATE TABLE IF NOT EXISTS userSettings (
                            userID INTEGER PRIMARY KEY,
                            channelName TEXT,
                            channelLimit INTEGER
                        )''')
            c.execute('''CREATE TABLE IF NOT EXISTS guildSettings (
                            guildID INTEGER PRIMARY KEY,
                            defaultTemplateName TEXT,
                            channelLimit INTEGER
                        )''')
            conn.commit()
        except sqlite3.Error as e:
            print(f"[VoiceMaster DB Init Error] {e}")
        finally:
            if conn:
                conn.close()

    async def _create_branded_embed(self, ctx: commands.Context, title: str, description: str = "", color: int = 0x2E66B6): # MinwooLee color (example)
        """Helper to create consistently branded embeds."""
        embed = discord.Embed(title=title, description=description, color=color)
        author_name = "MinwooLee's VoiceMaster"
        author_icon_url = None
        if ctx.guild and ctx.guild.icon:
            author_icon_url = ctx.guild.icon.url
        embed.set_author(name=author_name, icon_url=author_icon_url)
        embed.set_footer(text="VoiceMaster by MinwooLee")
        return embed

    @commands.Cog.listener()
    async def on_voice_state_update(self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
        # Avoid processing bot's own voice state changes if any
        if member.bot:
            return

        conn = sqlite3.connect(self.db_name)
        c = conn.cursor()
        try:
            guildID = member.guild.id
            c.execute("SELECT voiceChannelID, voiceCategoryID FROM guild WHERE guildID = ?", (guildID,))
            guild_config = c.fetchone()

            if not guild_config:
                return # VoiceMaster not set up for this guild

            master_channel_id, category_id = guild_config

            # User joins the "Join to Create" channel
            if after.channel and after.channel.id == master_channel_id:
                print(f"[VoiceMaster DEBUG] User {member.display_name} joined master channel {master_channel_id} in guild {guildID}.")
                c.execute("SELECT voiceID FROM voiceChannel WHERE userID = ?", (member.id,))
                existing_user_channel = c.fetchone()

                if existing_user_channel:
                    print(f"[VoiceMaster DEBUG] User {member.display_name} already has/had channel {existing_user_channel[0]}. Sending 'cooldown' message.")
                    try:
                        await member.send("You seem to already have an active channel or are creating them too quickly. Please wait or manage your existing channel.")
                    except discord.Forbidden: pass # Can't DM user
                    return

                target_category = self.bot.get_channel(category_id)
                if not target_category or not isinstance(target_category, discord.CategoryChannel):
                    print(f"[VoiceMaster ERROR] Category ID {category_id} not found or not a category in guild {guildID}.")
                    return

                # Determine channel name and limit
                c.execute("SELECT channelName, channelLimit FROM userSettings WHERE userID = ?", (member.id,))
                user_settings = c.fetchone()
                c.execute("SELECT channelLimit FROM guildSettings WHERE guildID = ?", (guildID,))
                guild_settings = c.fetchone()

                channel_name_to_create = f"{member.display_name}'s Channel"
                channel_limit_to_create = 0 # Default unlimited

                if guild_settings and guild_settings[0] is not None:
                    channel_limit_to_create = guild_settings[0]
                if user_settings:
                    if user_settings[0]: # Custom name
                        channel_name_to_create = user_settings[0]
                    if user_settings[1] is not None: # Custom limit (0 for unlimited)
                        channel_limit_to_create = user_settings[1]
                
                print(f"[VoiceMaster DEBUG] Determined creation params: Name='{channel_name_to_create}', Limit={channel_limit_to_create}")

                try:
                    overwrites = {
                        member.guild.default_role: discord.PermissionOverwrite(view_channel=True, connect=True), # Allow general connect if category allows
                        member: discord.PermissionOverwrite(view_channel=True, connect=True, manage_channels=True, manage_permissions=True, move_members=True, speak=True, stream=True),
                        member.guild.me: discord.PermissionOverwrite(view_channel=True, connect=True, manage_channels=True, manage_permissions=True, move_members=True)
                    }
                    print(f"[VoiceMaster DEBUG] About to create channel '{channel_name_to_create}' for {member.display_name} in category {target_category.name}.")
                    new_channel = await member.guild.create_voice_channel(
                        name=channel_name_to_create,
                        category=target_category,
                        user_limit=channel_limit_to_create,
                        overwrites=overwrites,
                        reason=f"Temporary channel for {member.display_name}"
                    )
                    print(f"[VoiceMaster DEBUG] Channel '{new_channel.name}' ({new_channel.id}) CREATED for {member.display_name}.")

                    try:
                        print(f"[VoiceMaster DEBUG] Attempting to move {member.display_name} to {new_channel.name} ({new_channel.id}).")
                        await member.move_to(new_channel)
                        print(f"[VoiceMaster DEBUG] Successfully moved {member.display_name} to {new_channel.name}.")
                    except discord.Forbidden as e_move_forbidden:
                        print(f"[VoiceMaster ERROR] FORBIDDEN to move {member.display_name} to {new_channel.name}: {e_move_forbidden}")
                        await member.send(f"I created your channel '{new_channel.name}', but I don't have permission to move you to it. Please check my 'Move Members' permission.")
                        await new_channel.delete(reason="Failed to move owner after creation due to permissions") # Cleanup
                        return # Stop further processing for this channel
                    except discord.HTTPException as e_move_http: # Catches other discord related errors for move
                        print(f"[VoiceMaster ERROR] HTTP Exception while moving {member.display_name} to {new_channel.name}: {e_move_http}")
                        await member.send(f"I created your channel '{new_channel.name}', but an API error occurred while trying to move you.")
                        await new_channel.delete(reason="Failed to move owner after creation due to API error") # Cleanup
                        return
                    except Exception as e_move_other: # Catch any other unexpected error during move
                        print(f"[VoiceMaster ERROR] UNKNOWN Exception while moving {member.display_name} to {new_channel.name}: {e_move_other}")
                        await member.send(f"I created your channel '{new_channel.name}', but an unexpected error occurred moving you.")
                        await new_channel.delete(reason="Failed to move owner after creation due to unknown error") # Cleanup
                        return

                    c.execute("INSERT INTO voiceChannel VALUES (?, ?)", (member.id, new_channel.id))
                    conn.commit()
                    print(f"[VoiceMaster DEBUG] DB record inserted for {member.display_name}, channel {new_channel.id}.")

                    # The original repository had a self-blocking wait_for here for channel deletion.
                    # This is bad practice as it holds up the on_voice_state_update handler.
                    # Deletion should be handled when users leave (see below) or by a periodic task.

                except discord.Forbidden as e_create_forbidden:
                    print(f"[VoiceMaster ERROR] FORBIDDEN during channel CREATION for {member.display_name} in guild {guildID}: {e_create_forbidden}")
                    try: await member.send("I don't have enough permissions to create a voice channel for you (I need 'Manage Channels'). Please contact a server admin.")
                    except discord.Forbidden: pass
                except Exception as e_create:
                    print(f"[VoiceMaster ERROR] Exception during channel CREATION for {member.display_name}: {e_create}")
                    try: await member.send(f"Sorry, an error occurred while trying to create your channel: {e_create}")
                    except discord.Forbidden: pass

            # User leaves a voice channel - check if it was a temporary one
            elif before.channel and not after.channel: # User disconnected from a channel
                # Check if the channel they left was a temporary channel
                # We don't necessarily need to check if they owned it to delete it if empty
                c.execute("SELECT voiceID FROM voiceChannel WHERE voiceID = ?", (before.channel.id,))
                temp_channel_data = c.fetchone()

                if temp_channel_data: # The channel left was a temporary channel
                    # Check if it's now empty
                    # Need to re-fetch the channel object as 'before.channel' might be stale or have old member list
                    channel_to_check = self.bot.get_channel(before.channel.id)
                    if channel_to_check and not channel_to_check.members: # Channel is now empty
                        print(f"[VoiceMaster DEBUG] Temp channel {channel_to_check.name} ({channel_to_check.id}) is now empty. Deleting.")
                        try:
                            await channel_to_check.delete(reason="Temporary channel empty")
                            c.execute('DELETE FROM voiceChannel WHERE voiceID=?', (channel_to_check.id,))
                            conn.commit()
                            print(f"[VoiceMaster DEBUG] Deleted channel {channel_to_check.id} and DB entry.")
                        except discord.NotFound:
                            print(f"[VoiceMaster DEBUG] Channel {channel_to_check.id} already deleted. Removing from DB.")
                            c.execute('DELETE FROM voiceChannel WHERE voiceID=?', (channel_to_check.id,)) # Ensure DB cleanup
                            conn.commit()
                        except discord.Forbidden:
                            print(f"[VoiceMaster ERROR] Missing permissions to delete temp channel {channel_to_check.id} in guild {guildID}.")
                        except Exception as e_del_leave:
                            print(f"[VoiceMaster ERROR] Error during auto-deletion on leave for {channel_to_check.id}: {e_del_leave}")

        except sqlite3.Error as e_sql:
            print(f"[VoiceMaster DB Error] on_voice_state_update: {e_sql}")
        except Exception as e_main:
            print(f"[VoiceMaster Main Error] on_voice_state_update: {e_main}")
        finally:
            if conn:
                conn.close()

    @commands.group(invoke_without_command=True, aliases=['voicechannel'])
    async def vc(self, ctx: commands.Context):
        """Manages temporary voice channels. Type .vc for help."""
        if ctx.invoked_subcommand is None:
            desc = (
                f"**Create Your Channel:** Join the designated 'Join to Create' voice channel.\n\n"
                f"**Available Commands:**\n"
                f"*(Manage your own temporary channel)*\n"
                f"`{ctx.prefix}vc lock` - Locks your channel (only permitted users can join).\n"
                f"`{ctx.prefix}vc unlock` - Unlocks your channel for everyone.\n"
                f"`{ctx.prefix}vc name <new channel name>` - Renames your channel.\n"
                f"`{ctx.prefix}vc limit <number>` - Sets user limit (0 for unlimited).\n"
                f"`{ctx.prefix}vc permit @user` - Allows a specific user to join your locked channel.\n"
                f"`{ctx.prefix}vc reject @user` - Removes user's permission & kicks them if in channel.\n"
                f"`{ctx.prefix}vc claim` - Claims an orphaned temporary channel you are in.\n\n"
                f"*(Admin Commands)*\n"
                f"`{ctx.prefix}vc setup` - Interactive setup for server (owner/admin only).\n"
                f"`{ctx.prefix}vc setguildlimit <number>` - Sets default user limit for new temp channels (owner/admin only)."
            )
            help_embed = await self._create_branded_embed(ctx, "MinwooLee's VoiceMaster Help", desc)
            await ctx.send(embed=help_embed)

    @vc.command(name="setup")
    async def vc_setup(self, ctx: commands.Context):
        """Interactive setup for VoiceMaster (Server Owner or Bot Admin only)."""
        # Hardcoded ID (151028268856770560) is from original repo.
        # Replace with MinwooLee's ID, make configurable, or rely purely on permissions.
        is_bot_owner = await self.bot.is_owner(ctx.author)
        if not (ctx.author.id == ctx.guild.owner_id or ctx.author.id == 151028268856770560 or is_bot_owner):
            return await ctx.send(embed=await self._create_branded_embed(ctx, "Permission Denied", "Only the Server Owner or Bot Administrator can run setup."))

        def check(m: discord.Message):
            return m.author == ctx.author and m.channel == ctx.channel

        await ctx.send(embed=await self._create_branded_embed(ctx, "VoiceMaster Setup", "Starting setup... You have 60 seconds per question."))

        try:
            await ctx.send("1. Please enter the name for the **Category** where new temporary voice channels will be created (e.g., 'Temp Channels'):")
            category_msg = await self.bot.wait_for('message', check=check, timeout=60.0)
            new_category = await ctx.guild.create_category_channel(category_msg.content, reason=f"VoiceMaster setup by {ctx.author.display_name}")

            await ctx.send(f"Category '{new_category.name}' created.\n2. Now, enter the name for the **'Join to Create' voice channel** (e.g., '➕ New VC'):")
            channel_msg = await self.bot.wait_for('message', check=check, timeout=60.0)
            master_channel = await ctx.guild.create_voice_channel(channel_msg.content, category=new_category, reason=f"VoiceMaster setup by {ctx.author.display_name}")

            conn = sqlite3.connect(self.db_name)
            c = conn.cursor()
            c.execute("SELECT guildID FROM guild WHERE guildID = ?", (ctx.guild.id,))
            if c.fetchone():
                c.execute("UPDATE guild SET ownerID = ?, voiceChannelID = ?, voiceCategoryID = ? WHERE guildID = ?",
                          (ctx.guild.owner_id, master_channel.id, new_category.id, ctx.guild.id))
            else:
                c.execute("INSERT INTO guild VALUES (?, ?, ?, ?)",
                          (ctx.guild.id, ctx.guild.owner_id, master_channel.id, new_category.id))
            conn.commit()
            conn.close()
            await ctx.send(embed=await self._create_branded_embed(ctx, "Setup Complete!", f"VoiceMaster is set up!\nJoin Channel: {master_channel.mention}\nChannels Category: '{new_category.name}'"))

        except asyncio.TimeoutError:
            await ctx.send(embed=await self._create_branded_embed(ctx, "Setup Timeout", "You took too long to respond. Setup cancelled."))
        except discord.Forbidden:
            await ctx.send(embed=await self._create_branded_embed(ctx, "Permission Error", "I lack permissions to create channels/categories. Please check my role."))
        except Exception as e:
            await ctx.send(embed=await self._create_branded_embed(ctx, "Setup Error", f"An error occurred: {e}"))
            print(f"[VoiceMaster Setup Error]: {e}")

    @vc.command(name="setguildlimit")
    async def vc_setguildlimit(self, ctx: commands.Context, limit: int):
        """Sets the default user limit for new temp channels (Admin only)."""
        is_bot_owner = await self.bot.is_owner(ctx.author)
        if not (ctx.author.id == ctx.guild.owner_id or ctx.author.id == 151028268856770560 or is_bot_owner):
            return await ctx.send(embed=await self._create_branded_embed(ctx, "Permission Denied", "Only the Server Owner or Bot Administrator can set this."))
        if limit < 0:
            return await ctx.send(embed=await self._create_branded_embed(ctx, "Invalid Limit", "Limit cannot be negative. Use 0 for unlimited."))

        conn = sqlite3.connect(self.db_name)
        c = conn.cursor()
        try:
            c.execute("SELECT guildID FROM guildSettings WHERE guildID = ?", (ctx.guild.id,))
            template_name = f"{ctx.author.display_name}'s default template" # As per original repo's behavior
            if c.fetchone():
                c.execute("UPDATE guildSettings SET channelLimit = ?, defaultTemplateName = ? WHERE guildID = ?", (limit, template_name, ctx.guild.id))
            else:
                c.execute("INSERT INTO guildSettings VALUES (?, ?, ?)", (ctx.guild.id, template_name, limit))
            conn.commit()
            limit_text = "Unlimited" if limit == 0 else str(limit)
            await ctx.send(embed=await self._create_branded_embed(ctx, "Guild Setting Updated", f"Default channel limit for new temporary VCs on this server is now: **{limit_text}**."))
        except sqlite3.Error as e_sql:
            await ctx.send(embed=await self._create_branded_embed(ctx, "Database Error", f"Could not set guild limit: {e_sql}"))
        except Exception as e:
            await ctx.send(embed=await self._create_branded_embed(ctx, "Error", f"Could not set guild limit: {e}"))
        finally:
            conn.close()

    # Helper to get user's current temporary channel
    async def _get_user_channel(self, ctx: commands.Context, c: sqlite3.Cursor):
        c.execute("SELECT voiceID FROM voiceChannel WHERE userID = ?", (ctx.author.id,))
        data = c.fetchone()
        if not data:
            await ctx.send(embed=await self._create_branded_embed(ctx, "Error", "You don't seem to own an active temporary channel."))
            return None
        
        channel = self.bot.get_channel(data[0])
        if not channel:
            # Clean up DB if channel is missing (e.g., deleted manually)
            c.execute("DELETE FROM voiceChannel WHERE voiceID = ?", (data[0],))
            # conn.commit() should be handled by the calling function's finally block
            await ctx.send(embed=await self._create_branded_embed(ctx, "Error", "Your channel was not found (it may have been deleted)."))
            return None
        return channel

    @vc.command(name="lock")
    async def vc_lock(self, ctx: commands.Context):
        """Locks your current temporary voice channel."""
        conn = sqlite3.connect(self.db_name)
        c = conn.cursor()
        try:
            channel = await self._get_user_channel(ctx, c)
            if not channel: return

            await channel.set_permissions(ctx.guild.default_role, connect=False)
            await channel.set_permissions(ctx.author, connect=True) # Ensure owner can still connect
            conn.commit() # Commit DB changes if _get_user_channel cleaned anything
            await ctx.send(embed=await self._create_branded_embed(ctx, "Channel Locked 🔒", f"Your channel '{channel.name}' is now locked. Only permitted users can join."))
        except discord.Forbidden:
            await ctx.send(embed=await self._create_branded_embed(ctx, "Permission Error", "I lack permissions to modify your channel's settings."))
        except Exception as e:
            await ctx.send(embed=await self._create_branded_embed(ctx, "Error", f"Could not lock channel: {e}"))
        finally:
            if conn: conn.close()

    @vc.command(name="unlock")
    async def vc_unlock(self, ctx: commands.Context):
        """Unlocks your current temporary voice channel."""
        conn = sqlite3.connect(self.db_name)
        c = conn.cursor()
        try:
            channel = await self._get_user_channel(ctx, c)
            if not channel: return

            await channel.set_permissions(ctx.guild.default_role, connect=None) # Resets to category/default perms
            conn.commit()
            await ctx.send(embed=await self._create_branded_embed(ctx, "Channel Unlocked 🔓", f"Your channel '{channel.name}' is now unlocked (respects category permissions)."))
        except discord.Forbidden:
            await ctx.send(embed=await self._create_branded_embed(ctx, "Permission Error", "I lack permissions to modify your channel's settings."))
        except Exception as e:
            await ctx.send(embed=await self._create_branded_embed(ctx, "Error", f"Could not unlock channel: {e}"))
        finally:
            if conn: conn.close()

    @vc.command(name="permit", aliases=["allow"])
    async def vc_permit(self, ctx: commands.Context, member: discord.Member):
        """Permits a specific user to join your locked channel."""
        conn = sqlite3.connect(self.db_name)
        c = conn.cursor()
        try:
            channel = await self._get_user_channel(ctx, c)
            if not channel: return

            await channel.set_permissions(member, connect=True, view_channel=True)
            conn.commit()
            await ctx.send(embed=await self._create_branded_embed(ctx, "User Permitted ✅", f"{member.mention} can now join '{channel.name}'."))
        except discord.Forbidden:
            await ctx.send(embed=await self._create_branded_embed(ctx, "Permission Error", "I lack permissions to modify your channel's settings for that user."))
        except Exception as e:
            await ctx.send(embed=await self._create_branded_embed(ctx, "Error", f"Could not permit user: {e}"))
        finally:
            if conn: conn.close()

    @vc.command(name="reject", aliases=["deny"])
    async def vc_reject(self, ctx: commands.Context, member: discord.Member):
        """Revokes a user's permission and kicks them if they are in your channel."""
        conn = sqlite3.connect(self.db_name)
        c = conn.cursor()
        try:
            channel = await self._get_user_channel(ctx, c)
            if not channel: return

            await channel.set_permissions(member, connect=False) # Deny connection
            if member in channel.members:
                # Get the "Join to Create" channel to move the user to
                c.execute("SELECT voiceChannelID FROM guild WHERE guildID = ?", (ctx.guild.id,))
                guild_setup_data = c.fetchone()
                fallback_channel = None
                if guild_setup_data:
                    fallback_channel = self.bot.get_channel(guild_setup_data[0])
                
                try:
                    if fallback_channel and isinstance(fallback_channel, discord.VoiceChannel):
                        await member.move_to(fallback_channel, reason=f"Rejected from {channel.name} by owner {ctx.author.name}")
                    else:
                        await member.move_to(None, reason=f"Rejected from {channel.name} by owner {ctx.author.name}") # Kick from voice
                except discord.HTTPException: # User might not be in a voice channel to move from/to
                    pass 
            conn.commit()
            await ctx.send(embed=await self._create_branded_embed(ctx, "User Rejected ❌", f"{member.mention} has been rejected from '{channel.name}'."))
        except discord.Forbidden:
            await ctx.send(embed=await self._create_branded_embed(ctx, "Permission Error", "I lack permissions to modify channel settings or move that user."))
        except Exception as e:
            await ctx.send(embed=await self._create_branded_embed(ctx, "Error", f"Could not reject user: {e}"))
        finally:
            if conn: conn.close()

    @vc.command(name="limit")
    async def vc_limit(self, ctx: commands.Context, limit: int):
        """Sets the user limit for your temporary channel."""
        if limit < 0:
            return await ctx.send(embed=await self._create_branded_embed(ctx, "Invalid Limit", "Limit cannot be negative. Use 0 for unlimited."))

        conn = sqlite3.connect(self.db_name)
        c = conn.cursor()
        try:
            channel = await self._get_user_channel(ctx, c)
            if not channel: return

            await channel.edit(user_limit=limit)
            
            c.execute("SELECT channelName FROM userSettings WHERE userID = ?", (ctx.author.id,))
            user_setting_data = c.fetchone()
            current_name_for_settings = user_setting_data[0] if user_setting_data and user_setting_data[0] else channel.name

            if user_setting_data is None:
                 c.execute("INSERT INTO userSettings VALUES (?, ?, ?)", (ctx.author.id, current_name_for_settings, limit))
            else:
                 c.execute("UPDATE userSettings SET channelLimit = ? WHERE userID = ?", (limit, ctx.author.id))
            conn.commit()
            limit_text = "Unlimited" if limit == 0 else str(limit)
            await ctx.send(embed=await self._create_branded_embed(ctx, "Channel Limit Set", f"User limit for '{channel.name}' is now **{limit_text}**."))
        except discord.Forbidden:
            await ctx.send(embed=await self._create_branded_embed(ctx, "Permission Error", "I lack permissions to modify your channel's settings."))
        except sqlite3.Error as e_sql:
            await ctx.send(embed=await self._create_branded_embed(ctx, "Database Error", f"Could not save limit setting: {e_sql}"))
        except Exception as e:
            await ctx.send(embed=await self._create_branded_embed(ctx, "Error", f"Could not set limit: {e}"))
        finally:
            if conn: conn.close()

    @vc.command(name="name")
    async def vc_name(self, ctx: commands.Context, *, new_name: str):
        """Changes the name of your temporary voice channel."""
        if not new_name.strip():
             return await ctx.send(embed=await self._create_branded_embed(ctx, "Invalid Name", "Channel name cannot be empty."))
        if len(new_name) > 100: # Discord limit
             return await ctx.send(embed=await self._create_branded_embed(ctx, "Invalid Name", "Channel name is too long (max 100 characters)."))

        conn = sqlite3.connect(self.db_name)
        c = conn.cursor()
        try:
            channel = await self._get_user_channel(ctx, c)
            if not channel: return

            await channel.edit(name=new_name)
            
            c.execute("SELECT channelLimit FROM userSettings WHERE userID = ?", (ctx.author.id,))
            user_setting_data = c.fetchone()
            current_limit_for_settings = user_setting_data[0] if user_setting_data and user_setting_data[0] is not None else 0

            if user_setting_data is None:
                 c.execute("INSERT INTO userSettings VALUES (?, ?, ?)", (ctx.author.id, new_name, current_limit_for_settings))
            else:
                 c.execute("UPDATE userSettings SET channelName = ? WHERE userID = ?", (new_name, ctx.author.id))
            conn.commit()
            await ctx.send(embed=await self._create_branded_embed(ctx, "Channel Name Changed", f"Your channel name is now **{new_name}**."))
        except discord.Forbidden:
            await ctx.send(embed=await self._create_branded_embed(ctx, "Permission Error", "I lack permissions to modify your channel's name."))
        except sqlite3.Error as e_sql:
            await ctx.send(embed=await self._create_branded_embed(ctx, "Database Error", f"Could not save name setting: {e_sql}"))
        except Exception as e:
            await ctx.send(embed=await self._create_branded_embed(ctx, "Error", f"Could not change name: {e}"))
        finally:
            if conn: conn.close()

    @vc.command(name="claim")
    async def vc_claim(self, ctx: commands.Context):
        """Claims an orphaned temporary channel you are currently in."""
        if not ctx.author.voice or not ctx.author.voice.channel:
            return await ctx.send(embed=await self._create_branded_embed(ctx, "Error", "You are not in a voice channel."))

        current_vc = ctx.author.voice.channel
        conn = sqlite3.connect(self.db_name)
        c = conn.cursor()
        try:
            c.execute("SELECT userID FROM voiceChannel WHERE voiceID = ?", (current_vc.id,))
            owner_data = c.fetchone()

            if not owner_data:
                return await ctx.send(embed=await self._create_branded_embed(ctx, "Error", f"'{current_vc.name}' is not a claimable temporary channel managed by me."))

            original_owner_id = owner_data[0]
            if original_owner_id == ctx.author.id:
                 return await ctx.send(embed=await self._create_branded_embed(ctx, "No Need", "You are already the owner of this channel!"))

            original_owner_member = ctx.guild.get_member(original_owner_id)
            if original_owner_member and original_owner_member in current_vc.members:
                return await ctx.send(embed=await self._create_branded_embed(ctx, "Claim Failed", f"The original owner, {original_owner_member.mention}, is still in the channel."))

            c.execute("SELECT voiceID FROM voiceChannel WHERE userID = ?", (ctx.author.id,))
            claimer_channel = c.fetchone()
            if claimer_channel and claimer_channel[0] != current_vc.id:
                 return await ctx.send(embed=await self._create_branded_embed(ctx, "Claim Failed", "You already own another temporary channel."))

            c.execute("UPDATE voiceChannel SET userID = ? WHERE voiceID = ?", (ctx.author.id, current_vc.id))
            # Remove old owner's settings for this channel name/limit preference if they exist,
            # or new owner starts fresh with defaults until they use .vc name/limit.
            # This part was not in original but makes sense. For now, stick to original DB logic.

            conn.commit() # Commit the ownership change
            
            await current_vc.set_permissions(ctx.author, connect=True, view_channel=True, manage_channels=True, manage_permissions=True, move_members=True, speak=True, stream=True)
            if original_owner_member : # If old owner can be identified
                await current_vc.set_permissions(original_owner_member, overwrite=None) # Reset their specific overwrites

            await ctx.send(embed=await self._create_branded_embed(ctx, "Channel Claimed! 🎉", f"{ctx.author.mention}, you are now the owner of '{current_vc.name}'."))
        except discord.Forbidden:
            await ctx.send(embed=await self._create_branded_embed(ctx, "Permission Error", "Ownership updated in DB, but I lack permissions to update channel permissions for you."))
        except sqlite3.Error as e_sql:
            await ctx.send(embed=await self._create_branded_embed(ctx, "Database Error", f"Could not update channel ownership: {e_sql}"))
        except Exception as e:
            await ctx.send(embed=await self._create_branded_embed(ctx, "Error", f"Could not claim channel: {e}"))
        finally:
            if conn: conn.close()
            
    @vc_setup.error
    @vc_setguildlimit.error
    @vc_lock.error
    @vc_unlock.error
    @vc_permit.error
    @vc_reject.error
    @vc_limit.error
    @vc_name.error
    @vc_claim.error
    async def vc_command_error(self, ctx: commands.Context, error: commands.CommandError):
        """Generic error handler for vc commands."""
        if isinstance(error, commands.MissingPermissions):
            await ctx.send(embed=await self._create_branded_embed(ctx, "Permission Denied", "You don't have the required permissions for this command."))
        elif isinstance(error, commands.MissingRequiredArgument):
            await ctx.send(embed=await self._create_branded_embed(ctx, "Missing Argument", f"You missed an argument: `{error.param.name}`. Use `{ctx.prefix}vc` for help."))
        elif isinstance(error, commands.BadArgument): # Catches failed conversions too (e.g., to discord.Member or int)
            await ctx.send(embed=await self._create_branded_embed(ctx, "Invalid Argument", f"An argument you provided was invalid (e.g., wrong type or format). Use `{ctx.prefix}vc` for help.\nError: {error}"))
        elif isinstance(error, commands.CommandInvokeError):
            # Attempt to send the original error if it's user-friendly enough
            original_err_text = str(error.original)
            if isinstance(error.original, discord.Forbidden):
                original_err_text = "I don't have the necessary permissions to do that."
            print(f"[VoiceMaster Invoke Error] in command {ctx.command}: {error.original}")
            await ctx.send(embed=await self._create_branded_embed(ctx, "Command Error", f"An error occurred: {original_err_text}"))
        else:
            print(f"[VoiceMaster Generic Error] in command {ctx.command}: {error}")
            await ctx.send(embed=await self._create_branded_embed(ctx, "Unexpected Error", "An unexpected error occurred. Please try again later."))

async def setup(bot: commands.Bot):
    await bot.add_cog(MinwooLeeVoiceCog(bot))
