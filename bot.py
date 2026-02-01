#!/usr/bin/env python3
"""
🌪️ TEMPEST AI - Complete Telegram Bot
Organization: Tempest Creed
Owner ID: 6108185460
"""

import os
import json
import sqlite3
import asyncio
import logging
import aiohttp
import random
from datetime import datetime
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes
)

# ======================
# CONFIGURATION
# ======================
OWNER_ID = 6108185460
BOT_TOKEN = "7869314780:AAFFU5jMv-WK9sCJnAJ4X0oRtog632B9sUg"
WEATHER_API_KEY = "b5622fffde3852de7528ec5d71a9850a"
LOG_CHANNEL = -1003662720845
WELCOME_PIC = "https://files.catbox.moe/s4k1rn.jpg"
RAPIDAPI_KEY = "92823ef8acmsh086c6b1d4344b79p128756jsn14144695e111"

# API Endpoints
OPENAI_CHAT_URL = "https://open-ai32.p.rapidapi.com/conversationgpt35"
OLLAMA_GEN_URL = "https://ollama-local-ai-text-generation-api-qwen-powered.p.rapidapi.com/generate"
FLUX_IMAGE_URL = "https://ai-text-to-image-generator-flux-free-api.p.rapidapi.com/aaaaaaaaaaaaaaaaaiimagegenerator/quick.php"

# Initialize logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ======================
# DATABASE SETUP
# ======================
def init_database():
    conn = sqlite3.connect('tempest.db', check_same_thread=False)
    cursor = conn.cursor()
    
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        username TEXT,
        first_name TEXT,
        last_name TEXT,
        role TEXT DEFAULT 'user',
        messages INTEGER DEFAULT 0,
        banned INTEGER DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    ''')
    
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS admins (
        user_id INTEGER PRIMARY KEY,
        promoted_by INTEGER,
        promoted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    ''')
    
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        chat_type TEXT,
        message TEXT,
        response TEXT,
        ai_model TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    ''')
    
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS bans (
        user_id INTEGER PRIMARY KEY,
        banned_by INTEGER,
        reason TEXT,
        banned_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    ''')
    
    conn.commit()
    return conn

DB = init_database()

# ======================
# DATABASE FUNCTIONS
# ======================
def get_user(user_id: int):
    cursor = DB.cursor()
    cursor.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
    user = cursor.fetchone()
    if user:
        return {
            'user_id': user[0], 'username': user[1], 'first_name': user[2],
            'last_name': user[3], 'role': user[4], 'messages': user[5],
            'banned': user[6], 'created_at': user[7], 'last_seen': user[8]
        }
    return None

def create_user(user_id: int, username: str = "", first_name: str = "", last_name: str = ""):
    cursor = DB.cursor()
    cursor.execute('''
    INSERT OR IGNORE INTO users (user_id, username, first_name, last_name)
    VALUES (?, ?, ?, ?)
    ''', (user_id, username, first_name, last_name))
    DB.commit()

def update_user_stats(user_id: int):
    cursor = DB.cursor()
    cursor.execute('''
    UPDATE users 
    SET messages = messages + 1, last_seen = CURRENT_TIMESTAMP
    WHERE user_id = ?
    ''', (user_id,))
    DB.commit()

def is_admin(user_id: int) -> bool:
    if user_id == OWNER_ID:
        return True
    cursor = DB.cursor()
    cursor.execute('SELECT 1 FROM admins WHERE user_id = ?', (user_id,))
    return cursor.fetchone() is not None

def is_banned(user_id: int) -> bool:
    cursor = DB.cursor()
    cursor.execute('SELECT banned FROM users WHERE user_id = ?', (user_id,))
    result = cursor.fetchone()
    return result and result[0] == 1 if result else False

def ban_user(user_id: int, banned_by: int, reason: str = ""):
    cursor = DB.cursor()
    cursor.execute('UPDATE users SET banned = 1 WHERE user_id = ?', (user_id,))
    cursor.execute('''
    INSERT OR REPLACE INTO bans (user_id, banned_by, reason)
    VALUES (?, ?, ?)
    ''', (user_id, banned_by, reason))
    DB.commit()

def unban_user(user_id: int):
    cursor = DB.cursor()
    cursor.execute('UPDATE users SET banned = 0 WHERE user_id = ?', (user_id,))
    cursor.execute('DELETE FROM bans WHERE user_id = ?', (user_id,))
    DB.commit()

def promote_to_admin(user_id: int, promoted_by: int):
    cursor = DB.cursor()
    cursor.execute('INSERT OR IGNORE INTO admins (user_id, promoted_by) VALUES (?, ?)', (user_id, promoted_by))
    cursor.execute('UPDATE users SET role = "admin" WHERE user_id = ?', (user_id,))
    DB.commit()

def demote_admin(user_id: int):
    cursor = DB.cursor()
    cursor.execute('DELETE FROM admins WHERE user_id = ?', (user_id,))
    cursor.execute('UPDATE users SET role = "user" WHERE user_id = ?', (user_id,))
    DB.commit()

def get_all_users():
    cursor = DB.cursor()
    cursor.execute('SELECT * FROM users ORDER BY created_at DESC')
    return cursor.fetchall()

def get_all_admins():
    cursor = DB.cursor()
    cursor.execute('''
    SELECT u.user_id, u.username, u.first_name, a.promoted_by, a.promoted_at
    FROM users u
    JOIN admins a ON u.user_id = a.user_id
    ''')
    return cursor.fetchall()

def log_message(user_id: int, chat_type: str, message: str, response: str, ai_model: str):
    cursor = DB.cursor()
    cursor.execute('''
    INSERT INTO messages (user_id, chat_type, message, response, ai_model)
    VALUES (?, ?, ?, ?, ?)
    ''', (user_id, chat_type, message, response, ai_model))
    DB.commit()

def get_stats():
    cursor = DB.cursor()
    cursor.execute('SELECT COUNT(*) FROM users')
    total_users = cursor.fetchone()[0]
    cursor.execute('SELECT COUNT(*) FROM users WHERE banned = 1')
    banned_users = cursor.fetchone()[0]
    cursor.execute('SELECT COUNT(*) FROM admins')
    total_admins = cursor.fetchone()[0]
    cursor.execute('SELECT SUM(messages) FROM users')
    total_messages = cursor.fetchone()[0] or 0
    cursor.execute('SELECT COUNT(*) FROM messages')
    total_interactions = cursor.fetchone()[0]
    return {
        'total_users': total_users, 'banned_users': banned_users,
        'total_admins': total_admins, 'total_messages': total_messages,
        'total_interactions': total_interactions
    }

def export_users_to_file():
    users = get_all_users()
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    content = f"""🌪️ TEMPEST CREED - USER REGISTRY
Generated: {timestamp}
Total Users: {len(users)}

ID          Username        Role    Messages    Status      Joined
{'-'*80}
"""
    for user in users:
        user_id = user[0]
        username = user[1] or "N/A"
        role = user[4]
        messages = user[5]
        banned = "🔴 BANNED" if user[6] else "🟢 ACTIVE"
        created = user[7]
        content += f"{user_id:<12} {username:<15} {role:<8} {messages:<10} {banned:<12} {created}\n"
    
    filename = f"users_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
    with open(filename, 'w', encoding='utf-8') as f:
        f.write(content)
    return filename

def export_logs_to_file(lines: int = 100):
    cursor = DB.cursor()
    cursor.execute('''
    SELECT m.created_at, u.user_id, u.username, m.message, m.response, m.ai_model
    FROM messages m
    LEFT JOIN users u ON m.user_id = u.user_id
    ORDER BY m.created_at DESC
    LIMIT ?
    ''', (lines,))
    logs = cursor.fetchall()
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    content = f"""🌪️ TEMPEST CREED - SYSTEM LOGS
Generated: {timestamp}
Total Logs: {len(logs)}

Timestamp           User ID     Username    Message Preview
{'-'*80}
"""
    for log in logs:
        timestamp = log[0]
        user_id = log[1]
        username = log[2] or "N/A"
        message = (log[3][:50] + '...') if len(log[3]) > 50 else log[3]
        content += f"{timestamp:<20} {user_id:<12} {username:<12} {message}\n"
    
    filename = f"logs_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
    with open(filename, 'w', encoding='utf-8') as f:
        f.write(content)
    return filename

def export_stats_to_file():
    stats = get_stats()
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    content = f"""🌪️ TEMPEST CREED - PERFORMANCE STATISTICS
Generated: {timestamp}

📊 USER STATISTICS:
• Total Users: {stats['total_users']}
• Banned Users: {stats['banned_users']}
• Active Admins: {stats['total_admins']}
• Total Messages: {stats['total_messages']}

🤖 BOT STATISTICS:
• Total Interactions: {stats['total_interactions']}
• AI System: Unified Tempest AI
"""
    filename = f"stats_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
    with open(filename, 'w', encoding='utf-8') as f:
        f.write(content)
    return filename

# ======================
# UNIFIED AI SYSTEM WITH FAILOVER
# ======================
async def unified_ai_response(prompt: str) -> Tuple[str, str]:
    """
    PRIMARY AI FUNCTION - No watermarks
    Returns: (response_text, model_used)
    """
    
    # 1. FIRST TRY: OpenAI GPT-3.5
    try:
        payload = {
            "model": "gpt-3.5-turbo",
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 800
        }
        headers = {
            "Content-Type": "application/json",
            "x-rapidapi-key": RAPIDAPI_KEY,
            "x-rapidapi-host": "open-ai32.p.rapidapi.com"
        }
        async with aiohttp.ClientSession() as session:
            async with session.post(OPENAI_CHAT_URL, json=payload, headers=headers, timeout=20) as response:
                if response.status == 200:
                    data = await response.json()
                    if "choices" in data and len(data["choices"]) > 0:
                        response_text = data["choices"][0]["message"]["content"]
                        return response_text.strip(), "gpt-3.5-turbo"
    except Exception:
        pass
    
    # 2. SECOND TRY: Ollama/Qwen
    try:
        payload = {
            "prompt": prompt,
            "model": "qwen2.5:0.5b",
            "max_tokens": 600,
            "temperature": 0.7
        }
        headers = {
            "Content-Type": "application/json",
            "x-rapidapi-key": RAPIDAPI_KEY,
            "x-rapidapi-host": "ollama-local-ai-text-generation-api-qwen-powered.p.rapidapi.com"
        }
        async with aiohttp.ClientSession() as session:
            async with session.post(OLLAMA_GEN_URL, json=payload, headers=headers, timeout=25) as response:
                if response.status == 200:
                    data = await response.json()
                    if "response" in data:
                        return data["response"].strip(), "qwen2.5"
                    elif "choices" in data:
                        return data["choices"][0]["text"].strip(), "qwen2.5"
    except Exception:
        pass
    
    # 3. FINAL FALLBACK
    fallback_responses = [
        "I'm currently optimizing my responses. Please try again in a moment.",
        "Processing your request... please rephrase or try again.",
        "Let me think about that... Could you provide more details?",
        "Interesting question! Let me process that information."
    ]
    return random.choice(fallback_responses), "system"

async def generate_tempest_image(prompt: str) -> Optional[str]:
    """Generate image using FLUX"""
    try:
        payload = {"prompt": prompt, "num_outputs": 1, "aspect_ratio": "1:1"}
        headers = {
            "Content-Type": "application/json",
            "x-rapidapi-key": RAPIDAPI_KEY,
            "x-rapidapi-host": "ai-text-to-image-generator-flux-free-api.p.rapidapi.com"
        }
        async with aiohttp.ClientSession() as session:
            async with session.post(FLUX_IMAGE_URL, json=payload, headers=headers, timeout=30) as response:
                if response.status == 200:
                    data = await response.json()
                    if "data" in data and "resultUrls" in data["data"]:
                        return data["data"]["resultUrls"][0]
                    elif "image_url" in data:
                        return data["image_url"]
                    elif "url" in data:
                        return data["url"]
    except Exception:
        pass
    return None

async def get_current_weather(city: str) -> str:
    """Get current weather"""
    if not WEATHER_API_KEY:
        return "Weather API not configured."
    try:
        url = f"http://api.openweathermap.org/data/2.5/weather?q={city}&appid={WEATHER_API_KEY}&units=metric"
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=10) as response:
                if response.status == 200:
                    data = await response.json()
                    temp = data['main']['temp']
                    desc = data['weather'][0]['description'].title()
                    humidity = data['main']['humidity']
                    return f"🌤️ Weather in {city}: {temp}°C, {desc}, Humidity: {humidity}%"
    except:
        pass
    return "Weather service unavailable."

def get_current_time() -> str:
    now = datetime.now()
    return f"📅 Date: {now.strftime('%Y-%m-%d')}\n⏰ Time: {now.strftime('%H:%M:%S')}"

# ======================
# LOG CHANNEL FUNCTIONS
# ======================
async def log_to_channel(context: ContextTypes.DEFAULT_TYPE, message: str):
    try:
        await context.bot.send_message(
            chat_id=LOG_CHANNEL,
            text=message,
            parse_mode='HTML'
        )
    except Exception:
        pass

# ======================
# PUBLIC COMMANDS
# ======================
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    create_user(user.id, user.username, user.first_name, user.last_name)
    welcome_text = f"""🤖 <b>Welcome to Tempest AI!</b>

<b>Organization:</b> Tempest Creed
<b>Status:</b> Private AI Research Division

<b>Available Commands:</b>
/start - Show this message
/help - Get assistance  
/info - About Tempest Creed
/image [prompt] - Generate AI image

<b>How to use:</b>
Just send me a message! I'll reply automatically.
In groups, mention "tempest" and I'll respond.

<b>Owner:</b> <code>6108185460</code>
"""
    await update.message.reply_photo(photo=WELCOME_PIC, caption=welcome_text, parse_mode='HTML')

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = """🆘 <b>Tempest AI Help</b>

<b>Basic Usage:</b>
Just send me any message and I'll reply!
No watermarks, no special commands needed.

<b>Special Commands:</b>
/start - Initialize bot
/help - Show this help
/image [prompt] - Generate AI image
/info - About organization

<b>In Groups:</b>
I only respond to messages containing "tempest"

<b>Features:</b>
• Unified AI with automatic failover
• Image generation
• Weather information
• Time/date queries
"""
    await update.message.reply_text(help_text, parse_mode='HTML')

async def info_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    info_text = """🏢 <b>About Tempest Creed</b>

<b>Organization:</b> Tempest Creed
<b>Type:</b> Private AI Research Division
<b>Focus:</b> Unified AI systems with failover protection
<b>Status:</b> Invite-only access

<b>Bot Owner:</b> <code>6108185460</code>
<b>Contact:</b> Telegram ID 6108185460

<b>AI Architecture:</b>
• Primary: GPT-3.5 Turbo
• Fallback: Qwen 2.5
• Image: FLUX AI Generator

For inquiries, contact the owner.
"""
    await update.message.reply_text(info_text, parse_mode='HTML')

async def image_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if is_banned(user.id):
        await update.message.reply_text("❌ You are banned from using this bot.")
        return
    if not context.args:
        await update.message.reply_text("Usage: <code>/image a beautiful sunset</code>", parse_mode='HTML')
        return
    prompt = " ".join(context.args)
    await update.message.reply_text(f"🖼️ Generating image: {prompt}...", parse_mode='HTML')
    image_url = await generate_tempest_image(prompt)
    if image_url:
        await update.message.reply_photo(photo=image_url, caption=f"Generated: {prompt}")
    else:
        await update.message.reply_text("❌ Failed to generate image.")

# ======================
# OWNER COMMANDS (ALL INCLUDED)
# ======================
async def owner_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if user.id != OWNER_ID:
        await update.message.reply_text("❌ Access denied.")
        return
    owner_commands = """👑 <b>OWNER COMMAND SUITE</b>

<b>User Management:</b>
/bfb [user_id] [reason] - Ban/Forbid user
/pro [user_id] - Promote to admin
/demote [user_id] - Demote admin
/admins - List all admins

<b>File Exports:</b>
/users - Export users list (txt)
/logs [num] - Export logs (txt)
/stats - Export statistics (txt)

<b>System Control:</b>
/broadcast [message] - Broadcast to all users
/restart - Restart bot
/backup - Backup database
/maintenance [on/off] - Maintenance mode

<b>Info:</b>
/owner - Show this help
"""
    await update.message.reply_text(owner_commands, parse_mode='HTML')

async def bfb_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if user.id != OWNER_ID and not is_admin(user.id):
        await update.message.reply_text("❌ Admin access required.")
        return
    if not context.args:
        await update.message.reply_text("Usage: <code>/bfb [user_id] [reason]</code>", parse_mode='HTML')
        return
    try:
        target_id = int(context.args[0])
        reason = " ".join(context.args[1:]) if len(context.args) > 1 else "No reason provided"
        if target_id == OWNER_ID:
            await update.message.reply_text("❌ Cannot ban owner.")
            return
        target_user = get_user(target_id)
        if not target_user:
            await update.message.reply_text(f"❌ User {target_id} not found.")
            return
        if is_banned(target_id):
            unban_user(target_id)
            await update.message.reply_text(f"✅ User {target_id} has been unbanned.")
        else:
            ban_user(target_id, user.id, reason)
            await update.message.reply_text(f"✅ User {target_id} has been banned.\nReason: {reason}")
    except ValueError:
        await update.message.reply_text("❌ Invalid user ID.")

async def pro_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if user.id != OWNER_ID:
        await update.message.reply_text("❌ Owner access required.")
        return
    if not context.args:
        await update.message.reply_text("Usage: <code>/pro [user_id]</code>", parse_mode='HTML')
        return
    try:
        target_id = int(context.args[0])
        if target_id == user.id:
            await update.message.reply_text("❌ You're already the owner.")
            return
        target_user = get_user(target_id)
        if not target_user:
            await update.message.reply_text(f"❌ User {target_id} not found.")
            return
        if is_admin(target_id):
            await update.message.reply_text(f"❌ User {target_id} is already an admin.")
            return
        promote_to_admin(target_id, user.id)
        await update.message.reply_text(f"✅ User {target_id} has been promoted to admin.")
    except ValueError:
        await update.message.reply_text("❌ Invalid user ID.")

async def broadcast_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if user.id != OWNER_ID and not is_admin(user.id):
        await update.message.reply_text("❌ Admin access required.")
        return
    if not context.args:
        await update.message.reply_text("Usage: <code>/broadcast [message]</code>", parse_mode='HTML')
        return
    message = " ".join(context.args)
    users = get_all_users()
    broadcast_msg = f"📢 <b>Broadcast from Tempest Creed</b>\n\n{message}"
    sent = 0
    failed = 0
    status_msg = await update.message.reply_text(f"📡 Starting broadcast to {len(users)} users...")
    for user_data in users:
        user_id = user_data[0]
        if user_id == user.id or is_banned(user_id):
            continue
        try:
            await context.bot.send_message(chat_id=user_id, text=broadcast_msg, parse_mode='HTML')
            sent += 1
            await asyncio.sleep(0.1)
        except:
            failed += 1
    result_msg = f"✅ <b>Broadcast Completed</b>\n\n📤 <b>Successfully sent:</b> {sent}\n❌ <b>Failed:</b> {failed}"
    await status_msg.edit_text(result_msg, parse_mode='HTML')

async def users_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if user.id != OWNER_ID and not is_admin(user.id):
        await update.message.reply_text("❌ Admin access required.")
        return
    await update.message.reply_text("📊 Generating users list...")
    filename = export_users_to_file()
    try:
        with open(filename, 'rb') as f:
            await update.message.reply_document(document=f, filename=filename)
        os.remove(filename)
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {str(e)}")

async def logs_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if user.id != OWNER_ID and not is_admin(user.id):
        await update.message.reply_text("❌ Admin access required.")
        return
    lines = 100
    if context.args:
        try:
            lines = int(context.args[0])
            lines = min(lines, 1000)
        except:
            pass
    await update.message.reply_text(f"📝 Generating logs ({lines} lines)...")
    filename = export_logs_to_file(lines)
    try:
        with open(filename, 'rb') as f:
            await update.message.reply_document(document=f, filename=filename)
        os.remove(filename)
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {str(e)}")

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if user.id != OWNER_ID and not is_admin(user.id):
        await update.message.reply_text("❌ Admin access required.")
        return
    await update.message.reply_text("📈 Generating statistics...")
    filename = export_stats_to_file()
    try:
        with open(filename, 'rb') as f:
            await update.message.reply_document(document=f, filename=filename)
        os.remove(filename)
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {str(e)}")

async def admins_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if user.id != OWNER_ID and not is_admin(user.id):
        await update.message.reply_text("❌ Admin access required.")
        return
    admins = get_all_admins()
    admin_list = f"👑 <b>ADMINISTRATORS</b>\n\n<b>• Owner:</b> <code>{OWNER_ID}</code>\n<b>• Total Admins:</b> {len(admins)}"
    if admins:
        admin_list += "\n\n<b>Admin List:</b>\n"
        for admin in admins:
            user_id = admin[0]
            username = admin[1] or "N/A"
            promoted_by = admin[3]
            admin_list += f"\n<b>ID:</b> <code>{user_id}</code>\n<b>Username:</b> @{username}\n"
    await update.message.reply_text(admin_list, parse_mode='HTML')

async def demote_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if user.id != OWNER_ID:
        await update.message.reply_text("❌ Owner access required.")
        return
    if not context.args:
        await update.message.reply_text("Usage: <code>/demote [user_id]</code>", parse_mode='HTML')
        return
    try:
        target_id = int(context.args[0])
        if target_id == user.id:
            await update.message.reply_text("❌ Cannot demote owner.")
            return
        if not is_admin(target_id):
            await update.message.reply_text(f"❌ User {target_id} is not an admin.")
            return
        demote_admin(target_id)
        await update.message.reply_text(f"✅ User {target_id} has been demoted.")
    except ValueError:
        await update.message.reply_text("❌ Invalid user ID.")

async def restart_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if user.id != OWNER_ID:
        await update.message.reply_text("❌ Owner access required.")
        return
    await update.message.reply_text("🔄 Restarting Tempest AI...")
    os._exit(0)

async def backup_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if user.id != OWNER_ID and not is_admin(user.id):
        await update.message.reply_text("❌ Admin access required.")
        return
    import shutil
    shutil.copy2('tempest.db', f'tempest_backup_{datetime.now().strftime("%Y%m%d_%H%M%S")}.db')
    await update.message.reply_text("✅ Database backup created.")

# ======================
# MAIN MESSAGE HANDLER
# ======================
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    message_text = update.message.text
    chat_type = update.message.chat.type
    
    create_user(user.id, user.username, user.first_name, user.last_name)
    
    if is_banned(user.id):
        return
    
    if chat_type in ['group', 'supergroup']:
        if "tempest" not in message_text.lower():
            return
    
    if message_text.startswith('/'):
        return
    
    # Weather queries
    if "weather" in message_text.lower() and "in" in message_text.lower():
        try:
            parts = message_text.lower().split("in")
            if len(parts) > 1:
                city = parts[1].strip()
                weather = await get_current_weather(city)
                await update.message.reply_text(weather)
                update_user_stats(user.id)
                log_message(user.id, chat_type, message_text, weather, "weather_api")
                return
        except:
            pass
    
    # Time queries
    if any(word in message_text.lower() for word in ["time", "date", "today", "now"]):
        time_info = get_current_time()
        await update.message.reply_text(time_info)
        update_user_stats(user.id)
        log_message(user.id, chat_type, message_text, time_info, "time_api")
        return
    
    await update.message.reply_chat_action(action="typing")
    
    # UNIFIED AI RESPONSE - NO WATERMARKS
    response, model_used = await unified_ai_response(message_text)
    
    # Send clean response without any watermarks
    await update.message.reply_text(response)
    
    update_user_stats(user.id)
    log_message(user.id, chat_type, message_text, response, model_used)

# ======================
# MAIN FUNCTION - ALWAYS AWAKE
# ======================
def main():
    application = Application.builder().token(BOT_TOKEN).build()
    
    # Public commands
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("info", info_command))
    application.add_handler(CommandHandler("image", image_command))
    
    # Owner commands (ALL INCLUDED)
    application.add_handler(CommandHandler("owner", owner_command))
    application.add_handler(CommandHandler("bfb", bfb_command))
    application.add_handler(CommandHandler("pro", pro_command))
    application.add_handler(CommandHandler("broadcast", broadcast_command))
    application.add_handler(CommandHandler("users", users_command))
    application.add_handler(CommandHandler("logs", logs_command))
    application.add_handler(CommandHandler("stats", stats_command))
    application.add_handler(CommandHandler("admins", admins_command))
    application.add_handler(CommandHandler("demote", demote_command))
    application.add_handler(CommandHandler("restart", restart_command))
    application.add_handler(CommandHandler("backup", backup_command))
    
    # Main message handler
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    print("🌪️ Tempest AI - ALWAYS AWAKE")
    print(f"🤖 Bot Token: {BOT_TOKEN[:15]}...")
    print(f"👑 Owner ID: {OWNER_ID}")
    print(f"🔑 RapidAPI Key: {RAPIDAPI_KEY[:10]}...")
    print("🚀 Bot is now running 24/7...")
    
    # Run with persistent polling (always awake)
    application.run_polling(
        allowed_updates=Update.ALL_TYPES,
        drop_pending_updates=True,
        close_loop=False
    )

if __name__ == '__main__':
    main()
