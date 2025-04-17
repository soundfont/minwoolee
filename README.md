minwoolee is a private Discord bot designed for server moderation and utility tasks.It provides commands for managing messages, moderating members, and displaying server statistics,with a clean embed format featuring the server icon.
Features

Command Prefix: .
Moderation: Purge messages, kick, ban, or timeout members.
Utility: Display human, bot, and total member counts in an embed.
Custom Embeds: All embeds include the server icon as a thumbnail (if available).

Formatting
-

Command
-
Alias  
Description  
Usage  
Required Permissions  



ping
-
Shows the bot's latency in milliseconds.  
.ping  
None


purge
-
Deletes a specified number of messages (1–100).  
.purge <amount>  
Manage Messages  


kick
-
Kicks a member from the server.  
.kick <@user> [reason]  
Kick Members  


ban
-
Bans a member from the server.  
.ban <@user> [reason]  
Ban Members  


timeout
to  
Times out a member for a specified duration (max 28 days).  
.timeout <@user> <minutes> [reason]  
Moderate Members  


membercount
mc  
Displays human, bot, and total member counts in the server.
.membercount  
None (Embed Links for bot)  
