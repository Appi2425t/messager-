#!/usr/bin/env python3
# =============================================================
# DISCORD BOT - SIMULTANEOUS MULTI-ACCOUNT MESSENGER (REDIS)
# =============================================================
# - ALL accounts send messages at the SAME TIME
# - Each account has independent channels/message/schedule
# - True parallel sending using asyncio.gather()
# - Redis database for persistent storage (Railway compatible)
# - Support for long messages via .txt file upload
# - Add multiple channels at once (comma-separated)
# - Failed logs per account
# - Professional panel replies with developer credit
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
    """Manages Redis database connection and data persistence."""
    
    def __init__(self):
        self.client = None
        self.connected = False
        
    def connect(self):
        """Connect to Redis using Railway environment variables."""
        try:
            # Get Redis URL from Railway environment
            redis_url = os.environ.get('REDIS_URL', '')
            
            if redis_url:
                # Use the Redis URL directly
                self.client = redis.from_url(redis_url, decode_responses=True)
            else:
                # Fallback to individual variables
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
            
            # Test connection
            self.client.ping()
            self.connected = True
            print("✅ Redis connected successfully!")
            print(f"📊 Redis DB: {self.client.info('server')['redis_version']}")
            return True
            
        except Exception as e:
            print(f"⚠️ Redis connection failed: {e}")
            print("💡 Falling back to JSON file storage...")
            self.connected = False
            return False
    
    def get(self, key: str):
        """Get value from Redis."""
        if not self.connected:
            return None
        try:
            return self.client.get(key)
        except Exception as e:
            print(f"⚠️ Redis get error: {e}")
            return None
    
    def set(self, key: str, value):
        """Set value in Redis."""
        if not self.connected:
            return False
        try:
            if isinstance(value, (dict, list)):
                value = json.dumps(value)
            self.client.set(key, value)
            return True
        except Exception as e:
            print(f"⚠️ Redis set error: {e}")
            return False
    
    def delete(self, key: str):
        """Delete key from Redis."""
        if not self.connected:
            return False
        try:
            self.client.delete(key)
            return True
        except Exception as e:
            print(f"⚠️ Redis delete error: {e}")
            return False
    
    def keys(self, pattern: str = '*'):
        """Get all keys matching pattern."""
        if not self.connected:
            return []
        try:
            return self.client.keys(pattern)
        except Exception as e:
            print(f"⚠️ Redis keys error: {e}")
            return []
    
    def hset(self, name: str, key: str, value):
        """Set hash field."""
        if not self.connected:
            return False
        try:
            if isinstance(value, (dict, list)):
                value = json.dumps(value)
            self.client.hset(name, key, value)
            return True
        except Exception as e:
            print(f"⚠️ Redis hset error: {e}")
            return False
    
    def hget(self, name: str, key: str):
        """Get hash field."""
        if not self.connected:
            return None
        try:
            return self.client.hget(name, key)
        except Exception as e:
            print(f"⚠️ Redis hget error: {e}")
            return None
    
    def hgetall(self, name: str):
        """Get all hash fields."""
        if not self.connected:
            return {}
        try:
            return self.client.hgetall(name)
        except Exception as e:
            print(f"⚠️ Redis hgetall error: {e}")
            return {}
    
    def hdel(self, name: str, key: str):
        """Delete hash field."""
        if not self.connected:
            return False
        try:
            self.client.hdel(name, key)
            return True
        except Exception as e:
            print(f"⚠️ Redis hdel error: {e}")
            return False
    
    def lpush(self, name: str, value):
        """Push to list."""
        if not self.connected:
            return False
        try:
            if isinstance(value, (dict, list)):
                value = json.dumps(value)
            self.client.lpush(name, value)
            return True
        except Exception as e:
            print(f"⚠️ Redis lpush error: {e}")
            return False
    
    def lrange(self, name: str, start: int = 0, end: int = -1):
        """Get list range."""
        if not self.connected:
            return []
        try:
            return self.client.lrange(name, start, end)
        except Exception as e:
            print(f"⚠️ Redis lrange error: {e}")
            return []
    
    def ltrim(self, name: str, start: int, end: int):
        """Trim list."""
        if not self.connected:
            return False
        try:
            self.client.ltrim(name, start, end)
            return True
        except Exception as e:
            print(f"⚠️ Redis ltrim error: {e}")
            return False
    
    def incr(self, key: str):
        """Increment counter."""
        if not self.connected:
            return 0
        try:
            return self.client.incr(key)
        except Exception as e:
            print(f"⚠️ Redis incr error: {e}")
            return 0

# Initialize Redis
redis_manager = RedisManager()

# =============================================================
# DATA MANAGEMENT WITH REDIS
# =============================================================

# Redis keys
KEY_ACCOUNTS = 'bot:accounts'
KEY_ACTIVE_ACCOUNT = 'bot:active_account'
KEY_TOTAL_SENT = 'bot:total_sent'
KEY_TOTAL_FAILED = 'bot:total_failed'
KEY_ACCOUNT_PREFIX = 'bot:account:'
KEY_LOGS_PREFIX = 'bot:logs:'
KEY_STATS = 'bot:stats'

def load_data():
    """Load data from Redis."""
    try:
        if not redis_manager.connected:
            return {}
        
        # Get accounts list
        accounts_raw = redis_manager.get(KEY_ACCOUNTS)
        accounts = json.loads(accounts_raw) if accounts_raw else {}
        
        # Get active account
        active_account = redis_manager.get(KEY_ACTIVE_ACCOUNT)
        
        # Get totals
        total_sent = int(redis_manager.get(KEY_TOTAL_SENT) or 0)
        total_failed = int(redis_manager.get(KEY_TOTAL_FAILED) or 0)
        
        # Load each account's full data
        for account_name in list(accounts.keys()):
            account_data = redis_manager.hgetall(f"{KEY_ACCOUNT_PREFIX}{account_name}")
            if account_data:
                # Parse JSON fields
                for key, value in account_data.items():
                    try:
                        if key in ['channels', 'failed_logs']:
                            account_data[key] = json.loads(value) if value else []
                        elif key in ['sent_count', 'failed_count', 'total_rounds', 'schedule_interval']:
                            account_data[key] = int(value) if value else 0
                        elif key == 'is_running':
                            account_data[key] = value == 'True'
                    except:
                        pass
                accounts[account_name] = account_data
        
        return {
            'accounts': accounts,
            'active_account': active_account,
            'total_sent': total_sent,
            'total_failed': total_failed
        }
        
    except Exception as e:
        print(f"⚠️ Error loading data from Redis: {e}")
        return {'accounts': {}, 'active_account': None, 'total_sent': 0, 'total_failed': 0}

def save_data(data):
    """Save data to Redis."""
    try:
        if not redis_manager.connected:
            return False
        
        # Save accounts list (names only)
        accounts = data.get('accounts', {})
        redis_manager.set(KEY_ACCOUNTS, json.dumps(accounts))
        
        # Save active account
        redis_manager.set(KEY_ACTIVE_ACCOUNT, data.get('active_account', ''))
        
        # Save totals
        redis_manager.set(KEY_TOTAL_SENT, data.get('total_sent', 0))
        redis_manager.set(KEY_TOTAL_FAILED, data.get('total_failed', 0))
        
        # Save each account's full data
        for account_name, account_data in accounts.items():
            hash_key = f"{KEY_ACCOUNT_PREFIX}{account_name}"
            for field, value in account_data.items():
                if isinstance(value, (dict, list)):
                    redis_manager.hset(hash_key, field, json.dumps(value))
                elif isinstance(value, bool):
                    redis_manager.hset(hash_key, field, str(value))
                else:
                    redis_manager.hset(hash_key, field, str(value) if value is not None else '')
        
        return True
        
    except Exception as e:
        print(f"⚠️ Error saving data to Redis: {e}")
        return False

def update_account(account_name: str, account_data: dict):
    """Update a single account in Redis."""
    try:
        if not redis_manager.connected:
            return False
        
        hash_key = f"{KEY_ACCOUNT_PREFIX}{account_name}"
        for field, value in account_data.items():
            if isinstance(value, (dict, list)):
                redis_manager.hset(hash_key, field, json.dumps(value))
            elif isinstance(value, bool):
                redis_manager.hset(hash_key, field, str(value))
            else:
                redis_manager.hset(hash_key, field, str(value) if value is not None else '')
        
        return True
        
    except Exception as e:
        print(f"⚠️ Error updating account in Redis: {e}")
        return False

def delete_account(account_name: str):
    """Delete an account from Redis."""
    try:
        if not redis_manager.connected:
            return False
        
        hash_key = f"{KEY_ACCOUNT_PREFIX}{account_name}"
        redis_manager.delete(hash_key)
        
        # Remove from accounts list
        accounts_raw = redis_manager.get(KEY_ACCOUNTS)
        accounts = json.loads(accounts_raw) if accounts_raw else {}
        if account_name in accounts:
            del accounts[account_name]
            redis_manager.set(KEY_ACCOUNTS, json.dumps(accounts))
        
        return True
        
    except Exception as e:
        print(f"⚠️ Error deleting account from Redis: {e}")
        return False

# =============================================================
# WEB SERVER (Keeps Railway Active)
# =============================================================

if FLASK_AVAILABLE:
    app = Flask(__name__)
    
    @app.route('/')
    @app.route('/health')
    def healthcheck():
        return "Bot is running!", 200
    
    @app.route('/redis-status')
    def redis_status():
        return jsonify({
            'status': 'connected' if redis_manager.connected else 'disconnected',
            'redis_version': redis_manager.client.info('server')['redis_version'] if redis_manager.connected else None
        })
    
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
    'failed_logs': []
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
data = load_data()

# Ensure default structure
if 'accounts' not in data:
    data['accounts'] = {}
if 'active_account' not in data:
    data['active_account'] = None
if 'total_sent' not in data:
    data['total_sent'] = 0
if 'total_failed' not in data:
    data['total_failed'] = 0

save_data(data)

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
    embed.set_footer(text="developed by @yathishyt ⚡ | Redis Mode")
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
                    headers2 = {'Authorization': f'Bot {token}', 'Content-Type': 'application/json'}
                    async with session.get(url, headers=headers2, timeout=10) as response2:
                        if response2.status == 200:
                            data = await response2.json()
                            return True, f"✅ Bot: {data.get('username')}"
                    return False, "❌ Invalid token"
                else:
                    return False, f"❌ HTTP {response.status}"
    except Exception as e:
        return False, f"❌ Error: {str(e)}"

# =============================================================
# SEND MESSAGE FUNCTIONS
# =============================================================

async def send_single_message(channel_id: str, message: str, token: str, account_name: str) -> tuple:
    token = clean_token(token)
    if not token:
        return False, "Invalid token"
    
    if account_name not in rate_limited:
        rate_limited[account_name] = False
        rate_limit_until[account_name] = 0
    
    if rate_limited.get(account_name, False) and time.time() < rate_limit_until.get(account_name, 0):
        await asyncio.sleep(rate_limit_until[account_name] - time.time())
        rate_limited[account_name] = False
    
    url = f"https://discord.com/api/v9/channels/{channel_id}/messages"
    headers = {'Authorization': token, 'Content-Type': 'application/json'}
    payload = {'content': message, 'tts': False}
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, json=payload, timeout=15) as response:
                if response.status == 200:
                    return True, None
                elif response.status == 429:
                    data = await response.json()
                    retry_after = data.get('retry_after', 5)
                    rate_limited[account_name] = True
                    rate_limit_until[account_name] = time.time() + retry_after
                    await asyncio.sleep(retry_after)
                    return await send_single_message(channel_id, message, token, account_name)
                else:
                    error_msg = f"HTTP {response.status}"
                    await log_failed_message(account_name, channel_id, error_msg)
                    return False, error_msg
    except Exception as e:
        error_msg = str(e)
        await log_failed_message(account_name, channel_id, error_msg)
        return False, error_msg

async def send_round_for_account(account_name: str) -> dict:
    global data
    
    account_data = data['accounts'].get(account_name)
    if not account_data:
        return {'sent': 0, 'failed': 0}
    
    token = account_data.get('token')
    channels = account_data.get('channels', [])
    message = account_data.get('message')
    
    if not token or not channels or not message:
        return {'sent': 0, 'failed': 0}
    
    sent = 0
    failed = 0
    
    tasks = []
    for channel_id in channels:
        tasks.append(send_single_message(channel_id, message, token, account_name))
    
    results = await asyncio.gather(*tasks)
    
    for success, error in results:
        if success:
            sent += 1
        else:
            failed += 1
    
    account_data['sent_count'] = account_data.get('sent_count', 0) + sent
    account_data['failed_count'] = account_data.get('failed_count', 0) + failed
    account_data['total_rounds'] = account_data.get('total_rounds', 0) + 1
    data['total_sent'] = data.get('total_sent', 0) + sent
    data['total_failed'] = data.get('total_failed', 0) + failed
    
    # Save to Redis
    update_account(account_name, account_data)
    save_data(data)
    
    return {'sent': sent, 'failed': failed, 'account': account_name}

async def send_round_for_all_accounts():
    global data
    
    accounts = data.get('accounts', {})
    running_accounts = [name for name, acc in accounts.items() if acc.get('is_running', False)]
    
    if not running_accounts:
        return
    
    print(f"\n🔄 Sending round for {len(running_accounts)} accounts simultaneously...")
    
    tasks = []
    for account_name in running_accounts:
        tasks.append(send_round_for_account(account_name))
    
    results = await asyncio.gather(*tasks)
    
    total_sent = sum(r.get('sent', 0) for r in results)
    total_failed = sum(r.get('failed', 0) for r in results)
    
    print(f"  📊 Round complete: ✅ {total_sent} sent | ❌ {total_failed} failed")
    
    return results

async def log_failed_message(account_name: str, channel_id: str, reason: str):
    global data
    
    account_data = data['accounts'].get(account_name)
    if not account_data:
        return
    
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
        if len(account_data['failed_logs']) > 100:
            account_data['failed_logs'] = account_data['failed_logs'][-100:]
        
        # Save to Redis
        update_account(account_name, account_data)
        
        embed = discord.Embed(
            title=f"❌ [{account_name}] MESSAGE FAILED",
            description=f"**Account:** `{account_name}`\n**Channel:** `{channel_id}`\n**Reason:** {reason}\n**Time:** {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            color=discord.Color.red(),
            timestamp=datetime.datetime.now()
        )
        embed.set_footer(text="developed by @yathishyt ⚡ | Redis Mode")
        await failed_channel.send(embed=embed)
        
    except Exception as e:
        print(f"⚠️ Error logging: {e}")

async def scheduled_send_task():
    global data
    
    while True:
        try:
            running = any(acc.get('is_running', False) for acc in data['accounts'].values())
            if not running:
                await asyncio.sleep(1)
                continue
            
            await send_round_for_all_accounts()
            
            min_interval = 1
            for acc in data['accounts'].values():
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
    
    if global_send_task is None or global_send_task.done():
        global_send_task = asyncio.create_task(scheduled_send_task())
        print("✅ Global send task started")

# -------- ACCOUNT MANAGEMENT --------

@bot.command(name='addaccount')
async def add_account(ctx, account_name: str, *, token: str):
    global data
    
    if account_name in data['accounts']:
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
    data['accounts'][account_name] = account_data
    data['active_account'] = account_name
    
    # Save to Redis
    update_account(account_name, account_data)
    save_data(data)
    
    await send_panel(ctx, "ADD ACCOUNT", 
        f"✅ **Account Added!**\n📛 Name: `{account_name}`\n{result}\n\n"
        f"🗄️ Data stored in Redis\n"
        f"Use `!account {account_name}` to configure it.", 
        success=True)

@bot.command(name='accounts')
async def list_accounts(ctx):
    accounts = data.get('accounts', {})
    
    if not accounts:
        await send_panel(ctx, "ACCOUNTS", "📭 No accounts added.", success=False)
        return
    
    content = "**📋 All Accounts:**\n\n"
    for name, acc in accounts.items():
        status = "🟢 Running" if acc.get('is_running', False) else "🔴 Stopped"
        channels = len(acc.get('channels', []))
        token_preview = acc.get('token', 'Not set')[:20] + '...' if acc.get('token') else 'Not set'
        content += f"• **{name}**\n  └ Status: {status} | Channels: {channels}\n\n"
    
    content += f"\n🗄️ **Redis Storage:** {'Connected ✅' if redis_manager.connected else 'Disconnected ❌'}"
    await send_panel(ctx, "ACCOUNTS", content, success=True)

@bot.command(name='account')
async def select_account(ctx, account_name: str):
    global data
    
    if account_name not in data['accounts']:
        await send_panel(ctx, "ACCOUNT", f"❌ Account `{account_name}` not found!", success=False)
        return
    
    data['active_account'] = account_name
    save_data(data)
    
    account_data = data['accounts'][account_name]
    status = "🟢 Running" if account_data.get('is_running', False) else "🔴 Stopped"
    
    content = f"""**Selected Account:** `{account_name}`
Status: {status}
Channels: {len(account_data.get('channels', []))}
Interval: Every {account_data.get('schedule_interval', 1)} minute(s)
Sent: {account_data.get('sent_count', 0)}
Failed: {account_data.get('failed_count', 0)}

**🗄️ Redis Storage:** {'Connected ✅' if redis_manager.connected else 'Disconnected ❌'}

**Commands now apply to this account:**
`!addchannel <id1,id2,id3>` - Add multiple channels
`!setmessage <msg>` - Set message (or attach .txt file)
`!start` - Start this account
`!stop` - Stop this account
"""
    await send_panel(ctx, "ACCOUNT", content, success=True)

@bot.command(name='removeaccount')
async def remove_account(ctx, account_name: str):
    global data
    
    if account_name not in data['accounts']:
        await send_panel(ctx, "REMOVE ACCOUNT", f"❌ Account `{account_name}` not found!", success=False)
        return
    
    if data['accounts'][account_name].get('is_running', False):
        data['accounts'][account_name]['is_running'] = False
    
    # Delete from Redis
    delete_account(account_name)
    del data['accounts'][account_name]
    
    if data.get('active_account') == account_name:
        data['active_account'] = None
    
    save_data(data)
    await send_panel(ctx, "REMOVE ACCOUNT", f"✅ Account `{account_name}` removed from Redis!", success=True)

# -------- ACCOUNT CONFIGURATION --------

def get_active_account(ctx):
    global data
    
    account_name = data.get('active_account')
    if not account_name:
        return None, "❌ No active account!\nUse `!account <name>` to select one."
    
    if account_name not in data['accounts']:
        return None, f"❌ Account `{account_name}` no longer exists!"
    
    return data['accounts'][account_name], None

@bot.command(name='addchannel')
async def add_channel(ctx, *, channel_ids: str):
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
    
    # Save to Redis
    update_account(data['active_account'], account_data)
    save_data(data)
    
    response_parts = []
    if added:
        response_parts.append(f"✅ Added: `{', '.join(added)}`")
    if skipped:
        response_parts.append(f"⚠️ Skipped (already exist): `{', '.join(skipped)}`")
    if invalid:
        response_parts.append(f"❌ Invalid: `{', '.join(invalid)}`")
    
    response_parts.append(f"📊 Total channels: **{len(account_data['channels'])}**")
    response_parts.append(f"🗄️ Saved to Redis ✅")
    
    await send_panel(ctx, "ADD CHANNEL", "\n".join(response_parts), success=True if added else False)

@bot.command(name='removechannel')
async def remove_channel(ctx, *, channel_ids: str):
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
    
    # Save to Redis
    update_account(data['active_account'], account_data)
    save_data(data)
    
    response_parts = []
    if removed:
        response_parts.append(f"✅ Removed: `{', '.join(removed)}`")
    if not_found:
        response_parts.append(f"⚠️ Not found: `{', '.join(not_found)}`")
    
    response_parts.append(f"📊 Total channels: **{len(account_data['channels'])}**")
    response_parts.append(f"🗄️ Saved to Redis ✅")
    
    await send_panel(ctx, "REMOVE CHANNEL", "\n".join(response_parts), success=True if removed else False)

@bot.command(name='listchannels')
async def list_channels(ctx):
    account_data, error = get_active_account(ctx)
    if not account_data:
        await send_panel(ctx, "LIST CHANNELS", error, success=False)
        return
    
    channels = account_data.get('channels', [])
    if not channels:
        await send_panel(ctx, "LIST CHANNELS", f"📭 No channels added for `{data['active_account']}`.", success=False)
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
    
    content = f"**Account:** `{data['active_account']}`\n**Total:** {len(channels)}\n\n" + "\n".join(channel_list)
    await send_panel(ctx, "LIST CHANNELS", content, success=True)

@bot.command(name='setmessage')
async def set_message(ctx, *, message: str = None):
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
                "**For long messages with newlines, use:**\n"
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
    
    # Save to Redis
    update_account(data['active_account'], account_data)
    save_data(data)
    
    preview = message[:150] + "..." if len(message) > 150 else message
    await send_panel(ctx, "SET MESSAGE", 
        f"✅ Message set for `{data['active_account']}`!\n\n"
        f"```\n{preview}\n```\n\n"
        f"📊 **Length:** {len(message)} characters\n"
        f"🗄️ Saved to Redis ✅", 
        success=True)

@bot.command(name='setinterval')
async def set_interval(ctx, minutes: int):
    account_data, error = get_active_account(ctx)
    if not account_data:
        await send_panel(ctx, "SET INTERVAL", error, success=False)
        return
    
    if minutes < 1 or minutes > 60:
        await send_panel(ctx, "SET INTERVAL", "❌ Must be 1-60 minutes!", success=False)
        return
    
    account_data['schedule_interval'] = minutes
    
    # Save to Redis
    update_account(data['active_account'], account_data)
    save_data(data)
    
    await send_panel(ctx, "SET INTERVAL", 
        f"✅ Interval set for `{data['active_account']}`: Every **{minutes} minute(s)**\n"
        f"🗄️ Saved to Redis ✅", 
        success=True)

@bot.command(name='failed')
async def set_failed_channel(ctx, channel_id: str):
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
    
    # Save to Redis
    update_account(data['active_account'], account_data)
    save_data(data)
    
    await send_panel(ctx, "SET FAILED CHANNEL", 
        f"✅ Failed logs for `{data['active_account']}` will go to `{channel_id}`\n"
        f"🗄️ Saved to Redis ✅", 
        success=True)

@bot.command(name='failedlogs')
async def show_failed_logs(ctx):
    account_data, error = get_active_account(ctx)
    if not account_data:
        await send_panel(ctx, "FAILED LOGS", error, success=False)
        return
    
    logs = account_data.get('failed_logs', [])
    if not logs:
        await send_panel(ctx, "FAILED LOGS", f"📭 No failed logs for `{data['active_account']}`.", success=True)
        return
    
    recent = logs[-10:]
    content = f"**Account:** `{data['active_account']}`\n\n" + "\n".join([
        f"• `{l.get('timestamp', '')[:16]}` | Channel: `{l.get('channel_id')}` | {l.get('reason', 'Unknown')}"
        for l in recent
    ])
    await send_panel(ctx, "FAILED LOGS", content, success=False)

@bot.command(name='start')
async def start_account(ctx):
    global data
    
    account_name = data.get('active_account')
    account_data, error = get_active_account(ctx)
    if not account_data:
        await send_panel(ctx, "START", error, success=False)
        return
    
    if not account_data.get('token'):
        await send_panel(ctx, "START", "❌ No token set for this account!", success=False)
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
    
    account_data['is_running'] = True
    account_data['sent_count'] = 0
    account_data['failed_count'] = 0
    account_data['total_rounds'] = 0
    
    # Save to Redis
    update_account(account_name, account_data)
    save_data(data)
    
    running = [name for name, acc in data['accounts'].items() if acc.get('is_running', False)]
    
    await send_panel(ctx, "START", 
        f"🚀 **Started `{account_name}`!**\n"
        f"📊 Channels: {len(account_data['channels'])}\n"
        f"⏱️ Interval: Every {account_data['schedule_interval']} minute(s)\n\n"
        f"🔄 **All running accounts ({len(running)}) will send simultaneously!**\n"
        f"🗄️ Data saved to Redis ✅", 
        success=True)

@bot.command(name='stop')
async def stop_account(ctx):
    global data
    
    account_name = data.get('active_account')
    account_data, error = get_active_account(ctx)
    if not account_data:
        await send_panel(ctx, "STOP", error, success=False)
        return
    
    if not account_data.get('is_running', False):
        await send_panel(ctx, "STOP", "⚠️ Not running!", success=False)
        return
    
    account_data['is_running'] = False
    
    # Save to Redis
    update_account(account_name, account_data)
    save_data(data)
    
    await send_panel(ctx, "STOP", 
        f"🛑 **Stopped `{account_name}`!**\n"
        f"✅ Sent: {account_data.get('sent_count', 0)}\n"
        f"❌ Failed: {account_data.get('failed_count', 0)}", 
        success=True)

@bot.command(name='sendnow')
async def send_now(ctx):
    global data
    
    running = [name for name, acc in data['accounts'].items() if acc.get('is_running', False)]
    
    if not running:
        await send_panel(ctx, "SEND NOW", "❌ No accounts are running!\nStart at least one account with `!start`", success=False)
        return
    
    await send_panel(ctx, "SEND NOW", f"📨 Sending one round for **{len(running)} accounts** simultaneously...", color=discord.Color.blue())
    
    results = await send_round_for_all_accounts()
    
    total_sent = sum(r.get('sent', 0) for r in results) if results else 0
    total_failed = sum(r.get('failed', 0) for r in results) if results else 0
    
    await send_panel(ctx, "SEND NOW", 
        f"✅ Done! **{len(running)} accounts** sent simultaneously!\n\n"
        f"✅ Total Sent: **{total_sent}**\n"
        f"❌ Total Failed: **{total_failed}**\n"
        f"🗄️ Data saved to Redis ✅", 
        success=True)

@bot.command(name='startall')
async def start_all_accounts(ctx):
    global data
    
    accounts = data.get('accounts', {})
    if not accounts:
        await send_panel(ctx, "START ALL", "❌ No accounts found!", success=False)
        return
    
    started = 0
    for name, acc in accounts.items():
        if not acc.get('is_running', False):
            if acc.get('token') and acc.get('channels') and acc.get('message'):
                acc['is_running'] = True
                acc['sent_count'] = 0
                acc['failed_count'] = 0
                acc['total_rounds'] = 0
                started += 1
                update_account(name, acc)
    
    save_data(data)
    
    running = [name for name, acc in data['accounts'].items() if acc.get('is_running', False)]
    
    await send_panel(ctx, "START ALL", 
        f"🚀 **Started {started} accounts!**\n"
        f"📊 Total Running: **{len(running)}**\n"
        f"🔄 All accounts will send simultaneously!\n"
        f"🗄️ Data saved to Redis ✅", 
        success=True)

@bot.command(name='stopall')
async def stop_all_accounts(ctx):
    global data
    
    accounts = data.get('accounts', {})
    stopped = 0
    
    for name, acc in accounts.items():
        if acc.get('is_running', False):
            acc['is_running'] = False
            stopped += 1
            update_account(name, acc)
    
    save_data(data)
    
    await send_panel(ctx, "STOP ALL", 
        f"🛑 **Stopped {stopped} accounts!**\n"
        f"🗄️ Data saved to Redis ✅", 
        success=True)

@bot.command(name='status')
async def show_status(ctx):
    account_name = data.get('active_account')
    account_data, error = get_active_account(ctx)
    if not account_data:
        await send_panel(ctx, "STATUS", error, success=False)
        return
    
    running = account_data.get('is_running', False)
    all_running = [name for name, acc in data['accounts'].items() if acc.get('is_running', False)]
    
    content = f"""**Account:** `{account_name}`
{"🟢" if running else "🔴"} Status: **{"Running" if running else "Stopped"}**
👤 Token: `{account_data.get('token', 'Not set')[:20]}...`
📋 Channels: {len(account_data.get('channels', []))}
⏱️ Interval: Every {account_data.get('schedule_interval', 1)} minute(s)
✅ Sent: {account_data.get('sent_count', 0)}
❌ Failed: {account_data.get('failed_count', 0)}
📊 Rounds: {account_data.get('total_rounds', 0)}
📋 Failed Logs: `{account_data.get('failed_channel_id', 'Not set')}`

**Global Stats:**
🔄 Running Accounts: **{len(all_running)}**
✅ Total Sent: {data.get('total_sent', 0)}
❌ Total Failed: {data.get('total_failed', 0)}
📋 Total Accounts: {len(data.get('accounts', {}))}

**⚡ All running accounts send SIMULTANEOUSLY!**
🗄️ Redis: {"Connected ✅" if redis_manager.connected else "Disconnected ❌"}"""
    
    await send_panel(ctx, "STATUS", content, success=running)

@bot.command(name='clear')
async def clear_settings(ctx):
    account_data, error = get_active_account(ctx)
    if not account_data:
        await send_panel(ctx, "CLEAR", error, success=False)
        return
    
    if account_data.get('is_running', False):
        await send_panel(ctx, "CLEAR", "❌ Cannot clear while running! Use `!stop`", success=False)
        return
    
    for key in DEFAULT_ACCOUNT:
        if key != 'token':
            account_data[key] = DEFAULT_ACCOUNT[key]
    
    # Save to Redis
    update_account(data['active_account'], account_data)
    save_data(data)
    
    await send_panel(ctx, "CLEAR", 
        f"🗑️ Settings cleared for `{data['active_account']}`!\n"
        f"🗄️ Data updated in Redis ✅", 
        success=True)

@bot.command(name='commands')
async def show_commands(ctx):
    content = """
**📋 Multi-Account Commands (Redis Mode)**

**Account Management:**
`!addaccount <name> <token>` - Add new account
`!accounts` - List all accounts
`!account <name>` - Select active account
`!removeaccount <name>` - Remove account

**Account Configuration (applies to active account):**
`!addchannel <id1,id2,id3>` - Add multiple channels
`!removechannel <id1,id2,id3>` - Remove multiple channels
`!listchannels` - List channels
`!setmessage <msg>` - Set message (or attach .txt file)
`!setinterval <min>` - Set interval (1-60 min)
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

**⚡ ALL running accounts send SIMULTANEOUSLY!**
**🗄️ All data stored in Redis database**"""
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
    print("🚀 Starting Simultaneous Multi-Account Bot (Redis)...")
    print(f"🗄️ Redis: {'Connected' if redis_manager.connected else 'Disconnected (JSON fallback)'}")
    
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
