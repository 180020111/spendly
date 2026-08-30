import os
import sqlite3
from datetime import date, timedelta

from werkzeug.security import generate_password_hash

DB_PATH = os.path.normpath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "expense_tracker.db")
)

CATEGORIES = ["Food", "Transport", "Bills", "Health", "Entertainment", "Shopping", "Other"]


def get_db():
    """Open a new SQLite connection with row access and FK enforcement."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    """Create tables if missing. Safe to call on every startup."""
    conn = get_db()
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                email TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                created_at TEXT DEFAULT (datetime('now'))
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS expenses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                amount REAL NOT NULL,
                category TEXT NOT NULL,
                date TEXT NOT NULL,
                description TEXT,
                created_at TEXT DEFAULT (datetime('now')),
                FOREIGN KEY (user_id) REFERENCES users (id)
            )
        """)
        conn.commit()
    finally:
        conn.close()


def _last_day_of_month(year, month):
    next_month_first = date(year + 1, 1, 1) if month == 12 else date(year, month + 1, 1)
    return (next_month_first - timedelta(days=1)).day


def seed_db():
    """Insert one demo user + 8 sample expenses, only if users table is empty."""
    conn = get_db()
    try:
        if conn.execute("SELECT COUNT(*) AS n FROM users").fetchone()["n"] > 0:
            return

        password_hash = generate_password_hash("demo123")
        cursor = conn.execute(
            "INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)",
            ("Demo User", "demo@spendly.com", password_hash),
        )
        user_id = cursor.lastrowid

        today = date.today()
        last_day = _last_day_of_month(today.year, today.month)
        sample_expenses = [
            (35.50, "Food", 2, "Groceries"),
            (12.00, "Transport", 4, "Bus pass top-up"),
            (89.99, "Bills", 5, "Electricity bill"),
            (45.00, "Health", 8, "Pharmacy"),
            (22.75, "Entertainment", 11, "Movie tickets"),
            (60.20, "Shopping", 14, "New shoes"),
            (15.00, "Other", 17, "Miscellaneous"),
            (8.50, "Food", 20, "Coffee and lunch"),
        ]
        for amount, category, day_offset, description in sample_expenses:
            expense_date = date(today.year, today.month, min(day_offset, last_day)).isoformat()
            conn.execute(
                "INSERT INTO expenses (user_id, amount, category, date, description) "
                "VALUES (?, ?, ?, ?, ?)",
                (user_id, amount, category, expense_date, description),
            )
        conn.commit()
    finally:
        conn.close()