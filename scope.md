# Discord Betting Bot - Project Scope

## Overview
A Discord bot that allows users to place bets using channel points (virtual currency) with plans to migrate to real money later. Built in Python using discord.py.

## 1. User Management & Economy System

### Auto-Registration System
- **Automatic Registration**: Users are auto-registered when they first interact with the bot
- **Registration Triggers**: Using any economy command, placing first bet, or any command requiring an account
- **No Manual Process**: No `!register` command needed - just use any bot command and you're in
- **Welcome Message**: First-time users get a welcome message with starting balance
- **Privacy Focused**: Only stores Discord ID, username, and betting data

### Points System
- **Starting Balance**: New users get 1000 points automatically upon registration
- **Daily Bonus**: Users can claim 100 points daily (`!daily`)
- **Leaderboard**: Show top users by balance (`!leaderboard`)
- **Transfer System**: Users can gift points to others (`!give @user amount`)
- **Bankruptcy Protection**: If user hits 0, can claim 50 points once per day (`!bailout`)

### User Profiles
- Track total bets placed
- Win/loss ratio
- Biggest win/loss
- Favorite betting categories
- Registration timestamp
- Last activity tracking

## 2. Betting System Types

### A. Simple Yes/No Bets
```
!bet create yn "Will it rain tomorrow?"
Users bet: !bet place 1 yes 100
```

### B. Multiple Choice Bets
```
!bet create multi "Who wins the tournament?" "Team A" "Team B" "Team C" "Team D"
Users bet: !bet place 2 "Team A" 250
```

### C. Over/Under Bets
```
!bet create ou "Total goals scored" 2.5
Users bet: !bet place 3 over 500
```

### D. Custom Odds Bets (Phase 2)
```
!bet create odds "Match winner" "Team A:1.5" "Team B:2.8" "Draw:3.2"
```

## 3. Bet Lifecycle & States

```
DRAFT → OPEN → LOCKED → RESOLVED → ARCHIVED

DRAFT: Creator setting up the bet
OPEN: Accepting wagers
LOCKED: No more bets accepted (manual or time-based)
RESOLVED: Winner determined, payouts processed
ARCHIVED: Historical record
```

## 4. Advanced Features

### Betting Pools
- Multiple users can contribute to create larger prize pools
- Community bets with shared risk/reward

### Bet Categories
- Sports, Gaming, Politics, Entertainment, Custom
- Category-specific channels
- Filter bets by category

### Time-Based Features
- Auto-lock bets at specified time
- Scheduled bet creation
- Bet expiration (auto-cancel if not enough participants)

### Anti-Abuse Measures
- Maximum bet limits (% of balance or fixed amount)
- Cooldown between creating bets
- Minimum participants required
- Rate limiting on commands

## 5. Permission System

### Roles
- **Bet Master** (Admin): Create/resolve any bet, modify balances
- **Bet Moderator**: Resolve bets, cannot modify balances
- **Bet Creator**: Can create bets (optional role restriction)
- **Regular User**: Can only place bets

### Channel Restrictions
- Betting only in specific channels
- Separate channels for different bet types
- Announcement channel for big wins

### **Bet History Channels**
- **Server Bet History Channel**: Public channel showing all bets placed in the server
  - Real-time updates when bets are created, placed, and resolved
  - Complete chronological history of all betting activity
  - Filterable by category, date, or bet type
  - Shows bet creators, participants, amounts, and outcomes
  - Formatted with rich embeds for easy reading

- **Personal Bet History**: Private channel/DM system for individual user's betting history
  - Command: `!history` or `!myhistory` to view personal betting timeline
  - Shows all bets participated in with detailed outcomes
  - Win/loss record with profit/loss tracking over time
  - Statistics on favorite bet types and performance
  - Filterable by date range, bet type, or win/loss status

## 6. Database Schema

### Users Table
```sql
users:
  - discord_id (PRIMARY KEY)
  - username
  - balance (DEFAULT 1000)
  - total_bets_placed (DEFAULT 0)
  - total_bets_won (DEFAULT 0)
  - total_amount_won (DEFAULT 0)
  - total_amount_lost (DEFAULT 0)
  - last_daily_claim (NULL)
  - last_bailout_claim (NULL)
  - is_registered (BOOLEAN DEFAULT TRUE)
  - registration_date (TIMESTAMP)
  - last_activity (TIMESTAMP)
  - created_at (TIMESTAMP)
  - updated_at (TIMESTAMP)
```

### Bets Table
```sql
bets:
  - bet_id (PRIMARY KEY, AUTO INCREMENT)
  - creator_id (FOREIGN KEY)
  - bet_type (yn/multi/ou/odds)
  - title
  - description
  - options (JSON)
  - odds (JSON, optional)
  - category
  - status
  - min_bet
  - max_bet
  - total_pool
  - lock_time (optional)
  - created_at
  - resolved_at
  - winning_option
```

### User Bets Table
```sql
user_bets:
  - id (PRIMARY KEY)
  - user_id (FOREIGN KEY)
  - bet_id (FOREIGN KEY)
  - option_chosen
  - amount
  - potential_payout
  - status (pending/won/lost)
  - created_at
```

### Transactions Table (Audit Trail)
```sql
transactions:
  - transaction_id (PRIMARY KEY)
  - user_id
  - amount
  - type (bet_placed/bet_won/daily_bonus/transfer/bailout)
  - reference_id (bet_id if applicable)
  - balance_before
  - balance_after
  - created_at
```

### Settings Table (Server Configurations)
```sql
settings:
  - guild_id (PRIMARY KEY)
  - betting_channels (JSON array)
  - announcement_channel
  - bet_history_channel          # <- ADD THIS
  - starting_balance
  - daily_bonus_amount
  - max_bet_percentage
  - min_participants
  - default_lock_time
```

## 7. Command Structure

### Economy Commands
```
!balance [@user]           - Check balance
!leaderboard [top 10]      - Show top users
!daily                     - Claim daily bonus
!bailout                   - Emergency points (once/day)
!give @user amount         - Transfer points
!stats [@user]             - Show betting statistics
!history                   - View personal betting history
!myhistory [filter]        - View filtered personal betting history
```

### Betting Commands
```
!bet create <type> <title> [options...]  - Create new bet
!bet place <bet_id> <option> <amount>    - Place a bet
!bet info <bet_id>                       - Show bet details
!bet list [active/resolved/my]           - List bets
!bet cancel <bet_id>                     - Cancel bet (creator/admin)
!bet lock <bet_id>                       - Lock betting (creator/admin)
!bet resolve <bet_id> <winning_option>   - Resolve bet (admin)
```

### Admin Commands
```
!admin setbalance @user amount   - Set user balance
!admin addpoints @user amount    - Add points to user
!admin removepoints @user amount - Remove points from user
!admin resetuser @user           - Reset user data
!admin bethistory <bet_id>       - Show bet history
!admin settings                  - Configure bot settings
!admin setchannel history  - Set bet history channel
```

## 8. Technical Architecture

### Main Components
- `bot.py` - Main bot file with Discord client
- `cogs/` - Command modules
  - `betting.py` - Betting commands
  - `economy.py` - Economy commands
  - `admin.py` - Admin commands
- `database/` - Database models and handlers
  - `models.py` - Database schemas
  - `database.py` - Database connection and operations
- `utils/` - Helper functions
  - `calculations.py` - Betting calculations
  - `validators.py` - Input validation
  - `formatters.py` - Message formatting
- `config.py` - Configuration settings
- `history.py` - Bet history and tracking

### Key Libraries
- `discord.py` - Discord API wrapper
- `python-dotenv` - Environment variables
- `aiosqlite` - Async SQLite for database
- `asyncio` - Async programming

## 9. Notification System

### DM Notifications (Opt-in)
- Bet resolved (won/lost)
- Someone placed bet on your created bet
- Daily bonus available

### Channel Announcements
- Big wins (over X amount)
- New bets created
- Bets closing soon
- Leaderboard changes

## 10. Statistics & Analytics

### User Stats
- Win rate by category
- Profit/loss over time
- Favorite bet types
- Risk profile (average bet size vs balance)

### Server Stats
- Most popular bet categories
- Total points in circulation
- Most active bettors
- Biggest upsets

## 11. Error Handling & Edge Cases

- Insufficient balance handling
- Duplicate bet prevention
- Handle Discord API rate limits
- Database connection failures
- Invalid bet amounts (negative, non-numeric)
- User leaving server with active bets
- Bot restart recovery

## 12. Phase 2 - Real Money Integration

### Requirements
- Stripe/PayPal integration
- KYC requirements
- Withdrawal system
- Legal compliance checks

### Advanced Features
- Live betting (update odds in real-time)
- Parlay bets (multiple bets combined)
- Bet insurance options
- Trading bets with other users
- API integration for real-world events

## 13. Testing Strategy

- Unit tests for calculation logic
- Integration tests for Discord commands
- Mock betting scenarios
- Load testing for concurrent bets
- Edge case testing (ties, refunds)

## 14. Implementation Priority

### Phase 1 (MVP)
1. Basic bot setup and database
2. Auto-registration system and balance tracking
3. Simple yes/no betting
4. Basic economy commands (!balance, !daily)
5. Admin controls for bet resolution
6. Bet history channels and personal history commands

**Auto-Registration Flow:**
- User runs any economy/betting command
- Bot automatically creates account with 1000 starting points
- Welcome message confirms registration
- No manual signup required

### Phase 2 (Enhanced Features)
1. Multiple choice bets
2. Advanced statistics
3. Notification system
4. Anti-abuse measures
5. Better UI/UX with embeds

### Phase 3 (Advanced)
1. Over/under bets
2. Custom odds system
3. Betting pools
4. Real money integration planning

### Phase 4 (Real Money)
1. Legal compliance research
2. Payment processor integration
3. KYC implementation
4. Security hardening
5. Financial reporting 