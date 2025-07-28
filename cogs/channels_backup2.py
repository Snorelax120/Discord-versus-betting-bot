import discord
from discord.ext import commands
import logging
from datetime import datetime, timezone
from typing import Optional, Dict, Any

from database.database import db_manager
from config import Config

logger = logging.getLogger(__name__)

class Channels(commands.Cog):
    """Manage bet history and active bet channels"""
    
    def __init__(self, bot):
        self.bot = bot
    
    async def get_guild_settings(self, guild_id: int) -> Dict[str, Any]:
        """Get guild settings including channel configurations"""
        conn = await db_manager.get_connection()
        
        cursor = await conn.execute(
            "SELECT bet_history_channel, active_bets_channel FROM settings WHERE guild_id = ?",
            (guild_id,)
        )
        row = await cursor.fetchone()
        
        if row:
            return {
                'bet_history_channel': row[0],
                'active_bets_channel': row[1]
            }
        else:
            return {
                'bet_history_channel': None,
                'active_bets_channel': None
            }
    
    async def update_guild_channels(self, guild_id: int, bet_history_channel: int = None, active_bets_channel: int = None) -> bool:
        """Update guild channel settings"""
        now = datetime.now(timezone.utc).isoformat()
        conn = await db_manager.get_connection()
        
        try:
            # Check if settings exist
            cursor = await conn.execute("SELECT guild_id FROM settings WHERE guild_id = ?", (guild_id,))
            exists = await cursor.fetchone()
            
            if exists:
                # Update existing settings
                updates = []
                params = []
                
                if bet_history_channel is not None:
                    updates.append("bet_history_channel = ?")
                    params.append(bet_history_channel)
                
                if active_bets_channel is not None:
                    updates.append("active_bets_channel = ?")
                    params.append(active_bets_channel)
                
                if updates:
                    updates.append("updated_at = ?")
                    params.append(now)
                    params.append(guild_id)
                    
                    query = f"UPDATE settings SET {', '.join(updates)} WHERE guild_id = ?"
                    await conn.execute(query, params)
            else:
                # Create new settings
                await conn.execute("""
                    INSERT INTO settings 
                    (guild_id, bet_history_channel, active_bets_channel, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?)
                """, (guild_id, bet_history_channel, active_bets_channel, now, now))
            
            await conn.commit()
            return True
            
        except Exception as e:
            logger.error(f"Error updating guild channels: {e}")
            await conn.rollback()
            return False
    
    async def post_bet_creation(self, bet_data: Dict[str, Any]) -> None:
        """Post bet creation to active bets channel"""
        guild_id = bet_data.get('guild_id')
        if not guild_id:
            return
        
        settings = await self.get_guild_settings(guild_id)
        channel_id = settings.get('active_bets_channel')
        
        if not channel_id:
            return
        
        guild = self.bot.get_guild(guild_id)
        if not guild:
            return
        
        channel = guild.get_channel(channel_id)
        if not channel:
            return
        
        try:
            # Create embed for new bet
            embed = discord.Embed(
                title=f"🎲 New Bet Created - #{bet_data['bet_id']}",
                description=bet_data['title'],
                color=discord.Color.blue()
            )
            
            if bet_data.get('description'):
                embed.add_field(
                    name="Description",
                    value=bet_data['description'][:1000],
                    inline=False
                )
            
            # Add options
            options = bet_data.get('options', [])
            if isinstance(options, str):
                import json
                options = json.loads(options)
            
            if options:
                options_text = "\n".join([f"**{i+1}.** {opt}" for i, opt in enumerate(options)])
                embed.add_field(
                    name="Options",
                    value=options_text[:1000],
                    inline=False
                )
            
            embed.add_field(name="Status", value="🟢 Open", inline=True)
            embed.add_field(name="Type", value=bet_data.get('bet_type', 'unknown').upper(), inline=True)
            embed.add_field(name="Min Bet", value=f"{bet_data.get('min_bet', 1)} points", inline=True)
            
            creator = guild.get_member(bet_data['creator_id'])
            if creator:
                embed.set_footer(text=f"Created by {creator.display_name}")
            
            embed.timestamp = datetime.now(timezone.utc)
            
            message = await channel.send(embed=embed)
            
            # Store the message ID in the database
            try:
                from database.database import db_manager
                conn = await db_manager.get_connection()
                await conn.execute(
                    "UPDATE bets SET active_message_id = ? WHERE bet_id = ?",
                    (message.id, bet_data['bet_id'])
                )
                await conn.commit()
            except Exception as e:
                logger.error(f"Error storing active message ID: {e}")
            
        except Exception as e:
            logger.error(f"Error posting bet creation to channel: {e}")
    
    async def post_bet_resolution(self, bet_data: Dict[str, Any], winning_option: str, participants: int, total_pool: int) -> None:
        """Post bet resolution to history channel"""
        guild_id = bet_data.get('guild_id')
        if not guild_id:
            return
        
        settings = await self.get_guild_settings(guild_id)
        channel_id = settings.get('bet_history_channel')
        
        if not channel_id:
            return
        
        guild = self.bot.get_guild(guild_id)
        if not guild:
            return
        
        channel = guild.get_channel(channel_id)
        if not channel:
            return
        
        try:
            # Create embed for resolved bet
            embed = discord.Embed(
                title=f"🏆 Bet Resolved - #{bet_data['bet_id']}",
                description=bet_data['title'],
                color=discord.Color.green()
            )
            
            if bet_data.get('description'):
                embed.add_field(
                    name="Description",
                    value=bet_data['description'][:1000],
                    inline=False
                )
            
            embed.add_field(name="✅ Winning Option", value=winning_option, inline=False)
            embed.add_field(name="👥 Participants", value=str(participants), inline=True)
            embed.add_field(name="💰 Total Pool", value=f"{total_pool} points", inline=True)
            embed.add_field(name="Status", value="🔒 Resolved", inline=True)
            
            creator = guild.get_member(bet_data['creator_id'])
            if creator:
                embed.set_footer(text=f"Created by {creator.display_name}")
            
            embed.timestamp = datetime.now(timezone.utc)
            
            await channel.send(embed=embed)
            
        except Exception as e:
            logger.error(f"Error posting bet resolution to history: {e}")
    
    async def update_active_bet_status(self, bet_data: Dict[str, Any], new_status: str, winning_option: str = None) -> None:
        """Update bet status in active bets channel"""
        guild_id = bet_data.get('guild_id')
        if not guild_id:
            return
        
        settings = await self.get_guild_settings(guild_id)
        channel_id = settings.get('active_bets_channel')
        
        if not channel_id:
            return
        
        guild = self.bot.get_guild(guild_id)
        if not guild:
            return
        
        channel = guild.get_channel(channel_id)
        if not channel:
            return
        
        # Try to find and update the original message
        active_message_id = bet_data.get('active_message_id')
        if active_message_id and new_status in ['resolved', 'cancelled']:
            try:
                message = await channel.fetch_message(active_message_id)
                if new_status == 'resolved':
                    # Delete the message for resolved bets
                    await message.delete()
                    logger.info(f"Deleted active bet message for resolved bet #{bet_data['bet_id']}")
                    return
                elif new_status == 'cancelled':
                    # Edit the message for cancelled bets
                    embed = message.embeds[0] if message.embeds else None
                    if embed:
                        embed.color = discord.Color.red()
                        embed.title = f"❌ CANCELLED - {embed.title}"
                        embed.clear_fields()
                        embed.add_field(
                            name="Status",
                            value="❌ **CANCELLED**\nAll bets have been refunded.",
                            inline=False
                        )
                        await message.edit(embed=embed)
                        logger.info(f"Updated active bet message for cancelled bet #{bet_data['bet_id']}")
                        return
            except discord.NotFound:
                logger.warning(f"Active message not found for bet #{bet_data['bet_id']}")
            except Exception as e:
                logger.error(f"Error updating active message: {e}")
        
        try:
            status_colors = {
                'locked': discord.Color.orange(),
                'cancelled': discord.Color.red(),
                'resolved': discord.Color.green()
            }
            
            status_icons = {
                'locked': '🔒',
                'cancelled': '❌',
                'resolved': '🏆'
            }
            
            embed = discord.Embed(
                title=f"{status_icons.get(new_status, '📊')} Bet #{bet_data['bet_id']} - {new_status.title()}",
                description=bet_data['title'],
                color=status_colors.get(new_status, discord.Color.greyple())
            )
            
            if new_status == 'resolved' and winning_option:
                embed.add_field(
                    name="🏆 Final Result", 
                    value=f"**Winning Option:** {winning_option}\n"
                          f"✅ This bet has been resolved and moved to bet history.\n"
                          f"💰 Winnings have been distributed to winners!",
                    inline=False
                )
            elif new_status == 'cancelled':
                embed.add_field(
                    name="❌ Bet Cancelled", 
                    value=f"This bet has been cancelled by an admin.\n"
                          f"💰 All participants have been refunded their bet amounts.\n"
                          f"📜 This action has been logged.",
                    inline=False
                )
            elif new_status == 'locked':
                embed.add_field(
                    name="🔒 Bet Locked", 
                    value=f"This bet is now locked - no more bets can be placed.\n"
                          f"⏳ Waiting for admin to resolve the bet.\n"
                          f"📊 Final results coming soon!",
                    inline=False
                )
            else:
                embed.add_field(name="Status Update", value=f"Bet is now **{new_status.upper()}**", inline=False)
            
            embed.timestamp = datetime.now(timezone.utc)
            
            await channel.send(embed=embed)
            
        except Exception as e:
            logger.error(f"Error updating bet status in channel: {e}")

# Admin Commands for Channel Management
class ChannelAdmin(commands.Cog):
    """Admin commands for managing bet channels"""
    
    def __init__(self, bot):
        self.bot = bot
        self.channels_cog = None
    
    async def cog_load(self):
        """Get reference to channels cog after loading"""
        self.channels_cog = self.bot.get_cog('Channels')
    
    @commands.group(name='setchannel', aliases=['channel'])
    @commands.has_permissions(administrator=True)
    async def setchannel_group(self, ctx):
        """Set up dedicated bet channels"""
        if ctx.invoked_subcommand is None:
            embed = discord.Embed(
                title="📺 Channel Setup Commands",
                description="Configure dedicated channels for betting",
                color=discord.Color.blue()
            )
            
            embed.add_field(
                name="Setup Commands",
                value="`!setchannel setup` - **Auto-create both channels** 🚀\n"
                      "`!setchannel history <#channel>` - Set bet history channel\n"
                      "`!setchannel active <#channel>` - Set active bets channel\n"
                      "`!setchannel view` - View current channel settings\n"
                      "`!setchannel remove <type>` - Remove channel setting",
                inline=False
            )
            
            embed.add_field(
                name="Channel Types",
                value="**History Channel**: Shows all resolved bets\n"
                      "**Active Channel**: Shows new bets and status updates",
                inline=False
            )
            
            embed.add_field(
                name="💡 Quick Start",
                value="Use `!setchannel setup` to automatically create and configure both channels!\n"
                      "*Checks for existing channels to avoid duplicates*",
                inline=False
            )
            
            await ctx.send(embed=embed)
    
    @setchannel_group.command(name='setup')
    @commands.has_permissions(administrator=True)
    async def auto_setup_channels(self, ctx):
        """Automatically create and configure bet channels"""
        if not self.channels_cog:
            await ctx.send("❌ Channels system not available")
            return
        
        # Check if bot has permission to manage channels
        if not ctx.guild.me.guild_permissions.manage_channels:
            embed = discord.Embed(
                title="❌ Missing Permissions",
                description="I need the **Manage Channels** permission to create channels.",
                color=discord.Color.red()
            )
            embed.add_field(
                name="How to fix:",
                value="1. Go to Server Settings → Roles\n"
                      "2. Find my bot role\n"
                      "3. Enable **Manage Channels** permission\n"
                      "4. Try the command again",
                inline=False
            )
            await ctx.send(embed=embed)
            return
        
        try:
            # Create loading embed
            embed = discord.Embed(
                title="🔄 Setting Up Bet Channels...",
                description="Checking existing channels and creating new ones if needed...",
                color=discord.Color.orange()
            )
            message = await ctx.send(embed=embed)
            
            # Check for existing channels
            existing_history = discord.utils.get(ctx.guild.text_channels, name="bet-history")
            existing_active = discord.utils.get(ctx.guild.text_channels, name="active-bets")
            
            created_channels = []
            used_existing = []
            
            # Handle History Channel
            if existing_history:
                history_channel = existing_history
                used_existing.append(f"📜 {history_channel.mention} (bet-history)")
            else:
                history_channel = await ctx.guild.create_text_channel(
                    name="bet-history",
                    topic="📜 Resolved bets and final results are posted here automatically",
                    reason="Automatic betting system setup"
                )
                created_channels.append(f"📜 {history_channel.mention} (bet-history)")
            
            # Handle Active Bets Channel
            if existing_active:
                active_channel = existing_active
                used_existing.append(f"🎲 {active_channel.mention} (active-bets)")
            else:
                active_channel = await ctx.guild.create_text_channel(
                    name="active-bets",
                    topic="🎲 New bets and status updates are posted here automatically",
                    reason="Automatic betting system setup"
                )
                created_channels.append(f"🎲 {active_channel.mention} (active-bets)")
            
            # Configure the channels
            success1 = await self.channels_cog.update_guild_channels(
                ctx.guild.id,
                bet_history_channel=history_channel.id
            )
            
            success2 = await self.channels_cog.update_guild_channels(
                ctx.guild.id,
                active_bets_channel=active_channel.id
            )
            
            if success1 and success2:
                # Success embed
                embed = discord.Embed(
                    title="✅ Betting Channels Setup Complete!",
                    description="Your betting system is now fully configured and ready to use!",
                    color=discord.Color.green()
                )
                
                if created_channels:
                    embed.add_field(
                        name="🆕 Created Channels",
                        value="\n".join(created_channels),
                        inline=False
                    )
                
                if used_existing:
                    embed.add_field(
                        name="🔄 Used Existing Channels",
                        value="\n".join(used_existing),
                        inline=False
                    )
                
                embed.add_field(
                    name="📜 History Channel",
                    value=f"{history_channel.mention}\n*Resolved bets will be posted here*",
                    inline=True
                )
                
                embed.add_field(
                    name="🎲 Active Bets Channel",
                    value=f"{active_channel.mention}\n*New bets will be posted here*",
                    inline=True
                )
                
                embed.add_field(
                    name="🚀 Ready to Use!",
                    value="Create your first bet with `!bet quick \"Test question?\"`\nand watch it appear in the active bets channel!",
                    inline=False
                )
                
                embed.set_footer(text="You can modify these settings anytime with !setchannel commands")
                
            else:
                embed = discord.Embed(
                    title="⚠️ Channels Created But Configuration Failed",
                    description="The channels were created but there was an error configuring them.",
                    color=discord.Color.orange()
                )
                embed.add_field(
                    name="Manual Setup Required",
                    value=f"Please run:\n"
                          f"`!setchannel history {history_channel.mention}`\n"
                          f"`!setchannel active {active_channel.mention}`",
                    inline=False
                )
            
            await message.edit(embed=embed)
            
        except discord.Forbidden:
            embed = discord.Embed(
                title="❌ Permission Denied",
                description="I don't have permission to create channels in this server.",
                color=discord.Color.red()
            )
            await message.edit(embed=embed)
            
        except discord.HTTPException as e:
            embed = discord.Embed(
                title="❌ Failed to Create Channels",
                description=f"Discord API error: {str(e)}",
                color=discord.Color.red()
            )
            await message.edit(embed=embed)
            
        except Exception as e:
            embed = discord.Embed(
                title="❌ Unexpected Error",
                description=f"An error occurred: {str(e)}",
                color=discord.Color.red()
            )
            await message.edit(embed=embed)


    
    @setchannel_group.command(name='history')
    @commands.has_permissions(administrator=True)
    async def set_history_channel(self, ctx, channel: discord.TextChannel):
        """Set the bet history channel"""
        if not self.channels_cog:
            await ctx.send("❌ Channels system not available")
            return
        
        success = await self.channels_cog.update_guild_channels(
            ctx.guild.id, 
            bet_history_channel=channel.id
        )
        
        if success:
            embed = discord.Embed(
                title="✅ History Channel Set",
                description=f"Bet history will now be posted to {channel.mention}",
                color=discord.Color.green()
            )
            embed.add_field(
                name="What gets posted here:",
                value="• All resolved bets\n• Final results and winners\n• Bet statistics",
                inline=False
            )
        else:
            embed = discord.Embed(
                title="❌ Failed to Set Channel",
                description="There was an error updating the channel settings",
                color=discord.Color.red()
            )
        
        await ctx.send(embed=embed)
    
    @setchannel_group.command(name='active')
    @commands.has_permissions(administrator=True)
    async def set_active_channel(self, ctx, channel: discord.TextChannel):
        """Set the active bets channel"""
        if not self.channels_cog:
            await ctx.send("❌ Channels system not available")
            return
        
        success = await self.channels_cog.update_guild_channels(
            ctx.guild.id, 
            active_bets_channel=channel.id
        )
        
        if success:
            embed = discord.Embed(
                title="✅ Active Bets Channel Set",
                description=f"New bets and updates will be posted to {channel.mention}",
                color=discord.Color.green()
            )
            embed.add_field(
                name="What gets posted here:",
                value="• New bet announcements\n• Status updates (locked/cancelled)\n• Quick bet info",
                inline=False
            )
        else:
            embed = discord.Embed(
                title="❌ Failed to Set Channel",
                description="There was an error updating the channel settings",
                color=discord.Color.red()
            )
        
        await ctx.send(embed=embed)
    
    @setchannel_group.command(name='view')
    @commands.has_permissions(administrator=True)
    async def view_channels(self, ctx):
        """View current channel settings"""
        if not self.channels_cog:
            await ctx.send("❌ Channels system not available")
            return
        
        settings = await self.channels_cog.get_guild_settings(ctx.guild.id)
        
        embed = discord.Embed(
            title="📺 Current Channel Settings",
            color=discord.Color.blue()
        )
        
        # History channel
        history_channel_id = settings.get('bet_history_channel')
        if history_channel_id:
            history_channel = ctx.guild.get_channel(history_channel_id)
            if history_channel:
                embed.add_field(
                    name="🏆 History Channel",
                    value=f"{history_channel.mention}\n*Resolved bets posted here*",
                    inline=True
                )
            else:
                embed.add_field(
                    name="🏆 History Channel",
                    value="❌ Channel not found (deleted?)",
                    inline=True
                )
        else:
            embed.add_field(
                name="🏆 History Channel",
                value="❌ Not configured",
                inline=True
            )
        
        # Active channel  
        active_channel_id = settings.get('active_bets_channel')
        if active_channel_id:
            active_channel = ctx.guild.get_channel(active_channel_id)
            if active_channel:
                embed.add_field(
                    name="🎲 Active Bets Channel",
                    value=f"{active_channel.mention}\n*New bets posted here*",
                    inline=True
                )
            else:
                embed.add_field(
                    name="🎲 Active Bets Channel",
                    value="❌ Channel not found (deleted?)",
                    inline=True
                )
        else:
            embed.add_field(
                name="🎲 Active Bets Channel",
                value="❌ Not configured",
                inline=True
            )
        
        if not history_channel_id and not active_channel_id:
            embed.add_field(
                name="Setup Required",
                value="Use `!setchannel history #channel` and `!setchannel active #channel` to configure",
                inline=False
            )
        
        await ctx.send(embed=embed)
    
    @setchannel_group.command(name='remove')
    @commands.has_permissions(administrator=True)
    async def remove_channel(self, ctx, channel_type: str):
        """Remove a channel setting"""
        if not self.channels_cog:
            await ctx.send("❌ Channels system not available")
            return
        
        channel_type = channel_type.lower()
        if channel_type not in ['history', 'active']:
            await ctx.send("❌ Channel type must be 'history' or 'active'")
            return
        
        if channel_type == 'history':
            success = await self.channels_cog.update_guild_channels(
                ctx.guild.id, 
                bet_history_channel=None
            )
            channel_name = "History"
        else:
            success = await self.channels_cog.update_guild_channels(
                ctx.guild.id, 
                active_bets_channel=None
            )
            channel_name = "Active Bets"
        
        if success:
            embed = discord.Embed(
                title="✅ Channel Removed",
                description=f"{channel_name} channel setting has been removed",
                color=discord.Color.green()
            )
        else:
            embed = discord.Embed(
                title="❌ Failed to Remove Channel",
                description="There was an error updating the channel settings",
                color=discord.Color.red()
            )
        
        await ctx.send(embed=embed)

async def setup(bot):
    await bot.add_cog(Channels(bot))
    await bot.add_cog(ChannelAdmin(bot)) 