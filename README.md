# minwoolee Discord Bot

**minwoolee** is a private Discord bot designed for **server moderation** and **utility tasks**. It provides commands for managing messages, moderating members, and displaying server statistics — all with a clean, consistent embed format that includes the server icon.

> This bot is still a work in progress as new features and commands are actively being developed by the collaborators.

## Features

* **Command Prefix:** `.`
* **Moderation Tools:** Kick, ban, unban, timeout, untimeout, mute, unmute, purge messages, view/manage moderation history, list bans, clear bot messages.
* **Utility Tools:** Display counts of humans, bots, and total members, AFK status, snipe deleted messages.
* **Clean Embeds:** All embed messages display the server icon (if available) as a thumbnail for consistent branding.

## Command Reference

**Command**: `<name>`
**Alias**: `<alias if applicable>`
**Description**: `<what the command does>`
**Usage**: `<syntax>`
**Permissions**: `<required Discord permissions>`

---

### `.afk [reason|off]`

* **Description:** Sets your status to AFK (Away From Keyboard). Typing `off` as the reason will remove your AFK status.
* **Usage:** `.afk Taking a break` or `.afk off`
* **Permissions:** None

---

### `.ban <@user> [reason]`

* **Description:** Bans a member from the server.
* **Usage:** `.ban @User Inappropriate behavior`
* **Permissions:** Ban Members

---

### `.bans`

* **Description:** Displays a paginated list of all users currently banned from the server.
* **Usage:** `.bans`
* **Permissions:** Ban Members

---

### `.bc [limit]`

* **Alias:** `.botclear`
* **Description:** Clears bot commands and bot messages from the current channel. Scans up to 'limit' recent messages (default 100).
* **Usage:** `.bc 50` or `.botclear 25`
* **Permissions:** Manage Messages

---

### `.help`

* **Description:** Provides a link to the bot's documentation.
* **Usage:** `.help`
* **Permissions:** None

---

### `.history <member>`

* **Description:** View *all* recorded punishments *against* a specific member. (Base command)
* **Usage:** `.history @User`
* **Permissions:** Manage Messages

---

### `.history removeall <member>`

* **Description:** Remove *all* history entries for a specific member.
* **Usage:** `.history removeall @User`
* **Permissions:** Administrator

---

### `.history remove <member> <case_id>`

* **Description:** Remove a *specific* punishment by Case ID for a member.
* **Usage:** `.history remove @User 123`
* **Permissions:** Manage Messages

---

### `.history view <case_id>`

* **Description:** View details for a specific Case ID.
* **Usage:** `.history view 123`
* **Permissions:** Manage Messages

---

### `.kick <@user> [reason]`

* **Description:** Kicks a member from the server.
* **Usage:** `.kick @User Spamming`
* **Permissions:** Kick Members

---

### `.membercount`

* **Alias:** `.mc`
* **Description:** Displays the number of human members, bots, and total users in an embed.
* **Usage:** `.membercount`
* **Permissions:** None

---

### `.moderationhistory <member>`

* **Alias:** `.mh`
* **Description:** View moderation actions *performed by* a specific staff member.
* **Usage:** `.moderationhistory @Moderator` or `.mh @Moderator`
* **Permissions:** Manage Messages

---

### `.mute <@member/ID> [reason]`

* **Description:** Assigns a "Muted" role to a member, restricting them from sending images and adding reactions.
* **Usage:** `.mute @User Repeatedly breaking rules`
* **Permissions:** Moderate Members

---

### `.mutedlist`

* **Description:** Displays a list of members who currently have the "Muted" role.
* **Usage:** `.mutedlist`
* **Permissions:** Manage Messages

---

### `.ping`

* **Description:** Shows the bot's latency in milliseconds.
* **Usage:** `.ping`
* **Permissions:** None

---

### `.purge <amount>`

* **Description:** Deletes a specified number of messages (1–100).
* **Usage:** `.purge 25`
* **Permissions:** Manage Messages

---

### `.snipe [index]`

* **Alias:** `.s`
* **Description:** Shows the last deleted message(s) in the channel (up to 10, within the last 2 hours). Use an index to view older snipes (e.g., `.snipe 2` for the second to last).
* **Usage:** `.snipe` or `.s 3`
* **Permissions:** None

---

### `.timeout <@user> <duration> [reason]`

* **Alias:** `.to`
* **Description:** Temporarily times out a member. Duration can be specified in weeks (w), days (d), hours (h), minutes (m), and seconds (s) (e.g., "1w2d3h4m5s", "30m", "1d 12h"). Max 28 days.
* **Usage:** `.timeout @User 30m Being disruptive` or `.to @User "1d 12h" Repeated warnings`
* **Permissions:** Moderate Members

---

### `.unban <user> [reason]`

* **Description:** Unbans a user from the server.
* **Usage:** `.unban UserID#1234 Appealed successfully` or `.unban @User Reason for unban`
* **Permissions:** Ban Members

---

### `.unmute <@member/ID> [reason]`

* **Description:** Removes the "Muted" role from a member.
* **Usage:** `.unmute @User Mute expired`
* **Permissions:** Moderate Members

---

### `.untimeout <member> [reason]`

* **Alias:** `.uto`
* **Description:** Removes an active timeout from a member.
* **Usage:** `.untimeout @User Appealed` or `.uto @User Behavior improved`
* **Permissions:** Moderate Members

---

## Upcoming Commands

Stay tuned! More moderation and utility commands are in development. This README will be updated accordingly.

## Authors

Developed and maintained by:

* [**soundfont**](https://github.com/soundfont)
* [**Rafan Ahmed**](https://github.com/RafanAhmed)
