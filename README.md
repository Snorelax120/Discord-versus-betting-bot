# 🎲 Discord Betting Bot

A feature-rich Discord bot for community betting using virtual points. Perfect for gaming communities, sports betting, and interactive engagement!

## ✨ Features

### 🎯 **Betting System**
- **Interactive Bet Creation** - Easy-to-use modals for creating custom bets
- **Quick Yes/No Bets** - Fast bet creation for simple predictions
- **Multi-Option Betting** - Support for multiple outcome bets
- **Smart Betting UI** - Discord buttons for seamless bet placement
- **Real-time Bet Tracking** - Live updates on bet pools and participants

### 💰 **Economy System**
- **Virtual Points** - Safe betting with virtual currency
- **Daily Bonuses** - Keep users engaged with daily rewards
- **Emergency Bailouts** - Help for users who run out of points
- **Balance Management** - Track earnings, losses, and net profit
- **Leaderboards** - Competition and ranking system

### 🛡️ **Admin Controls**
- **Interactive Resolution** - Button-based bet resolution interface
- **Permission System** - Role-based access control
- **User Management** - Balance adjustments and user statistics
- **Statistics Refresh** - Bulk updates for all user data
- **Integrated Admin UI** - Resolve bets directly from bet lists

### 📊 **Statistics & Analytics**
- **Detailed User Stats** - Win rates, profit/loss tracking
- **Betting History** - Complete audit trail of all bets
- **Real-time Calculations** - Accurate statistics from live data
- **Performance Metrics** - Track user engagement and activity

## 🚀 Quick Start

### Prerequisites
- Python 3.8 or higher
- Discord Bot Token
- Basic Discord server management knowledge

### Installation

1. **Clone the repository**
   ```bash
   git clone https://github.com/yourusername/discord-betting-bot.git
   cd discord-betting-bot
   ```

2. **Create virtual environment**
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate  # On Windows: .venv\Scripts\activate
   ```

3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

4. **Set up environment variables**
   ```bash
   cp .env.example .env
   # Edit .env and add your Discord bot token
   ```

5. **Run the bot**
   ```bash
   python bot.py
   ```

## 🔧 Configuration

### Discord Bot Setup
1. Go to [Discord Developer Portal](https://discord.com/developers/applications)
2. Create a new application and bot
3. Copy the bot token to your `.env` file
4. Enable these bot permissions:
   - Send Messages
   - Use Slash Commands
   - Embed Links
   - Read Message History
   - Add Reactions

### Environment Variables
```env
DISCORD_TOKEN=your_bot_token_here
```

## 📖 Commands

### Basic Commands
- `!ping` - Test bot responsiveness
- `!hello` - Welcome message with bot info
- `!help` - Complete command reference

### Economy Commands
- `!balance [@user]` - Check balance and betting stats
- `!daily` - Claim daily bonus points
- `!bailout` - Emergency points when broke
- `!leaderboard` - Top users by balance
- `!stats [@user]` - Detailed user statistics

### Betting Commands
- `!bet create` - Create a custom bet with multiple options
- `!bet quick <question>` - Quick yes/no bet
- `!bet list` - View all active bets (with admin controls)
- `!bet place <bet_id> <option> <amount>` - Place a bet
- `!bet info <bet_id>` - Detailed bet information
- `!bet mybets` - Your active bets

### Admin Commands
- `!admin` - Show admin command help
- `!admin resolve <bet_id>` - Interactive bet resolution
- `!admin setbalance @user <amount>` - Set user balance
- `!admin addpoints @user <amount>` - Add points to user
- `!admin removepoints @user <amount>` - Remove points from user
- `!admin userinfo @user` - Detailed user information
- `!admin refreshstats` - Refresh all user statistics

## 🎮 Usage Examples

### Creating a Bet
```
!bet quick "Will it rain tomorrow?"
```
Creates a simple yes/no bet that users can participate in.

### Placing a Bet
Click the bet in `!bet list` and use the interactive buttons to:
- Choose your option (Yes/No/Custom options)
- Select bet amount (10, 50, 100, 500, or custom)
- Confirm your bet

### Admin Resolution
Admins can resolve bets by:
1. Using `!bet list` (shows admin controls)
2. Clicking any bet → "🛡️ Admin Resolve"
3. Selecting the winning option
4. Confirming the resolution

## 🗃️ Database

The bot uses SQLite for data persistence with the following tables:
- **users** - User profiles, balances, and statistics
- **bets** - Bet information and status
- **user_bets** - Individual user bet records
- **transactions** - Complete financial audit trail
- **settings** - Bot configuration and server settings

## 🛠️ Development

### Project Structure
```
discord-betting-bot/
├── bot.py              # Main bot file
├── config.py           # Configuration management
├── requirements.txt    # Python dependencies
├── database/
│   ├── models.py       # Database schema and models
│   └── database.py     # Database operations
├── cogs/
│   ├── economy.py      # Economy system commands
│   ├── betting.py      # Betting system and UI
│   └── admin.py        # Admin commands and controls
└── data/               # Database files (auto-created)
```

### Adding Features
1. Create new commands in appropriate cog files
2. Add database models in `database/models.py`
3. Update help text in `bot.py`
4. Test thoroughly before deployment

## 📋 Roadmap

### Phase 1 ✅ (Complete)
- [x] Basic bot infrastructure
- [x] Economy system with virtual points
- [x] Interactive betting system
- [x] Admin controls and resolution
- [x] Statistics and leaderboards

### Phase 2 🚧 (In Progress)
- [ ] Bet history channels
- [ ] Scheduled bet resolution
- [ ] Advanced betting options
- [ ] User achievements system

### Phase 3 🔮 (Planned)
- [ ] Real money integration
- [ ] Tournament brackets
- [ ] Live sports betting feeds
- [ ] Mobile companion app

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## ⚠️ Disclaimer

This bot is designed for entertainment purposes with virtual currency only. When implementing real money features, ensure compliance with local gambling laws and regulations.

## 🆘 Support

- Create an [Issue](https://github.com/yourusername/discord-betting-bot/issues) for bug reports
- Join our [Discord Server](https://discord.gg/yourserver) for community support
- Check the [Wiki](https://github.com/yourusername/discord-betting-bot/wiki) for detailed documentation

---

**Made with ❤️ for Discord communities** 