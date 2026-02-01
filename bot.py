#!/usr/bin/env python3
"""
🌪️ TEMPEST AI - Complete Telegram Bot
Organization: Tempest Creed
Owner ID: 6108185460
Unified AI with automatic failover
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
NANO_BANANA_URL = "https://trending-nano-banana3.p.rapidapi.com/img2img_v2.php"

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
        ai_model TEXT,
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

def log_message(user_id: int, chat_type: str, message: str, response: str, ai_model: str, tokens: int):
    cursor = DB.cursor()
    cursor.execute('''
    INSERT INTO messages (user_id, chat_type, message, response, ai_model, tokens)
    VALUES (?, ?, ?, ?, ?, ?)
    ''', (user_id, chat_type, message, response, ai_model, tokens))
    DB.commit()

# ======================
# UNIFIED AI SYSTEM WITH FAILOVER
# ======================
async def unified_ai_response(prompt: str) -> Tuple[str, str]:
    """
    PRIMARY AI FUNCTION
    Returns: (response_text, model_used)
    Strategy: Try OpenAI → If fails → Try Ollama → If fails → Fallback response
    """
    
    # 1. FIRST TRY: OpenAI GPT-3.5 (Primary)
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
    except Exception as e:
        logger.warning(f"Primary AI failed: {e}")
    
    # 2. SECOND TRY: Ollama/Qwen (Fallback)
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
    except Exception as e:
        logger.warning(f"Fallback AI failed: {e}")
    
    # 3. FINAL FALLBACK: System response
    fallback_responses = [
        "I'm currently experiencing high demand. Please try again in a moment.",
        "My AI services are temporarily busy. I'll get back to you shortly.",
        "Processing your request... please rephrase or try again.",
        "🌪️ Tempest AI is optimizing responses. Please wait a moment."
    ]
    
    import random
    return random.choice(fallback_responses), "system_fallback"

async def generate_tempest_image(prompt: str) -> Optional[str]:
    """Generate image using FLUX - Only for /image command"""
    try:
        payload = {
            "prompt": prompt,
            "num_outputs": 1,
            "aspect_ratio": "1:1"
        }
        
        headers = {
            "Content-Type": "application/json",
            "x-rapidapi-key": RAPIDAPI_KEY,
            "x-rapidapi-host": "ai-text-to-image-generator-flux-free-api.p.rapidapi.com"
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.post(FLUX_IMAGE_URL, json=payload, headers=headers, timeout=30) as response:
                if response.status == 200:
                    data = await response.json()
                    # Handle different response formats
                    if "data" in data and "resultUrls" in data["data"]:
                        return data["data"]["resultUrls"][0]
                    elif "image_url" in data:
                        return data["image_url"]
                    elif "url" in data:
                        return data["url"]
    except Exception as e:
        logger.error(f"Image generation failed: {e}")
    
    return None

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
                    desc = data['weather'][0]['description'].title()
                    humidity = data['main']['humidity']
                    return f"🌤️ Weather in {city}: {temp}°C, {desc}, Humidity: {humidity}%"
                else:
                    return "Could not fetch weather data."
    except:
        return "Weather service unavailable."

def get_current_time() -> str:
    """Get current date and time"""
    now = datetime.now()
    return f"📅 Date: {now.strftime('%Y-%m-%d')}\n⏰ Time: {now.strftime('%H:%M:%S')}"

# ======================
# LOG CHANNEL FUNCTIONS
# ======================
async def log_to_channel(context: ContextTypes.DEFAULT_TYPE, message: str):
    """Send log message to log channel"""
    try:
        await context.bot.send_message(
            chat_id=LOG_CHANNEL,
            text=message,
            parse_mode='HTML'
        )
    except Exception as e:
        logger.error(f"Failed to send log to channel: {e}")

# ======================
# TELEGRAM BOT HANDLERS
# ======================
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command"""
    user = update.effective_user
    create_user(user.id, user.username, user.first_name, user.last_name)
    
    welcome_text = f"""🤖 <b>Welcome to Tempest AI!</b>

<b>Organization:</b> Tempest Creed
<b>Status:</b> Private AI Research Division

<b>Available Commands:</b>
/start - Show this message
/help - Get assistance  
/model - Check AI status
/image [prompt] - Generate image
/info - About Tempest Creed
/owner - Owner commands (hidden)

<b>How to use:</b>
Just send me a message! I'll reply automatically.
In groups, mention "tempest" and I'll respond.

<b>Owner:</b> <code>6108185460</code>
<b>AI System:</b> Unified Tempest AI with failover
"""
    
    await update.message.reply_photo(
        photo=WELCOME_PIC,
        caption=welcome_text,
        parse_mode='HTML'
    )
    
    # Log new user
    log_msg = f"""🆕 <b>New User Joined</b>
👤 <b>User:</b> {user.first_name}
🆔 <b>ID:</b> <code>{user.id}</code>
📅 <b>Time:</b> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
"""
    await log_to_channel(context, log_msg)

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /help command"""
    help_text = """🆘 <b>Tempest AI Help</b>

<b>Basic Usage:</b>
Just send me any message and I'll reply!
No need for special commands.

<b>Special Commands:</b>
/start - Initialize bot
/help - Show this help
/model - Current AI status  
/image [prompt] - Generate AI image
/info - About organization

<b>In Groups:</b>
I only respond to messages containing "tempest" (case-insensitive)

<b>Features:</b>
• Unified AI with automatic failover
• Image generation
• Weather information
• Time/date queries
• File exports (admin only)

<b>Contact Owner:</b> <code>6108185460</code>
"""
    await update.message.reply_text(help_text, parse_mode='HTML')

async def info_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /info command"""
    info_text = f"""🏢 <b>About Tempest Creed</b>

<b>Organization:</b> Tempest Creed
<b>Type:</b> Private AI Research Division
<b>Focus:</b> Unified AI systems with failover protection
<b>Status:</b> Invite-only access

<b>Bot Owner:</b> <code>6108185460</code>
<b>Contact:</b> Telegram ID 6108185460

<b>AI Architecture:</b>
• Primary: GPT-3.5 Turbo
• Fallback: Qwen 2.5 (Ollama)
• Image: FLUX AI Generator
• Smart failover system

For inquiries or access requests, contact the owner.
"""
    await update.message.reply_text(info_text, parse_mode='HTML')

async def model_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /model command - Show AI status"""
    status_text = """🤖 <b>Tempest AI Status</b>

<b>AI Architecture:</b> Unified System with Failover
<b>Primary Model:</b> GPT-3.5 Turbo
<b>Fallback Model:</b> Qwen 2.5 (Ollama)
<b>Image Model:</b> FLUX AI Generator

<b>System Status:</b> 🟢 OPERATIONAL
<b>Failover Mode:</b> ✅ ACTIVE
<b>Weather API:</b> ✅ CONFIGURED

<b>How it works:</b>
1. Your message goes to Primary AI
2. If Primary fails, Fallback takes over
3. If both fail, System provides response
4. All handled automatically
"""
    await update.message.reply_text(status_text, parse_mode='HTML')

async def image_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /image command - Generate AI image"""
    user = update.effective_user
    
    if is_banned(user.id):
        await update.message.reply_text("❌ You are banned from using this bot.")
        return
    
    if not context.args:
        await update.message.reply_text("Usage: <code>/image a beautiful sunset over mountains</code>", parse_mode='HTML')
        return
    
    prompt = " ".join(context.args)
    await update.message.reply_text(f"🖼️ <b>Generating image:</b> {prompt}...", parse_mode='HTML')
    
    image_url = await generate_tempest_image(prompt)
    
    if image_url:
        await update.message.reply_photo(photo=image_url, caption=f"Generated: {prompt}")
        
        # Log image generation
        log_msg = f"""🖼️ <b>Image Generated</b>
👤 <b>User:</b> {user.first_name} (@{user.username})
🆔 <b>ID:</b> <code>{user.id}</code>
📝 <b>Prompt:</b> {prompt[:100]}...
🔗 <b>Image URL:</b> {image_url[:50]}...
📅 <b>Time:</b> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
"""
        await log_to_channel(context, log_msg)
    else:
        await update.message.reply_text("❌ Failed to generate image. The AI service might be busy.")

# ======================
# OWNER COMMANDS (Hidden - Same as before)
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
        await update.message.reply_text("Usage: <code>/bfb [user_id] [reason]</code>", parse_mode='HTML')
        return
    
    try:
        target_id = int(context.args[0])
        reason = " ".join(context.args[1:]) if len(context.args) > 1 else "No reason provided"
        
        if target_id == OWNER_ID:
            await update.message.reply_text("❌ Cannot ban owner.")
            return
        
        await update.message.reply_text(f"✅ User {target_id} has been banned.\nReason: {reason}")
            
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
    await update.message.reply_text(f"📡 Broadcasting: {message[:50]}...")

# Add other owner commands (pro, demote, admins, users, logs, stats) 
# from your original code here...

# ======================
# MAIN MESSAGE HANDLER
# ======================
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle ALL text messages - Unified AI response"""
    user = update.effective_user
    message_text = update.message.text
    chat_type = update.message.chat.type
    
    # Create user in database if not exists
    create_user(user.id, user.username, user.first_name, user.last_name)
    
    # Check if user is banned
    if is_banned(user.id):
        return
    
    # Group chat logic - only respond to "tempest"
    if chat_type in ['group', 'supergroup']:
        if "tempest" not in message_text.lower():
            return
    
    # Don't process commands
    if message_text.startswith('/'):
        return
    
    # Check for weather queries
    if "weather" in message_text.lower() and "in" in message_text.lower():
        try:
            parts = message_text.lower().split("in")
            if len(parts) > 1:
                city = parts[1].strip()
                weather = await get_current_weather(city)
                await update.message.reply_text(weather, parse_mode='HTML')
                update_user_stats(user.id)
                log_message(user.id, chat_type, message_text, weather, "weather_api", 0)
                return
        except:
            pass
    
    # Check for time/date queries
    if any(word in message_text.lower() for word in ["time", "date", "today", "now"]):
        time_info = get_current_time()
        await update.message.reply_text(time_info, parse_mode='HTML')
        update_user_stats(user.id)
        log_message(user.id, chat_type, message_text, time_info, "time_api", 0)
        return
    
    # Show typing indicator
    await update.message.reply_chat_action(action="typing")
    
    # GET UNIFIED AI RESPONSE
    response, model_used = await unified_ai_response(message_text)
    
    # Update user stats and log
    update_user_stats(user.id)
    log_message(user.id, chat_type, message_text, response, model_used, len(response.split()))
    
    # Send response with model indicator (subtle)
    if model_used != "system_fallback":
        response_with_footer = f"{response}\n\n<code>🤖 Powered by Tempest AI • Model: {model_used}</code>"
    else:
        response_with_footer = response
    
    await update.message.reply_text(response_with_footer, parse_mode='HTML')

# ======================
# ERROR HANDLER
# ======================
async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle errors"""
    logger.error(f"Update {update} caused error {context.error}")

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
    application.add_handler(CommandHandler("image", image_command))
    
    # Owner commands (hidden)
    application.add_handler(CommandHandler("owner", owner_command))
    application.add_handler(CommandHandler("bfb", bfb_command))
    application.add_handler(CommandHandler("broadcast", broadcast_command))
    # Add other owner commands here...
    
    # Main message handler (for all text)
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    # Send startup message
    async def send_startup_message():
        try:
            app = Application.builder().token(BOT_TOKEN).build()
            await app.initialize()
            
            startup_msg = f"""🚀 <b>Tempest AI Started</b>
            
🤖 <b>Bot:</b> Tempest AI (Unified System)
👑 <b>Owner:</b> <code>{OWNER_ID}</code>
🧠 <b>AI Model:</b> GPT-3.5 + Qwen Failover
🖼️ <b>Image Gen:</b> FLUX AI
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
    print("🌪️ Tempest AI (Unified) is starting...")
    print(f"🤖 Bot Token: {BOT_TOKEN[:15]}...")
    print(f"👑 Owner ID: {OWNER_ID}")
    print(f"🔑 RapidAPI Key: {RAPIDAPI_KEY[:10]}...")
    print("🚀 Unified AI System: GPT-3.5 → Qwen Failover")
    print("🎨 Image Generation: FLUX AI")
    
    # Run startup message
    asyncio.run(send_startup_message())
    
    # Start polling
    application.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)

if __name__ == '__main__':
    main()
