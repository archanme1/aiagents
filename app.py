import os
import sqlite3

from flask import Flask, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash

from database.db import create_user, get_db, get_user_by_email, init_db, seed_db

app = Flask(__name__)
# Development fallback only — set SECRET_KEY in the environment for real use
app.secret_key = os.environ.get("SECRET_KEY", "dev-only-change-me")

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
    if not session.get("user_id"):
        return redirect(url_for("login"))

    # Hardcoded placeholder data — Step 5 replaces this with database queries
    user = {
        "name": "Demo User",
        "initials": "DU",
        "email": "demo@spendly.com",
        "member_since": "January 2026",
    }
    stats = {
        "total_spent": "₹203.89",
        "transaction_count": 7,
        "top_category": "Bills",
    }
    transactions = [
        {"date": "15 Oct 2026", "description": "Dinner out", "category": "Food", "amount": "₹18.75"},
        {"date": "14 Oct 2026", "description": "Miscellaneous", "category": "Other", "amount": "₹7.00"},
        {"date": "12 Oct 2026", "description": "New shoes", "category": "Shopping", "amount": "₹49.90"},
        {"date": "10 Oct 2026", "description": "Movie ticket", "category": "Entertainment", "amount": "₹15.00"},
        {"date": "08 Oct 2026", "description": "Pharmacy", "category": "Health", "amount": "₹24.99"},
        {"date": "05 Oct 2026", "description": "Electricity bill", "category": "Bills", "amount": "₹85.00"},
        {"date": "03 Oct 2026", "description": "Bus fare", "category": "Transport", "amount": "₹3.25"},
    ]
    categories = [
        {"name": "Bills", "total": "₹85.00", "percent": 42},
        {"name": "Shopping", "total": "₹49.90", "percent": 24},
        {"name": "Health", "total": "₹24.99", "percent": 12},
        {"name": "Food", "total": "₹18.75", "percent": 9},
        {"name": "Entertainment", "total": "₹15.00", "percent": 7},
        {"name": "Other", "total": "₹7.00", "percent": 3},
        {"name": "Transport", "total": "₹3.25", "percent": 2},
    ]
    return render_template(
        "profile.html",
        user=user,
        stats=stats,
        transactions=transactions,
        categories=categories,
    )


@app.route("/expenses/add")
def add_expense():
    return "Add expense — coming in Step 7"


@app.route("/expenses/<int:id>/edit")
def edit_expense(id):
    return "Edit expense — coming in Step 8"


@app.route("/expenses/<int:id>/delete")
def delete_expense(id):
    return "Delete expense — coming in Step 9"


if __name__ == "__main__":
    app.run(debug=True, port=5001)
