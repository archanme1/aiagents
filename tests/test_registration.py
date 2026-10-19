import sqlite3

import pytest
from werkzeug.security import check_password_hash

from database.db import create_user, get_db, get_user_by_email

VALID = {"name": "Asha Rao", "email": "asha@example.com", "password": "password123"}


def user_count():
    conn = get_db()
    try:
        return conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    finally:
        conn.close()


def test_get_register_renders_form(client):
    response = client.get("/register")
    html = response.get_data(as_text=True)
    assert response.status_code == 200
    for field in ('name="name"', 'name="email"', 'name="password"'):
        assert field in html
    assert 'action="/register"' in html


def test_valid_registration_creates_user_and_redirects(client):
    response = client.post("/register", data=VALID)
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/login")

    user = get_user_by_email(VALID["email"])
    assert user is not None
    assert user["name"] == VALID["name"]
    assert user["password_hash"] != VALID["password"]
    assert check_password_hash(user["password_hash"], VALID["password"])


def test_email_is_stored_lowercase_and_trimmed(client):
    client.post("/register", data={**VALID, "email": "  A@B.COM "})
    assert get_user_by_email("a@b.com")["email"] == "a@b.com"


def test_password_of_exactly_eight_characters_succeeds(client):
    response = client.post("/register", data={**VALID, "password": "12345678"})
    assert response.status_code == 302


@pytest.mark.parametrize("second_email", ["asha@example.com", "ASHA@Example.COM"])
def test_duplicate_email_rejected(client, second_email):
    client.post("/register", data=VALID)
    response = client.post("/register", data={**VALID, "email": second_email})
    assert response.status_code == 200
    assert "already exists" in response.get_data(as_text=True)
    assert user_count() == 1


def test_seeded_demo_email_rejected(client):
    create_user("Demo User", "demo@spendly.com", "demo12345")
    response = client.post("/register", data={**VALID, "email": "demo@spendly.com"})
    assert "already exists" in response.get_data(as_text=True)
    assert user_count() == 1


@pytest.mark.parametrize(
    "overrides",
    [{"name": ""}, {"name": "   "}, {"email": ""}, {"password": ""}],
)
def test_empty_fields_rejected(client, overrides):
    response = client.post("/register", data={**VALID, **overrides})
    assert response.status_code == 200
    assert "required" in response.get_data(as_text=True)
    assert user_count() == 0


def test_missing_form_keys_do_not_crash(client):
    response = client.post("/register", data={})
    assert response.status_code == 200
    assert user_count() == 0


def test_short_password_rejected(client):
    response = client.post("/register", data={**VALID, "password": "1234567"})
    assert response.status_code == 200
    assert "at least 8" in response.get_data(as_text=True)
    assert user_count() == 0


@pytest.mark.parametrize("bad_email", ["foo", "foo@bar", "@.", "@example.com", "a@@b.com", "a@b."])
def test_malformed_email_rejected(client, bad_email):
    response = client.post("/register", data={**VALID, "email": bad_email})
    assert response.status_code == 200
    assert "valid email" in response.get_data(as_text=True)
    assert user_count() == 0


def test_failed_submit_keeps_name_and_email_but_not_password(client):
    response = client.post("/register", data={**VALID, "password": "sEcr3t"})
    html = response.get_data(as_text=True)
    assert 'value="Asha Rao"' in html
    assert 'value="asha@example.com"' in html
    assert "sEcr3t" not in html


def test_name_is_html_escaped_on_rerender(client):
    response = client.post(
        "/register", data={**VALID, "name": '"><script>x</script>', "password": "short"}
    )
    html = response.get_data(as_text=True)
    assert "<script>x</script>" not in html
    assert "&lt;script&gt;" in html


def test_create_user_duplicate_raises_integrity_error():
    create_user("A", "dup@example.com", "password123")
    with pytest.raises(sqlite3.IntegrityError):
        create_user("B", "DUP@example.com", "password123")


def test_get_user_by_email_unknown_returns_none():
    assert get_user_by_email("nobody@example.com") is None
