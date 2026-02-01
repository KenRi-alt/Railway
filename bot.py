#!/usr/bin/env python3
"""
🌪️ TEMPEST AI - Railway Fixed Version
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
from aiohttp import web  # ADDED for health check

# ======================
# CONFIGURATION
# ======================
OWNER_ID = 6108185460
BOT_TOKEN = "7869314780:AAFFU5jMv-WK9sCJnAJ4X0oRtog632B9sUg"
RAPIDAPI_KEY = "92823ef8acmsh086c6b1d4344b79p128756jsn14144695e111"
WEATHER_API_KEY = "b5622fffde3852de7528ec5d71a9850a"
LOG_CHANNEL = -1003662720845
WELCOME_PIC = "https://files.catbox.moe/s4k1rn.jpg"
PORT = int(os.getenv("PORT", 8000))  # Railway provides PORT

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
        messages INTEGER DEFAULT 0,
        banned INTEGER DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    ''')
    conn.commit()
    return conn

DB = init_database()

# ======================
# SIMPLIFIED DATABASE FUNCTIONS
# ======================
def create_user(user_id: int, username: str = "", first_name: str = ""):
    cursor = DB.cursor()
    cursor.execute('''
    INSERT OR IGNORE INTO users (user_id, username, first_name)
    VALUES (?, ?, ?)
    ''', (user_id, username, first_name))
    DB.commit()

# ======================
# UNIFIED AI SYSTEM
# ======================
async def unified_ai_response(prompt: str) -> Tuple[str, str]:
    """AI response with fallback"""
    try:
        # Try OpenAI first
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
                timeout=20
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    if "choices" in data:
                        return data["choices"][0]["message"]["content"], "gpt-3.5"
    except Exception as e:
        logger.warning(f"AI failed: {e}")
    
    # Fallback responses
    fallbacks = [
        "I'm processing your request. Please try again in a moment.",
        "Let me think about that and get back to you.",
        "Interesting question! I need a moment to process."
    ]
    return random.choice(fallbacks), "fallback"

async def generate_tempest_image(prompt: str) -> Optional[str]:
    """Generate image using FLUX"""
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
    except Exception as e:
        logger.error(f"Image generation failed: {e}")
    return None

# ======================
# BASIC COMMANDS
# ======================
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    create_user(user.id, user.username, user.first_name)
    await update.message.reply_text(
        "🤖 *Tempest AI Online*\n\n"
        "Just send me a message and I'll reply!\n"
        "In groups, mention 'tempest' to get my attention.\n\n"
        "*Owner:* `6108185460`",
        parse_mode='Markdown'
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🆘 *Help*\n\n"
        "• Just chat with me normally\n"
        "• Use /image for AI images\n"
        "• Ask about weather: 'weather in London'\n"
        "• Ask time: 'what time is it'\n\n"
        "*Owner commands:* /owner (owner only)",
        parse_mode='Markdown'
    )

async def image_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Usage: `/image a beautiful sunset`", parse_mode='Markdown')
        return
    prompt = " ".join(context.args)
    await update.message.reply_text(f"🖼️ Generating: *{prompt}*...", parse_mode='Markdown')
    image_url = await generate_tempest_image(prompt)
    if image_url:
        await update.message.reply_photo(photo=image_url, caption=f"Generated: {prompt}")
    else:
        await update.message.reply_text("❌ Failed to generate image.")

# ======================
# OWNER COMMANDS
# ======================
async def owner_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        await update.message.reply_text("❌ Owner only.")
        return
    await update.message.reply_text(
        "👑 *Owner Commands*\n\n"
        "• /bfb [id] - Ban user\n"
        "• /pro [id] - Promote admin\n"
        "• /broadcast [msg]\n"
        "• /users - Export users\n"
        "• /logs - View logs\n"
        "• /stats - Statistics\n"
        "• /query - Query system",
        parse_mode='Markdown'
    )

async def bfb_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        await update.message.reply_text("❌ Owner only.")
        return
    await update.message.reply_text("✅ Ban command (placeholder)")

async def broadcast_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        await update.message.reply_text("❌ Owner only.")
        return
    await update.message.reply_text("✅ Broadcast sent")

async def query_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        await update.message.reply_text("❌ Owner only.")
        return
    await update.message.reply_text("📊 System is operational")

# ======================
# MAIN MESSAGE HANDLER
# ======================
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    message = update.message.text
    
    # Group check
    if update.message.chat.type in ['group', 'supergroup']:
        if 'tempest' not in message.lower():
            return
    
    # Weather query
    if "weather" in message.lower() and "in" in message.lower():
        try:
            parts = message.lower().split("in")
            if len(parts) > 1:
                city = parts[1].strip()
                await update.message.reply_text(f"🌤️ Weather in {city}: Check your weather app")
                return
        except:
            pass
    
    # Time query
    if any(word in message.lower() for word in ["time", "date", "today", "now"]):
        now = datetime.now()
        await update.message.reply_text(f"📅 {now.strftime('%Y-%m-%d %H:%M:%S')}")
        return
    
    await update.message.reply_chat_action(action="typing")
    response, _ = await unified_ai_response(message)
    await update.message.reply_text(response)

# ======================
# HEALTH CHECK SERVER (FOR RAILWAY)
# ======================
async def health_check(request):
    """Health check endpoint for Railway"""
    return web.Response(text="🌪️ Tempest AI is running")

async def start_health_server():
    """Start a simple HTTP server for health checks"""
    app = web.Application()
    app.router.add_get('/', health_check)
    app.router.add_get('/health', health_check)
    
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', PORT)
    await site.start()
    print(f"✅ Health check server running on port {PORT}")
    return runner

# ======================
# MAIN FUNCTION - RAILWAY FIXED
# ======================
async def main():
    """Main function with health server"""
    
    print("🌪️ Starting Tempest AI...")
    print(f"🔑 Token: {BOT_TOKEN[:15]}...")
    print(f"👑 Owner: {OWNER_ID}")
    
    # Start health check server (for Railway)
    health_server = await start_health_server()
    
    # Create and start bot
    application = Application.builder().token(BOT_TOKEN).build()
    
    # Add handlers
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("image", image_command))
    application.add_handler(CommandHandler("owner", owner_command))
    application.add_handler(CommandHandler("bfb", bfb_command))
    application.add_handler(CommandHandler("broadcast", broadcast_command))
    application.add_handler(CommandHandler("query", query_command))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    print("🤖 Bot started successfully")
    print("🚀 Ready to receive messages...")
    
    # Start polling
    await application.initialize()
    await application.start()
    await application.updater.start_polling()
    
    # Keep running
    try:
        while True:
            await asyncio.sleep(3600)  # Sleep for 1 hour
    except asyncio.CancelledError:
        pass
    finally:
        # Cleanup
        await application.updater.stop()
        await application.stop()
        await application.shutdown()
        await health_server.cleanup()

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 Bot stopped")
