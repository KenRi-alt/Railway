# Railway

# 🌪️ Tempest AI - Local AI Telegram Bot

A powerful local AI Telegram bot powered by Ollama.

## Features
- Local AI processing with Ollama
- Owner/admin commands
- Group chat support with "tempest" trigger
- File exports (logs, users, stats)
- User banning system
- Admin promotion system

## Deployment on Railway

1. Fork this repository
2. Go to [Railway](https://railway.app)
3. Create new project → Deploy from GitHub repo
4. Add environment variables:
   - `BOT_TOKEN` (from @BotFather)
   - `OWNER_ID` (6108185460)
5. Deploy!

## Local Setup
```bash
git clone https://github.com/yourusername/tempest-ai
cd tempest-ai
pip install -r requirements.txt
# Set up Ollama locally
ollama pull llama3
ollama serve
# Run bot
python bot.py
