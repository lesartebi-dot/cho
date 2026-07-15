import sqlite3
from datetime import datetime
from contextlib import contextmanager

DB_PATH = "bot.db"


@contextmanager
def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    with get_conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                username TEXT,
                summary TEXT NOT NULL,
                contact TEXT,
                status TEXT DEFAULT 'new',
                created_at TEXT,
                reminded_at TEXT,
                appointment_at TEXT,
                pre_visit_reminded_at TEXT,
                review_requested_at TEXT
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at TEXT
            )
        """)
        # Миграция для баз, созданных предыдущей версией бота
        existing_cols = {row["name"] for row in conn.execute("PRAGMA table_info(orders)")}
        for col in ("appointment_at", "pre_visit_reminded_at", "review_requested_at"):
            if col not in existing_cols:
                conn.execute(f"ALTER TABLE orders ADD COLUMN {col} TEXT")


def save_order(user_id: int, username: str, summary: str, contact: str = None, appointment_at: str = None):
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO orders (user_id, username, summary, contact, created_at, appointment_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (user_id, username, summary, contact, datetime.utcnow().isoformat(), appointment_at)
        )
        return conn.execute("SELECT last_insert_rowid() AS id").fetchone()["id"]


def get_pending_orders_older_than(hours: int):
    with get_conn() as conn:
        cur = conn.execute(
            """SELECT * FROM orders
               WHERE status = 'new'
               AND reminded_at IS NULL
               AND datetime(created_at) <= datetime('now', ?)""",
            (f"-{hours} hours",)
        )
        return cur.fetchall()


def mark_reminded(order_id: int):
    with get_conn() as conn:
        conn.execute(
            "UPDATE orders SET reminded_at = ? WHERE id = ?",
            (datetime.utcnow().isoformat(), order_id)
        )


def mark_confirmed(order_id: int):
    with get_conn() as conn:
        conn.execute("UPDATE orders SET status = 'confirmed' WHERE id = ?", (order_id,))


def set_appointment(order_id: int, appointment_at_iso: str):
    """Админ вручную подтверждает точное время визита (командой /confirm)."""
    with get_conn() as conn:
        conn.execute(
            "UPDATE orders SET appointment_at = ?, status = 'confirmed' WHERE id = ?",
            (appointment_at_iso, order_id)
        )


def get_order(order_id: int):
    with get_conn() as conn:
        return conn.execute("SELECT * FROM orders WHERE id = ?", (order_id,)).fetchone()


def get_appointments_needing_pre_visit_reminder(hours_before: int):
    """Записи со статусом confirmed, до которых осталось <= hours_before часов, и напоминание ещё не отправлено."""
    with get_conn() as conn:
        cur = conn.execute(
            """SELECT * FROM orders
               WHERE status = 'confirmed'
               AND appointment_at IS NOT NULL
               AND pre_visit_reminded_at IS NULL
               AND datetime(appointment_at) <= datetime('now', ?)
               AND datetime(appointment_at) > datetime('now')""",
            (f"+{hours_before} hours",)
        )
        return cur.fetchall()


def mark_pre_visit_reminded(order_id: int):
    with get_conn() as conn:
        conn.execute(
            "UPDATE orders SET pre_visit_reminded_at = ? WHERE id = ?",
            (datetime.utcnow().isoformat(), order_id)
        )


def get_appointments_needing_review(hours_after: int):
    """Записи, визит по которым уже прошёл (>= hours_after часов назад), отзыв ещё не запрашивали."""
    with get_conn() as conn:
        cur = conn.execute(
            """SELECT * FROM orders
               WHERE status = 'confirmed'
               AND appointment_at IS NOT NULL
               AND review_requested_at IS NULL
               AND datetime(appointment_at) <= datetime('now', ?)""",
            (f"-{hours_after} hours",)
        )
        return cur.fetchall()


def mark_review_requested(order_id: int):
    with get_conn() as conn:
        conn.execute(
            "UPDATE orders SET review_requested_at = ? WHERE id = ?",
            (datetime.utcnow().isoformat(), order_id)
        )


def save_message(user_id: int, role: str, content: str):
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO messages (user_id, role, content, created_at) VALUES (?, ?, ?, ?)",
            (user_id, role, content, datetime.utcnow().isoformat())
        )


def get_history(user_id: int, limit: int = 12):
    with get_conn() as conn:
        cur = conn.execute(
            "SELECT role, content FROM messages WHERE user_id = ? ORDER BY id DESC LIMIT ?",
            (user_id, limit)
        )
        rows = cur.fetchall()
        return list(reversed([{"role": r["role"], "content": r["content"]} for r in rows]))
