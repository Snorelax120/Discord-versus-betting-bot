import aiosqlite
import asyncio
import json
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Dict, Any
import logging
from config import Config
from database.models import DatabaseModels, User

logger = logging.getLogger(__name__)

class DatabaseManager:
    """Manages database connections and operations"""
    
    def __init__(self, db_path: str = None):
        self.db_path = db_path or Config.DATABASE_PATH
        self._connection_pool = {}
        
    async def get_connection(self) -> aiosqlite.Connection:
        """Get database connection with connection pooling"""
        task_id = id(asyncio.current_task())
        
        if task_id not in self._connection_pool:
            conn = await aiosqlite.connect(self.db_path)
            conn.row_factory = aiosqlite.Row
            self._connection_pool[task_id] = conn
            
        return self._connection_pool[task_id]
    
    async def close_connection(self):
        """Close database connection for current task"""
        task_id = id(asyncio.current_task())
        if task_id in self._connection_pool:
            await self._connection_pool[task_id].close()
            del self._connection_pool[task_id]
    
    async def initialize_database(self):
        """Initialize database with tables"""
        conn = await self.get_connection()
        await DatabaseModels.create_tables(conn)
        
        # Create data directory if it doesn't exist
        import os
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        
        logger.info(f"Database initialized at {self.db_path}")
    
    async def close_all_connections(self):
        """Close all database connections"""
        for conn in self._connection_pool.values():
            await conn.close()
        self._connection_pool.clear()

class UserManager:
    """Manages user-related database operations"""
    
    def __init__(self, db_manager: DatabaseManager):
        self.db = db_manager
    
    async def get_user(self, discord_id: int) -> Optional[User]:
        """Get user by Discord ID"""
        conn = await self.db.get_connection()
        cursor = await conn.execute(
            "SELECT * FROM users WHERE discord_id = ?", 
            (discord_id,)
        )
        row = await cursor.fetchone()
        return User.from_db_row(row)
    
    async def create_user(self, discord_id: int, username: str, starting_balance: int = None) -> User:
        """Create new user with auto-registration"""
        if starting_balance is None:
            starting_balance = Config.DEFAULT_BALANCE
            
        now = datetime.now(timezone.utc).isoformat()
        
        conn = await self.db.get_connection()
        await conn.execute("""
            INSERT INTO users (
                discord_id, username, balance, registration_date, 
                last_activity, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (discord_id, username, starting_balance, now, now, now, now))
        
        await conn.commit()
        
        # Log the registration transaction
        await self.add_transaction(
            discord_id, starting_balance, 'admin_adjustment', 
            description=f"Initial registration bonus", 
            balance_before=0, balance_after=starting_balance
        )
        
        logger.info(f"Created new user: {username} ({discord_id}) with {starting_balance} points")
        return await self.get_user(discord_id)
    
    async def get_or_create_user(self, discord_id: int, username: str) -> tuple[User, bool]:
        """Get existing user or create new one (auto-registration)"""
        user = await self.get_user(discord_id)
        
        if user is None:
            user = await self.create_user(discord_id, username)
            return user, True  # New user created
        
        # Update username if it changed
        if user.username != username:
            await self.update_user_activity(discord_id, username)
            user.username = username
        
        return user, False  # Existing user
    
    async def update_balance(self, discord_id: int, new_balance: int) -> bool:
        """Update user balance"""
        now = datetime.now(timezone.utc).isoformat()
        
        conn = await self.db.get_connection()
        cursor = await conn.execute(
            "UPDATE users SET balance = ?, updated_at = ? WHERE discord_id = ?",
            (new_balance, now, discord_id)
        )
        await conn.commit()
        
        return cursor.rowcount > 0
    
    async def add_points(self, discord_id: int, amount: int, transaction_type: str, 
                        reference_id: int = None, description: str = None) -> bool:
        """Add points to user balance with transaction logging"""
        user = await self.get_user(discord_id)
        if not user:
            return False
        
        old_balance = user.balance
        new_balance = old_balance + amount
        
        # Update balance
        success = await self.update_balance(discord_id, new_balance)
        if success:
            # Log transaction
            await self.add_transaction(
                discord_id, amount, transaction_type, 
                reference_id, description, old_balance, new_balance
            )
        
        return success
    
    async def deduct_points(self, discord_id: int, amount: int, transaction_type: str,
                           reference_id: int = None, description: str = None) -> bool:
        """Deduct points from user balance with transaction logging"""
        user = await self.get_user(discord_id)
        if not user or user.balance < amount:
            return False
        
        old_balance = user.balance
        new_balance = old_balance - amount
        
        # Update balance
        success = await self.update_balance(discord_id, new_balance)
        if success:
            # Log transaction
            await self.add_transaction(
                discord_id, -amount, transaction_type,
                reference_id, description, old_balance, new_balance
            )
        
        return success
    
    async def update_user_activity(self, discord_id: int, username: str = None):
        """Update user's last activity timestamp"""
        now = datetime.now(timezone.utc).isoformat()
        
        conn = await self.db.get_connection()
        if username:
            await conn.execute(
                "UPDATE users SET username = ?, last_activity = ?, updated_at = ? WHERE discord_id = ?",
                (username, now, now, discord_id)
            )
        else:
            await conn.execute(
                "UPDATE users SET last_activity = ?, updated_at = ? WHERE discord_id = ?",
                (now, now, discord_id)
            )
        await conn.commit()
    
    async def can_claim_daily(self, discord_id: int) -> bool:
        """Check if user can claim daily bonus"""
        user = await self.get_user(discord_id)
        if not user or not user.last_daily_claim:
            return True
        
        # Check if 24 hours have passed
        last_claim = datetime.fromisoformat(user.last_daily_claim.replace('Z', '+00:00'))
        next_claim = last_claim + timedelta(hours=24)
        
        return datetime.now(timezone.utc) >= next_claim
    
    async def claim_daily_bonus(self, discord_id: int) -> tuple[bool, int]:
        """Claim daily bonus if available"""
        if not await self.can_claim_daily(discord_id):
            return False, 0
        
        bonus_amount = Config.DAILY_BONUS
        now = datetime.now(timezone.utc).isoformat()
        
        # Update last claim time
        conn = await self.db.get_connection()
        await conn.execute(
            "UPDATE users SET last_daily_claim = ?, updated_at = ? WHERE discord_id = ?",
            (now, now, discord_id)
        )
        await conn.commit()
        
        # Add points
        success = await self.add_points(
            discord_id, bonus_amount, 'daily_bonus',
            description="Daily bonus claimed"
        )
        
        return success, bonus_amount if success else 0
    
    async def can_claim_bailout(self, discord_id: int) -> bool:
        """Check if user can claim bailout (emergency points)"""
        user = await self.get_user(discord_id)
        if not user or user.balance > 0:
            return False
        
        if not user.last_bailout_claim:
            return True
        
        # Check if 24 hours have passed
        last_claim = datetime.fromisoformat(user.last_bailout_claim.replace('Z', '+00:00'))
        next_claim = last_claim + timedelta(hours=24)
        
        return datetime.now(timezone.utc) >= next_claim
    
    async def claim_bailout(self, discord_id: int) -> tuple[bool, int]:
        """Claim bailout if available"""
        if not await self.can_claim_bailout(discord_id):
            return False, 0
        
        bailout_amount = Config.BAILOUT_AMOUNT
        now = datetime.now(timezone.utc).isoformat()
        
        # Update last bailout time
        conn = await self.db.get_connection()
        await conn.execute(
            "UPDATE users SET last_bailout_claim = ?, updated_at = ? WHERE discord_id = ?",
            (now, now, discord_id)
        )
        await conn.commit()
        
        # Add points
        success = await self.add_points(
            discord_id, bailout_amount, 'bailout',
            description="Emergency bailout claimed"
        )
        
        return success, bailout_amount if success else 0
    
    async def get_leaderboard(self, limit: int = 10) -> List[User]:
        """Get top users by balance"""
        conn = await self.db.get_connection()
        cursor = await conn.execute(
            "SELECT * FROM users ORDER BY balance DESC LIMIT ?", 
            (limit,)
        )
        rows = await cursor.fetchall()
        return [User.from_db_row(row) for row in rows]
    
    async def add_transaction(self, user_id: int, amount: int, transaction_type: str,
                             reference_id: int = None, description: str = None,
                             balance_before: int = None, balance_after: int = None):
        """Add transaction to audit trail"""
        if balance_before is None or balance_after is None:
            user = await self.get_user(user_id)
            if user:
                balance_before = balance_before or user.balance
                balance_after = balance_after or user.balance
        
        now = datetime.now(timezone.utc).isoformat()
        
        conn = await self.db.get_connection()
        await conn.execute("""
            INSERT INTO transactions (
                user_id, amount, transaction_type, reference_id, 
                balance_before, balance_after, description, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (user_id, amount, transaction_type, reference_id, 
              balance_before, balance_after, description, now))
        
        await conn.commit()
    
    async def update_betting_stats(self, user_id: int):
        """Calculate and update user's betting statistics from actual bet data"""
        conn = await self.db.get_connection()
        
        # Calculate total bets placed
        cursor = await conn.execute(
            "SELECT COUNT(*) FROM user_bets WHERE user_id = ?",
            (user_id,)
        )
        total_bets_placed = (await cursor.fetchone())[0]
        
        # Calculate total bets won
        cursor = await conn.execute(
            "SELECT COUNT(*) FROM user_bets WHERE user_id = ? AND status = 'won'",
            (user_id,)
        )
        total_bets_won = (await cursor.fetchone())[0]
        
        # Calculate total amount won (from bet winnings transactions)
        cursor = await conn.execute(
            "SELECT COALESCE(SUM(amount), 0) FROM transactions WHERE user_id = ? AND transaction_type = 'bet_won'",
            (user_id,)
        )
        total_amount_won = (await cursor.fetchone())[0]
        
        # Calculate total amount lost (from bet placement transactions)
        cursor = await conn.execute(
            "SELECT COALESCE(SUM(ABS(amount)), 0) FROM transactions WHERE user_id = ? AND transaction_type = 'bet_placed'",
            (user_id,)
        )
        total_amount_lost = (await cursor.fetchone())[0]
        
        # Update user statistics
        now = datetime.now(timezone.utc).isoformat()
        await conn.execute("""
            UPDATE users SET 
                total_bets_placed = ?, 
                total_bets_won = ?, 
                total_amount_won = ?, 
                total_amount_lost = ?, 
                updated_at = ?
            WHERE discord_id = ?
        """, (total_bets_placed, total_bets_won, total_amount_won, total_amount_lost, now, user_id))
        
        await conn.commit()
        
        logger.info(f"Updated betting stats for user {user_id}: {total_bets_placed} bets, {total_bets_won} won, {total_amount_won} won points, {total_amount_lost} lost points")
        
        return {
            'total_bets_placed': total_bets_placed,
            'total_bets_won': total_bets_won,
            'total_amount_won': total_amount_won,
            'total_amount_lost': total_amount_lost
        }
    
    async def get_user_with_fresh_stats(self, discord_id: int) -> Optional[User]:
        """Get user with up-to-date betting statistics"""
        user = await self.get_user(discord_id)
        if user:
            await self.update_betting_stats(discord_id)
            # Fetch again to get updated stats
            user = await self.get_user(discord_id)
        return user
    
    async def refresh_all_user_stats(self) -> int:
        """Refresh betting statistics for all users"""
        conn = await self.db.get_connection()
        cursor = await conn.execute("SELECT discord_id FROM users")
        user_ids = [row[0] for row in await cursor.fetchall()]
        
        count = 0
        for user_id in user_ids:
            await self.update_betting_stats(user_id)
            count += 1
        
        logger.info(f"Refreshed betting statistics for {count} users")
        return count

class ActivityManager:
    """Manage activity tracking and rewards"""
    
    def __init__(self, db_manager: DatabaseManager):
        self.db = db_manager
    
    async def track_message(self, user_id: int, guild_id: int, channel_id: int, message_length: int) -> bool:
        """Track a message for activity rewards (returns True if tracked, False if on cooldown)"""
        now = datetime.now(timezone.utc)
        hour_bucket = now.strftime('%Y-%m-%d-%H')
        now_str = now.isoformat()
        
        # Check settings for this guild
        settings = await self.get_activity_settings(guild_id)
        if not settings.get('enabled', True):
            return False
        
        # Check message length requirement
        if message_length < settings.get('min_message_length', 3):
            return False
        
        conn = await self.db.get_connection()
        
        try:
            # Check if user has existing record for this hour
            existing = await conn.execute(
                "SELECT message_count, last_message_time FROM activity_messages WHERE user_id = ? AND guild_id = ? AND hour_bucket = ?",
                (user_id, guild_id, hour_bucket)
            )
            row = await existing.fetchone()
            
            if row:
                message_count, last_message_time = row
                
                # Check cooldown
                last_time = datetime.fromisoformat(last_message_time)
                cooldown_seconds = settings.get('message_cooldown', 600)
                if (now - last_time).total_seconds() < cooldown_seconds:
                    return False
                
                # Check max messages per hour
                max_messages = settings.get('max_messages_per_hour', 50)
                if message_count >= max_messages:
                    return False
                
                # Update existing record
                await conn.execute("""
                    UPDATE activity_messages 
                    SET message_count = message_count + 1, last_message_time = ?, updated_at = ?
                    WHERE user_id = ? AND guild_id = ? AND hour_bucket = ?
                """, (now_str, now_str, user_id, guild_id, hour_bucket))
            else:
                # Create new record
                await conn.execute("""
                    INSERT INTO activity_messages (user_id, guild_id, channel_id, message_count, last_message_time, hour_bucket, created_at, updated_at)
                    VALUES (?, ?, ?, 1, ?, ?, ?, ?)
                """, (user_id, guild_id, channel_id, now_str, hour_bucket, now_str, now_str))
            
            await conn.commit()
            return True
            
        except Exception as e:
            logger.error(f"Error tracking message: {e}")
            await conn.rollback()
            return False
    
    async def process_daily_rewards(self, guild_id: int = None) -> Dict[str, int]:
        """Process activity rewards for the last 24 hours (daily batch)"""
        now = datetime.now(timezone.utc)
        # Process last 24 hours of activity
        end_time = now.replace(hour=0, minute=0, second=0, microsecond=0)  # Start of today
        start_time = end_time - timedelta(days=1)  # Start of yesterday
        
        # Create day bucket for tracking (YYYY-MM-DD format)
        day_bucket = end_time.strftime('%Y-%m-%d')
        
        conn = await self.db.get_connection()
        results = {'users_processed': 0, 'total_points_awarded': 0, 'guilds_processed': 0}
        
        try:
            # Get all activity for the last 24 hours (sum by user and guild)
            query = """
                SELECT user_id, guild_id, SUM(message_count) as total_messages
                FROM activity_messages 
                WHERE hour_bucket >= ? AND hour_bucket < ?
                GROUP BY user_id, guild_id
            """
            start_bucket = start_time.strftime('%Y-%m-%d-%H')
            end_bucket = end_time.strftime('%Y-%m-%d-%H')
            params = [start_bucket, end_bucket]
            
            if guild_id:
                query += " AND guild_id = ?"
                params.append(guild_id)
            
            cursor = await conn.execute(query, params)
            activities = await cursor.fetchall()
            
            guilds_processed = set()
            
            for user_id, guild_id, total_messages in activities:
                # Check if already rewarded for this day
                existing_reward = await conn.execute("""
                    SELECT messages_counted FROM activity_rewards 
                    WHERE user_id = ? AND guild_id = ? AND hour_bucket = ?
                    ORDER BY processed_at DESC LIMIT 1
                """, (user_id, guild_id, day_bucket))
                
                reward_row = await existing_reward.fetchone()
                already_rewarded_messages = reward_row[0] if reward_row else 0
                
                # Only process if there are new messages to reward
                new_messages = total_messages - already_rewarded_messages
                if new_messages <= 0:
                    continue
                
                # Get settings for this guild
                settings = await self.get_activity_settings(guild_id)
                if not settings.get('enabled', True):
                    continue
                
                # Calculate points for new messages only
                points_per_message = settings.get('points_per_message', 2)
                bonus_multiplier = settings.get('bonus_multiplier', 1.0)
                
                # Apply daily cap (max messages per day = max_per_hour * 16 active hours)
                max_daily_messages = settings.get('max_messages_per_hour', 50) * 16
                capped_messages = min(new_messages, max_daily_messages)
                
                points_earned = int(capped_messages * points_per_message * bonus_multiplier)
                
                if points_earned > 0:
                    # Award points to user
                    await user_manager.add_points(user_id, points_earned, 
                                                'activity_reward',
                                                description=f"Daily activity reward for {capped_messages} messages")
                    
                    # Record the reward (using day bucket instead of hour bucket)
                    await conn.execute("""
                        INSERT INTO activity_rewards (user_id, guild_id, points_earned, messages_counted, hour_bucket, bonus_multiplier, processed_at, created_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """, (user_id, guild_id, points_earned, total_messages, day_bucket, bonus_multiplier, now.isoformat(), now.isoformat()))
                    
                    results['users_processed'] += 1
                    results['total_points_awarded'] += points_earned
                    guilds_processed.add(guild_id)
            
            results['guilds_processed'] = len(guilds_processed)
            await conn.commit()
            
        except Exception as e:
            logger.error(f"Error processing daily activity rewards: {e}")
            await conn.rollback()
        
        return results

    async def process_hourly_rewards(self, guild_id: int = None) -> Dict[str, int]:
        """Process activity rewards for current/recent activity (testing mode)"""
        now = datetime.now(timezone.utc)
        # For testing: process current hour AND previous hour to catch all recent activity
        current_hour = now.replace(minute=0, second=0, microsecond=0)
        previous_hour = current_hour - timedelta(hours=1)
        
        current_bucket = current_hour.strftime('%Y-%m-%d-%H')
        previous_bucket = previous_hour.strftime('%Y-%m-%d-%H')
        
        conn = await self.db.get_connection()
        results = {'users_processed': 0, 'total_points_awarded': 0, 'guilds_processed': 0}
        
        try:
            # Get all activity for both current and previous hour (testing mode)
            query = """
                SELECT user_id, guild_id, message_count, hour_bucket
                FROM activity_messages 
                WHERE hour_bucket IN (?, ?)
            """
            params = [current_bucket, previous_bucket]
            
            if guild_id:
                query += " AND guild_id = ?"
                params.append(guild_id)
            
            cursor = await conn.execute(query, params)
            activities = await cursor.fetchall()
            
            guilds_processed = set()
            processed_buckets = set()
            
            for user_id, guild_id, message_count, hour_bucket in activities:
                # Skip if we already processed this user for this hour in this batch
                processing_key = f"{user_id}_{guild_id}_{hour_bucket}"
                if processing_key in processed_buckets:
                    continue
                processed_buckets.add(processing_key)
                
                # Check if already rewarded for this hour and how many messages were rewarded
                existing_reward = await conn.execute("""
                    SELECT messages_counted FROM activity_rewards 
                    WHERE user_id = ? AND guild_id = ? AND hour_bucket = ?
                    ORDER BY processed_at DESC LIMIT 1
                """, (user_id, guild_id, hour_bucket))
                
                reward_row = await existing_reward.fetchone()
                already_rewarded_messages = reward_row[0] if reward_row else 0
                
                # Only process if there are new messages to reward
                new_messages = message_count - already_rewarded_messages
                if new_messages <= 0:
                    continue
                
                # Get settings for this guild
                settings = await self.get_activity_settings(guild_id)
                if not settings.get('enabled', True):
                    continue
                
                # Calculate points for new messages only
                points_per_message = settings.get('points_per_message', 2)
                bonus_multiplier = settings.get('bonus_multiplier', 1.0)
                points_earned = int(new_messages * points_per_message * bonus_multiplier)
                
                if points_earned > 0:
                    # Award points to user
                    await user_manager.add_points(user_id, points_earned, 
                                                'activity_reward',
                                                description=f"Activity reward for {new_messages} new messages ({message_count} total)")
                    
                    # Record the reward
                    await conn.execute("""
                        INSERT INTO activity_rewards (user_id, guild_id, points_earned, messages_counted, hour_bucket, bonus_multiplier, processed_at, created_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """, (user_id, guild_id, points_earned, message_count, hour_bucket, bonus_multiplier, now.isoformat(), now.isoformat()))
                    
                    results['users_processed'] += 1
                    results['total_points_awarded'] += points_earned
                    guilds_processed.add(guild_id)
            
            results['guilds_processed'] = len(guilds_processed)
            await conn.commit()
            
        except Exception as e:
            logger.error(f"Error processing activity rewards: {e}")
            await conn.rollback()
        
        return results
    
    async def get_activity_settings(self, guild_id: int) -> Dict[str, Any]:
        """Get activity settings for a guild"""
        conn = await self.db.get_connection()
        
        cursor = await conn.execute(
            "SELECT * FROM activity_settings WHERE guild_id = ?", (guild_id,)
        )
        row = await cursor.fetchone()
        
        if row:
            return {
                'guild_id': row[0],
                'enabled': bool(row[1]),
                'points_per_message': row[2],
                'message_cooldown': row[3],
                'max_messages_per_hour': row[4],
                'min_message_length': row[5],
                'bonus_multiplier': row[6],
                'excluded_channels': json.loads(row[7]),
                'excluded_roles': json.loads(row[8])
            }
        else:
            # Return default settings
            return {
                'guild_id': guild_id,
                'enabled': True,
                'points_per_message': 2,
                'message_cooldown': 600,
                'max_messages_per_hour': 50,
                'min_message_length': 3,
                'bonus_multiplier': 1.0,
                'excluded_channels': [],
                'excluded_roles': []
            }
    
    async def update_activity_settings(self, guild_id: int, settings: Dict[str, Any]) -> bool:
        """Update activity settings for a guild"""
        now = datetime.now(timezone.utc).isoformat()
        conn = await self.db.get_connection()
        
        try:
            # Check if settings exist
            cursor = await conn.execute("SELECT guild_id FROM activity_settings WHERE guild_id = ?", (guild_id,))
            exists = await cursor.fetchone()
            
            excluded_channels = json.dumps(settings.get('excluded_channels', []))
            excluded_roles = json.dumps(settings.get('excluded_roles', []))
            
            if exists:
                await conn.execute("""
                    UPDATE activity_settings 
                    SET enabled = ?, points_per_message = ?, message_cooldown = ?, 
                        max_messages_per_hour = ?, min_message_length = ?, bonus_multiplier = ?,
                        excluded_channels = ?, excluded_roles = ?, updated_at = ?
                    WHERE guild_id = ?
                """, (
                    settings.get('enabled', True),
                    settings.get('points_per_message', 2),
                    settings.get('message_cooldown', 600),
                    settings.get('max_messages_per_hour', 50),
                    settings.get('min_message_length', 3),
                    settings.get('bonus_multiplier', 1.0),
                    excluded_channels,
                    excluded_roles,
                    now,
                    guild_id
                ))
            else:
                await conn.execute("""
                    INSERT INTO activity_settings 
                    (guild_id, enabled, points_per_message, message_cooldown, max_messages_per_hour, 
                     min_message_length, bonus_multiplier, excluded_channels, excluded_roles, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    guild_id,
                    settings.get('enabled', True),
                    settings.get('points_per_message', 2),
                    settings.get('message_cooldown', 600),
                    settings.get('max_messages_per_hour', 50),
                    settings.get('min_message_length', 3),
                    settings.get('bonus_multiplier', 1.0),
                    excluded_channels,
                    excluded_roles,
                    now,
                    now
                ))
            
            await conn.commit()
            return True
            
        except Exception as e:
            logger.error(f"Error updating activity settings: {e}")
            await conn.rollback()
            return False
    
    async def get_user_activity_stats(self, user_id: int, guild_id: int = None, days: int = 7) -> Dict[str, Any]:
        """Get activity statistics for a user"""
        conn = await self.db.get_connection()
        
        # Calculate date range
        end_date = datetime.now(timezone.utc)
        start_date = end_date - timedelta(days=days)
        start_bucket = start_date.strftime('%Y-%m-%d-%H')
        end_bucket = end_date.strftime('%Y-%m-%d-%H')
        
        try:
            # Get activity rewards for the period
            query = """
                SELECT COUNT(*) as reward_count, SUM(points_earned) as total_points, SUM(messages_counted) as total_messages
                FROM activity_rewards 
                WHERE user_id = ? AND hour_bucket >= ? AND hour_bucket <= ?
            """
            params = [user_id, start_bucket, end_bucket]
            
            if guild_id:
                query += " AND guild_id = ?"
                params.append(guild_id)
            
            cursor = await conn.execute(query, params)
            row = await cursor.fetchone()
            
            reward_count, total_points, total_messages = row if row else (0, 0, 0)
            
            return {
                'reward_periods': reward_count or 0,
                'total_points_earned': total_points or 0,
                'total_messages': total_messages or 0,
                'days_tracked': days,
                'average_points_per_day': round((total_points or 0) / days, 1),
                'average_messages_per_day': round((total_messages or 0) / days, 1)
            }
            
        except Exception as e:
            logger.error(f"Error getting user activity stats: {e}")
            return {
                'reward_periods': 0,
                'total_points_earned': 0, 
                'total_messages': 0,
                'days_tracked': days,
                'average_points_per_day': 0.0,
                'average_messages_per_day': 0.0
            }

# Create global activity manager instance
activity_manager = None

# Global database manager instances
db_manager = DatabaseManager()
user_manager = UserManager(db_manager)
