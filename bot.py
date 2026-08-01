#!/usr/bin/env python3
# =============================================================
# DISCORD BOT - DISCORD PANEL CONTROL
# =============================================================
# - Interactive Discord panels with buttons
# - Account management via Discord
# - View status, channels, delay, stats
# - Start/Stop/Edit/Delete accounts with buttons
# - Clean panel-style embeds
# =============================================================

import discord
from discord.ext import commands
from discord.ui import Button, View, Select
import asyncio
import json
import os
import time
import aiohttp
import datetime
import sys
import redis
import random

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
# GLOBAL DATA
# =============================================================

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
        print(f"⚠️ Error loading data: {e}")
        bot_data = {'accounts': {}, 'active_account': None, 'total_sent': 0, 'total_failed': 0}
        return bot_data

def save_data():
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
        print(f"⚠️ Error saving data: {e}")
        return False

def update_account(account_name: str, account_data: dict):
    global bot_data
    
    try:
        if not redis_manager.connected:
            return False
        
        if not account_data:
            return False
        
        if account_name in bot_data['accounts']:
            bot_data['accounts'][account_name] = account_data
        
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
        print(f"⚠️ Error updating account: {e}")
        return False

def delete_account_data(account_name: str):
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
        
        if account_name in bot_data['accounts']:
            del bot_data['accounts'][account_name]
        
        return True
        
    except Exception as e:
        print(f"⚠️ Error deleting account: {e}")
        return False

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
intents.members = True

bot = commands.Bot(command_prefix='!', intents=intents)

# Connect to Redis
redis_manager.connect()

# Load initial data
load_data()

sending_tasks = {}
rate_limited = {}
rate_limit_until = {}

# =============================================================
# BUTTON VIEWS (Discord Panel)
# =============================================================

class AccountControlView(View):
    """View with account control buttons."""
    
    def __init__(self, account_name: str):
        super().__init__(timeout=None)
        self.account_name = account_name
        
        # Get account data
        account_data = bot_data['accounts'].get(account_name, {})
        is_running = account_data.get('is_running', False)
        
        # Start/Stop button
        if is_running:
            self.add_item(Button(
                label="⏹ Stop",
                style=discord.ButtonStyle.danger,
                custom_id=f"stop_{account_name}"
            ))
        else:
            self.add_item(Button(
                label="▶ Start",
                style=discord.ButtonStyle.success,
                custom_id=f"start_{account_name}"
            ))
        
        self.add_item(Button(
            label="✏️ Edit",
            style=discord.ButtonStyle.primary,
            custom_id=f"edit_{account_name}"
        ))
        
        self.add_item(Button(
            label="🗑 Delete",
            style=discord.ButtonStyle.danger,
            custom_id=f"delete_{account_name}"
        ))
        
        self.add_item(Button(
            label="📊 Stats",
            style=discord.ButtonStyle.secondary,
            custom_id=f"stats_{account_name}"
        ))
        
        self.add_item(Button(
            label="🔙 Back",
            style=discord.ButtonStyle.secondary,
            custom_id="back_to_panel"
        ))

class MainPanelView(View):
    """Main panel with account selection."""
    
    def __init__(self):
        super().__init__(timeout=None)
        
        # Refresh button
        self.add_item(Button(
            label="🔄 Refresh",
            style=discord.ButtonStyle.primary,
            custom_id="refresh_panel"
        ))
        
        # Add Account button
        self.add_item(Button(
            label="➕ Add Account",
            style=discord.ButtonStyle.success,
            custom_id="add_account_panel"
        ))

class EditAccountView(View):
    """View for editing account settings."""
    
    def __init__(self, account_name: str):
        super().__init__(timeout=None)
        self.account_name = account_name
        
        self.add_item(Button(
            label="📝 Change Message",
            style=discord.ButtonStyle.primary,
            custom_id=f"edit_msg_{account_name}"
        ))
        
        self.add_item(Button(
            label="📋 Add Channels",
            style=discord.ButtonStyle.primary,
            custom_id=f"edit_channels_{account_name}"
        ))
        
        self.add_item(Button(
            label="⏱ Change Interval",
            style=discord.ButtonStyle.primary,
            custom_id=f"edit_interval_{account_name}"
        ))
        
        self.add_item(Button(
            label="⏳ Change Delay",
            style=discord.ButtonStyle.primary,
            custom_id=f"edit_delay_{account_name}"
        ))
        
        self.add_item(Button(
            label="🔙 Back",
            style=discord.ButtonStyle.secondary,
            custom_id=f"back_account_{account_name}"
        ))

# =============================================================
# PANEL EMBED BUILDER
# =============================================================

def create_panel_embed(account_name: str = None):
    """Create the main panel embed."""
    embed = discord.Embed(
        title="🚀 SendNow - Control Panel",
        color=discord.Color.blue(),
        timestamp=datetime.datetime.now()
    )
    
    # Add stats
    total_accounts = len(bot_data.get('accounts', {}))
    running = sum(1 for acc in bot_data.get('accounts', {}).values() if acc.get('is_running', False))
    total_sent = bot_data.get('total_sent', 0)
    total_failed = bot_data.get('total_failed', 0)
    total_channels = sum(len(acc.get('channels', [])) for acc in bot_data.get('accounts', {}).values())
    
    embed.add_field(
        name="📊 Overview",
        value=f"**Accounts:** {total_accounts} ({running} running)\n"
              f"**Channels:** {total_channels}\n"
              f"**Sent:** {total_sent} ✅ | **Failed:** {total_failed} ❌",
        inline=False
    )
    
    # List accounts with status
    accounts_list = ""
    for name, acc in bot_data.get('accounts', {}).items():
        status = "🟢" if acc.get('is_running', False) else "🔴"
        channels = len(acc.get('channels', []))
        delay = acc.get('message_delay', DEFAULT_DELAY)
        accounts_list += f"{status} **{name}** | {channels} channels | {delay}s delay\n"
    
    if accounts_list:
        embed.add_field(
            name="📋 Accounts",
            value=accounts_list,
            inline=False
        )
    else:
        embed.add_field(
            name="📋 Accounts",
            value="*No accounts added yet.*\nUse `!addaccount` to get started.",
            inline=False
        )
    
    embed.set_footer(text="developed by @yathishyt ⚡ | Click buttons to manage accounts")
    return embed

def create_account_embed(account_name: str):
    """Create an embed for a specific account."""
    account_data = bot_data['accounts'].get(account_name, {})
    
    status = "🟢 Online" if account_data.get('is_running', False) else "🔴 Offline"
    channels = len(account_data.get('channels', []))
    delay = account_data.get('message_delay', DEFAULT_DELAY)
    interval = account_data.get('schedule_interval', 1)
    sent = account_data.get('sent_count', 0)
    failed = account_data.get('failed_count', 0)
    rounds = account_data.get('total_rounds', 0)
    token_preview = account_data.get('token', '')[:20] + '...' if account_data.get('token') else 'Not set'
    
    embed = discord.Embed(
        title=f"📋 {account_name}'s Acc Overview",
        color=discord.Color.green() if account_data.get('is_running', False) else discord.Color.red(),
        timestamp=datetime.datetime.now()
    )
    
    embed.add_field(
        name="📊 Account Status",
        value=f"Status: {status} | Last Active: {rounds} rounds",
        inline=False
    )
    
    embed.add_field(
        name="📡 Monitoring Details",
        value=f"Total Channels: {channels} | Channel Delay: {delay}s | DM Mode: Disabled",
        inline=False
    )
    
    embed.add_field(
        name="📈 Stats",
        value=f"Sent: {sent} ✅ | Failed: {failed} ❌ | Rounds: {rounds}",
        inline=False
    )
    
    embed.add_field(
        name="🔑 Token",
        value=f"`{token_preview}`",
        inline=False
    )
    
    embed.set_footer(text=f"developed by @yathishyt ⚡ | {account_name}")
    return embed

def create_edit_embed(account_name: str):
    """Create an embed for editing account."""
    account_data = bot_data['accounts'].get(account_name, {})
    
    embed = discord.Embed(
        title=f"✏️ Editing {account_name}",
        color=discord.Color.blue(),
        timestamp=datetime.datetime.now()
    )
    
    embed.add_field(
        name="📝 Current Settings",
        value=f"**Message:** {account_data.get('message', 'Not set')[:100]}...\n"
              f"**Channels:** {len(account_data.get('channels', []))}\n"
              f"**Interval:** {account_data.get('schedule_interval', 1)} minutes\n"
              f"**Delay:** {account_data.get('message_delay', DEFAULT_DELAY)}s",
        inline=False
    )
    
    embed.set_footer(text="developed by @yathishyt ⚡ | Click buttons below to edit")
    return embed

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
                    return False, "❌ TOKEN EXPIRED"
                else:
                    return False, f"❌ HTTP {response.status}"
    except Exception as e:
        return False, f"❌ Error: {str(e)}"

# =============================================================
# SEND MESSAGE FUNCTIONS
# =============================================================

async def send_single_message(channel_id: str, message: str, token: str, account_name: str) -> tuple:
    global bot_data
    
    token = clean_token(token)
    if not token:
        return False, "Invalid token"
    
    if account_name not in rate_limited:
        rate_limited[account_name] = False
        rate_limit_until[account_name] = 0
    
    if rate_limited.get(account_name, False) and time.time() < rate_limit_until.get(account_name, 0):
        wait_time = rate_limit_until[account_name] - time.time()
        await asyncio.sleep(wait_time + 1)
        rate_limited[account_name] = False
    
    url = f"https://discord.com/api/v9/channels/{channel_id}/messages"
    headers = {'Authorization': token, 'Content-Type': 'application/json'}
    payload = {'content': message, 'tts': False}
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, json=payload, timeout=30) as response:
                if response.status in [200, 201]:
                    return True, None
                elif response.status == 429:
                    data = await response.json()
                    retry_after = data.get('retry_after', 30)
                    rate_limited[account_name] = True
                    rate_limit_until[account_name] = time.time() + retry_after + 2
                    await asyncio.sleep(retry_after + 2)
                    return await send_single_message(channel_id, message, token, account_name)
                elif response.status == 401:
                    await log_failed_message(account_name, channel_id, "TOKEN EXPIRED")
                    if account_name in bot_data['accounts']:
                        bot_data['accounts'][account_name]['is_running'] = False
                        update_account(account_name, bot_data['accounts'][account_name])
                        save_data()
                    return False, "TOKEN EXPIRED"
                elif response.status == 403:
                    await log_failed_message(account_name, channel_id, "No permission")
                    return False, "No permission"
                else:
                    await log_failed_message(account_name, channel_id, f"HTTP {response.status}")
                    return False, f"HTTP {response.status}"
    except Exception as e:
        await log_failed_message(account_name, channel_id, str(e))
        return False, str(e)

async def send_round_for_account(account_name: str) -> dict:
    global bot_data
    
    if account_name not in bot_data['accounts']:
        return {'sent': 0, 'failed': 0, 'account': account_name}
    
    account_data = bot_data['accounts'][account_name]
    token = account_data.get('token')
    channels = account_data.get('channels', [])
    message = account_data.get('message')
    
    if not token or not channels or not message:
        return {'sent': 0, 'failed': 0, 'account': account_name}
    
    test_valid, _ = await test_token(token)
    if not test_valid:
        account_data['is_running'] = False
        update_account(account_name, account_data)
        save_data()
        return {'sent': 0, 'failed': 0, 'account': account_name, 'error': 'Token expired'}
    
    message_delay = account_data.get('message_delay', DEFAULT_DELAY)
    sent = 0
    failed = 0
    
    for index, channel_id in enumerate(channels, 1):
        success, error = await send_single_message(channel_id, message, token, account_name)
        if success:
            sent += 1
        else:
            failed += 1
        if index < len(channels):
            await asyncio.sleep(message_delay)
    
    account_data['sent_count'] = account_data.get('sent_count', 0) + sent
    account_data['failed_count'] = account_data.get('failed_count', 0) + failed
    account_data['total_rounds'] = account_data.get('total_rounds', 0) + 1
    bot_data['total_sent'] = bot_data.get('total_sent', 0) + sent
    bot_data['total_failed'] = bot_data.get('total_failed', 0) + failed
    
    update_account(account_name, account_data)
    save_data()
    
    return {'sent': sent, 'failed': failed, 'account': account_name}

async def send_round_for_all_accounts():
    global bot_data
    
    accounts = bot_data.get('accounts', {})
    running_accounts = [name for name, acc in accounts.items() if acc.get('is_running', False)]
    
    if not running_accounts:
        return
    
    tasks = []
    for account_name in running_accounts:
        tasks.append(send_round_for_account(account_name))
    
    results = await asyncio.gather(*tasks)
    return results

async def log_failed_message(account_name: str, channel_id: str, reason: str):
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
            description=f"**Channel:** `{channel_id}`\n**Reason:** {reason}\n**Time:** {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            color=discord.Color.red(),
            timestamp=datetime.datetime.now()
        )
        embed.set_footer(text="developed by @yathishyt ⚡")
        await failed_channel.send(embed=embed)
        
    except Exception as e:
        print(f"⚠️ Error logging: {e}")

async def scheduled_send_task():
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
# DISCORD PANEL COMMANDS
# =============================================================

global_send_task = None

@bot.event
async def on_ready():
    global global_send_task
    
    print(f'✅ Bot online: {bot.user.name}')
    print(f'📡 Connected to {len(bot.guilds)} servers')
    print(f'🗄️ Redis: {"Connected" if redis_manager.connected else "Disconnected"}')
    
    if global_send_task is None or global_send_task.done():
        global_send_task = asyncio.create_task(scheduled_send_task())
        print("✅ Global send task started")

# =============================================================
# DISCORD PANEL COMMANDS
# =============================================================

@bot.command(name='panel')
async def show_panel(ctx):
    """Show the main control panel."""
    embed = create_panel_embed()
    view = MainPanelView()
    await ctx.send(embed=embed, view=view)

@bot.command(name='account')
async def show_account(ctx, account_name: str = None):
    """Show details for a specific account."""
    if not account_name:
        await ctx.send("❌ Please specify an account name: `!account <name>`")
        return
    
    if account_name not in bot_data['accounts']:
        await ctx.send(f"❌ Account `{account_name}` not found!")
        return
    
    embed = create_account_embed(account_name)
    view = AccountControlView(account_name)
    await ctx.send(embed=embed, view=view)

@bot.command(name='addaccount')
async def add_account_cmd(ctx, account_name: str = None, *, token: str = None):
    """Add a new account."""
    await ctx.send("📋 **Add Account**\n\nTo add an account, use this format:\n`!addaccount <name> <token>`\n\n**Example:**\n`!addaccount main mfa.xxxxxxxx`")
    
    # If parameters provided, proceed
    if account_name and token:
        if account_name in bot_data['accounts']:
            await ctx.send(f"❌ Account `{account_name}` already exists!")
            return
        
        token = clean_token(token)
        if not token:
            await ctx.send("❌ Invalid token!")
            return
        
        valid, result = await test_token(token)
        if not valid:
            await ctx.send(f"❌ {result}")
            return
        
        account_data = DEFAULT_ACCOUNT.copy()
        account_data['token'] = token
        bot_data['accounts'][account_name] = account_data
        update_account(account_name, account_data)
        save_data()
        
        embed = discord.Embed(
            title="✅ Account Added!",
            description=f"**Name:** `{account_name}`\n{result}\n\nUse `!panel` to view all accounts.",
            color=discord.Color.green(),
            timestamp=datetime.datetime.now()
        )
        embed.set_footer(text="developed by @yathishyt ⚡")
        await ctx.send(embed=embed)

@bot.command(name='removeaccount')
async def remove_account_cmd(ctx, account_name: str):
    """Remove an account."""
    if account_name not in bot_data['accounts']:
        await ctx.send(f"❌ Account `{account_name}` not found!")
        return
    
    delete_account_data(account_name)
    await ctx.send(f"✅ Account `{account_name}` removed!")

@bot.command(name='start')
async def start_account_cmd(ctx, account_name: str = None):
    """Start an account."""
    if not account_name:
        account_name = bot_data.get('active_account')
        if not account_name:
            await ctx.send("❌ Please specify an account: `!start <name>`")
            return
    
    if account_name not in bot_data['accounts']:
        await ctx.send(f"❌ Account `{account_name}` not found!")
        return
    
    account_data = bot_data['accounts'][account_name]
    
    if not account_data.get('token'):
        await ctx.send(f"❌ Account `{account_name}` has no token set!")
        return
    if not account_data.get('channels'):
        await ctx.send(f"❌ Account `{account_name}` has no channels added!")
        return
    if not account_data.get('message'):
        await ctx.send(f"❌ Account `{account_name}` has no message set!")
        return
    
    valid, result = await test_token(account_data.get('token'))
    if not valid:
        await ctx.send(f"❌ Token expired for `{account_name}`!\n{result}")
        return
    
    account_data['is_running'] = True
    account_data['sent_count'] = 0
    account_data['failed_count'] = 0
    account_data['total_rounds'] = 0
    update_account(account_name, account_data)
    save_data()
    
    embed = discord.Embed(
        title="🚀 Account Started!",
        description=f"**Account:** `{account_name}`\n**Channels:** {len(account_data['channels'])}\n**Interval:** Every {account_data['schedule_interval']} minute(s)",
        color=discord.Color.green(),
        timestamp=datetime.datetime.now()
    )
    embed.set_footer(text="developed by @yathishyt ⚡")
    await ctx.send(embed=embed)

@bot.command(name='stop')
async def stop_account_cmd(ctx, account_name: str = None):
    """Stop an account."""
    if not account_name:
        account_name = bot_data.get('active_account')
        if not account_name:
            await ctx.send("❌ Please specify an account: `!stop <name>`")
            return
    
    if account_name not in bot_data['accounts']:
        await ctx.send(f"❌ Account `{account_name}` not found!")
        return
    
    account_data = bot_data['accounts'][account_name]
    account_data['is_running'] = False
    update_account(account_name, account_data)
    save_data()
    
    embed = discord.Embed(
        title="🛑 Account Stopped!",
        description=f"**Account:** `{account_name}`\n**Sent:** {account_data.get('sent_count', 0)}\n**Failed:** {account_data.get('failed_count', 0)}",
        color=discord.Color.red(),
        timestamp=datetime.datetime.now()
    )
    embed.set_footer(text="developed by @yathishyt ⚡")
    await ctx.send(embed=embed)

# =============================================================
# BUTTON INTERACTIONS
# =============================================================

@bot.event
async def on_interaction(interaction: discord.Interaction):
    """Handle button interactions for the panel."""
    
    if not interaction.data or not interaction.data.get('custom_id'):
        return
    
    custom_id = interaction.data['custom_id']
    
    # ===== PANEL CONTROLS =====
    
    if custom_id == 'refresh_panel':
        embed = create_panel_embed()
        await interaction.response.edit_message(embed=embed)
        return
    
    if custom_id == 'add_account_panel':
        embed = discord.Embed(
            title="➕ Add Account",
            description="Use the command:\n`!addaccount <name> <token>`\n\n**Example:**\n`!addaccount main mfa.xxxxxxxx`\n\n**Get token from Chrome:**\nF12 → Console → `localStorage.getItem('token')`",
            color=discord.Color.blue(),
            timestamp=datetime.datetime.now()
        )
        embed.set_footer(text="developed by @yathishyt ⚡")
        await interaction.response.edit_message(embed=embed)
        return
    
    if custom_id == 'back_to_panel':
        embed = create_panel_embed()
        view = MainPanelView()
        await interaction.response.edit_message(embed=embed, view=view)
        return
    
    # ===== ACCOUNT CONTROLS =====
    
    if custom_id.startswith('start_'):
        account_name = custom_id.replace('start_', '')
        if account_name in bot_data['accounts']:
            account_data = bot_data['accounts'][account_name]
            
            valid, result = await test_token(account_data.get('token'))
            if not valid:
                embed = discord.Embed(
                    title="❌ Token Expired!",
                    description=f"Token for `{account_name}` has expired.\nPlease add a new token.",
                    color=discord.Color.red()
                )
                embed.set_footer(text="developed by @yathishyt ⚡")
                await interaction.response.edit_message(embed=embed)
                return
            
            account_data['is_running'] = True
            update_account(account_name, account_data)
            save_data()
            
            embed = create_account_embed(account_name)
            view = AccountControlView(account_name)
            await interaction.response.edit_message(embed=embed, view=view)
        return
    
    if custom_id.startswith('stop_'):
        account_name = custom_id.replace('stop_', '')
        if account_name in bot_data['accounts']:
            account_data = bot_data['accounts'][account_name]
            account_data['is_running'] = False
            update_account(account_name, account_data)
            save_data()
            
            embed = create_account_embed(account_name)
            view = AccountControlView(account_name)
            await interaction.response.edit_message(embed=embed, view=view)
        return
    
    if custom_id.startswith('edit_'):
        account_name = custom_id.replace('edit_', '')
        if account_name in bot_data['accounts']:
            embed = create_edit_embed(account_name)
            view = EditAccountView(account_name)
            await interaction.response.edit_message(embed=embed, view=view)
        return
    
    if custom_id.startswith('delete_'):
        account_name = custom_id.replace('delete_', '')
        if account_name in bot_data['accounts']:
            delete_account_data(account_name)
            embed = create_panel_embed()
            view = MainPanelView()
            await interaction.response.edit_message(
                content=f"🗑️ Account `{account_name}` deleted!",
                embed=embed,
                view=view
            )
        return
    
    if custom_id.startswith('stats_'):
        account_name = custom_id.replace('stats_', '')
        if account_name in bot_data['accounts']:
            account_data = bot_data['accounts'][account_name]
            embed = discord.Embed(
                title=f"📊 Stats for {account_name}",
                color=discord.Color.blue(),
                timestamp=datetime.datetime.now()
            )
            embed.add_field(name="Sent", value=f"`{account_data.get('sent_count', 0)}`", inline=True)
            embed.add_field(name="Failed", value=f"`{account_data.get('failed_count', 0)}`", inline=True)
            embed.add_field(name="Rounds", value=f"`{account_data.get('total_rounds', 0)}`", inline=True)
            embed.add_field(name="Channels", value=f"`{len(account_data.get('channels', []))}`", inline=True)
            embed.add_field(name="Interval", value=f"`{account_data.get('schedule_interval', 1)} min`", inline=True)
            embed.add_field(name="Delay", value=f"`{account_data.get('message_delay', DEFAULT_DELAY)}s`", inline=True)
            
            # Failed logs
            logs = account_data.get('failed_logs', [])[-5:]
            if logs:
                log_text = ""
                for log in logs:
                    log_text += f"• `{log.get('timestamp', '')[:16]}` | {log.get('reason', 'Unknown')}\n"
                embed.add_field(name="Recent Errors", value=log_text, inline=False)
            else:
                embed.add_field(name="Recent Errors", value="*No errors*", inline=False)
            
            embed.set_footer(text="developed by @yathishyt ⚡")
            await interaction.response.edit_message(embed=embed)
        return
    
    # ===== EDIT ACCOUNT BUTTONS =====
    
    if custom_id.startswith('edit_msg_'):
        account_name = custom_id.replace('edit_msg_', '')
        embed = discord.Embed(
            title="📝 Change Message",
            description=f"To change the message for `{account_name}`, use:\n`!setmessage <new message>`\n\n**Or attach a `.txt` file with:**\n`!setmessage`",
            color=discord.Color.blue()
        )
        embed.set_footer(text="developed by @yathishyt ⚡")
        await interaction.response.edit_message(embed=embed)
        return
    
    if custom_id.startswith('edit_channels_'):
        account_name = custom_id.replace('edit_channels_', '')
        embed = discord.Embed(
            title="📋 Add Channels",
            description=f"To add channels to `{account_name}`, use:\n`!addchannel <id1,id2,id3>`\n\n**Example:**\n`!addchannel 123456789,987654321`",
            color=discord.Color.blue()
        )
        embed.set_footer(text="developed by @yathishyt ⚡")
        await interaction.response.edit_message(embed=embed)
        return
    
    if custom_id.startswith('edit_interval_'):
        account_name = custom_id.replace('edit_interval_', '')
        embed = discord.Embed(
            title="⏱ Change Interval",
            description=f"To change the interval for `{account_name}`, use:\n`!setinterval <minutes>`\n\n**Example:**\n`!setinterval 5` (sends every 5 minutes)",
            color=discord.Color.blue()
        )
        embed.set_footer(text="developed by @yathishyt ⚡")
        await interaction.response.edit_message(embed=embed)
        return
    
    if custom_id.startswith('edit_delay_'):
        account_name = custom_id.replace('edit_delay_', '')
        embed = discord.Embed(
            title="⏳ Change Delay",
            description=f"To change the delay between messages for `{account_name}`, use:\n`!setdelay <seconds>`\n\n**Example:**\n`!setdelay 30` (30 seconds between messages)",
            color=discord.Color.blue()
        )
        embed.set_footer(text="developed by @yathishyt ⚡")
        await interaction.response.edit_message(embed=embed)
        return
    
    if custom_id.startswith('back_account_'):
        account_name = custom_id.replace('back_account_', '')
        if account_name in bot_data['accounts']:
            embed = create_account_embed(account_name)
            view = AccountControlView(account_name)
            await interaction.response.edit_message(embed=embed, view=view)
        return

# =============================================================
# ERROR HANDLING
# =============================================================

@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.MissingRequiredArgument):
        await ctx.send("❌ Missing argument! Use `!commands` for help.")
    elif isinstance(error, commands.CommandNotFound):
        pass
    else:
        await ctx.send(f"❌ Error: {str(error)}")

# =============================================================
# MAIN
# =============================================================

def main():
    print("🚀 Starting Discord Panel Bot...")
    print(f"🗄️ Redis: {'Connected' if redis_manager.connected else 'Disconnected'}")
    print(f"⏳ Default delay: {DEFAULT_DELAY} seconds")
    
    if not BOT_TOKEN:
        print("❌ No BOT_TOKEN found!")
        return
    
    try:
        bot.run(BOT_TOKEN)
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print("\n🛑 Bot stopped")
        sys.exit(0)
    except Exception as e:
        print(f"❌ Fatal: {e}")
        sys.exit(1)
