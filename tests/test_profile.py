import re

import pytest

from database.db import create_user, get_db

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


SEED_ROWS = [
    (12.50, "Food", "2026-10-01", "Groceries"),
    (3.25, "Transport", "2026-10-03", "Bus fare"),
    (85.00, "Bills", "2026-10-05", "Electricity bill"),
    (24.99, "Health", "2026-10-08", "Pharmacy"),
    (15.00, "Entertainment", "2026-10-10", "Movie ticket"),
    (49.90, "Shopping", "2026-10-12", "New shoes"),
    (7.00, "Other", "2026-10-14", None),
    (18.75, "Food", "2026-10-15", "Dinner out"),
]


def _insert_expenses(user_id, rows):
    conn = get_db()
    try:
        conn.executemany(
            "INSERT INTO expenses (user_id, amount, category, date, description) "
            "VALUES (?, ?, ?, ?, ?)",
            [(user_id, *row) for row in rows],
        )
        conn.commit()
    finally:
        conn.close()


@pytest.fixture
def seeded_expenses(user_id):
    _insert_expenses(user_id, SEED_ROWS)


def test_profile_shows_user_card_and_stats(logged_in):
    html = logged_in.get("/profile").get_data(as_text=True)
    assert "Jane" in html
    assert "jane@example.com" in html
    assert "Member since" in html
    for label in ("Total spent", "Transactions", "Top category"):
        assert label in html


def test_profile_shows_real_stats(logged_in, seeded_expenses):
    html = logged_in.get("/profile").get_data(as_text=True)
    assert "₹216.39" in html
    assert '<span class="stat-value">8</span>' in html
    assert '<span class="stat-value">Bills</span>' in html


def test_profile_has_transaction_rows(logged_in, seeded_expenses):
    html = logged_in.get("/profile").get_data(as_text=True)
    body = html.split("<tbody>")[1].split("</tbody>")[0]
    assert body.count("<tr>") == 8
    assert "badge--food" in html
    assert html.index("Dinner out") < html.index("Groceries")


def test_profile_has_category_breakdown(logged_in, seeded_expenses):
    html = logged_in.get("/profile").get_data(as_text=True)
    assert html.count('class="cat-row"') == 7
    assert "<progress" in html
    percents = [int(p) for p in re.findall(r'<span class="cat-pct">(\d+)%', html)]
    assert sum(percents) == 100


def test_profile_empty_state_for_new_user(logged_in):
    response = logged_in.get("/profile")
    html = response.get_data(as_text=True)
    assert response.status_code == 200
    assert "₹0.00" in html
    assert "No transactions yet." in html
    assert 'class="cat-row"' not in html


def test_profile_excludes_other_users_expenses(logged_in, seeded_expenses):
    other_id = create_user("Other", "other@example.com", "password123")
    _insert_expenses(other_id, [(999.00, "Bills", "2026-10-02", "Secret rent")])
    html = logged_in.get("/profile").get_data(as_text=True)
    assert "Secret rent" not in html
    assert "₹216.39" in html


def test_profile_redirects_when_session_user_missing(client):
    with client.session_transaction() as s:
        s["user_id"] = 99999
    response = client.get("/profile")
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/login")
    with client.session_transaction() as s:
        assert "user_id" not in s


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
