import calendar
import math
import os
import sqlite3
from datetime import date, datetime

from flask import Flask, abort, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash

from database.db import (
    CATEGORIES,
    create_user,
    format_inr,
    get_category_breakdown,
    get_db,
    get_expense_by_id,
    get_recent_transactions,
    get_summary_stats,
    get_user_by_email,
    get_user_by_id,
    init_db,
    insert_expense,
    seed_db,
    update_expense,
)

app = Flask(__name__)
# Development fallback only — set SECRET_KEY in the environment for real use
app.secret_key = os.environ.get("SECRET_KEY", "dev-only-change-me")
# Lax stops browsers sending the session cookie on cross-site POSTs (CSRF)
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"

MAX_EXPENSE_AMOUNT = 10_000_000

with app.app_context():
    init_db()
    seed_db()


def _validate_registration(name, email, password):
    if not name or not email or not password:
        return "All fields are required."

    local, _, domain = email.partition("@")
    if (
        not local
        or "@" in domain
        or "." not in domain
        or domain.startswith(".")
        or domain.endswith(".")
    ):
        return "Please enter a valid email address."

    if len(password) < 8:
        return "Password must be at least 8 characters."

    return None


def _normalize_iso_date(value):
    """Return value as zero-padded YYYY-MM-DD, or None if it isn't a real date."""
    try:
        return datetime.strptime(value or "", "%Y-%m-%d").date().isoformat()
    except ValueError:
        return None


def _validate_expense(amount, category, date_str, description):
    """Return (values, error); values is None when error is set.

    values keys (amount, category, date, description) match insert_expense's
    parameters after user_id.
    """
    try:
        amount = float(amount)
    except ValueError:
        return None, "Amount must be a number."
    if not math.isfinite(amount) or amount <= 0:
        return None, "Amount must be greater than 0."
    if amount > MAX_EXPENSE_AMOUNT:
        return None, f"Amount must not exceed {MAX_EXPENSE_AMOUNT:,}."

    if category not in CATEGORIES:
        return None, "Please choose a valid category."

    iso_date = _normalize_iso_date(date_str)
    if iso_date is None:
        return None, "Please enter a valid date."

    if len(description) > 200:
        return None, "Description must be 200 characters or fewer."

    return {
        "amount": round(amount, 2),
        "category": category,
        "date": iso_date,
        "description": description or None,
    }, None


def _parse_date_filter(date_from, date_to):
    """Return (date_from, date_to, error); bounds are None when unfiltered."""
    date_from = _normalize_iso_date(date_from)
    date_to = _normalize_iso_date(date_to)
    if date_from is None or date_to is None:
        return None, None, None
    # Normalised ISO strings sort chronologically, so a string compare is safe
    if date_from > date_to:
        return None, None, "Start date must be before end date."
    return date_from, date_to, None


def _months_ago(today, months):
    month_index = today.year * 12 + today.month - 1 - months
    year, month = divmod(month_index, 12)
    month += 1
    last_day = calendar.monthrange(year, month)[1]
    return date(year, month, min(today.day, last_day))


def _build_presets(today, date_from, date_to):
    """Return (presets, custom_active) for the filter bar.

    custom_active is True when a range is applied that matches no preset.
    """
    ranges = [
        ("This Month", today.replace(day=1), today),
        ("Last 3 Months", _months_ago(today, 3), today),
        ("Last 6 Months", _months_ago(today, 6), today),
        ("All Time", None, None),
    ]
    presets = []
    for label, start, end in ranges:
        start_iso = start.isoformat() if start else None
        end_iso = end.isoformat() if end else None
        presets.append(
            {
                "label": label,
                "date_from": start_iso,
                "date_to": end_iso,
                "active": start_iso == date_from and end_iso == date_to,
            }
        )
    custom_active = bool(date_from and date_to) and not any(
        p["active"] for p in presets
    )
    return presets, custom_active


# ------------------------------------------------------------------ #
# Routes                                                              #
# ------------------------------------------------------------------ #

@app.route("/")
def landing():
    return render_template("landing.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    if session.get("user_id"):
        return redirect(url_for("landing"))

    if request.method == "GET":
        return render_template("register.html")

    name = request.form.get("name", "").strip()
    email = request.form.get("email", "").strip().lower()
    password = request.form.get("password", "")

    error = _validate_registration(name, email, password)
    if error is None:
        try:
            create_user(name, email, password)
        except sqlite3.IntegrityError:
            error = "An account with that email already exists."

    if error:
        return render_template("register.html", error=error, name=name, email=email)

    return redirect(url_for("login"))


@app.route("/login", methods=["GET", "POST"])
def login():
    if session.get("user_id"):
        return redirect(url_for("landing"))

    if request.method == "GET":
        return render_template("login.html")

    email = request.form.get("email", "").strip().lower()
    password = request.form.get("password", "")

    user = get_user_by_email(email) if email else None
    if user is None or not check_password_hash(user["password_hash"], password):
        return render_template(
            "login.html", error="Invalid email or password.", email=email
        )

    session["user_id"] = user["id"]
    session["user_name"] = user["name"]
    return redirect(url_for("landing"))


@app.route("/terms")
def terms():
    return render_template("terms.html")


@app.route("/privacy")
def privacy():
    return render_template("privacy.html")


# ------------------------------------------------------------------ #
# Placeholder routes — students will implement these                  #
# ------------------------------------------------------------------ #

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("landing"))


@app.route("/profile")
def profile():
    user_id = session.get("user_id")
    if not user_id:
        return redirect(url_for("login"))

    user = get_user_by_id(user_id)
    if user is None:
        session.clear()
        return redirect(url_for("login"))

    date_from, date_to, filter_error = _parse_date_filter(
        request.args.get("date_from"), request.args.get("date_to")
    )

    date_range = {"date_from": date_from, "date_to": date_to}

    stats = get_summary_stats(user_id, **date_range)
    stats["total_spent"] = format_inr(stats["total_spent"])

    categories = [
        {**c, "total": format_inr(c["amount"]), "percent": c["pct"]}
        for c in get_category_breakdown(user_id, **date_range)
    ]

    presets, custom_active = _build_presets(date.today(), date_from, date_to)

    return render_template(
        "profile.html",
        user=user,
        stats=stats,
        transactions=get_recent_transactions(user_id, **date_range),
        categories=categories,
        filter_error=filter_error,
        presets=presets,
        custom_active=custom_active,
        **date_range,
    )


@app.route("/analytics")
def analytics():
    if not session.get("user_id"):
        return redirect(url_for("login"))
    return render_template("analytics.html")


@app.route("/expenses/add", methods=["GET", "POST"])
def add_expense():
    user_id = session.get("user_id")
    if not user_id:
        return redirect(url_for("login"))

    if get_user_by_id(user_id) is None:
        session.clear()
        return redirect(url_for("login"))

    if request.method == "GET":
        return render_template(
            "add_expense.html",
            categories=CATEGORIES,
            date=date.today().isoformat(),
        )

    # Keys double as the template's variable names for re-filling the form
    form = {
        "amount": request.form.get("amount", "").strip(),
        "category": request.form.get("category", ""),
        "date": request.form.get("date", "").strip(),
        "description": request.form.get("description", "").strip(),
    }
    values, error = _validate_expense(
        form["amount"], form["category"], form["date"], form["description"]
    )
    if error:
        return render_template(
            "add_expense.html", categories=CATEGORIES, error=error, **form
        )

    insert_expense(user_id, **values)
    return redirect(url_for("profile"))


@app.route("/expenses/<int:id>/edit", methods=["GET", "POST"])
def edit_expense(id):
    user_id = session.get("user_id")
    if not user_id:
        return redirect(url_for("login"))

    if get_user_by_id(user_id) is None:
        session.clear()
        return redirect(url_for("login"))

    expense = get_expense_by_id(id, user_id)
    if expense is None:
        abort(404)

    if request.method == "GET":
        return render_template(
            "edit_expense.html",
            expense_id=id,
            categories=CATEGORIES,
            amount=expense["amount"],
            category=expense["category"],
            date=expense["date"],
            description=expense["description"],
        )

    # Keys double as the template's variable names for re-filling the form
    form = {
        "amount": request.form.get("amount", "").strip(),
        "category": request.form.get("category", ""),
        "date": request.form.get("date", "").strip(),
        "description": request.form.get("description", "").strip(),
    }
    values, error = _validate_expense(
        form["amount"], form["category"], form["date"], form["description"]
    )
    if error:
        return render_template(
            "edit_expense.html",
            expense_id=id,
            categories=CATEGORIES,
            error=error,
            **form,
        )

    if not update_expense(id, user_id, **values):
        abort(404)
    return redirect(url_for("profile"))


@app.route("/expenses/<int:id>/delete")
def delete_expense(id):
    return "Delete expense — coming in Step 9"


if __name__ == "__main__":
    app.run(debug=True, port=5001)
