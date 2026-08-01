#!/usr/bin/env python3
# =============================================================
# DISCORD BOT - F-SOCIETY CONTROL PANEL
# =============================================================
# - Accepts ANY token format (User or Bot, any format)
# - Advanced Discord panel with buttons & modals
# - Add Account via TWO modals
# - Remove Account via modal with confirmation
# - Redis storage
# =============================================================

import discord
from discord.ext import commands
from discord.ui import Button, View, Modal, TextInput
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
        except:
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
        except:
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
        except:
            return False
    
    def hgetall(self, name: str):
        if not self.connected:
            return {}
        try:
            return self.client.hgetall(name)
        except:
            return {}
    
    def delete(self, key: str):
        if not self.connected:
            return False
        try:
            self.client.delete(key)
            return True
        except:
            return False

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

bot = commands.Bot(command_prefix='!', intents=intents)

redis_manager.connect()
load_data()

sending_tasks = {}
rate_limited = {}
rate_limit_until = {}

# =============================================================
# MODAL 1: BASIC INFO
# =============================================================

class AddAccountModal1(Modal, title='Step 1'):
    """First modal for adding account - Basic Info."""
    
    account_name = TextInput(
        label='⚡ Account Name',
        placeholder='Enter a name (e.g., main, alt, bot1)',
        required=True,
        max_length=50,
        style=discord.TextStyle.short
    )
    
    token = TextInput(
        label='🔑 Discord Token',
        placeholder='Paste ANY Discord token (any format)',
        required=True,
        max_length=500,
        style=discord.TextStyle.paragraph
    )
    
    channel_ids = TextInput(
        label='📋 Channel IDs',
        placeholder='Enter channel IDs separated by commas',
        required=True,
        max_length=500,
        style=discord.TextStyle.paragraph
    )
    
    async def on_submit(self, interaction: discord.Interaction):
        modal2 = AddAccountModal2(
            account_name=self.account_name.value,
            token=self.token.value,
            channels=self.channel_ids.value
        )
        await interaction.response.send_modal(modal2)

# =============================================================
# MODAL 2: MESSAGE + SETTINGS
# =============================================================

class AddAccountModal2(Modal, title='Step 2'):
    """Second modal for adding account - Message + Settings."""
    
    def __init__(self, account_name: str, token: str, channels: str):
        super().__init__()
        self.account_name_value = account_name
        self.token_value = token
        self.channels_value = channels
    
    message = TextInput(
        label='📝 Message to Send',
        placeholder='Enter the message you want to send',
        required=True,
        max_length=4000,
        style=discord.TextStyle.paragraph
    )
    
    delay = TextInput(
        label='⏳ Delay (seconds)',
        placeholder='Default: 30 seconds',
        required=False,
        max_length=10,
        default='30'
    )
    
    interval = TextInput(
        label='⏱️ Interval (min)',
        placeholder='Default: 1 minute',
        required=False,
        max_length=10,
        default='1'
    )
    
    async def on_submit(self, interaction: discord.Interaction):
        global bot_data
        
        name = self.account_name_value.strip()
        token = self.token_value.strip()
        channels_raw = self.channels_value.strip()
        message = self.message.value.strip()
        
        try:
            delay = int(self.delay.value.strip()) if self.delay.value.strip() else 30
            if delay < 5:
                delay = 5
            if delay > 300:
                delay = 300
        except:
            delay = 30
        
        try:
            interval = int(self.interval.value.strip()) if self.interval.value.strip() else 1
            if interval < 1:
                interval = 1
            if interval > 60:
                interval = 60
        except:
            interval = 1
        
        if not name or not token or not channels_raw or not message:
            embed = discord.Embed(
                title="❌ Error",
                description="Please fill in all required fields!",
                color=discord.Color.red()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        
        if name in bot_data['accounts']:
            embed = discord.Embed(
                title="❌ Error",
                description=f"Account `{name}` already exists!",
                color=discord.Color.red()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        
        # Clean token - just remove quotes and whitespace, accept ANY format
        token = token.strip()
        if token.startswith('"') and token.endswith('"'):
            token = token[1:-1]
        if token.startswith("'") and token.endswith("'"):
            token = token[1:-1]
        token = token.replace('"', '').replace("'", '').replace('`', '')
        token = token.replace(' ', '')
        
        # NO LENGTH CHECK - accept any token
        
        # Parse channels
        channels = []
        for cid in channels_raw.split(','):
            cid = cid.strip()
            if cid.isdigit():
                channels.append(cid)
        
        if not channels:
            embed = discord.Embed(
                title="❌ Error",
                description="Invalid channel IDs! Please enter valid numeric IDs.",
                color=discord.Color.red()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        
        # Test token (accepts ANY format)
        await interaction.response.defer(ephemeral=True)
        
        valid, result = await test_token(token)
        if not valid:
            embed = discord.Embed(
                title="❌ Invalid Token",
                description=f"Token test failed: {result}\n\n📌 The token will still be saved, but it may not work.\n\n**Token Preview:** `{token[:30]}...`",
                color=discord.Color.orange()
            )
            await interaction.followup.send(embed=embed, ephemeral=True)
            # Still save the account even if token test fails (user can fix later)
        
        # Create account
        account_data = DEFAULT_ACCOUNT.copy()
        account_data['token'] = token
        account_data['channels'] = channels
        account_data['message'] = message
        account_data['schedule_interval'] = interval
        account_data['message_delay'] = delay
        
        bot_data['accounts'][name] = account_data
        bot_data['active_account'] = name
        update_account(name, account_data)
        save_data()
        
        # Detect token type for display (just for info)
        token_type = "Detected"
        if token.startswith('mfa.'):
            token_type = "User (mfa.)"
        elif token.startswith('token.'):
            token_type = "User (token.)"
        elif token.startswith(('OTA', 'MTM')):
            token_type = "Bot"
        elif '.' in token and len(token) > 30:
            token_type = "User (JWT-like)"
        
        embed = discord.Embed(
            title="✅ Account Added!",
            description=f"**Account:** `{name}`\n"
                        f"**Token Type:** `{token_type}`\n"
                        f"**Token:** `{token[:30]}...`\n"
                        f"**Channels:** {len(channels)}\n"
                        f"**Delay:** {delay}s\n"
                        f"**Interval:** {interval} min(s)\n\n"
                        f"📌 Use `!panel` to see all accounts.",
            color=discord.Color.green()
        )
        embed.set_footer(text="developed by @yathishyt ⚡ | F-Society")
        await interaction.followup.send(embed=embed, ephemeral=True)

# =============================================================
# CONFIRM DELETE MODAL
# =============================================================

class ConfirmDeleteModal(Modal, title='Delete'):
    """Modal for confirming account deletion."""
    
    confirm = TextInput(
        label='Type DELETE to confirm',
        placeholder='Type DELETE here to confirm',
        required=True,
        max_length=10,
        style=discord.TextStyle.short
    )
    
    def __init__(self, account_name: str):
        super().__init__()
        self.account_name = account_name
    
    async def on_submit(self, interaction: discord.Interaction):
        if self.confirm.value.strip().upper() == 'DELETE':
            delete_account_data(self.account_name)
            
            embed = discord.Embed(
                title="🗑️ Account Deleted",
                description=f"Account `{self.account_name}` has been removed.",
                color=discord.Color.red()
            )
            embed.set_footer(text="developed by @yathishyt ⚡ | F-Society")
            await interaction.response.send_message(embed=embed, ephemeral=True)
        else:
            embed = discord.Embed(
                title="❌ Cancelled",
                description="Deletion cancelled. You must type `DELETE` to confirm.",
                color=discord.Color.red()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)

# =============================================================
# BUTTON VIEWS
# =============================================================

class AccountControlView(View):
    def __init__(self, account_name: str):
        super().__init__(timeout=None)
        self.account_name = account_name
        account_data = bot_data['accounts'].get(account_name, {})
        is_running = account_data.get('is_running', False)
        
        if is_running:
            self.add_item(Button(label="⏹ Stop", style=discord.ButtonStyle.danger, custom_id=f"stop_{account_name}"))
        else:
            self.add_item(Button(label="▶ Start", style=discord.ButtonStyle.success, custom_id=f"start_{account_name}"))
        
        self.add_item(Button(label="✏️ Edit", style=discord.ButtonStyle.primary, custom_id=f"edit_{account_name}"))
        self.add_item(Button(label="🗑 Delete", style=discord.ButtonStyle.danger, custom_id=f"delete_{account_name}"))
        self.add_item(Button(label="📊 Stats", style=discord.ButtonStyle.secondary, custom_id=f"stats_{account_name}"))
        self.add_item(Button(label="🔙 Back", style=discord.ButtonStyle.secondary, custom_id="back_to_panel"))

class MainPanelView(View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(Button(label="🔄 Refresh", style=discord.ButtonStyle.primary, custom_id="refresh_panel"))
        self.add_item(Button(label="➕ Add", style=discord.ButtonStyle.success, custom_id="add_account_modal"))

class EditAccountView(View):
    def __init__(self, account_name: str):
        super().__init__(timeout=None)
        self.account_name = account_name
        self.add_item(Button(label="📝 Message", style=discord.ButtonStyle.primary, custom_id=f"edit_msg_{account_name}"))
        self.add_item(Button(label="📋 Channels", style=discord.ButtonStyle.primary, custom_id=f"edit_channels_{account_name}"))
        self.add_item(Button(label="⏱ Interval", style=discord.ButtonStyle.primary, custom_id=f"edit_interval_{account_name}"))
        self.add_item(Button(label="⏳ Delay", style=discord.ButtonStyle.primary, custom_id=f"edit_delay_{account_name}"))
        self.add_item(Button(label="🔙 Back", style=discord.ButtonStyle.secondary, custom_id=f"back_account_{account_name}"))

# =============================================================
# PANEL EMBED BUILDER
# =============================================================

def create_panel_embed():
    """Create the main F-Society panel embed."""
    embed = discord.Embed(
        title="🔻 F-Society Control Panel",
        description="Welcome to the F-Society Control Panel. Manage your Discord automation accounts here.",
        color=discord.Color.from_rgb(0, 255, 200),
        timestamp=datetime.datetime.now()
    )
    
    total_accounts = len(bot_data.get('accounts', {}))
    running = sum(1 for acc in bot_data.get('accounts', {}).values() if acc.get('is_running', False))
    total_sent = bot_data.get('total_sent', 0)
    total_failed = bot_data.get('total_failed', 0)
    total_channels = sum(len(acc.get('channels', [])) for acc in bot_data.get('accounts', {}).values())
    
    embed.add_field(
        name="📜 License Info",
        value=f"**Status:** ███████ Active\n**Expires:** ∞",
        inline=True
    )
    
    embed.add_field(
        name="📊 Account Insights",
        value=f"**Slots:** {total_accounts}/10\n**Active:** {running}\n**Inactive:** {total_accounts - running}",
        inline=True
    )
    
    embed.add_field(
        name="📈 Statistics",
        value=f"**Total Channels:** {total_channels}\n**Messages Sent:** {total_sent} ✅\n**Failed:** {total_failed} ❌",
        inline=False
    )
    
    if bot_data.get('accounts'):
        accounts_list = ""
        for name, acc in bot_data.get('accounts', {}).items():
            status_icon = "🟢" if acc.get('is_running', False) else "🔴"
            status_text = "Online" if acc.get('is_running', False) else "Offline"
            channels = len(acc.get('channels', []))
            sent = acc.get('sent_count', 0)
            failed = acc.get('failed_count', 0)
            delay = acc.get('message_delay', DEFAULT_DELAY)
            token = acc.get('token', '')
            token_preview = token[:20] + '...' if token else 'Not set'
            accounts_list += f"{status_icon} **{name}** — {status_text}\n"
            accounts_list += f"   ↳ Channels: {channels} | Delay: {delay}s | Token: `{token_preview}`\n"
        
        embed.add_field(name="📋 Active Accounts", value=accounts_list, inline=False)
    else:
        embed.add_field(
            name="📋 Active Accounts",
            value="*No accounts found. Click `➕ Add` to get started.*",
            inline=False
        )
    
    embed.set_footer(text="developed by @yathishyt ⚡ | F-Society")
    return embed

def create_account_embed(account_name: str):
    """Create account details embed."""
    account_data = bot_data['accounts'].get(account_name, {})
    is_running = account_data.get('is_running', False)
    status_icon = "🟢" if is_running else "🔴"
    status_text = "Online" if is_running else "Offline"
    last_active = f"{account_data.get('total_rounds', 0)} rounds" if is_running else "Stopped"
    channels = len(account_data.get('channels', []))
    delay = account_data.get('message_delay', DEFAULT_DELAY)
    sent = account_data.get('sent_count', 0)
    failed = account_data.get('failed_count', 0)
    rounds = account_data.get('total_rounds', 0)
    token = account_data.get('token', '')
    token_preview = token[:30] + '...' if token and len(token) > 30 else token or 'Not set'
    
    embed = discord.Embed(
        title=f"🔻 {account_name}'s Acc Overview",
        color=discord.Color.green() if is_running else discord.Color.red(),
        timestamp=datetime.datetime.now()
    )
    embed.add_field(
        name="📊 Account Status",
        value=f"Status: {status_icon} {status_text} | Last Active: {last_active}",
        inline=False
    )
    embed.add_field(
        name="📡 Monitoring Details",
        value=f"**Total Channels:** {channels}\n**Channel Delay:** {delay}s\n**DM Mode:** Disabled",
        inline=False
    )
    embed.add_field(
        name="📈 Statistics",
        value=f"**Sent:** {sent} ✅\n**Failed:** {failed} ❌\n**Total Rounds:** {rounds}",
        inline=False
    )
    embed.add_field(
        name="🔑 Token Preview",
        value=f"`{token_preview}`",
        inline=False
    )
    embed.set_footer(text=f"developed by @yathishyt ⚡ | F-Society | {account_name}")
    return embed

def create_stats_embed(account_name: str):
    """Create stats embed."""
    account_data = bot_data['accounts'].get(account_name, {})
    embed = discord.Embed(
        title=f"📊 Stats for {account_name}",
        color=discord.Color.from_rgb(0, 255, 200),
        timestamp=datetime.datetime.now()
    )
    embed.add_field(name="✅ Sent", value=f"`{account_data.get('sent_count', 0)}`", inline=True)
    embed.add_field(name="❌ Failed", value=f"`{account_data.get('failed_count', 0)}`", inline=True)
    embed.add_field(name="🔄 Rounds", value=f"`{account_data.get('total_rounds', 0)}`", inline=True)
    embed.add_field(name="📋 Channels", value=f"`{len(account_data.get('channels', []))}`", inline=True)
    embed.add_field(name="⏱️ Interval", value=f"`{account_data.get('schedule_interval', 1)} min`", inline=True)
    embed.add_field(name="⏳ Delay", value=f"`{account_data.get('message_delay', DEFAULT_DELAY)}s`", inline=True)
    
    logs = account_data.get('failed_logs', [])[-5:]
    if logs:
        log_text = ""
        for log in logs:
            log_text += f"• `{log.get('timestamp', '')[:16]}` | {log.get('reason', 'Unknown')}\n"
        embed.add_field(name="❌ Recent Errors", value=log_text, inline=False)
    else:
        embed.add_field(name="❌ Recent Errors", value="*No errors logged*", inline=False)
    
    embed.set_footer(text="developed by @yathishyt ⚡ | F-Society")
    return embed

# =============================================================
# TOKEN TESTING - ACCEPTS ANY FORMAT
# =============================================================

async def test_token(token: str):
    """Test if a token is valid (accepts ANY format)."""
    token = token.strip()
    if token.startswith('"') and token.endswith('"'):
        token = token[1:-1]
    if token.startswith("'") and token.endswith("'"):
        token = token[1:-1]
    token = token.replace('"', '').replace("'", '').replace('`', '')
    token = token.replace(' ', '')
    
    if len(token) < 5:
        return False, "Token too short (minimum 5 characters)"
    
    url = "https://discord.com/api/v9/users/@me"
    
    # Try as User Token (no prefix)
    headers = {'Authorization': token, 'Content-Type': 'application/json'}
    
    try:
        async with aiohttp.ClientSession() as session:
            # First try: use token as-is
            async with session.get(url, headers=headers, timeout=10) as response:
                if response.status == 200:
                    data = await response.json()
                    return True, f"✅ {data.get('username')}#{data.get('discriminator', '0')} (Valid)"
                elif response.status == 401:
                    # Second try: try as Bot Token (add "Bot " prefix)
                    headers2 = {'Authorization': f'Bot {token}', 'Content-Type': 'application/json'}
                    async with session.get(url, headers=headers2, timeout=10) as response2:
                        if response2.status == 200:
                            data = await response2.json()
                            return True, f"✅ {data.get('username')} (Bot Token)"
                        else:
                            return False, "❌ Token not recognized. It may still work for sending messages."
                else:
                    return False, f"❌ HTTP {response.status}"
    except Exception as e:
        return False, f"⚠️ Error: {str(e)}"

# =============================================================
# SEND MESSAGE FUNCTIONS
# =============================================================

async def send_single_message(channel_id: str, message: str, token: str, account_name: str) -> tuple:
    global bot_data
    
    # Clean token
    token = token.strip()
    if token.startswith('"') and token.endswith('"'):
        token = token[1:-1]
    if token.startswith("'") and token.endswith("'"):
        token = token[1:-1]
    token = token.replace('"', '').replace("'", '').replace('`', '')
    token = token.replace(' ', '')
    
    if len(token) < 5:
        return False, "Invalid token (too short)"
    
    if account_name not in rate_limited:
        rate_limited[account_name] = False
        rate_limit_until[account_name] = 0
    
    if rate_limited.get(account_name, False) and time.time() < rate_limit_until.get(account_name, 0):
        await asyncio.sleep(rate_limit_until[account_name] - time.time() + 1)
        rate_limited[account_name] = False
    
    url = f"https://discord.com/api/v9/channels/{channel_id}/messages"
    
    # Try as User Token (no prefix)
    headers = {'Authorization': token, 'Content-Type': 'application/json'}
    payload = {'content': message, 'tts': False}
    
    try:
        async with aiohttp.ClientSession() as session:
            # Try as User Token first
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
                    # Try as Bot Token (add "Bot " prefix)
                    headers2 = {'Authorization': f'Bot {token}', 'Content-Type': 'application/json'}
                    async with session.post(url, headers=headers2, json=payload, timeout=30) as response2:
                        if response2.status in [200, 201]:
                            return True, None
                        elif response2.status == 429:
                            data = await response2.json()
                            retry_after = data.get('retry_after', 30)
                            rate_limited[account_name] = True
                            rate_limit_until[account_name] = time.time() + retry_after + 2
                            await asyncio.sleep(retry_after + 2)
                            return await send_single_message(channel_id, message, token, account_name)
                        else:
                            await log_failed_message(account_name, channel_id, "Invalid token - HTTP 401")
                            if account_name in bot_data['accounts']:
                                bot_data['accounts'][account_name]['is_running'] = False
                                update_account(account_name, bot_data['accounts'][account_name])
                                save_data()
                            return False, "INVALID TOKEN"
                else:
                    await log_failed_message(account_name, channel_id, f"HTTP {response.status}")
                    return False, f"HTTP {response.status}"
    except Exception as e:
        await log_failed_message(account_name, channel_id, str(e))
        return False, str(e)

# =============================================================
# REST OF BOT FUNCTIONS
# =============================================================

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
    tasks = [send_round_for_account(name) for name in running_accounts]
    return await asyncio.gather(*tasks)

async def log_failed_message(account_name: str, channel_id: str, reason: str):
    global bot_data
    if account_name not in bot_data['accounts']:
        return
    account_data = bot_data['accounts'][account_name]
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
# BOT COMMANDS
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
    print("\n🔻 F-Society Control Panel Ready!")
    print("📌 Use !panel to open the control panel")
    print("📌 Accepts ANY token format")

# =============================================================
# PANEL COMMANDS
# =============================================================

@bot.command(name='panel')
async def show_panel(ctx):
    """Show the F-Society control panel."""
    embed = create_panel_embed()
    view = MainPanelView()
    await ctx.send(embed=embed, view=view)

@bot.command(name='account')
async def show_account(ctx, account_name: str):
    """Show account details."""
    if account_name not in bot_data['accounts']:
        await ctx.send(f"❌ Account `{account_name}` not found!")
        return
    embed = create_account_embed(account_name)
    view = AccountControlView(account_name)
    await ctx.send(embed=embed, view=view)

# =============================================================
# BUTTON INTERACTIONS
# =============================================================

@bot.event
async def on_interaction(interaction: discord.Interaction):
    if not interaction.data or not interaction.data.get('custom_id'):
        return
    
    custom_id = interaction.data['custom_id']
    
    if custom_id == 'refresh_panel':
        embed = create_panel_embed()
        view = MainPanelView()
        await interaction.response.edit_message(embed=embed, view=view)
        return
    
    if custom_id == 'add_account_modal':
        modal = AddAccountModal1()
        await interaction.response.send_modal(modal)
        return
    
    if custom_id == 'back_to_panel':
        embed = create_panel_embed()
        view = MainPanelView()
        await interaction.response.edit_message(embed=embed, view=view)
        return
    
    if custom_id.startswith('start_'):
        account_name = custom_id.replace('start_', '')
        if account_name in bot_data['accounts']:
            account_data = bot_data['accounts'][account_name]
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
            account_data = bot_data['accounts'][account_name]
            embed = discord.Embed(
                title=f"✏️ Editing {account_name}",
                color=discord.Color.from_rgb(0, 255, 200),
                timestamp=datetime.datetime.now()
            )
            embed.add_field(
                name="📝 Current Settings",
                value=f"**Message:** {account_data.get('message', 'Not set')[:100]}...\n"
                      f"**Channels:** {len(account_data.get('channels', []))}\n"
                      f"**Interval:** {account_data.get('schedule_interval', 1)} min\n"
                      f"**Delay:** {account_data.get('message_delay', DEFAULT_DELAY)}s",
                inline=False
            )
            embed.set_footer(text="developed by @yathishyt ⚡ | F-Society")
            view = EditAccountView(account_name)
            await interaction.response.edit_message(embed=embed, view=view)
        return
    
    if custom_id.startswith('delete_'):
        account_name = custom_id.replace('delete_', '')
        if account_name in bot_data['accounts']:
            modal = ConfirmDeleteModal(account_name)
            await interaction.response.send_modal(modal)
        return
    
    if custom_id.startswith('stats_'):
        account_name = custom_id.replace('stats_', '')
        if account_name in bot_data['accounts']:
            embed = create_stats_embed(account_name)
            await interaction.response.edit_message(embed=embed)
        return
    
    if custom_id.startswith('edit_msg_'):
        account_name = custom_id.replace('edit_msg_', '')
        embed = discord.Embed(
            title="📝 Change Message",
            description=f"**For `{account_name}`:**\nUse `!setmessage <new message>`\n\n**Or attach a `.txt` file with:**\n`!setmessage`",
            color=discord.Color.blue()
        )
        embed.set_footer(text="developed by @yathishyt ⚡ | F-Society")
        await interaction.response.edit_message(embed=embed)
        return
    
    if custom_id.startswith('edit_channels_'):
        account_name = custom_id.replace('edit_channels_', '')
        embed = discord.Embed(
            title="📋 Add Channels",
            description=f"**For `{account_name}`:**\nUse `!addchannel <id1,id2,id3>`\n\n**Example:**\n`!addchannel 123456789,987654321`",
            color=discord.Color.blue()
        )
        embed.set_footer(text="developed by @yathishyt ⚡ | F-Society")
        await interaction.response.edit_message(embed=embed)
        return
    
    if custom_id.startswith('edit_interval_'):
        account_name = custom_id.replace('edit_interval_', '')
        embed = discord.Embed(
            title="⏱ Change Interval",
            description=f"**For `{account_name}`:**\nUse `!setinterval <minutes>`\n\n**Example:**\n`!setinterval 5` (sends every 5 minutes)",
            color=discord.Color.blue()
        )
        embed.set_footer(text="developed by @yathishyt ⚡ | F-Society")
        await interaction.response.edit_message(embed=embed)
        return
    
    if custom_id.startswith('edit_delay_'):
        account_name = custom_id.replace('edit_delay_', '')
        embed = discord.Embed(
            title="⏳ Change Delay",
            description=f"**For `{account_name}`:**\nUse `!setdelay <seconds>`\n\n**Example:**\n`!setdelay 30` (30 seconds between messages)",
            color=discord.Color.blue()
        )
        embed.set_footer(text="developed by @yathishyt ⚡ | F-Society")
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
# COMMANDS (SECONDARY METHOD)
# =============================================================

@bot.command(name='addaccount')
async def add_account_cmd(ctx, account_name: str, *, token: str):
    """Secondary: Add account via command (accepts ANY token)."""
    if account_name in bot_data['accounts']:
        await ctx.send(f"❌ Account `{account_name}` already exists!")
        return
    
    token = token.strip()
    if token.startswith('"') and token.endswith('"'):
        token = token[1:-1]
    if token.startswith("'") and token.endswith("'"):
        token = token[1:-1]
    token = token.replace('"', '').replace("'", '').replace('`', '')
    token = token.replace(' ', '')
    
    account_data = DEFAULT_ACCOUNT.copy()
    account_data['token'] = token
    bot_data['accounts'][account_name] = account_data
    update_account(account_name, account_data)
    save_data()
    
    embed = discord.Embed(
        title="✅ Account Added!",
        description=f"**Name:** `{account_name}`\n**Token:** `{token[:30]}...`\n\nUse `!panel` to view all accounts.",
        color=discord.Color.green()
    )
    embed.set_footer(text="developed by @yathishyt ⚡ | F-Society")
    await ctx.send(embed=embed)

@bot.command(name='removeaccount')
async def remove_account_cmd(ctx, account_name: str):
    """Secondary: Remove account via command."""
    if account_name not in bot_data['accounts']:
        await ctx.send(f"❌ Account `{account_name}` not found!")
        return
    delete_account_data(account_name)
    embed = discord.Embed(
        title="🗑 Account Removed",
        description=f"Account `{account_name}` has been removed.",
        color=discord.Color.red()
    )
    embed.set_footer(text="developed by @yathishyt ⚡ | F-Society")
    await ctx.send(embed=embed)

@bot.command(name='start')
async def start_account_cmd(ctx, account_name: str):
    """Secondary: Start account via command."""
    if account_name not in bot_data['accounts']:
        await ctx.send(f"❌ Account `{account_name}` not found!")
        return
    account_data = bot_data['accounts'][account_name]
    if not account_data.get('token'):
        await ctx.send(f"❌ Account `{account_name}` has no token!")
        return
    if not account_data.get('channels'):
        await ctx.send(f"❌ Account `{account_name}` has no channels!")
        return
    if not account_data.get('message'):
        await ctx.send(f"❌ Account `{account_name}` has no message!")
        return
    account_data['is_running'] = True
    update_account(account_name, account_data)
    save_data()
    embed = discord.Embed(
        title="🚀 Account Started!",
        description=f"**Account:** `{account_name}`",
        color=discord.Color.green()
    )
    embed.set_footer(text="developed by @yathishyt ⚡ | F-Society")
    await ctx.send(embed=embed)

@bot.command(name='stop')
async def stop_account_cmd(ctx, account_name: str):
    """Secondary: Stop account via command."""
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
        color=discord.Color.red()
    )
    embed.set_footer(text="developed by @yathishyt ⚡ | F-Society")
    await ctx.send(embed=embed)

@bot.command(name='setmessage')
async def set_message_cmd(ctx, *, message: str = None):
    """Secondary: Set message via command."""
    account_name = bot_data.get('active_account')
    if not account_name:
        await ctx.send("❌ No active account! Use `!account <name>` first.")
        return
    if account_name not in bot_data['accounts']:
        await ctx.send(f"❌ Account `{account_name}` not found!")
        return
    if message is None:
        if ctx.message.attachments:
            for attachment in ctx.message.attachments:
                if attachment.filename.endswith('.txt'):
                    content = await attachment.read()
                    message = content.decode('utf-8')
                    break
        if not message:
            await ctx.send("❌ Please provide a message or attach a `.txt` file!")
            return
    account_data = bot_data['accounts'][account_name]
    account_data['message'] = message
    update_account(account_name, account_data)
    save_data()
    embed = discord.Embed(
        title="✅ Message Set!",
        description=f"**Account:** `{account_name}`\n**Message:** ```\n{message[:200]}```",
        color=discord.Color.green()
    )
    embed.set_footer(text="developed by @yathishyt ⚡ | F-Society")
    await ctx.send(embed=embed)

@bot.command(name='addchannel')
async def add_channel_cmd(ctx, *, channel_ids: str):
    """Secondary: Add channels via command."""
    account_name = bot_data.get('active_account')
    if not account_name:
        await ctx.send("❌ No active account! Use `!account <name>` first.")
        return
    if account_name not in bot_data['accounts']:
        await ctx.send(f"❌ Account `{account_name}` not found!")
        return
    channel_list = []
    for separator in [',', ';', ' ']:
        if separator in channel_ids:
            channel_list = [c.strip() for c in channel_ids.split(separator) if c.strip()]
            break
    if not channel_list:
        channel_list = [channel_ids.strip()]
    account_data = bot_data['accounts'][account_name]
    added = []
    for cid in channel_list:
        if cid.isdigit() and cid not in account_data.get('channels', []):
            account_data['channels'].append(cid)
            added.append(cid)
    update_account(account_name, account_data)
    save_data()
    embed = discord.Embed(
        title="✅ Channels Added!",
        description=f"**Account:** `{account_name}`\n**Added:** `{', '.join(added)}`\n**Total Channels:** {len(account_data['channels'])}",
        color=discord.Color.green()
    )
    embed.set_footer(text="developed by @yathishyt ⚡ | F-Society")
    await ctx.send(embed=embed)

@bot.command(name='setinterval')
async def set_interval_cmd(ctx, minutes: int):
    """Secondary: Set interval via command."""
    account_name = bot_data.get('active_account')
    if not account_name:
        await ctx.send("❌ No active account! Use `!account <name>` first.")
        return
    if account_name not in bot_data['accounts']:
        await ctx.send(f"❌ Account `{account_name}` not found!")
        return
    if minutes < 1 or minutes > 60:
        await ctx.send("❌ Interval must be 1-60 minutes!")
        return
    account_data = bot_data['accounts'][account_name]
    account_data['schedule_interval'] = minutes
    update_account(account_name, account_data)
    save_data()
    embed = discord.Embed(
        title="✅ Interval Set!",
        description=f"**Account:** `{account_name}`\n**Interval:** Every {minutes} minute(s)",
        color=discord.Color.green()
    )
    embed.set_footer(text="developed by @yathishyt ⚡ | F-Society")
    await ctx.send(embed=embed)

@bot.command(name='setdelay')
async def set_delay_cmd(ctx, seconds: int):
    """Secondary: Set delay via command."""
    account_name = bot_data.get('active_account')
    if not account_name:
        await ctx.send("❌ No active account! Use `!account <name>` first.")
        return
    if account_name not in bot_data['accounts']:
        await ctx.send(f"❌ Account `{account_name}` not found!")
        return
    if seconds < 5 or seconds > 300:
        await ctx.send("❌ Delay must be 5-300 seconds!")
        return
    account_data = bot_data['accounts'][account_name]
    account_data['message_delay'] = seconds
    update_account(account_name, account_data)
    save_data()
    embed = discord.Embed(
        title="✅ Delay Set!",
        description=f"**Account:** `{account_name}`\n**Delay:** {seconds}s between messages",
        color=discord.Color.green()
    )
    embed.set_footer(text="developed by @yathishyt ⚡ | F-Society")
    await ctx.send(embed=embed)

@bot.command(name='commands')
async def show_commands(ctx):
    """Show all commands."""
    embed = discord.Embed(
        title="🔻 F-Society Commands",
        description="**🎯 Primary Method (Recommended):**\n`!panel` - Open the F-Society panel\n\n**⚡ Secondary Method (Commands):**\n`!addaccount <name> <token>` - Add account (ANY token)\n`!removeaccount <name>` - Remove account\n`!start <name>` - Start account\n`!stop <name>` - Stop account\n`!setmessage <msg>` - Set message\n`!addchannel <ids>` - Add channels\n`!setinterval <min>` - Set interval\n`!setdelay <sec>` - Set delay\n\n**ℹ️ Info:**\n`!account <name>` - View account details\n`!commands` - Show this menu",
        color=discord.Color.from_rgb(0, 255, 200),
        timestamp=datetime.datetime.now()
    )
    embed.set_footer(text="developed by @yathishyt ⚡ | F-Society")
    await ctx.send(embed=embed)

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
    print("🔻 Starting F-Society Control Panel...")
    print(f"🗄️ Redis: {'Connected' if redis_manager.connected else 'Disconnected'}")
    print(f"⏳ Default delay: {DEFAULT_DELAY} seconds")
    print("🔑 Accepts ANY token format (User or Bot, any format)")
    
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
