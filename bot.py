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
WEATHER_API_KEY = "b5622fffde3852de7528ec5d71a9850a"  # Your OpenWeather API key
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
DEFAULT_MODEL = os.getenv("DEFAULT_MODEL", "llama3")
LOG_CHANNEL = -1003662720845  # Your log channel ID
WELCOME_PIC = "https://files.catbox.moe/s4k1rn.jpg"  # Your welcome picture

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
# LOG CHANNEL FUNCTIONS
# ======================
async def log_to_channel(context: ContextTypes.DEFAULT_TYPE, message: str, photo_url: str = None):
    """Send log message to log channel"""
    try:
        if photo_url:
            await context.bot.send_photo(
                chat_id=LOG_CHANNEL,
                photo=photo_url,
                caption=message,
                parse_mode='HTML'
            )
        else:
            await context.bot.send_message(
                chat_id=LOG_CHANNEL,
                text=message,
                parse_mode='HTML'
            )
    except Exception as e:
        logger.error(f"Failed to send log to channel: {e}")

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
# AI FUNCTIONS (Ollama with Fallback)
# ======================
async def ask_ollama(prompt: str, model: str = DEFAULT_MODEL) -> str:
    """Query Ollama for response with better error handling"""
    try:
        # First check if Ollama is running
        async with aiohttp.ClientSession() as session:
            try:
                # Check Ollama status
                async with session.get(f"{OLLAMA_URL}/api/tags", timeout=5) as check_response:
                    if check_response.status != 200:
                        return "❌ Ollama is not running or not accessible.\n\nTo fix this:\n1. Install Ollama from https://ollama.ai/\n2. Run: `ollama pull llama3`\n3. Run: `ollama serve`\n4. Make sure port 11434 is accessible"
            except:
                return "❌ Cannot connect to Ollama server.\n\nMake sure Ollama is installed and running on your machine.\nInstall from: https://ollama.ai/\n\nFor Railway deployment, you need to use a cloud Ollama service or switch to a different AI provider."
        
        # If Ollama is reachable, proceed with generation
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
                    return f"⚠️ Ollama returned error status: {response.status}"
    except asyncio.TimeoutError:
        return "⏱️ Request timed out. Ollama might be busy or the model is loading."
    except Exception as e:
        logger.error(f"Ollama error: {e}")
        return "❌ Error connecting to Ollama. Please ensure Ollama is installed and running locally, or use a cloud Ollama service for deployment."

# ======================
# CURRENT DATA FUNCTIONS
# ======================
async def get_current_weather(city: str) -> str:
    """Get current weather for a city using OpenWeatherMap"""
    if not WEATHER_API_KEY:
        return "Weather API not configured."
    
    try:
        url = f"http://api.openweathermap.org/data/2.5/weather?q={city}&appid={WEATHER_API_KEY}&units=metric"
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=10) as response:
                if response.status == 200:
                    data = await response.json()
                    temp = data['main']['temp']
                    feels_like = data['main']['feels_like']
                    desc = data['weather'][0]['description'].title()
                    humidity = data['main']['humidity']
                    wind_speed = data['wind']['speed']
                    city_name = data['name']
                    country = data['sys']['country']
                    
                    # Weather emoji mapping
                    weather_icons = {
                        'clear': '☀️',
                        'clouds': '☁️',
                        'rain': '🌧️',
                        'drizzle': '🌦️',
                        'thunderstorm': '⛈️',
                        'snow': '❄️',
                        'mist': '🌫️',
                        'fog': '🌁'
                    }
                    
                    icon = '🌤️'
                    for key, value in weather_icons.items():
                        if key in data['weather'][0]['main'].lower():
                            icon = value
                            break
                    
                    return f"""{icon} <b>Weather in {city_name}, {country}</b>

🌡️ Temperature: {temp}°C (Feels like {feels_like}°C)
📝 Condition: {desc}
💧 Humidity: {humidity}%
💨 Wind Speed: {wind_speed} m/s
📍 Location: {city_name}, {country}
"""
                elif response.status == 404:
                    return f"❌ City '{city}' not found. Please check the city name."
                else:
                    return f"⚠️ Weather service error: {response.status}"
    except asyncio.TimeoutError:
        return "⏱️ Weather request timed out. Please try again later."
    except Exception as e:
        logger.error(f"Weather API error: {e}")
        return "❌ Could not fetch weather data at the moment."

def get_current_time() -> str:
    """Get current date and time"""
    now = datetime.now()
    timezones = {
        "UTC": pytz.UTC,
        "EST": pytz.timezone('US/Eastern'),
        "PST": pytz.timezone('US/Pacific'),
        "GMT": pytz.timezone('GMT'),
        "IST": pytz.timezone('Asia/Kolkata')
    }
    
    time_info = "🕒 <b>Current Time</b>\n\n"
    for tz_name, tz in timezones.items():
        tz_time = datetime.now(tz)
        time_info += f"• <b>{tz_name}:</b> {tz_time.strftime('%Y-%m-%d %H:%M:%S')}\n"
    
    return time_info

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
• Weather API: {'✅ Configured' if WEATHER_API_KEY else '❌ Not configured'}
• Log Channel: {'✅ Configured' if LOG_CHANNEL else '❌ Not configured'}
"""
    
    filename = f"stats_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
    with open(filename, 'w', encoding='utf-8') as f:
        f.write(content)
    
    return filename

# ======================
# TELEGRAM BOT HANDLERS
# ======================
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command with welcome picture"""
    user = update.effective_user
    create_user(user.id, user.username, user.first_name, user.last_name)
    
    welcome_text = f"""🤖 <b>Welcome to Tempest AI!</b>

<b>Organization:</b> Tempest Creed
<b>Status:</b> Private AI Research Division

<b>Available Commands:</b>
/start - Show this message
/help - Get assistance  
/model - Check current AI model
/ask [question] - Ask me anything
/reset - Clear conversation history
/info - About Tempest Creed

<b>How to use in groups:</b> 
Mention "tempest" in your message and I'll reply!

<b>Owner:</b> <code>6108185460</code>
<b>Default Model:</b> <code>{DEFAULT_MODEL}</code>
"""
    
    # Send welcome picture with caption
    await update.message.reply_photo(
        photo=WELCOME_PIC,
        caption=welcome_text,
        parse_mode='HTML'
    )
    
    # Log new user to channel
    log_message = f"""🆕 <b>New User Joined</b>

👤 <b>User:</b> {user.first_name} {f'({user.last_name})' if user.last_name else ''}
🆔 <b>ID:</b> <code>{user.id}</code>
📛 <b>Username:</b> @{user.username if user.username else 'N/A'}
📅 <b>Time:</b> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
👥 <b>Total Users:</b> {len(get_all_users())}
"""
    await log_to_channel(context, log_message)

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /help command"""
    help_text = """🆘 <b>Tempest AI Help</b>

<b>Basic Commands:</b>
/start - Initialize bot
/help - Show this help
/model - Current AI model  
/ask [question] - Direct question
/reset - Clear memory
/info - About organization

<b>In Groups:</b>
I only respond to messages containing "tempest" (case-insensitive)

<b>Current Features:</b>
• Local AI with Ollama
• Weather information (use: "weather in [city]")
• Time/date queries
• Conversation memory
• File exports (admin only)

<b>Contact Owner:</b> <code>6108185460</code>
"""
    await update.message.reply_text(help_text, parse_mode='HTML')

async def info_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /info command"""
    info_text = f"""🏢 <b>About Tempest Creed</b>

<b>Organization:</b> Tempest Creed
<b>Type:</b> Private AI Research Division
<b>Focus:</b> Local AI systems and secure communication
<b>Status:</b> Invite-only access

<b>Bot Owner:</b> <code>6108185460</code>
<b>Contact:</b> Telegram ID 6108185460

<b>Mission:</b> To provide secure, private AI assistance through locally-hosted models, ensuring complete data privacy and user control.

<b>Current AI Provider:</b> Ollama
<b>Default Model:</b> {DEFAULT_MODEL}

For inquiries or access requests, contact the owner.
"""
    await update.message.reply_text(info_text, parse_mode='HTML')

async def model_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /model command"""
    # Test Ollama connection
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{OLLAMA_URL}/api/tags", timeout=5) as response:
                if response.status == 200:
                    status = "🟢 Connected"
                else:
                    status = "🔴 Not responding"
    except:
        status = "🔴 Cannot connect"
    
    model_text = f"""🤖 <b>AI Configuration</b>

<b>Current Model:</b> <code>{DEFAULT_MODEL}</code>
<b>Ollama URL:</b> <code>{OLLAMA_URL}</code>
<b>Status:</b> {status}
<b>Weather API:</b> {'✅ Configured' if WEATHER_API_KEY else '❌ Not configured'}

<b>Note:</b> If Ollama is not running locally, you can:
1. Install from https://ollama.ai/
2. Run: <code>ollama pull {DEFAULT_MODEL}</code>
3. Run: <code>ollama serve</code>
"""
    await update.message.reply_text(model_text, parse_mode='HTML')

async def ask_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /ask command"""
    user = update.effective_user
    
    if is_banned(user.id):
        await update.message.reply_text("❌ You are banned from using this bot.")
        return
    
    if not context.args:
        await update.message.reply_text("Please provide a question: <code>/ask What is AI?</code>", parse_mode='HTML')
        return
    
    question = " ".join(context.args)
    await update.message.reply_chat_action(action="typing")
    
    # Check for weather queries
    if "weather" in question.lower():
        if "in" in question.lower():
            try:
                parts = question.lower().split("in")
                if len(parts) > 1:
                    city = parts[1].strip()
                    weather = await get_current_weather(city)
                    await update.message.reply_text(weather, parse_mode='HTML')
                    
                    # Log to database
                    log_message(user.id, "private", question, weather, "weather_api", 0)
                    update_user_stats(user.id)
                    return
            except Exception as e:
                logger.error(f"Weather query error: {e}")
    
    # Check for time/date queries
    if any(word in question.lower() for word in ["time", "date", "today", "now", "current time"]):
        time_info = get_current_time()
        await update.message.reply_text(time_info, parse_mode='HTML')
        
        # Log to database
        log_message(user.id, "private", question, time_info, "time_api", 0)
        update_user_stats(user.id)
        return
    
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
/prompt [text] - Change system prompt
/cleardb - Clear all data (⚠️ DANGER)

<b>Info:</b>
/owner - Show this help
"""
    
    await update.message.reply_text(owner_commands, parse_mode='HTML')

async def bfb_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /bfb command - Ban/Forbid user"""
    user = update.effective_user
    if user.id != OWNER_ID and not is_admin(user.id):
        await update.message.reply_text("❌ Admin access required.")
        return
    
    if not context.args:
        await update.message.reply_text("Usage: <code>/bfb [user_id] [reason]</code>\nExample: <code>/bfb 123456789 Spamming</code>", parse_mode='HTML')
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
            
            # Log to channel
            log_msg = f"""🔓 <b>User Unbanned</b>

👤 <b>Target:</b> {target_user['first_name']} (@{target_user['username']})
🆔 <b>ID:</b> <code>{target_id}</code>
👮 <b>By:</b> {user.first_name} (@{user.username})
🆔 <b>Moderator ID:</b> <code>{user.id}</code>
📅 <b>Time:</b> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
"""
            await log_to_channel(context, log_msg)
        else:
            ban_user(target_id, user.id, reason)
            await update.message.reply_text(f"✅ User {target_id} has been banned.\nReason: {reason}")
            
            # Log to channel
            log_msg = f"""🔒 <b>User Banned</b>

👤 <b>Target:</b> {target_user['first_name']} (@{target_user['username']})
🆔 <b>ID:</b> <code>{target_id}</code>
👮 <b>By:</b> {user.first_name} (@{user.username})
🆔 <b>Moderator ID:</b> <code>{user.id}</code>
📝 <b>Reason:</b> {reason}
📅 <b>Time:</b> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
"""
            await log_to_channel(context, log_msg)
            
    except ValueError:
        await update.message.reply_text("❌ Invalid user ID.")

async def pro_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /pro command - Promote user to admin"""
    user = update.effective_user
    if user.id != OWNER_ID:
        await update.message.reply_text("❌ Owner access required.")
        return
    
    if not context.args:
        await update.message.reply_text("Usage: <code>/pro [user_id]</code>\nExample: <code>/pro 123456789</code>", parse_mode='HTML')
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
        
        # Log to channel
        log_msg = f"""⬆️ <b>User Promoted to Admin</b>

👤 <b>New Admin:</b> {target_user['first_name']} (@{target_user['username']})
🆔 <b>ID:</b> <code>{target_id}</code>
👑 <b>Promoted by:</b> {user.first_name} (@{user.username})
🆔 <b>Owner ID:</b> <code>{user.id}</code>
📅 <b>Time:</b> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
👥 <b>Total Admins:</b> {len(get_all_admins()) + 1}
"""
        await log_to_channel(context, log_msg)
        
    except ValueError:
        await update.message.reply_text("❌ Invalid user ID.")

async def broadcast_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /broadcast command"""
    user = update.effective_user
    if user.id != OWNER_ID and not is_admin(user.id):
        await update.message.reply_text("❌ Admin access required.")
        return
    
    if not context.args:
        await update.message.reply_text("Usage: <code>/broadcast [message]</code>", parse_mode='HTML')
        return
    
    message = " ".join(context.args)
    users = get_all_users()
    
    broadcast_msg = f"""📢 <b>Broadcast from Tempest Creed</b>

{message}

<i>This is an automated message from the system.</i>
"""
    
    sent = 0
    failed = 0
    
    status_msg = await update.message.reply_text(f"📡 Starting broadcast to {len(users)} users...")
    
    for user_data in users:
        user_id = user_data[0]
        if user_id == user.id or is_banned(user_id):
            continue
        
        try:
            await context.bot.send_message(
                chat_id=user_id,
                text=broadcast_msg,
                parse_mode='HTML'
            )
            sent += 1
            await asyncio.sleep(0.1)  # Rate limiting
        except:
            failed += 1
    
    result_msg = f"""✅ <b>Broadcast Completed</b>

📤 <b>Successfully sent:</b> {sent}
❌ <b>Failed:</b> {failed}
👥 <b>Total recipients:</b> {len(users)}
📅 <b>Time:</b> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
"""
    
    await status_msg.edit_text(result_msg, parse_mode='HTML')
    
    # Log to channel
    log_msg = f"""📢 <b>Broadcast Sent</b>

📝 <b>Message:</b> {message[:100]}...
👤 <b>Sent by:</b> {user.first_name} (@{user.username})
🆔 <b>Sender ID:</b> <code>{user.id}</code>
📤 <b>Successful:</b> {sent}
❌ <b>Failed:</b> {failed}
📅 <b>Time:</b> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
"""
    await log_to_channel(context, log_msg)

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
    
    admin_list = f"""👑 <b>ADMINISTRATORS LIST</b>

<b>• Owner:</b> <code>{OWNER_ID}</code>
<b>• Total Admins:</b> {len(admins)}
"""
    
    if admins:
        admin_list += "\n<b>Admin List:</b>\n"
        for admin in admins:
            user_id = admin[0]
            username = admin[1] or "N/A"
            promoted_by = admin[3]
            promoted_at = admin[4]
            
            admin_list += f"\n<b>ID:</b> <code>{user_id}</code>\n"
            admin_list += f"<b>Username:</b> @{username}\n"
            admin_list += f"<b>Promoted by:</b> <code>{promoted_by}</code>\n"
            admin_list += f"<b>Promoted at:</b> {promoted_at}\n"
    else:
        admin_list += "\nNo additional admins (only owner)."
    
    await update.message.reply_text(admin_list, parse_mode='HTML')

async def demote_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /demote command - Demote admin"""
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
        
        target_user = get_user(target_id)
        demote_admin(target_id)
        await update.message.reply_text(f"✅ User {target_id} has been demoted to user.")
        
        # Log to channel
        log_msg = f"""⬇️ <b>Admin Demoted</b>

👤 <b>Demoted User:</b> {target_user['first_name']} (@{target_user['username']})
🆔 <b>ID:</b> <code>{target_id}</code>
👑 <b>Demoted by:</b> {user.first_name} (@{user.username})
🆔 <b>Owner ID:</b> <code>{user.id}</code>
📅 <b>Time:</b> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
👥 <b>Remaining Admins:</b> {len(get_all_admins())}
"""
        await log_to_channel(context, log_msg)
        
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
    
    # Check for weather queries
    if "weather" in prompt.lower():
        if "in" in prompt.lower():
            try:
                parts = prompt.lower().split("in")
                if len(parts) > 1:
                    city = parts[1].strip()
                    weather = await get_current_weather(city)
                    await update.message.reply_text(weather, parse_mode='HTML')
                    
                    # Log to database
                    log_message(user.id, chat_type, prompt, weather, "weather_api", 0)
                    update_user_stats(user.id)
                    return
            except Exception as e:
                logger.error(f"Weather query error: {e}")
    
    # Check for time/date queries
    if any(word in prompt.lower() for word in ["time", "date", "today", "now", "current time"]):
        time_info = get_current_time()
        await update.message.reply_text(time_info, parse_mode='HTML')
        
        # Log to database
        log_message(user.id, chat_type, prompt, time_info, "time_api", 0)
        update_user_stats(user.id)
        return
    
    # Get AI response
    response = await ask_ollama(prompt)
    
    # Update stats and log
    update_user_stats(user.id)
    log_message(user.id, chat_type, prompt, response, DEFAULT_MODEL, len(response.split()))
    
    # Send response
    await update.message.reply_text(response)

# ======================
# ERROR HANDLER
# ======================
async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle errors"""
    logger.error(f"Update {update} caused error {context.error}")
    
    try:
        error_msg = f"""⚠️ <b>Bot Error Occurred</b>

🔄 <b>Update:</b> {update.update_id if update else 'N/A'}
❌ <b>Error:</b> {context.error}
📅 <b>Time:</b> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
"""
        await log_to_channel(context, error_msg)
    except:
        pass

# ======================
# MAIN FUNCTION
# ======================
def main():
    """Start the bot"""
    # Create application
    application = Application.builder().token(BOT_TOKEN).build()
    
    # Add error handler
    application.add_error_handler(error_handler)
    
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
    
    # Send startup message to log channel
    async def send_startup_message():
        try:
            app = Application.builder().token(BOT_TOKEN).build()
            await app.initialize()
            
            startup_msg = f"""🚀 <b>Tempest AI Started Successfully</b>

🤖 <b>Bot:</b> Tempest AI
👑 <b>Owner:</b> <code>{OWNER_ID}</code>
🌐 <b>Ollama URL:</b> <code>{OLLAMA_URL}</code>
🧠 <b>Default Model:</b> {DEFAULT_MODEL}
🌤️ <b>Weather API:</b> {'✅ Configured' if WEATHER_API_KEY else '❌ Not configured'}
📅 <b>Startup Time:</b> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
"""
            await app.bot.send_message(
                chat_id=LOG_CHANNEL,
                text=startup_msg,
                parse_mode='HTML'
            )
            await app.shutdown()
        except Exception as e:
            logger.error(f"Failed to send startup message: {e}")
    
    # Start the bot
    print("🌪️ Tempest AI is starting...")
    print(f"🤖 Bot Token: {BOT_TOKEN[:15]}...")
    print(f"👑 Owner ID: {OWNER_ID}")
    print(f"🧠 Default Model: {DEFAULT_MODEL}")
    print(f"🌐 Ollama URL: {OLLAMA_URL}")
    print(f"🌤️ Weather API: {'✅ Configured' if WEATHER_API_KEY else '❌ Not configured'}")
    print(f"📺 Log Channel: {LOG_CHANNEL}")
    print(f"🖼️ Welcome Pic: {WELCOME_PIC}")
    print("🚀 Bot is now running...")
    
    # Run startup message
    asyncio.run(send_startup_message())
    
    # Start polling
    application.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)

if __name__ == '__main__':
    main()
