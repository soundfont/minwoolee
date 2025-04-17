minwoolee is a private Discord bot designed for server moderation and utility tasks. It provides commands for managing messages, moderating members, and displaying server statistics, with a clean embed format featuring the server icon.
Features

Command Prefix: .

Commands



Command
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
Times out a member for a specified duration (in minutes, max 28 days).
.timeout <@user> <minutes> [reason]
Moderate Members


membercount
mc
Displays human, bot, and total member counts in an embed with server icon thumbnail.
.membercount
None (Embed Links for bot)


Troubleshooting

Commands not responding:
Ensure the bot has View Channels, Send Messages, and Embed Links permissions in the channel (Channel Settings > Permissions).
For .kick, .ban, or .timeout, verify the bot’s role has Kick Members, Ban Members, or Moderate Members permissions and is above the target member’s role (Server Settings > Roles).
Check Heroku logs for errors: heroku logs --tail --app your-app-name.


Moderation commands failing:
Reinvite the bot with required permissions (Kick Members, Ban Members, Moderate Members) via the Discord Developer Portal.
Ensure Message Content Intent is enabled in the Developer Portal (Bot > Privileged Gateway Intents).



