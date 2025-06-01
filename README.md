# minwoolee Discord Bot

**minwoolee** is a comprehensive Discord bot featuring advanced **moderation tools**, **utility functions**, **music playback**, **voice channel management**, and **entertainment features**. Built with Python and discord.py, it provides a clean, consistent interface with server-branded embeds and robust database integration.

> **Active Development**: This bot is continuously evolving with new features and improvements being added regularly by our development team.

## Key Features

### 🛡️ **Moderation & Safety**
- **Role-based punishments** with automatic logging
- **Comprehensive member management** (kick, ban, timeout, mute)
- **Message management** with smart purging and bot cleanup
- **Detailed moderation history** with case tracking and removal
- **Auto-role assignment** for new members
- **Reaction statistics** tracking and leaderboards

### 🎵 **Music & Entertainment**
- **High-quality music playback** with YouTube support
- **Last.fm integration** with collage generation
- **Message sniping** for recently deleted content
- **AFK status management** with duration tracking
- **Contextual reactions** for polls and votes

### 🔊 **Voice Channel Management**
- **Temporary voice channels** with automatic creation/deletion
- **Channel ownership system** with permission management
- **Customizable channel names and limits**
- **Channel claiming** for orphaned rooms

### 📊 **Utility & Information**
- **Server statistics** and member counts
- **Flexible embed system** with server branding
- **Ping monitoring** and status checking
- **Comprehensive help system**

---

## Getting Started

### Prerequisites
- Python 3.8+
- Discord.py 2.0+
- PostgreSQL database (for persistent features)
- Required API keys (Last.fm, YouTube/music services)

### Bot Permissions Required
- **Manage Channels** (for voice management)
- **Manage Roles** (for muting and auto-roles)
- **Manage Messages** (for purging and moderation)
- **Ban Members** & **Kick Members** (for moderation)
- **Moderate Members** (for timeouts)
- **Add Reactions** (for polls and reactions)
- **Connect** & **Speak** (for music features)

---

## Command Reference

### 🛡️ **Moderation Commands**

| Command | Description | Usage | Permissions |
|---------|-------------|-------|-------------|
| `.ban <@user> [reason]` | Bans a member from the server | `.ban @User Inappropriate behavior` | Ban Members |
| `.kick <@user> [reason]` | Kicks a member from the server | `.kick @User Spamming` | Kick Members |
| `.timeout <@user> <duration> [reason]` | Times out a member temporarily | `.timeout @User 30m Being disruptive` | Moderate Members |
| `.untimeout <@user> [reason]` | Removes an active timeout | `.untimeout @User Appealed` | Moderate Members |
| `.mute <@user> [reason]` | Restricts media/reactions with role | `.mute @User Repeatedly breaking rules` | Moderate Members |
| `.unmute <@user> [reason]` | Removes media restrictions | `.unmute @User Mute expired` | Moderate Members |
| `.unban <user> [reason]` | Unbans a user from the server | `.unban UserID#1234 Appealed successfully` | Ban Members |

**Duration Formats**: `30m`, `1d`, `2h 30m`, `1w2d3h4m5s` (max 28 days)

### 📊 **Moderation History & Lists**

| Command | Alias | Description | Usage | Permissions |
|---------|-------|-------------|-------|-------------|
| `.history <@member>` | | View all punishments against a member | `.history @User` | Manage Messages |
| `.history remove <@member> <case_id>` | | Remove specific punishment record | `.history remove @User 123` | Manage Messages |
| `.history removeall <@member>` | | Remove all history for a member | `.history removeall @User` | Administrator |
| `.history view <case_id>` | | View details of specific case | `.history view 123` | Manage Messages |
| `.moderationhistory <@member>` | `.mh` | View actions performed BY a moderator | `.mh @Moderator` | Manage Messages |
| `.bans` | | Display paginated list of banned users | `.bans` | Ban Members |
| `.mutedlist` | | Show members with muted role | `.mutedlist` | Manage Messages |

### 🧹 **Message Management**

| Command | Alias | Description | Usage | Permissions |
|---------|-------|-------------|-------|-------------|
| `.purge <amount>` | `.clear` | Delete specified number of messages | `.purge 25` | Manage Messages |
| `.purge <@user> <amount>` | | Delete messages from specific user | `.purge @User 50` | Manage Messages |
| `.bc [limit]` | `.botclear` | Clear bot commands and responses | `.bc 50` | Manage Messages |
| `.snipe [index]` | `.s` | Show recently deleted messages | `.snipe` or `.s 3` | None |

### ⚙️ **Server Management**

| Command | Description | Usage | Permissions |
|---------|-------------|-------|-------------|
| `.autorole set <@role>` | Set auto-role for new members | `.autorole set @Member` | Manage Roles |
| `.autorole remove` | Disable auto-role assignment | `.autorole remove` | Manage Roles |
| `.autorole status` | View current auto-role setting | `.autorole status` | Manage Roles |

### 🎵 **Music Commands**

| Command | Alias | Description | Usage | Permissions |
|---------|-------|-------------|-------|-------------|
| `.play <query>` | `.p` | Play music from YouTube or URL | `.play Never Gonna Give You Up` | None |
| `.join` | `.connect`, `.j` | Join your voice channel | `.join` | None |
| `.leave` | `.disconnect`, `.dc`, `.stop` | Leave voice channel and stop music | `.leave` | None |

### 🔊 **Voice Channel Management**

| Command | Description | Usage | Permissions |
|---------|-------------|-------|-------------|
| `.vc setup` | Interactive VoiceMaster setup | `.vc setup` | Server Owner |
| `.vc lock` | Lock your temporary channel | `.vc lock` | Channel Owner |
| `.vc unlock` | Unlock your temporary channel | `.vc unlock` | Channel Owner |
| `.vc name <name>` | Rename your channel | `.vc name Study Room` | Channel Owner |
| `.vc limit <number>` | Set user limit (0 = unlimited) | `.vc limit 5` | Channel Owner |
| `.vc allow <@user>` | Allow user to join locked channel | `.vc allow @Friend` | Channel Owner |
| `.vc reject <@user>` | Remove user permission and kick | `.vc reject @User` | Channel Owner |
| `.vc claim` | Claim an orphaned temp channel | `.vc claim` | None |

### 🎯 **Entertainment & Social**

| Command | Alias | Description | Usage | Permissions |
|---------|-------|-------------|-------|-------------|
| `.afk [reason\|off]` | | Set AFK status or turn off | `.afk Taking a break` | None |
| `.fm [user]` | `.lfm` | Show Last.fm now playing | `.fm @User` | None |
| `.fm set <username>` | | Link your Last.fm account | `.fm set MyUsername` | None |
| `.fm topartists [user] [period] [limit]` | `.fm ta` | Show top artists | `.fm ta @User 7d 10` | None |
| `.fm collage [user] [grid] [period]` | `.fm col` | Generate album art collage | `.fm col 3x3 1m` | None |
| `.topreactions [user]` | `.rstats` | Show top reactions received | `.rstats @User` | None |
| `.topreactions leaderboard <emoji>` | | Emoji reaction leaderboard | `.rstats leaderboard 🎉` | None |

### 📊 **Information & Utility**

| Command | Alias | Description | Usage | Permissions |
|---------|-------|-------------|-------|-------------|
| `.membercount` | `.mc` | Display server member statistics | `.membercount` | None |
| `.ping` | | Show bot latency | `.ping` | None |
| `.help` | | Link to documentation | `.help` | None |

---

## 🎛️ **Advanced Features**

### **Moderation History System**
- **Persistent logging** of all moderation actions
- **Case ID tracking** for easy reference and removal
- **Moderator attribution** with timestamps
- **Paginated history viewing** with navigation controls

### **Smart Auto-Role Management**
- **Database-backed** role assignment for new members
- **Automatic permission verification** and channel overwrites
- **Role hierarchy validation** to prevent permission issues

### **Voice Channel Automation**
- **Join-to-create** temporary voice channels
- **Automatic cleanup** when channels become empty
- **Ownership transfer** and claiming system
- **Customizable defaults** per user and server

### **Music Integration**
- **YouTube search** and direct URL support
- **Automatic fallback** to YouTube for non-YouTube sources
- **Volume control** and audio filtering
- **Connection management** with auto-join

### **Last.fm Integration**
- **Global account linking** across all servers
- **Album art collages** with customizable grids
- **Multiple time periods** for statistics
- **Rich embed formatting** with clickable links

### **Reaction Statistics**
- **Real-time tracking** of all reactions
- **Automatic cleanup** of deleted messages
- **Top reaction leaderboards** for specific emojis
- **Time-based filtering** (24h, 7d, all time)

### **Contextual Reactions**
The bot automatically adds poll reactions to messages containing:
- **`y/n`** → Adds ⬆️⬇️ (yes/no voting)
- **`v/s`** → Adds ⬅️➡️ (versus/comparison)

---

## 🗄️ **Database Integration**

### **Supported Features**
- **PostgreSQL** for production deployments
- **SQLite** for voice channel management
- **Automatic schema creation** and migration
- **Connection pooling** and error handling

### **Stored Data**
- Moderation history and case tracking
- Auto-role configurations per server
- Last.fm account linkages (global)
- Voice channel ownership and settings
- Reaction statistics and leaderboards
- User preferences and settings

---

### **Bot Setup Checklist**
1. ✅ **Invite bot** with required permissions
2. ✅ **Run** `.autorole set @role` for new member management
3. ✅ **Run** `.vc setup` for voice channel features
4. ✅ **Configure** moderation roles and hierarchy
5. ✅ **Test** key features (ban, music, voice creation)

---

## 🎨 **Embed System**

All bot responses use **consistent, branded embeds** featuring:
- **Server icon** as embed author thumbnail
- **Requester information** in footer with avatar
- **Color-coded responses** (green=success, red=error, etc.)
- **Timestamp information** for all actions
- **Proper formatting** with fields and descriptions

---

## 🔄 **Automatic Features**

### **Background Tasks**
- **Cleanup expired** reaction statistics (every 30 minutes)
- **Remove orphaned** voice channels when empty
- **Validate auto-role** permissions on member join
- **Archive old** moderation logs (configurable)

### **Event Listeners**
- **Member join/leave** handling for auto-roles
- **Message deletion** tracking for snipe feature
- **Voice state changes** for channel management
- **Reaction tracking** for statistics
- **AFK status** monitoring and notifications

---

## 👥 **Development Team**

**Core Developers:**
- [**soundfont**](https://github.com/soundfont) - Lead Developer
- [**Rafan Ahmed**](https://github.com/RafanAhmed) - Core Contributor

**Contributing:**
We welcome contributions! Please check our issues page for features in development or bug reports.

---

## 📜 **Version History**

### **Current Version**: 2.0
- ✨ **Full PostgreSQL integration** for all persistent features
- 🎵 **Enhanced music system** with improved YouTube support
- 🔊 **Complete voice channel management** with MinwooLee VoiceMaster
- 📊 **Advanced reaction statistics** and leaderboards
- 🎨 **Revamped embed system** with consistent branding
- 🛡️ **Comprehensive moderation** with detailed history tracking

### **Upcoming Features** (In Development)
- 📈 **Advanced server analytics** and insights
- 🎮 **Game integration** and activity tracking
- 🤖 **Custom command creation** for server administrators
- 🌐 **Multi-language support** for international servers
- 📱 **Mobile-optimized** command responses

---

## 📞 **Support & Links**

- **Documentation**: [GitHub Repository](https://github.com/soundfont/minwoolee-public)
- **Issues**: Report bugs or request features on our GitHub issues page
- **Discord**: Contact the development team for technical support

---
