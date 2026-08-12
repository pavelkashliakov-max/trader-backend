import sqlite3
import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo

BOT_TOKEN = os.getenv("BOT_TOKEN", "1234567890:ABCdefGhIJKlmNoPQ")
WEBAPP_URL = os.getenv("WEBAPP_URL", "https://example.com")

app = FastAPI()

# CORS разрешает запросы из Telegram Mini App
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def init_db():
    conn = sqlite3.connect("users.db")
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            xp INTEGER DEFAULT 0,
            coins INTEGER DEFAULT 0,
            energy INTEGER DEFAULT 100,
            current_lesson INTEGER DEFAULT 0,
            streak INTEGER DEFAULT 1,
            clan TEXT DEFAULT 'Нет'
        )
    """)
    conn.commit()
    conn.close()

init_db()

class UserProgress(BaseModel):
    user_id: int
    xp: int
    coins: int
    energy: int
    current_lesson: int
    clan: str

@app.get("/")
def read_root():
    return {"status": "ok", "message": "Trader RPG Backend is running"}

@app.get("/api/user/{user_id}")
def get_user(user_id: int):
    conn = sqlite3.connect("users.db")
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    conn.close()

    if not row:
        conn = sqlite3.connect("users.db")
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO users (user_id, username, xp, coins, energy, current_lesson, streak, clan) VALUES (?, ?, 0, 0, 100, 0, 1, 'Нет')",
            (user_id, "Player")
        )
        conn.commit()
        conn.close()
        return {"user_id": user_id, "xp": 0, "coins": 0, "energy": 100, "current": 0, "clan": "Нет"}

    return {
        "user_id": row["user_id"],
        "xp": row["xp"],
        "coins": row["coins"],
        "energy": row["energy"],
        "current": row["current_lesson"],
        "clan": row["clan"]
    }

@app.post("/api/user/save")
def save_progress(data: UserProgress):
    conn = sqlite3.connect("users.db")
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE users 
        SET xp = ?, coins = ?, energy = ?, current_lesson = ?, clan = ?
        WHERE user_id = ?
    """, (data.xp, data.coins, data.energy, data.current_lesson, data.clan, data.user_id))
    conn.commit()
    conn.close()
    return {"status": "ok"}
