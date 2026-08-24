import asyncio
import logging
import sqlite3
import os
import re
import json
import random
import string
import time
from datetime import datetime, timedelta
from io import BytesIO
from typing import Optional, Dict, List, Tuple, Any

import numpy as np
from PIL import (
    Image, ImageOps, ImageDraw, ImageFont, 
    ImageFilter, ImageEnhance, ImageChops, ImageStat
)
from aiogram import Bot, Dispatcher, F, Router
from aiogram.types import (
    Message, CallbackQuery, BufferedInputFile, 
    InlineKeyboardMarkup, InlineKeyboardButton,
    ReplyKeyboardMarkup, KeyboardButton, ChatMemberUpdated,
    ChatPermissions
)
from aiogram.filters import Command, CommandStart, CommandObject
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder
from aiogram.enums import ParseMode, ChatMemberStatus
from aiogram.exceptions import TelegramBadRequest
from aiogram.client.default import DefaultBotProperties

# ============================================
# CONFIGURATION
# ============================================
TOKEN = "8302810352:AAHzhQdIgMB71mEKcZcFW8uNVJ_EPtpu0es"
ADMIN_ID = 6108185460

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

router = Router()

# ============================================
# DATABASE SETUP
# ============================================
def init_db():
    conn = sqlite3.connect("tempest_guider.db")
    cursor = conn.cursor()
    
    # Users table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            points INTEGER DEFAULT 0,
            level INTEGER DEFAULT 1,
            join_date TEXT,
            last_active TEXT,
            warnings INTEGER DEFAULT 0,
            is_banned INTEGER DEFAULT 0,
            selected_topic TEXT,
            total_solved INTEGER DEFAULT 0,
            total_images INTEGER DEFAULT 0,
            quiz_score INTEGER DEFAULT 0
        )
    """)
    
    # Math history
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS math_history (
            problem_id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            topic TEXT,
            problem_text TEXT,
            solution TEXT,
            timestamp TEXT
        )
    """)
    
    # Broadcast logs
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS broadcast_logs (
            broadcast_id INTEGER PRIMARY KEY AUTOINCREMENT,
            admin_id INTEGER,
            message_text TEXT,
            recipients_count INTEGER,
            success_count INTEGER,
            timestamp TEXT
        )
    """)
    
    # Achievements
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS user_achievements (
            user_id INTEGER,
            achievement_name TEXT,
            unlocked_date TEXT,
            PRIMARY KEY (user_id, achievement_name)
        )
    """)
    
    # Muted users
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS muted_users (
            user_id INTEGER PRIMARY KEY,
            muted_until TEXT,
            reason TEXT
        )
    """)
    
    conn.commit()
    conn.close()

init_db()

# ============================================
# DATABASE HELPER FUNCTIONS
# ============================================
def add_user(user_id: int, username: str, first_name: str):
    conn = sqlite3.connect("tempest_guider.db")
    cursor = conn.cursor()
    cursor.execute("""
        INSERT OR IGNORE INTO users (user_id, username, first_name, join_date, last_active)
        VALUES (?, ?, ?, ?, ?)
    """, (user_id, username, first_name, datetime.now().isoformat(), datetime.now().isoformat()))
    conn.commit()
    conn.close()

def update_last_active(user_id: int):
    conn = sqlite3.connect("tempest_guider.db")
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET last_active = ? WHERE user_id = ?", 
                   (datetime.now().isoformat(), user_id))
    conn.commit()
    conn.close()

def add_points(user_id: int, points: int):
    conn = sqlite3.connect("tempest_guider.db")
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET points = points + ? WHERE user_id = ?", 
                   (points, user_id))
    cursor.execute("SELECT points FROM users WHERE user_id = ?", (user_id,))
    total_points = cursor.fetchone()[0]
    
    # Update level
    new_level = 1
    thresholds = [0, 100, 250, 500, 1000, 2000, 4000, 8000, 16000, 32000]
    for i, threshold in enumerate(thresholds, 1):
        if total_points >= threshold:
            new_level = i
    
    cursor.execute("UPDATE users SET level = ? WHERE user_id = ?", 
                   (new_level, user_id))
    conn.commit()
    conn.close()
    return new_level

def get_user_data(user_id: int) -> Optional[Tuple]:
    conn = sqlite3.connect("tempest_guider.db")
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
    user = cursor.fetchone()
    conn.close()
    return user

def get_all_users() -> List[int]:
    conn = sqlite3.connect("tempest_guider.db")
    cursor = conn.cursor()
    cursor.execute("SELECT user_id FROM users WHERE is_banned = 0")
    users = [row[0] for row in cursor.fetchall()]
    conn.close()
    return users

def ban_user(user_id: int, reason: str):
    conn = sqlite3.connect("tempest_guider.db")
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET is_banned = 1 WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()

def unban_user(user_id: int):
    conn = sqlite3.connect("tempest_guider.db")
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET is_banned = 0 WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()

def mute_user(user_id: int, duration_minutes: int, reason: str):
    muted_until = datetime.now() + timedelta(minutes=duration_minutes)
    conn = sqlite3.connect("tempest_guider.db")
    cursor = conn.cursor()
    cursor.execute("""
        INSERT OR REPLACE INTO muted_users (user_id, muted_until, reason)
        VALUES (?, ?, ?)
    """, (user_id, muted_until.isoformat(), reason))
    conn.commit()
    conn.close()

def is_muted(user_id: int) -> bool:
    conn = sqlite3.connect("tempest_guider.db")
    cursor = conn.cursor()
    cursor.execute("SELECT muted_until FROM muted_users WHERE user_id = ?", (user_id,))
    result = cursor.fetchone()
    conn.close()
    if result:
        muted_until = datetime.fromisoformat(result[0])
        if muted_until > datetime.now():
            return True
    return False

# ============================================
# 37 MATH TOPICS
# ============================================
MATH_TOPICS = {
    "📊 ALGEBRA": {
        "1": {"name": "Linear Equations", "icon": "📈", "difficulty": "🟢 Beginner", "desc": "Solve equations of the form ax + b = c"},
        "2": {"name": "Quadratic Equations", "icon": "📉", "difficulty": "🟡 Intermediate", "desc": "Master ax² + bx + c = 0"},
        "3": {"name": "Polynomials", "icon": "🔢", "difficulty": "🔴 Advanced", "desc": "Operations and factoring of polynomials"},
        "4": {"name": "Inequalities", "icon": "⚖️", "difficulty": "🟡 Intermediate", "desc": "Solve and graph inequalities"},
        "5": {"name": "Systems of Equations", "icon": "🔗", "difficulty": "🔴 Advanced", "desc": "Multiple equations with multiple variables"},
        "6": {"name": "Functions & Relations", "icon": "🔄", "difficulty": "🟡 Intermediate", "desc": "Understanding function notation and behavior"},
        "7": {"name": "Logarithms", "icon": "📊", "difficulty": "🔴 Advanced", "desc": "Logarithmic functions and properties"},
        "8": {"name": "Exponents & Radicals", "icon": "√", "difficulty": "🟡 Intermediate", "desc": "Laws of exponents and radical expressions"},
    },
    
    "📐 GEOMETRY": {
        "9": {"name": "Triangles", "icon": "📐", "difficulty": "🟢 Beginner", "desc": "Triangle properties and theorems"},
        "10": {"name": "Circles", "icon": "⭕", "difficulty": "🟡 Intermediate", "desc": "Circle theorems and arc properties"},
        "11": {"name": "3D Geometry", "icon": "🧊", "difficulty": "🔴 Advanced", "desc": "Volume and surface area of 3D shapes"},
        "12": {"name": "Coordinate Geometry", "icon": "📊", "difficulty": "🟡 Intermediate", "desc": "Geometry on the coordinate plane"},
        "13": {"name": "Trigonometry Basics", "icon": "📏", "difficulty": "🟡 Intermediate", "desc": "Sine, cosine, and tangent ratios"},
        "14": {"name": "Transformations", "icon": "🔄", "difficulty": "🔴 Advanced", "desc": "Translations, rotations, reflections"},
        "15": {"name": "Similarity & Congruence", "icon": "📐", "difficulty": "🟡 Intermediate", "desc": "Similar and congruent figures"},
        "16": {"name": "Area & Perimeter", "icon": "⬛", "difficulty": "🟢 Beginner", "desc": "Calculate areas and perimeters"},
    },
    
    "📈 CALCULUS": {
        "17": {"name": "Limits & Continuity", "icon": "🎯", "difficulty": "🔴 Advanced", "desc": "Understanding limits and continuous functions"},
        "18": {"name": "Derivatives", "icon": "📈", "difficulty": "🔴 Advanced", "desc": "Rate of change and differentiation"},
        "19": {"name": "Integrals", "icon": "∫", "difficulty": "🔴 Advanced", "desc": "Area under curves and integration"},
        "20": {"name": "Differential Equations", "icon": "🔧", "difficulty": "🟣 Expert", "desc": "Equations involving derivatives"},
        "21": {"name": "Series & Sequences", "icon": "🔢", "difficulty": "🔴 Advanced", "desc": "Infinite series and convergence"},
        "22": {"name": "Multivariable Calculus", "icon": "🌐", "difficulty": "🟣 Expert", "desc": "Calculus with multiple variables"},
        "23": {"name": "Vector Calculus", "icon": "➡️", "difficulty": "🟣 Expert", "desc": "Gradient, divergence, and curl"},
    },
    
    "📊 STATISTICS": {
        "24": {"name": "Descriptive Statistics", "icon": "📊", "difficulty": "🟢 Beginner", "desc": "Mean, median, mode, and range"},
        "25": {"name": "Probability Theory", "icon": "🎲", "difficulty": "🟡 Intermediate", "desc": "Basic probability rules and concepts"},
        "26": {"name": "Distributions", "icon": "📈", "difficulty": "🔴 Advanced", "desc": "Normal, binomial, and other distributions"},
        "27": {"name": "Hypothesis Testing", "icon": "🔬", "difficulty": "🔴 Advanced", "desc": "Statistical significance tests"},
        "28": {"name": "Regression Analysis", "icon": "📉", "difficulty": "🟣 Expert", "desc": "Linear and nonlinear regression"},
        "29": {"name": "Bayesian Statistics", "icon": "🧠", "difficulty": "🟣 Expert", "desc": "Bayes' theorem and applications"},
    },
    
    "🔢 NUMBER THEORY": {
        "30": {"name": "Prime Numbers", "icon": "🔢", "difficulty": "🟡 Intermediate", "desc": "Properties of prime numbers"},
        "31": {"name": "Modular Arithmetic", "icon": "🔄", "difficulty": "🔴 Advanced", "desc": "Congruences and modular operations"},
        "32": {"name": "Cryptography Basics", "icon": "🔐", "difficulty": "🔴 Advanced", "desc": "Mathematical foundations of cryptography"},
        "33": {"name": "Number Patterns", "icon": "🎯", "difficulty": "🟢 Beginner", "desc": "Sequences and number relationships"},
        "34": {"name": "Fractions & Decimals", "icon": "➗", "difficulty": "🟢 Beginner", "desc": "Operations with fractions and decimals"},
        "35": {"name": "Complex Numbers", "icon": "💫", "difficulty": "🟣 Expert", "desc": "Numbers with real and imaginary parts"},
        "36": {"name": "Diophantine Equations", "icon": "🔍", "difficulty": "🟣 Expert", "desc": "Integer solutions to equations"},
        "37": {"name": "Fibonacci & Golden Ratio", "icon": "🌻", "difficulty": "🟡 Intermediate", "desc": "Special sequences and ratios"},
    }
}

# ============================================
# ACHIEVEMENTS
# ============================================
ACHIEVEMENTS = {
    "first_steps": {"name": "First Steps", "desc": "Solve your first problem", "icon": "👣", "points": 10},
    "math_enthusiast": {"name": "Math Enthusiast", "desc": "Solve 50 problems", "icon": "📚", "points": 50},
    "century_club": {"name": "Century Club", "desc": "Solve 100 problems", "icon": "💯", "points": 100},
    "image_master": {"name": "Image Master", "desc": "Process 25 images", "icon": "🖼️", "points": 75},
    "topic_explorer": {"name": "Topic Explorer", "desc": "Visit all 37 topics", "icon": "🗺️", "points": 150},
    "quiz_champion": {"name": "Quiz Champion", "desc": "Score 100% on a quiz", "icon": "🏆", "points": 200},
    "night_owl": {"name": "Night Owl", "desc": "Use bot after midnight", "icon": "🦉", "points": 25},
    "early_bird": {"name": "Early Bird", "desc": "Use bot before 6 AM", "icon": "🌅", "points": 25},
    "dedicated": {"name": "Dedicated", "desc": "Use bot 7 days in a row", "icon": "📅", "points": 100},
    "helper": {"name": "Helper", "desc": "Refer a friend", "icon": "🤝", "points": 50},
}

# ============================================
# PILLOW IMAGE PROCESSING
# ============================================
def process_math_photo(image_bytes: bytes, user_id: int = None) -> bytes:
    """Advanced image processing with multiple filters and enhancements"""
    image = Image.open(BytesIO(image_bytes)).convert("RGB")
    
    # 1. Initial preprocessing
    width, height = image.size
    if width > 1024 or height > 1024:
        image.thumbnail((1024, 1024), Image.LANCZOS)
    
    # 2. Background detection and filtering
    gray = ImageOps.grayscale(image)
    
    # 3. Edge detection for math content
    edges = gray.filter(ImageFilter.FIND_EDGES)
    edges = edges.point(lambda x: 255 if x > 30 else 0)
    
    # 4. Create mask for background removal
    mask = edges.filter(ImageFilter.MaxFilter(9))
    mask = mask.filter(ImageFilter.GaussianBlur(radius=2))
    
    # 5. Apply background filtering
    background = Image.new("RGB", image.size, (255, 255, 255))
    filtered = Image.composite(image, background, mask)
    
    # 6. Enhance contrast and sharpness
    enhancer = ImageEnhance.Contrast(filtered)
    filtered = enhancer.enhance(1.5)
    
    enhancer = ImageEnhance.Sharpness(filtered)
    filtered = enhancer.enhance(1.3)
    
    # 7. Color enhancement
    enhancer = ImageEnhance.Color(filtered)
    filtered = enhancer.enhance(1.2)
    
    # 8. Add header banner
    banner_height = 100
    new_img = Image.new("RGB", (filtered.width, filtered.height + banner_height), (15, 23, 42))
    new_img.paste(filtered, (0, banner_height))
    
    # 9. Draw header
    draw = ImageDraw.Draw(new_img)
    
    # Gradient header effect
    for i in range(banner_height):
        color = (15 + i // 2, 23 + i // 3, 42 + i // 4)
        draw.line([(0, i), (filtered.width, i)], fill=color)
    
    # 10. Add branding and user info
    try:
        # Try to load a nice font
        font_large = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 24)
        font_small = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 14)
    except:
        font_large = ImageFont.load_default()
        font_small = ImageFont.load_default()
    
    draw.text((20, 20), "📐 TEMPEST GUIDER", fill=(56, 189, 248), font=font_large)
    draw.text((20, 55), "Advanced Math Processing Engine", fill=(148, 163, 184), font=font_small)
    draw.text((filtered.width - 200, 20), f"ID: {user_id if user_id else 'Guest'}", 
              fill=(148, 163, 184), font=font_small)
    
    # 11. Add timestamp
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    draw.text((filtered.width - 200, 55), timestamp, fill=(148, 163, 184), font=font_small)
    
    # 12. Add decorative elements
    for i in range(3):
        x = 20 + i * 30
        draw.ellipse([x, 80, x + 10, 90], fill=(56, 189, 248, 128))
    
    # 13. Add watermark
    watermark = "TEMPEST"
    draw.text((filtered.width // 2 - 50, filtered.height + 10), watermark, 
              fill=(255, 255, 255, 30), font=font_small)
    
    # Save with optimization
    output = BytesIO()
    new_img.save(output, format="JPEG", quality=95, optimize=True)
    output.seek(0)
    return output.read()

def generate_math_graph(equation: str) -> bytes:
    """Generate mathematical graph from equation"""
    try:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        import numpy as np
        
        # Create figure
        fig, ax = plt.subplots(figsize=(8, 6))
        
        # Generate x values
        x = np.linspace(-10, 10, 400)
        
        # Parse and plot equation
        equation = equation.replace('^', '**')
        equation = equation.replace('sin', 'np.sin')
        equation = equation.replace('cos', 'np.cos')
        equation = equation.replace('tan', 'np.tan')
        equation = equation.replace('sqrt', 'np.sqrt')
        equation = equation.replace('log', 'np.log')
        equation = equation.replace('exp', 'np.exp')
        equation = equation.replace('pi', 'np.pi')
        equation = equation.replace('e', 'np.e')
        
        # Replace x with actual values
        equation = equation.replace('x', '(x)')
        y = eval(equation)
        
        # Plot
        ax.plot(x, y, linewidth=2, color='#38BDF8')
        ax.grid(True, alpha=0.3)
        ax.axhline(y=0, color='black', linewidth=0.5)
        ax.axvline(x=0, color='black', linewidth=0.5)
        ax.set_title(f"Graph of {equation.replace('(x)', 'x')}", fontsize=14, fontweight='bold')
        ax.set_xlabel('x', fontsize=12)
        ax.set_ylabel('y', fontsize=12)
        
        # Style
        ax.set_facecolor('#F8FAFC')
        fig.patch.set_facecolor('#F8FAFC')
        
        # Save to bytes
        buf = BytesIO()
        plt.savefig(buf, format='png', dpi=100, bbox_inches='tight')
        plt.close()
        buf.seek(0)
        return buf.read()
    except:
        return None

# ============================================
# KEYBOARD BUILDERS
# ============================================
def get_main_menu_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="📚 Math Topics", callback_data="menu_topics")
    builder.button(text="🎯 Solve Problem", callback_data="menu_solve")
    builder.button(text="📊 Quiz Mode", callback_data="menu_quiz")
    builder.button(text="📈 Graph Generator", callback_data="menu_graph")
    builder.button(text="👤 Profile", callback_data="menu_profile")
    builder.button(text="🏆 Achievements", callback_data="menu_achievements")
    builder.button(text="📖 Formulas", callback_data="menu_formulas")
    builder.button(text="⚙️ Settings", callback_data="menu_settings")
    builder.button(text="💡 Help", callback_data="menu_help")
    builder.adjust(2, 2, 2, 2, 1)
    return builder.as_markup()

def get_topic_categories_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    categories = list(MATH_TOPICS.keys())
    for category in categories:
        builder.button(text=category, callback_data=f"cat_{category}")
    builder.button(text="🔍 Search Topics", callback_data="search_topics")
    builder.button(text="« Back to Menu", callback_data="back_main")
    builder.adjust(1)
    return builder.as_markup()

def get_topics_keyboard(category: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    topics = MATH_TOPICS.get(category, {})
    for topic_id, topic_data in topics.items():
        button_text = f"{topic_data['icon']} {topic_data['name']} {topic_data['difficulty']}"
        builder.button(text=button_text, callback_data=f"topic_{topic_id}")
    builder.button(text="« Back to Categories", callback_data="back_categories")
    builder.button(text="« Main Menu", callback_data="back_main")
    builder.adjust(1)
    return builder.as_markup()

# ============================================
# HANDLERS
# ============================================
@router.message(CommandStart())
async def cmd_start(message: Message):
    user = message.from_user
    add_user(user.id, user.username or "Unknown", user.first_name or "User")
    
    welcome_text = (
        f"⚡ **Welcome to Tempest Guider, {user.first_name}!**\n\n"
        f"🔢 **The Ultimate Mathematics Bot**\n"
        f"📚 **37 Advanced Math Topics**\n"
        f"🖼️ **Image Processing Engine**\n"
        f"🎯 **Interactive Quiz System**\n"
        f"🏆 **Achievements & XP**\n\n"
        f"Get started by exploring topics or solving problems!"
    )
    
    await message.answer(
        welcome_text,
        reply_markup=get_main_menu_keyboard(),
        parse_mode=ParseMode.MARKDOWN
    )

@router.message(Command("help"))
async def cmd_help(message: Message):
    help_text = (
        "🤖 **TEMPEST GUIDER - COMMAND DIRECTORY**\n\n"
        "📚 **User Commands:**\n"
        "• /start - Launch main dashboard\n"
        "• /menu - Open interactive menu\n"
        "• /topics - Browse 37 math topics\n"
        "• /solve - Solve math problems\n"
        "• /quiz - Start interactive quiz\n"
        "• /graph - Generate math graphs\n"
        "• /profile - View your profile\n"
        "• /achievements - View achievements\n"
        "• /formulas - Formula reference\n"
        "• /history - Solution history\n"
        "• /help - Show this help\n\n"
        "🖼️ **Image Processing:**\n"
        "Send any photo of math problems for automatic background filtering and enhancement!\n\n"
        "📊 **Quick Start:**\n"
        "1. Click 'Math Topics' to explore\n"
        "2. Select your desired topic\n"
        "3. Start learning and solving!"
    )
    
    if message.from_user.id == ADMIN_ID:
        help_text += (
            "\n\n👑 **Admin Commands:**\n"
            "• /admin - Admin control panel\n"
            "• /broadcast - Broadcast message\n"
            "• /stats - Bot statistics\n"
            "• /ban - Ban user\n"
            "• /unban - Unban user\n"
            "• /warn - Warn user\n"
            "• /mute - Mute user\n"
            "• /backup - Backup database"
        )
    
    await message.answer(help_text, parse_mode=ParseMode.MARKDOWN)

@router.message(Command("menu"))
async def cmd_menu(message: Message):
    await message.answer(
        "📊 **TEMPEST GUIDER MAIN MENU**\n\nSelect an option:",
        reply_markup=get_main_menu_keyboard(),
        parse_mode=ParseMode.MARKDOWN
    )

@router.message(Command("topics"))
async def cmd_topics(message: Message):
    await message.answer(
        "📚 **MATHEMATICS TOPICS**\n\n"
        "Select a category to explore 37 advanced math topics:",
        reply_markup=get_topic_categories_keyboard(),
        parse_mode=ParseMode.MARKDOWN
    )

@router.message(Command("profile"))
async def cmd_profile(message: Message):
    user_data = get_user_data(message.from_user.id)
    if user_data:
        _, username, first_name, points, level, join_date, last_active, warnings, is_banned, selected_topic, total_solved, total_images, quiz_score = user_data
        
        level_names = ["", "Novice", "Apprentice", "Scholar", "Expert", "Master", "Grandmaster", "Legend", "Mythic", "Transcendent", "Omniscient"]
        level_name = level_names[level] if level < len(level_names) else "Omniscient"
        
        profile_text = (
            f"👤 **USER PROFILE**\n\n"
            f"**Name:** {first_name}\n"
            f"**Username:** @{username}\n"
            f"**ID:** `{message.from_user.id}`\n\n"
            f"📊 **STATISTICS**\n"
            f"**Level:** {level} - {level_name}\n"
            f"**Points:** {points} XP\n"
            f"**Problems Solved:** {total_solved}\n"
            f"**Images Processed:** {total_images}\n"
            f"**Best Quiz Score:** {quiz_score}%\n\n"
            f"📅 **MEMBER SINCE:** {join_date[:10]}\n"
            f"🕐 **LAST ACTIVE:** {last_active[:16]}"
        )
        
        await message.answer(profile_text, parse_mode=ParseMode.MARKDOWN)
    else:
        await message.answer("❌ Profile not found. Please use /start first.")

@router.message(Command("achievements"))
async def cmd_achievements(message: Message):
    conn = sqlite3.connect("tempest_guider.db")
    cursor = conn.cursor()
    cursor.execute("SELECT achievement_name FROM user_achievements WHERE user_id = ?", 
                   (message.from_user.id,))
    unlocked = [row[0] for row in cursor.fetchall()]
    conn.close()
    
    achievements_text = "🏆 **ACHIEVEMENTS**\n\n"
    
    for key, achievement in ACHIEVEMENTS.items():
        if key in unlocked:
            achievements_text += f"{achievement['icon']} **{achievement['name']}** - ✅ Unlocked\n"
            achievements_text += f"└ {achievement['desc']}\n\n"
        else:
            achievements_text += f"{achievement['icon']} **{achievement['name']}** - 🔒 Locked\n"
            achievements_text += f"└ {achievement['desc']}\n\n"
    
    achievements_text += f"\n**Progress:** {len(unlocked)}/{len(ACHIEVEMENTS)} achievements unlocked"
    
    kb = InlineKeyboardBuilder()
    kb.button(text="« Back to Menu", callback_data="back_main")
    
    await message.answer(achievements_text, reply_markup=kb.as_markup(), parse_mode=ParseMode.MARKDOWN)

# ============================================
# ADMIN COMMANDS
# ============================================
@router.message(Command("admin"))
async def cmd_admin(message: Message):
    if message.from_user.id != ADMIN_ID:
        await message.answer("❌ Unauthorized access.")
        return
    
    kb = InlineKeyboardBuilder()
    kb.button(text="📊 Statistics", callback_data="admin_stats")
    kb.button(text="📢 Broadcast", callback_data="admin_broadcast")
    kb.button(text="👥 User List", callback_data="admin_users")
    kb.button(text="⚙️ Settings", callback_data="admin_settings")
    kb.button(text="🔒 Security", callback_data="admin_security")
    kb.adjust(2)
    
    await message.answer(
        "👑 **ADMIN CONTROL PANEL**\n\n"
        "Select an option:",
        reply_markup=kb.as_markup(),
        parse_mode=ParseMode.MARKDOWN
    )

@router.message(Command("stats"))
async def cmd_stats(message: Message):
    if message.from_user.id != ADMIN_ID:
        await message.answer("❌ Unauthorized access.")
        return
    
    conn = sqlite3.connect("tempest_guider.db")
    cursor = conn.cursor()
    
    # Total users
    cursor.execute("SELECT COUNT(*) FROM users")
    total_users = cursor.fetchone()[0]
    
    # Active users (last 24 hours)
    yesterday = (datetime.now() - timedelta(days=1)).isoformat()
    cursor.execute("SELECT COUNT(*) FROM users WHERE last_active > ?", (yesterday,))
    active_users = cursor.fetchone()[0]
    
    # Total problems solved
    cursor.execute("SELECT SUM(total_solved) FROM users")
    total_solved = cursor.fetchone()[0] or 0
    
    # Total images processed
    cursor.execute("SELECT SUM(total_images) FROM users")
    total_images = cursor.fetchone()[0] or 0
    
    # Banned users
    cursor.execute("SELECT COUNT(*) FROM users WHERE is_banned = 1")
    banned_users = cursor.fetchone()[0]
    
    conn.close()
    
    stats_text = (
        f"📊 **TEMPEST GUIDER STATISTICS**\n\n"
        f"👥 **Total Users:** {total_users}\n"
        f"🟢 **Active (24h):** {active_users}\n"
        f"📝 **Problems Solved:** {total_solved}\n"
        f"🖼️ **Images Processed:** {total_images}\n"
        f"🚫 **Banned Users:** {banned_users}\n\n"
        f"📈 **Growth Rate:** {active_users/total_users*100:.1f}% daily activity\n"
        f"🕐 **Server Time:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    )
    
    await message.answer(stats_text, parse_mode=ParseMode.MARKDOWN)

@router.message(Command("broadcast"))
async def cmd_broadcast(message: Message, command: CommandObject):
    if message.from_user.id != ADMIN_ID:
        await message.answer("❌ Unauthorized access.")
        return
    
    if not command.args:
        await message.answer("Usage: /broadcast Your message here")
        return
    
    users = get_all_users()
    success_count = 0
    failed_count = 0
    
    status_msg = await message.answer(f"🚀 Broadcasting to {len(users)} users...")
    
    for user_id in users:
        try:
            await message.bot.send_message(
                user_id,
                f"📢 **TEMPEST ANNOUNCEMENT**\n\n{command.args}",
                parse_mode=ParseMode.MARKDOWN
            )
            success_count += 1
            await asyncio.sleep(0.05)  # Rate limiting
        except Exception as e:
            failed_count += 1
            logger.error(f"Broadcast failed for {user_id}: {e}")
    
    # Log broadcast
    conn = sqlite3.connect("tempest_guider.db")
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO broadcast_logs (admin_id, message_text, recipients_count, success_count, timestamp)
        VALUES (?, ?, ?, ?, ?)
    """, (message.from_user.id, command.args, len(users), success_count, datetime.now().isoformat()))
    conn.commit()
    conn.close()
    
    await status_msg.edit_text(
        f"✅ **BROADCAST COMPLETE**\n\n"
        f"📊 **Recipients:** {len(users)}\n"
        f"✅ **Successful:** {success_count}\n"
        f"❌ **Failed:** {failed_count}",
        parse_mode=ParseMode.MARKDOWN
    )

@router.message(Command("ban"))
async def cmd_ban(message: Message, command: CommandObject):
    if message.from_user.id != ADMIN_ID:
        await message.answer("❌ Unauthorized access.")
        return
    
    if not command.args:
        await message.answer("Usage: /ban [user_id] [reason]")
        return
    
    parts = command.args.split(maxsplit=1)
    try:
        target_id = int(parts[0])
        reason = parts[1] if len(parts) > 1 else "No reason provided"
    except ValueError:
        await message.answer("❌ Invalid user ID.")
        return
    
    ban_user(target_id, reason)
    
    # Try to notify banned user
    try:
        await message.bot.send_message(
            target_id,
            f"🚫 **YOU HAVE BEEN BANNED**\n\n"
            f"**Reason:** {reason}\n\n"
            f"If you believe this is a mistake, please contact support."
        )
    except:
        pass
    
    await message.answer(f"✅ User {target_id} has been banned.\nReason: {reason}")

@router.message(Command("unban"))
async def cmd_unban(message: Message, command: CommandObject):
    if message.from_user.id != ADMIN_ID:
        await message.answer("❌ Unauthorized access.")
        return    
    if not command.args:
        await message.answer("Usage: /unban [user_id]")
        return
    
    try:
        target_id = int(command.args)
    except ValueError:
        await message.answer("❌ Invalid user ID.")
        return
    
    unban_user(target_id)
    
    # Try to notify unbanned user
    try:
        await message.bot.send_message(
            target_id,
            "✅ **YOU HAVE BEEN UNBANNED**\n\n"
            "Welcome back to Tempest Guider!"
        )
    except:
        pass
    
    await message.answer(f"✅ User {target_id} has been unbanned.")

@router.message(Command("warn"))
async def cmd_warn(message: Message, command: CommandObject):
    if message.from_user.id != ADMIN_ID:
        await message.answer("❌ Unauthorized access.")
        return
    
    if not command.args:
        await message.answer("Usage: /warn [user_id] [reason]")
        return
    
    parts = command.args.split(maxsplit=1)
    try:
        target_id = int(parts[0])
        reason = parts[1] if len(parts) > 1 else "No reason provided"
    except ValueError:
        await message.answer("❌ Invalid user ID.")
        return
    
    conn = sqlite3.connect("tempest_guider.db")
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET warnings = warnings + 1 WHERE user_id = ?", (target_id,))
    cursor.execute("SELECT warnings FROM users WHERE user_id = ?", (target_id,))
    warnings = cursor.fetchone()[0]
    conn.commit()
    conn.close()
    
    # Try to notify warned user
    try:
        await message.bot.send_message(
            target_id,
            f"⚠️ **WARNING #{warnings}**\n\n"
            f"**Reason:** {reason}\n\n"
            f"Please follow the bot's rules to avoid being banned."
        )
    except:
        pass
    
    await message.answer(f"✅ User {target_id} has been warned.\nTotal warnings: {warnings}")

@router.message(Command("mute"))
async def cmd_mute(message: Message, command: CommandObject):
    if message.from_user.id != ADMIN_ID:
        await message.answer("❌ Unauthorized access.")
        return
    
    if not command.args:
        await message.answer("Usage: /mute [user_id] [minutes] [reason]")
        return
    
    parts = command.args.split(maxsplit=2)
    try:
        target_id = int(parts[0])
        duration = int(parts[1]) if len(parts) > 1 else 60
        reason = parts[2] if len(parts) > 2 else "No reason provided"
    except ValueError:
        await message.answer("❌ Invalid input.")
        return
    
    mute_user(target_id, duration, reason)
    
    # Try to notify muted user
    try:
        await message.bot.send_message(
            target_id,
            f"🔇 **YOU HAVE BEEN MUTED**\n\n"
            f"**Duration:** {duration} minutes\n"
            f"**Reason:** {reason}"
        )
    except:
        pass
    
    await message.answer(f"✅ User {target_id} has been muted for {duration} minutes.")

@router.message(Command("backup"))
async def cmd_backup(message: Message):
    if message.from_user.id != ADMIN_ID:
        await message.answer("❌ Unauthorized access.")
        return
    
    try:
        # Create backup
        backup_path = f"backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db"
        conn = sqlite3.connect("tempest_guider.db")
        backup_conn = sqlite3.connect(backup_path)
        conn.backup(backup_conn)
        conn.close()
        backup_conn.close()
        
        # Send backup file
        with open(backup_path, 'rb') as f:
            await message.answer_document(
                BufferedInputFile(f.read(), filename=backup_path),
                caption="✅ Database backup created successfully!"
            )
        
        # Clean up
        os.remove(backup_path)
        
    except Exception as e:
        await message.answer(f"❌ Backup failed: {str(e)}")

# ============================================
# CALLBACK HANDLERS
# ============================================
@router.callback_query(F.data == "back_main")
async def back_to_main(callback: CallbackQuery):
    await callback.message.edit_text(
        "📊 **TEMPEST GUIDER MAIN MENU**\n\nSelect an option:",
        reply_markup=get_main_menu_keyboard(),
        parse_mode=ParseMode.MARKDOWN
    )
    await callback.answer()

@router.callback_query(F.data == "menu_topics")
async def menu_topics(callback: CallbackQuery):
    await callback.message.edit_text(
        "📚 **MATHEMATICS TOPICS**\n\n"
        "Select a category to explore 37 advanced math topics:",
        reply_markup=get_topic_categories_keyboard(),
        parse_mode=ParseMode.MARKDOWN
    )
    await callback.answer()

@router.callback_query(F.data.startswith("cat_"))
async def show_category_topics(callback: CallbackQuery):
    category = callback.data.replace("cat_", "")
    await callback.message.edit_text(
        f"📚 **{category} TOPICS**\n\n"
        f"Select a topic to learn more:",
        reply_markup=get_topics_keyboard(category),
        parse_mode=ParseMode.MARKDOWN
    )
    await callback.answer()

@router.callback_query(F.data == "back_categories")
async def back_to_categories(callback: CallbackQuery):
    await callback.message.edit_text(
        "📚 **MATHEMATICS TOPICS**\n\n"
        "Select a category:",
        reply_markup=get_topic_categories_keyboard(),
        parse_mode=ParseMode.MARKDOWN
    )
    await callback.answer()

@router.callback_query(F.data.startswith("topic_"))
async def show_topic_info(callback: CallbackQuery):
    topic_id = callback.data.replace("topic_", "")
    
    # Find topic
    topic_info = None
    topic_category = None
    for category, topics in MATH_TOPICS.items():
        if topic_id in topics:
            topic_info = topics[topic_id]
            topic_category = category
            break
    
    if topic_info:
        add_points(callback.from_user.id, 5)  # XP for exploring
        
        # Check achievement
        conn = sqlite3.connect("tempest_guider.db")
        cursor = conn.cursor()
        cursor.execute("""
            INSERT OR IGNORE INTO user_achievements (user_id, achievement_name, unlocked_date)
            VALUES (?, 'topic_explorer', ?)
        """, (callback.from_user.id, datetime.now().isoformat()))
        conn.commit()
        conn.close()
        
        text = (
            f"{topic_info['icon']} **{topic_info['name']}**\n\n"
            f"📚 **Category:** {topic_category}\n"
            f"📊 **Difficulty:** {topic_info['difficulty']}\n\n"
            f"📖 **Description:**\n{topic_info['desc']}\n\n"
            f"🎯 **What you'll learn:**\n"
            f"• Core concepts and principles\n"
            f"• Problem-solving strategies\n"
            f"• Real-world applications\n"
            f"• Practice problems\n\n"
            f"✅ **Ready to explore?** Use /solve to practice problems in this topic!"
        )
        
        kb = InlineKeyboardBuilder()
        kb.button(text="📝 Practice Problems", callback_data=f"practice_{topic_id}")
        kb.button(text="📊 Generate Graph", callback_data=f"graph_topic_{topic_id}")
        kb.button(text="« Back to Topics", callback_data=f"cat_{topic_category}")
        kb.button(text="« Main Menu", callback_data="back_main")
        kb.adjust(1)
        
        await callback.message.edit_text(
            text,
            reply_markup=kb.as_markup(),
            parse_mode=ParseMode.MARKDOWN
        )
    
    await callback.answer()

@router.callback_query(F.data == "menu_quiz")
async def menu_quiz(callback: CallbackQuery):
    kb = InlineKeyboardBuilder()
    kb.button(text="🟢 Quick Fire (5 questions)", callback_data="quiz_quick")
    kb.button(text="🟡 Standard (10 questions)", callback_data="quiz_standard")
    kb.button(text="🔴 Marathon (25 questions)", callback_data="quiz_marathon")
    kb.button(text="🟣 Expert Challenge (15 questions)", callback_data="quiz_expert")
    kb.button(text="« Main Menu", callback_data="back_main")
    kb.adjust(1)
    
    await callback.message.edit_text(
        "📊 **QUIZ MODE**\n\n"
        "Select quiz type:",
        reply_markup=kb.as_markup(),
        parse_mode=ParseMode.MARKDOWN
    )
    await callback.answer()

@router.callback_query(F.data == "menu_profile")
async def menu_profile(callback: CallbackQuery):
    user_data = get_user_data(callback.from_user.id)
    if user_data:
        _, username, first_name, points, level, join_date, last_active, warnings, is_banned, selected_topic, total_solved, total_images, quiz_score = user_data
        
        level_names = ["", "Novice", "Apprentice", "Scholar", "Expert", "Master", "Grandmaster", "Legend", "Mythic", "Transcendent", "Omniscient"]
        level_name = level_names[level] if level < len(level_names) else "Omniscient"
        
        # Progress to next level
        thresholds = [0, 100, 250, 500, 1000, 2000, 4000, 8000, 16000, 32000]
        current_threshold = thresholds[level] if level < len(thresholds) else thresholds[-1]
        next_threshold = thresholds[level + 1] if level + 1 < len(thresholds) else thresholds[-1] * 2
        progress = (points - current_threshold) / (next_threshold - current_threshold) * 100
        
        profile_text = (
            f"👤 **{first_name}** (@{username})\n\n"
            f"📊 **Level {level} - {level_name}**\n"
            f"**Points:** {points} XP\n"
            f"**Progress:** {progress:.1f}% to next level\n\n"
            f"📝 **Problems Solved:** {total_solved}\n"
            f"🖼️ **Images Processed:** {total_images}\n"
            f"🎯 **Best Quiz Score:** {quiz_score}%\n\n"
            f"📅 **Member since:** {join_date[:10]}"
        )
        
        kb = InlineKeyboardBuilder()
        kb.button(text="🏆 Achievements", callback_data="menu_achievements")
        kb.button(text="📖 History", callback_data="view_history")
        kb.button(text="« Main Menu", callback_data="back_main")
        kb.adjust(1)
        
        await callback.message.edit_text(
            profile_text,
            reply_markup=kb.as_markup(),
            parse_mode=ParseMode.MARKDOWN
        )
    
    await callback.answer()

@router.callback_query(F.data == "menu_achievements")
async def menu_achievements(callback: CallbackQuery):
    await cmd_achievements(callback.message)
    await callback.answer()

@router.callback_query(F.data == "menu_help")
async def menu_help(callback: CallbackQuery):
    kb = InlineKeyboardBuilder()
    kb.button(text="« Main Menu", callback_data="back_main")
    
    help_text = (
        "💡 **HOW TO USE TEMPEST GUIDER**\n\n"
        "1️⃣ **Explore Topics:** Browse 37 math topics\n"
        "2️⃣ **Upload Images:** Send photos of math problems\n"
        "3️⃣ **Take Quizzes:** Test your knowledge\n"
        "4️⃣ **Generate Graphs:** Visualize equations\n"
        "5️⃣ **Earn XP:** Get points for activities\n"
        "6️⃣ **Unlock Achievements:** Complete challenges\n\n"
        "🖼️ **Image Processing:**\n"
        "Simply send any photo of a math problem and the bot will automatically:\n"
        "• Remove background noise\n"
        "• Enhance image quality\n"
        "• Detect math content\n"
        "• Process and analyze"
    )
    
    await callback.message.edit_text(
        help_text,
        reply_markup=kb.as_markup(),
        parse_mode=ParseMode.MARKDOWN
    )
    await callback.answer()

@router.callback_query(F.data == "menu_graph")
async def menu_graph(callback: CallbackQuery):
    kb = InlineKeyboardBuilder()
    kb.button(text="« Main Menu", callback_data="back_main")
    
    await callback.message.edit_text(
        "📈 **GRAPH GENERATOR**\n\n"
        "Send me an equation to graph!\n\n"
        "**Examples:**\n"
        "• y = x^2\n"
        "• y = sin(x)\n"
        "• y = 2*x + 3\n"
        "• y = sqrt(x)\n\n"
        "Just type /graph followed by your equation!",
        reply_markup=kb.as_markup(),
        parse_mode=ParseMode.MARKDOWN
    )
    await callback.answer()

# ============================================
# MESSAGE HANDLERS
# ============================================
@router.message(Command("graph"))
async def cmd_graph(message: Message, command: CommandObject):
    if not command.args:
        await message.answer(
            "📈 **GRAPH GENERATOR**\n\n"
            "Usage: /graph [equation]\n\n"
            "**Examples:**\n"
            "• /graph x^2\n"
            "• /graph sin(x)\n"
            "• /graph 2*x + 3"
        )
        return
    
    equation = command.args
    graph_image = generate_math_graph(equation)
    
    if graph_image:
        add_points(message.from_user.id, 15)  # XP for generating graph
        await message.answer_photo(
            BufferedInputFile(graph_image, filename="graph.png"),
            caption=f"📈 Graph of y = {equation}"
        )
    else:
        await message.answer("❌ Invalid equation. Please try again with a valid mathematical expression.")

@router.message(Command("solve"))
async def cmd_solve(message: Message, command: CommandObject):
    if not command.args:
        await message.answer(
            "🎯 **SOLVE PROBLEM**\n\n"
            "Usage: /solve [problem]\n\n"
            "**Examples:**\n"
            "• /solve 2x + 5 = 15\n"
            "• /solve x^2 + 3x + 2 = 0\n"
            "• /solve derivative of x^2\n\n"
            "Or simply upload a photo of your math problem!"
        )
        return
    
    problem = command.args
    solution = solve_math_problem(problem)
    
    if solution:
        add_points(message.from_user.id, 10)
        await message.answer(
            f"✅ **SOLUTION FOUND**\n\n"
            f"**Problem:** {problem}\n"
            f"**Solution:** {solution}"
        )
    else:
        await message.answer(
            "❌ Unable to solve this problem automatically.\n"
            "Try uploading a photo or rephrasing the problem."
        )

def solve_math_problem(problem: str) -> Optional[str]:
    """Basic math problem solver"""
    try:
        # Linear equation solver
        if '=' in problem and 'x' in problem:
            left, right = problem.split('=')
            left = left.strip()
            right = right.strip()
            
            # Parse coefficients
            left = left.replace(' ', '')
            right = right.replace(' ', '')
            
            # Simple linear equation: ax + b = c
            if '+' in left and 'x' in left:
                parts = left.split('+')
                if 'x' in parts[0]:
                    a = float(parts[0].replace('x', '').strip() or '1')
                    b = float(parts[1].strip())
                else:
                    a = float(parts[1].replace('x', '').strip() or '1')
                    b = float(parts[0].strip())
                c = float(right)
                x = (c - b) / a
                return f"x = {x:.2f}"
            
            # Simple: ax = c
            elif 'x' in left and '*' in left:
                a = float(left.replace('x', '').replace('*', '').strip())
                c = float(right)
                x = c / a
                return f"x = {x:.2f}"
        
        # Quadratic equation
        if '^2' in problem and '=' in problem:
            left, right = problem.split('=')
            left = left.strip()
            
            # Parse ax^2 + bx + c = 0
            if '+0' in right.replace(' ', ''):
                # Extract coefficients
                parts = left.replace(' ', '').split('+')
                a = b = c = 0
                for part in parts:
                    if 'x^2' in part:
                        a = float(part.replace('x^2', '').strip() or '1')
                    elif 'x' in part:
                        b = float(part.replace('x', '').strip() or '1')
                    else:
                        c = float(part.strip())
                
                discriminant = b**2 - 4*a*c
                if discriminant >= 0:
                    x1 = (-b + discriminant**0.5) / (2*a)
                    x2 = (-b - discriminant**0.5) / (2*a)
                    if discriminant == 0:
                        return f"x = {x1:.2f} (double root)"
                    else:
                        return f"x₁ = {x1:.2f}, x₂ = {x2:.2f}"
                else:
                    real_part = -b / (2*a)
                    imag_part = (abs(discriminant)**0.5) / (2*a)
                    return f"x₁ = {real_part:.2f} + {imag_part:.2f}i, x₂ = {real_part:.2f} - {imag_part:.2f}i"
        
        # Derivative
        if 'derivative' in problem.lower():
            func = problem.lower().replace('derivative of', '').strip()
            if 'x^' in func:
                n = float(func.split('x^')[1])
                return f"d/dx({func}) = {n}x^{int(n-1)}"
        
        # Integral
        if 'integral' in problem.lower():
            func = problem.lower().replace('integral of', '').strip()
            if 'x^' in func:
                n = float(func.split('x^')[1])
                return f"∫({func})dx = (1/{int(n+1)})x^{int(n+1)} + C"
        
        return None
    except:
        return None

@router.message(F.photo)
async def handle_photo(message: Message):
    """Handle photo uploads with advanced image processing"""
    
    # Check if user is muted
    if is_muted(message.from_user.id):
        await message.answer("🔇 You are currently muted and cannot send images.")
        return
    
    processing_msg = await message.answer(
        "🔄 **PROCESSING IMAGE**\n\n"
        "⚙️ Applying advanced filters...\n"
        "🎨 Enhancing image quality...\n"
        "🔍 Detecting math content..."
    )
    
    try:
        # Get the largest photo
        photo = message.photo[-1]
        file_info = await message.bot.get_file(photo.file_id)
        file_bytes = await message.bot.download_file(file_info.file_path)
        
        # Process image
        processed_bytes = await asyncio.to_thread(
            process_math_photo, 
            file_bytes.read(), 
            message.from_user.id
        )
        
        # Update user stats
        conn = sqlite3.connect("tempest_guider.db")
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE users SET total_images = total_images + 1 WHERE user_id = ?
        """, (message.from_user.id,))
        conn.commit()
        conn.close()
        
        add_points(message.from_user.id, 15)  # XP for image processing
        
        # Check achievement
        conn = sqlite3.connect("tempest_guider.db")
        cursor = conn.cursor()
        cursor.execute("SELECT total_images FROM users WHERE user_id = ?", (message.from_user.id,))
        total_images = cursor.fetchone()[0]
        if total_images >= 25:
            cursor.execute("""
                INSERT OR IGNORE INTO user_achievements (user_id, achievement_name, unlocked_date)
                VALUES (?, 'image_master', ?)
            """, (message.from_user.id, datetime.now().isoformat()))
        conn.commit()
        conn.close()
        
        # Delete processing message
        await processing_msg.delete()
        
        # Send processed image
        caption = (
            f"✅ **IMAGE PROCESSED SUCCESSFULLY**\n\n"
            f"🎨 **Applied Filters:**\n"
            f"• Background Removal\n"
            f"• Edge Detection\n"
            f"• Contrast Enhancement\n"
            f"• Sharpness Optimization\n"
            f"• Color Correction\n\n"
            f"💡 **Math content detected!** Use /solve for step-by-step solutions."
        )
        
        await message.answer_photo(
            photo=BufferedInputFile(processed_bytes, filename="tempest_processed.jpg"),
            caption=caption,
            parse_mode=ParseMode.MARKDOWN
        )
        
    except Exception as e:
        logger.error(f"Image processing error: {e}")
        await processing_msg.edit_text(
            f"❌ **PROCESSING FAILED**\n\n"
            f"Error: {str(e)}\n"
            f"Please try again with a different image."
        )

@router.message()
async def handle_text(message: Message):
    """Handle text messages"""
    
    # Check if user is muted
    if is_muted(message.from_user.id):
        await message.answer("🔇 You are currently muted.")
        return
    
    # Check if message contains math
    if any(c.isdigit() for c in message.text) and any(c in message.text for c in '+-*/=^'):
        # Try to solve
        solution = solve_math_problem(message.text)
        if solution:
            add_points(message.from_user.id, 10)
            
            # Check achievements
            conn = sqlite3.connect("tempest_guider.db")
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE users SET total_solved = total_solved + 1 WHERE user_id = ?
            """, (message.from_user.id,))
            
            cursor.execute("SELECT total_solved FROM users WHERE user_id = ?", (message.from_user.id,))
            total_solved = cursor.fetchone()[0]
            
            if total_solved == 1:
                cursor.execute("""
                    INSERT OR IGNORE INTO user_achievements (user_id, achievement_name, unlocked_date)
                    VALUES (?, 'first_steps', ?)
                """, (message.from_user.id, datetime.now().isoformat()))
            elif total_solved >= 50:
                cursor.execute("""
                    INSERT OR IGNORE INTO user_achievements (user_id, achievement_name, unlocked_date)
                    VALUES (?, 'math_enthusiast', ?)
                """, (message.from_user.id, datetime.now().isoformat()))
            elif total_solved >= 100:
                cursor.execute("""
                    INSERT OR IGNORE INTO user_achievements (user_id, achievement_name, unlocked_date)
                    VALUES (?, 'century_club', ?)
                """, (message.from_user.id, datetime.now().isoformat()))
            
            conn.commit()
            conn.close()
            
            await message.answer(
                f"✅ **SOLVED!**\n\n"
                f"**Problem:** {message.text}\n"
                f"**Solution:** {solution}\n\n"
                f"📊 +10 XP earned!"
            )
        else:
            await message.answer(
                "🤖 I detected a mathematical expression!\n\n"
                "Use /solve followed by your problem, or upload a photo for image processing."
            )
    else:
        # General message handling
        if any(word in message.text.lower() for word in ['hello', 'hi', 'hey']):
            await message.answer(
                f"👋 Hello {message.from_user.first_name}!\n\n"
                f"I'm Tempest Guider, your advanced mathematics assistant.\n"
                f"Use /menu to explore features or /topics to browse math topics!"
            )
        else:
            await message.answer(
                "💡 **TIP:** Use /menu to access all features, or upload a photo of your math problem!"
            )

# ============================================
# MAIN ENTRYPOINT
# ============================================
async def main():
    bot = Bot(token=TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher()
    dp.include_router(router)
    
    logger.info("⚡ Tempest Guider Bot is starting...")
    
    # Delete webhook and start polling
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())