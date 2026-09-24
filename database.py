import sqlite3
from datetime import datetime


DB_NAME = "signals.db"


def get_connection():
    return sqlite3.connect(DB_NAME)


def initialize_database():

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS signals (

            id INTEGER PRIMARY KEY AUTOINCREMENT,

            symbol TEXT NOT NULL,
            direction TEXT NOT NULL,

            score INTEGER NOT NULL,

            timeframe_4h TEXT,
            timeframe_1h TEXT,
            timeframe_15m TEXT,
            timeframe_1m TEXT,

            entry REAL,
            stop_loss REAL,

            tp1 REAL,
            tp2 REAL,
            tp3 REAL,

            risk_reward TEXT,

            signal_time TEXT NOT NULL,

            published INTEGER DEFAULT 0,

            selected INTEGER DEFAULT 0,

            chart_saved INTEGER DEFAULT 0,

            post_id TEXT,

            outcome TEXT,

            created_at TEXT NOT NULL
        )
    """)

    conn.commit()
    conn.close()


def save_signal(signal):

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO signals (
            symbol,
            direction,
            score,
            timeframe_4h,
            timeframe_1h,
            timeframe_15m,
            timeframe_1m,
            entry,
            stop_loss,
            tp1,
            tp2,
            tp3,
            risk_reward,
            signal_time,
            published,
            chart_saved,
            post_id,
            outcome,
            created_at
        )

        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (

        signal["symbol"],
        signal["direction"],
        signal["score"],

        signal.get("4h"),
        signal.get("1h"),
        signal.get("15m"),
        signal.get("1m"),

        signal["entry"],
        signal["stop_loss"],

        signal["tp1"],
        signal["tp2"],
        signal["tp3"],

        signal["risk_reward"],

        signal.get(
            "signal_time",
            datetime.utcnow().isoformat()
        ),

        0,
        0,
        None,
        None,

        datetime.utcnow().isoformat()
    ))

    conn.commit()

    signal_id = cursor.lastrowid

    conn.close()

    return signal_id

def mark_signal_selected(signal_id):

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        UPDATE signals
        SET selected = 1
        WHERE id = ?
    """, (signal_id,))

    conn.commit()
    conn.close()


if __name__ == "__main__":

    initialize_database()

    print(
        "DATABASE INITIALIZED SUCCESSFULLY"
    )