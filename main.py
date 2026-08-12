import sqlite3
import os
import random
from datetime import datetime, timezone
from typing import Optional, List
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
    # Таблица пройденных фаз
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS completed_phases (
            user_id INTEGER,
            phase_id TEXT,
            completed_at TEXT,
            PRIMARY KEY (user_id, phase_id)
        )
    """)
    conn.commit()
    conn.close()

init_db()

# База фаз обучения (120-дневный план)
PHASES_DATA = {
    "phase_00": {
        "id": "phase_00",
        "title": "Phase 00 · Механика рынка и Ордера",
        "energy_cost": 10,
        "theory": {
            "fact": "Маркет-ордер исполняется мгновенно по стакану, снимая комиссию Taker. Лимитный ордер добавляет ликвидность в стакан (Maker).",
            "interpretation": "При резком всплеске Taker-покупок цена импульсивно растет, пробивая ближайшие лимитные уровни.",
            "hypothesis": "Торговать против импульса без подтверждения лимитным плотным уровнем опасным."
        },
        "quiz": {
            "question": "Что происходит при исполнении Market-Buy ордера?",
            "options": [
                "Он мгновенно выедает ближайшие Sell-лимиты из стакана (Taker)",
                "Он встает в очередь в стакане и ждет исполнения (Maker)",
                "Он гарантированно исполняется без комиссии"
            ],
            "correct_index": 0
        },
        "reward": {"coins": 150, "xp": 50}
    },
    "phase_01": {
        "id": "phase_01",
        "title": "Phase 01 · Свечной анализ и Механика OHLC",
        "energy_cost": 10,
        "theory": {
            "fact": "Длинная верхняя тень свечи означает, что покупатели толкали цену вверх, но продавцы полностью вернули её назад.",
            "interpretation": "На вершине свечи произошла агрессивная реакция продавцов или сброс позиций.",
            "hypothesis": "Высокая вероятность продолжения нисходящего движения или флэта."
        },
        "quiz": {
            "question": "О чем указывает длинная верхняя тень свечи при подходе к сопротивлению?",
            "options": [
                "О слабой активности продавцов",
                "О сильном отпоре продавцов и возможной защите уровня",
                "О гарантированном пробое уровня вверх"
            ],
            "correct_index": 1
        },
        "reward": {"coins": 200, "xp": 70}
    },
    "phase_04": {
        "id": "phase_04",
        "title": "Phase 04 · Ликвидность и Sweeps",
        "energy_cost": 15,
        "theory": {
            "fact": "Цена резко вышла за пределы равных максимумов (EQH) и мгновенно вернулась обратно под уровень.",
            "interpretation": "Произошло снятие ликвидности (Liquidity Sweep) — крупный игрок исполнил свои ордера об стоп-лоссы розничных трейдеров.",
            "hypothesis": "Заходить в SHORT-позицию после подтверждения возврата цены под уровень."
        },
        "quiz": {
            "question": "Какова главная цель захода цены за каскад равных максимумов (EQH)?",
            "options": [
                "Сбор ликвидности (стоп-лоссов) крупным участником",
                "Технический сбой торгового терминала",
                "Начало долгосрочного бычьего тренда"
            ],
            "correct_index": 0
        },
        "reward": {"coins": 300, "xp": 100}
    }
}

class QuizAnswerRequest(BaseModel):
    user_id: int
    phase_id: str
    selected_option: int

@app.get("/api/phases/{user_id}")
def get_user_phases(user_id: int):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT phase_id FROM completed_phases WHERE user_id = ?", (user_id,))
    completed = [r["phase_id"] for r in cursor.fetchall()]
    conn.close()

    result = []
    for p_id, p_data in PHASES_DATA.items():
        item = {
            "id": p_id,
            "title": p_data["title"],
            "energy_cost": p_data["energy_cost"],
            "theory": p_data["theory"],
            "question": p_data["quiz"]["question"],
            "options": p_data["quiz"]["options"],
            "reward": p_data["reward"],
            "is_completed": p_id in completed
        }
        result.append(item)
        
    return {"phases": result}

@app.post("/api/phases/complete")
def complete_phase(req: QuizAnswerRequest):
    phase = PHASES_DATA.get(req.phase_id)
    if not phase:
        raise HTTPException(status_code=404, detail="Фаза не найдена")

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT coins, xp, energy FROM users WHERE user_id = ?", (req.user_id,))
    user = cursor.fetchone()

    if not user:
        conn.close()
        raise HTTPException(status_code=404, detail="Пользователь не найден")

    if user["energy"] < phase["energy_cost"]:
        conn.close()
        return {"success": False, "message": "Недостаточно энергии!"}

    # Проверка ответа
    if req.selected_option != phase["quiz"]["correct_index"]:
        conn.close()
        return {"success": False, "message": "Неверный ответ! Перечитайте триаду (Факт-Интерпретация-Гипотеза) и попробуйте снова."}

    # Проверка на повторное прохождение
    cursor.execute("SELECT 1 FROM completed_phases WHERE user_id = ? AND phase_id = ?", (req.user_id, req.phase_id))
    already_done = cursor.fetchone()

    new_energy = user["energy"] - phase["energy_cost"]
    new_coins = user["coins"]
    new_xp = user["xp"]

    if not already_done:
        new_coins += phase["reward"]["coins"]
        new_xp += phase["reward"]["xp"]
        now_str = datetime.now(timezone.utc).isoformat()
        cursor.execute("INSERT INTO completed_phases (user_id, phase_id, completed_at) VALUES (?, ?, ?)",
                       (req.user_id, req.phase_id, now_str))

    cursor.execute("""
        UPDATE users 
        SET energy = ?, coins = ?, xp = ?, current_lesson = current_lesson + 1 
        WHERE user_id = ?
    """, (new_energy, new_coins, new_xp, req.user_id))

    conn.commit()
    conn.close()

    return {
        "success": True,
        "message": "Уровень пройден!" if not already_done else "Тест пройден повторно (без повторного зачисления монет)",
        "coins": new_coins,
        "xp": new_xp,
        "energy": new_energy
    }
