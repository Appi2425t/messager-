#!/usr/bin/env python3
# =============================================================
# DISCORD BOT - SIMULTANEOUS MULTI-ACCOUNT MESSENGER (REDIS)
# =============================================================
# - 30 SECOND DELAY between messages
# - FIXED: data variable scope issue
# - FIXED: Token expired handling
# - ALL accounts send simultaneously
# =============================================================

import discord
from discord.ext import commands
import asyncio
import json
import os
import time
import aiohttp
import datetime
import sys
import redis
import random

try:
    from flask import Flask, request, jsonify
    import threading
    FLASK_AVAILABLE = True
except ImportError:
    FLASK_AVAILABLE = False

# =============================================================
# REDIS DATABASE CONNECTION
# =============================================================

class RedisManager:
    def __init__(self):
        self.client = None
        self.connected = False
        
    def connect(self):
        try:
            redis_url = os.environ.get('REDIS_URL', '')
            
            if redis_url:
                self.client = redis.from_url(redis_url, decode_responses=True)
            else:
                redis_host = os.environ.get('REDIS_HOST', 'localhost')
                redis_port = int(os.environ.get('REDIS_PORT', 6379))
                redis_password = os.environ.get('REDIS_PASSWORD', '')
                redis_db = int(os.environ.get('REDIS_DB', 0))
                
                self.client = redis.Redis(
                    host=redis_host,
                    port=redis_port,
                    password=redis_password,
                    db=redis_db,
                    decode_responses=True
                )
            
            self.client.ping()
            self.connected = True
            print("✅ Redis connected successfully!")
            return True
            
        except Exception as e:
            print(f"⚠️ Redis connection failed: {e}")
            self.connected = False
            return False
    
    def get(self, key: str):
        if not self.connected:
            return None
        try:
            return self.client.get(key)
        except Exception as e:
            return None
    
    def set(self, key: str, value):
        if not self.connected:
            return False
        try:
            if value is None:
                return False
            if isinstance(value, (dict, list)):
                value = json.dumps(value)
            self.client.set(key, value)
            return True
        except Exception as e:
            print(f"⚠️ Redis set error: {e}")
            return False
    
    def delete(self, key: str):
        if not self.connected:
            return False
        try:
            self.client.delete(key)
            return True
        except Exception as e:
            return False
    
    def keys(self, pattern: str = '*'):
        if not self.connected:
            return []
        try:
            return self.client.keys(pattern)
        except Exception as e:
            return []
    
    def hset(self, name: str, key: str, value):
        if not self.connected:
            return False
        try:
            if value is None:
                return False
            if isinstance(value, (dict, list)):
                value = json.dumps(value)
            self.client.hset(name, key, value)
            return True
        except Exception as e:
            print(f"⚠️ Redis hset error: {e}")
            return False
    
    def hget(self, name: str, key: str):
        if not self.connected:
            return None
        try:
            return self.client.hget(name, key)
        except Exception as e:
            return None
    
    def hgetall(self, name: str):
        if not self.connected:
            return {}
        try:
            result = self.client.hgetall(name)
            return result if result else {}
        except Exception as e:
            print(f"⚠️ Redis hgetall error: {e}")
            return {}
    
    def hdel(self, name: str, key: str):
        if not self.connected:
            return False
        try:
            self.client.hdel(name, key)
            return True
        except Exception as e:
            return False
    
    def incr(self, key: str):
        if not self.connected:
            return 0
        try:
            return self.client.incr(key)
        except Exception as e:
            return 0

redis_manager = RedisManager()

# =============================================================
# GLOBAL DATA (Accessible everywhere)
# =============================================================

# This is the global data variable that all functions can access
bot_data = {
    'accounts': {},
    'active_account': None,
    'total_sent': 0,
    'total_failed': 0
}

# =============================================================
# DATA MANAGEMENT
# =============================================================

KEY_ACCOUNTS = 'bot:accounts'
KEY_ACTIVE_ACCOUNT = 'bot:active_account'
KEY_TOTAL_SENT = 'bot:total_sent'
KEY_TOTAL_FAILED = 'bot:total_failed'
KEY_ACCOUNT_PREFIX = 'bot:account:'

def load_data():
    """Load data from Redis into global bot_data."""
    global bot_data
    
    try:
        if not redis_manager.connected:
            bot_data = {'accounts': {}, 'active_account': None, 'total_sent': 0, 'total_failed': 0}
            return bot_data
        
        accounts_raw = redis_manager.get(KEY_ACCOUNTS)
        accounts = json.loads(accounts_raw) if accounts_raw else {}
        
        active_account = redis_manager.get(KEY_ACTIVE_ACCOUNT)
        total_sent = int(redis_manager.get(KEY_TOTAL_SENT) or 0)
        total_failed = int(redis_manager.get(KEY_TOTAL_FAILED) or 0)
        
        for account_name in list(accounts.keys()):
            account_data = redis_manager.hgetall(f"{KEY_ACCOUNT_PREFIX}{account_name}")
            if account_data:
                for key, value in account_data.items():
                    try:
                        if key in ['channels', 'failed_logs']:
                            account_data[key] = json.loads(value) if value else []
                        elif key in ['sent_count', 'failed_count', 'total_rounds', 'schedule_interval', 'message_delay']:
                            account_data[key] = int(value) if value else 0
                        elif key == 'is_running':
                            account_data[key] = value == 'True'
                    except:
                        pass
                accounts[account_name] = account_data
        
        bot_data = {
            'accounts': accounts,
            'active_account': active_account,
            'total_sent': total_sent,
            'total_failed': total_failed
        }
        
        return bot_data
        
    except Exception as e:
        print(f"⚠️ Error loading data from Redis: {e}")
        bot_data = {'accounts': {}, 'active_account': None, 'total_sent': 0, 'total_failed': 0}
        return bot_data

def save_data():
    """Save global bot_data to Redis."""
    global bot_data
    
    try:
        if not redis_manager.connected:
            return False
        
        accounts = bot_data.get('accounts', {})
        redis_manager.set(KEY_ACCOUNTS, json.dumps(accounts))
        redis_manager.set(KEY_ACTIVE_ACCOUNT, bot_data.get('active_account', '') or '')
        redis_manager.set(KEY_TOTAL_SENT, bot_data.get('total_sent', 0))
        redis_manager.set(KEY_TOTAL_FAILED, bot_data.get('total_failed', 0))
        
        for account_name, account_data in accounts.items():
            if account_data:
                hash_key = f"{KEY_ACCOUNT_PREFIX}{account_name}"
                for field, value in account_data.items():
                    if value is not None:
                        if isinstance(value, (dict, list)):
                            redis_manager.hset(hash_key, field, json.dumps(value))
                        elif isinstance(value, bool):
                            redis_manager.hset(hash_key, field, str(value))
                        else:
                            redis_manager.hset(hash_key, field, str(value))
        
        return True
        
    except Exception as e:
        print(f"⚠️ Error saving data to Redis: {e}")
        return False

def update_account(account_name: str, account_data: dict):
    """Update a single account in Redis and sync global data."""
    global bot_data
    
    try:
        if not redis_manager.connected:
            return False
        
        if not account_data:
            return False
        
        # Update global data
        if account_name in bot_data['accounts']:
            bot_data['accounts'][account_name] = account_data
        
        # Save to Redis
        hash_key = f"{KEY_ACCOUNT_PREFIX}{account_name}"
        for field, value in account_data.items():
            if value is not None:
                if isinstance(value, (dict, list)):
                    redis_manager.hset(hash_key, field, json.dumps(value))
                elif isinstance(value, bool):
                    redis_manager.hset(hash_key, field, str(value))
                else:
                    redis_manager.hset(hash_key, field, str(value))
        
        return True
        
    except Exception as e:
        print(f"⚠️ Error updating account in Redis: {e}")
        return False

def delete_account(account_name: str):
    """Delete an account from Redis and global data."""
    global bot_data
    
    try:
        if not redis_manager.connected:
            return False
        
        hash_key = f"{KEY_ACCOUNT_PREFIX}{account_name}"
        redis_manager.delete(hash_key)
        
        accounts_raw = redis_manager.get(KEY_ACCOUNTS)
        accounts = json.loads(accounts_raw) if accounts_raw else {}
        if account_name in accounts:
            del accounts[account_name]
            redis_manager.set(KEY_ACCOUNTS, json.dumps(accounts))
        
        # Remove from global data
        if account_name in bot_data['accounts']:
            del bot_data['accounts'][account_name]
        
        return True
        
    except Exception as e:
        print(f"⚠️ Error deleting account from Redis: {e}")
        return False

# =============================================================
# WEB SERVER
# =============================================================

if FLASK_AVAILABLE:
    app = Flask(__name__)
    
    @app.route('/')
    @app.route('/health')
    def healthcheck():
        return "Bot is running!", 200
    
    def run_web_server():
        try:
            port = int(os.environ.get('PORT', 8080))
            app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False)
        except Exception as e:
            print(f"⚠️ Web server error: {e}")
    
    def start_web_server():
        thread = threading.Thread(target=run_web_server, daemon=True)
        thread.start()
        print("🌐 Web server started")
else:
    def start_web_server():
        print("⚠️ Flask not installed")

# =============================================================
# CONFIGURATION
# =============================================================

BOT_TOKEN = os.environ.get('BOT_TOKEN', '')
DEFAULT_DELAY = 30

DEFAULT_ACCOUNT = {
    'token': None,
    'channels': [],
    'message': None,
    'schedule_interval': 1,
    'is_running': False,
    'sent_count': 0,
    'failed_count': 0,
    'total_rounds': 0,
    'failed_channel_id': None,
    'failed_logs': [],
    'message_delay': DEFAULT_DELAY
}

# =============================================================
# DISCORD BOT
# =============================================================

intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True

bot = commands.Bot(command_prefix='!', intents=intents)

# Connect to Redis
redis_manager.connect()

# Load initial data
load_data()

sending_tasks = {}
rate_limited = {}
rate_limit_until = {}

# =============================================================
# PANEL REPLY HELPER
# =============================================================

def create_panel(title: str, content: str, color=None, success=None) -> discord.Embed:
    if color is None:
        color = discord.Color.blue()
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
    embed.set_footer(text="developed by @yathishyt ⚡ | 30s Delay Mode")
    return embed

async def send_panel(ctx, title: str, content: str, success=None, color=None):
    embed = create_panel(title, content, color, success)
    try:
        await ctx.send(embed=embed)
    except Exception as e:
        print(f"⚠️ Failed to send panel: {e}")

# =============================================================
# TOKEN HANDLING
# =============================================================

def clean_token(token: str) -> str:
    if not token:
        return None
    token = token.strip()
    if token.startswith('"') and token.endswith('"'):
        token = token[1:-1]
    if token.startswith("'") and token.endswith("'"):
        token = token[1:-1]
    token = token.replace('"', '').replace("'", '').replace('`', '')
    token = token.replace(' ', '')
    return token if len(token) > 10 else None

async def test_token(token: str):
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
                    return True, f"✅ {data.get('username')}#{data.get('discriminator', '0')}"
                elif response.status == 401:
                    return False, "❌ TOKEN EXPIRED - Get new one from Chrome"
                else:
                    return False, f"❌ HTTP {response.status}"
    except Exception as e:
        return False, f"❌ Error: {str(e)}"

# =============================================================
# SEND MESSAGE FUNCTIONS (FIXED)
# =============================================================

async def send_single_message(channel_id: str, message: str, token: str, account_name: str) -> tuple:
    """Send a single message to a channel."""
    global bot_data
    
    token = clean_token(token)
    if not token:
        return False, "Invalid token"
    
    if account_name not in rate_limited:
        rate_limited[account_name] = False
        rate_limit_until[account_name] = 0
    
    if rate_limited.get(account_name, False) and time.time() < rate_limit_until.get(account_name, 0):
        wait_time = rate_limit_until[account_name] - time.time()
        print(f"⏳ [{account_name}] Rate limited, waiting {wait_time:.2f}s...")
        await asyncio.sleep(wait_time + 1)
        rate_limited[account_name] = False
    
    url = f"https://discord.com/api/v9/channels/{channel_id}/messages"
    headers = {'Authorization': token, 'Content-Type': 'application/json'}
    payload = {'content': message, 'tts': False}
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, json=payload, timeout=30) as response:
                if response.status == 200 or response.status == 201:
                    return True, None
                elif response.status == 429:
                    data = await response.json()
                    retry_after = data.get('retry_after', 30)
                    print(f"⚠️ [{account_name}] Rate limited! Waiting {retry_after:.2f}s...")
                    rate_limited[account_name] = True
                    rate_limit_until[account_name] = time.time() + retry_after + 2
                    await asyncio.sleep(retry_after + 2)
                    return await send_single_message(channel_id, message, token, account_name)
                elif response.status == 401:
                    print(f"❌ [{account_name}] TOKEN EXPIRED! Channel: {channel_id}")
                    await log_failed_message(account_name, channel_id, "TOKEN EXPIRED - Get new token from Chrome")
                    
                    # Stop the account
                    if account_name in bot_data['accounts']:
                        bot_data['accounts'][account_name]['is_running'] = False
                        update_account(account_name, bot_data['accounts'][account_name])
                        save_data()
                    
                    return False, "TOKEN EXPIRED"
                elif response.status == 403:
                    print(f"❌ [{account_name}] No permission in {channel_id}")
                    await log_failed_message(account_name, channel_id, "No permission to send")
                    return False, "No permission"
                elif response.status == 400:
                    print(f"❌ [{account_name}] Bad request for {channel_id}")
                    await log_failed_message(account_name, channel_id, "Bad request - message too long?")
                    return False, "Bad request"
                else:
                    print(f"❌ [{account_name}] Failed: HTTP {response.status} on {channel_id}")
                    await log_failed_message(account_name, channel_id, f"HTTP {response.status}")
                    return False, f"HTTP {response.status}"
    except asyncio.TimeoutError:
        print(f"⏳ [{account_name}] Timeout on {channel_id}")
        await log_failed_message(account_name, channel_id, "Timeout")
        return False, "Timeout"
    except Exception as e:
        print(f"❌ [{account_name}] Error on {channel_id}: {str(e)}")
        await log_failed_message(account_name, channel_id, str(e))
        return False, str(e)

async def send_round_for_account(account_name: str) -> dict:
    """Send one round for a single account."""
    global bot_data
    
    if account_name not in bot_data['accounts']:
        return {'sent': 0, 'failed': 0, 'account': account_name}
    
    account_data = bot_data['accounts'][account_name]
    
    token = account_data.get('token')
    channels = account_data.get('channels', [])
    message = account_data.get('message')
    
    if not token or not channels or not message:
        return {'sent': 0, 'failed': 0, 'account': account_name}
    
    # Check if token is expired before sending
    test_valid, _ = await test_token(token)
    if not test_valid:
        print(f"❌ [{account_name}] Token expired! Stopping account.")
        account_data['is_running'] = False
        update_account(account_name, account_data)
        save_data()
        return {'sent': 0, 'failed': 0, 'account': account_name, 'error': 'Token expired'}
    
    message_delay = account_data.get('message_delay', DEFAULT_DELAY)
    
    print(f"📨 [{account_name}] Sending to {len(channels)} channels (delay: {message_delay}s)...")
    
    sent = 0
    failed = 0
    
    for index, channel_id in enumerate(channels, 1):
        print(f"  📤 [{account_name}] {channel_id}...")
        success, error = await send_single_message(channel_id, message, token, account_name)
        
        if success:
            sent += 1
            print(f"    ✅ [{account_name}] Sent!")
        else:
            failed += 1
            print(f"    ❌ [{account_name}] Failed: {error}")
        
        # Wait between messages (30 seconds default)
        if index < len(channels):
            print(f"  ⏳ [{account_name}] Waiting {message_delay}s before next message...")
            await asyncio.sleep(message_delay)
    
    # Update stats
    account_data['sent_count'] = account_data.get('sent_count', 0) + sent
    account_data['failed_count'] = account_data.get('failed_count', 0) + failed
    account_data['total_rounds'] = account_data.get('total_rounds', 0) + 1
    bot_data['total_sent'] = bot_data.get('total_sent', 0) + sent
    bot_data['total_failed'] = bot_data.get('total_failed', 0) + failed
    
    update_account(account_name, account_data)
    save_data()
    
    print(f"  📊 [{account_name}] Round complete: ✅ {sent} sent | ❌ {failed} failed")
    
    return {'sent': sent, 'failed': failed, 'account': account_name}

async def send_round_for_all_accounts():
    """Send one round for ALL running accounts simultaneously."""
    global bot_data
    
    accounts = bot_data.get('accounts', {})
    running_accounts = [name for name, acc in accounts.items() if acc.get('is_running', False)]
    
    if not running_accounts:
        return
    
    print(f"\n🔄 Sending round for {len(running_accounts)} accounts simultaneously...")
    print(f"⏳ Each account has {DEFAULT_DELAY}s delay between messages")
    
    tasks = []
    for account_name in running_accounts:
        tasks.append(send_round_for_account(account_name))
    
    results = await asyncio.gather(*tasks)
    
    total_sent = sum(r.get('sent', 0) for r in results)
    total_failed = sum(r.get('failed', 0) for r in results)
    
    print(f"  📊 Round complete: ✅ {total_sent} sent | ❌ {total_failed} failed\n")
    
    return results

async def log_failed_message(account_name: str, channel_id: str, reason: str):
    """Log a failed message to the failed channel."""
    global bot_data
    
    if account_name not in bot_data['accounts']:
        return
    
    account_data = bot_data['accounts'][account_name]
    failed_channel_id = account_data.get('failed_channel_id')
    if not failed_channel_id:
        return
    
    try:
        failed_channel = bot.get_channel(int(failed_channel_id))
        if not failed_channel:
            return
        
        if 'failed_logs' not in account_data:
            account_data['failed_logs'] = []
        account_data['failed_logs'].append({
            'timestamp': datetime.datetime.now().isoformat(),
            'channel_id': channel_id,
            'reason': reason
        })
        if len(account_data['failed_logs']) > 50:
            account_data['failed_logs'] = account_data['failed_logs'][-50:]
        
        update_account(account_name, account_data)
        save_data()
        
        embed = discord.Embed(
            title=f"❌ [{account_name}] MESSAGE FAILED",
            description=f"**Account:** `{account_name}`\n**Channel:** `{channel_id}`\n**Reason:** {reason}\n**Time:** {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            color=discord.Color.red(),
            timestamp=datetime.datetime.now()
        )
        embed.set_footer(text="developed by @yathishyt ⚡ | 30s Delay Mode")
        await failed_channel.send(embed=embed)
        
    except Exception as e:
        print(f"⚠️ Error logging: {e}")

async def scheduled_send_task():
    """Main scheduled task that sends for ALL running accounts."""
    global bot_data
    
    while True:
        try:
            running = any(acc.get('is_running', False) for acc in bot_data['accounts'].values())
            if not running:
                await asyncio.sleep(5)
                continue
            
            await send_round_for_all_accounts()
            
            min_interval = 1
            for acc in bot_data['accounts'].values():
                if acc.get('is_running', False):
                    interval = acc.get('schedule_interval', 1)
                    if interval < min_interval:
                        min_interval = interval
            
            await asyncio.sleep(min_interval * 60)
            
        except Exception as e:
            print(f"❌ Error in scheduled task: {e}")
            await asyncio.sleep(10)

# =============================================================
# BOT COMMANDS
# =============================================================

global_send_task = None

@bot.event
async def on_ready():
    global global_send_task
    
    print(f'✅ Bot online: {bot.user.name}')
    print(f'📡 Connected to {len(bot.guilds)} servers')
    print(f'🗄️ Redis: {"Connected" if redis_manager.connected else "Disconnected (using JSON fallback)"}')
    print(f'⏳ Default message delay: {DEFAULT_DELAY} seconds')
    
    if global_send_task is None or global_send_task.done():
        global_send_task = asyncio.create_task(scheduled_send_task())
        print("✅ Global send task started")

# -------- COMMANDS --------

@bot.command(name='setdelay')
async def set_delay(ctx, seconds: int):
    """Set delay between messages for active account (in seconds)."""
    global bot_data
    
    account_name = bot_data.get('active_account')
    if not account_name or account_name not in bot_data['accounts']:
        await send_panel(ctx, "SET DELAY", "❌ No active account! Use `!account <name>` first.", success=False)
        return
    
    account_data = bot_data['accounts'][account_name]
    
    if seconds < 5:
        await send_panel(ctx, "SET DELAY", "❌ Delay must be at least 5 seconds!", success=False)
        return
    
    if seconds > 300:
        await send_panel(ctx, "SET DELAY", "❌ Delay cannot exceed 300 seconds (5 minutes)!", success=False)
        return
    
    account_data['message_delay'] = seconds
    update_account(account_name, account_data)
    save_data()
    
    await send_panel(ctx, "SET DELAY", 
        f"✅ Delay set for `{account_name}`: **{seconds} seconds** between messages!\n"
        f"⏳ This will help avoid rate limits.", 
        success=True)

@bot.command(name='addaccount')
async def add_account(ctx, account_name: str, *, token: str):
    global bot_data
    
    if account_name in bot_data['accounts']:
        await send_panel(ctx, "ADD ACCOUNT", f"❌ Account `{account_name}` already exists!", success=False)
        return
    
    token = clean_token(token)
    if not token:
        await send_panel(ctx, "ADD ACCOUNT", "❌ Invalid token!", success=False)
        return
    
    await send_panel(ctx, "ADD ACCOUNT", f"🔍 Testing token for `{account_name}`...", color=discord.Color.blue())
    valid, result = await test_token(token)
    
    if not valid:
        await send_panel(ctx, "ADD ACCOUNT", f"❌ {result}", success=False)
        return
    
    account_data = DEFAULT_ACCOUNT.copy()
    account_data['token'] = token
    account_data['message_delay'] = DEFAULT_DELAY
    bot_data['accounts'][account_name] = account_data
    bot_data['active_account'] = account_name
    
    update_account(account_name, account_data)
    save_data()
    
    await send_panel(ctx, "ADD ACCOUNT", 
        f"✅ **Account Added!**\n📛 Name: `{account_name}`\n{result}\n\n"
        f"⏳ Default delay: **{DEFAULT_DELAY}s** between messages\n"
        f"Use `!setdelay <seconds>` to change", 
        success=True)

@bot.command(name='accounts')
async def list_accounts(ctx):
    global bot_data
    
    accounts = bot_data.get('accounts', {})
    
    if not accounts:
        await send_panel(ctx, "ACCOUNTS", "📭 No accounts added.", success=False)
        return
    
    content = "**📋 All Accounts:**\n\n"
    for name, acc in accounts.items():
        status = "🟢 Running" if acc.get('is_running', False) else "🔴 Stopped"
        channels = len(acc.get('channels', []))
        delay = acc.get('message_delay', DEFAULT_DELAY)
        content += f"• **{name}**\n  └ Status: {status} | Channels: {channels} | Delay: {delay}s\n\n"
    
    content += f"\n🗄️ **Redis Storage:** {'Connected ✅' if redis_manager.connected else 'Disconnected ❌'}"
    content += f"\n⏳ **Default Delay:** {DEFAULT_DELAY}s between messages"
    await send_panel(ctx, "ACCOUNTS", content, success=True)

@bot.command(name='account')
async def select_account(ctx, account_name: str):
    global bot_data
    
    if account_name not in bot_data['accounts']:
        await send_panel(ctx, "ACCOUNT", f"❌ Account `{account_name}` not found!", success=False)
        return
    
    bot_data['active_account'] = account_name
    save_data()
    
    account_data = bot_data['accounts'][account_name]
    status = "🟢 Running" if account_data.get('is_running', False) else "🔴 Stopped"
    delay = account_data.get('message_delay', DEFAULT_DELAY)
    
    content = f"""**Selected Account:** `{account_name}`
Status: {status}
Channels: {len(account_data.get('channels', []))}
Interval: Every {account_data.get('schedule_interval', 1)} minute(s)
Delay: {delay}s between messages
Sent: {account_data.get('sent_count', 0)}
Failed: {account_data.get('failed_count', 0)}

**🗄️ Redis Storage:** {'Connected ✅' if redis_manager.connected else 'Disconnected ❌'}

**Commands:**
`!addchannel <id1,id2,id3>` - Add multiple channels
`!setmessage <msg>` - Set message (or attach .txt)
`!setdelay <seconds>` - Set delay between messages
`!start` - Start this account
`!stop` - Stop this account
"""
    await send_panel(ctx, "ACCOUNT", content, success=True)

@bot.command(name='removeaccount')
async def remove_account(ctx, account_name: str):
    global bot_data
    
    if account_name not in bot_data['accounts']:
        await send_panel(ctx, "REMOVE ACCOUNT", f"❌ Account `{account_name}` not found!", success=False)
        return
    
    if bot_data['accounts'][account_name].get('is_running', False):
        bot_data['accounts'][account_name]['is_running'] = False
    
    delete_account(account_name)
    
    if bot_data.get('active_account') == account_name:
        bot_data['active_account'] = None
    
    save_data()
    await send_panel(ctx, "REMOVE ACCOUNT", f"✅ Account `{account_name}` removed!", success=True)

def get_active_account(ctx):
    global bot_data
    
    account_name = bot_data.get('active_account')
    if not account_name:
        return None, "❌ No active account!\nUse `!account <name>` to select one."
    
    if account_name not in bot_data['accounts']:
        return None, f"❌ Account `{account_name}` no longer exists!"
    
    return bot_data['accounts'][account_name], None

@bot.command(name='addchannel')
async def add_channel(ctx, *, channel_ids: str):
    global bot_data
    
    account_data, error = get_active_account(ctx)
    if not account_data:
        await send_panel(ctx, "ADD CHANNEL", error, success=False)
        return
    
    channel_list = []
    for separator in [',', ';', ' ']:
        if separator in channel_ids:
            channel_list = [c.strip() for c in channel_ids.split(separator) if c.strip()]
            break
    
    if not channel_list:
        channel_list = [channel_ids.strip()]
    
    added = []
    skipped = []
    invalid = []
    
    for cid in channel_list:
        if not cid.isdigit():
            invalid.append(cid)
            continue
        
        if cid in account_data.get('channels', []):
            skipped.append(cid)
            continue
        
        account_data['channels'].append(cid)
        added.append(cid)
    
    account_name = bot_data.get('active_account')
    update_account(account_name, account_data)
    save_data()
    
    response_parts = []
    if added:
        response_parts.append(f"✅ Added: `{', '.join(added)}`")
    if skipped:
        response_parts.append(f"⚠️ Skipped (already exist): `{', '.join(skipped)}`")
    if invalid:
        response_parts.append(f"❌ Invalid: `{', '.join(invalid)}`")
    
    delay = account_data.get('message_delay', DEFAULT_DELAY)
    response_parts.append(f"📊 Total channels: **{len(account_data['channels'])}**")
    response_parts.append(f"⏳ Delay: **{delay}s** between messages")
    
    await send_panel(ctx, "ADD CHANNEL", "\n".join(response_parts), success=True if added else False)

@bot.command(name='removechannel')
async def remove_channel(ctx, *, channel_ids: str):
    global bot_data
    
    account_data, error = get_active_account(ctx)
    if not account_data:
        await send_panel(ctx, "REMOVE CHANNEL", error, success=False)
        return
    
    channel_list = []
    for separator in [',', ';', ' ']:
        if separator in channel_ids:
            channel_list = [c.strip() for c in channel_ids.split(separator) if c.strip()]
            break
    
    if not channel_list:
        channel_list = [channel_ids.strip()]
    
    removed = []
    not_found = []
    
    for cid in channel_list:
        if cid in account_data.get('channels', []):
            account_data['channels'].remove(cid)
            removed.append(cid)
        else:
            not_found.append(cid)
    
    account_name = bot_data.get('active_account')
    update_account(account_name, account_data)
    save_data()
    
    response_parts = []
    if removed:
        response_parts.append(f"✅ Removed: `{', '.join(removed)}`")
    if not_found:
        response_parts.append(f"⚠️ Not found: `{', '.join(not_found)}`")
    
    response_parts.append(f"📊 Total channels: **{len(account_data['channels'])}**")
    
    await send_panel(ctx, "REMOVE CHANNEL", "\n".join(response_parts), success=True if removed else False)

@bot.command(name='listchannels')
async def list_channels(ctx):
    global bot_data
    
    account_data, error = get_active_account(ctx)
    if not account_data:
        await send_panel(ctx, "LIST CHANNELS", error, success=False)
        return
    
    channels = account_data.get('channels', [])
    if not channels:
        await send_panel(ctx, "LIST CHANNELS", f"📭 No channels added for `{bot_data.get('active_account')}`.", success=False)
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
    
    delay = account_data.get('message_delay', DEFAULT_DELAY)
    content = f"**Account:** `{bot_data.get('active_account')}`\n**Total:** {len(channels)}\n⏳ **Delay:** {delay}s\n\n" + "\n".join(channel_list)
    await send_panel(ctx, "LIST CHANNELS", content, success=True)

@bot.command(name='setmessage')
async def set_message(ctx, *, message: str = None):
    global bot_data
    
    account_data, error = get_active_account(ctx)
    if not account_data:
        await send_panel(ctx, "SET MESSAGE", error, success=False)
        return
    
    if message is None:
        if ctx.message.attachments:
            for attachment in ctx.message.attachments:
                if attachment.filename.endswith('.txt'):
                    try:
                        content = await attachment.read()
                        message = content.decode('utf-8')
                        break
                    except Exception as e:
                        await send_panel(ctx, "SET MESSAGE", f"❌ Error reading file: {str(e)}", success=False)
                        return
                else:
                    await send_panel(ctx, "SET MESSAGE", "❌ Please attach a `.txt` file!", success=False)
                    return
        else:
            await send_panel(ctx, "SET MESSAGE", 
                "❌ Please provide a message or attach a `.txt` file!\n\n"
                "**For long messages:**\n"
                "1. Create `message.txt`\n"
                "2. Type `!setmessage`\n"
                "3. Attach the `.txt` file\n"
                "4. Send", 
                success=False)
            return
    
    if len(message) > 4000:
        await send_panel(ctx, "SET MESSAGE", f"❌ Message too long! Max 4000 characters. You have **{len(message)}** characters.", success=False)
        return
    
    account_data['message'] = message
    account_name = bot_data.get('active_account')
    update_account(account_name, account_data)
    save_data()
    
    preview = message[:150] + "..." if len(message) > 150 else message
    await send_panel(ctx, "SET MESSAGE", 
        f"✅ Message set for `{account_name}`!\n\n"
        f"```\n{preview}\n```\n\n"
        f"📊 **Length:** {len(message)} characters\n"
        f"⏳ Delay: {account_data.get('message_delay', DEFAULT_DELAY)}s between messages", 
        success=True)

@bot.command(name='setinterval')
async def set_interval(ctx, minutes: int):
    global bot_data
    
    account_data, error = get_active_account(ctx)
    if not account_data:
        await send_panel(ctx, "SET INTERVAL", error, success=False)
        return
    
    if minutes < 1 or minutes > 60:
        await send_panel(ctx, "SET INTERVAL", "❌ Must be 1-60 minutes!", success=False)
        return
    
    account_data['schedule_interval'] = minutes
    account_name = bot_data.get('active_account')
    update_account(account_name, account_data)
    save_data()
    
    await send_panel(ctx, "SET INTERVAL", 
        f"✅ Interval set for `{account_name}`: Every **{minutes} minute(s)**", 
        success=True)

@bot.command(name='failed')
async def set_failed_channel(ctx, channel_id: str):
    global bot_data
    
    account_data, error = get_active_account(ctx)
    if not account_data:
        await send_panel(ctx, "SET FAILED CHANNEL", error, success=False)
        return
    
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
    
    account_data['failed_channel_id'] = channel_id
    account_name = bot_data.get('active_account')
    update_account(account_name, account_data)
    save_data()
    
    await send_panel(ctx, "SET FAILED CHANNEL", 
        f"✅ Failed logs for `{account_name}` will go to `{channel_id}`", 
        success=True)

@bot.command(name='failedlogs')
async def show_failed_logs(ctx):
    global bot_data
    
    account_data, error = get_active_account(ctx)
    if not account_data:
        await send_panel(ctx, "FAILED LOGS", error, success=False)
        return
    
    logs = account_data.get('failed_logs', [])
    if not logs:
        await send_panel(ctx, "FAILED LOGS", f"📭 No failed logs for `{bot_data.get('active_account')}`.", success=True)
        return
    
    recent = logs[-10:]
    content = f"**Account:** `{bot_data.get('active_account')}`\n\n" + "\n".join([
        f"• `{l.get('timestamp', '')[:16]}` | Channel: `{l.get('channel_id')}` | {l.get('reason', 'Unknown')}"
        for l in recent
    ])
    await send_panel(ctx, "FAILED LOGS", content, success=False)

@bot.command(name='start')
async def start_account(ctx):
    global bot_data
    
    account_name = bot_data.get('active_account')
    if not account_name or account_name not in bot_data['accounts']:
        await send_panel(ctx, "START", "❌ No active account! Use `!account <name>` first.", success=False)
        return
    
    account_data = bot_data['accounts'][account_name]
    
    if not account_data.get('token'):
        await send_panel(ctx, "START", "❌ No token set!", success=False)
        return
    if not account_data.get('channels'):
        await send_panel(ctx, "START", "❌ No channels added!", success=False)
        return
    if not account_data.get('message'):
        await send_panel(ctx, "START", "❌ No message set!", success=False)
        return
    if account_data.get('is_running', False):
        await send_panel(ctx, "START", "⚠️ Already running!", success=False)
        return
    
    # Test token before starting
    valid, result = await test_token(account_data.get('token'))
    if not valid:
        await send_panel(ctx, "START", f"❌ Token is invalid or expired!\n{result}\n\nGet a new token from Chrome and use `!settoken <new_token>`", success=False)
        return
    
    account_data['is_running'] = True
    account_data['sent_count'] = 0
    account_data['failed_count'] = 0
    account_data['total_rounds'] = 0
    
    update_account(account_name, account_data)
    save_data()
    
    running = [name for name, acc in bot_data['accounts'].items() if acc.get('is_running', False)]
    delay = account_data.get('message_delay', DEFAULT_DELAY)
    
    await send_panel(ctx, "START", 
        f"🚀 **Started `{account_name}`!**\n"
        f"📊 Channels: {len(account_data['channels'])}\n"
        f"⏱️ Interval: Every {account_data['schedule_interval']} minute(s)\n"
        f"⏳ Delay: **{delay}s** between messages\n\n"
        f"🔄 **Running accounts: {len(running)}**", 
        success=True)

@bot.command(name='stop')
async def stop_account(ctx):
    global bot_data
    
    account_name = bot_data.get('active_account')
    if not account_name or account_name not in bot_data['accounts']:
        await send_panel(ctx, "STOP", "❌ No active account!", success=False)
        return
    
    account_data = bot_data['accounts'][account_name]
    
    if not account_data.get('is_running', False):
        await send_panel(ctx, "STOP", "⚠️ Not running!", success=False)
        return
    
    account_data['is_running'] = False
    update_account(account_name, account_data)
    save_data()
    
    await send_panel(ctx, "STOP", 
        f"🛑 **Stopped `{account_name}`!**\n"
        f"✅ Sent: {account_data.get('sent_count', 0)}\n"
        f"❌ Failed: {account_data.get('failed_count', 0)}", 
        success=True)

@bot.command(name='sendnow')
async def send_now(ctx):
    global bot_data
    
    running = [name for name, acc in bot_data['accounts'].items() if acc.get('is_running', False)]
    
    if not running:
        await send_panel(ctx, "SEND NOW", "❌ No accounts running!", success=False)
        return
    
    await send_panel(ctx, "SEND NOW", f"📨 Sending for **{len(running)} accounts**...\n⏳ {DEFAULT_DELAY}s delay between messages", color=discord.Color.blue())
    
    results = await send_round_for_all_accounts()
    
    total_sent = sum(r.get('sent', 0) for r in results) if results else 0
    total_failed = sum(r.get('failed', 0) for r in results) if results else 0
    
    await send_panel(ctx, "SEND NOW", 
        f"✅ Done!\n\n"
        f"✅ Total Sent: **{total_sent}**\n"
        f"❌ Total Failed: **{total_failed}**\n"
        f"⏳ Delay used: **{DEFAULT_DELAY}s** between messages", 
        success=True)

@bot.command(name='startall')
async def start_all_accounts(ctx):
    global bot_data
    
    accounts = bot_data.get('accounts', {})
    if not accounts:
        await send_panel(ctx, "START ALL", "❌ No accounts found!", success=False)
        return
    
    started = 0
    for name, acc in accounts.items():
        if not acc.get('is_running', False):
            if acc.get('token') and acc.get('channels') and acc.get('message'):
                # Test token before starting
                valid, _ = await test_token(acc.get('token'))
                if valid:
                    acc['is_running'] = True
                    acc['sent_count'] = 0
                    acc['failed_count'] = 0
                    acc['total_rounds'] = 0
                    started += 1
                    update_account(name, acc)
    
    save_data()
    
    running = [name for name, acc in bot_data['accounts'].items() if acc.get('is_running', False)]
    
    await send_panel(ctx, "START ALL", 
        f"🚀 **Started {started} accounts!**\n"
        f"📊 Total Running: **{len(running)}**\n"
        f"⏳ Delay: **{DEFAULT_DELAY}s** between messages", 
        success=True)

@bot.command(name='stopall')
async def stop_all_accounts(ctx):
    global bot_data
    
    accounts = bot_data.get('accounts', {})
    stopped = 0
    
    for name, acc in accounts.items():
        if acc.get('is_running', False):
            acc['is_running'] = False
            stopped += 1
            update_account(name, acc)
    
    save_data()
    
    await send_panel(ctx, "STOP ALL", f"🛑 **Stopped {stopped} accounts!**", success=True)

@bot.command(name='status')
async def show_status(ctx):
    global bot_data
    
    account_name = bot_data.get('active_account')
    if not account_name or account_name not in bot_data['accounts']:
        await send_panel(ctx, "STATUS", "❌ No active account! Use `!account <name>` first.", success=False)
        return
    
    account_data = bot_data['accounts'][account_name]
    running = account_data.get('is_running', False)
    all_running = [name for name, acc in bot_data['accounts'].items() if acc.get('is_running', False)]
    delay = account_data.get('message_delay', DEFAULT_DELAY)
    
    content = f"""**Account:** `{account_name}`
{"🟢" if running else "🔴"} Status: **{"Running" if running else "Stopped"}**
👤 Token: `{account_data.get('token', 'Not set')[:20]}...`
📋 Channels: {len(account_data.get('channels', []))}
⏱️ Interval: Every {account_data.get('schedule_interval', 1)} minute(s)
⏳ Delay: **{delay}s** between messages
✅ Sent: {account_data.get('sent_count', 0)}
❌ Failed: {account_data.get('failed_count', 0)}
📊 Rounds: {account_data.get('total_rounds', 0)}

**Global Stats:**
🔄 Running: **{len(all_running)}**
✅ Total Sent: {bot_data.get('total_sent', 0)}
❌ Total Failed: {bot_data.get('total_failed', 0)}
📋 Total Accounts: {len(bot_data.get('accounts', {}))}

🗄️ Redis: {"Connected ✅" if redis_manager.connected else "Disconnected ❌"}"""
    
    await send_panel(ctx, "STATUS", content, success=running)

@bot.command(name='clear')
async def clear_settings(ctx):
    global bot_data
    
    account_data, error = get_active_account(ctx)
    if not account_data:
        await send_panel(ctx, "CLEAR", error, success=False)
        return
    
    if account_data.get('is_running', False):
        await send_panel(ctx, "CLEAR", "❌ Cannot clear while running!", success=False)
        return
    
    for key in DEFAULT_ACCOUNT:
        if key != 'token':
            account_data[key] = DEFAULT_ACCOUNT[key]
    
    account_name = bot_data.get('active_account')
    update_account(account_name, account_data)
    save_data()
    
    await send_panel(ctx, "CLEAR", f"🗑️ Settings cleared for `{account_name}`!", success=True)

@bot.command(name='commands')
async def show_commands(ctx):
    content = """
**📋 Multi-Account Commands (30s Delay Mode)**

**Account Management:**
`!addaccount <name> <token>` - Add new account
`!accounts` - List all accounts
`!account <name>` - Select active account
`!removeaccount <name>` - Remove account

**Configuration:**
`!addchannel <id1,id2,id3>` - Add multiple channels
`!removechannel <id1,id2,id3>` - Remove channels
`!listchannels` - List channels
`!setmessage <msg>` - Set message (or attach .txt)
`!setinterval <min>` - Set interval (1-60 min)
`!setdelay <seconds>` - Set delay between messages (5-300s)
`!failed <channel_id>` - Set failed logs channel
`!failedlogs` - Show failed logs

**Control:**
`!start` - Start active account
`!stop` - Stop active account
`!startall` - Start ALL accounts
`!stopall` - Stop ALL accounts
`!sendnow` - Send one round
`!status` - Show status
`!clear` - Clear settings

**Other:**
`!commands` - Show this menu

**⚡ ALL running accounts send simultaneously!**
**⏳ Default delay: 30 seconds between messages**
**🗄️ All data stored in Redis**"""
    await send_panel(ctx, "COMMANDS", content, color=discord.Color.blue())

# =============================================================
# ERROR HANDLING
# =============================================================

@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.MissingRequiredArgument):
        await send_panel(ctx, "ERROR", "❌ Missing argument! Use `!commands`", success=False)
    elif isinstance(error, commands.CommandNotFound):
        pass
    else:
        await send_panel(ctx, "ERROR", f"❌ {str(error)}", success=False)

# =============================================================
# MAIN
# =============================================================

def main():
    print("🚀 Starting Multi-Account Bot (30s Delay Mode)...")
    print(f"🗄️ Redis: {'Connected' if redis_manager.connected else 'Disconnected (JSON fallback)'}")
    print(f"⏳ Default delay: {DEFAULT_DELAY} seconds between messages")
    
    if not BOT_TOKEN:
        print("❌ No BOT_TOKEN found! Set in Railway Variables")
        return
    
    try:
        bot.run(BOT_TOKEN)
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == '__main__':
    start_web_server()
    try:
        main()
    except KeyboardInterrupt:
        print("\n🛑 Bot stopped")
        sys.exit(0)
    except Exception as e:
        print(f"❌ Fatal: {e}")
        sys.exit(1)
