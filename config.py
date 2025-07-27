import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

class Config:
    # Discord settings
    DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')
    COMMAND_PREFIX = os.getenv('COMMAND_PREFIX', '!')
    
    # Database settings
    DATABASE_PATH = os.getenv('DATABASE_PATH', './data/betting_bot.db')
    
    # Economy settings
    DEFAULT_BALANCE = int(os.getenv('DEFAULT_BALANCE', 1000))
    DAILY_BONUS = int(os.getenv('DAILY_BONUS', 100))
    BAILOUT_AMOUNT = int(os.getenv('BAILOUT_AMOUNT', 50))
    
    # Activity Reward settings
    ACTIVITY_ENABLED = os.getenv('ACTIVITY_ENABLED', 'True').lower() == 'true'
    ACTIVITY_POINTS_PER_MESSAGE = int(os.getenv('ACTIVITY_POINTS_PER_MESSAGE', 2))
    ACTIVITY_MESSAGE_COOLDOWN = int(os.getenv('ACTIVITY_MESSAGE_COOLDOWN', 60))  # seconds
    ACTIVITY_MAX_MESSAGES_PER_HOUR = int(os.getenv('ACTIVITY_MAX_MESSAGES_PER_HOUR', 50))
    ACTIVITY_MIN_MESSAGE_LENGTH = int(os.getenv('ACTIVITY_MIN_MESSAGE_LENGTH', 3))
    ACTIVITY_BONUS_MULTIPLIER = float(os.getenv('ACTIVITY_BONUS_MULTIPLIER', 1.5))  # Weekend/event bonus
    
    # Bot settings
    BOT_NAME = "Betting Bot"
    BOT_VERSION = "1.0.0"
    
    @classmethod
    def validate(cls):
        """Validate that required configuration is present"""
        if not cls.DISCORD_TOKEN:
            raise ValueError("DISCORD_TOKEN is required in environment variables")
        return True 