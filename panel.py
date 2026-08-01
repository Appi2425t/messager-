#!/usr/bin/env python3
# =============================================================
# DISCORD BOT - WEB CONTROL PANEL
# =============================================================
# - Manage multiple accounts from a web dashboard
# - View status, channels, message, delay
# - Start/Stop accounts with one click
# - View errors and statistics
# - Clean panel-style UI
# =============================================================

from flask import Flask, render_template_string, request, jsonify, redirect, url_for
import os
import json
import redis
import datetime

# =============================================================
# HTML TEMPLATE (Full Panel UI)
# =============================================================

HTML_TEMPLATE = '''
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>SendNow - Bot Control Panel</title>
    <style>
        /* ============================================================ */
        /* GLOBAL STYLES */
        /* ============================================================ */
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: #0d1117;
            color: #c9d1d9;
            min-height: 100vh;
            padding: 20px;
        }
        
        ::-webkit-scrollbar {
            width: 8px;
        }
        ::-webkit-scrollbar-track {
            background: #161b22;
        }
        ::-webkit-scrollbar-thumb {
            background: #30363d;
            border-radius: 10px;
        }
        ::-webkit-scrollbar-thumb:hover {
            background: #5865f2;
        }
        
        .container {
            max-width: 1400px;
            margin: 0 auto;
        }
        
        /* ============================================================ */
        /* HEADER */
        /* ============================================================ */
        .header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 20px 30px;
            background: #161b22;
            border-radius: 15px;
            margin-bottom: 30px;
            border: 1px solid #30363d;
        }
        
        .header-left {
            display: flex;
            align-items: center;
            gap: 15px;
        }
        
        .header-logo {
            font-size: 28px;
            font-weight: 700;
            background: linear-gradient(135deg, #5865f2, #7289da);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }
        
        .header-status {
            display: flex;
            align-items: center;
            gap: 8px;
            font-size: 14px;
            color: #8b949e;
        }
        
        .status-dot {
            width: 10px;
            height: 10px;
            border-radius: 50%;
            display: inline-block;
        }
        
        .status-dot.online {
            background: #3fb950;
            animation: pulse 2s infinite;
        }
        
        .status-dot.offline {
            background: #f85149;
        }
        
        @keyframes pulse {
            0%, 100% { opacity: 1; }
            50% { opacity: 0.5; }
        }
        
        .header-right {
            display: flex;
            align-items: center;
            gap: 20px;
            font-size: 14px;
            color: #8b949e;
        }
        
        .header-right .badge {
            background: #5865f2;
            color: white;
            padding: 4px 12px;
            border-radius: 20px;
            font-size: 12px;
            font-weight: 600;
        }
        
        /* ============================================================ */
        /* STATS CARDS */
        /* ============================================================ */
        .stats-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 15px;
            margin-bottom: 30px;
        }
        
        .stat-card {
            background: #161b22;
            border: 1px solid #30363d;
            border-radius: 12px;
            padding: 20px;
            text-align: center;
        }
        
        .stat-card .number {
            font-size: 32px;
            font-weight: 700;
            color: #f0f6fc;
        }
        
        .stat-card .label {
            font-size: 13px;
            color: #8b949e;
            margin-top: 5px;
        }
        
        .stat-card .icon {
            font-size: 24px;
            margin-bottom: 5px;
        }
        
        .stat-card.green .number { color: #3fb950; }
        .stat-card.blue .number { color: #58a6ff; }
        .stat-card.orange .number { color: #d29922; }
        .stat-card.red .number { color: #f85149; }
        .stat-card.purple .number { color: #bc8cff; }
        
        /* ============================================================ */
        /* ACCOUNT CARDS */
        /* ============================================================ */
        .account-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(350px, 1fr));
            gap: 20px;
            margin-bottom: 30px;
        }
        
        .account-card {
            background: #161b22;
            border: 1px solid #30363d;
            border-radius: 15px;
            padding: 25px;
            transition: all 0.3s ease;
        }
        
        .account-card:hover {
            border-color: #5865f2;
            transform: translateY(-2px);
            box-shadow: 0 8px 30px rgba(88, 101, 242, 0.15);
        }
        
        .account-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 15px;
            padding-bottom: 15px;
            border-bottom: 1px solid #30363d;
        }
        
        .account-name {
            font-size: 18px;
            font-weight: 600;
            color: #f0f6fc;
        }
        
        .account-status {
            display: flex;
            align-items: center;
            gap: 6px;
            font-size: 13px;
            padding: 4px 12px;
            border-radius: 20px;
            background: #21262d;
        }
        
        .account-status .dot {
            width: 8px;
            height: 8px;
            border-radius: 50%;
            display: inline-block;
        }
        
        .account-status .dot.running { background: #3fb950; }
        .account-status .dot.stopped { background: #f85149; }
        .account-status .dot.error { background: #d29922; }
        
        .account-details {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 10px;
            font-size: 14px;
        }
        
        .account-details .detail {
            display: flex;
            flex-direction: column;
        }
        
        .account-details .detail .label {
            font-size: 11px;
            color: #8b949e;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }
        
        .account-details .detail .value {
            color: #f0f6fc;
            font-weight: 500;
            word-break: break-all;
        }
        
        .account-details .detail .value.token {
            font-size: 12px;
            color: #8b949e;
            font-family: monospace;
        }
        
        .account-actions {
            display: flex;
            gap: 10px;
            margin-top: 15px;
            padding-top: 15px;
            border-top: 1px solid #30363d;
        }
        
        /* ============================================================ */
        /* BUTTONS */
        /* ============================================================ */
        .btn {
            padding: 8px 20px;
            border: none;
            border-radius: 8px;
            font-size: 13px;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.2s ease;
            flex: 1;
            text-align: center;
        }
        
        .btn:hover {
            transform: scale(1.02);
        }
        
        .btn-start {
            background: #238636;
            color: white;
        }
        .btn-start:hover {
            background: #2ea043;
        }
        
        .btn-stop {
            background: #da3633;
            color: white;
        }
        .btn-stop:hover {
            background: #f85149;
        }
        
        .btn-edit {
            background: #1f6feb;
            color: white;
        }
        .btn-edit:hover {
            background: #388bfd;
        }
        
        .btn-danger {
            background: #da3633;
            color: white;
        }
        .btn-danger:hover {
            background: #f85149;
        }
        
        .btn-primary {
            background: #5865f2;
            color: white;
        }
        .btn-primary:hover {
            background: #7289da;
        }
        
        .btn-secondary {
            background: #21262d;
            color: #c9d1d9;
        }
        .btn-secondary:hover {
            background: #30363d;
        }
        
        .btn-success {
            background: #238636;
            color: white;
        }
        .btn-success:hover {
            background: #2ea043;
        }
        
        .btn-sm {
            padding: 6px 14px;
            font-size: 12px;
        }
        
        /* ============================================================ */
        /* FORM */
        /* ============================================================ */
        .form-container {
            background: #161b22;
            border: 1px solid #30363d;
            border-radius: 15px;
            padding: 30px;
            margin-bottom: 30px;
        }
        
        .form-title {
            font-size: 20px;
            font-weight: 600;
            margin-bottom: 20px;
            color: #f0f6fc;
        }
        
        .form-group {
            margin-bottom: 18px;
        }
        
        .form-group label {
            display: block;
            font-size: 14px;
            font-weight: 600;
            color: #c9d1d9;
            margin-bottom: 6px;
        }
        
        .form-group .hint {
            font-size: 12px;
            color: #8b949e;
            margin-top: 4px;
        }
        
        .form-group input,
        .form-group textarea,
        .form-group select {
            width: 100%;
            padding: 10px 14px;
            background: #0d1117;
            border: 1px solid #30363d;
            border-radius: 8px;
            color: #f0f6fc;
            font-size: 14px;
            transition: border-color 0.2s;
        }
        
        .form-group input:focus,
        .form-group textarea:focus {
            outline: none;
            border-color: #5865f2;
        }
        
        .form-group textarea {
            min-height: 80px;
            resize: vertical;
            font-family: inherit;
        }
        
        .form-row {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 20px;
        }
        
        .form-actions {
            display: flex;
            gap: 15px;
            margin-top: 10px;
        }
        
        /* ============================================================ */
        /* ERRORS / LOGS */
        /* ============================================================ */
        .log-container {
            background: #0d1117;
            border-radius: 10px;
            padding: 15px;
            max-height: 200px;
            overflow-y: auto;
            font-family: monospace;
            font-size: 13px;
        }
        
        .log-entry {
            padding: 4px 0;
            border-bottom: 1px solid #161b22;
            color: #8b949e;
        }
        
        .log-entry .time {
            color: #5865f2;
        }
        
        .log-entry .error {
            color: #f85149;
        }
        
        .log-entry .success {
            color: #3fb950;
        }
        
        /* ============================================================ */
        /* RESPONSIVE */
        /* ============================================================ */
        @media (max-width: 768px) {
            .header {
                flex-direction: column;
                align-items: flex-start;
                gap: 10px;
            }
            
            .form-row {
                grid-template-columns: 1fr;
            }
            
            .account-grid {
                grid-template-columns: 1fr;
            }
            
            .account-details {
                grid-template-columns: 1fr;
            }
            
            .stats-grid {
                grid-template-columns: 1fr 1fr;
            }
        }
        
        @media (max-width: 480px) {
            .stats-grid {
                grid-template-columns: 1fr;
            }
            
            .account-actions {
                flex-wrap: wrap;
            }
            
            .account-actions .btn {
                flex: 1 1 45%;
            }
        }
        
        /* ============================================================ */
        /* TOAST / ALERT */
        /* ============================================================ */
        .toast {
            position: fixed;
            bottom: 30px;
            right: 30px;
            background: #161b22;
            border: 1px solid #30363d;
            padding: 15px 25px;
            border-radius: 12px;
            color: #f0f6fc;
            font-size: 14px;
            max-width: 400px;
            z-index: 1000;
            animation: slideUp 0.3s ease;
            box-shadow: 0 8px 30px rgba(0,0,0,0.5);
        }
        
        .toast.success { border-color: #3fb950; }
        .toast.error { border-color: #f85149; }
        .toast.info { border-color: #58a6ff; }
        
        @keyframes slideUp {
            from { opacity: 0; transform: translateY(20px); }
            to { opacity: 1; transform: translateY(0); }
        }
        
        .hidden { display: none; }
        
        /* ============================================================ */
        /* FOOTER */
        /* ============================================================ */
        .footer {
            text-align: center;
            padding: 20px 0;
            color: #8b949e;
            font-size: 13px;
            border-top: 1px solid #30363d;
            margin-top: 30px;
        }
        
        .footer span {
            color: #5865f2;
        }
    </style>
</head>
<body>
    <div class="container">
        <!-- ========================================================== -->
        <!-- HEADER -->
        <!-- ========================================================== -->
        <div class="header">
            <div class="header-left">
                <div class="header-logo">🚀 SendNow</div>
                <div class="header-status">
                    <span class="status-dot online"></span>
                    <span>Connected</span>
                </div>
                <span class="badge">v2.0</span>
            </div>
            <div class="header-right">
                <span id="currentTime">Loading...</span>
                <span>|</span>
                <span>developed by <span style="color:#5865f2;">@yathishyt</span></span>
            </div>
        </div>
        
        <!-- ========================================================== -->
        <!-- STATS CARDS -->
        <!-- ========================================================== -->
        <div class="stats-grid">
            <div class="stat-card blue">
                <div class="icon">📋</div>
                <div class="number" id="totalAccounts">{{ stats.total_accounts }}</div>
                <div class="label">Total Accounts</div>
            </div>
            <div class="stat-card green">
                <div class="icon">🟢</div>
                <div class="number" id="runningAccounts">{{ stats.running_accounts }}</div>
                <div class="label">Running</div>
            </div>
            <div class="stat-card red">
                <div class="icon">🔴</div>
                <div class="number" id="stoppedAccounts">{{ stats.stopped_accounts }}</div>
                <div class="label">Stopped</div>
            </div>
            <div class="stat-card orange">
                <div class="icon">📨</div>
                <div class="number" id="totalSent">{{ stats.total_sent }}</div>
                <div class="label">Messages Sent</div>
            </div>
            <div class="stat-card purple">
                <div class="icon">📊</div>
                <div class="number" id="totalChannels">{{ stats.total_channels }}</div>
                <div class="label">Total Channels</div>
            </div>
        </div>
        
        <!-- ========================================================== -->
        <!-- ADD ACCOUNT FORM -->
        <!-- ========================================================== -->
        <div class="form-container">
            <div class="form-title">➕ Add New Account</div>
            <form method="POST" action="/add">
                <div class="form-row">
                    <div class="form-group">
                        <label>Account Token *</label>
                        <input type="text" name="token" placeholder="Enter Discord token (mfa. or OTA...)" required>
                        <div class="hint">Get from Chrome: F12 → Console → localStorage.getItem('token')</div>
                    </div>
                    <div class="form-group">
                        <label>Channel IDs (separate with commas) *</label>
                        <input type="text" name="channels" placeholder="123456789,987654321,456789123" required>
                        <div class="hint">Separate multiple channels with commas</div>
                    </div>
                </div>
                <div class="form-group">
                    <label>Channel Message *</label>
                    <textarea name="message" placeholder="Enter your message here..." required></textarea>
                </div>
                <div class="form-row">
                    <div class="form-group">
                        <label>Message Delay (minutes)</label>
                        <input type="number" name="delay" value="1" min="1" max="60">
                        <div class="hint">How often to send messages (1-60 minutes)</div>
                    </div>
                    <div class="form-group">
                        <label>Account Name</label>
                        <input type="text" name="name" placeholder="e.g., main, alt, bot1" value="account_{{ loop.index }}">
                        <div class="hint">Optional – a name to identify this account</div>
                    </div>
                </div>
                <div class="form-actions">
                    <button type="submit" class="btn btn-primary">➕ Add Account</button>
                    <button type="reset" class="btn btn-secondary">↺ Clear</button>
                </div>
            </form>
        </div>
        
        <!-- ========================================================== -->
        <!-- ACCOUNT CARDS -->
        <!-- ========================================================== -->
        <h2 style="margin-bottom: 15px; font-size: 20px;">📋 Your Accounts</h2>
        
        {% if accounts %}
        <div class="account-grid">
            {% for name, acc in accounts.items() %}
            <div class="account-card">
                <div class="account-header">
                    <span class="account-name">{{ name }}</span>
                    <span class="account-status">
                        <span class="dot {{ 'running' if acc.is_running else 'stopped' }}"></span>
                        {{ '🟢 Running' if acc.is_running else '🔴 Stopped' }}
                    </span>
                </div>
                <div class="account-details">
                    <div class="detail">
                        <span class="label">Channels</span>
                        <span class="value">{{ acc.channels|length }}</span>
                    </div>
                    <div class="detail">
                        <span class="label">Delay</span>
                        <span class="value">{{ acc.schedule_interval }} min</span>
                    </div>
                    <div class="detail">
                        <span class="label">Sent</span>
                        <span class="value">{{ acc.sent_count or 0 }}</span>
                    </div>
                    <div class="detail">
                        <span class="label">Failed</span>
                        <span class="value">{{ acc.failed_count or 0 }}</span>
                    </div>
                    <div class="detail" style="grid-column: span 2;">
                        <span class="label">Token</span>
                        <span class="value token">{{ acc.token[:20] if acc.token else 'Not set' }}...</span>
                    </div>
                </div>
                <div class="account-actions">
                    <form method="POST" action="/start/{{ name }}" style="flex:1;">
                        <button type="submit" class="btn btn-start btn-sm">▶ Start</button>
                    </form>
                    <form method="POST" action="/stop/{{ name }}" style="flex:1;">
                        <button type="submit" class="btn btn-stop btn-sm">⏹ Stop</button>
                    </form>
                    <form method="POST" action="/edit/{{ name }}" style="flex:1;">
                        <button type="submit" class="btn btn-edit btn-sm">✏️ Edit</button>
                    </form>
                    <form method="POST" action="/delete/{{ name }}" style="flex:1;" onsubmit="return confirm('Delete account {{ name }}?')">
                        <button type="submit" class="btn btn-danger btn-sm">🗑 Delete</button>
                    </form>
                </div>
            </div>
            {% endfor %}
        </div>
        {% else %}
        <div style="background: #161b22; border: 1px solid #30363d; border-radius: 15px; padding: 40px; text-align: center;">
            <div style="font-size: 48px; margin-bottom: 15px;">📭</div>
            <h3 style="color: #8b949e; margin-bottom: 10px;">No Accounts Found</h3>
            <p style="color: #8b949e; font-size: 14px;">Add your first account using the form above!</p>
        </div>
        {% endif %}
        
        <!-- ========================================================== -->
        <!-- LOGS / ERRORS -->
        <!-- ========================================================== -->
        <div style="margin-top: 30px;">
            <h2 style="margin-bottom: 15px; font-size: 20px;">📊 Recent Activity</h2>
            <div class="log-container" id="logContainer">
                <div class="log-entry">📌 System ready – waiting for activity...</div>
            </div>
        </div>
        
        <!-- ========================================================== -->
        <!-- FOOTER -->
        <!-- ========================================================== -->
        <div class="footer">
            developed by <span>@yathishyt</span> ⚡ | Discord Bot Control Panel
        </div>
    </div>
    
    <!-- ============================================================ -->
    <!-- JAVASCRIPT -->
    <!-- ============================================================ -->
    <script>
        // Update time
        function updateTime() {
            const now = new Date();
            document.getElementById('currentTime').textContent = now.toLocaleString();
        }
        updateTime();
        setInterval(updateTime, 1000);
        
        // Auto-refresh stats every 10 seconds
        function refreshStats() {
            fetch('/api/stats')
                .then(res => res.json())
                .then(data => {
                    document.getElementById('totalAccounts').textContent = data.total_accounts || 0;
                    document.getElementById('runningAccounts').textContent = data.running_accounts || 0;
                    document.getElementById('stoppedAccounts').textContent = data.stopped_accounts || 0;
                    document.getElementById('totalSent').textContent = data.total_sent || 0;
                    document.getElementById('totalChannels').textContent = data.total_channels || 0;
                })
                .catch(() => {});
        }
        setInterval(refreshStats, 10000);
        
        // Auto-refresh accounts every 30 seconds
        function refreshAccounts() {
            fetch('/api/accounts')
                .then(res => res.json())
                .then(data => {
                    // Reload page if accounts changed
                    if (data.accounts) {
                        // Simple reload to keep sync
                        // location.reload();
                    }
                })
                .catch(() => {});
        }
        setInterval(refreshAccounts, 30000);
        
        // Toast notification for form submissions
        const params = new URLSearchParams(window.location.search);
        const msg = params.get('message');
        const status = params.get('status');
        if (msg) {
            const toast = document.createElement('div');
            toast.className = 'toast ' + (status || 'info');
            toast.textContent = msg;
            document.body.appendChild(toast);
            setTimeout(() => toast.remove(), 5000);
        }
        
        // Add log entry
        function addLog(message, type = 'info') {
            const container = document.getElementById('logContainer');
            const entry = document.createElement('div');
            entry.className = 'log-entry';
            const time = new Date().toLocaleTimeString();
            const icon = type === 'error' ? '❌' : type === 'success' ? '✅' : '📌';
            entry.innerHTML = `<span class="time">${time}</span> ${icon} ${message}`;
            if (type === 'error') entry.querySelector('.log-entry .time').style.color = '#f85149';
            container.prepend(entry);
            if (container.children.length > 50) {
                container.removeChild(container.lastChild);
            }
        }
        
        // Initial log
        addLog('Panel loaded successfully');
    </script>
</body>
</html>
'''

# =============================================================
# FLASK APP
# =============================================================

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'dev-secret-key')

# =============================================================
# REDIS CONNECTION
# =============================================================

def get_redis():
    try:
        redis_url = os.environ.get('REDIS_URL', '')
        if redis_url:
            return redis.from_url(redis_url, decode_responses=True)
        else:
            return redis.Redis(
                host=os.environ.get('REDIS_HOST', 'localhost'),
                port=int(os.environ.get('REDIS_PORT', 6379)),
                password=os.environ.get('REDIS_PASSWORD', ''),
                db=int(os.environ.get('REDIS_DB', 0)),
                decode_responses=True
            )
    except:
        return None

# =============================================================
# DATA HELPERS
# =============================================================

def get_accounts():
    r = get_redis()
    if not r:
        return {}
    
    accounts_raw = r.get('bot:accounts')
    accounts = json.loads(accounts_raw) if accounts_raw else {}
    
    for name in list(accounts.keys()):
        acc_data = r.hgetall(f'bot:account:{name}')
        if acc_data:
            for key, value in acc_data.items():
                try:
                    if key in ['channels', 'failed_logs']:
                        acc_data[key] = json.loads(value) if value else []
                    elif key in ['sent_count', 'failed_count', 'total_rounds', 'schedule_interval', 'message_delay']:
                        acc_data[key] = int(value) if value else 0
                    elif key == 'is_running':
                        acc_data[key] = value == 'True'
                except:
                    pass
            accounts[name] = acc_data
    
    return accounts

def get_stats():
    accounts = get_accounts()
    r = get_redis()
    
    total_sent = int(r.get('bot:total_sent') or 0) if r else 0
    total_failed = int(r.get('bot:total_failed') or 0) if r else 0
    running = sum(1 for acc in accounts.values() if acc.get('is_running', False))
    stopped = len(accounts) - running
    total_channels = sum(len(acc.get('channels', [])) for acc in accounts.values())
    
    return {
        'total_accounts': len(accounts),
        'running_accounts': running,
        'stopped_accounts': stopped,
        'total_sent': total_sent,
        'total_failed': total_failed,
        'total_channels': total_channels
    }

def save_account(name, data):
    r = get_redis()
    if not r:
        return False
    
    accounts_raw = r.get('bot:accounts')
    accounts = json.loads(accounts_raw) if accounts_raw else {}
    accounts[name] = name
    r.set('bot:accounts', json.dumps(accounts))
    
    for key, value in data.items():
        if value is not None:
            if isinstance(value, (dict, list)):
                r.hset(f'bot:account:{name}', key, json.dumps(value))
            elif isinstance(value, bool):
                r.hset(f'bot:account:{name}', key, str(value))
            else:
                r.hset(f'bot:account:{name}', key, str(value))
    
    return True

def delete_account_data(name):
    r = get_redis()
    if not r:
        return False
    
    r.delete(f'bot:account:{name}')
    accounts_raw = r.get('bot:accounts')
    accounts = json.loads(accounts_raw) if accounts_raw else {}
    if name in accounts:
        del accounts[name]
        r.set('bot:accounts', json.dumps(accounts))
    return True

# =============================================================
# ROUTES
# =============================================================

@app.route('/')
def index():
    accounts = get_accounts()
    stats = get_stats()
    return render_template_string(HTML_TEMPLATE, accounts=accounts, stats=stats)

@app.route('/add', methods=['POST'])
def add_account():
    name = request.form.get('name', '').strip()
    token = request.form.get('token', '').strip()
    channels_raw = request.form.get('channels', '').strip()
    message = request.form.get('message', '').strip()
    delay = int(request.form.get('delay', 1))
    
    if not token or not channels_raw or not message:
        return redirect('/?status=error&message=Please fill all required fields')
    
    if not name:
        name = f'account_{len(get_accounts()) + 1}'
    
    channels = [c.strip() for c in channels_raw.split(',') if c.strip()]
    
    account_data = {
        'token': token,
        'channels': channels,
        'message': message,
        'schedule_interval': delay,
        'is_running': False,
        'sent_count': 0,
        'failed_count': 0,
        'total_rounds': 0,
        'message_delay': 30,
        'failed_logs': []
    }
    
    save_account(name, account_data)
    return redirect('/?status=success&message=Account added successfully!')

@app.route('/start/<name>', methods=['POST'])
def start_account(name):
    accounts = get_accounts()
    if name in accounts:
        accounts[name]['is_running'] = True
        save_account(name, accounts[name])
    return redirect('/?status=success&message=Account started!')

@app.route('/stop/<name>', methods=['POST'])
def stop_account(name):
    accounts = get_accounts()
    if name in accounts:
        accounts[name]['is_running'] = False
        save_account(name, accounts[name])
    return redirect('/?status=success&message=Account stopped!')

@app.route('/edit/<name>', methods=['POST'])
def edit_account(name):
    return redirect(f'/?status=info&message=Edit mode coming soon!')

@app.route('/delete/<name>', methods=['POST'])
def delete_account(name):
    delete_account_data(name)
    return redirect('/?status=success&message=Account deleted!')

@app.route('/api/stats')
def api_stats():
    return jsonify(get_stats())

@app.route('/api/accounts')
def api_accounts():
    return jsonify({'accounts': get_accounts()})

@app.route('/api/logs')
def api_logs():
    accounts = get_accounts()
    logs = []
    for name, acc in accounts.items():
        for log in acc.get('failed_logs', [])[-5:]:
            logs.append({
                'account': name,
                'time': log.get('timestamp', ''),
                'channel': log.get('channel_id', ''),
                'reason': log.get('reason', '')
            })
    return jsonify({'logs': logs[-20:]})

# =============================================================
# MAIN
# =============================================================

if __name__ == '__main__':
    port = int(os.environ.get('PANEL_PORT', 5000))
    print(f"🚀 Starting Web Panel on port {port}")
    print(f"🌐 Open: http://localhost:{port}")
    app.run(host='0.0.0.0', port=port, debug=False)
