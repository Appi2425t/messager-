#!/usr/bin/env python3
# =============================================================
# DISCORD HYBRID BOT - SCHEDULED MESSENGER
# =============================================================
# Accepts ANY token format from Chrome (bot, user, OTA, mfa., etc.)
# Uses the token EXACTLY as provided - NO prefix added
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
    'total_rounds': 0
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
# TOKEN HANDLING - ACCEPTS ANY FORMAT
# =============================================================

def clean_token(token: str) -> str:
    """Clean and normalize any token format."""
    if not token:
        return None
    
    # Remove whitespace
    token = token.strip()
    
    # Remove quotes if present
    if token.startswith('"') and token.endswith('"'):
        token = token[1:-1]
    if token.startswith("'") and token.endswith("'"):
        token = token[1:-1]
    
    # Remove any other quote-like characters
    token = token.replace('"', '').replace("'", '').replace('`', '')
    
    # Remove any extra spaces
    token = token.replace(' ', '')
    
    # Remove "Bot " prefix if someone accidentally adds it
    if token.lower().startswith('bot '):
        token = token[4:]
    
    return token

async def test_token(token: str):
    """Test if a token is valid (works with ANY format)."""
    if not token or len(token) < 10:
        return False, "Token too short"
    
    # Clean the token
    token = clean_token(token)
    
    url = "https://discord.com/api/v9/users/@me"
    
    # Use the token AS-IS - NO prefix added
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
                    return True, f"✅ Valid token! Logged in as: {username}#{discrim} ({user_id})"
                elif response.status == 401:
                    # Try with "Bot " prefix for bot tokens
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
                                return True, f"✅ Valid Bot token! Logged in as: {username}#{data.get('discriminator', '0000')} ({user_id})"
                    except:
                        pass
                    return False, "❌ Invalid token! Make sure you copied it correctly from Chrome."
                else:
                    return False, f"❌ Error: HTTP {response.status}"
    except Exception as e:
        return False, f"❌ Error: {str(e)}"

async def send_message_with_token(channel_id: str, message: str, token: str) -> bool:
    """Send a message using ANY token format."""
    global rate_limited, rate_limit_until
    
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
    
    # Use token AS-IS - NO prefix added
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
                    # Try with "Bot " prefix for bot tokens
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
                    print(f"❌ Invalid token! (HTTP 401)")
                    return False
                elif response.status == 403:
                    print(f"❌ No permission to send in this channel")
                    return False
                else:
                    print(f"❌ Failed: HTTP {response.status}")
                    return False
    except Exception as e:
        print(f"❌ Error: {str(e)}")
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
            print(f"    ❌ Failed")
        
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
    
    if user_data.get('is_running', False):
        print(f"\n⚠️ Previous session found! Restarting...")
        global sending_task
        if sending_task is None or sending_task.done():
            sending_task = asyncio.create_task(scheduled_send_task())

@bot.command(name='settoken')
async def set_token(ctx, *, token: str):
    """Set ANY token from Chrome (bot, user, OTA, mfa., etc.)."""
    global user_data
    
    # Clean the token
    token = clean_token(token)
    
    if len(token) < 10:
        await ctx.send("❌ Token too short! Make sure you copied the full token.")
        return
    
    # Test the token
    await ctx.send(f"🔍 Testing token... Please wait.")
    
    valid, test_result = await test_token(token)
    
    if not valid:
        await ctx.send(f"❌ {test_result}\n"
                       "Make sure you copied the token correctly from Chrome.")
        return
    
    # Save the token
    user_data['user_token'] = token
    user_data['sent_count'] = 0
    user_data['failed_count'] = 0
    user_data['total_rounds'] = 0
    
    if save_data(user_data):
        await ctx.send(f"✅ {test_result}\n"
                       f"📝 Token saved: `{token[:20]}...`")
    else:
        await ctx.send("❌ Failed to save token!")

@bot.command(name='testtoken')
async def test_token_cmd(ctx):
    """Test if the current token is valid."""
    token = user_data.get('user_token')
    
    if not token:
        await ctx.send("❌ No token set! Use `!settoken <token>` first.")
        return
    
    await ctx.send("🔍 Testing token... Please wait.")
    
    valid, result = await test_token(token)
    
    if valid:
        await ctx.send(f"✅ {result}")
    else:
        await ctx.send(f"❌ {result}")

@bot.command(name='addchannel')
async def add_channel(ctx, channel_id: str):
    """Add a channel ID to send messages to."""
    global user_data
    
    if not channel_id.isdigit():
        await ctx.send("❌ Invalid channel ID! Must be a number.")
        return
    
    if channel_id in user_data['channels']:
        await ctx.send(f"⚠️ Channel {channel_id} already in list!")
        return
    
    user_data['channels'].append(channel_id)
    save_data(user_data)
    
    try:
        channel = bot.get_channel(int(channel_id))
        if channel:
            await ctx.send(f"✅ Added: #{channel.name} (`{channel_id}`)")
        else:
            await ctx.send(f"✅ Added channel ID: `{channel_id}`")
    except:
        await ctx.send(f"✅ Added channel ID: `{channel_id}`")

@bot.command(name='removechannel')
async def remove_channel(ctx, channel_id: str):
    """Remove a channel ID from the list."""
    global user_data
    
    if channel_id in user_data['channels']:
        user_data['channels'].remove(channel_id)
        save_data(user_data)
        await ctx.send(f"✅ Removed: `{channel_id}`")
    else:
        await ctx.send(f"⚠️ Channel `{channel_id}` not found!")

@bot.command(name='listchannels')
async def list_channels(ctx):
    """List all channels that have been added."""
    channels = user_data.get('channels', [])
    
    if not channels:
        await ctx.send("📭 No channels added. Use `!addchannel <id>`")
        return
    
    channel_list = []
    for cid in channels:
        try:
            channel = bot.get_channel(int(cid))
            if channel:
                channel_list.append(f"#{channel.name} (`{cid}`)")
            else:
                channel_list.append(f"`{cid}` (unknown)")
        except:
            channel_list.append(f"`{cid}`")
    
    response = f"📋 **Channels ({len(channel_list)}):**\n" + "\n".join(f"• {ch}" for ch in channel_list)
    await ctx.send(response)

@bot.command(name='setmessage')
async def set_message(ctx, *, message: str):
    """Set the message to send."""
    global user_data
    
    if len(message) > 2000:
        await ctx.send("❌ Message too long! Max 2000 characters.")
        return
    
    user_data['message'] = message
    save_data(user_data)
    
    preview = message[:100] + "..." if len(message) > 100 else message
    await ctx.send(f"✅ Message set!\n```\n{preview}\n```")

@bot.command(name='setinterval')
async def set_interval(ctx, minutes: int):
    """Set the interval between sends (1-60 minutes)."""
    global user_data
    
    if minutes < 1:
        await ctx.send("❌ Interval must be at least 1 minute!")
        return
    
    if minutes > 60:
        await ctx.send("❌ Interval must be 60 minutes or less!")
        return
    
    user_data['schedule_interval'] = minutes
    save_data(user_data)
    
    await ctx.send(f"✅ Interval: **{minutes} minute(s)**")

@bot.command(name='start')
async def start_sending(ctx):
    """Start scheduled sending."""
    global user_data, sending_task
    
    if not user_data.get('user_token'):
        await ctx.send("❌ No token set! Use `!settoken <token>`")
        return
    
    if not user_data.get('channels'):
        await ctx.send("❌ No channels! Use `!addchannel <id>`")
        return
    
    if not user_data.get('message'):
        await ctx.send("❌ No message! Use `!setmessage <message>`")
        return
    
    if user_data.get('is_running', False):
        await ctx.send("⚠️ Already running! Use `!stop`")
        return
    
    interval = user_data.get('schedule_interval', 1)
    
    user_data['sent_count'] = 0
    user_data['failed_count'] = 0
    user_data['total_rounds'] = 0
    user_data['is_running'] = True
    user_data['start_time'] = datetime.datetime.now().isoformat()
    save_data(user_data)
    
    await ctx.send(f"🚀 **Started!**\n"
                   f"📊 Channels: {len(user_data['channels'])}\n"
                   f"⏱️ Interval: Every {interval} minute(s)")
    
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
        await ctx.send("⚠️ Not running!")
        return
    
    user_data['is_running'] = False
    save_data(user_data)
    
    if sending_task and not sending_task.done():
        sending_task.cancel()
        try:
            await sending_task
        except asyncio.CancelledError:
            pass
    
    await ctx.send(f"🛑 **Stopped!**\n"
                   f"✅ Sent: {user_data.get('sent_count', 0)}\n"
                   f"❌ Failed: {user_data.get('failed_count', 0)}")

@bot.command(name='sendnow')
async def send_now(ctx):
    """Send one round immediately (doesn't affect schedule)."""
    await ctx.send("📨 Sending one round...")
    success = await send_one_round()
    if success:
        await ctx.send("✅ Round sent!")
    else:
        await ctx.send("❌ Failed. Check configuration.")

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
    
    status_emoji = "🟢" if running else "🔴"
    status_text = "**Running**" if running else "**Stopped**"
    
    response = f"""📊 **Bot Status**
{status_emoji} Status: {status_text}
👤 Token: `{token[:20] if token else 'Not set'}...`
📋 Channels: {len(channels)}
📝 Message: `{message[:50] if message else 'Not set'}...`
⏱️ Interval: Every {interval} minute(s)
📊 Total Rounds: {rounds}
✅ Sent: {sent}
❌ Failed: {failed}
"""
    await ctx.send(response)

@bot.command(name='clear')
async def clear_settings(ctx):
    """Clear all settings (token, channels, message)."""
    global user_data
    
    if user_data.get('is_running', False):
        await ctx.send("❌ Cannot clear while running! Use `!stop`")
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
    
    save_data(user_data)
    await ctx.send("🗑️ **All settings cleared!**")

@bot.command(name='commands')
async def show_commands(ctx):
    """Show all available commands."""
    help_text = """
📋 **Available Commands:**

**Setup:**
`!settoken <token>` - Set ANY token from Chrome
`!testtoken` - Test if current token is valid
`!addchannel <id>` - Add channel
`!removechannel <id>` - Remove channel
`!listchannels` - List channels
`!setmessage <msg>` - Set message
`!setinterval <min>` - Set interval (1-60 min)

**Control:**
`!start` - Start sending
`!stop` - Stop sending
`!sendnow` - Send one round
`!status` - Show status

**Other:**
`!clear` - Clear settings
`!commands` - Show this menu

**How to get token from Chrome:**
1. Open Discord in Chrome
2. Press F12 → Application → Local Storage → https://discord.com
3. Find the "token" key
4. Copy the value (any format: OTA, mfa., token., etc.)
5. Use: `!settoken <token>`

**Example:**
`!settoken OTAxNjY1MzgzNjc5OTUwODc4.GMJRO-j8Z221bljbpbzVSmyYTNW6qPx8gFgqokl2uZCo`
"""
    await ctx.send(help_text)

# =============================================================
# ERROR HANDLING
# =============================================================

@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.MissingRequiredArgument):
        await ctx.send(f"❌ Missing argument! Use `!commands`")
    elif isinstance(error, commands.BadArgument):
        await ctx.send(f"❌ Invalid argument! Use `!commands`")
    elif isinstance(error, commands.CommandNotFound):
        await ctx.send(f"❌ Unknown command! Use `!commands`")
    else:
        await ctx.send(f"❌ Error: {str(error)}")
        print(f"Error: {error}")

# =============================================================
# MAIN
# =============================================================

if __name__ == '__main__':
    if not BOT_TOKEN or BOT_TOKEN == 'YOUR_BOT_TOKEN_HERE':
        print("❌ Please set BOT_TOKEN in environment variables!")
        print("   Railway: Add BOT_TOKEN in Variables tab")
        exit(1)
    
    print("🚀 Starting Discord Scheduled Bot...")
    print(f"📁 Data file: {DATA_FILE}")
    
    try:
        bot.run(BOT_TOKEN)
    except discord.LoginFailure:
        print("❌ Invalid bot token!")
    except Exception as e:
        print(f"❌ Error: {str(e)}")