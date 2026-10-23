import re

import pytest

from database.db import create_user

CREDS = {"email": "jane@example.com", "password": "password123"}


@pytest.fixture
def user_id():
    return create_user("Jane", CREDS["email"], CREDS["password"])


@pytest.fixture
def logged_in(client, user_id):
    client.post("/login", data=CREDS)
    return client


def test_profile_redirects_to_login_when_logged_out(client):
    response = client.get("/profile")
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/login")


def test_profile_returns_200_when_logged_in(logged_in):
    assert logged_in.get("/profile").status_code == 200


def test_login_stores_user_name_in_session(logged_in):
    with logged_in.session_transaction() as s:
        assert s["user_name"] == "Jane"


def test_profile_shows_user_card_and_stats(logged_in):
    html = logged_in.get("/profile").get_data(as_text=True)
    assert "Demo User" in html
    assert "demo@spendly.com" in html
    assert "Member since" in html
    for label in ("Total spent", "Transactions", "Top category"):
        assert label in html


def test_profile_has_transaction_rows(logged_in):
    html = logged_in.get("/profile").get_data(as_text=True)
    body = html.split("<tbody>")[1].split("</tbody>")[0]
    assert body.count("<tr>") >= 3
    assert "badge--food" in html


def test_profile_has_category_breakdown(logged_in):
    html = logged_in.get("/profile").get_data(as_text=True)
    assert html.count('class="cat-row"') >= 3
    assert "<progress" in html


def test_profile_navbar_shows_name_and_logout(logged_in):
    html = logged_in.get("/profile").get_data(as_text=True)
    assert 'class="nav-user">Jane<' in html
    assert "/logout" in html


def test_profile_has_no_inline_styles_or_hex_colours(logged_in):
    html = logged_in.get("/profile").get_data(as_text=True)
    assert "style=" not in html
    assert not re.search(r"#[0-9a-fA-F]{3,8}\b", html)


def test_profile_inaccessible_after_logout(logged_in):
    logged_in.get("/logout")
    response = logged_in.get("/profile")
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/login")
