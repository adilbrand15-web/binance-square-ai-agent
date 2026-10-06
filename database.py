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

            rsi REAL,

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

            post_link TEXT,

            outcome TEXT,

            created_at TEXT NOT NULL
        )
    """)

    # =====================================================
    # CHECK EXISTING DATABASE COLUMNS
    # =====================================================

    cursor.execute("""
        PRAGMA table_info(signals)
    """)

    columns = [
        row[1]
        for row in cursor.fetchall()
    ]

    # =====================================================
    # ADD MISSING COLUMNS TO OLD DATABASES
    # =====================================================

    if "selected" not in columns:

        cursor.execute("""
            ALTER TABLE signals
            ADD COLUMN selected INTEGER DEFAULT 0
        """)

    if "rsi" not in columns:

        cursor.execute("""
            ALTER TABLE signals
            ADD COLUMN rsi REAL
        """)

    if "post_link" not in columns:

        cursor.execute("""
            ALTER TABLE signals
            ADD COLUMN post_link TEXT
        """)

    if "published" not in columns:

        cursor.execute("""
            ALTER TABLE signals
            ADD COLUMN published INTEGER DEFAULT 0
        """)

    if "chart_saved" not in columns:

        cursor.execute("""
            ALTER TABLE signals
            ADD COLUMN chart_saved INTEGER DEFAULT 0
        """)

    if "post_id" not in columns:

        cursor.execute("""
            ALTER TABLE signals
            ADD COLUMN post_id TEXT
        """)

    if "outcome" not in columns:

        cursor.execute("""
            ALTER TABLE signals
            ADD COLUMN outcome TEXT
        """)

    conn.commit()
    conn.close()


# =========================================================
# SAVE SIGNAL
# =========================================================

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

            rsi,

            entry,
            stop_loss,

            tp1,
            tp2,
            tp3,

            risk_reward,

            signal_time,

            published,
            selected,
            chart_saved,

            post_id,
            post_link,

            outcome,
            created_at
        )

        VALUES (
            ?, ?, ?,
            ?, ?, ?, ?,
            ?,
            ?, ?,
            ?, ?, ?,
            ?,
            ?,
            ?, ?, ?,
            ?, ?,
            ?,
            ?
        )
    """, (

        signal["symbol"],
        signal["direction"],
        signal["score"],

        signal.get("4h"),
        signal.get("1h"),
        signal.get("15m"),
        signal.get("1m"),

        signal.get("rsi"),

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
        0,

        None,
        None,

        None,

        datetime.utcnow().isoformat()
    ))

    conn.commit()

    signal_id = cursor.lastrowid

    conn.close()

    return signal_id


# =========================================================
# MARK SIGNAL SELECTED
# =========================================================

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


# =========================================================
# MARK SIGNAL PUBLISHED
# =========================================================

def mark_signal_published(
    signal_id,
    post_id=None,
    post_link=None
):

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        UPDATE signals

        SET
            published = 1,
            post_id = ?,
            post_link = ?

        WHERE id = ?
    """, (
        post_id,
        post_link,
        signal_id
    ))

    conn.commit()
    conn.close()


# =========================================================
# MARK CHART SAVED
# =========================================================

def mark_chart_saved(signal_id):

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        UPDATE signals

        SET chart_saved = 1

        WHERE id = ?
    """, (signal_id,))

    conn.commit()
    conn.close()


# =========================================================
# GET SIGNAL
# =========================================================

def get_signal(signal_id):

    conn = get_connection()
    conn.row_factory = sqlite3.Row

    cursor = conn.cursor()

    cursor.execute("""
        SELECT *
        FROM signals
        WHERE id = ?
    """, (signal_id,))

    row = cursor.fetchone()

    conn.close()

    if row:

        return dict(row)

    return None


# =========================================================
# DATABASE TEST
# =========================================================

if __name__ == "__main__":

    initialize_database()

    print(
        "DATABASE INITIALIZED SUCCESSFULLY"
    )