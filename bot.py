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
import requests
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from enum import Enum
from dataclasses import dataclass, asdict
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
    CallbackQueryHandler
)
from telegram.error import TelegramError
import pytz

# ======================
# CONFIGURATION
# ======================
OWNER_ID = 6108185460  # Hardcoded owner ID
BOT_TOKEN = "7869314780:AAFFU5jMv-WK9sCJnAJ4X0oRtog632B9sUg"
WEATHER_API_KEY = os.getenv("WEATHER_API_KEY", "")
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
DEFAULT_MODEL = os.getenv("DEFAULT_MODEL", "llama3")

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
    """Initialize SQLite database"""
    conn = sqlite3.connect('tempest.db', check_same_thread=False)
    cursor = conn.cursor()
    
    # Users table
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
    
    # Admins table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS admins (
        user_id INTEGER PRIMARY KEY,
        promoted_by INTEGER,
        promoted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users (user_id)
    )
    ''')
    
    # Messages table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        chat_type TEXT,
        message TEXT,
        response TEXT,
        model TEXT,
        tokens INTEGER,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    ''')
    
    # Bans table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS bans (
        user_id INTEGER PRIMARY KEY,
        banned_by INTEGER,
        reason TEXT,
        banned_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users (user_id)
    )
    ''')
    
    conn.commit()
    return conn

DB = init_database()

# ======================
# DATABASE FUNCTIONS
# ======================
def get_user(user_id: int):
    """Get user from database"""
    cursor = DB.cursor()
    cursor.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
    user = cursor.fetchone()
    if user:
        return {
            'user_id': user[0],
            'username': user[1],
            'first_name': user[2],
            'last_name': user[3],
            'role': user[4],
            'messages': user[5],
            'banned': user[6],
            'created_at': user[7],
            'last_seen': user[8]
        }
    return None

def create_user(user_id: int, username: str = "", first_name: str = "", last_name: str = ""):
    """Create new user in database"""
    cursor = DB.cursor()
    cursor.execute('''
    INSERT OR IGNORE INTO users (user_id, username, first_name, last_name)
    VALUES (?, ?, ?, ?)
    ''', (user_id, username, first_name, last_name))
    DB.commit()

def update_user_stats(user_id: int):
    """Update user message count and last seen"""
    cursor = DB.cursor()
    cursor.execute('''
    UPDATE users 
    SET messages = messages + 1, last_seen = CURRENT_TIMESTAMP
    WHERE user_id = ?
    ''', (user_id,))
    DB.commit()

def is_admin(user_id: int) -> bool:
    """Check if user is admin"""
    if user_id == OWNER_ID:
        return True
    cursor = DB.cursor()
    cursor.execute('SELECT 1 FROM admins WHERE user_id = ?', (user_id,))
    return cursor.fetchone() is not None

def is_banned(user_id: int) -> bool:
    """Check if user is banned"""
    cursor = DB.cursor()
    cursor.execute('SELECT banned FROM users WHERE user_id = ?', (user_id,))
    result = cursor.fetchone()
    return result and result[0] == 1 if result else False

def ban_user(user_id: int, banned_by: int, reason: str = ""):
    """Ban a user"""
    cursor = DB.cursor()
    cursor.execute('UPDATE users SET banned = 1 WHERE user_id = ?', (user_id,))
    cursor.execute('''
    INSERT OR REPLACE INTO bans (user_id, banned_by, reason)
    VALUES (?, ?, ?)
    ''', (user_id, banned_by, reason))
    DB.commit()

def unban_user(user_id: int):
    """Unban a user"""
    cursor = DB.cursor()
    cursor.execute('UPDATE users SET banned = 0 WHERE user_id = ?', (user_id,))
    cursor.execute('DELETE FROM bans WHERE user_id = ?', (user_id,))
    DB.commit()

def promote_to_admin(user_id: int, promoted_by: int):
    """Promote user to admin"""
    cursor = DB.cursor()
    cursor.execute('INSERT OR IGNORE INTO admins (user_id, promoted_by) VALUES (?, ?)', (user_id, promoted_by))
    cursor.execute('UPDATE users SET role = "admin" WHERE user_id = ?', (user_id,))
    DB.commit()

def demote_admin(user_id: int):
    """Demote admin to user"""
    cursor = DB.cursor()
    cursor.execute('DELETE FROM admins WHERE user_id = ?', (user_id,))
    cursor.execute('UPDATE users SET role = "user" WHERE user_id = ?', (user_id,))
    DB.commit()

def get_all_users():
    """Get all users"""
    cursor = DB.cursor()
    cursor.execute('SELECT * FROM users ORDER BY created_at DESC')
    return cursor.fetchall()

def get_all_admins():
    """Get all admins"""
    cursor = DB.cursor()
    cursor.execute('''
    SELECT u.user_id, u.username, u.first_name, a.promoted_by, a.promoted_at
    FROM users u
    JOIN admins a ON u.user_id = a.user_id
    ''')
    return cursor.fetchall()

def log_message(user_id: int, chat_type: str, message: str, response: str, model: str, tokens: int):
    """Log message to database"""
    cursor = DB.cursor()
    cursor.execute('''
    INSERT INTO messages (user_id, chat_type, message, response, model, tokens)
    VALUES (?, ?, ?, ?, ?, ?)
    ''', (user_id, chat_type, message, response, model, tokens))
    DB.commit()

def get_stats():
    """Get bot statistics"""
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
        'total_users': total_users,
        'banned_users': banned_users,
        'total_admins': total_admins,
        'total_messages': total_messages,
        'total_interactions': total_interactions
    }

# ======================
# AI FUNCTIONS (Ollama)
# ======================
async def ask_ollama(prompt: str, model: str = DEFAULT_MODEL) -> str:
    """Query Ollama for response"""
    try:
        url = f"{OLLAMA_URL}/api/generate"
        payload = {
            "model": model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": 0.7,
                "top_p": 0.9,
                "max_tokens": 1000
            }
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, timeout=30) as response:
                if response.status == 200:
                    data = await response.json()
                    return data.get("response", "I apologize, but I couldn't generate a response.")
                else:
                    return "⚠️ Ollama is not responding. Please check if Ollama is running."
    except Exception as e:
        logger.error(f"Ollama error: {e}")
        return "❌ Error connecting to Ollama. Please ensure Ollama is installed and running."

# ======================
# CURRENT DATA FUNCTIONS
# ======================
async def get_current_weather(city: str) -> str:
    """Get current weather for a city"""
    if not WEATHER_API_KEY:
        return "Weather API not configured."
    
    try:
        url = f"http://api.openweathermap.org/data/2.5/weather?q={city}&appid={WEATHER_API_KEY}&units=metric"
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=10) as response:
                if response.status == 200:
                    data = await response.json()
                    temp = data['main']['temp']
                    desc = data['weather'][0]['description']
                    humidity = data['main']['humidity']
                    return f"🌤️ Weather in {city}: {temp}°C, {desc}, Humidity: {humidity}%"
                else:
                    return "Could not fetch weather data."
    except:
        return "Weather service unavailable."

def get_current_time() -> str:
    """Get current date and time"""
    now = datetime.now()
    return now.strftime("📅 Date: %Y-%m-%d\n⏰ Time: %H:%M:%S\n🌐 Timezone: UTC")

# ======================
# FILE EXPORT FUNCTIONS
# ======================
def export_users_to_file():
    """Export users list to text file"""
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
    """Export recent logs to text file"""
    cursor = DB.cursor()
    cursor.execute('''
    SELECT m.created_at, u.user_id, u.username, m.message, m.response, m.model
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
    """Export statistics to text file"""
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
• Default Model: {DEFAULT_MODEL}
• Ollama URL: {OLLAMA_URL}

🕒 SYSTEM INFO:
• Bot Owner: 6108185460
• Organization: Tempest Creed
"""
    
    filename = f"stats_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
    with open(filename, 'w', encoding='utf-8') as f:
        f.write(content)
    
    return filename

# ======================
# TELEGRAM BOT HANDLERS
# ======================
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command"""
    user = update.effective_user
    create_user(user.id, user.username, user.first_name, user.last_name)
    
    welcome_text = f"""🤖 *Welcome to Tempest AI!*
    
*Organization:* Tempest Creed
*Status:* Private AI Research Division

*Available Commands:*
/start - Show this message
/help - Get assistance  
/model - Check current AI model
/ask [question] - Ask me anything
/reset - Clear conversation history
/info - About Tempest Creed

*How to use in groups:* 
Mention "tempest" in your message and I'll reply!

*Owner:* `6108185460`
*Default Model:* `{DEFAULT_MODEL}`
"""
    await update.message.reply_text(welcome_text, parse_mode='Markdown')

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /help command"""
    help_text = """🆘 *Tempest AI Help*
    
*Basic Commands:*
/start - Initialize bot
/help - Show this help
/model - Current AI model  
/ask [question] - Direct question
/reset - Clear memory
/info - About organization

*In Groups:*
I only respond to messages containing "tempest" (case-insensitive)

*Current Features:*
• Local AI with Ollama
• Weather information
• Time/date queries
• Conversation memory
• File exports (admin only)

*Contact Owner:* `6108185460`
"""
    await update.message.reply_text(help_text, parse_mode='Markdown')

async def info_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /info command"""
    info_text = """🏢 *About Tempest Creed*
    
*Organization:* Tempest Creed
*Type:* Private AI Research Division
*Focus:* Local AI systems and secure communication
*Status:* Invite-only access

*Bot Owner:* `6108185460`
*Contact:* Telegram ID 6108185460

*Mission:* To provide secure, private AI assistance through locally-hosted models, ensuring complete data privacy and user control.

*Current AI Provider:* Ollama
*Default Model:* {DEFAULT_MODEL}

For inquiries or access requests, contact the owner.
"""
    await update.message.reply_text(info_text.format(DEFAULT_MODEL=DEFAULT_MODEL), parse_mode='Markdown')

async def model_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /model command"""
    await update.message.reply_text(
        f"🤖 *Current AI Model:* `{DEFAULT_MODEL}`\n"
        f"🌐 *Ollama URL:* `{OLLAMA_URL}`\n"
        f"⚡ *Status:* {'🟢 Connected' if OLLAMA_URL else '🔴 Not configured'}",
        parse_mode='Markdown'
    )

async def ask_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /ask command"""
    user = update.effective_user
    
    if is_banned(user.id):
        await update.message.reply_text("❌ You are banned from using this bot.")
        return
    
    if not context.args:
        await update.message.reply_text("Please provide a question: `/ask What is AI?`", parse_mode='Markdown')
        return
    
    question = " ".join(context.args)
    await update.message.reply_chat_action(action="typing")
    
    # Check for current data queries
    if "weather" in question.lower() and "in" in question.lower():
        # Extract city name
        try:
            parts = question.lower().split("in")
            if len(parts) > 1:
                city = parts[1].strip()
                weather = await get_current_weather(city)
                await update.message.reply_text(weather)
                return
        except:
            pass
    
    if any(word in question.lower() for word in ["time", "date", "today", "now"]):
        time_info = get_current_time()
        await update.message.reply_text(time_info)
    
    # Use AI for other questions
    response = await ask_ollama(question)
    
    # Update user stats
    update_user_stats(user.id)
    log_message(user.id, "private", question, response, DEFAULT_MODEL, len(response.split()))
    
    await update.message.reply_text(response)

# ======================
# OWNER COMMANDS (Hidden)
# ======================
async def owner_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /owner command (owner only)"""
    user = update.effective_user
    if user.id != OWNER_ID:
        await update.message.reply_text("❌ Access denied.")
        return
    
    owner_commands = """👑 *OWNER COMMAND SUITE*

*User Management:*
/bfb [user_id] [reason] - Ban/Forbid user
/pro [user_id] - Promote to admin
/demote [user_id] - Demote admin
/admins - List all admins

*File Exports:*
/users - Export users list (txt)
/logs [num] - Export logs (txt)
/stats - Export statistics (txt)

*System Control:*
/broadcast [message] - Broadcast to all users
/restart - Restart bot
/backup - Backup database
/maintenance [on/off] - Maintenance mode
/prompt [text] - Change system prompt
/cleardb - Clear all data (⚠️ DANGER)

*Info:*
/owner - Show this help
"""
    
    await update.message.reply_text(owner_commands, parse_mode='Markdown')

async def bfb_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /bfb command - Ban/Forbid user"""
    user = update.effective_user
    if user.id != OWNER_ID and not is_admin(user.id):
        await update.message.reply_text("❌ Admin access required.")
        return
    
    if not context.args:
        await update.message.reply_text("Usage: `/bfb [user_id] [reason]`\nExample: `/bfb 123456789 Spamming`", parse_mode='Markdown')
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
    """Handle /pro command - Promote user to admin"""
    user = update.effective_user
    if user.id != OWNER_ID:
        await update.message.reply_text("❌ Owner access required.")
        return
    
    if not context.args:
        await update.message.reply_text("Usage: `/pro [user_id]`\nExample: `/pro 123456789`", parse_mode='Markdown')
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
        
        promote_to_admin(target_id, user.id)
        await update.message.reply_text(f"✅ User {target_id} has been promoted to admin.")
        
    except ValueError:
        await update.message.reply_text("❌ Invalid user ID.")

async def broadcast_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /broadcast command"""
    user = update.effective_user
    if user.id != OWNER_ID and not is_admin(user.id):
        await update.message.reply_text("❌ Admin access required.")
        return
    
    if not context.args:
        await update.message.reply_text("Usage: `/broadcast [message]`", parse_mode='Markdown')
        return
    
    message = " ".join(context.args)
    users = get_all_users()
    
    broadcast_msg = f"📢 *Broadcast from Tempest Creed*\n\n{message}\n\n_This is an automated message_"
    
    sent = 0
    failed = 0
    
    await update.message.reply_text(f"📡 Starting broadcast to {len(users)} users...")
    
    for user_data in users:
        user_id = user_data[0]
        if user_id == user.id or is_banned(user_id):
            continue
        
        try:
            await context.bot.send_message(
                chat_id=user_id,
                text=broadcast_msg,
                parse_mode='Markdown'
            )
            sent += 1
            await asyncio.sleep(0.1)  # Rate limiting
        except:
            failed += 1
    
    await update.message.reply_text(
        f"✅ Broadcast completed!\n"
        f"• Successfully sent: {sent}\n"
        f"• Failed: {failed}"
    )

async def users_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /users command - Export users list"""
    user = update.effective_user
    if user.id != OWNER_ID and not is_admin(user.id):
        await update.message.reply_text("❌ Admin access required.")
        return
    
    await update.message.reply_text("📊 Generating users list...")
    filename = export_users_to_file()
    
    try:
        with open(filename, 'rb') as f:
            await update.message.reply_document(
                document=f,
                filename=filename,
                caption=f"📋 Users list generated at {datetime.now().strftime('%H:%M:%S')}"
            )
        os.remove(filename)
    except Exception as e:
        await update.message.reply_text(f"❌ Error exporting users: {str(e)}")

async def logs_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /logs command - Export logs"""
    user = update.effective_user
    if user.id != OWNER_ID and not is_admin(user.id):
        await update.message.reply_text("❌ Admin access required.")
        return
    
    lines = 100
    if context.args:
        try:
            lines = int(context.args[0])
            lines = min(lines, 1000)  # Limit to 1000 lines
        except:
            pass
    
    await update.message.reply_text(f"📝 Generating logs ({lines} lines)...")
    filename = export_logs_to_file(lines)
    
    try:
        with open(filename, 'rb') as f:
            await update.message.reply_document(
                document=f,
                filename=filename,
                caption=f"📜 Logs file ({lines} lines)"
            )
        os.remove(filename)
    except Exception as e:
        await update.message.reply_text(f"❌ Error exporting logs: {str(e)}")

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /stats command - Export statistics"""
    user = update.effective_user
    if user.id != OWNER_ID and not is_admin(user.id):
        await update.message.reply_text("❌ Admin access required.")
        return
    
    await update.message.reply_text("📈 Generating statistics...")
    filename = export_stats_to_file()
    
    try:
        with open(filename, 'rb') as f:
            await update.message.reply_document(
                document=f,
                filename=filename,
                caption="📊 Tempest Creed Statistics"
            )
        os.remove(filename)
    except Exception as e:
        await update.message.reply_text(f"❌ Error exporting stats: {str(e)}")

async def admins_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /admins command - List all admins"""
    user = update.effective_user
    if user.id != OWNER_ID and not is_admin(user.id):
        await update.message.reply_text("❌ Admin access required.")
        return
    
    admins = get_all_admins()
    
    if not admins:
        await update.message.reply_text("No admins found (except owner).")
        return
    
    admin_list = "👑 *ADMINISTRATORS LIST*\n\n"
    admin_list += f"• Owner: `{OWNER_ID}`\n"
    
    for admin in admins:
        user_id = admin[0]
        username = admin[1] or "N/A"
        promoted_by = admin[3]
        promoted_at = admin[4]
        
        admin_list += f"\n• Admin: `{user_id}`\n"
        admin_list += f"  Username: @{username}\n"
        admin_list += f"  Promoted by: `{promoted_by}`\n"
        admin_list += f"  Promoted at: {promoted_at}\n"
    
    await update.message.reply_text(admin_list, parse_mode='Markdown')

async def demote_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /demote command - Demote admin"""
    user = update.effective_user
    if user.id != OWNER_ID:
        await update.message.reply_text("❌ Owner access required.")
        return
    
    if not context.args:
        await update.message.reply_text("Usage: `/demote [user_id]`")
        return
    
    try:
        target_id = int(context.args[0])
        
        if target_id == user.id:
            await update.message.reply_text("❌ Cannot demote owner.")
            return
        
        demote_admin(target_id)
        await update.message.reply_text(f"✅ User {target_id} has been demoted to user.")
        
    except ValueError:
        await update.message.reply_text("❌ Invalid user ID.")

# ======================
# MESSAGE HANDLER
# ======================
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle all text messages"""
    user = update.effective_user
    message_text = update.message.text
    chat_type = update.message.chat.type
    
    # Create user in database if not exists
    create_user(user.id, user.username, user.first_name, user.last_name)
    
    # Check if user is banned
    if is_banned(user.id):
        return
    
    # Group chat logic
    if chat_type in ['group', 'supergroup']:
        # Only respond if message contains "tempest" (case-insensitive)
        if "tempest" not in message_text.lower():
            return
        
        # Remove trigger word for AI processing
        prompt = message_text.lower().replace("tempest", "").strip()
        if not prompt:
            prompt = "Hello"
    
    # Private chat logic
    else:
        prompt = message_text
    
    # Don't process commands
    if prompt.startswith('/'):
        return
    
    await update.message.reply_chat_action(action="typing")
    
    # Get AI response
    response = await ask_ollama(prompt)
    
    # Update stats and log
    update_user_stats(user.id)
    log_message(user.id, chat_type, prompt, response, DEFAULT_MODEL, len(response.split()))
    
    # Send response
    await update.message.reply_text(response)

# ======================
# MAIN FUNCTION
# ======================
def main():
    """Start the bot"""
    # Create application
    application = Application.builder().token(BOT_TOKEN).build()
    
    # Add command handlers
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("info", info_command))
    application.add_handler(CommandHandler("model", model_command))
    application.add_handler(CommandHandler("ask", ask_command))
    
    # Owner/Admin commands (hidden from help)
    application.add_handler(CommandHandler("owner", owner_command))
    application.add_handler(CommandHandler("bfb", bfb_command))
    application.add_handler(CommandHandler("pro", pro_command))
    application.add_handler(CommandHandler("broadcast", broadcast_command))
    application.add_handler(CommandHandler("users", users_command))
    application.add_handler(CommandHandler("logs", logs_command))
    application.add_handler(CommandHandler("stats", stats_command))
    application.add_handler(CommandHandler("admins", admins_command))
    application.add_handler(CommandHandler("demote", demote_command))
    
    # Message handler
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    # Start the bot
    print("🌪️ Tempest AI is starting...")
    print(f"🤖 Bot Token: {BOT_TOKEN[:15]}...")
    print(f"👑 Owner ID: {OWNER_ID}")
    print(f"🧠 Default Model: {DEFAULT_MODEL}")
    print(f"🌐 Ollama URL: {OLLAMA_URL}")
    print("🚀 Bot is now running...")
    
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()
