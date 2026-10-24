"""Tests for Step 8: edit an expense via GET/POST /expenses/<id>/edit.

Self-contained: relies only on the autouse ``clean_db`` and ``app`` fixtures
from conftest.py (temp SQLite DB). Behaviour is taken from
.claude/specs/08-edit-expense.md ("Tests to write" section). Helpers live in
database/db.py.
"""
import pytest

from database.db import (
    CATEGORIES,
    create_user,
    get_db,
    get_expense_by_id,
    get_recent_transactions,
    insert_expense,
    update_expense,
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


def valid_form(**overrides):
    form = {
        "amount": "75.5",
        "category": "Transport",
        "date": "2026-04-01",
        "description": "Updated taxi",
    }
    form.update(overrides)
    return form


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def user_id():
    return create_user("Edit User", "edit@example.com", "password123")


@pytest.fixture
def other_user_id():
    return create_user("Other User", "other-edit@example.com", "password123")


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
        sess["user_name"] = "Edit User"
    return client


def edit_url(expense_id):
    return f"/expenses/{expense_id}/edit"


# --------------------------------------------------------------------------
# get_expense_by_id
# --------------------------------------------------------------------------

def test_get_expense_by_id_returns_matching_row(user_id, expense_id):
    row = get_expense_by_id(expense_id, user_id)

    assert row is not None
    assert row["id"] == expense_id
    assert row["amount"] == pytest.approx(50.0)
    assert row["category"] == "Food"
    assert row["date"] == "2026-03-20"
    assert row["description"] == "Lunch"


def test_get_expense_by_id_wrong_user_returns_none(other_user_id, expense_id):
    assert get_expense_by_id(expense_id, other_user_id) is None


def test_get_expense_by_id_nonexistent_returns_none(user_id):
    assert get_expense_by_id(999999, user_id) is None


# --------------------------------------------------------------------------
# update_expense
# --------------------------------------------------------------------------

def test_update_expense_updates_row(user_id, expense_id):
    result = update_expense(expense_id, user_id, 99.0, "Health", "2026-05-05", "Doc")

    row = fetch_expense(expense_id)
    assert result is True
    assert row["amount"] == pytest.approx(99.0)
    assert row["category"] == "Health"
    assert row["date"] == "2026-05-05"
    assert row["description"] == "Doc"


def test_update_expense_wrong_user_leaves_row_unchanged(other_user_id, expense_id):
    result = update_expense(
        expense_id, other_user_id, 99.0, "Health", "2026-05-05", "Hacked"
    )

    row = fetch_expense(expense_id)
    assert not result
    assert row["amount"] == pytest.approx(50.0)
    assert row["category"] == "Food"
    assert row["date"] == "2026-03-20"
    assert row["description"] == "Lunch"


def test_update_expense_nonexistent_returns_false(user_id):
    assert not update_expense(999999, user_id, 1.0, "Food", "2026-05-05", None)


def test_update_expense_none_description_stored_as_null(user_id, expense_id):
    update_expense(expense_id, user_id, 50.0, "Food", "2026-03-20", None)

    assert fetch_expense(expense_id)["description"] is None


# --------------------------------------------------------------------------
# get_recent_transactions / profile edit link
# --------------------------------------------------------------------------

def test_get_recent_transactions_includes_id(user_id, expense_id):
    rows = get_recent_transactions(user_id)

    assert len(rows) == 1
    assert rows[0]["id"] == expense_id


def test_profile_rows_have_edit_link(auth_client, expense_id):
    body = auth_client.get("/profile").get_data(as_text=True)

    assert f'href="/expenses/{expense_id}/edit"' in body
    assert "Edit" in body
    assert "Actions" in body


# --------------------------------------------------------------------------
# Auth
# --------------------------------------------------------------------------

def test_get_unauthenticated_redirects_to_login(client, expense_id):
    response = client.get(edit_url(expense_id))

    assert response.status_code == 302
    assert "/login" in response.headers["Location"]


def test_post_unauthenticated_redirects_to_login_and_no_change(client, expense_id):
    response = client.post(edit_url(expense_id), data=valid_form())

    assert response.status_code == 302
    assert "/login" in response.headers["Location"]
    row = fetch_expense(expense_id)
    assert row["amount"] == pytest.approx(50.0)
    assert row["description"] == "Lunch"


# --------------------------------------------------------------------------
# GET
# --------------------------------------------------------------------------

def test_get_own_expense_renders_prefilled_form(auth_client, expense_id):
    response = auth_client.get(edit_url(expense_id))
    body = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "<form" in body
    assert 'method="POST"' in body
    assert 'value="50.0"' in body or 'value="50"' in body or 'value="50.00"' in body
    assert 'value="2026-03-20"' in body
    assert 'value="Lunch"' in body
    assert "Save Changes" in body


def test_get_own_expense_lists_all_categories_with_current_selected(
    auth_client, expense_id
):
    body = auth_client.get(edit_url(expense_id)).get_data(as_text=True)

    for category in CATEGORIES:
        assert f'<option value="{category}"' in body
    assert '<option value="Food" selected>' in body
    assert body.count(" selected>") == 1


def test_get_other_users_expense_returns_404(auth_client, other_expense_id):
    assert auth_client.get(edit_url(other_expense_id)).status_code == 404


def test_get_nonexistent_expense_returns_404(auth_client):
    assert auth_client.get(edit_url(999999)).status_code == 404


# --------------------------------------------------------------------------
# POST — success
# --------------------------------------------------------------------------

def test_post_valid_redirects_to_profile_and_updates(auth_client, expense_id):
    response = auth_client.post(edit_url(expense_id), data=valid_form())

    assert response.status_code == 302
    assert "/profile" in response.headers["Location"]
    row = fetch_expense(expense_id)
    assert row["amount"] == pytest.approx(75.5)
    assert row["category"] == "Transport"
    assert row["date"] == "2026-04-01"
    assert row["description"] == "Updated taxi"


def test_post_valid_does_not_create_new_row(auth_client, user_id, expense_id):
    auth_client.post(edit_url(expense_id), data=valid_form())

    assert len(get_recent_transactions(user_id)) == 1


def test_post_without_description_stores_null(auth_client, expense_id):
    response = auth_client.post(edit_url(expense_id), data=valid_form(description=""))

    assert response.status_code == 302
    assert "/profile" in response.headers["Location"]
    assert fetch_expense(expense_id)["description"] is None


def test_post_whitespace_description_stores_null(auth_client, expense_id):
    auth_client.post(edit_url(expense_id), data=valid_form(description="   "))

    assert fetch_expense(expense_id)["description"] is None


def test_post_amount_at_max_is_accepted(auth_client, expense_id):
    response = auth_client.post(edit_url(expense_id), data=valid_form(amount="10000000"))

    assert response.status_code == 302
    assert fetch_expense(expense_id)["amount"] == pytest.approx(10000000)


def test_updated_values_appear_on_profile(auth_client, expense_id):
    auth_client.post(
        edit_url(expense_id), data=valid_form(description="Unique-edited-text")
    )

    body = auth_client.get("/profile").get_data(as_text=True)

    assert "Unique-edited-text" in body
    assert "₹75.50" in body


def test_post_sql_injection_in_description_stored_literally(auth_client, expense_id):
    payload = "'); DROP TABLE expenses;--"

    response = auth_client.post(edit_url(expense_id), data=valid_form(description=payload))

    assert response.status_code == 302
    assert fetch_expense(expense_id)["description"] == payload


# --------------------------------------------------------------------------
# POST — ownership
# --------------------------------------------------------------------------

def test_post_other_users_expense_returns_404(auth_client, other_expense_id):
    response = auth_client.post(edit_url(other_expense_id), data=valid_form())

    assert response.status_code == 404


def test_post_other_users_expense_leaves_it_unchanged(auth_client, other_expense_id):
    auth_client.post(edit_url(other_expense_id), data=valid_form())

    row = fetch_expense(other_expense_id)
    assert row["amount"] == pytest.approx(20.0)
    assert row["category"] == "Bills"
    assert row["date"] == "2026-02-10"
    assert row["description"] == "Their bill"


def test_post_nonexistent_expense_returns_404(auth_client):
    assert auth_client.post(edit_url(999999), data=valid_form()).status_code == 404


# --------------------------------------------------------------------------
# POST — validation errors (form re-rendered, row unchanged)
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
        {"category": "Gambling"},
        {"category": ""},
        {"date": "not-a-date"},
        {"date": ""},
        {"description": "x" * 201},
    ],
)
def test_post_invalid_rerenders_with_error(auth_client, expense_id, overrides):
    response = auth_client.post(edit_url(expense_id), data=valid_form(**overrides))

    assert response.status_code == 200
    assert 'class="auth-error"' in response.get_data(as_text=True)
    row = fetch_expense(expense_id)
    assert row["amount"] == pytest.approx(50.0)
    assert row["category"] == "Food"
    assert row["date"] == "2026-03-20"
    assert row["description"] == "Lunch"


def test_post_missing_amount_field_rerenders_with_error(auth_client, expense_id):
    form = valid_form()
    del form["amount"]

    response = auth_client.post(edit_url(expense_id), data=form)

    assert response.status_code == 200
    assert 'class="auth-error"' in response.get_data(as_text=True)
    assert fetch_expense(expense_id)["amount"] == pytest.approx(50.0)


def test_post_error_keeps_submitted_values(auth_client, expense_id):
    response = auth_client.post(
        edit_url(expense_id),
        data=valid_form(amount="0", category="Bills", description="Kept text"),
    )
    body = response.get_data(as_text=True)

    assert response.status_code == 200
    assert 'value="Kept text"' in body
    assert '<option value="Bills" selected>' in body
    assert 'value="2026-04-01"' in body
    assert 'value="Lunch"' not in body, "Original values must not replace submitted"


# --------------------------------------------------------------------------
# Step 9 stub is untouched
# --------------------------------------------------------------------------

def test_delete_route_still_returns_step_9_stub(auth_client, expense_id):
    response = auth_client.get(f"/expenses/{expense_id}/delete")

    assert response.status_code == 200
    assert "Delete expense — coming in Step 9" in response.get_data(as_text=True)
    assert fetch_expense(expense_id) is not None
