"""Tests for Step 7: add an expense via GET/POST /expenses/add.

Self-contained: relies only on the autouse ``clean_db`` and ``app`` fixtures
from conftest.py (temp SQLite DB). Behaviour is taken from
.claude/specs/07-add-expense.md.
"""
import pytest

from database.db import CATEGORIES, create_user, get_db, insert_expense


# --------------------------------------------------------------------------
# Helpers / fixtures
# --------------------------------------------------------------------------

def fetch_expenses(user_id):
    conn = get_db()
    try:
        return conn.execute(
            "SELECT * FROM expenses WHERE user_id = ? ORDER BY id", (user_id,)
        ).fetchall()
    finally:
        conn.close()


def valid_form(**overrides):
    form = {
        "amount": "50.0",
        "category": "Food",
        "date": "2026-03-20",
        "description": "Lunch",
    }
    form.update(overrides)
    return form


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def user_id():
    return create_user("Add User", "add@example.com", "password123")


@pytest.fixture
def auth_client(client, user_id):
    with client.session_transaction() as sess:
        sess["user_id"] = user_id
        sess["user_name"] = "Add User"
    return client


# --------------------------------------------------------------------------
# insert_expense
# --------------------------------------------------------------------------

def test_insert_expense_inserts_row(user_id):
    insert_expense(user_id, 50.0, "Food", "2026-03-20", "Lunch")

    rows = fetch_expenses(user_id)
    assert len(rows) == 1
    assert rows[0]["amount"] == pytest.approx(50.0)
    assert rows[0]["category"] == "Food"
    assert rows[0]["date"] == "2026-03-20"
    assert rows[0]["description"] == "Lunch"


def test_insert_expense_none_description_stored_as_null(user_id):
    insert_expense(user_id, 10.0, "Other", "2026-03-20", None)

    assert fetch_expenses(user_id)[0]["description"] is None


# --------------------------------------------------------------------------
# Auth
# --------------------------------------------------------------------------

def test_get_unauthenticated_redirects_to_login(client):
    response = client.get("/expenses/add")

    assert response.status_code == 302
    assert "/login" in response.headers["Location"]


def test_post_unauthenticated_redirects_to_login(client, user_id):
    response = client.post("/expenses/add", data=valid_form())

    assert response.status_code == 302
    assert "/login" in response.headers["Location"]
    assert fetch_expenses(user_id) == []


# --------------------------------------------------------------------------
# GET
# --------------------------------------------------------------------------

def test_get_authenticated_renders_form(auth_client):
    response = auth_client.get("/expenses/add")
    body = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "<form" in body
    assert 'method="POST"' in body
    for category in CATEGORIES:
        assert f'<option value="{category}"' in body


def test_categories_are_the_seven_fixed_options():
    assert CATEGORIES == [
        "Food",
        "Transport",
        "Bills",
        "Health",
        "Entertainment",
        "Shopping",
        "Other",
    ]


@pytest.mark.parametrize("method", ["get", "post"])
def test_stale_session_user_is_logged_out(client, method):
    with client.session_transaction() as sess:
        sess["user_id"] = 99999

    response = getattr(client, method)("/expenses/add", data=valid_form())

    assert response.status_code == 302
    assert "/login" in response.headers["Location"]
    with client.session_transaction() as sess:
        assert "user_id" not in sess


def test_session_cookie_is_samesite_lax(app):
    assert app.config["SESSION_COOKIE_SAMESITE"] == "Lax"


# --------------------------------------------------------------------------
# POST — success
# --------------------------------------------------------------------------

def test_post_valid_redirects_to_profile_and_inserts(auth_client, user_id):
    response = auth_client.post("/expenses/add", data=valid_form())

    assert response.status_code == 302
    assert "/profile" in response.headers["Location"]
    rows = fetch_expenses(user_id)
    assert len(rows) == 1
    assert rows[0]["amount"] == pytest.approx(50.0)
    assert rows[0]["description"] == "Lunch"


def test_post_without_description_stores_null(auth_client, user_id):
    response = auth_client.post("/expenses/add", data=valid_form(description="  "))

    assert response.status_code == 302
    assert fetch_expenses(user_id)[0]["description"] is None


def test_post_saves_against_session_user_only(auth_client, user_id):
    other_id = create_user("Other", "other@example.com", "password123")

    auth_client.post("/expenses/add", data=valid_form(user_id=str(other_id)))

    assert len(fetch_expenses(user_id)) == 1
    assert fetch_expenses(other_id) == []


def test_new_expense_appears_on_profile(auth_client):
    auth_client.post("/expenses/add", data=valid_form(description="Unique-lunch"))

    body = auth_client.get("/profile").get_data(as_text=True)

    assert "Unique-lunch" in body
    assert "₹50.00" in body


# --------------------------------------------------------------------------
# POST — validation errors (form re-rendered, nothing inserted)
# --------------------------------------------------------------------------

@pytest.mark.parametrize(
    "overrides",
    [
        {"amount": ""},
        {"amount": "0"},
        {"amount": "-5"},
        {"amount": "abc"},
        {"amount": "nan"},
        {"amount": "inf"},
        {"amount": "10000000.01"},
        {"amount": "1e308"},
        {"category": "Gambling"},
        {"category": ""},
        {"date": "not-a-date"},
        {"date": ""},
        {"description": "x" * 201},
    ],
)
def test_post_invalid_rerenders_with_error(auth_client, user_id, overrides):
    response = auth_client.post("/expenses/add", data=valid_form(**overrides))

    assert response.status_code == 200
    assert 'class="auth-error"' in response.get_data(as_text=True)
    assert fetch_expenses(user_id) == []


def test_post_error_keeps_submitted_values(auth_client):
    response = auth_client.post(
        "/expenses/add",
        data=valid_form(amount="0", category="Bills", description="Kept text"),
    )
    body = response.get_data(as_text=True)

    assert 'value="Kept text"' in body
    assert '<option value="Bills" selected>' in body
    assert 'value="2026-03-20"' in body
