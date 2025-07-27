import discord
from discord.ext import commands, tasks
import json
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Optional

from database.database import db_manager, user_manager, ActivityManager
from config import Config

logger = logging.getLogger(__name__)

class Activity(commands.Cog):
    """Activity tracking and reward system"""
    
    def __init__(self, bot):
        self.bot = bot
        self.activity_manager = ActivityManager(db_manager)
        self.message_cache = {}  # In-memory cooldown tracking for performance
        
        # Start background task
        if Config.ACTIVITY_ENABLED:
            self.process_rewards.start()
    
    def cog_unload(self):
        """Stop background tasks when cog is unloaded"""
        self.process_rewards.cancel()
    
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """Track messages for activity rewards"""
        # Skip if activity is disabled
        if not Config.ACTIVITY_ENABLED:
            return
        
        # Skip bots and DMs
        if message.author.bot or not message.guild:
            return
        
        # Skip if message is too short
        if len(message.content) < Config.ACTIVITY_MIN_MESSAGE_LENGTH:
            return
        
        # Skip command messages (starting with prefix)
        if message.content.startswith(Config.COMMAND_PREFIX):
            return
        
        user_id = message.author.id
        guild_id = message.guild.id
        channel_id = message.channel.id
        
        # Check in-memory cooldown cache first (performance optimization)
        cache_key = f"{user_id}_{guild_id}"
        now = datetime.now(timezone.utc)
        
        if cache_key in self.message_cache:
            last_time = self.message_cache[cache_key]
            if (now - last_time).total_seconds() < Config.ACTIVITY_MESSAGE_COOLDOWN:
                return
        
        # Get guild-specific settings
        settings = await self.activity_manager.get_activity_settings(guild_id)
        
        # Check if channel or user roles are excluded
        if channel_id in settings.get('excluded_channels', []):
            return
        
        user_role_ids = [role.id for role in message.author.roles]
        if any(role_id in settings.get('excluded_roles', []) for role_id in user_role_ids):
            return
        
        # Track the message
        tracked = await self.activity_manager.track_message(
            user_id, guild_id, channel_id, len(message.content)
        )
        
        if tracked:
            # Update in-memory cache
            self.message_cache[cache_key] = now
            
            # Clean old cache entries (keep cache size manageable)
            if len(self.message_cache) > 1000:
                cutoff_time = now - timedelta(minutes=5)
                self.message_cache = {
                    k: v for k, v in self.message_cache.items() 
                    if v > cutoff_time
                }
    
    @tasks.loop(hours=24)
    async def process_rewards(self):
        """Process daily activity rewards (production mode)"""
        if not Config.ACTIVITY_ENABLED:
            return
        
        try:
            results = await self.activity_manager.process_daily_rewards()
            if results['users_processed'] > 0:
                logger.info(f"Daily activity rewards processed: {results['users_processed']} users, "
                           f"{results['total_points_awarded']} points awarded across "
                           f"{results['guilds_processed']} guilds")
        except Exception as e:
            logger.error(f"Error in daily reward processing: {e}")
    
    @process_rewards.before_loop
    async def before_process_rewards(self):
        """Wait for bot to be ready before starting the loop"""
        await self.bot.wait_until_ready()
    
    # Activity Commands
    @commands.group(name='activity', aliases=['act'])
    async def activity_group(self, ctx):
        """Activity tracking and reward commands"""
        if ctx.invoked_subcommand is None:
            await self.show_activity_help(ctx)
    
    async def show_activity_help(self, ctx):
        """Show activity command help"""
        embed = discord.Embed(
            title="🎯 Activity System Commands",
            description="Track and reward server activity with points!",
            color=discord.Color.blue()
        )
        
        embed.add_field(
            name="User Commands",
            value="`!activity stats [@user]` - View activity statistics\n"
                  "`!activity leaderboard` - View activity leaderboard",
            inline=False
        )
        
        if ctx.author.guild_permissions.administrator:
            embed.add_field(
                name="Admin Commands",
                value="`!activity settings` - View current settings\n"
                      "`!activity config <setting> <value>` - Update settings\n"
                      "`!activity process` - Manually process rewards\n"
                      "`!activity toggle` - Enable/disable activity tracking",
                inline=False
            )
        
        embed.add_field(
            name="How It Works",
            value=f"• Earn **{Config.ACTIVITY_POINTS_PER_MESSAGE} points** per message\n"
                  f"• **{Config.ACTIVITY_MESSAGE_COOLDOWN//60} minutes** cooldown between counted messages\n"
                  f"• Max **{Config.ACTIVITY_MAX_MESSAGES_PER_HOUR}** messages per hour\n"
                  f"• Messages must be **{Config.ACTIVITY_MIN_MESSAGE_LENGTH}+** characters\n"
                  f"• 🏭 **Production Mode**: Rewards processed daily at midnight!",
            inline=False
        )
        
        await ctx.send(embed=embed)
    
    @activity_group.command(name='stats')
    async def activity_stats(self, ctx, user: discord.Member = None):
        """Show activity statistics for a user"""
        target_user = user or ctx.author
        
        # Auto-register user if needed
        await user_manager.get_or_create_user(target_user.id, target_user.display_name)
        
        # Get activity stats
        stats = await self.activity_manager.get_user_activity_stats(
            target_user.id, ctx.guild.id, days=7
        )
        
        embed = discord.Embed(
            title=f"📊 Activity Stats - {target_user.display_name}",
            color=discord.Color.green()
        )
        
        embed.add_field(
            name="Last 7 Days",
            value=f"**{stats['total_points_earned']}** points earned\n"
                  f"**{stats['total_messages']}** messages counted\n"
                  f"**{stats['reward_periods']}** reward periods",
            inline=True
        )
        
        embed.add_field(
            name="Daily Averages",
            value=f"**{stats['average_points_per_day']}** points/day\n"
                  f"**{stats['average_messages_per_day']}** messages/day",
            inline=True
        )
        
        # Get current settings
        settings = await self.activity_manager.get_activity_settings(ctx.guild.id)
        
        embed.add_field(
            name="Current Rates",
            value=f"**{settings['points_per_message']}** points per message\n"
                  f"**{settings['max_messages_per_hour']}** max messages/hour\n"
                  f"**{settings['message_cooldown']}s** cooldown",
            inline=True
        )
        
        embed.set_thumbnail(url=target_user.avatar.url if target_user.avatar else target_user.default_avatar.url)
        embed.set_footer(text="🏭 Production Mode: Rewards processed daily at midnight!")
        
        await ctx.send(embed=embed)
    
    @activity_group.command(name='leaderboard', aliases=['lb', 'top'])
    async def activity_leaderboard(self, ctx, days: int = 7):
        """Show activity leaderboard"""
        if days < 1 or days > 30:
            days = 7
        
        # This would require a more complex query to get leaderboard data
        # For now, show a simple message
        embed = discord.Embed(
            title=f"🏆 Activity Leaderboard - Last {days} Days",
            description="Activity leaderboard feature coming soon!\n"
                       f"Use `!activity stats` to view your personal statistics.",
            color=discord.Color.gold()
        )
        
        await ctx.send(embed=embed)
    
    # Admin Commands
    @activity_group.command(name='settings')
    @commands.has_permissions(administrator=True)
    async def activity_settings(self, ctx):
        """View current activity settings"""
        settings = await self.activity_manager.get_activity_settings(ctx.guild.id)
        
        embed = discord.Embed(
            title="⚙️ Activity Settings",
            color=discord.Color.blue()
        )
        
        embed.add_field(
            name="Status",
            value="🟢 Enabled" if settings['enabled'] else "🔴 Disabled",
            inline=True
        )
        
        embed.add_field(
            name="Rewards",
            value=f"**{settings['points_per_message']}** points per message\n"
                  f"**{settings['bonus_multiplier']}x** bonus multiplier",
            inline=True
        )
        
        embed.add_field(
            name="Limits",
            value=f"**{settings['max_messages_per_hour']}** max messages/hour\n"
                  f"**{settings['message_cooldown']}s** cooldown\n"
                  f"**{settings['min_message_length']}** min characters",
            inline=True
        )
        
        if settings['excluded_channels']:
            channel_mentions = []
            for channel_id in settings['excluded_channels']:
                channel = ctx.guild.get_channel(channel_id)
                if channel:
                    channel_mentions.append(channel.mention)
            
            if channel_mentions:
                embed.add_field(
                    name="Excluded Channels",
                    value="\n".join(channel_mentions),
                    inline=False
                )
        
        if settings['excluded_roles']:
            role_mentions = []
            for role_id in settings['excluded_roles']:
                role = ctx.guild.get_role(role_id)
                if role:
                    role_mentions.append(role.mention)
            
            if role_mentions:
                embed.add_field(
                    name="Excluded Roles",
                    value="\n".join(role_mentions),
                    inline=False
                )
        
        await ctx.send(embed=embed)
    
    @activity_group.command(name='toggle')
    @commands.has_permissions(administrator=True)
    async def toggle_activity(self, ctx):
        """Toggle activity tracking on/off"""
        current_settings = await self.activity_manager.get_activity_settings(ctx.guild.id)
        new_enabled = not current_settings['enabled']
        
        await self.activity_manager.update_activity_settings(ctx.guild.id, {
            'enabled': new_enabled
        })
        
        status = "🟢 **Enabled**" if new_enabled else "🔴 **Disabled**"
        embed = discord.Embed(
            title="⚙️ Activity Tracking Updated",
            description=f"Activity tracking is now {status}",
            color=discord.Color.green() if new_enabled else discord.Color.red()
        )
        
        await ctx.send(embed=embed)
    
    @activity_group.command(name='config')
    @commands.has_permissions(administrator=True)
    async def config_activity(self, ctx, setting: str = None, *, value: str = None):
        """Configure activity settings"""
        if not setting or not value:
            await ctx.send("Usage: `!activity config <setting> <value>`\n"
                          "Available settings: `points`, `cooldown`, `max_messages`, `min_length`, `bonus`")
            return
        
        current_settings = await self.activity_manager.get_activity_settings(ctx.guild.id)
        updates = {}
        
        try:
            if setting.lower() in ['points', 'points_per_message']:
                points = int(value)
                if 1 <= points <= 10:
                    updates['points_per_message'] = points
                else:
                    await ctx.send("❌ Points per message must be between 1 and 10")
                    return
            
            elif setting.lower() in ['cooldown', 'message_cooldown']:
                cooldown = int(value)
                if 10 <= cooldown <= 300:
                    updates['message_cooldown'] = cooldown
                else:
                    await ctx.send("❌ Cooldown must be between 10 and 300 seconds")
                    return
            
            elif setting.lower() in ['max_messages', 'max_messages_per_hour']:
                max_msgs = int(value)
                if 10 <= max_msgs <= 100:
                    updates['max_messages_per_hour'] = max_msgs
                else:
                    await ctx.send("❌ Max messages per hour must be between 10 and 100")
                    return
            
            elif setting.lower() in ['min_length', 'min_message_length']:
                min_len = int(value)
                if 1 <= min_len <= 20:
                    updates['min_message_length'] = min_len
                else:
                    await ctx.send("❌ Min message length must be between 1 and 20 characters")
                    return
            
            elif setting.lower() in ['bonus', 'bonus_multiplier']:
                bonus = float(value)
                if 0.5 <= bonus <= 3.0:
                    updates['bonus_multiplier'] = bonus
                else:
                    await ctx.send("❌ Bonus multiplier must be between 0.5 and 3.0")
                    return
            
            else:
                await ctx.send("❌ Unknown setting. Available: `points`, `cooldown`, `max_messages`, `min_length`, `bonus`")
                return
            
            # Update settings
            success = await self.activity_manager.update_activity_settings(ctx.guild.id, updates)
            
            if success:
                setting_name = list(updates.keys())[0]
                new_value = list(updates.values())[0]
                
                embed = discord.Embed(
                    title="✅ Setting Updated",
                    description=f"**{setting_name}** has been set to **{new_value}**",
                    color=discord.Color.green()
                )
                await ctx.send(embed=embed)
            else:
                await ctx.send("❌ Failed to update setting")
        
        except ValueError:
            await ctx.send("❌ Invalid value format")
    
    @activity_group.command(name='process')
    @commands.has_permissions(administrator=True)
    async def process_activity_rewards(self, ctx):
        """Manually process daily activity rewards (production mode)"""
        embed = discord.Embed(
            title="🔄 Processing Daily Activity Rewards...",
            description="Processing rewards for the last 24 hours...\n🏭 **Production Mode**: Normally processed daily at midnight!",
            color=discord.Color.orange()
        )
        
        message = await ctx.send(embed=embed)
        
        try:
            results = await self.activity_manager.process_daily_rewards(ctx.guild.id)
            
            embed = discord.Embed(
                title="✅ Daily Activity Rewards Processed",
                color=discord.Color.green()
            )
            
            embed.add_field(
                name="Results",
                value=f"**{results['users_processed']}** users processed\n"
                      f"**{results['total_points_awarded']}** total points awarded",
                inline=False
            )
            
            await message.edit(embed=embed)
            
        except Exception as e:
            embed = discord.Embed(
                title="❌ Processing Failed",
                description=f"Error: {str(e)}",
                color=discord.Color.red()
            )
            await message.edit(embed=embed)

async def setup(bot):
    await bot.add_cog(Activity(bot)) 