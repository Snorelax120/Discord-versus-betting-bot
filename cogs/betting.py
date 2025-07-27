import discord
from discord.ext import commands
import json
from datetime import datetime, timezone
from database.database import user_manager, db_manager
from database.models import User
import logging
import asyncio

logger = logging.getLogger(__name__)

class BetListAdminView(discord.ui.View):
    """Combined view with betting buttons + admin controls for bet list"""
    
    def __init__(self, bet_id: int, bet_title: str, options: list):
        super().__init__(timeout=600)
        self.bet_id = bet_id
        self.bet_title = bet_title
        self.options = options
        
        # Add betting buttons for each option (row 0-1)
        for i, option in enumerate(options[:5]):
            button = BetOptionButton(option, bet_id, bet_title, i)
            if i < 2:
                button.row = 0
            elif i < 4:
                button.row = 1
            else:
                button.row = 2
            self.add_item(button)
        
        # Add admin resolution buttons (row 2-3)
        resolve_button = discord.ui.Button(
            label="🛡️ Admin Resolve",
            style=discord.ButtonStyle.danger,
            custom_id=f"admin_resolve_{bet_id}",
            row=3
        )
        resolve_button.callback = self.show_admin_resolve
        self.add_item(resolve_button)
        
        # Add lock button
        lock_button = discord.ui.Button(
            label="🔒 Lock Bet",
            style=discord.ButtonStyle.secondary,
            custom_id=f"admin_lock_{bet_id}",
            row=3
        )
        lock_button.callback = self.lock_bet
        self.add_item(lock_button)
        
        # Add info button
        info_button = discord.ui.Button(
            label="📊 Detailed Info",
            style=discord.ButtonStyle.secondary,
            custom_id=f"admin_info_{bet_id}",
            row=4
        )
        info_button.callback = self.show_detailed_info
        self.add_item(info_button)
    
    async def show_admin_resolve(self, interaction: discord.Interaction):
        """Show admin resolution interface"""
        # Check admin permissions
        if not (interaction.user.guild_permissions.administrator or 
                any(role.name in ['Bet Master', 'Bet Moderator', 'Admin'] for role in interaction.user.roles)):
            await interaction.response.send_message("❌ You need admin permissions to resolve bets!", ephemeral=True)
            return
        
        # Get fresh bet data
        bet = await bet_manager.get_bet(self.bet_id)
        if not bet or bet['status'] not in ['open', 'locked']:
            await interaction.response.send_message(f"❌ Bet #{self.bet_id} cannot be resolved (Status: {bet['status'] if bet else 'Not found'})", ephemeral=True)
            return
        
        # Get bet statistics
        user_bets = await bet_manager.get_user_bets_for_bet(self.bet_id)
        
        embed = discord.Embed(
            title="🛡️ Admin: Resolve Bet",
            description=f"**{bet['title']}**",
            color=discord.Color.red()
        )
        
        embed.add_field(name="Bet ID", value=f"#{self.bet_id}", inline=True)
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
            value="• Click an option button to resolve with that winner\n• Click ❌ to cancel and refund all players",
            inline=False
        )
        
        embed.set_footer(text="Choose the winning option or cancel below:")
        
        # Create resolution view
        view = BetResolutionView(self.bet_id, bet['title'], bet['options'])
        
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
    
    async def lock_bet(self, interaction: discord.Interaction):
        """Lock the bet (no more bets allowed)"""
        # Check admin permissions
        if not (interaction.user.guild_permissions.administrator or 
                any(role.name in ['Bet Master', 'Bet Moderator', 'Admin'] for role in interaction.user.roles)):
            await interaction.response.send_message("❌ You need admin permissions to lock bets!", ephemeral=True)
            return
        
        try:
            # Update bet status to locked
            conn = await db_manager.get_connection()
            cursor = await conn.execute(
                "UPDATE bets SET status = 'locked' WHERE bet_id = ? AND status = 'open'",
                (self.bet_id,)
            )
            await conn.commit()
            
            if cursor.rowcount == 0:
                await interaction.response.send_message("❌ Bet is not in open status or doesn't exist.", ephemeral=True)
                return
            
            embed = discord.Embed(
                title="🔒 Bet Locked",
                description=f"**{self.bet_title}**\n\nBet #{self.bet_id} has been locked. No more bets can be placed.",
                color=discord.Color.orange()
            )
            embed.add_field(name="Admin", value=interaction.user.mention, inline=True)
            embed.set_footer(text="Use '🛡️ Admin Resolve' button to resolve when ready.")
            
            await interaction.response.send_message(embed=embed, ephemeral=True)
            logger.info(f"Bet #{self.bet_id} locked by {interaction.user}")
            
        except Exception as e:
            logger.error(f"Error locking bet: {e}")
            await interaction.response.send_message("❌ Failed to lock bet.", ephemeral=True)
    
    async def show_detailed_info(self, interaction: discord.Interaction):
        """Show detailed bet information"""
        # This will use the existing bet info functionality from BetButtonView
        bet_button_view = BetButtonView(self.bet_id, self.bet_title, self.options)
        await bet_button_view.show_bet_info(interaction)

class BetResolutionView(discord.ui.View):
    """View with buttons for resolving bets"""
    
    def __init__(self, bet_id: int, bet_title: str, options: list):
        super().__init__(timeout=600)  # 10 minute timeout
        self.bet_id = bet_id
        self.bet_title = bet_title
        self.options = options
        
        # Create resolution buttons for each option
        option_emojis = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣"]
        for i, option in enumerate(options[:5]):
            emoji = option_emojis[i] if i < len(option_emojis) else "▫️"
            button = discord.ui.Button(
                label=f"{emoji} {option}",
                style=discord.ButtonStyle.success,
                custom_id=f"resolve_{bet_id}_{i}",
                row=0 if i < 2 else 1 if i < 4 else 2
            )
            button.callback = self.create_resolve_callback(option)
            self.add_item(button)
        
        # Add cancel bet button
        cancel_button = discord.ui.Button(
            label="❌ Cancel Bet",
            style=discord.ButtonStyle.danger,
            custom_id=f"cancel_{bet_id}",
            row=3
        )
        cancel_button.callback = self.cancel_bet
        self.add_item(cancel_button)
        
        # Add lock bet button
        lock_button = discord.ui.Button(
            label="🔒 Lock Bet",
            style=discord.ButtonStyle.secondary,
            custom_id=f"lock_{bet_id}",
            row=3
        )
        lock_button.callback = self.lock_bet
        self.add_item(lock_button)
    
    def create_resolve_callback(self, winning_option: str):
        async def resolve_callback(interaction: discord.Interaction):
            await self.resolve_bet(interaction, winning_option)
        return resolve_callback
    
    async def resolve_bet(self, interaction: discord.Interaction, winning_option: str):
        """Resolve the bet with the selected option"""
        # Check admin permissions
        if not (interaction.user.guild_permissions.administrator or 
                any(role.name in ['Bet Master', 'Bet Moderator', 'Admin'] for role in interaction.user.roles)):
            await interaction.response.send_message("❌ You need admin permissions to resolve bets!", ephemeral=True)
            return
        
        # Show confirmation modal
        modal = BetResolutionConfirmModal(self.bet_id, self.bet_title, winning_option)
        await interaction.response.send_modal(modal)
    
    async def cancel_bet(self, interaction: discord.Interaction):
        """Cancel the bet and refund all players"""
        # Check admin permissions
        if not (interaction.user.guild_permissions.administrator or 
                any(role.name in ['Bet Master', 'Bet Moderator', 'Admin'] for role in interaction.user.roles)):
            await interaction.response.send_message("❌ You need admin permissions to cancel bets!", ephemeral=True)
            return
        
        modal = BetCancelConfirmModal(self.bet_id, self.bet_title)
        await interaction.response.send_modal(modal)
    
    async def lock_bet(self, interaction: discord.Interaction):
        """Lock the bet (no more bets allowed)"""
        # Check admin permissions
        if not (interaction.user.guild_permissions.administrator or 
                any(role.name in ['Bet Master', 'Bet Moderator', 'Admin'] for role in interaction.user.roles)):
            await interaction.response.send_message("❌ You need admin permissions to lock bets!", ephemeral=True)
            return
        
        try:
            # Update bet status to locked
            conn = await db_manager.get_connection()
            await conn.execute(
                "UPDATE bets SET status = 'locked' WHERE bet_id = ? AND status = 'open'",
                (self.bet_id,)
            )
            await conn.commit()
            
            embed = discord.Embed(
                title="🔒 Bet Locked",
                description=f"**{self.bet_title}**\n\nBet #{self.bet_id} has been locked. No more bets can be placed.",
                color=discord.Color.orange()
            )
            embed.add_field(name="Admin", value=interaction.user.mention, inline=True)
            embed.set_footer(text="Use the resolution buttons when ready to resolve the bet.")
            
            await interaction.response.send_message(embed=embed)
            logger.info(f"Bet #{self.bet_id} locked by {interaction.user}")
            
        except Exception as e:
            logger.error(f"Error locking bet: {e}")
            await interaction.response.send_message("❌ Failed to lock bet.", ephemeral=True)

class BetResolutionConfirmModal(discord.ui.Modal):
    """Confirmation modal for bet resolution"""
    
    def __init__(self, bet_id: int, bet_title: str, winning_option: str):
        super().__init__(title=f"Resolve Bet #{bet_id}")
        self.bet_id = bet_id
        self.bet_title = bet_title
        self.winning_option = winning_option
        
        # Confirmation input
        self.confirmation_input = discord.ui.TextInput(
            label=f"Confirm winner: {winning_option}",
            placeholder=f"Type 'CONFIRM' to resolve bet with '{winning_option}' as winner",
            min_length=7,
            max_length=7,
            required=True
        )
        self.add_item(self.confirmation_input)
        
        # Optional reason
        self.reason_input = discord.ui.TextInput(
            label="Resolution Reason (Optional)",
            placeholder="e.g., Official result announced, match completed...",
            style=discord.TextStyle.paragraph,
            min_length=0,
            max_length=200,
            required=False
        )
        self.add_item(self.reason_input)
    
    async def on_submit(self, interaction: discord.Interaction):
        if self.confirmation_input.value.upper() != "CONFIRM":
            await interaction.response.send_message("❌ You must type 'CONFIRM' to resolve the bet.", ephemeral=True)
            return
        
        try:
            # Resolve the bet
            result = await bet_manager.resolve_bet(self.bet_id, self.winning_option)
            
            if not result['success']:
                await interaction.response.send_message(f"❌ Failed to resolve bet: {result.get('error', 'Unknown error')}", ephemeral=True)
                return
            
            # Create success embed
            embed = discord.Embed(
                title="✅ Bet Resolved Successfully!",
                description=f"**{self.bet_title}**",
                color=discord.Color.green()
            )
            
            embed.add_field(name="Bet ID", value=f"#{self.bet_id}", inline=True)
            embed.add_field(name="Winning Option", value=f"🏆 **{result['winning_option']}**", inline=True)
            embed.add_field(name="Admin", value=interaction.user.mention, inline=True)
            
            embed.add_field(name="Results", value=f"**{result['winners']}** winners, **{result['losers']}** losers", inline=True)
            embed.add_field(name="Total Pool", value=f"{result['total_pool']:,} points", inline=True)
            embed.add_field(name="Status", value="🏁 Resolved", inline=True)
            
            # Show reason if provided
            reason = self.reason_input.value.strip()
            if reason:
                embed.add_field(name="Reason", value=reason, inline=False)
            
            # Show top payouts
            if result['payouts']:
                payout_text = ""
                for payout in result['payouts'][:5]:  # Show first 5 payouts
                    profit = payout['winnings'] - payout['bet_amount']
                    payout_text += f"• {payout['username']}: +{profit:,} profit ({payout['winnings']:,} total)\n"
                
                if len(result['payouts']) > 5:
                    payout_text += f"... and {len(result['payouts']) - 5} more winners"
                
                embed.add_field(name="Top Payouts", value=payout_text, inline=False)
            
            embed.set_footer(text="All winnings have been distributed!")
            
            await interaction.response.send_message(embed=embed)
            logger.info(f"Bet #{self.bet_id} resolved by {interaction.user} - Winner: {self.winning_option}")
            
        except Exception as e:
            logger.error(f"Error resolving bet: {e}")
            await interaction.response.send_message("❌ An error occurred while resolving the bet.", ephemeral=True)

class BetCancelConfirmModal(discord.ui.Modal):
    """Confirmation modal for bet cancellation"""
    
    def __init__(self, bet_id: int, bet_title: str):
        super().__init__(title=f"Cancel Bet #{bet_id}")
        self.bet_id = bet_id
        self.bet_title = bet_title
        
        # Confirmation input
        self.confirmation_input = discord.ui.TextInput(
            label="Confirm cancellation",
            placeholder="Type 'CANCEL' to cancel bet and refund all players",
            min_length=6,
            max_length=6,
            required=True
        )
        self.add_item(self.confirmation_input)
        
        # Reason for cancellation
        self.reason_input = discord.ui.TextInput(
            label="Cancellation Reason",
            placeholder="e.g., Event cancelled, insufficient participants...",
            style=discord.TextStyle.paragraph,
            min_length=5,
            max_length=200,
            required=True
        )
        self.add_item(self.reason_input)
    
    async def on_submit(self, interaction: discord.Interaction):
        if self.confirmation_input.value.upper() != "CANCEL":
            await interaction.response.send_message("❌ You must type 'CANCEL' to cancel the bet.", ephemeral=True)
            return
        
        try:
            # Get bet details and all user bets
            bet = await bet_manager.get_bet(self.bet_id)
            if not bet or bet['status'] not in ['open', 'locked']:
                await interaction.response.send_message("❌ Bet cannot be cancelled at this time.", ephemeral=True)
                return
            
            user_bets = await bet_manager.get_user_bets_for_bet(self.bet_id)
            
            # Refund all players
            total_refunded = 0
            refund_count = 0
            
            conn = await db_manager.get_connection()
            
            for user_bet in user_bets:
                if user_bet['status'] == 'pending':
                    # Refund the user
                    await user_manager.add_points(
                        user_bet['user_id'], user_bet['amount'], 'bet_refunded',
                        self.bet_id, f"Bet cancelled - {self.reason_input.value.strip()[:50]}"
                    )
                    
                    # Update user bet status
                    await conn.execute(
                        "UPDATE user_bets SET status = 'refunded' WHERE id = ?",
                        (user_bet['id'],)
                    )
                    
                    total_refunded += user_bet['amount']
                    refund_count += 1
            
            # Update bet status
            now = datetime.now(timezone.utc).isoformat()
            await conn.execute(
                "UPDATE bets SET status = 'cancelled', resolved_at = ? WHERE bet_id = ?",
                (now, self.bet_id)
            )
            
            await conn.commit()
            
            # Create response embed
            embed = discord.Embed(
                title="❌ Bet Cancelled",
                description=f"**{self.bet_title}**",
                color=discord.Color.red()
            )
            
            embed.add_field(name="Bet ID", value=f"#{self.bet_id}", inline=True)
            embed.add_field(name="Admin", value=interaction.user.mention, inline=True)
            embed.add_field(name="Status", value="❌ Cancelled", inline=True)
            
            embed.add_field(name="Refunds", value=f"**{refund_count}** players refunded", inline=True)
            embed.add_field(name="Total Refunded", value=f"{total_refunded:,} points", inline=True)
            embed.add_field(name="Original Pool", value=f"{bet['total_pool']:,} points", inline=True)
            
            embed.add_field(name="Reason", value=self.reason_input.value.strip(), inline=False)
            
            embed.set_footer(text="All players have been refunded their bet amounts.")
            
            await interaction.response.send_message(embed=embed)
            logger.info(f"Bet #{self.bet_id} cancelled by {interaction.user} - Reason: {self.reason_input.value.strip()}")
            
        except Exception as e:
            logger.error(f"Error cancelling bet: {e}")
            await interaction.response.send_message("❌ An error occurred while cancelling the bet.", ephemeral=True)

class BetCreationModal(discord.ui.Modal):
    """Modal for creating a new bet"""
    
    def __init__(self):
        super().__init__(title="🎲 Create New Bet")
        
        # Bet title/question
        self.title_input = discord.ui.TextInput(
            label="Bet Question/Title",
            placeholder="e.g., Who will win the match?",
            min_length=5,
            max_length=200,
            required=True
        )
        self.add_item(self.title_input)
        
        # Description (optional)
        self.description_input = discord.ui.TextInput(
            label="Description (Optional)",
            placeholder="Additional details about the bet...",
            style=discord.TextStyle.paragraph,
            min_length=0,
            max_length=500,
            required=False
        )
        self.add_item(self.description_input)
        
        # Options (comma separated)
        self.options_input = discord.ui.TextInput(
            label="Bet Options (comma separated)",
            placeholder="e.g., Team A, Team B, Draw",
            min_length=5,
            max_length=300,
            required=True
        )
        self.add_item(self.options_input)
    
    async def on_submit(self, interaction: discord.Interaction):
        try:
            # Parse options
            options_text = self.options_input.value.strip()
            options = [opt.strip() for opt in options_text.split(',') if opt.strip()]
            
            # Validate options
            if len(options) < 2:
                await interaction.response.send_message("❌ You need at least 2 options for a bet!", ephemeral=True)
                return
            
            if len(options) > 5:
                await interaction.response.send_message("❌ Maximum 5 options allowed per bet!", ephemeral=True)
                return
            
            # Check for duplicate options
            if len(options) != len(set(opt.lower() for opt in options)):
                await interaction.response.send_message("❌ Duplicate options found! Each option must be unique.", ephemeral=True)
                return
            
            # Auto-register user
            db_user, is_new = await user_manager.get_or_create_user(
                interaction.user.id, interaction.user.display_name
            )
            
            # Determine bet type
            bet_type = 'yn' if len(options) == 2 else 'multi'
            
            # Create the bet
            title = self.title_input.value.strip()
            description = self.description_input.value.strip() or None
            
            bet_id = await bet_manager.create_bet(
                interaction.user.id, bet_type, title, options, description
            )
            
            # Create success embed
            embed = discord.Embed(
                title="🎲 Bet Created Successfully!",
                description=f"**{title}**",
                color=discord.Color.green()
            )
            
            embed.add_field(name="Bet ID", value=f"#{bet_id}", inline=True)
            embed.add_field(name="Creator", value=interaction.user.mention, inline=True)
            embed.add_field(name="Type", value="Custom" if len(options) > 2 else "Yes/No", inline=True)
            
            # Show options with emojis
            options_display = ""
            option_emojis = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣"]
            for i, option in enumerate(options):
                emoji = option_emojis[i] if i < len(option_emojis) else "▫️"
                options_display += f"{emoji} **{option}**\n"
            
            embed.add_field(name="Options", value=options_display, inline=False)
            
            if description:
                embed.add_field(name="Description", value=description, inline=False)
            
            embed.add_field(
                name="Status",
                value="🟢 **Open** - Ready for bets!",
                inline=False
            )
            
            embed.set_footer(text="Click the buttons below to place your bet!")
            
            # Create button view for the new bet
            view = BetButtonView(bet_id, title, options)
            
            await interaction.response.send_message(embed=embed, view=view)
            logger.info(f"Bet created via modal: #{bet_id} by {interaction.user} - {title} - {len(options)} options")
            
        except Exception as e:
            logger.error(f"Error in bet creation modal: {e}")
            await interaction.response.send_message("❌ An error occurred while creating your bet. Please try again.", ephemeral=True)

class BetCreationView(discord.ui.View):
    """View for bet creation options"""
    
    def __init__(self):
        super().__init__(timeout=300)
    
    @discord.ui.button(label="🎲 Create Custom Bet", style=discord.ButtonStyle.primary)
    async def create_custom_bet(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Open modal for custom bet creation"""
        modal = BetCreationModal()
        await interaction.response.send_modal(modal)
    
    @discord.ui.button(label="⚡ Quick Yes/No Bet", style=discord.ButtonStyle.success)
    async def create_quick_bet(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Create a quick yes/no bet with simple modal"""
        modal = QuickYesNoModal()
        await interaction.response.send_modal(modal)

class QuickYesNoModal(discord.ui.Modal):
    """Quick modal for simple yes/no bets"""
    
    def __init__(self):
        super().__init__(title="⚡ Quick Yes/No Bet")
        
        # Just the question
        self.question_input = discord.ui.TextInput(
            label="Your Yes/No Question",
            placeholder="e.g., Will it rain tomorrow?",
            min_length=5,
            max_length=200,
            required=True
        )
        self.add_item(self.question_input)
        
        # Optional description
        self.description_input = discord.ui.TextInput(
            label="Description (Optional)",
            placeholder="Additional details...",
            style=discord.TextStyle.paragraph,
            min_length=0,
            max_length=300,
            required=False
        )
        self.add_item(self.description_input)
    
    async def on_submit(self, interaction: discord.Interaction):
        try:
            # Auto-register user
            db_user, is_new = await user_manager.get_or_create_user(
                interaction.user.id, interaction.user.display_name
            )
            
            # Create yes/no bet
            title = self.question_input.value.strip()
            description = self.description_input.value.strip() or None
            options = ["Yes", "No"]
            
            bet_id = await bet_manager.create_bet(
                interaction.user.id, 'yn', title, options, description
            )
            
            # Create success embed
            embed = discord.Embed(
                title="⚡ Quick Bet Created!",
                description=f"**{title}**",
                color=discord.Color.green()
            )
            
            embed.add_field(name="Bet ID", value=f"#{bet_id}", inline=True)
            embed.add_field(name="Type", value="Yes/No", inline=True)
            embed.add_field(name="Creator", value=interaction.user.mention, inline=True)
            
            if description:
                embed.add_field(name="Description", value=description, inline=False)
            
            embed.add_field(
                name="Options",
                value="1️⃣ **Yes**\n2️⃣ **No**",
                inline=False
            )
            
            embed.set_footer(text="Click the buttons below to place your bet!")
            
            # Create button view
            view = BetButtonView(bet_id, title, options)
            
            await interaction.response.send_message(embed=embed, view=view)
            logger.info(f"Quick Y/N bet created: #{bet_id} by {interaction.user} - {title}")
            
        except Exception as e:
            logger.error(f"Error in quick bet modal: {e}")
            await interaction.response.send_message("❌ An error occurred while creating your bet. Please try again.", ephemeral=True)

class QuickBetView(discord.ui.View):
    """View with quick bet amount buttons"""
    
    def __init__(self, bet_id: int, option: str, bet_title: str, user_balance: int):
        super().__init__(timeout=60)
        self.bet_id = bet_id
        self.option = option
        self.bet_title = bet_title
        
        # Add quick amount buttons based on user balance
        amounts = []
        if user_balance >= 50:
            amounts.append(50)
        if user_balance >= 100:
            amounts.append(100)
        if user_balance >= 250:
            amounts.append(250)
        if user_balance >= 500:
            amounts.append(500)
        if user_balance >= 1000:
            amounts.append(1000)
        
        # Add buttons for each amount
        for amount in amounts[:4]:  # Max 4 quick buttons
            button = discord.ui.Button(
                label=f"{amount:,} points",
                style=discord.ButtonStyle.success,
                custom_id=f"quick_bet_{amount}"
            )
            button.callback = self.create_amount_callback(amount)
            self.add_item(button)
        
        # Add custom amount button
        custom_button = discord.ui.Button(
            label="💰 Custom Amount",
            style=discord.ButtonStyle.primary,
            custom_id="custom_amount"
        )
        custom_button.callback = self.show_custom_modal
        self.add_item(custom_button)
    
    def create_amount_callback(self, amount: int):
        async def amount_callback(interaction: discord.Interaction):
            await self.place_bet_with_amount(interaction, amount)
        return amount_callback
    
    async def show_custom_modal(self, interaction: discord.Interaction):
        modal = BetAmountModal(self.bet_id, self.option, self.bet_title)
        await interaction.response.send_modal(modal)
    
    async def place_bet_with_amount(self, interaction: discord.Interaction, amount: int):
        """Place bet with specified amount"""
        try:
            # Auto-register user
            db_user, is_new = await user_manager.get_or_create_user(
                interaction.user.id, interaction.user.display_name
            )
            
            # Check balance
            if db_user.balance < amount:
                embed = discord.Embed(
                    title="❌ Insufficient Balance",
                    description=f"You need **{amount:,}** points but only have **{db_user.balance:,}** points.",
                    color=discord.Color.red()
                )
                await interaction.response.send_message(embed=embed, ephemeral=True)
                return
            
            # Attempt to place bet
            success = await bet_manager.place_bet(interaction.user.id, self.bet_id, self.option, amount)
            
            if not success:
                await interaction.response.send_message("❌ Failed to place bet. You may have already bet on this or there was an error.", ephemeral=True)
                return
            
            # Get updated user balance
            updated_user = await user_manager.get_user(interaction.user.id)
            
            embed = discord.Embed(
                title="✅ Bet Placed Successfully!",
                color=discord.Color.green()
            )
            
            embed.add_field(name="Bet", value=f"#{self.bet_id}: {self.bet_title}", inline=False)
            embed.add_field(name="Your Choice", value=f"**{self.option}**", inline=True)
            embed.add_field(name="Amount", value=f"**{amount:,}** points", inline=True)
            embed.add_field(name="New Balance", value=f"**{updated_user.balance:,}** points", inline=True)
            
            embed.set_footer(text="Good luck! Your bet has been recorded.")
            
            await interaction.response.send_message(embed=embed, ephemeral=True)
            logger.info(f"Bet placed: {interaction.user} bet {amount} on '{self.option}' for bet #{self.bet_id}")
            
        except Exception as e:
            logger.error(f"Error placing bet: {e}")
            await interaction.response.send_message("❌ An error occurred while placing your bet.", ephemeral=True)

class BetAmountModal(discord.ui.Modal):
    """Modal for entering custom bet amount"""
    
    def __init__(self, bet_id: int, option: str, bet_title: str):
        super().__init__(title=f"Custom Bet: {option}")
        self.bet_id = bet_id
        self.option = option
        self.bet_title = bet_title
        
        # Add amount input
        self.amount_input = discord.ui.TextInput(
            label="Bet Amount",
            placeholder="Enter amount in points (e.g., 100)",
            min_length=1,
            max_length=10,
            required=True
        )
        self.add_item(self.amount_input)
    
    async def on_submit(self, interaction: discord.Interaction):
        try:
            amount = int(self.amount_input.value)
            if amount <= 0:
                await interaction.response.send_message("❌ Bet amount must be positive!", ephemeral=True)
                return
            
            # Auto-register user
            db_user, is_new = await user_manager.get_or_create_user(
                interaction.user.id, interaction.user.display_name
            )
            
            # Check balance
            if db_user.balance < amount:
                embed = discord.Embed(
                    title="❌ Insufficient Balance",
                    description=f"You need **{amount:,}** points but only have **{db_user.balance:,}** points.",
                    color=discord.Color.red()
                )
                embed.add_field(
                    name="Get More Points",
                    value="• Use `!daily` for daily bonus\n• Use `!bailout` if balance is 0",
                    inline=False
                )
                await interaction.response.send_message(embed=embed, ephemeral=True)
                return
            
            # Attempt to place bet
            success = await bet_manager.place_bet(interaction.user.id, self.bet_id, self.option, amount)
            
            if not success:
                await interaction.response.send_message("❌ Failed to place bet. You may have already bet on this or there was an error.", ephemeral=True)
                return
            
            # Get updated user balance
            updated_user = await user_manager.get_user(interaction.user.id)
            
            embed = discord.Embed(
                title="✅ Bet Placed Successfully!",
                color=discord.Color.green()
            )
            
            embed.add_field(name="Bet", value=f"#{self.bet_id}: {self.bet_title}", inline=False)
            embed.add_field(name="Your Choice", value=f"**{self.option}**", inline=True)
            embed.add_field(name="Amount", value=f"**{amount:,}** points", inline=True)
            embed.add_field(name="New Balance", value=f"**{updated_user.balance:,}** points", inline=True)
            
            embed.set_footer(text="Good luck! Your bet has been recorded.")
            
            await interaction.response.send_message(embed=embed, ephemeral=True)
            logger.info(f"Bet placed: {interaction.user} bet {amount} on '{self.option}' for bet #{self.bet_id}")
            
        except ValueError:
            await interaction.response.send_message("❌ Please enter a valid number for the bet amount!", ephemeral=True)
        except Exception as e:
            logger.error(f"Error in bet amount modal: {e}")
            await interaction.response.send_message("❌ An error occurred while placing your bet.", ephemeral=True)

class BetButtonView(discord.ui.View):
    """View with buttons for betting options"""
    
    def __init__(self, bet_id: int, bet_title: str, options: list):
        super().__init__(timeout=None)  # Persistent view
        self.bet_id = bet_id
        self.bet_title = bet_title
        self.options = options
        
        # Create buttons for each option (up to 5 buttons max)
        for i, option in enumerate(options[:5]):
            button = BetOptionButton(option, bet_id, bet_title, i)
            self.add_item(button)
        
        # Add info button
        info_button = discord.ui.Button(
            label="📊 Bet Info",
            style=discord.ButtonStyle.secondary,
            custom_id=f"bet_info_{bet_id}"
        )
        info_button.callback = self.show_bet_info
        self.add_item(info_button)
    
    async def show_bet_info(self, interaction: discord.Interaction):
        """Show detailed bet information"""
        bet = await bet_manager.get_bet(self.bet_id)
        if not bet:
            await interaction.response.send_message("❌ Bet not found!", ephemeral=True)
            return
        
        # Get creator info
        try:
            creator = interaction.client.get_user(bet['creator_id'])
            creator_name = creator.display_name if creator else "Unknown"
        except:
            creator_name = "Unknown"
        
        # Get all user bets for this bet
        user_bets = await bet_manager.get_user_bets_for_bet(self.bet_id)
        
        embed = discord.Embed(
            title=f"🎲 Bet #{self.bet_id} Details",
            description=f"**{bet['title']}**",
            color=discord.Color.blue()
        )
        
        embed.add_field(name="Creator", value=creator_name, inline=True)
        embed.add_field(name="Status", value=f"🟢 {bet['status'].title()}", inline=True)
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
        for option in bet['options']:
            stats = option_stats.get(option, {'count': 0, 'amount': 0})
            options_text += f"**{option}**: {stats['count']} bets, {stats['amount']:,} points\n"
        
        embed.add_field(name="Options & Bets", value=options_text or "No bets placed yet", inline=False)
        
        # Show recent bets
        if user_bets:
            recent_bets_text = ""
            for user_bet in user_bets[:5]:  # Show last 5
                recent_bets_text += f"• {user_bet['username']}: {user_bet['amount']:,} on {user_bet['option_chosen']}\n"
            
            embed.add_field(
                name=f"Recent Bets ({len(user_bets)} total)",
                value=recent_bets_text,
                inline=False
            )
        
        await interaction.response.send_message(embed=embed, ephemeral=True)

class BetOptionButton(discord.ui.Button):
    """Button for a specific betting option"""
    
    def __init__(self, option: str, bet_id: int, bet_title: str, index: int):
        # Use different colors for different options
        colors = [
            discord.ButtonStyle.primary,   # Blue
            discord.ButtonStyle.danger,    # Red  
            discord.ButtonStyle.success,   # Green
            discord.ButtonStyle.secondary, # Gray
            discord.ButtonStyle.secondary  # Gray
        ]
        
        super().__init__(
            label=option,
            style=colors[index],
            custom_id=f"bet_{bet_id}_{option.lower().replace(' ', '_')}"
        )
        self.option = option
        self.bet_id = bet_id
        self.bet_title = bet_title
    
    async def callback(self, interaction: discord.Interaction):
        """Handle button click - show amount modal"""
        # Check if bet is still open
        bet = await bet_manager.get_bet(self.bet_id)
        if not bet or bet['status'] != 'open':
            await interaction.response.send_message(
                f"❌ This bet is no longer accepting wagers (Status: {bet['status'] if bet else 'Not found'})", 
                ephemeral=True
            )
            return
        
        # Check if user already bet
        db_user = await user_manager.get_user(interaction.user.id)
        if db_user:
            # Check existing bet
            conn = await db_manager.get_connection()
            cursor = await conn.execute(
                "SELECT option_chosen FROM user_bets WHERE user_id = ? AND bet_id = ?",
                (interaction.user.id, self.bet_id)
            )
            existing_bet = await cursor.fetchone()
            
            if existing_bet:
                await interaction.response.send_message(
                    f"❌ You already bet on **{existing_bet[0]}** for this question!", 
                    ephemeral=True
                )
                return
        
        # Get user balance for quick bet options
        db_user, is_new = await user_manager.get_or_create_user(
            interaction.user.id, interaction.user.display_name
        )
        
        # Show quick bet view with amount buttons
        embed = discord.Embed(
            title=f"🎲 Place Bet: {self.option}",
            description=f"**{self.bet_title}**\n\nYour balance: **{db_user.balance:,}** points",
            color=discord.Color.blue()
        )
        embed.add_field(name="Your Choice", value=f"**{self.option}**", inline=True)
        embed.set_footer(text="Choose a quick amount or enter a custom amount!")
        
        view = QuickBetView(self.bet_id, self.option, self.bet_title, db_user.balance)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

class BetManager:
    """Manages bet-related database operations"""
    
    def __init__(self, db_manager):
        self.db = db_manager
    
    async def create_bet(self, creator_id: int, bet_type: str, title: str, options: list, description: str = None) -> int:
        """Create a new bet and return bet_id"""
        now = datetime.now(timezone.utc).isoformat()
        options_json = json.dumps(options)
        
        conn = await self.db.get_connection()
        cursor = await conn.execute("""
            INSERT INTO bets (
                creator_id, bet_type, title, description, options, 
                status, created_at
            ) VALUES (?, ?, ?, ?, ?, 'open', ?)
        """, (creator_id, bet_type, title, description, options_json, now))
        
        await conn.commit()
        return cursor.lastrowid
    
    async def get_bet(self, bet_id: int):
        """Get bet by ID"""
        conn = await self.db.get_connection()
        cursor = await conn.execute(
            "SELECT * FROM bets WHERE bet_id = ?", 
            (bet_id,)
        )
        row = await cursor.fetchone()
        
        if row:
            # Convert to dict and parse JSON fields
            bet = dict(row)
            bet['options'] = json.loads(bet['options'])
            if bet['odds']:
                bet['odds'] = json.loads(bet['odds'])
            return bet
        return None
    
    async def get_active_bets(self, limit: int = 10):
        """Get active bets"""
        conn = await self.db.get_connection()
        cursor = await conn.execute(
            "SELECT * FROM bets WHERE status = 'open' ORDER BY created_at DESC LIMIT ?", 
            (limit,)
        )
        rows = await cursor.fetchall()
        
        bets = []
        for row in rows:
            bet = dict(row)
            bet['options'] = json.loads(bet['options'])
            if bet['odds']:
                bet['odds'] = json.loads(bet['odds'])
            bets.append(bet)
        return bets
    
    async def place_bet(self, user_id: int, bet_id: int, option: str, amount: int) -> bool:
        """Place a bet on an option"""
        # Check if bet exists and is open
        bet = await self.get_bet(bet_id)
        if not bet or bet['status'] != 'open':
            return False
        
        # Check if option is valid
        if option.lower() not in [opt.lower() for opt in bet['options']]:
            return False
        
        # Check if user has already bet on this
        conn = await self.db.get_connection()
        cursor = await conn.execute(
            "SELECT id FROM user_bets WHERE user_id = ? AND bet_id = ?",
            (user_id, bet_id)
        )
        if await cursor.fetchone():
            return False  # Already bet on this
        
        # Check user balance and deduct points
        success = await user_manager.deduct_points(
            user_id, amount, 'bet_placed', bet_id, 
            f"Bet placed on '{bet['title']}' - {option}"
        )
        
        if not success:
            return False
        
        # Record the bet
        now = datetime.now(timezone.utc).isoformat()
        await conn.execute("""
            INSERT INTO user_bets (
                user_id, bet_id, option_chosen, amount, created_at
            ) VALUES (?, ?, ?, ?, ?)
        """, (user_id, bet_id, option, amount, now))
        
        # Update bet total pool
        await conn.execute(
            "UPDATE bets SET total_pool = total_pool + ? WHERE bet_id = ?",
            (amount, bet_id)
        )
        
        await conn.commit()
        return True
    
    async def get_user_bets_for_bet(self, bet_id: int):
        """Get all user bets for a specific bet"""
        conn = await self.db.get_connection()
        cursor = await conn.execute("""
            SELECT ub.*, u.username 
            FROM user_bets ub 
            JOIN users u ON ub.user_id = u.discord_id 
            WHERE ub.bet_id = ?
            ORDER BY ub.created_at DESC
        """, (bet_id,))
        
        return await cursor.fetchall()
    
    async def resolve_bet(self, bet_id: int, winning_option: str) -> dict:
        """Resolve a bet and distribute winnings"""
        bet = await self.get_bet(bet_id)
        if not bet or bet['status'] != 'open':
            return {'success': False, 'error': 'Bet not found or already resolved'}
        
        # Check if winning option is valid
        if winning_option.lower() not in [opt.lower() for opt in bet['options']]:
            return {'success': False, 'error': 'Invalid winning option'}
        
        conn = await self.db.get_connection()
        
        # Get all bets for this bet_id
        user_bets = await self.get_user_bets_for_bet(bet_id)
        
        # Calculate winners and losers
        winners = []
        losers = []
        total_winning_amount = 0
        total_losing_amount = 0
        
        for user_bet in user_bets:
            if user_bet['option_chosen'].lower() == winning_option.lower():
                winners.append(user_bet)
                total_winning_amount += user_bet['amount']
            else:
                losers.append(user_bet)
                total_losing_amount += user_bet['amount']
        
        # Calculate payouts (simple proportional distribution)
        payout_results = []
        
        if winners and total_losing_amount > 0:
            # Winners split the pot proportionally
            for winner in winners:
                # Winner gets their bet back + proportional share of losers' money
                proportion = winner['amount'] / total_winning_amount
                winnings = winner['amount'] + int(total_losing_amount * proportion)
                
                # Add winnings to user balance
                await user_manager.add_points(
                    winner['user_id'], winnings, 'bet_won', bet_id,
                    f"Won bet '{bet['title']}' - {winning_option}"
                )
                
                # Update user bet status
                await conn.execute(
                    "UPDATE user_bets SET status = 'won', potential_payout = ? WHERE id = ?",
                    (winnings, winner['id'])
                )
                
                payout_results.append({
                    'user_id': winner['user_id'],
                    'username': winner['username'],
                    'bet_amount': winner['amount'],
                    'winnings': winnings,
                    'profit': winnings - winner['amount']
                })
        
        elif winners and total_losing_amount == 0:
            # No losers, refund everyone
            for winner in winners:
                await user_manager.add_points(
                    winner['user_id'], winner['amount'], 'bet_refunded', bet_id,
                    f"Bet refunded '{bet['title']}' - no opposing bets"
                )
                
                await conn.execute(
                    "UPDATE user_bets SET status = 'refunded', potential_payout = ? WHERE id = ?",
                    (winner['amount'], winner['id'])
                )
        
        # Mark losing bets
        for loser in losers:
            await conn.execute(
                "UPDATE user_bets SET status = 'lost' WHERE id = ?",
                (loser['id'],)
            )
        
        # Update bet status
        now = datetime.now(timezone.utc).isoformat()
        await conn.execute(
            "UPDATE bets SET status = 'resolved', winning_option = ?, resolved_at = ? WHERE bet_id = ?",
            (winning_option, now, bet_id)
        )
        
        await conn.commit()
        
        return {
            'success': True,
            'winners': len(winners),
            'losers': len(losers),
            'total_pool': bet['total_pool'],
            'winning_option': winning_option,
            'payouts': payout_results
        }

# Global bet manager instance
bet_manager = BetManager(db_manager)

class Betting(commands.Cog):
    """Betting commands for the betting bot"""
    
    def __init__(self, bot):
        self.bot = bot
    
    @commands.group(name='bet', invoke_without_command=True)
    async def bet_group(self, ctx):
        """Betting command group"""
        if ctx.invoked_subcommand is None:
            embed = discord.Embed(
                title="🎲 Betting Commands",
                description="Use these commands to create and place bets:",
                color=discord.Color.blue()
            )
            
            embed.add_field(
                name="Create Bets",
                value="`!bet create \"Question?\" \"Option 1\" \"Option 2\"`\n"
                      "`!bet create \"Will it rain?\" \"Yes\" \"No\"`",
                inline=False
            )
            
            embed.add_field(
                name="Place Bets",
                value="`!bet place <bet_id> <option> <amount>`\n"
                      "`!bet place 1 yes 100`",
                inline=False
            )
            
            embed.add_field(
                name="View Bets",
                value="`!bet list` - Show active bets (admins see resolve controls)\n"
                      "`!bet info <bet_id>` - Show bet details\n"
                      "`!bet mybets` - Show your active bets",
                inline=False
            )
            
            embed.set_footer(text="Start by creating a bet or check !bet list for active bets!")
            await ctx.send(embed=embed)
    
    @bet_group.command(name='create')
    async def create_bet(self, ctx):
        """Create a new bet with interactive UI"""
        embed = discord.Embed(
            title="🎲 Create a New Bet",
            description="Choose how you'd like to create your bet:",
            color=discord.Color.blue()
        )
        
        embed.add_field(
            name="🎲 Custom Bet",
            value="Create a bet with 2-5 custom options\nFull control over question and description",
            inline=False
        )
        
        embed.add_field(
            name="⚡ Quick Yes/No",
            value="Fast creation for simple yes/no questions\nPerfect for quick polls and predictions",
            inline=False
        )
        
        embed.set_footer(text="Click a button below to get started!")
        
        view = BetCreationView()
        await ctx.send(embed=embed, view=view)
    
    @bet_group.command(name='quick')
    async def create_quick_bet(self, ctx, *, question: str = None):
        """Create a quick yes/no bet (legacy command for backwards compatibility)"""
        if question:
            # Auto-register user
            db_user, is_new = await user_manager.get_or_create_user(
                ctx.author.id, ctx.author.display_name
            )
            
            # Create yes/no bet
            options = ["Yes", "No"]
            bet_id = await bet_manager.create_bet(
                ctx.author.id, 'yn', question, options, None
            )
            
            embed = discord.Embed(
                title="⚡ Quick Bet Created!",
                description=f"**{question}**",
                color=discord.Color.green()
            )
            
            embed.add_field(name="Bet ID", value=f"#{bet_id}", inline=True)
            embed.add_field(name="Type", value="Yes/No", inline=True)
            embed.add_field(name="Creator", value=ctx.author.mention, inline=True)
            
            embed.add_field(
                name="Options",
                value="1️⃣ **Yes**\n2️⃣ **No**",
                inline=False
            )
            
            embed.set_footer(text="Click the buttons below to place your bet!")
            
            # Create button view
            view = BetButtonView(bet_id, question, options)
            
            await ctx.send(embed=embed, view=view)
            logger.info(f"Quick bet created via command: #{bet_id} by {ctx.author} - {question}")
        else:
            # Show quick creation modal
            embed = discord.Embed(
                title="⚡ Quick Yes/No Bet",
                description="Create a simple yes/no bet quickly!",
                color=discord.Color.green()
            )
            embed.set_footer(text="Click the button below to start!")
            
            class QuickBetButton(discord.ui.View):
                def __init__(self):
                    super().__init__(timeout=300)
                
                @discord.ui.button(label="⚡ Create Yes/No Bet", style=discord.ButtonStyle.success)
                async def quick_bet(self, interaction: discord.Interaction, button: discord.ui.Button):
                    modal = QuickYesNoModal()
                    await interaction.response.send_modal(modal)
            
            await ctx.send(embed=embed, view=QuickBetButton())
    
    @bet_group.command(name='place')
    async def place_bet(self, ctx, bet_id: int, option: str, amount: int):
        """Place a bet on an option"""
        # Validate amount
        if amount <= 0:
            await ctx.send("❌ Bet amount must be positive!")
            return
        
        # Auto-register user
        db_user, is_new = await user_manager.get_or_create_user(
            ctx.author.id, ctx.author.display_name
        )
        
        # Check balance
        if db_user.balance < amount:
            embed = discord.Embed(
                title="❌ Insufficient Balance",
                description=f"You need **{amount:,}** points but only have **{db_user.balance:,}** points.",
                color=discord.Color.red()
            )
            embed.add_field(
                name="Get More Points",
                value="• Use `!daily` for daily bonus\n• Use `!bailout` if balance is 0",
                inline=False
            )
            await ctx.send(embed=embed)
            return
        
        # Get bet details
        bet = await bet_manager.get_bet(bet_id)
        if not bet:
            await ctx.send(f"❌ Bet #{bet_id} not found!")
            return
        
        if bet['status'] != 'open':
            await ctx.send(f"❌ Bet #{bet_id} is not accepting bets (Status: {bet['status']})")
            return
        
        # Check if option is valid
        valid_options = [opt.lower() for opt in bet['options']]
        if option.lower() not in valid_options:
            options_text = ", ".join(bet['options'])
            await ctx.send(f"❌ Invalid option '{option}'. Valid options: {options_text}")
            return
        
        # Attempt to place bet
        success = await bet_manager.place_bet(ctx.author.id, bet_id, option, amount)
        
        if not success:
            await ctx.send("❌ Failed to place bet. You may have already bet on this or there was an error.")
            return
        
        # Get updated user balance
        updated_user = await user_manager.get_user(ctx.author.id)
        
        embed = discord.Embed(
            title="✅ Bet Placed Successfully!",
            color=discord.Color.green()
        )
        
        embed.add_field(name="Bet", value=f"#{bet_id}: {bet['title']}", inline=False)
        embed.add_field(name="Your Choice", value=f"**{option}**", inline=True)
        embed.add_field(name="Amount", value=f"**{amount:,}** points", inline=True)
        embed.add_field(name="New Balance", value=f"**{updated_user.balance:,}** points", inline=True)
        
        embed.set_footer(text="Good luck! Check !bet info to see all bets on this question.")
        
        await ctx.send(embed=embed)
        logger.info(f"Bet placed: {ctx.author} bet {amount} on '{option}' for bet #{bet_id}")
    
    @bet_group.command(name='list')
    async def list_bets(self, ctx, limit: int = 5):
        """List active bets"""
        if limit > 10:
            limit = 10
        elif limit < 1:
            limit = 5
        
        active_bets = await bet_manager.get_active_bets(limit)
        
        if not active_bets:
            embed = discord.Embed(
                title="🎲 No Active Bets",
                description="No bets are currently active. Create one with `!bet create`!",
                color=discord.Color.orange()
            )
            await ctx.send(embed=embed)
            return
        
        embed = discord.Embed(
            title="🎲 Active Bets",
            description=f"Here are the latest {len(active_bets)} active bets:",
            color=discord.Color.blue()
        )
        
        for bet in active_bets:
            # Get creator info
            try:
                creator = self.bot.get_user(bet['creator_id'])
                creator_name = creator.display_name if creator else "Unknown"
            except:
                creator_name = "Unknown"
            
            options_text = " vs ".join(bet['options'])
            pool_text = f"{bet['total_pool']:,} points" if bet['total_pool'] > 0 else "No bets yet"
            
            embed.add_field(
                name=f"#{bet['bet_id']}: {bet['title']}",
                value=f"**Options:** {options_text}\n"
                      f"**Pool:** {pool_text}\n"
                      f"**Creator:** {creator_name}\n"
                      f"Click buttons below to bet!",
                inline=False
            )
        
        embed.set_footer(text="Use !bet info <bet_id> for detailed information about a specific bet")
        
        # Create a view with buttons for each active bet
        class BetListView(discord.ui.View):
            def __init__(self, bets, is_admin=False):
                super().__init__(timeout=300)  # 5 minute timeout
                self.is_admin = is_admin
                
                # Add a button for each bet (up to 5)
                for bet in bets[:5]:
                    button = discord.ui.Button(
                        label=f"#{bet['bet_id']}: {bet['title'][:30]}...",
                        style=discord.ButtonStyle.primary,
                        custom_id=f"bet_details_{bet['bet_id']}"
                    )
                    button.callback = self.create_bet_callback(bet)
                    self.add_item(button)
            
            def create_bet_callback(self, bet):
                async def bet_callback(interaction: discord.Interaction):
                    # Check if user is admin
                    is_admin = (interaction.user.guild_permissions.administrator or 
                              any(role.name in ['Bet Master', 'Bet Moderator', 'Admin'] for role in interaction.user.roles))
                    
                    # Show bet with buttons
                    embed = discord.Embed(
                        title=f"🎲 Bet #{bet['bet_id']}",
                        description=f"**{bet['title']}**",
                        color=discord.Color.blue()
                    )
                    
                    options_text = " vs ".join(bet['options'])
                    pool_text = f"{bet['total_pool']:,} points" if bet['total_pool'] > 0 else "No bets yet"
                    
                    embed.add_field(name="Options", value=options_text, inline=True)
                    embed.add_field(name="Pool", value=pool_text, inline=True)
                    embed.add_field(name="Status", value="🟢 Open", inline=True)
                    
                    if bet['description']:
                        embed.add_field(name="Description", value=bet['description'], inline=False)
                    
                    if is_admin:
                        embed.add_field(
                            name="🛡️ Admin Options",
                            value="Use the admin buttons below to manage this bet",
                            inline=False
                        )
                        embed.set_footer(text="Place bets OR use admin controls below!")
                        
                        # Create combined view with betting + admin buttons
                        combined_view = BetListAdminView(bet['bet_id'], bet['title'], bet['options'])
                    else:
                        embed.set_footer(text="Click a button below to place your bet!")
                        # Create regular betting view
                        combined_view = BetButtonView(bet['bet_id'], bet['title'], bet['options'])
                    
                    await interaction.response.send_message(embed=embed, view=combined_view, ephemeral=True)
                
                return bet_callback
        
        if active_bets:
            # Check if user is admin
            is_admin = (ctx.author.guild_permissions.administrator or 
                       any(role.name in ['Bet Master', 'Bet Moderator', 'Admin'] for role in ctx.author.roles))
            
            view = BetListView(active_bets, is_admin)
            
            if is_admin:
                embed.add_field(
                    name="🛡️ Admin Mode",
                    value="You have admin permissions! Click any bet to see admin controls.",
                    inline=False
                )
            
            await ctx.send(embed=embed, view=view)
        else:
            await ctx.send(embed=embed)
    
    @bet_group.command(name='info')
    async def bet_info(self, ctx, bet_id: int):
        """Show detailed information about a bet"""
        bet = await bet_manager.get_bet(bet_id)
        if not bet:
            await ctx.send(f"❌ Bet #{bet_id} not found!")
            return
        
        # Get creator info
        try:
            creator = self.bot.get_user(bet['creator_id'])
            creator_name = creator.display_name if creator else "Unknown"
        except:
            creator_name = "Unknown"
        
        # Get all user bets for this bet
        user_bets = await bet_manager.get_user_bets_for_bet(bet_id)
        
        embed = discord.Embed(
            title=f"🎲 Bet #{bet_id} Details",
            description=f"**{bet['title']}**",
            color=discord.Color.blue()
        )
        
        embed.add_field(name="Creator", value=creator_name, inline=True)
        embed.add_field(name="Status", value=f"🟢 {bet['status'].title()}", inline=True)
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
        for option in bet['options']:
            stats = option_stats.get(option, {'count': 0, 'amount': 0})
            options_text += f"**{option}**: {stats['count']} bets, {stats['amount']:,} points\n"
        
        embed.add_field(name="Options & Bets", value=options_text or "No bets placed yet", inline=False)
        
        # Show recent bets
        if user_bets:
            recent_bets_text = ""
            for user_bet in user_bets[:5]:  # Show last 5
                recent_bets_text += f"• {user_bet['username']}: {user_bet['amount']:,} on {user_bet['option_chosen']}\n"
            
            embed.add_field(
                name=f"Recent Bets ({len(user_bets)} total)",
                value=recent_bets_text,
                inline=False
            )
        
        if bet['status'] == 'open':
            embed.add_field(
                name="Place Your Bet",
                value=f"`!bet place {bet_id} <option> <amount>`",
                inline=False
            )
        elif bet['status'] == 'resolved':
            embed.add_field(
                name="Winner",
                value=f"🏆 **{bet['winning_option']}**",
                inline=False
            )
        
        await ctx.send(embed=embed)
    

    
    @bet_group.command(name='mybets')
    async def my_bets(self, ctx):
        """Show your active bets"""
        # Get user's active bets
        conn = await db_manager.get_connection()
        cursor = await conn.execute("""
            SELECT b.bet_id, b.title, b.status, ub.option_chosen, ub.amount, ub.status as bet_status
            FROM bets b
            JOIN user_bets ub ON b.bet_id = ub.bet_id
            WHERE ub.user_id = ? AND b.status IN ('open', 'locked')
            ORDER BY b.created_at DESC
        """, (ctx.author.id,))
        user_bets = await cursor.fetchall()
        
        if not user_bets:
            embed = discord.Embed(
                title="🎲 Your Active Bets",
                description="You don't have any active bets.\nUse `!bet list` to see available bets!",
                color=discord.Color.orange()
            )
            await ctx.send(embed=embed)
            return
        
        embed = discord.Embed(
            title="🎲 Your Active Bets",
            description=f"You have {len(user_bets)} active bets:",
            color=discord.Color.blue()
        )
        
        total_amount = 0
        for bet in user_bets:
            bet_id, title, status, option, amount, bet_status = bet
            total_amount += amount
            
            status_emoji = "🟢" if status == "open" else "🔒"
            
            embed.add_field(
                name=f"{status_emoji} #{bet_id}: {title[:40]}...",
                value=f"**Your bet:** {option} - {amount:,} points\n**Status:** {status.title()}",
                inline=False
            )
        
        embed.add_field(
            name="💰 Total Invested",
            value=f"**{total_amount:,}** points across all active bets",
            inline=False
        )
        
        embed.set_footer(text="Use !bet info <bet_id> for detailed information")
        await ctx.send(embed=embed)

async def setup(bot):
    await bot.add_cog(Betting(bot))
