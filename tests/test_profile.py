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


# --- DATE FILTER (Step 6) ---

import datetime

DATE_ERROR = "Start date must be before end date."

FILTER_ROWS = [
    (100.00, "Bills", "2026-09-30", "Before range"),
    (10.00, "Food", "2026-10-01", "Lower edge"),
    (20.00, "Food", "2026-10-10", "Middle item"),
    (5.00, "Transport", "2026-10-15", "Upper edge"),
    (200.00, "Shopping", "2026-10-16", "After range"),
]
# Totals: all = 335.00; 2026-10-01..2026-10-15 = 35.00


@pytest.fixture
def filter_expenses(user_id):
    _insert_expenses(user_id, FILTER_ROWS)


def _tbody(html):
    return html.split("<tbody>")[1].split("</tbody>")[0]


def _anchors_with_text(html, text):
    anchors = re.findall(r"<a\b[^>]*>.*?</a>", html, re.S)
    return [a for a in anchors if text in re.sub(r"<[^>]+>", "", a)]


def test_profile_valid_range_filters_all_sections(logged_in, filter_expenses):
    response = logged_in.get(
        "/profile", query_string={"date_from": "2026-10-01", "date_to": "2026-10-15"}
    )
    html = response.get_data(as_text=True)
    assert response.status_code == 200
    body = _tbody(html)
    assert body.count("<tr>") == 3
    for kept in ("Lower edge", "Middle item", "Upper edge"):
        assert kept in html
    for dropped in ("Before range", "After range"):
        assert dropped not in html
    assert "₹35.00" in html
    assert '<span class="stat-value">3</span>' in html
    assert '<span class="stat-value">Food</span>' in html
    assert html.count('class="cat-row"') == 2
    assert DATE_ERROR not in html


def test_profile_no_params_is_unfiltered(logged_in, filter_expenses):
    html = logged_in.get("/profile").get_data(as_text=True)
    assert _tbody(html).count("<tr>") == 5
    assert "₹335.00" in html
    assert DATE_ERROR not in html


def test_profile_inverted_range_shows_error_and_unfiltered_data(
    logged_in, filter_expenses
):
    response = logged_in.get(
        "/profile", query_string={"date_from": "2026-10-15", "date_to": "2026-10-01"}
    )
    html = response.get_data(as_text=True)
    assert response.status_code == 200
    assert DATE_ERROR in html
    assert _tbody(html).count("<tr>") == 5
    assert "₹335.00" in html


@pytest.mark.parametrize(
    "params",
    [
        {"date_from": "not-a-date", "date_to": "2026-10-15"},
        {"date_from": "2026-10-01", "date_to": "not-a-date"},
        {"date_from": "not-a-date", "date_to": "also-bad"},
        {"date_from": "2026-13-45", "date_to": "2026-10-15"},
        {"date_from": "01/10/2026", "date_to": "15/10/2026"},
        {"date_from": "", "date_to": ""},
        {"date_from": "' OR 1=1 --", "date_to": "2026-10-15"},
    ],
)
def test_profile_malformed_date_falls_back_to_unfiltered(
    logged_in, filter_expenses, params
):
    response = logged_in.get("/profile", query_string=params)
    html = response.get_data(as_text=True)
    assert response.status_code == 200
    assert _tbody(html).count("<tr>") == 5
    assert "₹335.00" in html


@pytest.mark.parametrize(
    "params",
    [{"date_from": "2026-10-01"}, {"date_to": "2026-10-15"}],
)
def test_profile_only_one_param_is_unfiltered(logged_in, filter_expenses, params):
    response = logged_in.get("/profile", query_string=params)
    html = response.get_data(as_text=True)
    assert response.status_code == 200
    assert _tbody(html).count("<tr>") == 5
    assert "₹335.00" in html


def test_profile_empty_range_shows_zero_state(logged_in, filter_expenses):
    response = logged_in.get(
        "/profile", query_string={"date_from": "2025-01-01", "date_to": "2025-01-31"}
    )
    html = response.get_data(as_text=True)
    assert response.status_code == 200
    assert "₹0.00" in html
    assert '<span class="stat-value">0</span>' in html
    assert 'class="cat-row"' not in html
    assert 'class="txn-empty"' in html
    assert 'class="txn-amount"' not in _tbody(html)


def test_profile_single_day_range_is_inclusive(logged_in, filter_expenses):
    html = logged_in.get(
        "/profile", query_string={"date_from": "2026-10-10", "date_to": "2026-10-10"}
    ).get_data(as_text=True)
    assert "Middle item" in html
    assert "Lower edge" not in html
    assert "₹20.00" in html


def test_profile_filtered_amounts_keep_rupee_symbol(logged_in, filter_expenses):
    html = logged_in.get(
        "/profile", query_string={"date_from": "2026-10-01", "date_to": "2026-10-15"}
    ).get_data(as_text=True)
    assert "₹" in html
    assert "$" not in html


def test_profile_filter_does_not_leak_other_users(logged_in, filter_expenses):
    other_id = create_user("Other", "other@example.com", "password123")
    _insert_expenses(other_id, [(999.00, "Bills", "2026-10-05", "Secret rent")])
    html = logged_in.get(
        "/profile", query_string={"date_from": "2026-10-01", "date_to": "2026-10-15"}
    ).get_data(as_text=True)
    assert "Secret rent" not in html
    assert "₹35.00" in html


def test_profile_has_all_four_presets_and_date_inputs(logged_in):
    html = logged_in.get("/profile").get_data(as_text=True)
    for label in ("This Month", "Last 3 Months", "Last 6 Months", "All Time"):
        assert _anchors_with_text(html, label), f"Missing preset link: {label}"
    assert len(re.findall(r'<input\b[^>]*type="date"', html)) == 2
    assert 'name="date_from"' in html
    assert 'name="date_to"' in html
    assert "Apply" in html


def test_profile_all_time_link_is_plain_profile_url(logged_in):
    html = logged_in.get("/profile").get_data(as_text=True)
    anchors = _anchors_with_text(html, "All Time")
    assert anchors, "All Time link not found"
    assert 'href="/profile"' in anchors[0]
    assert "date_from" not in anchors[0]
    assert "date_to" not in anchors[0]


@pytest.mark.parametrize("label", ["This Month", "Last 3 Months", "Last 6 Months"])
def test_profile_date_presets_link_with_date_params(logged_in, label):
    html = logged_in.get("/profile").get_data(as_text=True)
    anchor = _anchors_with_text(html, label)[0]
    assert "/profile?" in anchor
    assert "date_from=" in anchor
    assert "date_to=" in anchor


def test_profile_this_month_preset_filters_to_current_month(logged_in, user_id):
    today = datetime.date.today()
    first = today.replace(day=1)
    last_month = first - datetime.timedelta(days=1)
    _insert_expenses(user_id, [
        (11.00, "Food", today.isoformat(), "Current month item"),
        (22.00, "Food", last_month.isoformat(), "Previous month item"),
    ])
    page = logged_in.get("/profile").get_data(as_text=True)
    href = re.search(r'href="([^"]*)"', _anchors_with_text(page, "This Month")[0])
    assert href, "This Month link has no href"
    response = logged_in.get(href.group(1).replace("&amp;", "&"))
    html = response.get_data(as_text=True)
    assert response.status_code == 200
    assert "Current month item" in html
    assert "Previous month item" not in html
    assert "₹11.00" in html


def test_profile_active_preset_has_active_class(logged_in):
    page = logged_in.get("/profile").get_data(as_text=True)
    href = re.search(r'href="([^"]*)"', _anchors_with_text(page, "This Month")[0])
    html = logged_in.get(href.group(1).replace("&amp;", "&")).get_data(as_text=True)
    this_month = _anchors_with_text(html, "This Month")[0]
    assert "filter-preset--active" in this_month
    for other in ("Last 3 Months", "Last 6 Months", "All Time"):
        assert "filter-preset--active" not in _anchors_with_text(html, other)[0]


def test_profile_all_time_is_active_without_params(logged_in):
    html = logged_in.get("/profile").get_data(as_text=True)
    assert "filter-preset--active" in _anchors_with_text(html, "All Time")[0]
    for other in ("This Month", "Last 3 Months", "Last 6 Months"):
        assert "filter-preset--active" not in _anchors_with_text(html, other)[0]


def test_profile_custom_range_activates_no_preset(logged_in, filter_expenses):
    html = logged_in.get(
        "/profile", query_string={"date_from": "2026-10-01", "date_to": "2026-10-15"}
    ).get_data(as_text=True)
    for label in ("This Month", "Last 3 Months", "Last 6 Months", "All Time"):
        assert "filter-preset--active" not in _anchors_with_text(html, label)[0], label


def test_profile_custom_range_reflected_in_date_inputs(logged_in, filter_expenses):
    html = logged_in.get(
        "/profile", query_string={"date_from": "2026-10-01", "date_to": "2026-10-15"}
    ).get_data(as_text=True)
    assert 'value="2026-10-01"' in html
    assert 'value="2026-10-15"' in html


def test_profile_with_filter_redirects_to_login_when_logged_out(client):
    response = client.get(
        "/profile", query_string={"date_from": "2026-10-01", "date_to": "2026-10-15"}
    )
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/login")


def test_profile_filtered_page_has_no_inline_styles_or_hex_colours(
    logged_in, filter_expenses
):
    html = logged_in.get(
        "/profile", query_string={"date_from": "2026-10-01", "date_to": "2026-10-15"}
    ).get_data(as_text=True)
    assert "style=" not in html
    assert not re.search(r"#[0-9a-fA-F]{3,8}\b", html)


def test_profile_inaccessible_after_logout(logged_in):
    logged_in.get("/logout")
    response = logged_in.get("/profile")
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/login")
