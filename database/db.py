import os
import sqlite3
from datetime import date, datetime

from werkzeug.security import generate_password_hash

DB_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "expense_tracker.db",
)

CATEGORIES = [
    "Food",
    "Transport",
    "Bills",
    "Health",
    "Entertainment",
    "Shopping",
    "Other",
]


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


def insert_expense(user_id, amount, category, date, description):
    conn = get_db()
    try:
        cursor = conn.execute(
            "INSERT INTO expenses (user_id, amount, category, date, description) "
            "VALUES (?, ?, ?, ?, ?)",
            (user_id, amount, category, date, description),
        )
        conn.commit()
        return cursor.lastrowid
    finally:
        conn.close()


def get_expense_by_id(expense_id, user_id):
    """Return the expense as a dict, or None if missing or owned by another user."""
    conn = get_db()
    try:
        row = conn.execute(
            "SELECT id, amount, category, date, description FROM expenses "
            "WHERE id = ? AND user_id = ?",
            (expense_id, user_id),
        ).fetchone()
    finally:
        conn.close()

    return dict(row) if row else None


def update_expense(expense_id, user_id, amount, category, date, description):
    """Update an expense; return True if a row owned by user_id was changed."""
    conn = get_db()
    try:
        cursor = conn.execute(
            "UPDATE expenses SET amount = ?, category = ?, date = ?, description = ? "
            "WHERE id = ? AND user_id = ?",
            (amount, category, date, description, expense_id, user_id),
        )
        conn.commit()
        return cursor.rowcount > 0
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


def _date_clause(date_from, date_to):
    """Return (sql_fragment, params) restricting expenses to an inclusive range.

    Both bounds are required; otherwise no restriction is applied.
    """
    if date_from and date_to:
        return " AND date BETWEEN ? AND ?", [date_from, date_to]
    return "", []


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

def get_recent_transactions(user_id, limit=10, date_from=None, date_to=None):
    """Return the user's newest expenses as a list of dicts.

    Keys: id, date ("15 Oct 2026"), description (None -> "—"), category,
    badge (category_slug), amount (format_inr). Ordered date DESC, id DESC.
    Optionally restricted to an inclusive ISO date range.
    """
    clause, params = _date_clause(date_from, date_to)
    conn = get_db()
    try:
        rows = conn.execute(
            "SELECT id, date, description, category, amount FROM expenses "
            "WHERE user_id = ?" + clause + " ORDER BY date DESC, id DESC LIMIT ?",
            (user_id, *params, limit),
        ).fetchall()
    finally:
        conn.close()

    return [
        {
            "id": row["id"],
            "date": datetime.strptime(row["date"], "%Y-%m-%d").strftime("%d %b %Y"),
            "description": row["description"] or "—",
            "category": row["category"],
            "badge": category_slug(row["category"]),
            "amount": format_inr(row["amount"]),
        }
        for row in rows
    ]


# ===== SECTION: SUMMARY STATS (subagent 2) =====

def get_summary_stats(user_id, date_from=None, date_to=None):
    """Return {"total_spent": float, "transaction_count": int, "top_category": str}.

    No expenses -> {"total_spent": 0, "transaction_count": 0, "top_category": "—"}.
    Optionally restricted to an inclusive ISO date range.
    """
    clause, params = _date_clause(date_from, date_to)
    conn = get_db()
    try:
        totals = conn.execute(
            "SELECT COUNT(*) AS cnt, COALESCE(SUM(amount), 0) AS total "
            "FROM expenses WHERE user_id = ?" + clause,
            (user_id, *params),
        ).fetchone()
        top = conn.execute(
            "SELECT category FROM expenses WHERE user_id = ?" + clause
            + " GROUP BY category ORDER BY SUM(amount) DESC, category ASC LIMIT 1",
            (user_id, *params),
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

def get_category_breakdown(user_id, date_from=None, date_to=None):
    """Return per-category totals as a list of dicts.

    Keys: name, amount (float), pct (int, all pct sum to 100), badge.
    Ordered amount DESC, name ASC. No expenses -> [].
    Optionally restricted to an inclusive ISO date range.
    """
    clause, params = _date_clause(date_from, date_to)
    conn = get_db()
    try:
        rows = conn.execute(
            "SELECT category, SUM(amount) AS amount FROM expenses "
            "WHERE user_id = ?" + clause + " GROUP BY category "
            "ORDER BY amount DESC, category ASC",
            (user_id, *params),
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
