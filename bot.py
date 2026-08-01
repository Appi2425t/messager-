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
import sys

# =============================================================
# WEB SERVER FOR RAILWAY HEALTHCHECK
# =============================================================

try:
    from flask import Flask
    import threading
    FLASK_AVAILABLE = True
except ImportError:
    FLASK_AVAILABLE = False

if FLASK_AVAILABLE:
    app = Flask(__name__)
    
    @app.route('/')
    def healthcheck():
        return "Bot is running!", 200
    
    @app.route('/health')
    def health():
        return "OK", 200
    
    def run_web_server():
        try:
            port = int(os.environ.get('PORT', 8080))
            app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False)
        except Exception as e:
            print(f"⚠️ Web server error: {e}")
    
    def start_web_server():
        thread = threading.Thread(target=run_web_server, daemon=True)
        thread.start()
        print("🌐 Web server started on port 8080 for healthchecks")
else:
    def start_web_server():
        print("⚠️ Flask not installed - healthcheck will not work")

# =============================================================
# CONFIGURATION
# =============================================================

BOT_TOKEN = os.environ.get('BOT_TOKEN', '')
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
    'failed_channel_id': None,
    'failed_logs': []
}

# =============================================================
# DATA MANAGEMENT
# =============================================================

def load_data():
    try:
        if os.path.exists(DATA_FILE):
            with open(DATA_FILE, 'r') as f:
                data = json.load(f)
                # Ensure all keys exist
                for key in DEFAULT_SETTINGS:
                    if key not in data:
                        data[key] = DEFAULT_SETTINGS[key]
                return data
        return DEFAULT_SETTINGS.copy()
    except Exception as e:
        print(f"⚠️ Error loading data: {e}")
        return DEFAULT_SETTINGS.copy()

def save_data(data):
    try:
        with open(DATA_FILE, 'w') as f:
            json.dump(data, f, indent=4)
        return True
    except Exception as e:
        print(f"⚠️ Error saving data: {e}")
        return False

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
    embed.set_footer(text="developed by @yathishyt ⚡")
    return embed

async def send_panel(ctx, title: str, content: str, color: discord.Color = discord.Color.blue(), success: bool = None, channel=None):
    """Send a panel-style message to a channel."""
    embed = create_panel(title, content, color, success)
    try:
        if channel:
            await channel.send(embed=embed)
        else:
            await ctx.send(embed=embed)
    except Exception as e:
        print(f"⚠️ Failed to send panel: {e}")

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
            print(f"⚠️ Failed channel {failed_channel_id} not found")
            return
        
        if 'failed_logs' not in user_data:
            user_data['failed_logs'] = []
        user_data['failed_logs'].append({
            'timestamp': datetime.datetime.now().isoformat(),
            'channel_id': channel_id,
            'reason': reason,
            'token_preview': token_preview
        })
        
        if len(user_data['failed_logs']) > 100:
            user_data['failed_logs'] = user_data['failed_logs'][-100:]
        save_data(user_data)
        
        embed = discord.Embed(
            title="❌ MESSAGE FAILED",
            description=f"**Channel ID:** `{channel_id}`\n**Reason:** {reason}\n**Time:** {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            color=discord.Color.red(),
            timestamp=datetime.datetime.now()
        )
        embed.set_footer(text="developed by @yathishyt ⚡")
        await failed_channel.send(embed=embed)
        
    except Exception as e:
        print(f"⚠️ Error logging failed message: {e}")

# =============================================================
# TOKEN HANDLING
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
    return token if len(token) > 10 else None

async def test_token(token: str):
    """Test if a token is valid."""
    token = clean_token(token)
    if not token:
        return False, "Token too short"
    
    url = "https://discord.com/api/v9/users/@me"
    headers = {'Authorization': token, 'Content-Type': 'application/json'}
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers, timeout=10) as response:
                if response.status == 200:
                    data = await response.json()
                    return True, f"✅ Valid! Logged in as: `{data.get('username')}` (`{data.get('id')}`)"
                elif response.status == 401:
                    headers2 = {'Authorization': f'Bot {token}', 'Content-Type': 'application/json'}
                    async with session.get(url, headers=headers2, timeout=10) as response2:
                        if response2.status == 200:
                            data = await response2.json()
                            return True, f"✅ Valid Bot token! Logged in as: `{data.get('username')}`"
                    return False, "❌ Invalid token"
                else:
                    return False, f"❌ HTTP {response.status}"
    except asyncio.TimeoutError:
        return False, "❌ Connection timeout"
    except Exception as e:
        return False, f"❌ Error: {str(e)}"

async def send_message_with_token(channel_id: str, message: str, token: str) -> bool:
    """Send a message using ANY token format."""
    global rate_limited, rate_limit_until
    
    token = clean_token(token)
    if not token:
        return False
    
    if rate_limited and time.time() < rate_limit_until:
        await asyncio.sleep(rate_limit_until - time.time())
        rate_limited = False
    
    url = f"https://discord.com/api/v9/channels/{channel_id}/messages"
    headers = {'Authorization': token, 'Content-Type': 'application/json'}
    payload = {'content': message, 'tts': False}
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, json=payload, timeout=15) as response:
                if response.status == 200:
                    return True
                elif response.status == 429:
                    data = await response.json()
                    retry_after = data.get('retry_after', 5)
                    rate_limited = True
                    rate_limit_until = time.time() + retry_after
                    await asyncio.sleep(retry_after)
                    return await send_message_with_token(channel_id, message, token)
                else:
                    await log_failed_message(channel_id, f"HTTP {response.status}", token[:20])
                    return False
    except asyncio.TimeoutError:
        await log_failed_message(channel_id, "Timeout", token[:20])
        return False
    except Exception as e:
        await log_failed_message(channel_id, f"Error: {str(e)}", token[:20])
        return False

async def send_one_round():
    """Send one round of messages to all channels."""
    global user_data
    
    token = user_data.get('user_token')
    channels = user_data.get('channels', [])
    message = user_data.get('message')
    
    if not token or not channels or not message:
        return False
    
    sent = 0
    failed = 0
    
    for channel_id in channels:
        if await send_message_with_token(channel_id, message, token):
            sent += 1
        else:
            failed += 1
        await asyncio.sleep(1)
    
    user_data['sent_count'] = user_data.get('sent_count', 0) + sent
    user_data['failed_count'] = user_data.get('failed_count', 0) + failed
    user_data['total_rounds'] = user_data.get('total_rounds', 0) + 1
    user_data['last_send_time'] = datetime.datetime.now().isoformat()
    save_data(user_data)
    
    return True

async def scheduled_send_task():
    """Background task that sends messages on a schedule."""
    global user_data
    
    if not user_data.get('is_running', False):
        return
    
    interval_minutes = user_data.get('schedule_interval', 1)
    interval_seconds = interval_minutes * 60
    
    print(f"\n🔄 Scheduled messenger started! Every {interval_minutes} minute(s)")
    
    while user_data.get('is_running', False):
        try:
            await send_one_round()
            for i in range(interval_seconds):
                if not user_data.get('is_running', False):
                    break
                await asyncio.sleep(1)
        except Exception as e:
            print(f"❌ Error: {e}")
            await asyncio.sleep(10)
    
    print(f"\n🛑 Scheduled messenger stopped!")

# =============================================================
# BOT COMMANDS
# =============================================================

@bot.event
async def on_ready():
    print(f'✅ Bot is online!')
    print(f'🤖 Bot Name: {bot.user.name}')
    print(f'🆔 Bot ID: {bot.user.id}')
    print(f'📡 Connected to {len(bot.guilds)} servers')
    
    if user_data.get('is_running', False):
        global sending_task
        if sending_task is None or sending_task.done():
            sending_task = asyncio.create_task(scheduled_send_task())

@bot.command(name='settoken')
async def set_token(ctx, *, token: str):
    token = clean_token(token)
    if not token:
        await send_panel(ctx, "SET TOKEN", "❌ Invalid token!", success=False)
        return
    
    await send_panel(ctx, "SET TOKEN", "🔍 Testing token...", color=discord.Color.blue())
    valid, result = await test_token(token)
    
    if not valid:
        await send_panel(ctx, "SET TOKEN", f"❌ {result}", success=False)
        return
    
    user_data['user_token'] = token
    save_data(user_data)
    await send_panel(ctx, "SET TOKEN", f"✅ {result}\n\n📝 Token saved!", success=True)

@bot.command(name='testtoken')
async def test_token_cmd(ctx):
    token = user_data.get('user_token')
    if not token:
        await send_panel(ctx, "TEST TOKEN", "❌ No token set!", success=False)
        return
    
    await send_panel(ctx, "TEST TOKEN", "🔍 Testing token...", color=discord.Color.blue())
    valid, result = await test_token(token)
    
    if valid:
        await send_panel(ctx, "TEST TOKEN", f"✅ {result}", success=True)
    else:
        await send_panel(ctx, "TEST TOKEN", f"❌ {result}", success=False)

@bot.command(name='addchannel')
async def add_channel(ctx, channel_id: str):
    if not channel_id.isdigit():
        await send_panel(ctx, "ADD CHANNEL", "❌ Invalid channel ID!", success=False)
        return
    
    if channel_id in user_data.get('channels', []):
        await send_panel(ctx, "ADD CHANNEL", f"⚠️ Channel `{channel_id}` already added!", success=False)
        return
    
    user_data['channels'].append(channel_id)
    save_data(user_data)
    await send_panel(ctx, "ADD CHANNEL", f"✅ Channel `{channel_id}` added!\nTotal: **{len(user_data['channels'])}**", success=True)

@bot.command(name='removechannel')
async def remove_channel(ctx, channel_id: str):
    if channel_id in user_data.get('channels', []):
        user_data['channels'].remove(channel_id)
        save_data(user_data)
        await send_panel(ctx, "REMOVE CHANNEL", f"✅ Channel `{channel_id}` removed!", success=True)
    else:
        await send_panel(ctx, "REMOVE CHANNEL", f"⚠️ Channel `{channel_id}` not found!", success=False)

@bot.command(name='listchannels')
async def list_channels(ctx):
    channels = user_data.get('channels', [])
    if not channels:
        await send_panel(ctx, "LIST CHANNELS", "📭 No channels added.", success=False)
        return
    
    content = "**Total:** " + str(len(channels)) + "\n\n" + "\n".join([f"• `{c}`" for c in channels])
    await send_panel(ctx, "LIST CHANNELS", content, success=True)

@bot.command(name='setmessage')
async def set_message(ctx, *, message: str):
    if len(message) > 2000:
        await send_panel(ctx, "SET MESSAGE", "❌ Message too long!", success=False)
        return
    
    user_data['message'] = message
    save_data(user_data)
    await send_panel(ctx, "SET MESSAGE", f"✅ Message set!\n\n```{message[:100]}```", success=True)

@bot.command(name='setinterval')
async def set_interval(ctx, minutes: int):
    if minutes < 1 or minutes > 60:
        await send_panel(ctx, "SET INTERVAL", "❌ Must be 1-60 minutes!", success=False)
        return
    
    user_data['schedule_interval'] = minutes
    save_data(user_data)
    await send_panel(ctx, "SET INTERVAL", f"✅ Every **{minutes} minute(s)**", success=True)

@bot.command(name='failed')
async def set_failed_channel(ctx, channel_id: str):
    if not channel_id.isdigit():
        await send_panel(ctx, "SET FAILED CHANNEL", "❌ Invalid channel ID!", success=False)
        return
    
    try:
        channel = bot.get_channel(int(channel_id))
        if not channel:
            await send_panel(ctx, "SET FAILED CHANNEL", "❌ Channel not found!", success=False)
            return
    except:
        await send_panel(ctx, "SET FAILED CHANNEL", "❌ Invalid channel!", success=False)
        return
    
    user_data['failed_channel_id'] = channel_id
    save_data(user_data)
    await send_panel(ctx, "SET FAILED CHANNEL", f"✅ Failed logs will be sent to `{channel_id}`", success=True)

@bot.command(name='failedlogs')
async def show_failed_logs(ctx):
    logs = user_data.get('failed_logs', [])
    if not logs:
        await send_panel(ctx, "FAILED LOGS", "📭 No failed logs.", success=True)
        return
    
    recent = logs[-10:]
    content = "**Recent Failed Attempts:**\n\n" + "\n".join([
        f"• `{l.get('timestamp', '')[:16]}` | Channel: `{l.get('channel_id')}` | {l.get('reason', 'Unknown')}"
        for l in recent
    ])
    await send_panel(ctx, "FAILED LOGS", content, color=discord.Color.orange(), success=False)

@bot.command(name='start')
async def start_sending(ctx):
    global user_data, sending_task
    
    if not user_data.get('user_token'):
        await send_panel(ctx, "START", "❌ No token set!", success=False)
        return
    if not user_data.get('channels'):
        await send_panel(ctx, "START", "❌ No channels added!", success=False)
        return
    if not user_data.get('message'):
        await send_panel(ctx, "START", "❌ No message set!", success=False)
        return
    if user_data.get('is_running', False):
        await send_panel(ctx, "START", "⚠️ Already running!", success=False)
        return
    
    user_data['is_running'] = True
    user_data['sent_count'] = 0
    user_data['failed_count'] = 0
    user_data['total_rounds'] = 0
    user_data['start_time'] = datetime.datetime.now().isoformat()
    save_data(user_data)
    
    await send_panel(ctx, "START", f"🚀 **Started!**\n📊 Channels: {len(user_data['channels'])}\n⏱️ Interval: Every {user_data['schedule_interval']} minute(s)", success=True)
    
    sending_task = asyncio.create_task(scheduled_send_task())

@bot.command(name='stop')
async def stop_sending(ctx):
    global user_data, sending_task
    
    if not user_data.get('is_running', False):
        await send_panel(ctx, "STOP", "⚠️ Not running!", success=False)
        return
    
    user_data['is_running'] = False
    save_data(user_data)
    
    if sending_task and not sending_task.done():
        sending_task.cancel()
    
    await send_panel(ctx, "STOP", f"🛑 **Stopped!**\n✅ Sent: {user_data.get('sent_count', 0)}\n❌ Failed: {user_data.get('failed_count', 0)}", success=True)

@bot.command(name='sendnow')
async def send_now(ctx):
    await send_panel(ctx, "SEND NOW", "📨 Sending one round...", color=discord.Color.blue())
    await send_one_round()
    await send_panel(ctx, "SEND NOW", f"✅ Done!\n✅ Sent: {user_data.get('sent_count', 0)}\n❌ Failed: {user_data.get('failed_count', 0)}", success=True)

@bot.command(name='status')
async def show_status(ctx):
    running = user_data.get('is_running', False)
    content = f"""{"🟢" if running else "🔴"} Status: **{"Running" if running else "Stopped"}**
👤 Token: `{user_data.get('user_token', 'Not set')[:20]}...`
📋 Channels: {len(user_data.get('channels', []))}
⏱️ Interval: Every {user_data.get('schedule_interval', 1)} minute(s)
✅ Sent: {user_data.get('sent_count', 0)}
❌ Failed: {user_data.get('failed_count', 0)}
📊 Rounds: {user_data.get('total_rounds', 0)}
📋 Failed Logs: `{user_data.get('failed_channel_id', 'Not set')}`"""
    
    await send_panel(ctx, "STATUS", content, color=discord.Color.blue(), success=running)

@bot.command(name='clear')
async def clear_settings(ctx):
    if user_data.get('is_running', False):
        await send_panel(ctx, "CLEAR", "❌ Cannot clear while running!", success=False)
        return
    
    user_data.update(DEFAULT_SETTINGS)
    save_data(user_data)
    await send_panel(ctx, "CLEAR", "🗑️ All settings cleared!", success=True)

@bot.command(name='commands')
async def show_commands(ctx):
    content = """
**Setup Commands:**
`!settoken <token>` - Set token
`!testtoken` - Test token
`!addchannel <id>` - Add channel
`!removechannel <id>` - Remove channel
`!listchannels` - List channels
`!setmessage <msg>` - Set message
`!setinterval <min>` - Set interval
`!failed <channel_id>` - Set failed logs channel
`!failedlogs` - Show failed logs

**Control Commands:**
`!start` - Start sending
`!stop` - Stop sending
`!sendnow` - Send one round
`!status` - Show status

**Other:**
`!clear` - Clear settings
`!commands` - Show this menu
"""
    await send_panel(ctx, "COMMANDS", content, color=discord.Color.blue())

# =============================================================
# ERROR HANDLING
# =============================================================

@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.MissingRequiredArgument):
        await send_panel(ctx, "ERROR", "❌ Missing argument! Use `!commands`", success=False)
    elif isinstance(error, commands.BadArgument):
        await send_panel(ctx, "ERROR", "❌ Invalid argument! Use `!commands`", success=False)
    elif isinstance(error, commands.CommandNotFound):
        await send_panel(ctx, "ERROR", "❌ Unknown command! Use `!commands`", success=False)
    else:
        await send_panel(ctx, "ERROR", f"❌ {str(error)}", success=False)

# =============================================================
# MAIN
# =============================================================

def main():
    print("🚀 Starting Discord Scheduled Bot...")
    print(f"📁 Data file: {DATA_FILE}")
    print(f"📁 Flask available: {FLASK_AVAILABLE}")
    
    if not BOT_TOKEN or BOT_TOKEN == '':
        print("❌ No BOT_TOKEN found in environment variables!")
        print("   Please set BOT_TOKEN in Railway Variables tab")
        print("   Bot will stay running but cannot connect to Discord")
        return
    
    try:
        bot.run(BOT_TOKEN, log_handler=None)
    except discord.LoginFailure:
        print("❌ Invalid bot token! Please check BOT_TOKEN")
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == '__main__':
    # Start web server first
    start_web_server()
    
    # Then run the bot
    try:
        main()
    except KeyboardInterrupt:
        print("\n🛑 Bot stopped by user")
        sys.exit(0)
    except Exception as e:
        print(f"\n❌ Fatal error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
