import sqlite3
import os
from datetime import datetime, timedelta
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

DB_PATH = "/tmp/users.db" if os.path.exists("/tmp") else "users.db"

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            xp INTEGER DEFAULT 0,
            coins INTEGER DEFAULT 0,
            energy INTEGER DEFAULT 100,
            max_energy INTEGER DEFAULT 100,
            current_lesson INTEGER DEFAULT 0,
            streak INTEGER DEFAULT 0,
            last_login TEXT,
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
    energy: int = 100
    max_energy: int = 100
    current_lesson: int
    streak: int = 0
    clan: str = "Нет"

@app.get("/")
def root():
    return {"status": "ok", "message": "Trader RPG Economy API Online"}

@app.get("/api/user/{user_id}")
def get_user(user_id: int):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    
    today_str = datetime.utcnow().strftime("%Y-%m-%d")
    
    if not row:
        cursor.execute(
            "INSERT INTO users (user_id, username, xp, coins, energy, max_energy, current_lesson, streak, last_login, clan) VALUES (?, 'Player', 0, 0, 100, 100, 0, 1, ?, 'Нет')",
            (user_id, today_str)
        )
        conn.commit()
        conn.close()
        return {
            "user_id": user_id, "xp": 0, "coins": 0, "energy": 100, "max_energy": 100,
            "current": 0, "streak": 1, "last_login": today_str, "clan": "Нет"
        }
    
    # Расчет стриков
    last_login_str = row["last_login"]
    streak = row["streak"] or 0
    energy = row["energy"]
    max_energy = row["max_energy"] or 100
    
    if last_login_str:
        last_date = datetime.strptime(last_login_str, "%Y-%m-%d").date()
        today = datetime.utcnow().date()
        diff = (today - last_date).days
        
        if diff == 1:
            streak += 1
            cursor.execute("UPDATE users SET streak = ?, last_login = ? WHERE user_id = ?", (streak, today_str, user_id))
        elif diff > 1:
            streak = 1
            cursor.execute("UPDATE users SET streak = ?, last_login = ? WHERE user_id = ?", (streak, today_str, user_id))
        conn.commit()

    conn.close()
    
    return {
        "user_id": row["user_id"],
        "xp": row["xp"],
        "coins": row["coins"],
        "energy": energy,
        "max_energy": max_energy,
        "current": row["current_lesson"],
        "streak": streak,
        "clan": row["clan"]
    }

@app.post("/api/user/save")
def save_progress(data: UserProgress):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    today_str = datetime.utcnow().strftime("%Y-%m-%d")
    
    cursor.execute("""
        UPDATE users 
        SET xp = ?, coins = ?, energy = ?, max_energy = ?, current_lesson = ?, streak = ?, clan = ?, last_login = ?
        WHERE user_id = ?
    """, (data.xp, data.coins, data.energy, data.max_energy, data.current_lesson, data.streak, data.clan, today_str, data.user_id))
    
    if cursor.rowcount == 0:
        cursor.execute("""
            INSERT INTO users (user_id, username, xp, coins, energy, max_energy, current_lesson, streak, clan, last_login)
            VALUES (?, 'Player', ?, ?, ?, ?, ?, ?, ?, ?)
        """, (data.user_id, data.xp, data.coins, data.energy, data.max_energy, data.current_lesson, data.streak, data.clan, today_str))
        
    conn.commit()
    conn.close()
    return {"status": "ok"}
