import discord
from discord.ext import commands
from database.database import user_manager
from cogs.betting import bet_manager
import logging

logger = logging.getLogger(__name__)

class Admin(commands.Cog):
    """Admin commands for the betting bot"""
    
    def __init__(self, bot):
        self.bot = bot
    
    def is_admin_or_owner():
        """Check if user is admin or bot owner"""
        async def predicate(ctx):
            # Check if user is server admin or has manage server permission
            if ctx.author.guild_permissions.administrator:
                return True
            
            # Check if user has specific betting roles (we can add this later)
            admin_roles = ['Bet Master', 'Bet Moderator', 'Admin']
            user_roles = [role.name for role in ctx.author.roles]
            
            return any(role in admin_roles for role in user_roles)
        
        return commands.check(predicate)
    
    @commands.group(name='admin', invoke_without_command=True)
    @is_admin_or_owner()
    async def admin_group(self, ctx):
        """Admin command group"""
        if ctx.invoked_subcommand is None:
            embed = discord.Embed(
                title="🛡️ Admin Commands",
                description="Administrative commands for managing the betting bot:",
                color=discord.Color.red()
            )
            
            embed.add_field(
                name="Bet Management",
                value="`!admin resolve <bet_id>` - Show bet resolution interface with buttons\n"
                      "Interactive buttons for: resolve, lock, or cancel bets",
                inline=False
            )
            
            embed.add_field(
                name="User Management",
                value="`!admin setbalance @user <amount>` - Set user balance\n"
                      "`!admin addpoints @user <amount>` - Add points to user\n"
                      "`!admin removepoints @user <amount>` - Remove points from user",
                inline=False
            )
            
            embed.add_field(
                name="Information",
                value="`!admin userinfo @user` - Show detailed user info\n"
                      "`!admin refreshstats` - Refresh betting statistics for all users",
                inline=False
            )
            
            embed.set_footer(text="⚠️ Admin commands require appropriate permissions")
            await ctx.send(embed=embed)
    
    @admin_group.command(name='resolve')
    @is_admin_or_owner()
    async def resolve_bet(self, ctx, bet_id: int):
        """Show resolution interface for a bet"""
        # Import here to avoid circular imports
        from cogs.betting import BetResolutionView, bet_manager
        
        # Get bet details first
        bet = await bet_manager.get_bet(bet_id)
        if not bet:
            await ctx.send(f"❌ Bet #{bet_id} not found!")
            return
        
        if bet['status'] not in ['open', 'locked']:
            await ctx.send(f"❌ Bet #{bet_id} cannot be resolved (Status: {bet['status']})")
            return
        
        # Get bet statistics
        user_bets = await bet_manager.get_user_bets_for_bet(bet_id)
        
        embed = discord.Embed(
            title="🛡️ Admin: Resolve Bet",
            description=f"**{bet['title']}**",
            color=discord.Color.red()
        )
        
        embed.add_field(name="Bet ID", value=f"#{bet_id}", inline=True)
        embed.add_field(name="Status", value=bet['status'].title(), inline=True)
        embed.add_field(name="Total Pool", value=f"{bet['total_pool']:,} points", inline=True)
        
        if bet['description']:
            embed.add_field(name="Description", value=bet['description'], inline=False)
        
        # Show options with bet counts
        option_stats = {}
        for user_bet in user_bets:
            option = user_bet['option_chosen']
            if option not in option_stats:
                option_stats[option] = {'count': 0, 'amount': 0}
            option_stats[option]['count'] += 1
            option_stats[option]['amount'] += user_bet['amount']
        
        options_text = ""
        option_emojis = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣"]
        for i, option in enumerate(bet['options']):
            emoji = option_emojis[i] if i < len(option_emojis) else "▫️"
            stats = option_stats.get(option, {'count': 0, 'amount': 0})
            options_text += f"{emoji} **{option}**: {stats['count']} bets ({stats['amount']:,} points)\n"
        
        embed.add_field(name="Options & Current Bets", value=options_text, inline=False)
        
        embed.add_field(
            name="⚠️ Resolution Actions",
            value="• Click an option button to resolve with that winner\n• Click 🔒 to lock betting (no more bets)\n• Click ❌ to cancel and refund all players",
            inline=False
        )
        
        embed.set_footer(text="Choose the winning option or action below:")
        
        # Create resolution view
        view = BetResolutionView(bet_id, bet['title'], bet['options'])
        
        await ctx.send(embed=embed, view=view)
    
    @admin_group.command(name='setbalance')
    @is_admin_or_owner()
    async def set_balance(self, ctx, user: discord.Member, amount: int):
        """Set a user's balance"""
        if amount < 0:
            await ctx.send("❌ Balance cannot be negative!")
            return
        
        # Get or create user
        db_user, is_new = await user_manager.get_or_create_user(user.id, user.display_name)
        old_balance = db_user.balance
        
        # Update balance
        success = await user_manager.update_balance(user.id, amount)
        
        if success:
            # Log the transaction
            difference = amount - old_balance
            await user_manager.add_transaction(
                user.id, difference, 'admin_adjustment',
                description=f"Balance set by admin {ctx.author.display_name}",
                balance_before=old_balance, balance_after=amount
            )
            
            embed = discord.Embed(
                title="✅ Balance Updated",
                color=discord.Color.green()
            )
            embed.add_field(name="User", value=user.mention, inline=True)
            embed.add_field(name="Old Balance", value=f"{old_balance:,} points", inline=True)
            embed.add_field(name="New Balance", value=f"{amount:,} points", inline=True)
            embed.add_field(name="Admin", value=ctx.author.mention, inline=True)
            
            await ctx.send(embed=embed)
            logger.info(f"Balance set: {user} balance changed from {old_balance} to {amount} by {ctx.author}")
        else:
            await ctx.send("❌ Failed to update balance!")
    
    @admin_group.command(name='addpoints')
    @is_admin_or_owner()
    async def add_points(self, ctx, user: discord.Member, amount: int):
        """Add points to a user's balance"""
        if amount <= 0:
            await ctx.send("❌ Amount must be positive!")
            return
        
        # Get or create user
        db_user, is_new = await user_manager.get_or_create_user(user.id, user.display_name)
        
        # Add points
        success = await user_manager.add_points(
            user.id, amount, 'admin_adjustment',
            description=f"Points added by admin {ctx.author.display_name}"
        )
        
        if success:
            # Get updated balance
            updated_user = await user_manager.get_user(user.id)
            
            embed = discord.Embed(
                title="✅ Points Added",
                color=discord.Color.green()
            )
            embed.add_field(name="User", value=user.mention, inline=True)
            embed.add_field(name="Points Added", value=f"+{amount:,} points", inline=True)
            embed.add_field(name="New Balance", value=f"{updated_user.balance:,} points", inline=True)
            embed.add_field(name="Admin", value=ctx.author.mention, inline=True)
            
            await ctx.send(embed=embed)
            logger.info(f"Points added: {amount} points added to {user} by {ctx.author}")
        else:
            await ctx.send("❌ Failed to add points!")
    
    @admin_group.command(name='removepoints')
    @is_admin_or_owner()
    async def remove_points(self, ctx, user: discord.Member, amount: int):
        """Remove points from a user's balance"""
        if amount <= 0:
            await ctx.send("❌ Amount must be positive!")
            return
        
        # Get user
        db_user = await user_manager.get_user(user.id)
        if not db_user:
            await ctx.send(f"❌ User {user.mention} not found in database!")
            return
        
        if db_user.balance < amount:
            await ctx.send(f"❌ {user.mention} only has {db_user.balance:,} points (need {amount:,})!")
            return
        
        # Remove points
        success = await user_manager.deduct_points(
            user.id, amount, 'admin_adjustment',
            description=f"Points removed by admin {ctx.author.display_name}"
        )
        
        if success:
            # Get updated balance
            updated_user = await user_manager.get_user(user.id)
            
            embed = discord.Embed(
                title="✅ Points Removed",
                color=discord.Color.orange()
            )
            embed.add_field(name="User", value=user.mention, inline=True)
            embed.add_field(name="Points Removed", value=f"-{amount:,} points", inline=True)
            embed.add_field(name="New Balance", value=f"{updated_user.balance:,} points", inline=True)
            embed.add_field(name="Admin", value=ctx.author.mention, inline=True)
            
            await ctx.send(embed=embed)
            logger.info(f"Points removed: {amount} points removed from {user} by {ctx.author}")
        else:
            await ctx.send("❌ Failed to remove points!")
    
    @admin_group.command(name='userinfo')
    @is_admin_or_owner()
    async def user_info(self, ctx, user: discord.Member):
        """Show detailed user information"""
        db_user = await user_manager.get_user(user.id)
        if not db_user:
            await ctx.send(f"❌ User {user.mention} not found in database!")
            return
        
        embed = discord.Embed(
            title=f"👤 User Info: {user.display_name}",
            color=discord.Color.blue()
        )
        
        # Basic info
        embed.add_field(name="Discord ID", value=str(user.id), inline=True)
        embed.add_field(name="Balance", value=f"{db_user.balance:,} points", inline=True)
        embed.add_field(name="Status", value="🟢 Active" if db_user.is_registered else "🔴 Inactive", inline=True)
        
        # Betting stats
        stats = db_user.to_dict()
        embed.add_field(name="Total Bets", value=str(stats['total_bets_placed']), inline=True)
        embed.add_field(name="Win Rate", value=f"{stats['win_rate']}%", inline=True)
        embed.add_field(name="Net Profit", value=f"{stats['net_profit']:,} points", inline=True)
        
        # Dates
        if db_user.registration_date:
            embed.add_field(name="Registered", value=db_user.registration_date[:10], inline=True)
        if db_user.last_activity:
            embed.add_field(name="Last Active", value=db_user.last_activity[:10], inline=True)
        
        # Bonus claims
        daily_status = "✅ Available" if await user_manager.can_claim_daily(user.id) else "⏰ Claimed"
        bailout_status = "✅ Available" if await user_manager.can_claim_bailout(user.id) else "❌ Not needed" if db_user.balance > 0 else "⏰ Used"
        
        embed.add_field(name="Daily Bonus", value=daily_status, inline=True)
        embed.add_field(name="Bailout", value=bailout_status, inline=True)
        
        await ctx.send(embed=embed)
    
    @admin_group.command(name='refreshstats')
    @is_admin_or_owner()
    async def refresh_stats(self, ctx):
        """Refresh betting statistics for all users"""
        embed = discord.Embed(
            title="🔄 Refreshing Statistics...",
            description="Calculating betting statistics for all users...",
            color=discord.Color.orange()
        )
        
        message = await ctx.send(embed=embed)
        
        try:
            count = await user_manager.refresh_all_user_stats()
            
            embed = discord.Embed(
                title="✅ Statistics Refreshed",
                description=f"Successfully updated betting statistics for **{count}** users.",
                color=discord.Color.green()
            )
            
            embed.add_field(
                name="What was updated:",
                value="• Total bets placed\n• Total bets won\n• Total amount won\n• Total amount lost\n• Win rates",
                inline=False
            )
            
            embed.set_footer(text="All balance and stats commands will now show accurate data.")
            
            await message.edit(embed=embed)
            
        except Exception as e:
            logger.error(f"Error refreshing stats: {e}")
            embed = discord.Embed(
                title="❌ Error",
                description="Failed to refresh statistics. Check logs for details.",
                color=discord.Color.red()
            )
            await message.edit(embed=embed)

async def setup(bot):
    await bot.add_cog(Admin(bot))
