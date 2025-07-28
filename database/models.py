import aiosqlite
import json
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List
import logging

logger = logging.getLogger(__name__)

class DatabaseModels:
    """Database schema and table creation"""
    
    @staticmethod
    async def create_tables(db: aiosqlite.Connection):
        """Create all necessary tables for the betting bot"""
        
        # Users table
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                discord_id INTEGER PRIMARY KEY,
                username TEXT NOT NULL,
                balance INTEGER DEFAULT 1000,
                total_bets_placed INTEGER DEFAULT 0,
                total_bets_won INTEGER DEFAULT 0,
                total_amount_won INTEGER DEFAULT 0,
                total_amount_lost INTEGER DEFAULT 0,
                last_daily_claim TEXT NULL,
                last_bailout_claim TEXT NULL,
                is_registered BOOLEAN DEFAULT TRUE,
                registration_date TEXT NOT NULL,
                last_activity TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """)
        
        # Bets table
        await db.execute("""
            CREATE TABLE IF NOT EXISTS bets (
                bet_id INTEGER PRIMARY KEY AUTOINCREMENT,
                creator_id INTEGER NOT NULL,
                guild_id INTEGER NOT NULL,
                bet_type TEXT NOT NULL CHECK (bet_type IN ('yn', 'multi', 'ou', 'odds')),
                title TEXT NOT NULL,
                description TEXT,
                options TEXT NOT NULL,
                odds TEXT,
                category TEXT DEFAULT 'general',
                status TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('draft', 'open', 'locked', 'resolved', 'archived', 'cancelled')),
                min_bet INTEGER DEFAULT 1,
                max_bet INTEGER DEFAULT NULL,
                total_pool INTEGER DEFAULT 0,
                lock_time TEXT NULL,
                created_at TEXT NOT NULL,
                resolved_at TEXT NULL,
                winning_option TEXT NULL,
                active_message_id INTEGER NULL,
                FOREIGN KEY (creator_id) REFERENCES users (discord_id)
            )
        """)
        
        # User bets table
        await db.execute("""
            CREATE TABLE IF NOT EXISTS user_bets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                bet_id INTEGER NOT NULL,
                option_chosen TEXT NOT NULL,
                amount INTEGER NOT NULL,
                potential_payout INTEGER DEFAULT 0,
                status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'won', 'lost', 'refunded')),
                created_at TEXT NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users (discord_id),
                FOREIGN KEY (bet_id) REFERENCES bets (bet_id),
                UNIQUE(user_id, bet_id)
            )
        """)
        
        # Transactions table
        await db.execute("""
            CREATE TABLE IF NOT EXISTS transactions (
                transaction_id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                amount INTEGER NOT NULL,
                transaction_type TEXT NOT NULL CHECK (transaction_type IN ('bet_placed', 'bet_won', 'bet_lost', 'bet_refunded', 'daily_bonus', 'transfer_sent', 'transfer_received', 'bailout', 'admin_adjustment', 'activity_reward')),
                reference_id INTEGER NULL,
                balance_before INTEGER NOT NULL,
                balance_after INTEGER NOT NULL,
                description TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users (discord_id)
            )
        """)
        
        # Settings table
        await db.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                guild_id INTEGER PRIMARY KEY,
                command_prefix TEXT DEFAULT '!',
                default_balance INTEGER DEFAULT 1000,
                daily_bonus_amount INTEGER DEFAULT 100,
                bailout_amount INTEGER DEFAULT 50,
                max_bet_percentage INTEGER DEFAULT 50,
                min_participants INTEGER DEFAULT 2,
                default_lock_time INTEGER DEFAULT 3600,
                bet_history_channel INTEGER NULL,
                active_bets_channel INTEGER NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """)
        
        # Activity tracking tables
        await db.execute("""
            CREATE TABLE IF NOT EXISTS activity_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                guild_id INTEGER NOT NULL,
                channel_id INTEGER NOT NULL,
                message_count INTEGER DEFAULT 1,
                last_message_time TEXT NOT NULL,
                hour_bucket TEXT NOT NULL,  -- Format: YYYY-MM-DD-HH for grouping
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(user_id, guild_id, hour_bucket)
            )
        """)
        
        await db.execute("""
            CREATE TABLE IF NOT EXISTS activity_rewards (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                guild_id INTEGER NOT NULL,
                points_earned INTEGER NOT NULL,
                messages_counted INTEGER NOT NULL,
                hour_bucket TEXT NOT NULL,
                bonus_multiplier REAL DEFAULT 1.0,
                processed_at TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
        """)
        
        await db.execute("""
            CREATE TABLE IF NOT EXISTS activity_settings (
                guild_id INTEGER PRIMARY KEY,
                enabled BOOLEAN DEFAULT TRUE,
                points_per_message INTEGER DEFAULT 2,
                message_cooldown INTEGER DEFAULT 600,
                max_messages_per_hour INTEGER DEFAULT 50,
                min_message_length INTEGER DEFAULT 3,
                bonus_multiplier REAL DEFAULT 1.0,
                excluded_channels TEXT DEFAULT '[]',  -- JSON array of channel IDs
                excluded_roles TEXT DEFAULT '[]',     -- JSON array of role IDs
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """)

        # Create indexes
        await db.execute("CREATE INDEX IF NOT EXISTS idx_users_username ON users(username)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_bets_creator ON bets(creator_id)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_bets_status ON bets(status)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_user_bets_user ON user_bets(user_id)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_user_bets_bet ON user_bets(bet_id)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_transactions_user ON transactions(user_id)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_transactions_type ON transactions(transaction_type)")
        
        # Activity indexes for performance
        await db.execute("CREATE INDEX IF NOT EXISTS idx_activity_messages_user_guild ON activity_messages(user_id, guild_id)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_activity_messages_hour ON activity_messages(hour_bucket)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_activity_rewards_user_guild ON activity_rewards(user_id, guild_id)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_activity_rewards_hour ON activity_rewards(hour_bucket)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_activity_settings_guild ON activity_settings(guild_id)")

        await db.commit()
        logger.info("Database tables created successfully")

class User:
    """User model for database operations"""
    
    def __init__(self, discord_id: int, username: str, balance: int = 1000, **kwargs):
        self.discord_id = discord_id
        self.username = username
        self.balance = balance
        self.total_bets_placed = kwargs.get('total_bets_placed', 0)
        self.total_bets_won = kwargs.get('total_bets_won', 0)
        self.total_amount_won = kwargs.get('total_amount_won', 0)
        self.total_amount_lost = kwargs.get('total_amount_lost', 0)
        self.last_daily_claim = kwargs.get('last_daily_claim')
        self.last_bailout_claim = kwargs.get('last_bailout_claim')
        self.is_registered = kwargs.get('is_registered', True)
        self.registration_date = kwargs.get('registration_date')
        self.last_activity = kwargs.get('last_activity')
        self.created_at = kwargs.get('created_at')
        self.updated_at = kwargs.get('updated_at')
    
    @classmethod
    def from_db_row(cls, row):
        """Create User instance from database row"""
        if not row:
            return None
        return cls(
            discord_id=row[0],
            username=row[1],
            balance=row[2],
            total_bets_placed=row[3],
            total_bets_won=row[4],
            total_amount_won=row[5],
            total_amount_lost=row[6],
            last_daily_claim=row[7],
            last_bailout_claim=row[8],
            is_registered=row[9],
            registration_date=row[10],
            last_activity=row[11],
            created_at=row[12],
            updated_at=row[13]
        )
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert user to dictionary"""
        return {
            'discord_id': self.discord_id,
            'username': self.username,
            'balance': self.balance,
            'total_bets_placed': self.total_bets_placed,
            'total_bets_won': self.total_bets_won,
            'total_amount_won': self.total_amount_won,
            'total_amount_lost': self.total_amount_lost,
            'win_rate': round((self.total_bets_won / max(1, self.total_bets_placed)) * 100, 1),
            'net_profit': self.total_amount_won - self.total_amount_lost,
            'registration_date': self.registration_date,
            'last_activity': self.last_activity
        }
