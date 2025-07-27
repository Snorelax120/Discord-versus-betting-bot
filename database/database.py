import aiosqlite
import asyncio
import json
from datetime import datetime, timezone
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
        from datetime import datetime, timedelta
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
        from datetime import datetime, timedelta
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

# Global database manager instance
db_manager = DatabaseManager()
user_manager = UserManager(db_manager)
