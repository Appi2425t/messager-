#!/usr/bin/env python3
# =============================================================
# DISCORD HYBRID BOT - SCHEDULED MESSENGER
# =============================================================
# Accepts ANY token format from Chrome (bot, user, OTA, mfa., etc.)
# Uses the token EXACTLY as provided - NO prefix added
# Failed messages logged to a dedicated channel
# All replies in panel style with developer credit
# =============================================================

import discord
from discord.ext import commands
import asyncio
import json
import os
import time
import aiohttp
import datetime
import random

# =============================================================
# CONFIGURATION
# =============================================================

BOT_TOKEN = os.environ.get('BOT_TOKEN', 'YOUR_BOT_TOKEN_HERE')
DATA_FILE = 'user_data.json'

DEFAULT_SETTINGS = {
    'user_token': None,
    'channels': [],
    'message': None,
    'schedule_interval': 1,
    'is_running': False,
    'start_time': None,
    'sent_count': 0,
    'failed_count': 0,
    'last_send_time': None,
    'total_rounds': 0,
    'failed_channel_id': None,  # Channel ID for failed message logs
    'failed_logs': []  # List of failed attempts
}

# =============================================================
# DATA MANAGEMENT
# =============================================================

def load_data():
    try:
        if os.path.exists(DATA_FILE):
            with open(DATA_FILE, 'r') as f:
                return json.load(f)
        return DEFAULT_SETTINGS.copy()
    except Exception as e:
        print(f"Error loading data: {e}")
        return DEFAULT_SETTINGS.copy()

def save_data(data):
    try:
        with open(DATA_FILE, 'w') as f:
            json.dump(data, f, indent=4)
        return True
    except Exception as e:
        print(f"Error saving data: {e}")
        return False

# =============================================================
# DISCORD BOT
# =============================================================

intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True

bot = commands.Bot(command_prefix='!', intents=intents)

user_data = load_data()
sending_task = None
rate_limited = False
rate_limit_until = 0

# =============================================================
# PANEL REPLY HELPER
# =============================================================

def create_panel(title: str, content: str, color: discord.Color = discord.Color.blue(), success: bool = None) -> discord.Embed:
    """Create a professional panel-style embed."""
    if success is True:
        color = discord.Color.green()
    elif success is False:
        color = discord.Color.red()
    
    embed = discord.Embed(
        title=f"📋 {title}",
        description=content,
        color=color,
        timestamp=datetime.datetime.now()
    )
    
    # Add footer with developer credit
    embed.set_footer(
        text="developed by @yathishyt ⚡",
        icon_url="https://cdn.discordapp.com/attachments/.../developer_icon.png"  # Optional
    )
    
    # Add border effect
    embed.add_field(name="═" + "─" * 48 + "╒", value="", inline=False)
    
    return embed

async def send_panel(ctx, title: str, content: str, color: discord.Color = discord.Color.blue(), success: bool = None, channel=None):
    """Send a panel-style message to a channel."""
    embed = create_panel(title, content, color, success)
    if channel:
        await channel.send(embed=embed)
    else:
        await ctx.send(embed=embed)

# =============================================================
# FAILED LOG HELPER
# =============================================================

async def log_failed_message(channel_id: str, reason: str, token_preview: str = None):
    """Log a failed message to the configured failed channel."""
    global user_data
    
    failed_channel_id = user_data.get('failed_channel_id')
    if not failed_channel_id:
        return
    
    try:
        failed_channel = bot.get_channel(int(failed_channel_id))
        if not failed_channel:
            return
        
        # Create log entry
        log_entry = {
            'timestamp': datetime.datetime.now().isoformat(),
            'channel_id': channel_id,
            'reason': reason,
            'token_preview': token_preview
        }
        
        # Store in data
        if 'failed_logs' not in user_data:
            user_data['failed_logs'] = []
        user_data['failed_logs'].append(log_entry)
        
        # Keep only last 100 logs
        if len(user_data['failed_logs']) > 100:
            user_data['failed_logs'] = user_data['failed_logs'][-100:]
        save_data(user_data)
        
        # Send panel to failed channel
        embed = discord.Embed(
            title="❌ MESSAGE FAILED",
            description=f"**Channel ID:** `{channel_id}`\n**Reason:** {reason}\n**Time:** {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            color=discord.Color.red(),
            timestamp=datetime.datetime.now()
        )
        embed.set_footer(text="developed by @yathishyt ⚡")
        await failed_channel.send(embed=embed)
        
    except Exception as e:
        print(f"Error logging failed message: {e}")

# =============================================================
# TOKEN HANDLING - ACCEPTS ANY FORMAT
# =============================================================

def clean_token(token: str) -> str:
    """Clean and normalize any token format."""
    if not token:
        return None
    
    token = token.strip()
    
    if token.startswith('"') and token.endswith('"'):
        token = token[1:-1]
    if token.startswith("'") and token.endswith("'"):
        token = token[1:-1]
    
    token = token.replace('"', '').replace("'", '').replace('`', '')
    token = token.replace(' ', '')
    
    if token.lower().startswith('bot '):
        token = token[4:]
    
    return token

async def test_token(token: str):
    """Test if a token is valid (works with ANY format)."""
    if not token or len(token) < 10:
        return False, "Token too short"
    
    token = clean_token(token)
    
    url = "https://discord.com/api/v9/users/@me"
    
    headers = {
        'Authorization': token,
        'Content-Type': 'application/json',
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    }
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers) as response:
                if response.status == 200:
                    data = await response.json()
                    username = data.get('username', 'Unknown')
                    user_id = data.get('id', 'Unknown')
                    discrim = data.get('discriminator', '0000')
                    return True, f"✅ Valid token! Logged in as: `{username}#{discrim}` (`{user_id}`)"
                elif response.status == 401:
                    try:
                        headers2 = {
                            'Authorization': f'Bot {token}',
                            'Content-Type': 'application/json',
                            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
                        }
                        async with session.get(url, headers=headers2) as response2:
                            if response2.status == 200:
                                data = await response2.json()
                                username = data.get('username', 'Unknown')
                                user_id = data.get('id', 'Unknown')
                                return True, f"✅ Valid Bot token! Logged in as: `{username}#{data.get('discriminator', '0000')}` (`{user_id}`)"
                    except:
                        pass
                    return False, "❌ Invalid token! Please check and try again."
                else:
                    return False, f"❌ Error: HTTP {response.status}"
    except Exception as e:
        return False, f"❌ Error: {str(e)}"

async def send_message_with_token(channel_id: str, message: str, token: str) -> bool:
    """Send a message using ANY token format."""
    global rate_limited, rate_limit_until, user_data
    
    if not token or len(token) < 10:
        print(f"❌ Invalid token!")
        return False
    
    token = clean_token(token)
    
    if rate_limited and time.time() < rate_limit_until:
        wait_time = rate_limit_until - time.time()
        print(f"⏳ Rate limited, waiting {wait_time:.1f}s...")
        await asyncio.sleep(wait_time)
        rate_limited = False
    
    url = f"https://discord.com/api/v9/channels/{channel_id}/messages"
    
    headers = {
        'Authorization': token,
        'Content-Type': 'application/json',
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    }
    
    payload = {
        'content': message,
        'tts': False,
        'nonce': str(int(time.time() * 1000))
    }
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, json=payload) as response:
                if response.status == 200:
                    return True
                elif response.status == 429:
                    data = await response.json()
                    retry_after = data.get('retry_after', 5)
                    rate_limited = True
                    rate_limit_until = time.time() + retry_after
                    print(f"⚠️ Rate limited! Waiting {retry_after}s...")
                    await asyncio.sleep(retry_after)
                    return await send_message_with_token(channel_id, message, token)
                elif response.status == 401:
                    try:
                        headers2 = {
                            'Authorization': f'Bot {token}',
                            'Content-Type': 'application/json',
                            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
                        }
                        async with session.post(url, headers=headers2, json=payload) as response2:
                            if response2.status == 200:
                                return True
                    except:
                        pass
                    # Log the failed attempt
                    await log_failed_message(channel_id, "Invalid token or unauthorized (HTTP 401)", token[:20])
                    print(f"❌ Invalid token! (HTTP 401) - Channel: {channel_id}")
                    return False
                elif response.status == 403:
                    await log_failed_message(channel_id, "No permission to send in this channel", token[:20])
                    print(f"❌ No permission to send in channel: {channel_id}")
                    return False
                else:
                    await log_failed_message(channel_id, f"HTTP {response.status} - {response.text[:100]}", token[:20])
                    print(f"❌ Failed: HTTP {response.status} - Channel: {channel_id}")
                    return False
    except Exception as e:
        await log_failed_message(channel_id, f"Error: {str(e)}", token[:20])
        print(f"❌ Error: {str(e)} - Channel: {channel_id}")
        return False

async def send_one_round():
    """Send one round of messages to all channels."""
    global user_data
    
    token = user_data.get('user_token')
    channels = user_data.get('channels', [])
    message = user_data.get('message')
    
    if not token:
        print("❌ No token set!")
        return False
    
    if not channels:
        print("❌ No channels added!")
        return False
    
    if not message:
        print("❌ No message set!")
        return False
    
    print(f"\n📨 Sending round to {len(channels)} channels...")
    print(f"🔑 Using token: {token[:20]}...")
    
    sent = 0
    failed = 0
    
    for channel_id in channels:
        print(f"  📤 Sending to {channel_id}...")
        success = await send_message_with_token(channel_id, message, token)
        
        if success:
            sent += 1
            print(f"    ✅ Sent!")
        else:
            failed += 1
            print(f"    ❌ Failed - Logged to #failed channel")
        
        await asyncio.sleep(1)
    
    user_data['sent_count'] = user_data.get('sent_count', 0) + sent
    user_data['failed_count'] = user_data.get('failed_count', 0) + failed
    user_data['total_rounds'] = user_data.get('total_rounds', 0) + 1
    user_data['last_send_time'] = datetime.datetime.now().isoformat()
    save_data(user_data)
    
    print(f"  📊 Round complete: ✅ {sent} | ❌ {failed}")
    return True

async def scheduled_send_task():
    """Background task that sends messages on a schedule."""
    global user_data
    
    if not user_data.get('is_running', False):
        return
    
    interval_minutes = user_data.get('schedule_interval', 1)
    interval_seconds = interval_minutes * 60
    
    print(f"\n🔄 Scheduled messenger started!")
    print(f"⏱️ Interval: Every {interval_minutes} minute(s)")
    print(f"📊 Channels: {len(user_data.get('channels', []))}")
    print(f"📝 Message: {user_data.get('message', '')[:50]}...")
    
    while user_data.get('is_running', False):
        try:
            await send_one_round()
            
            for i in range(interval_seconds):
                if not user_data.get('is_running', False):
                    break
                
                if i % 30 == 0 and i > 0:
                    remaining = interval_seconds - i
                    minutes = remaining // 60
                    seconds = remaining % 60
                    if minutes > 0:
                        print(f"⏳ Next send in {minutes}m {seconds}s...")
                    else:
                        print(f"⏳ Next send in {seconds}s...")
                
                await asyncio.sleep(1)
                
        except Exception as e:
            print(f"❌ Error in scheduled task: {str(e)}")
            await asyncio.sleep(10)
    
    print(f"\n🛑 Scheduled messenger stopped!")
    print(f"📊 Total rounds: {user_data.get('total_rounds', 0)}")
    print(f"✅ Total sent: {user_data.get('sent_count', 0)}")
    print(f"❌ Total failed: {user_data.get('failed_count', 0)}")

# =============================================================
# BOT COMMANDS
# =============================================================

@bot.event
async def on_ready():
    print(f'✅ Bot is online!')
    print(f'🤖 Bot Name: {bot.user.name}')
    print(f'🆔 Bot ID: {bot.user.id}')
    print(f'📡 Connected to {len(bot.guilds)} servers')
    print(f'\n📋 Commands:')
    print(f'  !settoken <token> - Set ANY token from Chrome')
    print(f'  !testtoken - Test if current token is valid')
    print(f'  !addchannel <channel_id> - Add a channel')
    print(f'  !removechannel <channel_id> - Remove a channel')
    print(f'  !listchannels - List all channels')
    print(f'  !setmessage <message> - Set the message')
    print(f'  !setinterval <minutes> - Set interval (1-60 min)')
    print(f'  !start - Start sending')
    print(f'  !stop - Stop sending')
    print(f'  !status - Show status')
    print(f'  !clear - Clear settings')
    print(f'  !commands - Show all commands')
    print(f'  !sendnow - Send one round')
    print(f'  !failed <channel_id> - Set failed logs channel')
    print(f'  !failedlogs - Show recent failed logs')
    
    if user_data.get('is_running', False):
        print(f"\n⚠️ Previous session found! Restarting...")
        global sending_task
        if sending_task is None or sending_task.done():
            sending_task = asyncio.create_task(scheduled_send_task())

@bot.command(name='settoken')
async def set_token(ctx, *, token: str):
    """Set ANY token from Chrome (bot, user, OTA, mfa., etc.)."""
    global user_data
    
    token = clean_token(token)
    
    if len(token) < 10:
        await send_panel(ctx, "SET TOKEN", "❌ **Token too short!**\nMake sure you copied the full token from Chrome.", success=False)
        return
    
    await send_panel(ctx, "SET TOKEN", "🔍 **Testing token...**\nPlease wait while we validate your token.", color=discord.Color.blue())
    
    valid, test_result = await test_token(token)
    
    if not valid:
        await send_panel(ctx, "SET TOKEN", f"❌ **{test_result}**\n\nMake sure you copied the token correctly from Chrome:\n1. Press F12 → Application\n2. Local Storage → https://discord.com\n3. Find 'token' key\n4. Copy the value", success=False)
        return
    
    user_data['user_token'] = token
    user_data['sent_count'] = 0
    user_data['failed_count'] = 0
    user_data['total_rounds'] = 0
    
    if save_data(user_data):
        await send_panel(ctx, "SET TOKEN", f"✅ **{test_result}**\n\n📝 **Token saved:** `{token[:20]}...`\n\nNow use `!addchannel <id>` to add channels and `!start` to begin sending.", success=True)
    else:
        await send_panel(ctx, "SET TOKEN", "❌ **Failed to save token!**\nPlease try again.", success=False)

@bot.command(name='testtoken')
async def test_token_cmd(ctx):
    """Test if the current token is valid."""
    token = user_data.get('user_token')
    
    if not token:
        await send_panel(ctx, "TEST TOKEN", "❌ **No token set!**\nUse `!settoken <token>` first.", success=False)
        return
    
    await send_panel(ctx, "TEST TOKEN", "🔍 **Testing token...**\nPlease wait.", color=discord.Color.blue())
    
    valid, result = await test_token(token)
    
    if valid:
        await send_panel(ctx, "TEST TOKEN", f"✅ **{result}**\n\nToken is valid and working correctly.", success=True)
    else:
        await send_panel(ctx, "TEST TOKEN", f"❌ **{result}**\n\nPlease set a new token using `!settoken <token>`", success=False)

@bot.command(name='addchannel')
async def add_channel(ctx, channel_id: str):
    """Add a channel ID to send messages to."""
    global user_data
    
    if not channel_id.isdigit():
        await send_panel(ctx, "ADD CHANNEL", f"❌ **Invalid channel ID!**\n`{channel_id}` is not a valid number.\n\nChannel IDs are numeric, e.g., `123456789012345678`", success=False)
        return
    
    if channel_id in user_data['channels']:
        await send_panel(ctx, "ADD CHANNEL", f"⚠️ **Channel already in list!**\n`{channel_id}` is already added.", success=False)
        return
    
    user_data['channels'].append(channel_id)
    save_data(user_data)
    
    try:
        channel = bot.get_channel(int(channel_id))
        if channel:
            await send_panel(ctx, "ADD CHANNEL", f"✅ **Channel added!**\n#{channel.name} (`{channel_id}`)\n\nTotal channels: **{len(user_data['channels'])}**", success=True)
        else:
            await send_panel(ctx, "ADD CHANNEL", f"✅ **Channel ID added!**\n`{channel_id}`\n\n⚠️ Bot may not be in this server.\nTotal channels: **{len(user_data['channels'])}**", success=True)
    except:
        await send_panel(ctx, "ADD CHANNEL", f"✅ **Channel ID added!**\n`{channel_id}`\n\nTotal channels: **{len(user_data['channels'])}**", success=True)

@bot.command(name='removechannel')
async def remove_channel(ctx, channel_id: str):
    """Remove a channel ID from the list."""
    global user_data
    
    if channel_id in user_data['channels']:
        user_data['channels'].remove(channel_id)
        save_data(user_data)
        await send_panel(ctx, "REMOVE CHANNEL", f"✅ **Channel removed!**\n`{channel_id}`\n\nTotal channels: **{len(user_data['channels'])}**", success=True)
    else:
        await send_panel(ctx, "REMOVE CHANNEL", f"⚠️ **Channel not found!**\n`{channel_id}` is not in the list.", success=False)

@bot.command(name='listchannels')
async def list_channels(ctx):
    """List all channels that have been added."""
    channels = user_data.get('channels', [])
    
    if not channels:
        await send_panel(ctx, "LIST CHANNELS", "📭 **No channels added.**\nUse `!addchannel <id>` to add one.", success=False)
        return
    
    channel_list = []
    for cid in channels:
        try:
            channel = bot.get_channel(int(cid))
            if channel:
                channel_list.append(f"• #{channel.name} (`{cid}`)")
            else:
                channel_list.append(f"• `{cid}` (unknown)")
        except:
            channel_list.append(f"• `{cid}`")
    
    content = "**Total Channels:** " + str(len(channel_list)) + "\n\n" + "\n".join(channel_list)
    await send_panel(ctx, "LIST CHANNELS", content, success=True)

@bot.command(name='setmessage')
async def set_message(ctx, *, message: str):
    """Set the message to send."""
    global user_data
    
    if len(message) > 2000:
        await send_panel(ctx, "SET MESSAGE", f"❌ **Message too long!**\nMaximum 2000 characters. You have **{len(message)}** characters.", success=False)
        return
    
    user_data['message'] = message
    save_data(user_data)
    
    preview = message[:100] + "..." if len(message) > 100 else message
    await send_panel(ctx, "SET MESSAGE", f"✅ **Message set!**\n\n```\n{preview}\n```\n\nLength: **{len(message)}** characters", success=True)

@bot.command(name='setinterval')
async def set_interval(ctx, minutes: int):
    """Set the interval between sends (1-60 minutes)."""
    global user_data
    
    if minutes < 1:
        await send_panel(ctx, "SET INTERVAL", "❌ **Invalid interval!**\nInterval must be at least **1 minute**.", success=False)
        return
    
    if minutes > 60:
        await send_panel(ctx, "SET INTERVAL", "❌ **Invalid interval!**\nInterval must be **60 minutes or less**.", success=False)
        return
    
    user_data['schedule_interval'] = minutes
    save_data(user_data)
    
    await send_panel(ctx, "SET INTERVAL", f"✅ **Interval set!**\nMessages will send every **{minutes} minute(s)**", success=True)

@bot.command(name='failed')
async def set_failed_channel(ctx, channel_id: str):
    """Set the channel for failed message logs."""
    global user_data
    
    if not channel_id.isdigit():
        await send_panel(ctx, "SET FAILED CHANNEL", f"❌ **Invalid channel ID!**\n`{channel_id}` is not a valid number.", success=False)
        return
    
    # Check if the channel exists
    try:
        channel = bot.get_channel(int(channel_id))
        if not channel:
            await send_panel(ctx, "SET FAILED CHANNEL", f"❌ **Channel not found!**\nBot cannot see channel `{channel_id}`.\nMake sure the bot is in that server.", success=False)
            return
    except:
        await send_panel(ctx, "SET FAILED CHANNEL", f"❌ **Invalid channel!**\nCould not find channel `{channel_id}`.", success=False)
        return
    
    user_data['failed_channel_id'] = channel_id
    save_data(user_data)
    
    # Send test message to the failed channel
    try:
        failed_channel = bot.get_channel(int(channel_id))
        embed = discord.Embed(
            title="✅ FAILED LOGS CHANNEL SET",
            description="All failed message attempts will be logged here.\n\n**Status:** Ready\n**Time:** " + datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            color=discord.Color.green(),
            timestamp=datetime.datetime.now()
        )
        embed.set_footer(text="developed by @yathishyt ⚡")
        await failed_channel.send(embed=embed)
    except:
        pass
    
    await send_panel(ctx, "SET FAILED CHANNEL", f"✅ **Failed logs channel set!**\nChannel ID: `{channel_id}`\n\nAll failed message attempts will be logged there.", success=True)

@bot.command(name='failedlogs')
async def show_failed_logs(ctx):
    """Show recent failed logs."""
    logs = user_data.get('failed_logs', [])
    
    if not logs:
        await send_panel(ctx, "FAILED LOGS", "📭 **No failed logs.**\nAll messages have been sent successfully so far.", success=True)
        return
    
    # Get last 10 logs
    recent = logs[-10:]
    
    log_lines = []
    for log in recent:
        timestamp = log.get('timestamp', 'Unknown time')[:16]
        channel_id = log.get('channel_id', 'Unknown')
        reason = log.get('reason', 'Unknown')
        log_lines.append(f"• `{timestamp}` | Channel: `{channel_id}` | Reason: {reason}")
    
    content = "**Recent Failed Attempts (Last 10):**\n\n" + "\n".join(log_lines)
    await send_panel(ctx, "FAILED LOGS", content, color=discord.Color.orange(), success=False if logs else True)

@bot.command(name='start')
async def start_sending(ctx):
    """Start scheduled sending."""
    global user_data, sending_task
    
    if not user_data.get('user_token'):
        await send_panel(ctx, "START", "❌ **No token set!**\nUse `!settoken <token>` first.", success=False)
        return
    
    if not user_data.get('channels'):
        await send_panel(ctx, "START", "❌ **No channels added!**\nUse `!addchannel <id>` to add one.", success=False)
        return
    
    if not user_data.get('message'):
        await send_panel(ctx, "START", "❌ **No message set!**\nUse `!setmessage <message>` first.", success=False)
        return
    
    if user_data.get('is_running', False):
        await send_panel(ctx, "START", "⚠️ **Already running!**\nUse `!stop` to stop first.", success=False)
        return
    
    interval = user_data.get('schedule_interval', 1)
    failed_channel = user_data.get('failed_channel_id', 'Not set')
    
    user_data['sent_count'] = 0
    user_data['failed_count'] = 0
    user_data['total_rounds'] = 0
    user_data['is_running'] = True
    user_data['start_time'] = datetime.datetime.now().isoformat()
    save_data(user_data)
    
    await send_panel(ctx, "START", f"🚀 **Started scheduled sending!**\n\n📊 **Channels:** {len(user_data['channels'])}\n⏱️ **Interval:** Every {interval} minute(s)\n📝 **Message:** {user_data['message'][:50]}...\n📋 **Failed Logs:** {failed_channel if failed_channel != 'Not set' else '⚠️ Not set'}", success=True)
    
    if sending_task is None or sending_task.done():
        sending_task = asyncio.create_task(scheduled_send_task())
    else:
        sending_task.cancel()
        sending_task = asyncio.create_task(scheduled_send_task())

@bot.command(name='stop')
async def stop_sending(ctx):
    """Stop scheduled sending."""
    global user_data, sending_task
    
    if not user_data.get('is_running', False):
        await send_panel(ctx, "STOP", "⚠️ **Not running!**\nUse `!start` to start sending.", success=False)
        return
    
    user_data['is_running'] = False
    save_data(user_data)
    
    if sending_task and not sending_task.done():
        sending_task.cancel()
        try:
            await sending_task
        except asyncio.CancelledError:
            pass
    
    await send_panel(ctx, "STOP", f"🛑 **Stopped!**\n\n📊 **Total Rounds:** {user_data.get('total_rounds', 0)}\n✅ **Sent:** {user_data.get('sent_count', 0)}\n❌ **Failed:** {user_data.get('failed_count', 0)}", success=True)

@bot.command(name='sendnow')
async def send_now(ctx):
    """Send one round immediately (doesn't affect schedule)."""
    await send_panel(ctx, "SEND NOW", "📨 **Sending one round...**\nPlease wait.", color=discord.Color.blue())
    success = await send_one_round()
    if success:
        await send_panel(ctx, "SEND NOW", f"✅ **Round sent!**\n\n📊 **Total Rounds:** {user_data.get('total_rounds', 0)}\n✅ **Sent:** {user_data.get('sent_count', 0)}\n❌ **Failed:** {user_data.get('failed_count', 0)}", success=True)
    else:
        await send_panel(ctx, "SEND NOW", "❌ **Failed to send round.**\nCheck your configuration and token.", success=False)

@bot.command(name='status')
async def show_status(ctx):
    """Show current bot status."""
    running = user_data.get('is_running', False)
    token = user_data.get('user_token')
    channels = user_data.get('channels', [])
    message = user_data.get('message')
    interval = user_data.get('schedule_interval', 1)
    sent = user_data.get('sent_count', 0)
    failed = user_data.get('failed_count', 0)
    rounds = user_data.get('total_rounds', 0)
    failed_channel = user_data.get('failed_channel_id', 'Not set')
    
    status_emoji = "🟢" if running else "🔴"
    status_text = "**Running**" if running else "**Stopped**"
    
    content = f"""{status_emoji} Status: {status_text}
👤 Token: `{token[:20] if token else 'Not set'}...`
📋 Channels: {len(channels)}
📝 Message: `{message[:50] if message else 'Not set'}...`
⏱️ Interval: Every {interval} minute(s)
📊 Total Rounds: {rounds}
✅ Sent: {sent}
❌ Failed: {failed}
📋 Failed Logs Channel: `{failed_channel}`"""
    
    await send_panel(ctx, "STATUS", content, color=discord.Color.blue(), success=True if running else None)

@bot.command(name='clear')
async def clear_settings(ctx):
    """Clear all settings (token, channels, message)."""
    global user_data
    
    if user_data.get('is_running', False):
        await send_panel(ctx, "CLEAR", "❌ **Cannot clear while running!**\nUse `!stop` first.", success=False)
        return
    
    user_data['user_token'] = None
    user_data['channels'] = []
    user_data['message'] = None
    user_data['schedule_interval'] = 1
    user_data['sent_count'] = 0
    user_data['failed_count'] = 0
    user_data['total_rounds'] = 0
    user_data['start_time'] = None
    user_data['last_send_time'] = None
    user_data['failed_channel_id'] = None
    user_data['failed_logs'] = []
    
    save_data(user_data)
    await send_panel(ctx, "CLEAR", "🗑️ **All settings cleared!**\n\nToken, channels, message, and logs have been reset.", success=True)

@bot.command(name='commands')
async def show_commands(ctx):
    """Show all available commands."""
    content = """
**Setup Commands:**
`!settoken <token>` - Set ANY token from Chrome
`!testtoken` - Test if current token is valid
`!addchannel <id>` - Add a channel
`!removechannel <id>` - Remove a channel
`!listchannels` - List all channels
`!setmessage <msg>` - Set the message
`!setinterval <min>` - Set interval (1-60 min)
`!failed <channel_id>` - Set failed logs channel
`!failedlogs` - Show recent failed logs

**Control Commands:**
`!start` - Start scheduled sending
`!stop` - Stop scheduled sending
`!sendnow` - Send one round
`!status` - Show current status

**Other:**
`!clear` - Clear all settings
`!commands` - Show this menu

**How to get token from Chrome:**
1. Open Discord in Chrome
2. Press F12 → Application → Local Storage
3. Find the "token" key
4. Copy the value (any format)
5. Use: `!settoken <token>`
"""
    await send_panel(ctx, "COMMANDS", content, color=discord.Color.blue())

# =============================================================
# ERROR HANDLING
# =============================================================

@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.MissingRequiredArgument):
        await send_panel(ctx, "ERROR", f"❌ **Missing argument!**\nUse `!commands` to see available commands.", success=False)
    elif isinstance(error, commands.BadArgument):
        await send_panel(ctx, "ERROR", f"❌ **Invalid argument!**\nUse `!commands` to see available commands.", success=False)
    elif isinstance(error, commands.CommandNotFound):
        await send_panel(ctx, "ERROR", f"❌ **Unknown command!**\nUse `!commands` to see available commands.", success=False)
    else:
        await send_panel(ctx, "ERROR", f"❌ **Error:** {str(error)}", success=False)
        print(f"Error: {error}")

# =============================================================
# MAIN
# =============================================================

if __name__ == '__main__':
    if not BOT_TOKEN or BOT_TOKEN == 'YOUR_BOT_TOKEN_HERE':
        print