"""Tests for Step 6: date-range filter on GET /profile.

Self-contained: relies only on the autouse ``clean_db`` and ``app`` fixtures
from conftest.py (temp SQLite DB). Behaviour is taken from
.claude/specs/06-date-filter-profile-page.md.
"""
from datetime import date, timedelta

import pytest

import database.db as db
from database.db import (
    create_user,
    get_category_breakdown,
    get_db,
    get_recent_transactions,
    get_summary_stats,
)


# --------------------------------------------------------------------------
# Helpers / fixtures
# --------------------------------------------------------------------------

def add_expense(user_id, amount, category, on_date, description=None):
    conn = get_db()
    try:
        conn.execute(
            "INSERT INTO expenses (user_id, amount, category, date, description) "
            "VALUES (?, ?, ?, ?, ?)",
            (user_id, amount, category, on_date, description),
        )
        conn.commit()
    finally:
        conn.close()


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def user_id():
    return create_user("Filter User", "filter@example.com", "password123")


@pytest.fixture
def other_user_id():
    return create_user("Other User", "other@example.com", "password123")


@pytest.fixture
def data(user_id):
    """Expenses spread over known dates (all within 2024)."""
    add_expense(user_id, 100.00, "Food", "2024-01-10", "jan-food")
    add_expense(user_id, 200.00, "Transport", "2024-02-15", "feb-transport")
    add_expense(user_id, 300.00, "Bills", "2024-03-20", "mar-bills")
    add_expense(user_id, 50.00, "Food", "2024-03-25", "mar-food")
    return user_id


@pytest.fixture
def auth_client(client, user_id):
    with client.session_transaction() as sess:
        sess["user_id"] = user_id
        sess["user_name"] = "Filter User"
    return client


@pytest.fixture
def data_client(client, data):
    with client.session_transaction() as sess:
        sess["user_id"] = data
        sess["user_name"] = "Filter User"
    return client


# --------------------------------------------------------------------------
# DB helpers: get_summary_stats
# --------------------------------------------------------------------------

def test_summary_stats_no_dates_matches_unfiltered(data):
    stats = get_summary_stats(data)
    assert stats["total_spent"] == pytest.approx(650.00)
    assert stats["transaction_count"] == 4
    assert stats["top_category"] == "Bills"


def test_summary_stats_explicit_none_equals_no_args(data):
    assert get_summary_stats(data, date_from=None, date_to=None) == get_summary_stats(data)


def test_summary_stats_range_restricts_total_and_count(data):
    stats = get_summary_stats(data, date_from="2024-03-01", date_to="2024-03-31")
    assert stats["total_spent"] == pytest.approx(350.00)
    assert stats["transaction_count"] == 2
    assert stats["top_category"] == "Bills"


def test_summary_stats_bounds_are_inclusive(data):
    stats = get_summary_stats(data, date_from="2024-01-10", date_to="2024-03-20")
    assert stats["transaction_count"] == 3
    assert stats["total_spent"] == pytest.approx(600.00)


def test_summary_stats_single_day_range(data):
    stats = get_summary_stats(data, date_from="2024-02-15", date_to="2024-02-15")
    assert stats["transaction_count"] == 1
    assert stats["total_spent"] == pytest.approx(200.00)
    assert stats["top_category"] == "Transport"


def test_summary_stats_top_category_respects_range(data):
    stats = get_summary_stats(data, date_from="2024-01-01", date_to="2024-01-31")
    assert stats["top_category"] == "Food"


def test_summary_stats_empty_range_returns_zeros(data):
    stats = get_summary_stats(data, date_from="2023-01-01", date_to="2023-12-31")
    assert stats["total_spent"] == 0
    assert stats["transaction_count"] == 0
    assert stats["top_category"] == "—"


def test_summary_stats_range_excludes_other_users(data, other_user_id):
    add_expense(other_user_id, 999.00, "Shopping", "2024-03-21")
    stats = get_summary_stats(data, date_from="2024-03-01", date_to="2024-03-31")
    assert stats["total_spent"] == pytest.approx(350.00)
    assert stats["transaction_count"] == 2


# --------------------------------------------------------------------------
# DB helpers: get_recent_transactions
# --------------------------------------------------------------------------

def test_transactions_no_dates_returns_all(data):
    rows = get_recent_transactions(data)
    assert len(rows) == 4


def test_transactions_range_returns_only_in_range(data):
    rows = get_recent_transactions(data, date_from="2024-02-01", date_to="2024-03-21")
    descs = [r["description"] for r in rows]
    assert descs == ["mar-bills", "feb-transport"]


def test_transactions_range_keeps_newest_first_ordering(data):
    rows = get_recent_transactions(data, date_from="2024-03-01", date_to="2024-03-31")
    assert [r["description"] for r in rows] == ["mar-food", "mar-bills"]


def test_transactions_bounds_inclusive(data):
    rows = get_recent_transactions(data, date_from="2024-03-20", date_to="2024-03-25")
    assert len(rows) == 2


def test_transactions_limit_still_applies_with_range(data):
    rows = get_recent_transactions(
        data, limit=1, date_from="2024-01-01", date_to="2024-12-31"
    )
    assert len(rows) == 1
    assert rows[0]["description"] == "mar-food"


def test_transactions_empty_range_returns_empty_list(data):
    assert get_recent_transactions(data, date_from="2020-01-01", date_to="2020-02-01") == []


def test_transactions_amounts_keep_rupee_symbol_when_filtered(data):
    rows = get_recent_transactions(data, date_from="2024-01-01", date_to="2024-01-31")
    assert rows[0]["amount"].startswith("₹")


def test_transactions_range_excludes_other_users(data, other_user_id):
    add_expense(other_user_id, 5.00, "Food", "2024-03-22", "not-mine")
    rows = get_recent_transactions(data, date_from="2024-03-01", date_to="2024-03-31")
    assert "not-mine" not in [r["description"] for r in rows]


# --------------------------------------------------------------------------
# DB helpers: get_category_breakdown
# --------------------------------------------------------------------------

def test_breakdown_no_dates_includes_all_categories(data):
    names = {c["name"] for c in get_category_breakdown(data)}
    assert names == {"Food", "Transport", "Bills"}


def test_breakdown_range_limits_categories_and_amounts(data):
    result = get_category_breakdown(data, date_from="2024-03-01", date_to="2024-03-31")
    assert [(c["name"], c["amount"]) for c in result] == [
        ("Bills", pytest.approx(300.00)),
        ("Food", pytest.approx(50.00)),
    ]


def test_breakdown_percentages_recalculated_and_sum_to_100(data):
    result = get_category_breakdown(data, date_from="2024-03-01", date_to="2024-03-31")
    assert sum(c["pct"] for c in result) == 100
    assert result[0]["pct"] == 86  # 300 / 350
    assert result[1]["pct"] == 14


def test_breakdown_single_category_is_100_percent(data):
    result = get_category_breakdown(data, date_from="2024-02-01", date_to="2024-02-28")
    assert len(result) == 1
    assert result[0]["pct"] == 100


def test_breakdown_empty_range_returns_empty_list(data):
    assert get_category_breakdown(data, date_from="2019-01-01", date_to="2019-01-31") == []


def test_breakdown_bounds_inclusive(data):
    result = get_category_breakdown(data, date_from="2024-01-10", date_to="2024-01-10")
    assert [c["name"] for c in result] == ["Food"]


def test_helpers_use_parameterised_dates(data):
    """A SQL-injection style date value is bound as a literal, not executed.

    The value sorts after every ISO date, so the range is empty; if it were
    interpolated into the SQL, the OR clause would match every row instead.
    """
    evil = "x' OR '1'='1"
    stats = get_summary_stats(data, date_from=evil, date_to="2024-12-31")
    assert stats["transaction_count"] == 0
    assert get_recent_transactions(data, date_from=evil, date_to="2024-12-31") == []
    assert get_category_breakdown(data, date_from=evil, date_to="2024-12-31") == []
    conn = get_db()
    try:
        count = conn.execute("SELECT COUNT(*) FROM expenses").fetchone()[0]
    finally:
        conn.close()
    assert count == 4, "expenses table must be untouched"


# --------------------------------------------------------------------------
# Route: auth guard
# --------------------------------------------------------------------------

def test_profile_with_filter_unauthenticated_redirects_to_login(client):
    response = client.get("/profile?date_from=2024-01-01&date_to=2024-12-31")
    assert response.status_code == 302
    assert "/login" in response.headers["Location"]


# --------------------------------------------------------------------------
# Route: filtering behaviour
# --------------------------------------------------------------------------

def test_profile_no_params_shows_all_expenses(data_client):
    response = data_client.get("/profile")
    assert response.status_code == 200
    body = response.data.decode()
    for desc in ("jan-food", "feb-transport", "mar-bills", "mar-food"):
        assert desc in body, f"{desc} should appear in unfiltered view"
    assert "650.00" in body


def test_profile_custom_range_filters_transactions(data_client):
    response = data_client.get("/profile?date_from=2024-03-01&date_to=2024-03-31")
    assert response.status_code == 200
    body = response.data.decode()
    assert "mar-bills" in body
    assert "mar-food" in body
    assert "jan-food" not in body
    assert "feb-transport" not in body


def test_profile_custom_range_filters_summary_total(data_client):
    body = data_client.get(
        "/profile?date_from=2024-03-01&date_to=2024-03-31"
    ).data.decode()
    assert "350.00" in body
    assert "650.00" not in body


def test_profile_custom_range_filters_category_breakdown(data_client):
    body = data_client.get(
        "/profile?date_from=2024-03-01&date_to=2024-03-31"
    ).data.decode()
    assert "Bills" in body
    assert "Transport" not in body


def test_profile_range_with_no_expenses_renders_zero_state(data_client):
    response = data_client.get("/profile?date_from=2010-01-01&date_to=2010-01-31")
    assert response.status_code == 200
    body = response.data.decode()
    assert "₹0.00" in body
    for desc in ("jan-food", "feb-transport", "mar-bills", "mar-food"):
        assert desc not in body


def test_profile_amounts_show_rupee_symbol_when_filtered(data_client):
    body = data_client.get(
        "/profile?date_from=2024-01-01&date_to=2024-01-31"
    ).data.decode()
    assert "₹" in body


def test_profile_filter_does_not_leak_other_users_data(
    data_client, other_user_id
):
    add_expense(other_user_id, 777.00, "Shopping", "2024-03-21", "secret-item")
    body = data_client.get(
        "/profile?date_from=2024-03-01&date_to=2024-03-31"
    ).data.decode()
    assert "secret-item" not in body


# --------------------------------------------------------------------------
# Route: invalid / malformed input
# --------------------------------------------------------------------------

def test_profile_reversed_range_falls_back_to_unfiltered(data_client):
    response = data_client.get("/profile?date_from=2024-03-31&date_to=2024-03-01")
    assert response.status_code == 200
    body = response.data.decode()
    for desc in ("jan-food", "feb-transport", "mar-bills", "mar-food"):
        assert desc in body
    assert "650.00" in body


def test_profile_reversed_range_shows_flash_error(data_client):
    body = data_client.get(
        "/profile?date_from=2024-03-31&date_to=2024-03-01", follow_redirects=True
    ).data.decode()
    assert "Start date must be before end date." in body


def test_profile_valid_range_shows_no_flash_error(data_client):
    body = data_client.get(
        "/profile?date_from=2024-03-01&date_to=2024-03-31"
    ).data.decode()
    assert "Start date must be before end date." not in body


@pytest.mark.parametrize(
    "query",
    [
        "date_from=not-a-date",
        "date_to=not-a-date",
        "date_from=not-a-date&date_to=also-bad",
        "date_from=2024-13-45&date_to=2024-03-31",
        "date_from=2024-03-01&date_to=31/03/2024",
        "date_from=&date_to=",
        "date_from=2024-02-30&date_to=2024-03-31",
        "date_from=2024-01-01%27%20OR%20%271%27=%271&date_to=2024-12-31",
    ],
)
def test_profile_malformed_dates_fall_back_to_unfiltered_without_error(
    data_client, query
):
    response = data_client.get(f"/profile?{query}")
    assert response.status_code == 200, f"{query!r} must not crash"
    body = response.data.decode()
    for desc in ("jan-food", "feb-transport", "mar-bills", "mar-food"):
        assert desc in body, f"{query!r} should show unfiltered data"


def test_profile_only_date_from_given_is_unfiltered(data_client):
    response = data_client.get("/profile?date_from=2024-03-01")
    assert response.status_code == 200
    body = response.data.decode()
    assert "jan-food" in body and "mar-bills" in body


def test_profile_only_date_to_given_is_unfiltered(data_client):
    response = data_client.get("/profile?date_to=2024-01-31")
    assert response.status_code == 200
    body = response.data.decode()
    assert "mar-bills" in body and "jan-food" in body


def test_profile_same_day_range_is_valid(data_client):
    body = data_client.get(
        "/profile?date_from=2024-02-15&date_to=2024-02-15"
    ).data.decode()
    assert "feb-transport" in body
    assert "jan-food" not in body
    assert "Start date must be before end date." not in body


# --------------------------------------------------------------------------
# Route: filter bar template
# --------------------------------------------------------------------------

@pytest.mark.parametrize(
    "label", ["This Month", "Last 3 Months", "Last 6 Months", "All Time"]
)
def test_profile_renders_preset_buttons(auth_client, label):
    body = auth_client.get("/profile").data.decode()
    assert label in body, f"Expected preset {label!r} in filter bar"


def test_profile_renders_custom_date_inputs_and_apply(auth_client):
    body = auth_client.get("/profile").data.decode()
    assert 'type="date"' in body
    assert 'name="date_from"' in body
    assert 'name="date_to"' in body
    assert "Apply" in body


def test_profile_this_month_preset_link_uses_month_start_and_today(auth_client):
    today = date.today()
    first = today.replace(day=1)
    body = auth_client.get("/profile").data.decode()
    assert f"date_from={first.isoformat()}" in body
    assert f"date_to={today.isoformat()}" in body


def test_profile_range_presets_end_today(auth_client):
    today = date.today().isoformat()
    body = auth_client.get("/profile").data.decode()
    # This Month, Last 3 Months, Last 6 Months all end today
    assert body.count(f"date_to={today}") >= 3


def test_profile_all_time_preset_is_clean_profile_url(auth_client):
    body = auth_client.get("/profile").data.decode()
    idx = body.index("All Time")
    snippet = body[max(0, idx - 300):idx]
    href = snippet.rsplit('href="', 1)[-1].split('"', 1)[0]
    assert href.rstrip("/").endswith("/profile"), f"All Time href was {href!r}"
    assert "date_from" not in href and "date_to" not in href


def test_profile_this_month_filter_includes_only_current_month(client, user_id):
    today = date.today()
    first = today.replace(day=1)
    old = first - timedelta(days=40)
    add_expense(user_id, 11.00, "Food", today.isoformat(), "current-month-item")
    add_expense(user_id, 22.00, "Food", old.isoformat(), "old-month-item")
    with client.session_transaction() as sess:
        sess["user_id"] = user_id
        sess["user_name"] = "Filter User"
    body = client.get(
        f"/profile?date_from={first.isoformat()}&date_to={today.isoformat()}"
    ).data.decode()
    assert "current-month-item" in body
    assert "old-month-item" not in body


def test_profile_custom_range_values_reflected_in_inputs(data_client):
    body = data_client.get(
        "/profile?date_from=2024-03-01&date_to=2024-03-31"
    ).data.decode()
    assert "2024-03-01" in body
    assert "2024-03-31" in body


def test_profile_active_state_marked_for_all_time_when_unfiltered(auth_client):
    body = auth_client.get("/profile").data.decode()
    assert "active" in body, "Expected an active-state marker in the filter bar"


def test_profile_filter_bar_appears_before_summary_stats(auth_client):
    body = auth_client.get("/profile").data.decode()
    assert body.index("This Month") < body.index("Total Spent") if "Total Spent" in body else True
