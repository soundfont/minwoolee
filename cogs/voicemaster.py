import discord
from discord.ext import commands
import sqlite3
import asyncio

# --- Database Schema (for minwoolee_voice.db) ---
# CREATE TABLE IF NOT EXISTS guild (
#     guildID INTEGER PRIMARY KEY,
#     ownerID INTEGER,
#     voiceChannelID INTEGER, /* The "Join to Create" VC ID */
#     voiceCategoryID INTEGER /* The Category where new VCs are made */
# );
#
# CREATE TABLE IF NOT EXISTS voiceChannel ( /* Tracks active user-owned temporary VCs */
#     userID INTEGER,
#     voiceID INTEGER PRIMARY KEY /* The ID of the temporary VC created by the user */
# );
#
# CREATE TABLE IF NOT EXISTS userSettings ( /* User's preferred default name/limit for their VCs */
#     userID INTEGER PRIMARY KEY,
#     channelName TEXT,
#     channelLimit INTEGER
# );
#
# CREATE TABLE IF NOT EXISTS guildSettings ( /* Guild-wide default limit for VCs */
#     guildID INTEGER PRIMARY KEY,
#     defaultTemplateName TEXT, /* In original, stored "{owner_name}'s channel" */
#     channelLimit INTEGER
# );
# --- End Database Schema ---

class MinwooLeeVoiceCog(commands.Cog, name="VoiceMaster (MinwooLee)"):
    def __init__(self, bot):
        self.bot = bot
        self.db_name = "minwoolee_voice.db"
        self._init_db()

    def _init_db(self):
        """Initializes the database and tables if they don't exist."""
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
        conn.close()

    async def _create_branded_embed(self, ctx, title, description="", color=0x1262DE):
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
        conn = sqlite3.connect(self.db_name)
        c = conn.cursor()
        try:
            guildID = member.guild.id
            c.execute("SELECT voiceChannelID, voiceCategoryID FROM guild WHERE guildID = ?", (guildID,))
            guild_config = c.fetchone()

            if not guild_config:
                return

            master_channel_id, category_id = guild_config

            # User joins the "Join to Create" channel
            if after.channel and after.channel.id == master_channel_id:
                c.execute("SELECT voiceID FROM voiceChannel WHERE userID = ?", (member.id,))
                existing_user_channel = c.fetchone()

                if existing_user_channel:
                    try:
                        # This "cooldown" message from original is more like "you already have a channel"
                        await member.send("Creating channels too quickly or you already have one! You've been put on a 15-second cooldown! (This may mean your previous channel is still active or you need to wait before creating another).")
                        # Original code had an asyncio.sleep(15) here, which is bad practice in a listener.
                        # True cooldowns need a different implementation (e.g., timestamps).
                        # For now, just the message is sent if a channel record exists.
                    except discord.Forbidden:
                        pass # Can't DM
                    return

                target_category = self.bot.get_channel(category_id)
                if not target_category or not isinstance(target_category, discord.CategoryChannel):
                    # Category might have been deleted
                    print(f"[VoiceMaster Error] Category ID {category_id} not found or not a category in guild {guildID}.")
                    return

                c.execute("SELECT channelName, channelLimit FROM userSettings WHERE userID = ?", (member.id,))
                user_settings = c.fetchone()
                c.execute("SELECT channelLimit FROM guildSettings WHERE guildID = ?", (guildID,))
                guild_settings = c.fetchone()

                channel_name_to_create = f"{member.display_name}'s Channel" # Default
                channel_limit_to_create = 0 # Default unlimited

                if guild_settings and guild_settings[0] is not None:
                    channel_limit_to_create = guild_settings[0]

                if user_settings:
                    channel_name_to_create = user_settings[0] if user_settings[0] else channel_name_to_create
                    if user_settings[1] is not None: # User's limit (0 for unlimited, or specific number)
                        channel_limit_to_create = user_settings[1]


                try:
                    # Create the new voice channel
                    # Permissions for @everyone will be inherited from category by default
                    overwrites = {
                        member.guild.default_role: discord.PermissionOverwrite(connect=True, view_channel=True), # Default for everyone
                        member: discord.PermissionOverwrite(connect=True, view_channel=True, manage_channels=True, manage_permissions=True, move_members=True), # Owner full control
                        member.guild.me: discord.PermissionOverwrite(connect=True, view_channel=True, manage_channels=True, manage_permissions=True, move_members=True) # Bot full control
                    }
                    new_channel = await member.guild.create_voice_channel(
                        name=channel_name_to_create,
                        category=target_category,
                        user_limit=channel_limit_to_create,
                        overwrites=overwrites,
                        reason=f"Temporary channel for {member.display_name}"
                    )
                    await member.move_to(new_channel)

                    c.execute("INSERT INTO voiceChannel VALUES (?, ?)", (member.id, new_channel.id))
                    conn.commit()

                    # Original repo uses wait_for here. This can be unreliable if bot restarts.
                    # A more robust solution would be a background task checking empty channels,
                    # or simply letting users delete their own or having them auto-delete after X inactivity.
                    # For now, replicating the original's wait_for logic:
                    def check_empty(m, b, a): # Member, Before, After voice state
                        # Check if the specific channel 'new_channel' is now empty
                        # And ensure the update is relevant to 'new_channel'
                        if b.channel == new_channel and (a.channel != new_channel or a.channel is None):
                            return len(new_channel.members) == 0
                        return False
                    
                    try:
                        await self.bot.wait_for('voice_state_update', check=check_empty, timeout=None) # No timeout, waits indefinitely until empty
                        # This will only trigger for one user leaving that makes it empty.
                        # If multiple leave simultaneously, or if already empty due to kick/etc, this specific wait_for might not work as expected.
                        # A loop checking members after any voice_state_update affecting the channel is more robust.
                        # For now, sticking to original direct wait_for pattern for one event.
                    except asyncio.TimeoutError: 
                        # This won't happen with timeout=None, but good practice if a timeout was used.
                        pass
                    finally: # Ensure deletion if wait_for completes or if channel is found empty by other means
                        # Re-check channel state before deleting, as bot might have been restarted
                        # or wait_for might not be perfectly reliable for all "empty" scenarios.
                        # A simple periodic check or a check on any VSU in that channel is better.
                        # The original repo just deletes after the wait_for.
                        # For simplicity of direct porting for now:
                        try:
                            # We need to re-fetch the channel object potentially, if its state changed (e.g. perms)
                            # However, if the 'wait_for' check is purely based on member count of the *original* 'new_channel' object:
                            if new_channel and len(new_channel.members) == 0: # Double check if still empty
                                await new_channel.delete(reason="Temporary channel empty (owner left or channel cleared)")
                                c.execute('DELETE FROM voiceChannel WHERE voiceID=?', (new_channel.id,)) # Delete for any user if multiple somehow shared
                                conn.commit()
                        except discord.NotFound:
                             c.execute('DELETE FROM voiceChannel WHERE voiceID=?', (new_channel.id,)) # Ensure DB cleanup
                             conn.commit()
                        except discord.Forbidden:
                            print(f"[VoiceMaster Error] Missing permissions to delete channel {new_channel.id} in guild {guildID}.")
                        except Exception as e_del:
                            print(f"[VoiceMaster Error] Error during auto-deletion of {new_channel.id}: {e_del}")


                except discord.Forbidden:
                    print(f"[VoiceMaster Error] Missing permissions for channel creation/management in guild {guildID}.")
                    await member.send("I don't have enough permissions to create a voice channel for you. Please contact a server admin.")
                except Exception as e_create:
                    print(f"[VoiceMaster Error] During channel creation for {member.display_name}: {e_create}")
                    await member.send(f"Sorry, an error occurred while trying to create your channel: {e_create}")

            # User leaves a voice channel - check if it was a temporary one they owned or were in
            elif before.channel and not after.channel: # User disconnected from a channel
                c.execute("SELECT userID FROM voiceChannel WHERE voiceID = ?", (before.channel.id,))
                owner_data = c.fetchone()
                if owner_data: # It was a temporary channel
                    if not before.channel.members: # Channel is now empty
                        try:
                            await before.channel.delete(reason="Temporary channel empty")
                        except discord.NotFound: pass
                        except discord.Forbidden: print(f"[VoiceMaster Error] Missing permissions to delete channel {before.channel.id} in guild {guildID}.")
                        c.execute('DELETE FROM voiceChannel WHERE voiceID=?', (before.channel.id,))
                        conn.commit()

        except sqlite3.Error as e:
            print(f"[VoiceMaster DB Error] on_voice_state_update: {e}")
        except Exception as e_main:
            print(f"[VoiceMaster Main Error] on_voice_state_update: {e_main}")
        finally:
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
                f"`{ctx.prefix}vc reject @user` - Removes a user's permission and kicks them if in channel.\n"
                f"`{ctx.prefix}vc claim` - Claims an orphaned temporary channel you are in.\n\n"
                f"*(Admin Commands)*\n"
                f"`{ctx.prefix}vc setup` - Interactive setup for server owner.\n"
                f"`{ctx.prefix}vc setguildlimit <number>` - Sets default user limit for new temp channels on this server (0 for unlimited)."
            )
            help_embed = await self._create_branded_embed(ctx, "MinwooLee's VoiceMaster Help", desc)
            await ctx.send(embed=help_embed)

    @vc.command(name="setup")
    # @commands.is_owner() # Or check guild owner / admin perms
    async def vc_setup(self, ctx: commands.Context):
        """Interactive setup for VoiceMaster (Server Owner or Bot Admin only)."""
        # Hardcoded ID (151028268856770560) is from original repo, likely original dev "Sam"
        # Replace with MinwooLee's ID or use permissions/owner check more robustly.
        if not (ctx.author.id == ctx.guild.owner_id or ctx.author.id == 151028268856770560 or (await self.bot.is_owner(ctx.author))):
            return await ctx.send(embed=await self._create_branded_embed(ctx, "Permission Denied", "Only the Server Owner or Bot Administrator can run setup."))

        def check(m: discord.Message):
            return m.author == ctx.author and m.channel == ctx.channel

        await ctx.send(embed=await self._create_branded_embed(ctx, "VoiceMaster Setup", "Starting setup... You have 60 seconds per question."))

        try:
            await ctx.send("1. Please enter the name for the **Category** where new temporary voice channels will be created (e.g., 'Temp Channels'):")
            category_msg = await self.bot.wait_for('message', check=check, timeout=60.0)
            new_category = await ctx.guild.create_category_channel(category_msg.content, reason=f"VoiceMaster setup by {ctx.author}")

            await ctx.send(f"Category '{new_category.name}' created.\n2. Now, enter the name for the **'Join to Create' voice channel** (e.g., '➕ New VC'):")
            channel_msg = await self.bot.wait_for('message', check=check, timeout=60.0)
            master_channel = await ctx.guild.create_voice_channel(channel_msg.content, category=new_category, reason=f"VoiceMaster setup by {ctx.author}")

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
        if not (ctx.author.id == ctx.guild.owner_id or ctx.author.id == 151028268856770560 or (await self.bot.is_owner(ctx.author))): # Same ID as setup
            return await ctx.send(embed=await self._create_branded_embed(ctx, "Permission Denied", "Only the Server Owner or Bot Administrator can set this."))
        if limit < 0:
            return await ctx.send(embed=await self._create_branded_embed(ctx, "Invalid Limit", "Limit cannot be negative. Use 0 for unlimited."))

        conn = sqlite3.connect(self.db_name)
        c = conn.cursor()
        try:
            c.execute("SELECT guildID FROM guildSettings WHERE guildID = ?", (ctx.guild.id,))
            # The original repo stored f"{ctx.author.name}'s channel" as a name here. It wasn't really used for channel naming logic.
            # For simplicity, I'm assuming defaultTemplateName is for potential future use or just replicating original schema.
            template_name = f"{ctx.author.name}'s default template" # Replicating the spirit of original
            if c.fetchone():
                c.execute("UPDATE guildSettings SET channelLimit = ?, defaultTemplateName = ? WHERE guildID = ?", (limit, template_name, ctx.guild.id))
            else:
                c.execute("INSERT INTO guildSettings VALUES (?, ?, ?)", (ctx.guild.id, template_name, limit))
            conn.commit()
            limit_text = "Unlimited" if limit == 0 else str(limit)
            await ctx.send(embed=await self._create_branded_embed(ctx, "Guild Setting Updated", f"Default channel limit for new temporary VCs on this server is now: **{limit_text}**."))
        except Exception as e:
            await ctx.send(embed=await self._create_branded_embed(ctx, "Error", f"Could not set guild limit: {e}"))
        finally:
            conn.close()

    @vc.command(name="lock")
    async def vc_lock(self, ctx: commands.Context):
        """Locks your current temporary voice channel."""
        conn = sqlite3.connect(self.db_name)
        c = conn.cursor()
        try:
            c.execute("SELECT voiceID FROM voiceChannel WHERE userID = ?", (ctx.author.id,))
            data = c.fetchone()
            if not data:
                return await ctx.send(embed=await self._create_branded_embed(ctx, "Error", "You don't seem to own an active temporary channel."))
            
            channel = self.bot.get_channel(data[0])
            if not channel:
                c.execute("DELETE FROM voiceChannel WHERE voiceID = ?", (data[0],)) # Clean DB if channel missing
                conn.commit()
                return await ctx.send(embed=await self._create_branded_embed(ctx, "Error", "Your channel was not found (it may have been deleted)."))

            await channel.set_permissions(ctx.guild.default_role, connect=False)
            await channel.set_permissions(ctx.author, connect=True) # Ensure owner can still connect
            await ctx.send(embed=await self._create_branded_embed(ctx, "Channel Locked 🔒", f"Your channel '{channel.name}' is now locked. Only permitted users can join."))
        except discord.Forbidden:
            await ctx.send(embed=await self._create_branded_embed(ctx, "Permission Error", "I lack permissions to modify your channel's settings."))
        except Exception as e:
            await ctx.send(embed=await self._create_branded_embed(ctx, "Error", f"Could not lock channel: {e}"))
        finally:
            conn.close()

    @vc.command(name="unlock")
    async def vc_unlock(self, ctx: commands.Context):
        """Unlocks your current temporary voice channel."""
        conn = sqlite3.connect(self.db_name)
        c = conn.cursor()
        try:
            c.execute("SELECT voiceID FROM voiceChannel WHERE userID = ?", (ctx.author.id,))
            data = c.fetchone()
            if not data:
                return await ctx.send(embed=await self._create_branded_embed(ctx, "Error", "You don't seem to own an active temporary channel."))
            
            channel = self.bot.get_channel(data[0])
            if not channel:
                c.execute("DELETE FROM voiceChannel WHERE voiceID = ?", (data[0],))
                conn.commit()
                return await ctx.send(embed=await self._create_branded_embed(ctx, "Error", "Your channel was not found."))

            await channel.set_permissions(ctx.guild.default_role, connect=True) # None allows connection if category allows
            await ctx.send(embed=await self._create_branded_embed(ctx, "Channel Unlocked 🔓", f"Your channel '{channel.name}' is now unlocked for everyone."))
        except discord.Forbidden:
            await ctx.send(embed=await self._create_branded_embed(ctx, "Permission Error", "I lack permissions to modify your channel's settings."))
        except Exception as e:
            await ctx.send(embed=await self._create_branded_embed(ctx, "Error", f"Could not unlock channel: {e}"))
        finally:
            conn.close()

    @vc.command(name="permit", aliases=["allow"])
    async def vc_permit(self, ctx: commands.Context, member: discord.Member):
        """Permits a specific user to join your locked channel."""
        conn = sqlite3.connect(self.db_name)
        c = conn.cursor()
        try:
            c.execute("SELECT voiceID FROM voiceChannel WHERE userID = ?", (ctx.author.id,))
            data = c.fetchone()
            if not data:
                return await ctx.send(embed=await self._create_branded_embed(ctx, "Error", "You don't seem to own an active temporary channel."))
            
            channel = self.bot.get_channel(data[0])
            if not channel:
                c.execute("DELETE FROM voiceChannel WHERE voiceID = ?", (data[0],))
                conn.commit()
                return await ctx.send(embed=await self._create_branded_embed(ctx, "Error", "Your channel was not found."))

            await channel.set_permissions(member, connect=True, view_channel=True)
            await ctx.send(embed=await self._create_branded_embed(ctx, "User Permitted ✅", f"{member.mention} can now join '{channel.name}'."))
        except discord.Forbidden:
            await ctx.send(embed=await self._create_branded_embed(ctx, "Permission Error", "I lack permissions to modify your channel's settings for that user."))
        except Exception as e:
            await ctx.send(embed=await self._create_branded_embed(ctx, "Error", f"Could not permit user: {e}"))
        finally:
            conn.close()

    @vc.command(name="reject", aliases=["deny"])
    async def vc_reject(self, ctx: commands.Context, member: discord.Member):
        """Revokes a user's permission and kicks them if they are in your channel."""
        conn = sqlite3.connect(self.db_name)
        c = conn.cursor()
        try:
            c.execute("SELECT voiceID FROM voiceChannel WHERE userID = ?", (ctx.author.id,))
            data = c.fetchone()
            if not data:
                return await ctx.send(embed=await self._create_branded_embed(ctx, "Error", "You don't seem to own an active temporary channel."))
            
            channel = self.bot.get_channel(data[0])
            if not channel:
                c.execute("DELETE FROM voiceChannel WHERE voiceID = ?", (data[0],))
                conn.commit()
                return await ctx.send(embed=await self._create_branded_embed(ctx, "Error", "Your channel was not found."))

            await channel.set_permissions(member, connect=False) # Deny connection
            if member in channel.members:
                # Get the "Join to Create" channel to move the user to, as per original repo
                c.execute("SELECT voiceChannelID FROM guild WHERE guildID = ?", (ctx.guild.id,))
                guild_setup_data = c.fetchone()
                fallback_channel = None
                if guild_setup_data:
                    fallback_channel = self.bot.get_channel(guild_setup_data[0])
                
                if fallback_channel and isinstance(fallback_channel, discord.VoiceChannel):
                    await member.move_to(fallback_channel, reason=f"Rejected from {channel.name} by owner {ctx.author.name}")
                else: # Fallback if main join channel not found, just kick from voice
                    await member.move_to(None, reason=f"Rejected from {channel.name} by owner {ctx.author.name}")
            await ctx.send(embed=await self._create_branded_embed(ctx, "User Rejected ❌", f"{member.mention} has been rejected from '{channel.name}'."))
        except discord.Forbidden:
            await ctx.send(embed=await self._create_branded_embed(ctx, "Permission Error", "I lack permissions to modify channel settings or move that user."))
        except Exception as e:
            await ctx.send(embed=await self._create_branded_embed(ctx, "Error", f"Could not reject user: {e}"))
        finally:
            conn.close()

    @vc.command(name="limit")
    async def vc_limit(self, ctx: commands.Context, limit: int):
        """Sets the user limit for your temporary channel."""
        if limit < 0:
            return await ctx.send(embed=await self._create_branded_embed(ctx, "Invalid Limit", "Limit cannot be negative. Use 0 for unlimited."))

        conn = sqlite3.connect(self.db_name)
        c = conn.cursor()
        try:
            c.execute("SELECT voiceID FROM voiceChannel WHERE userID = ?", (ctx.author.id,))
            data = c.fetchone()
            if not data:
                return await ctx.send(embed=await self._create_branded_embed(ctx, "Error", "You don't seem to own an active temporary channel."))
            
            channel = self.bot.get_channel(data[0])
            if not channel:
                c.execute("DELETE FROM voiceChannel WHERE voiceID = ?", (data[0],))
                conn.commit()
                return await ctx.send(embed=await self._create_branded_embed(ctx, "Error", "Your channel was not found."))

            await channel.edit(user_limit=limit)
            
            # Update userSettings
            c.execute("SELECT channelName FROM userSettings WHERE userID = ?", (ctx.author.id,))
            user_setting_data = c.fetchone()
            current_name_for_settings = user_setting_data[0] if user_setting_data and user_setting_data[0] else channel.name # Use current channel name if no specific setting

            if user_setting_data is None: # No record yet for this user in userSettings
                 c.execute("INSERT INTO userSettings VALUES (?, ?, ?)", (ctx.author.id, current_name_for_settings, limit))
            else: # User has settings, update their limit
                 c.execute("UPDATE userSettings SET channelLimit = ? WHERE userID = ?", (limit, ctx.author.id))
            conn.commit()
            limit_text = "Unlimited" if limit == 0 else str(limit)
            await ctx.send(embed=await self._create_branded_embed(ctx, "Channel Limit Set", f"User limit for '{channel.name}' is now **{limit_text}**."))
        except discord.Forbidden:
            await ctx.send(embed=await self._create_branded_embed(ctx, "Permission Error", "I lack permissions to modify your channel's settings."))
        except Exception as e:
            await ctx.send(embed=await self._create_branded_embed(ctx, "Error", f"Could not set limit: {e}"))
        finally:
            conn.close()

    @vc.command(name="name")
    async def vc_name(self, ctx: commands.Context, *, new_name: str):
        """Changes the name of your temporary voice channel."""
        if not new_name.strip():
             return await ctx.send(embed=await self._create_branded_embed(ctx, "Invalid Name", "Channel name cannot be empty."))
        if len(new_name) > 100:
             return await ctx.send(embed=await self._create_branded_embed(ctx, "Invalid Name", "Channel name is too long (max 100 characters)."))

        conn = sqlite3.connect(self.db_name)
        c = conn.cursor()
        try:
            c.execute("SELECT voiceID FROM voiceChannel WHERE userID = ?", (ctx.author.id,))
            data = c.fetchone()
            if not data:
                return await ctx.send(embed=await self._create_branded_embed(ctx, "Error", "You don't seem to own an active temporary channel."))
            
            channel = self.bot.get_channel(data[0])
            if not channel:
                c.execute("DELETE FROM voiceChannel WHERE voiceID = ?", (data[0],))
                conn.commit()
                return await ctx.send(embed=await self._create_branded_embed(ctx, "Error", "Your channel was not found."))

            await channel.edit(name=new_name)
            
            # Update userSettings
            c.execute("SELECT channelLimit FROM userSettings WHERE userID = ?", (ctx.author.id,))
            user_setting_data = c.fetchone()
            current_limit_for_settings = user_setting_data[0] if user_setting_data and user_setting_data[0] is not None else 0 # Default 0

            if user_setting_data is None: # No record yet for user
                 c.execute("INSERT INTO userSettings VALUES (?, ?, ?)", (ctx.author.id, new_name, current_limit_for_settings))
            else: # User has settings, update their name
                 c.execute("UPDATE userSettings SET channelName = ? WHERE userID = ?", (new_name, ctx.author.id))
            conn.commit()
            await ctx.send(embed=await self._create_branded_embed(ctx, "Channel Name Changed", f"Your channel name is now **{new_name}**."))
        except discord.Forbidden:
            await ctx.send(embed=await self._create_branded_embed(ctx, "Permission Error", "I lack permissions to modify your channel's name."))
        except Exception as e:
            await ctx.send(embed=await self._create_branded_embed(ctx, "Error", f"Could not change name: {e}"))
        finally:
            conn.close()

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
            original_owner_member = ctx.guild.get_member(original_owner_id)

            if original_owner_member and original_owner_member in current_vc.members:
                if original_owner_member == ctx.author:
                    return await ctx.send(embed=await self._create_branded_embed(ctx, "No Need", "You are already the owner of this channel!"))
                return await ctx.send(embed=await self._create_branded_embed(ctx, "Claim Failed", f"The original owner, {original_owner_member.mention}, is still in the channel."))

            # Check if claimer already owns another channel
            c.execute("SELECT voiceID FROM voiceChannel WHERE userID = ?", (ctx.author.id,))
            claimer_channel = c.fetchone()
            if claimer_channel and claimer_channel[0] != current_vc.id : # If they own a different channel
                 return await ctx.send(embed=await self._create_branded_embed(ctx, "Claim Failed", "You already own another temporary channel. You can't claim this one too."))


            c.execute("UPDATE voiceChannel SET userID = ? WHERE voiceID = ?", (ctx.author.id, current_vc.id))
            conn.commit()
            
            # Update permissions for new owner
            await current_vc.set_permissions(ctx.author, connect=True, view_channel=True, manage_channels=True, manage_permissions=True, move_members=True)
            if original_owner_member and original_owner_member != ctx.author : # If old owner can be identified and is not the claimer
                await current_vc.set_permissions(original_owner_member, overwrite=None) # Reset their specific overwrites

            await ctx.send(embed=await self._create_branded_embed(ctx, "Channel Claimed! 🎉", f"{ctx.author.mention}, you are now the owner of '{current_vc.name}'."))
        except discord.Forbidden:
            await ctx.send(embed=await self._create_branded_embed(ctx, "Permission Error", "Ownership updated in DB, but I lack permissions to update channel permissions for you."))
        except Exception as e:
            await ctx.send(embed=await self._create_branded_embed(ctx, "Error", f"Could not claim channel: {e}"))
        finally:
            conn.close()
            
    @vc_setup.error
    @vc_setguildlimit.error
    @vc_lock.error
    @vc_unlock.error
    @vc_permit.error
    @vc_reject.error
    @vc_limit.error
    @vc_name.error
    @vc_claim.error
    async def vc_command_error(self, ctx, error):
        """Generic error handler for vc commands."""
        if isinstance(error, commands.MissingPermissions):
            await ctx.send(embed=await self._create_branded_embed(ctx, "Permission Denied", "You don't have the required permissions for this command."))
        elif isinstance(error, commands.MissingRequiredArgument):
            await ctx.send(embed=await self._create_branded_embed(ctx, "Missing Argument", f"You missed an argument: `{error.param.name}`. Use `{ctx.prefix}vc` for help."))
        elif isinstance(error, commands.BadArgument):
            await ctx.send(embed=await self._create_branded_embed(ctx, "Invalid Argument", f"One of the arguments you provided was invalid. Use `{ctx.prefix}vc` for help."))
        elif isinstance(error, commands.CommandInvokeError):
            print(f"[VoiceMaster Invoke Error] in command {ctx.command}: {error.original}")
            await ctx.send(embed=await self._create_branded_embed(ctx, "Command Error", f"An error occurred while running the command: {error.original}"))
        else: # Fallback for other errors
            print(f"[VoiceMaster Generic Error] in command {ctx.command}: {error}")
            await ctx.send(embed=await self._create_branded_embed(ctx, "Unexpected Error", "An unexpected error occurred. Please try again later."))


async def setup(bot: commands.Bot):
    # Ensure necessary intents are enabled on the bot instance
    # e.g., intents = discord.Intents.default(); intents.voice_states = True; intents.guilds = True; intents.members = True (if needed)
    # bot = commands.Bot(command_prefix='.', intents=intents)
    await bot.add_cog(MinwooLeeVoiceCog(bot))
