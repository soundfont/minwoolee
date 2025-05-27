# ... (channel_limit_to_create setup) ...
                try:
                    overwrites = {
                        member.guild.default_role: discord.PermissionOverwrite(connect=True, view_channel=True),
                        member: discord.PermissionOverwrite(connect=True, view_channel=True, manage_channels=True, manage_permissions=True, move_members=True),
                        member.guild.me: discord.PermissionOverwrite(connect=True, view_channel=True, manage_channels=True, manage_permissions=True, move_members=True)
                    }
                    print(f"[VoiceMaster Debug] About to create channel '{channel_name_to_create}' with limit {channel_limit_to_create} for {member.display_name} ({member.id}) in category {target_category.id}") # DEBUG
                    new_channel = await member.guild.create_voice_channel(
                        name=channel_name_to_create,
                        category=target_category,
                        user_limit=channel_limit_to_create,
                        overwrites=overwrites,
                        reason=f"Temporary channel for {member.display_name}"
                    )
                    print(f"[VoiceMaster Debug] Channel '{new_channel.name}' ({new_channel.id}) CREATED for {member.display_name}.") # DEBUG

                    try:
                        print(f"[VoiceMaster Debug] Attempting to move {member.display_name} to {new_channel.name} ({new_channel.id}).") # DEBUG
                        await member.move_to(new_channel)
                        print(f"[VoiceMaster Debug] Successfully moved {member.display_name} to {new_channel.name}.") # DEBUG
                    except discord.Forbidden as e_move_forbidden:
                        print(f"[VoiceMaster Error] FORBIDDEN to move {member.display_name} to {new_channel.name}: {e_move_forbidden}")
                        await member.send(f"I created your channel '{new_channel.name}', but I don't have permission to move you to it. Please check my 'Move Members' permission.")
                        # You might want to delete new_channel here if the move fails catastrophically
                        # await new_channel.delete(reason="Failed to move owner after creation")
                    except discord.HTTPException as e_move_http:
                        print(f"[VoiceMaster Error] HTTP Exception while moving {member.display_name} to {new_channel.name}: {e_move_http}")
                        await member.send(f"I created your channel '{new_channel.name}', but an API error occurred while trying to move you.")
                    except Exception as e_move_other:
                        print(f"[VoiceMaster Error] UNKNOWN Exception while moving {member.display_name} to {new_channel.name}: {e_move_other}")
                        await member.send(f"I created your channel '{new_channel.name}', but an unexpected error occurred moving you.")

                    c.execute("INSERT INTO voiceChannel VALUES (?, ?)", (member.id, new_channel.id))
                    conn.commit()
                    print(f"[VoiceMaster Debug] DB record inserted for {member.display_name}, channel {new_channel.id}.") # DEBUG

                    # ... (rest of the channel deletion logic with wait_for) ...

                except discord.Forbidden as e_create_forbidden:
                    print(f"[VoiceMaster Error] FORBIDDEN during channel CREATION for {member.display_name} in guild {guildID}: {e_create_forbidden}")
                    try:
                        await member.send("I don't have enough permissions to create a voice channel for you. Please contact a server admin (I need 'Manage Channels').")
                    except discord.Forbidden: pass # Can't DM
                except Exception as e_create:
                    print(f"[VoiceMaster Error] During channel CREATION for {member.display_name}: {e_create}")
                    try:
                        await member.send(f"Sorry, an error occurred while trying to create your channel: {e_create}")
                    except discord.Forbidden: pass # Can't DM
