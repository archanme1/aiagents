import os
import sqlite3
from datetime import date, datetime

from werkzeug.security import generate_password_hash

DB_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "expense_tracker.db",
)


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    conn = get_db()
    try:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                name          TEXT NOT NULL,
                email         TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                created_at    TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS expenses (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id     INTEGER NOT NULL REFERENCES users(id),
                amount      REAL NOT NULL,
                category    TEXT NOT NULL,
                date        TEXT NOT NULL,
                description TEXT,
                created_at  TEXT DEFAULT (datetime('now'))
            );
            """
        )
        conn.commit()
    finally:
        conn.close()


def get_user_by_email(email):
    conn = get_db()
    try:
        return conn.execute(
            "SELECT * FROM users WHERE email = ?",
            (email.strip().lower(),),
        ).fetchone()
    finally:
        conn.close()


def create_user(name, email, password):
    conn = get_db()
    try:
        cursor = conn.execute(
            "INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)",
            (name, email.strip().lower(), generate_password_hash(password)),
        )
        conn.commit()
        return cursor.lastrowid
    finally:
        conn.close()


def seed_db():
    conn = get_db()
    try:
        user_count = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        if user_count > 0:
            return

        cursor = conn.execute(
            "INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)",
            ("Demo User", "demo@spendly.com", generate_password_hash("demo123")),
        )
        user_id = cursor.lastrowid

        today = date.today()

        def day_in_month(day):
            # Keep dates within the current month and never in the future
            return today.replace(day=min(day, today.day)).isoformat()

        sample_expenses = [
            (12.50, "Food", 1, "Groceries"),
            (3.25, "Transport", 3, "Bus fare"),
            (85.00, "Bills", 5, "Electricity bill"),
            (24.99, "Health", 8, "Pharmacy"),
            (15.00, "Entertainment", 10, "Movie ticket"),
            (49.90, "Shopping", 12, "New shoes"),
            (7.00, "Other", 14, None),
            (18.75, "Food", 15, "Dinner out"),
        ]
        conn.executemany(
            "INSERT INTO expenses (user_id, amount, category, date, description) "
            "VALUES (?, ?, ?, ?, ?)",
            [
                (user_id, amount, category, day_in_month(day), description)
                for amount, category, day, description in sample_expenses
            ],
        )
        conn.commit()
    finally:
        conn.close()


# ------------------------------------------------------------------ #
# Profile page queries                                                #
# ------------------------------------------------------------------ #

# ===== SHARED (orchestrator-owned — do not edit) =====

KNOWN_CATEGORIES = {
    "food",
    "transport",
    "bills",
    "health",
    "entertainment",
    "shopping",
    "other",
}


def category_slug(name):
    slug = (name or "").strip().lower()
    return slug if slug in KNOWN_CATEGORIES else "other"


def format_inr(amount):
    return f"₹{amount:,.2f}"


def get_user_by_id(user_id):
    conn = get_db()
    try:
        row = conn.execute(
            "SELECT name, email, created_at FROM users WHERE id = ?",
            (user_id,),
        ).fetchone()
    finally:
        conn.close()

    if row is None:
        return None

    initials = "".join(part[0] for part in row["name"].split()[:2]).upper()
    try:
        member_since = datetime.strptime(
            row["created_at"], "%Y-%m-%d %H:%M:%S"
        ).strftime("%B %Y")
    except (TypeError, ValueError):
        member_since = "—"

    return {
        "name": row["name"],
        "email": row["email"],
        "initials": initials,
        "member_since": member_since,
    }


# ===== SECTION: TRANSACTIONS (subagent 1) =====

def get_recent_transactions(user_id, limit=10):
    """Return the user's newest expenses as a list of dicts.

    Keys: date ("15 Oct 2026"), description (None -> "—"), category,
    badge (category_slug), amount (format_inr). Ordered date DESC, id DESC.
    """
    conn = get_db()
    try:
        rows = conn.execute(
            "SELECT date, description, category, amount FROM expenses "
            "WHERE user_id = ? ORDER BY date DESC, id DESC LIMIT ?",
            (user_id, limit),
        ).fetchall()
    finally:
        conn.close()

    return [
        {
            "date": datetime.strptime(row["date"], "%Y-%m-%d").strftime("%d %b %Y"),
            "description": row["description"] or "—",
            "category": row["category"],
            "badge": category_slug(row["category"]),
            "amount": format_inr(row["amount"]),
        }
        for row in rows
    ]


# ===== SECTION: SUMMARY STATS (subagent 2) =====

def get_summary_stats(user_id):
    """Return {"total_spent": float, "transaction_count": int, "top_category": str}.

    No expenses -> {"total_spent": 0, "transaction_count": 0, "top_category": "—"}.
    """
    conn = get_db()
    try:
        totals = conn.execute(
            "SELECT COUNT(*) AS cnt, COALESCE(SUM(amount), 0) AS total "
            "FROM expenses WHERE user_id = ?",
            (user_id,),
        ).fetchone()
        top = conn.execute(
            "SELECT category FROM expenses WHERE user_id = ? "
            "GROUP BY category ORDER BY SUM(amount) DESC, category ASC LIMIT 1",
            (user_id,),
        ).fetchone()
    finally:
        conn.close()

    if totals["cnt"] == 0 or top is None:
        return {"total_spent": 0, "transaction_count": 0, "top_category": "—"}

    return {
        "total_spent": float(totals["total"]),
        "transaction_count": int(totals["cnt"]),
        "top_category": top["category"],
    }


# ===== SECTION: CATEGORY BREAKDOWN (subagent 3) =====

def get_category_breakdown(user_id):
    """Return per-category totals as a list of dicts.

    Keys: name, amount (float), pct (int, all pct sum to 100), badge.
    Ordered amount DESC, name ASC. No expenses -> [].
    """
    conn = get_db()
    try:
        rows = conn.execute(
            "SELECT category, SUM(amount) AS amount FROM expenses "
            "WHERE user_id = ? GROUP BY category "
            "ORDER BY amount DESC, category ASC",
            (user_id,),
        ).fetchall()
    finally:
        conn.close()

    total = sum(row["amount"] for row in rows)
    breakdown = [
        {
            "name": row["category"],
            "amount": float(row["amount"]),
            "pct": round(row["amount"] / total * 100) if total else 0,
            "badge": category_slug(row["category"]),
        }
        for row in rows
    ]
    if breakdown and total:
        breakdown[0]["pct"] += 100 - sum(item["pct"] for item in breakdown)
    return breakdown
