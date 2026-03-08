import os
import logging

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_FILE = os.path.join(BASE_DIR, "app_debug.log")

# 2. НАЛАШТУВАННЯ ЛОГУВАННЯ (ЗМІННА LOG_FILE ВЖЕ ІСНУЄ)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE, mode='w', encoding='utf-8'),
        logging.StreamHandler()
    ]
)

AI_KEY = "YOUR_GEMINI_KEY_HERE"
TELEGRAM_TOKEN = "YOUR_BOT_TOKEN_HERE"
ADMIN_CHAT_ID = 000000000
DB_CONFIG = {'host': 'localhost', 'database': 'path/to/db.fdb', ...}
SOURCE_FOLDER = "img"


