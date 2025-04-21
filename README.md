# minwoolee Discord Bot

**minwoolee** is a private Discord bot designed for **server moderation** and **utility tasks**. It provides commands for managing messages, moderating members, and displaying server statistics — all with a clean, consistent embed format that includes the server icon.

> This bot is still a work in progress as new features and commands are actively being developed by the collaborators.

## Features

* **Command Prefix:** `.`
* **Moderation Tools:** Kick, ban, timeout, purge messages, view/manage moderation history.
* **Utility Tools:** Display counts of humans, bots, and total members.
* **Clean Embeds:** All embed messages display the server icon (if available) as a thumbnail for consistent branding.

## Command Reference

**Command**: `<name>`
**Alias**: `<alias if applicable>`
**Description**: `<what the command does>`
**Usage**: `<syntax>`
**Permissions**: `<required Discord permissions>`

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

### `.kick <@user> [reason]`

* **Description:** Kicks a member from the server.
* **Usage:** `.kick @User Spamming`
* **Permissions:** Kick Members

---

### `.ban <@user> [reason]`

* **Description:** Bans a member from the server.
* **Usage:** `.ban @User Inappropriate behavior`
* **Permissions:** Ban Members

---

### `.timeout <@user> <minutes> [reason]`

* **Description:** Temporarily times out a member (max 28 days).
* **Usage:** `.timeout @User 30 Being disruptive`
* **Permissions:** Moderate Members

---

### `.membercount`

* **Description:** Displays the number of human members, bots, and total users in an embed.
* **Usage:** `.membercount`
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

### `.moderationhistory <member>`

* **Alias:** `.modhist`
* **Description:** View moderation actions *performed by* a specific staff member.
* **Usage:** `.moderationhistory @Moderator` or `.modhist @Moderator`
* **Permissions:** Manage Messages

---

## Upcoming Commands

Stay tuned! More moderation and utility commands are in development. This README will be updated accordingly.

## Authors

Developed and maintained by:

* [**soundfont**](https://github.com/soundfont)
* [**Rafan Ahmed**](https://github.com/RafanAhmed)
