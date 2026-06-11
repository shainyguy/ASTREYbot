import os
from typing import List
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN: str = os.getenv("BOT_TOKEN", "")
ADMIN_PASSWORD: str = os.getenv("ADMIN_PASSWORD", "ASTREYKIRILL")
ADMIN_IDS: List[int] = [
    int(x.strip()) for x in os.getenv("ADMIN_IDS", "574947799").split(",") if x.strip()
]

GIGACHAT_AUTH_KEY: str = os.getenv("GIGACHAT_AUTH_KEY", "")
GIGACHAT_CLIENT_ID: str = os.getenv("GIGACHAT_CLIENT_ID", "")
GIGACHAT_CLIENT_SECRET: str = os.getenv("GIGACHAT_CLIENT_SECRET", "")
GIGACHAT_SCOPE: str = os.getenv("GIGACHAT_SCOPE", "GIGACHAT_API_PERS")

DATABASE_PATH: str = os.getenv("DATABASE_PATH", "/data/astreybot.db")

VK_TOKEN: str = os.getenv("VK_TOKEN", "")
VK_GROUP_ID: int = int(os.getenv("VK_GROUP_ID", "0"))

WEBSITE_URL: str = "https://astreys.ru"

AI_CONFUSION_THRESHOLD: int = 3
MAX_HISTORY_MESSAGES: int = 12
