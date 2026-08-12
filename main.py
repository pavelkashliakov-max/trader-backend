import sqlite3
import os
import random
from datetime import datetime, timezone
from typing import Optional
from fastapi import FastAPI, HTTPException
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

# Храним базу локально в директории проекта, а не во временном /tmp/
DB_PATH = os.path.join(os.path.dirname(__file__), "users.db")

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            xp INTEGER DEFAULT 0,
            coins INTEGER DEFAULT 0,
            sim_balance REAL DEFAULT 10000.0,
            energy INTEGER DEFAULT 100,
            max_energy INTEGER DEFAULT 100,
            current_lesson INTEGER DEFAULT 0,
            streak INTEGER DEFAULT 0,
            last_login TEXT,
            clan TEXT DEFAULT 'Нет',
            referrer_id INTEGER DEFAULT NULL,
            title TEXT DEFAULT 'Новичок',
            theme TEXT DEFAULT 'neon',
            pvp_wins INTEGER DEFAULT 0,
            claimed_daily_day INTEGER DEFAULT 0,
            last_daily_claim TEXT DEFAULT '',
            last_energy_update TEXT
        )
    """)
    conn.commit()
    conn.close()

init_db()

class UserProgress(BaseModel):
    user_id: int
    username: str = "Player"
    xp: int
    coins: int
    sim_balance: float = 10000.0
    energy: int = 100
    max_energy: int = 100
    current_lesson: int
    streak: int = 0
    clan: str = "Нет"
    referrer_id: Optional[int] = None
    title: str = "Новичок"
    theme: str = "neon"
    pvp_wins: int = 0

class PvpBattleRequest(BaseModel):
    user_id: int
    bet: float

class BuyItemRequest(BaseModel):
    user_id: int
    item_type: str  # 'energy' или 'max_energy'
    cost: int
    value: int

@app.get("/")
def root():
    return {"status": "ok", "message": "Trader RPG API Online"}

def apply_energy_regen(row, conn):
    """Автоматическая регенерация энергии: +1 ⚡ за каждые 3 минуты (180 секунд)"""
    user_id = row["user_id"]
    current_energy = row["energy"]
    max_energy = row["max_energy"] or 100
    last_update_str = row["last_energy_update"]
    
    now = datetime.now(timezone.utc)
    now_str = now.isoformat()

    if not last_update_str:
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET last_energy_update = ? WHERE user_id = ?", (now_str, user_id))
        conn.commit()
        return current_energy

    last_update = datetime.fromisoformat(last_update_str)
    seconds_passed = (now - last_update).total_seconds()
    
    REGEN_INTERVAL = 180  # 3 минуты
    energy_to_add = int(seconds_passed // REGEN_INTERVAL)

    if energy_to_add > 0 and current_energy < max_energy:
        new_energy = min(max_energy, current_energy + energy_to_add)
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE users SET energy = ?, last_energy_update = ? WHERE user_id = ?",
            (new_energy, now_str, user_id)
        )
        conn.commit()
        return new_energy

    return current_energy

@app.get("/api/user/{user_id}")
def get_user(user_id: int, ref: Optional[int] = None):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    
    today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    now_iso = datetime.now(timezone.utc).isoformat()
    
    if not row:
        initial_coins = 0
        referrer = None
        
        if ref and ref != user_id:
            cursor.execute("SELECT user_id FROM users WHERE user_id = ?", (ref,))
            if cursor.fetchone():
                referrer = ref
                initial_coins = 250
                cursor.execute("""
                    UPDATE users 
                    SET coins = coins + 500, xp = xp + 50 
                    WHERE user_id = ?
                """, (ref,))

        cursor.execute(
            """INSERT INTO users 
               (user_id, username, xp, coins, sim_balance, energy, max_energy, current_lesson, streak, last_login, clan, referrer_id, title, theme, pvp_wins, last_energy_update) 
               VALUES (?, 'Трейдер', 0, ?, 10000.0, 100, 100, 0, 1, ?, 'Нет', ?, 'Новичок', 'neon', 0, ?)""",
            (user_id, initial_coins, today_str, referrer, now_iso)
        )
        conn.commit()
        cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
        row = cursor.fetchone()

    # Проверка стрика
    last_login_str = row["last_login"]
    streak = row["streak"] or 0
    if last_login_str:
        last_date = datetime.strptime(last_login_str, "%Y-%m-%d").date()
        today = datetime.now(timezone.utc).date()
        diff = (today - last_date).days
        
        if diff == 1:
            streak += 1
            cursor.execute("UPDATE users SET streak = ?, last_login = ? WHERE user_id = ?", (streak, today_str, user_id))
        elif diff > 1:
            streak = 1
            cursor.execute("UPDATE users SET streak = ?, last_login = ? WHERE user_id = ?", (streak, today_str, user_id))
        conn.commit()

    current_energy = apply_energy_regen(row, conn)
    conn.close()
    
    return {
        "user_id": row["user_id"],
        "username": row["username"] or "Трейдер",
        "xp": row["xp"],
        "coins": row["coins"],
        "sim_balance": row["sim_balance"] or 10000.0,
        "energy": current_energy,
        "max_energy": row["max_energy"] or 100,
        "current": row["current_lesson"],
        "streak": streak,
        "clan": row["clan"],
        "referrer_id": row["referrer_id"],
        "title": row["title"] or "Новичок",
        "theme": row["theme"] or "neon",
        "pvp_wins": row["pvp_wins"] or 0,
        "claimed_daily_day": row["claimed_daily_day"] or 0,
        "last_daily_claim": row["last_daily_claim"] or ""
    }

@app.post("/api/user/claim_daily")
def claim_daily(user_id: int):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="User not found")
        
    today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    last_claim = row["last_daily_claim"] or ""
    
    if last_claim == today_str:
        conn.close()
        return {"status": "already_claimed"}
        
    current_day = (row["claimed_daily_day"] or 0) % 7 + 1
    
    rewards = {
        1: {"coins": 100, "xp": 20},
        2: {"coins": 200, "xp": 40},
        3: {"coins": 300, "xp": 60},
        4: {"coins": 500, "xp": 80},
        5: {"coins": 750, "xp": 100},
        6: {"coins": 1000, "xp": 150},
        7: {"coins": 2500, "xp": 300}
    }
    rew = rewards[current_day]
    
    cursor.execute("""
        UPDATE users 
        SET coins = coins + ?, xp = xp + ?, claimed_daily_day = ?, last_daily_claim = ?
        WHERE user_id = ?
    """, (rew["coins"], rew["xp"], current_day, today_str, user_id))
    
    conn.commit()
    conn.close()
    return {"status": "ok", "day": current_day, "reward": rew}

@app.post("/api/pvp/match")
def pvp_match(req: PvpBattleRequest):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT coins FROM users WHERE user_id = ?", (req.user_id,))
    row = cursor.fetchone()

    if not row or row["coins"] < req.bet:
        conn.close()
        raise HTTPException(status_code=400, detail="Недостаточно монет для дуэли")

    player_score = random.uniform(-3.0, 8.0)
    bot_score = random.uniform(-2.0, 6.0)
    
    win = player_score > bot_score
    reward = req.bet if win else -req.bet
    
    if win:
        cursor.execute("UPDATE users SET coins = coins + ?, xp = xp + 30, pvp_wins = pvp_wins + 1 WHERE user_id = ?", (req.bet, req.user_id))
    else:
        cursor.execute("UPDATE users SET coins = coins - ? WHERE user_id = ?", (req.bet, req.user_id))
        
    conn.commit()
    conn.close()
    
    return {
        "win": win,
        "player_pnl": round(player_score, 2),
        "opponent_pnl": round(bot_score, 2),
        "reward": reward
    }

@app.post("/api/user/buy_item")
def buy_item(req: BuyItemRequest):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT coins, energy, max_energy FROM users WHERE user_id = ?", (req.user_id,))
    row = cursor.fetchone()

    if not row or row["coins"] < req.cost:
        conn.close()
        raise HTTPException(status_code=400, detail="Недостаточно монет")

    new_coins = row["coins"] - req.cost
    new_energy = row["energy"]
    new_max_energy = row["max_energy"]

    if req.item_type == 'energy':
        new_energy = min(new_max_energy, new_energy + req.value)
    elif req.item_type == 'max_energy':
        new_max_energy += req.value
        new_energy += req.value

    cursor.execute("""
        UPDATE users SET coins = ?, energy = ?, max_energy = ? WHERE user_id = ?
    """, (new_coins, new_energy, new_max_energy, req.user_id))

    conn.commit()
    conn.close()

    return {"status": "ok", "coins": new_coins, "energy": new_energy, "max_energy": new_max_energy}

@app.get("/api/referrals/{user_id}")
def get_referrals(user_id: int):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT user_id, username, xp, current_lesson 
        FROM users 
        WHERE referrer_id = ?
    """, (user_id,))
    rows = cursor.fetchall()
    conn.close()
    
    result = [{
        "user_id": r["user_id"],
        "username": r["username"] or f"Player #{r['user_id'] % 10000}",
        "xp": r["xp"],
        "current": r["current_lesson"]
    } for r in rows]
    
    return {"count": len(result), "referrals": result}

@app.get("/api/leaderboard")
def get_leaderboard():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT user_id, username, xp, streak, current_lesson, clan, title 
        FROM users 
        ORDER BY xp DESC 
        LIMIT 50
    """)
    rows = cursor.fetchall()
    conn.close()
    
    result = [{
        "user_id": r["user_id"],
        "username": r["username"] or f"Player #{r['user_id'] % 10000}",
        "xp": r["xp"],
        "streak": r["streak"] or 1,
        "current": r["current_lesson"],
        "clan": r["clan"] or "Нет",
        "title": r["title"] or "Новичок"
    } for r in rows]
    
    return result

@app.post("/api/user/save")
def save_progress(data: UserProgress):
    conn = get_db()
    cursor = conn.cursor()
    today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    
    cursor.execute("""
        UPDATE users 
        SET username = ?, xp = ?, coins = ?, sim_balance = ?, energy = ?, max_energy = ?, current_lesson = ?, streak = ?, clan = ?, title = ?, theme = ?, pvp_wins = ?, last_login = ?
        WHERE user_id = ?
    """, (
        data.username, data.xp, data.coins, data.sim_balance, 
        data.energy, data.max_energy, data.current_lesson, 
        data.streak, data.clan, data.title, data.theme, 
        data.pvp_wins, today_str, data.user_id
    ))
    
    conn.commit()
    conn.close()
    return {"status": "ok"}
