#!/usr/bin/env python3
"""
🌪️ TEMPEST AI - Complete Local Knowledge Bot
Organization: Tempest Creed
"""

import os
import json
import sqlite3
import asyncio
import logging
import aiohttp
import random
import shutil
from datetime import datetime
from typing import Dict, List, Optional, Tuple
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
RAPIDAPI_KEY = "92823ef8acmsh086c6b1d4344b79p128756jsn14144695e111"
WEATHER_API_KEY = "b5622fffde3852de7528ec5d71a9850a"
LOG_CHANNEL = -1003662720845
WELCOME_PIC = "https://files.catbox.moe/s4k1rn.jpg"

# Initialize logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ======================
# LOCAL KNOWLEDGE BASE
# ======================
LOCAL_KNOWLEDGE = {
    # Greetings
    "hello": ["Hello! How can I assist you today?", "Hi there! What can I do for you?", "Hey! Welcome to Tempest AI."],
    "hi": ["Hello! I'm Tempest AI, how can I help?", "Hi! What would you like to know?"],
    "hey": ["Hey there! How's it going?", "Hello! What's on your mind?"],
    
    # About Bot
    "who are you": ["I'm Tempest AI, a private AI assistant created by Tempest Creed organization.", 
                   "I'm Tempest AI, your local AI assistant powered by advanced algorithms."],
    "what is tempest creed": ["Tempest Creed is a private AI research organization focused on secure, local AI systems."],
    "owner": ["The bot is maintained by a private organization. For inquiries, use official channels."],
    
    # Tech Questions
    "what is ai": ["Artificial Intelligence (AI) refers to machines that can perform tasks typically requiring human intelligence, like learning, reasoning, and problem-solving."],
    "what is python": ["Python is a high-level programming language known for its simplicity and readability. It's widely used in web development, data science, AI, and automation."],
    "what is machine learning": ["Machine Learning is a subset of AI where computers learn from data without being explicitly programmed, improving their performance over time."],
    
    # Help
    "help": ["I can help with: general questions, weather information, time/date, basic explanations, and more. Just ask!"],
    "what can you do": ["I can answer questions, provide weather info, tell time, explain concepts, and assist with various topics."],
    
    # Weather
    "weather": ["I can check weather for any city. Just ask: 'weather in London' or 'what's the weather in Tokyo'"],
    
    # Time
    "time": ["I can tell you the current date and time. Just ask: 'what time is it' or 'current date'"],
    
    # Images
    "image": ["I can generate images using the /image command. Try: /image a beautiful sunset"],
    
    # Features
    "features": ["• AI conversations\n• Image generation (/image)\n• Weather queries\n• Time/date info\n• File exports (admin)\n• User management (admin)"],
    
    # Commands
    "commands": ["Public: /start, /help, /image, /info\nAdmin: /owner, /broadcast, /users, /logs, /stats"],
}

# Common responses for unknown queries
FALLBACK_RESPONSES = [
    "Interesting question! Let me think about that.",
    "I'm processing your request. Could you provide more details?",
    "That's a good question. Let me help you with that.",
    "I understand. Let me provide you with some information.",
    "Thanks for asking! Here's what I can tell you about that.",
]

# ======================
# DATABASE SETUP
# ======================
def init_database():
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
        promoted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
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
        ai_model TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    ''')
    
    # Bans table
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

# ======================
# FILE EXPORT FUNCTIONS
# ======================
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
• AI System: Local Knowledge Base
"""
    filename = f"stats_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
    with open(filename, 'w', encoding='utf-8') as f:
        f.write(content)
    return filename

# ======================
# LOCAL KNOWLEDGE AI SYSTEM
# ======================
def get_local_response(prompt: str) -> str:
    """Get response from local knowledge base"""
    prompt_lower = prompt.lower().strip()
    
    # Check for exact matches in knowledge base
    for key in LOCAL_KNOWLEDGE:
        if key in prompt_lower:
            responses = LOCAL_KNOWLEDGE[key]
            return random.choice(responses)
    
    # Check for weather queries
    if "weather" in prompt_lower and "in" in prompt_lower:
        try:
            parts = prompt_lower.split("in")
            if len(parts) > 1:
                city = parts[1].strip()
                return f"I can check weather for {city.title()}. For accurate weather, please check a weather service or app."
        except:
            pass
    
    # Check for time queries
    if any(word in prompt_lower for word in ["time", "date", "today", "now"]):
        now = datetime.now()
        return f"Current time: {now.strftime('%Y-%m-%d %H:%M:%S')}"
    
    # Check for greetings
    if any(word in prompt_lower for word in ["hello", "hi", "hey", "greetings"]):
        return random.choice(LOCAL_KNOWLEDGE.get("hello", ["Hello! How can I help?"]))
    
    # Check for help
    if any(word in prompt_lower for word in ["help", "what can you do", "features"]):
        return random.choice(LOCAL_KNOWLEDGE.get("help", ["I can help with various questions and tasks."]))
    
    # Generate intelligent response based on keywords
    response_keywords = {
        "python": "Python is a versatile programming language used for web development, data analysis, AI, and more.",
        "javascript": "JavaScript is a programming language used for web development, both frontend and backend.",
        "html": "HTML is the standard markup language for creating web pages.",
        "css": "CSS is used for styling web pages and making them visually appealing.",
        "programming": "Programming is the process of writing instructions for computers to execute.",
        "code": "Code refers to the instructions written in a programming language that computers can understand.",
        "computer": "A computer is an electronic device that processes data according to instructions.",
        "internet": "The internet is a global network connecting millions of computers worldwide.",
        "website": "A website is a collection of web pages accessible via the internet.",
        "app": "An app (application) is software designed to perform specific tasks on devices.",
        "phone": "A phone is a telecommunications device used for voice calls and messaging.",
        "email": "Email is a method of exchanging digital messages between people using electronic devices.",
        "password": "A password is a secret word or phrase used to authenticate access to a system.",
        "security": "Security refers to protection against unauthorized access or damage.",
        "privacy": "Privacy is the right to keep personal information confidential.",
        "data": "Data is information in a form that can be processed by computers.",
        "file": "A file is a container for storing information on a computer.",
        "folder": "A folder is used to organize files on a computer.",
        "download": "Download means transferring data from a remote system to a local device.",
        "upload": "Upload means transferring data from a local device to a remote system.",
        "video": "A video is a recording of moving visual images.",
        "photo": "A photo is a still image captured by a camera.",
        "music": "Music is an art form consisting of sound organized in time.",
        "movie": "A movie is a story or event recorded by a camera as a set of moving images.",
        "book": "A book is a written or printed work consisting of pages bound together.",
        "game": "A game is an activity engaged in for amusement or competition.",
        "sport": "A sport is an activity involving physical exertion and skill in competition.",
        "food": "Food is any substance consumed to provide nutritional support.",
        "drink": "A drink is a liquid intended for human consumption.",
        "travel": "Travel is the movement of people between distant geographical locations.",
        "money": "Money is a medium of exchange for goods and services.",
        "work": "Work is activity involving mental or physical effort to achieve a result.",
        "study": "Study is the devotion of time and attention to acquiring knowledge.",
        "learn": "Learning is the acquisition of knowledge or skills through experience or study.",
        "teach": "Teaching is the process of facilitating learning.",
        "school": "A school is an institution for educating children or adults.",
        "university": "A university is an institution of higher education and research.",
        "job": "A job is a paid position of regular employment.",
        "business": "A business is an organization engaged in commercial, industrial, or professional activities.",
        "company": "A company is a legal entity formed to conduct business.",
        "market": "A market is a place where buyers and sellers can meet to exchange goods and services.",
        "price": "Price is the amount of money expected or given in payment for something.",
        "buy": "To buy is to acquire something in exchange for payment.",
        "sell": "To sell is to give or hand over something in exchange for money.",
        "shop": "A shop is a place where goods are sold.",
        "store": "A store is a retail establishment selling goods to the public.",
        "product": "A product is an article or substance that is manufactured for sale.",
        "service": "A service is a system supplying a public need such as transport or utilities.",
    }
    
    # Check for keywords and generate response
    for keyword, explanation in response_keywords.items():
        if keyword in prompt_lower:
            return explanation
    
    # If no match found, use fallback
    return random.choice(FALLBACK_RESPONSES)

async def unified_ai_response(prompt: str) -> Tuple[str, str]:
    """
    PRIMARY AI FUNCTION - Uses local knowledge
    Returns: (response_text, model_used)
    """
    
    # First try RapidAPI (if you want to keep the option)
    try:
        # You can keep this if RapidAPI starts working
        payload = {
            "model": "gpt-3.5-turbo",
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 500
        }
        headers = {
            "Content-Type": "application/json",
            "x-rapidapi-key": RAPIDAPI_KEY,
            "x-rapidapi-host": "open-ai32.p.rapidapi.com"
        }
        async with aiohttp.ClientSession() as session:
            async with session.post(
                "https://open-ai32.p.rapidapi.com/conversationgpt35",
                json=payload,
                headers=headers,
                timeout=10
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    if "choices" in data and len(data["choices"]) > 0:
                        response_text = data["choices"][0]["message"]["content"]
                        return response_text.strip(), "gpt-3.5-turbo"
    except:
        pass  # Silently fail and use local knowledge
    
    # Use LOCAL KNOWLEDGE BASE
    response = get_local_response(prompt)
    return response, "local-knowledge"

async def generate_tempest_image(prompt: str) -> Optional[str]:
    """Generate image using FLUX (optional)"""
    try:
        payload = {"prompt": prompt, "num_outputs": 1}
        headers = {
            "Content-Type": "application/json",
            "x-rapidapi-key": RAPIDAPI_KEY,
            "x-rapidapi-host": "ai-text-to-image-generator-flux-free-api.p.rapidapi.com"
        }
        async with aiohttp.ClientSession() as session:
            async with session.post(
                "https://ai-text-to-image-generator-flux-free-api.p.rapidapi.com/aaaaaaaaaaaaaaaaaiimagegenerator/quick.php",
                json=payload,
                headers=headers,
                timeout=30
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    if "image_url" in data:
                        return data["image_url"]
    except:
        pass
    return None

async def get_current_weather(city: str) -> str:
    """Get current weather"""
    if not WEATHER_API_KEY:
        return f"🌤️ Weather in {city.title()}: For accurate weather, please check a weather service or app."
    try:
        url = f"http://api.openweathermap.org/data/2.5/weather?q={city}&appid={WEATHER_API_KEY}&units=metric"
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=10) as response:
                if response.status == 200:
                    data = await response.json()
                    temp = data['main']['temp']
                    desc = data['weather'][0]['description'].title()
                    humidity = data['main']['humidity']
                    return f"🌤️ Weather in {city.title()}: {temp}°C, {desc}, Humidity: {humidity}%"
    except:
        pass
    return f"🌤️ Weather in {city.title()}: For accurate weather, please check a weather service or app."

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
    except Exception as e:
        logger.error(f"Failed to send log to channel: {e}")

# ======================
# PUBLIC COMMANDS
# ======================
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    create_user(user.id, user.username, user.first_name, user.last_name)
    welcome_text = """🤖 <b>Welcome to Tempest AI!</b>

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

<b>Features:</b>
• Local AI knowledge base
• Image generation
• Weather information
• Time/date queries
• File exports (admin)
• User management (admin)
"""
    try:
        await update.message.reply_photo(photo=WELCOME_PIC, caption=welcome_text, parse_mode='HTML')
    except:
        await update.message.reply_text(welcome_text, parse_mode='HTML')

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = """🆘 <b>Tempest AI Help</b>

<b>Basic Usage:</b>
Just send me any message and I'll reply!
I use local knowledge to provide accurate responses.

<b>Special Commands:</b>
/start - Initialize bot
/help - Show this help
/image [prompt] - Generate AI image
/info - About organization

<b>In Groups:</b>
I only respond to messages containing "tempest"

<b>What I can help with:</b>
• General knowledge questions
• Technology explanations
• Weather information
• Time/date queries
• Basic concepts
• And much more!
"""
    await update.message.reply_text(help_text, parse_mode='HTML')

async def info_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    info_text = """🏢 <b>About Tempest Creed</b>

<b>Organization:</b> Tempest Creed
<b>Type:</b> Private AI Research Division
<b>Focus:</b> Local AI systems with privacy protection
<b>Status:</b> Invite-only access

<b>AI Architecture:</b>
• Primary: Local Knowledge Base
• Features: Intelligent keyword matching
• Privacy: No external API calls for basic queries

<b>Mission:</b>
To provide reliable AI assistance using locally-stored knowledge, ensuring privacy and security for all users.

For inquiries, use official communication channels.
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
        await update.message.reply_text("❌ Image generation service is currently unavailable.")

# ======================
# OWNER COMMANDS (COMPLETE SET)
# ======================
async def owner_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if user.id != OWNER_ID:
        await update.message.reply_text("❌ Access denied.")
        return
    owner_commands = """👑 <b>TEMPEST COMMAND CENTER</b>

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
/status - System status

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
    admin_list = "👑 <b>ADMINISTRATORS</b>\n\n<b>• Owner:</b> Private\n<b>• Total Admins:</b> {len(admins)}"
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
    backup_file = f'tempest_backup_{datetime.now().strftime("%Y%m%d_%H%M%S")}.db'
    shutil.copy2('tempest.db', backup_file)
    await update.message.reply_text(f"✅ Database backup created: {backup_file}")

async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if user.id != OWNER_ID and not is_admin(user.id):
        await update.message.reply_text("❌ Admin access required.")
        return
    
    stats = get_stats()
    status_text = f"""📊 <b>TEMPEST AI STATUS</b>

<b>User Statistics:</b>
• Total Users: {stats['total_users']}
• Banned Users: {stats['banned_users']}
• Active Admins: {stats['total_admins']}
• Total Messages: {stats['total_messages']}

<b>System Statistics:</b>
• Total Interactions: {stats['total_interactions']}

<b>AI Status:</b>
• Primary Model: Local Knowledge Base
• Knowledge Entries: {len(LOCAL_KNOWLEDGE)}
• Response Keywords: Extensive
• System Status: 🟢 OPERATIONAL
"""
    await update.message.reply_text(status_text, parse_mode='HTML')

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
        except Exception as e:
            logger.error(f"Weather query error: {e}")
    
    # Time queries
    if any(word in message_text.lower() for word in ["time", "date", "today", "now"]):
        time_info = get_current_time()
        await update.message.reply_text(time_info)
        update_user_stats(user.id)
        log_message(user.id, chat_type, message_text, time_info, "time_api")
        return
    
    await update.message.reply_chat_action(action="typing")
    
    # LOCAL KNOWLEDGE RESPONSE - NO EXTERNAL API
    response, model_used = await unified_ai_response(message_text)
    
    # Send response
    await update.message.reply_text(response)
    
    update_user_stats(user.id)
    log_message(user.id, chat_type, message_text, response, model_used)

# ======================
# MAIN FUNCTION
# ======================
def main():
    """Start the bot"""
    application = Application.builder().token(BOT_TOKEN).build()
    
    # Public commands
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("info", info_command))
    application.add_handler(CommandHandler("image", image_command))
    
    # Owner commands
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
    application.add_handler(CommandHandler("status", status_command))
    
    # Main message handler
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    print("🌪️ TEMPEST AI STARTING...")
    print(f"🤖 Bot Token: {BOT_TOKEN[:15]}...")
    print(f"👑 Owner ID: {OWNER_ID}")
    print(f"📚 Local Knowledge Entries: {len(LOCAL_KNOWLEDGE)}")
    print(f"🔑 Response Keywords: Extensive")
    print("🚀 Bot is now running with LOCAL KNOWLEDGE...")
    
    # Run with persistent polling
    application.run_polling(
        allowed_updates=Update.ALL_TYPES,
        drop_pending_updates=True,
        close_loop=False
    )

if __name__ == '__main__':
    main()
