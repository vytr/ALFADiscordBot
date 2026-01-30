# GuildBrew - Discord Bot

Professional Discord bot for server statistics, moderation, and management.

[![Python](https://img.shields.io/badge/Python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![Discord.py](https://img.shields.io/badge/discord.py-2.4.0+-blue.svg)](https://github.com/Rapptz/discord.py)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

## 🌟 Features

### 📊 Activity Tracking
- **Message Statistics**: Track user messages with daily/weekly/monthly breakdowns
- **Voice Tracking**: Monitor time spent in voice channels
- **Leaderboards**: View top active members by messages or voice time
- **Inactive Users**: Identify members with no activity over specified periods
- **Export**: Download statistics as CSV/XLSX files

### 🎮 Mini-Games
- **Drink Game**: Fun drinking game with statistics tracking
- **Duels**: Challenge other members to random duels
- **Leaderboards**: Track top players and their stats

### 🎛️ Interactive Panel
- **Slash Commands**: Modern Discord interactions with `/panel`
- **Button Navigation**: Easy-to-use interface with buttons and menus
- **Whitelist Management**: Control access to bot commands
- **Role Management**: Create and assign roles with custom permissions

## 📦 Installation

### Prerequisites
- Python 3.8 or higher
- pip (Python package manager)
- Discord Bot Token ([Get one here](https://discord.com/developers/applications))

### 1. Clone Repository
```bash
git clone https://github.com/vytr/guildbrew.app.git
cd guildbrew.app
```

### 2. Create Virtual Environment
```bash
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

### 3. Install Dependencies
```bash
pip install -r requirements.txt
```

### 4. Configure Environment
```bash
cp .env.example .env
nano .env  # Edit with your favorite editor
```

**Required configuration in `.env`:**
```env
DISCORD_TOKEN=your_bot_token_here
DISCORD_PREFIX=!
```

### 5. Enable Discord Intents

1. Go to [Discord Developer Portal](https://discord.com/developers/applications)
2. Select your bot application
3. Navigate to **Bot** section
4. Enable **Privileged Gateway Intents**:
   - ✅ **MESSAGE CONTENT INTENT**
   - ✅ **SERVER MEMBERS INTENT**
   - ✅ **PRESENCE INTENT** (optional)
5. Save changes

### 6. Invite Bot to Server

Generate invite URL with required permissions:

```
https://discord.com/api/oauth2/authorize?client_id=YOUR_BOT_CLIENT_ID&permissions=8&scope=bot%20applications.commands
```

Replace `YOUR_BOT_CLIENT_ID` with your bot's Client ID from Developer Portal.

### 7. Run Bot

```bash
# Make sure virtual environment is activated
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Start the bot
python bot.py
```

```

## 🎯 Usage

### Basic Commands

#### Statistics
```bash
!gb_stats [@user] [7/14/30]              # View user statistics
!gb_leaderboard [7/14/30]                # Server leaderboard
!gb_inactive [7/14/30] [@role]           # Find inactive members
!gb_summary [7/14/30] [@role]            # Activity summary
!gb_export [7/14/30] [@role]             # Export to CSV
```

#### Polls
```bash
!gb_poll_export_detailed <message_id> [7/14/30]  # Export poll with stats
```

**How to get poll message ID:**
- Right-click on poll → "Copy Message Link"
- Or enable Developer Mode → Right-click → "Copy ID"

#### Warnings(TEST FEATURE)
```bash
!warn @user <reason>                     # Issue warning
!unwarn <warning_id> [reason]            # Remove warning
!warnings [@user]                        # Check warnings
!warnings_list                           # List all users with warnings
!warnings_active                         # Active warnings statistics
```

#### Whitelist (Admin Only)
```bash
!gb_whitelist_add @user                  # Add to whitelist
!gb_whitelist_remove @user               # Remove from whitelist
!gb_whitelist_list                       # Show whitelist
```

#### Games
```bash
!drink                                   # Drink game (1 hour cooldown)
!drink_stats [@user]                     # Drink statistics
!drink_top [limit]                       # Top drinkers
!gb_duel @user                           # Challenge to duel
```

### Slash Commands

```bash
/panel                                   # Open interactive control panel
```

## 🔧 Configuration

### Database

Bot uses SQLite database:
- `bot_database.db` - Main database (stats, whitelist, warnings)

**Automatic cleanup:** Data older than 30 days is automatically removed. Can be turned off for each server

### Customization

Edit `config.py` for bot settings:
```python
DISCORD_PREFIX = '!'  # Command prefix
```

### Voice Session Tracking

**IMPORTANT:** The bot automatically:
- Starts voice sessions when users join voice channels
- Ends sessions when users leave
- Recovers active sessions on bot restart
- Closes hanging sessions (>24h) automatically

## 🐛 Troubleshooting

### Commands Not Working

**Symptom:** Bot doesn't respond to commands

**Solution:**
1. Check prefix in `.env` matches your commands
2. Verify bot has "Send Messages" permission
3. Check you're in whitelist or have Administrator role
4. View console for error messages

### Voice Time Not Recording

**Symptom:** Voice statistics show 0 hours

**Solution:**
1. Check "Server Members Intent" is enabled
2. Verify bot can see voice channels
3. Check database for hanging sessions: `!gb_voice_debug` (admin only)
4. Restart bot to close hanging sessions

### High Memory Usage

**Symptom:** Bot uses excessive RAM

**Solution:**
```bash
# Run database cleanup
# (automatic every 24h, but can trigger manually by restarting)
python bot.py
```

## 📊 Architecture

```
guildbrew/
├── bot.py                 # Main bot entry point
├── config.py              # Configuration
├── database.py            # Database operations
├── utils.py               # Helper functions
├── requirements.txt       # Python dependencies
├── .env.example          # Environment template
├── cogs/                 # Bot modules (cogs)
│   ├── api.py           # REST API (Flask)
│   ├── basic.py         # Basic commands
│   ├── drink_game.py    # Drink game
│   ├── help.py          # Help system
│   ├── native_polls.py  # Poll tracking
│   ├── panel.py         # Interactive panel
│   ├── role_manager.py  # Role management
│   ├── stats.py         # Statistics tracking
│   ├── user_panel.py    # User panel
│   ├── warnings.py      # Warning system
│   └── whitelist.py     # Whitelist management
└── views/               # UI components
    └── whitelist_view.py
```

## 🔐 Security

- ✅ Bot token stored in `.env` (not committed to git)
- ✅ Whitelist system restricts command access
- ✅ Administrator-only commands for sensitive operations
- ✅ Rate limiting on API endpoints (Gunicorn workers)
- ✅ Input validation on all commands

**Never share your `.env` file or bot token!**

## 🚀 Production Deployment

### Using systemd (Linux)

Create service file:
```bash
sudo nano /etc/systemd/system/guildbrew.service
```

```ini
[Unit]
Description=GuildBrew Discord Bot
After=network.target

[Service]
Type=simple
User=YOUR_USER
WorkingDirectory=/path/to/guildbrew
Environment="PATH=/path/to/guildbrew/venv/bin"
ExecStart=/path/to/guildbrew/venv/bin/python bot.py
Restart=on-failure
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Enable and start:
```bash
sudo systemctl daemon-reload
sudo systemctl enable guildbrew
sudo systemctl start guildbrew
sudo systemctl status guildbrew
```

### Automatic Restart Script

If you have multiple services:
```bash
#!/bin/bash
# restart_services.sh

SERVICES=("guildbrew.service")
INTERVAL=5

for service in "${SERVICES[@]}"; do
    echo "⏳ Restarting: $service"
    sudo systemctl restart "$service"
    sleep $INTERVAL
done

echo "✅ All services restarted"
```

## 📝 Contributing

1. Fork the repository
2. Create feature branch: `git checkout -b feature/amazing-feature`
3. Commit changes: `git commit -m 'Add amazing feature'`
4. Push to branch: `git push origin feature/amazing-feature`
5. Open Pull Request

## 📜 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🙏 Support

- **Documentation:** [GitHub Wiki](https://github.com/vytr/guildbrew/wiki)
- **Issues:** [GitHub Issues](https://github.com/vytr/guildbrew/issues)
- **Donate:** [Buy Me a Coffee](https://buymeacoffee.com/vytr94a)

## 🏆 Credits

- Built with [discord.py](https://github.com/Rapptz/discord.py)
- Database: SQLite3
- API Server: Flask
- UI: Discord Interactions

---

**Made with ❤️ by the GuildBrew team**
