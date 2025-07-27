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
    
    # Bot settings
    BOT_NAME = "Betting Bot"
    BOT_VERSION = "1.0.0"
    
    @classmethod
    def validate(cls):
        """Validate that required configuration is present"""
        if not cls.DISCORD_TOKEN:
            raise ValueError("DISCORD_TOKEN is required in environment variables")
        return True 