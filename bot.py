import discord
from discord.ext import commands
import asyncio
import logging
from config import Config
from database.database import db_manager

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Validate configuration
try:
    Config.validate()
except ValueError as e:
    logger.error(f"Configuration error: {e}")
    exit(1)

# Bot setup with intents
intents = discord.Intents.default()
intents.message_content = True  # Required for reading message content
intents.guilds = True
intents.members = True  # Might be needed for user management

class BettingBot(commands.Bot):
    def __init__(self):
        super().__init__(
            command_prefix=Config.COMMAND_PREFIX,
            intents=intents,
            help_command=None  # We'll create a custom help command later
        )
    
    async def setup_hook(self):
        """Called when the bot is starting up"""
        logger.info(f"{Config.BOT_NAME} v{Config.BOT_VERSION} is starting up...")
        
        # Initialize database
        try:
            await db_manager.initialize_database()
            logger.info("Database initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize database: {e}")
            raise
        
        # Load cogs
        try:
            await self.load_extension('cogs.economy')
            await self.load_extension('cogs.betting')
            await self.load_extension('cogs.admin')
            await self.load_extension('cogs.activity')
            logger.info("All cogs loaded successfully")
        except Exception as e:
            logger.error(f"Failed to load cogs: {e}")
    
    async def on_ready(self):
        """Called when bot is fully ready"""
        logger.info(f"{self.user} has connected to Discord!")
        logger.info(f"Bot is in {len(self.guilds)} guild(s)")
        
        # Set bot status
        activity = discord.Activity(
            type=discord.ActivityType.watching,
            name="for bets | !help"
        )
        await self.change_presence(activity=activity)
    
    async def on_command_error(self, ctx, error):
        """Global error handler"""
        if isinstance(error, commands.CommandNotFound):
            await ctx.send("❌ Command not found. Use `!help` to see available commands.")
        elif isinstance(error, commands.MissingRequiredArgument):
            await ctx.send(f"❌ Missing required argument: {error.param}")
        elif isinstance(error, commands.BadArgument):
            await ctx.send("❌ Invalid argument provided.")
        elif isinstance(error, commands.CommandOnCooldown):
            await ctx.send(f"⏰ Command on cooldown. Try again in {error.retry_after:.1f} seconds.")
        else:
            logger.error(f"Unhandled error in {ctx.command}: {error}")
            await ctx.send("❌ An unexpected error occurred.")
    
    async def close(self):
        """Clean up when bot shuts down"""
        await db_manager.close_all_connections()
        await super().close()

# Initialize bot
bot = BettingBot()

# Basic ping-pong commands (keep these for testing)
@bot.command(name='ping')
async def ping(ctx):
    """Simple ping command to test bot responsiveness"""
    latency = round(bot.latency * 1000)
    embed = discord.Embed(
        title="🏓 Pong!",
        description=f"Bot latency: {latency}ms",
        color=discord.Color.green()
    )
    await ctx.send(embed=embed)

@bot.command(name='pong')
async def pong(ctx):
    """Reverse ping-pong command"""
    embed = discord.Embed(
        title="🏓 Ping!",
        description="You said pong, I say ping!",
        color=discord.Color.blue()
    )
    await ctx.send(embed=embed)

@bot.command(name='hello')
async def hello(ctx):
    """Greet the user"""
    embed = discord.Embed(
        title="👋 Hello!",
        description=f"Hello {ctx.author.mention}! I'm {Config.BOT_NAME}.",
        color=discord.Color.gold()
    )
    embed.add_field(
        name="Getting Started",
        value="Try `!balance` to get started with betting or `!help` for more commands.",
        inline=False
    )
    await ctx.send(embed=embed)

@bot.command(name='info')
async def info(ctx):
    """Show bot information"""
    embed = discord.Embed(
        title=f"ℹ️ {Config.BOT_NAME} Information",
        color=discord.Color.blue()
    )
    embed.add_field(name="Version", value=Config.BOT_VERSION, inline=True)
    embed.add_field(name="Prefix", value=Config.COMMAND_PREFIX, inline=True)
    embed.add_field(name="Guilds", value=len(bot.guilds), inline=True)
    embed.add_field(
        name="Description",
        value="A Discord bot for placing bets with virtual points!",
        inline=False
    )
    embed.add_field(
        name="New Features",
        value="✅ Auto-registration system\n✅ Economy commands\n✅ Database storage",
        inline=False
    )
    embed.set_footer(text="Use !help to see all available commands!")
    await ctx.send(embed=embed)

@bot.command(name='help')
async def help_command(ctx):
    """Custom help command"""
    embed = discord.Embed(
        title="📖 Help - Available Commands",
        description="Here are the commands you can use:",
        color=discord.Color.purple()
    )
    
    embed.add_field(
        name="🏓 Basic Commands",
        value="`!ping` - Test bot responsiveness\n"
              "`!pong` - Reverse ping\n"
              "`!hello` - Get a greeting\n"
              "`!info` - Show bot information",
        inline=False
    )
    
    embed.add_field(
        name="💰 Economy Commands",
        value="`!balance [@user]` - Check balance (auto-registers new users)\n"
              "`!daily` - Claim daily bonus (100 points)\n"
              "`!bailout` - Emergency points when balance is 0\n"
              "`!leaderboard [limit]` - Show top users\n"
              "`!stats [@user]` - Show detailed user statistics",
        inline=False
    )
    
    embed.add_field(
        name="🎯 Activity Rewards",
        value="`!activity stats [@user]` - View activity statistics\n"
              "`!activity settings` - View/configure activity system (admins)\n"
              "`!activity toggle` - Enable/disable activity tracking (admins)\n"
              "🔥 **Auto Rewards**: Earn points by chatting! 2 points per message.",
        inline=False
    )
    
    embed.add_field(
        name="🎲 Betting Commands",
        value="`!bet create` - Interactive bet creation (2-5 options)\n"
              "`!bet quick [question]` - Quick yes/no bet creation\n"
              "`!bet list` - Show active bets with buttons\n"
              "`!bet mybets` - Show your active bets\n"
              "✨ **Clean UI**: Beautiful modals & buttons - simple and fast!",
        inline=False
    )
    
    embed.add_field(
        name="🛡️ Admin Commands (Admins Only)",
        value="`!bet list` - Shows admin controls in bet list for admins\n"
              "`!admin resolve <bet_id>` - Interactive bet resolution with buttons\n"
              "`!admin setbalance @user <amount>` - Set user balance\n"
              "`!admin addpoints @user <amount>` - Add points to user",
        inline=False
    )
    
    embed.set_footer(text="Use !<command> to run any command • New users get 1000 starting points!")
    await ctx.send(embed=embed)

if __name__ == "__main__":
    try:
        bot.run(Config.DISCORD_TOKEN)
    except discord.LoginFailure:
        logger.error("Invalid Discord token provided")
    except Exception as e:
        logger.error(f"Failed to start bot: {e}")
