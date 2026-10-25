"""Tests for Step 9: delete an expense via POST /expenses/<id>/delete.

Self-contained: relies only on the autouse ``clean_db`` and ``app`` fixtures
from conftest.py (temp SQLite DB). Behaviour is taken from
.claude/specs/09-delete-expense.md ("Tests to write" section).
"""
import pytest

from database.db import (
    create_user,
    delete_expense,
    get_db,
    insert_expense,
)


# --------------------------------------------------------------------------
# Helpers / fixtures
# --------------------------------------------------------------------------

def fetch_expense(expense_id):
    conn = get_db()
    try:
        return conn.execute(
            "SELECT * FROM expenses WHERE id = ?", (expense_id,)
        ).fetchone()
    finally:
        conn.close()


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def user_id():
    return create_user("Delete User", "delete@example.com", "password123")


@pytest.fixture
def other_user_id():
    return create_user("Other User", "other-delete@example.com", "password123")


@pytest.fixture
def expense_id(user_id):
    return insert_expense(user_id, 50.0, "Food", "2026-03-20", "Lunch")


@pytest.fixture
def other_expense_id(other_user_id):
    return insert_expense(other_user_id, 20.0, "Bills", "2026-02-10", "Their bill")


@pytest.fixture
def auth_client(client, user_id):
    with client.session_transaction() as sess:
        sess["user_id"] = user_id
        sess["user_name"] = "Delete User"
    return client


def delete_url(expense_id):
    return f"/expenses/{expense_id}/delete"


# --------------------------------------------------------------------------
# delete_expense helper
# --------------------------------------------------------------------------

def test_delete_expense_removes_owned_row(user_id, expense_id):
    assert delete_expense(expense_id, user_id) is True
    assert fetch_expense(expense_id) is None


def test_delete_expense_wrong_user_leaves_row(other_user_id, expense_id):
    assert delete_expense(expense_id, other_user_id) is False
    assert fetch_expense(expense_id) is not None


def test_delete_expense_missing_id_is_noop(user_id, expense_id):
    assert delete_expense(99999, user_id) is False
    assert fetch_expense(expense_id) is not None


# --------------------------------------------------------------------------
# POST /expenses/<id>/delete
# --------------------------------------------------------------------------

def test_post_unauthenticated_redirects_to_login(client, expense_id):
    response = client.post(delete_url(expense_id))

    assert response.status_code == 302
    assert "/login" in response.headers["Location"]
    assert fetch_expense(expense_id) is not None


def test_post_own_expense_deletes_and_redirects_to_profile(auth_client, expense_id):
    response = auth_client.post(delete_url(expense_id))

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/profile")
    assert fetch_expense(expense_id) is None


def test_post_other_users_expense_returns_404(auth_client, other_expense_id):
    response = auth_client.post(delete_url(other_expense_id))

    assert response.status_code == 404
    assert fetch_expense(other_expense_id) is not None


def test_post_missing_expense_returns_404(auth_client):
    assert auth_client.post(delete_url(99999)).status_code == 404


def test_post_twice_second_returns_404(auth_client, expense_id):
    assert auth_client.post(delete_url(expense_id)).status_code == 302
    assert auth_client.post(delete_url(expense_id)).status_code == 404


def test_post_stale_session_redirects_to_login(client, expense_id):
    with client.session_transaction() as sess:
        sess["user_id"] = 99999

    response = client.post(delete_url(expense_id))

    assert response.status_code == 302
    assert "/login" in response.headers["Location"]
    assert fetch_expense(expense_id) is not None


@pytest.mark.parametrize("authenticated", [True, False])
def test_get_returns_405_and_does_not_delete(client, user_id, expense_id, authenticated):
    if authenticated:
        with client.session_transaction() as sess:
            sess["user_id"] = user_id

    response = client.get(delete_url(expense_id))

    assert response.status_code == 405
    assert fetch_expense(expense_id) is not None


# --------------------------------------------------------------------------
# Profile page
# --------------------------------------------------------------------------

def test_profile_renders_delete_form_per_row(auth_client, expense_id):
    body = auth_client.get("/profile").get_data(as_text=True)

    assert f'action="{delete_url(expense_id)}"' in body
    assert 'class="btn-delete"' in body


def test_deleted_expense_disappears_from_profile(auth_client, expense_id):
    auth_client.post(delete_url(expense_id))

    body = auth_client.get("/profile").get_data(as_text=True)

    assert f'action="{delete_url(expense_id)}"' not in body
