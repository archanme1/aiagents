import os
import tempfile

import pytest

import database.db as db

# app.py seeds the database at import time, so point DB_PATH at a throwaway
# file before importing it — the real expense_tracker.db must never be touched.
db.DB_PATH = os.path.join(tempfile.mkdtemp(), "test_expense_tracker.db")

from app import app as flask_app  # noqa: E402


@pytest.fixture
def app():
    flask_app.config["TESTING"] = True
    return flask_app


@pytest.fixture(autouse=True)
def clean_db():
    db.init_db()
    conn = db.get_db()
    try:
        conn.execute("DELETE FROM expenses")
        conn.execute("DELETE FROM users")
        conn.commit()
    finally:
        conn.close()
