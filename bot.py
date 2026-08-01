#!/usr/bin/env python3
# =============================================================
# DISCORD BOT - SIMULTANEOUS MULTI-ACCOUNT MESSENGER
# =============================================================
# - ALL accounts send messages at the SAME TIME
# - Each account has independent channels/message/schedule
# - True parallel sending using asyncio.gather()
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

try:
    from flask import Flask, request, jsonify
    import threading
    FLASK_AVAILABLE = True
except ImportError:
    FLASK_AVAILABLE = False

# =============================================================
# WEB SERVER (Keeps Railway Active)
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
DATA_FILE = 'multi_account_data.json'

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

DEFAULT_SETTINGS = {
    'accounts': {},
    'active_account': None,
    'total_sent': 0,
    'total_failed': 0,
    'simultaneous_mode': True
}

# =============================================================
# DATA MANAGEMENT
# =============================================================

def load_data():
    try:
        if os.path.exists(DATA_FILE):
            with open(DATA_FILE, 'r') as f:
                data = json.load(f)
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
    embed.set_footer(text="developed by @yathishyt ⚡ | Simultaneous Mode")
    return embed

async def send_panel(ctx, title: str, content: str, success=None, color=None):
    embed = create_panel(title, content, color, success)
    try:
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

data = load_data()
sending_tasks = {}
rate_limited = {}
rate_limit_until = {}

if 'accounts' not in data:
    data['accounts'] = {}
if 'active_account' not in data:
    data['active_account'] = None
if 'total_sent' not in data:
    data['total_sent'] = 0
if 'total_failed' not in data:
    data['total_failed'] = 0
if 'simultaneous_mode' not in data:
    data['simultaneous_mode'] = True
save_data(data)

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
        save_data(data)
        
        embed = discord.Embed(
            title=f"❌ [{account_name}] MESSAGE FAILED",
            description=f"**Account:** `{account_name}`\n**Channel:** `{channel_id}`\n**Reason:** {reason}\n**Time:** {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            color=discord.Color.red(),
            timestamp=datetime.datetime.now()
        )
        embed.set_footer(text="developed by @yathishyt ⚡")
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
    save_data(data)
    
    await send_panel(ctx, "ADD ACCOUNT", f"✅ **Account Added!**\n📛 Name: `{account_name}`\n{result}\n\nUse `!account {account_name}` to configure it.", success=True)

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

**Commands now apply to this account!**
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
    
    del data['accounts'][account_name]
    if data.get('active_account') == account_name:
        data['active_account'] = None
    
    save_data(data)
    await send_panel(ctx, "REMOVE ACCOUNT", f"✅ Account `{account_name}` removed!", success=True)

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
    """Add multiple channel IDs (comma-separated)."""
    account_data, error = get_active_account(ctx)
    if not account_data:
        await send_panel(ctx, "ADD CHANNEL", error, success=False)
        return
    
    # Split by comma, semicolon, or space
    channel_list = []
    for separator in [',', ';', ' ']:
        if separator in channel_ids:
            channel_list = [c.strip() for c in channel_ids.split(separator) if c.strip()]
            break
    
    if not channel_list:
        channel_list = [channel_ids.strip()]
    
    # Validate and add
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
    
    save_data(data)
    
    # Build response
    response_parts = []
    if added:
        response_parts.append(f"✅ Added: `{', '.join(added)}`")
    if skipped:
        response_parts.append(f"⚠️ Skipped (already exist): `{', '.join(skipped)}`")
    if invalid:
        response_parts.append(f"❌ Invalid: `{', '.join(invalid)}`")
    
    response_parts.append(f"📊 Total channels: **{len(account_data['channels'])}**")
    
    await send_panel(ctx, "ADD CHANNEL", "\n".join(response_parts), success=True if added else False)

@bot.command(name='removechannel')
async def remove_channel(ctx, *, channel_ids: str):
    """Remove multiple channel IDs (comma-separated)."""
    account_data, error = get_active_account(ctx)
    if not account_data:
        await send_panel(ctx, "REMOVE CHANNEL", error, success=False)
        return
    
    # Split by comma, semicolon, or space
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
    
    save_data(data)
    
    response_parts = []
    if removed:
        response_parts.append(f"✅ Removed: `{', '.join(removed)}`")
    if not_found:
        response_parts.append(f"⚠️ Not found: `{', '.join(not_found)}`")
    
    response_parts.append(f"📊 Total channels: **{len(account_data['channels'])}**")
    
    await send_panel(ctx, "REMOVE CHANNEL", "\n".join(response_parts), success=True if removed else False)

@bot.command(name='listchannels')
async def list_channels(ctx):
    """List all channels for active account."""
    account_data, error = get_active_account(ctx)
    if not account_data:
        await send_panel(ctx, "LIST CHANNELS", error, success=False)
        return
    
    channels = account_data.get('channels', [])
    if not channels:
        await send_panel(ctx, "LIST CHANNELS", f"📭 No channels added for `{data['active_account']}`.", success=False)
        return
    
    # Try to get channel names
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
    """Set the message to send for active account.\nCan also attach a .txt file."""
    account_data, error = get_active_account(ctx)
    if not account_data:
        await send_panel(ctx, "SET MESSAGE", error, success=False)
        return
    
    # If no message provided, try to read from attached text file
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
            await send_panel(ctx, "SET MESSAGE", "❌ Please provide a message or attach a `.txt` file!\n\n**Example:** `!setmessage Hello World!`\n**OR:** `!setmessage` (with .txt file attached)", success=False)
            return
    
    # Check length
    if len(message) > 4000:
        await send_panel(ctx, "SET MESSAGE", f"❌ Message too long! Max 4000 characters. You have **{len(message)}** characters.", success=False)
        return
    
    account_data['message'] = message
    save_data(data)
    
    # Preview
    preview = message[:150] + "..." if len(message) > 150 else message
    await send_panel(ctx, "SET MESSAGE", f"✅ Message set for `{data['active_account']}`!\n\n```\n{preview}\n```\n\n📊 **Length:** {len(message)} characters", success=True)

@bot.command(name='setinterval')
async def set_interval(ctx, minutes: int):
    """Set the interval between sends (1-60 minutes)."""
    account_data, error = get_active_account(ctx)
    if not account_data:
        await send_panel(ctx, "SET INTERVAL", error, success=False)
        return
    
    if minutes < 1 or minutes > 60:
        await send_panel(ctx, "SET INTERVAL", "❌ Must be 1-60 minutes!", success=False)
        return
    
    account_data['schedule_interval'] = minutes
    save_data(data)
    await send_panel(ctx, "SET INTERVAL", f"✅ Interval set for `{data['active_account']}`: Every **{minutes} minute(s)**", success=True)

@bot.command(name='failed')
async def set_failed_channel(ctx, channel_id: str):
    """Set failed logs channel for active account."""
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
    save_data(data)
    await send_panel(ctx, "SET FAILED CHANNEL", f"✅ Failed logs for `{data['active_account']}` will go to `{channel_id}`", success=True)

@bot.command(name='failedlogs')
async def show_failed_logs(ctx):
    """Show failed logs for active account."""
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
    """Start sending for active account."""
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
    save_data(data)
    
    running = [name for name, acc in data['accounts'].items() if acc.get('is_running', False)]
    
    await send_panel(ctx, "START", f"🚀 **Started `{account_name}`!**\n📊 Channels: {len(account_data['channels'])}\n⏱️ Interval: Every {account_data['schedule_interval']} minute(s)\n\n🔄 **All running accounts ({len(running)}) will send simultaneously!**", success=True)

@bot.command(name='stop')
async def stop_account(ctx):
    """Stop sending for active account."""
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
    save_data(data)
    
    await send_panel(ctx, "STOP", f"🛑 **Stopped `{account_name}`!**\n✅ Sent: {account_data.get('sent_count', 0)}\n❌ Failed: {account_data.get('failed_count', 0)}", success=True)

@bot.command(name='sendnow')
async def send_now(ctx):
    """Send one round for ALL running accounts simultaneously."""
    global data
    
    running = [name for name, acc in data['accounts'].items() if acc.get('is_running', False)]
    
    if not running:
        await send_panel(ctx, "SEND NOW", "❌ No accounts are running!\nStart at least one account with `!start`", success=False)
        return
    
    await send_panel(ctx, "SEND NOW", f"📨 Sending one round for **{len(running)} accounts** simultaneously...", color=discord.Color.blue())
    
    results = await send_round_for_all_accounts()
    
    total_sent = sum(r.get('sent', 0) for r in results) if results else 0
    total_failed = sum(r.get('failed', 0) for r in results) if results else 0
    
    await send_panel(ctx, "SEND NOW", f"✅ Done! **{len(running)} accounts** sent simultaneously!\n\n✅ Total Sent: **{total_sent}**\n❌ Total Failed: **{total_failed}**", success=True)

@bot.command(name='startall')
async def start_all_accounts(ctx):
    """Start ALL accounts at once."""
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
    
    save_data(data)
    
    running = [name for name, acc in data['accounts'].items() if acc.get('is_running', False)]
    
    await send_panel(ctx, "START ALL", f"🚀 **Started {started} accounts!**\n📊 Total Running: **{len(running)}**\n🔄 All accounts will send simultaneously!", success=True)

@bot.command(name='stopall')
async def stop_all_accounts(ctx):
    """Stop ALL accounts."""
    global data
    
    accounts = data.get('accounts', {})
    stopped = 0
    
    for name, acc in accounts.items():
        if acc.get('is_running', False):
            acc['is_running'] = False
            stopped += 1
    
    save_data(data)
    
    await send_panel(ctx, "STOP ALL", f"🛑 **Stopped {stopped} accounts!**", success=True)

@bot.command(name='status')
async def show_status(ctx):
    """Show status for active account."""
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

**⚡ All running accounts send SIMULTANEOUSLY!**"""
    
    await send_panel(ctx, "STATUS", content, success=running)

@bot.command(name='clear')
async def clear_settings(ctx):
    """Clear settings for active account."""
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
    save_data(data)
    await send_panel(ctx, "CLEAR", f"🗑️ Settings cleared for `{data['active_account']}`!", success=True)

@bot.command(name='commands')
async def show_commands(ctx):
    """Show all available commands."""
    content = """
**📋 Multi-Account Commands (Simultaneous Mode)**

**Account Management:**
`!addaccount <name> <token>` - Add new account
`!accounts` - List all accounts
`!account <name>` - Select active account
`!removeaccount <name>` - Remove account

**Account Configuration (applies to active account):**
`!addchannel <id1,id2,id3>` - Add multiple channels (comma-separated)
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
`!sendnow` - Send one round for all running accounts
`!status` - Show status
`!clear` - Clear settings

**Other:**
`!commands` - Show this menu

**⚡ ALL running accounts send SIMULTANEOUSLY!**

**Example Workflow:**
1. `!addaccount main mfa.xxxxx`
2. `!account main`
3. `!addchannel 123456789,987654321,456789123`
4. `!setmessage Hello!` (or attach .txt file)
5. `!setinterval 5`
6. `!start`

**Long Messages:** Use `!setmessage` and attach a `.txt` file!
"""
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
    print("🚀 Starting Simultaneous Multi-Account Bot...")
    print(f"📁 Data file: {DATA_FILE}")
    
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
