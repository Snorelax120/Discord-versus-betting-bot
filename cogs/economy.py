import discord
from discord.ext import commands
from datetime import datetime, timezone, timedelta
from database.database import user_manager
import logging

logger = logging.getLogger(__name__)

class Economy(commands.Cog):
    """Economy commands for the betting bot"""
    
    def __init__(self, bot):
        self.bot = bot
    
    @commands.command(name='balance', aliases=['bal', 'money'])
    async def balance(self, ctx, user: discord.Member = None):
        """Check balance (yours or another user's)"""
        target_user = user or ctx.author
        
        # Auto-register and get user
        db_user, is_new = await user_manager.get_or_create_user(
            target_user.id, target_user.display_name
        )
        
        # Get fresh betting statistics
        if not is_new:
            db_user = await user_manager.get_user_with_fresh_stats(target_user.id)
        
        embed = discord.Embed(
            title=f"💰 {target_user.display_name}'s Balance",
            color=discord.Color.gold()
        )
        
        if is_new and target_user == ctx.author:
            embed.description = f"🎉 **Welcome to the betting system!**\nYou've been registered with your starting balance!"
        
        embed.add_field(
            name="Current Balance", 
            value=f"**{db_user.balance:,}** points", 
            inline=True
        )
        
        embed.add_field(
            name="Bets Placed", 
            value=f"{db_user.total_bets_placed}", 
            inline=True
        )
        
        embed.add_field(
            name="Win Rate", 
            value=f"{db_user.to_dict()['win_rate']}%", 
            inline=True
        )
        
        embed.add_field(
            name="Total Won", 
            value=f"{db_user.total_amount_won:,} points", 
            inline=True
        )
        
        embed.add_field(
            name="Total Lost", 
            value=f"{db_user.total_amount_lost:,} points", 
            inline=True
        )
        
        net_profit = db_user.to_dict()['net_profit']
        profit_emoji = "📈" if net_profit >= 0 else "📉"
        embed.add_field(
            name="Net Profit", 
            value=f"{profit_emoji} {net_profit:,} points", 
            inline=True
        )
        
        if target_user == ctx.author:
            embed.set_footer(text="Use !daily to claim your daily bonus!")
        
        await ctx.send(embed=embed)
    
    @commands.command(name='daily')
    async def daily(self, ctx):
        """Claim daily bonus points"""
        # Auto-register user
        db_user, is_new = await user_manager.get_or_create_user(
            ctx.author.id, ctx.author.display_name
        )
        
        # Try to claim daily bonus
        success, amount = await user_manager.claim_daily_bonus(ctx.author.id)
        
        embed = discord.Embed(
            title="🎁 Daily Bonus",
            color=discord.Color.green() if success else discord.Color.orange()
        )
        
        if success:
            # Get updated balance
            updated_user = await user_manager.get_user(ctx.author.id)
            
            embed.description = f"✅ **Daily bonus claimed!**\n+{amount:,} points added to your balance!"
            embed.add_field(
                name="New Balance", 
                value=f"**{updated_user.balance:,}** points", 
                inline=False
            )
            embed.set_footer(text="Come back in 24 hours for your next bonus!")
        else:
            # Check when they can claim next
            if db_user.last_daily_claim:
                last_claim = datetime.fromisoformat(db_user.last_daily_claim.replace('Z', '+00:00'))
                next_claim = last_claim + timedelta(hours=24)
                time_left = next_claim - datetime.now(timezone.utc)
                
                hours = int(time_left.total_seconds() // 3600)
                minutes = int((time_left.total_seconds() % 3600) // 60)
                
                embed.description = f"⏰ **Daily bonus already claimed!**\nCome back in **{hours}h {minutes}m** for your next bonus."
            else:
                embed.description = "❌ Unable to claim daily bonus right now."
        
        await ctx.send(embed=embed)
    
    @commands.command(name='bailout')
    async def bailout(self, ctx):
        """Claim emergency points when balance is 0"""
        # Auto-register user
        db_user, is_new = await user_manager.get_or_create_user(
            ctx.author.id, ctx.author.display_name
        )
        
        # Try to claim bailout
        success, amount = await user_manager.claim_bailout(ctx.author.id)
        
        embed = discord.Embed(
            title="🆘 Emergency Bailout",
            color=discord.Color.red() if not success else discord.Color.blue()
        )
        
        if success:
            # Get updated balance
            updated_user = await user_manager.get_user(ctx.author.id)
            
            embed.description = f"🆘 **Emergency bailout granted!**\n+{amount:,} points added to help you get back in the game!"
            embed.add_field(
                name="New Balance", 
                value=f"**{updated_user.balance:,}** points", 
                inline=False
            )
            embed.set_footer(text="Use these points wisely! Bailout available once per day when balance is 0.")
        else:
            if db_user.balance > 0:
                embed.description = f"❌ **Bailout not needed!**\nYou still have **{db_user.balance:,}** points.\nBailout is only available when your balance reaches 0."
            else:
                # Check when they can claim next
                if db_user.last_bailout_claim:
                    last_claim = datetime.fromisoformat(db_user.last_bailout_claim.replace('Z', '+00:00'))
                    next_claim = last_claim + timedelta(hours=24)
                    time_left = next_claim - datetime.now(timezone.utc)
                    
                    hours = int(time_left.total_seconds() // 3600)
                    minutes = int((time_left.total_seconds() % 3600) // 60)
                    
                    embed.description = f"⏰ **Bailout already used!**\nYou can claim another bailout in **{hours}h {minutes}m**."
                else:
                    embed.description = "❌ Unable to claim bailout right now."
        
        await ctx.send(embed=embed)
    
    @commands.command(name='leaderboard', aliases=['lb', 'top'])
    async def leaderboard(self, ctx, limit: int = 10):
        """Show top users by balance"""
        if limit > 20:
            limit = 20
        elif limit < 1:
            limit = 10
        
        top_users = await user_manager.get_leaderboard(limit)
        
        if not top_users:
            embed = discord.Embed(
                title="📊 Leaderboard",
                description="No users found! Be the first to start betting!",
                color=discord.Color.blue()
            )
            await ctx.send(embed=embed)
            return
        
        embed = discord.Embed(
            title=f"📊 Top {len(top_users)} Users - Leaderboard",
            color=discord.Color.gold()
        )
        
        leaderboard_text = ""
        for i, user in enumerate(top_users, 1):
            emoji = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else f"{i}."
            
            # Try to get Discord user for display name
            try:
                discord_user = self.bot.get_user(user.discord_id)
                display_name = discord_user.display_name if discord_user else user.username
            except:
                display_name = user.username
            
            leaderboard_text += f"{emoji} **{display_name}** - {user.balance:,} points\n"
        
        embed.description = leaderboard_text
        embed.set_footer(text="Keep betting to climb the leaderboard!")
        
        await ctx.send(embed=embed)
    
    @commands.command(name='stats')
    async def stats(self, ctx, user: discord.Member = None):
        """Show detailed user statistics"""
        target_user = user or ctx.author
        
        # Auto-register and get user
        db_user, is_new = await user_manager.get_or_create_user(
            target_user.id, target_user.display_name
        )
        
        # Get fresh betting statistics
        db_user = await user_manager.get_user_with_fresh_stats(target_user.id)
        
        embed = discord.Embed(
            title=f"📊 {target_user.display_name}'s Statistics",
            color=discord.Color.blue()
        )
        
        stats = db_user.to_dict()
        
        # Basic stats
        embed.add_field(
            name="💰 Current Balance", 
            value=f"{stats['balance']:,} points", 
            inline=True
        )
        
        embed.add_field(
            name="🎯 Total Bets", 
            value=f"{stats['total_bets_placed']}", 
            inline=True
        )
        
        embed.add_field(
            name="🏆 Bets Won", 
            value=f"{stats['total_bets_won']}", 
            inline=True
        )
        
        embed.add_field(
            name="📈 Win Rate", 
            value=f"{stats['win_rate']}%", 
            inline=True
        )
        
        embed.add_field(
            name="💎 Total Won", 
            value=f"{stats['total_amount_won']:,} points", 
            inline=True
        )
        
        embed.add_field(
            name="💸 Total Lost", 
            value=f"{stats['total_amount_lost']:,} points", 
            inline=True
        )
        
        # Net profit with emoji
        net_profit = stats['net_profit']
        profit_emoji = "📈" if net_profit >= 0 else "📉"
        profit_color = "green" if net_profit >= 0 else "red"
        
        embed.add_field(
            name=f"{profit_emoji} Net Profit", 
            value=f"{net_profit:,} points", 
            inline=True
        )
        
        # Registration info
        if stats['registration_date']:
            reg_date = datetime.fromisoformat(stats['registration_date'].replace('Z', '+00:00'))
            embed.add_field(
                name="📅 Member Since", 
                value=reg_date.strftime("%B %d, %Y"), 
                inline=True
            )
        
        # Risk assessment
        if stats['total_bets_placed'] > 0:
            avg_bet = (stats['total_amount_won'] + stats['total_amount_lost']) / stats['total_bets_placed']
            risk_level = "🟢 Conservative" if avg_bet < 100 else "🟡 Moderate" if avg_bet < 500 else "🔴 Aggressive"
            
            embed.add_field(
                name="⚖️ Risk Profile", 
                value=risk_level, 
                inline=True
            )
        
        if is_new and target_user == ctx.author:
            embed.set_footer(text="🎉 Welcome to the betting system! Start placing bets to build your stats.")
        else:
            embed.set_footer(text=f"Use !balance to see current balance • !daily for daily bonus")
        
        await ctx.send(embed=embed)

async def setup(bot):
    await bot.add_cog(Economy(bot))
