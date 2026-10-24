from database.db import create_user, get_db


def make_user_with_expenses(rows, email="tester@example.com"):
    """Create a user and insert (amount, category, date, description) rows."""
    user_id = create_user("Test User", email, "password123")
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
    return user_id


# --- TRANSACTIONS ---

from database.db import get_recent_transactions


def test_recent_transactions_newest_first_with_id_tiebreak():
    uid = make_user_with_expenses([
        (10.0, "Food", "2026-10-01", "old"),
        (20.0, "Food", "2026-10-15", "first same day"),
        (30.0, "Bills", "2026-10-15", "second same day"),
    ])
    result = get_recent_transactions(uid)
    assert [r["description"] for r in result] == [
        "second same day", "first same day", "old"
    ]
    assert result[0]["date"] == "15 Oct 2026"
    assert result[0]["amount"] == "₹30.00"
    assert result[0]["badge"] == "bills"


def test_recent_transactions_null_description_dash():
    uid = make_user_with_expenses([(5.0, "Food", "2026-10-01", None)])
    assert get_recent_transactions(uid)[0]["description"] == "—"


def test_recent_transactions_unknown_category_badge_other():
    uid = make_user_with_expenses([(5.0, "Pets", "2026-10-01", "dog food")])
    row = get_recent_transactions(uid)[0]
    assert row["category"] == "Pets"
    assert row["badge"] == "other"


def test_recent_transactions_limit_respected():
    uid = make_user_with_expenses(
        [(1.0, "Food", f"2026-10-{d:02d}", "x") for d in range(1, 8)]
    )
    assert len(get_recent_transactions(uid, limit=3)) == 3
    assert len(get_recent_transactions(uid)) == 7


def test_recent_transactions_empty_user():
    uid = make_user_with_expenses([])
    assert get_recent_transactions(uid) == []


def test_recent_transactions_excludes_other_users():
    uid = make_user_with_expenses(
        [(1.0, "Food", "2026-10-01", "mine")], email="a@example.com"
    )
    make_user_with_expenses(
        [(2.0, "Food", "2026-10-02", "theirs")], email="b@example.com"
    )
    result = get_recent_transactions(uid)
    assert [r["description"] for r in result] == ["mine"]


# --- STATS ---

SUMMARY_STATS_ROWS = [
    (12.50, "Food", "2026-10-01", "Lunch"),
    (3.25, "Transport", "2026-10-02", "Bus"),
    (85.00, "Bills", "2026-10-03", "Electricity"),
    (24.99, "Health", "2026-10-04", "Pharmacy"),
    (15.00, "Entertainment", "2026-10-05", "Movie"),
    (49.90, "Shopping", "2026-10-06", "Shirt"),
    (7.00, "Other", "2026-10-07", "Misc"),
    (18.75, "Food", "2026-10-08", "Dinner"),
]


def test_summary_stats_seed_style_data():
    import pytest
    from database.db import get_summary_stats

    user_id = make_user_with_expenses(SUMMARY_STATS_ROWS, email="stats1@example.com")
    stats = get_summary_stats(user_id)
    assert stats["total_spent"] == pytest.approx(216.39)
    assert stats["transaction_count"] == 8
    assert stats["top_category"] == "Bills"


def test_summary_stats_empty_user():
    from database.db import get_summary_stats

    user_id = make_user_with_expenses([], email="stats2@example.com")
    assert get_summary_stats(user_id) == {
        "total_spent": 0,
        "transaction_count": 0,
        "top_category": "—",
    }


def test_summary_stats_tie_is_alphabetical():
    from database.db import get_summary_stats

    rows = [
        (10.0, "Transport", "2026-10-01", None),
        (10.0, "Food", "2026-10-02", None),
    ]
    user_id = make_user_with_expenses(rows, email="stats3@example.com")
    assert get_summary_stats(user_id)["top_category"] == "Food"


def test_summary_stats_excludes_other_users():
    import pytest
    from database.db import get_summary_stats

    user_a = make_user_with_expenses(
        [(10.0, "Food", "2026-10-01", None)], email="stats4a@example.com"
    )
    make_user_with_expenses(
        [(500.0, "Bills", "2026-10-01", None)], email="stats4b@example.com"
    )
    stats = get_summary_stats(user_a)
    assert stats["total_spent"] == pytest.approx(10.0)
    assert stats["transaction_count"] == 1
    assert stats["top_category"] == "Food"


# --- BREAKDOWN ---

import pytest

from database.db import get_category_breakdown

SEED_BREAKDOWN_ROWS = [
    (12.50, "Food", "2026-10-01", "a"),
    (3.25, "Transport", "2026-10-02", "b"),
    (85.00, "Bills", "2026-10-03", "c"),
    (24.99, "Health", "2026-10-04", "d"),
    (15.00, "Entertainment", "2026-10-05", "e"),
    (49.90, "Shopping", "2026-10-06", "f"),
    (7.00, "Other", "2026-10-07", "g"),
    (18.75, "Food", "2026-10-08", "h"),
]


def test_category_breakdown_seed_data():
    uid = make_user_with_expenses(SEED_BREAKDOWN_ROWS)
    result = get_category_breakdown(uid)
    assert len(result) == 7
    assert result[0]["name"] == "Bills"
    amounts = [r["amount"] for r in result]
    assert amounts == sorted(amounts, reverse=True)
    assert all(isinstance(r["pct"], int) for r in result)
    assert sum(r["pct"] for r in result) == 100
    food = next(r for r in result if r["name"] == "Food")
    assert food["amount"] == pytest.approx(31.25)
    assert food["badge"] == "food"


def test_category_breakdown_remainder_goes_to_first():
    rows = [(10.0, c, "2026-10-01", None) for c in ("Food", "Bills", "Health")]
    uid = make_user_with_expenses(rows)
    result = get_category_breakdown(uid)
    assert [r["name"] for r in result] == ["Bills", "Food", "Health"]
    assert [r["pct"] for r in result] == [34, 33, 33]


def test_category_breakdown_single_category():
    uid = make_user_with_expenses([(5.0, "Food", "2026-10-01", None)])
    result = get_category_breakdown(uid)
    assert len(result) == 1
    assert result[0]["pct"] == 100


def test_category_breakdown_empty_user():
    uid = make_user_with_expenses([])
    assert get_category_breakdown(uid) == []


def test_category_breakdown_excludes_other_users():
    uid = make_user_with_expenses([(5.0, "Food", "2026-10-01", None)], email="a@example.com")
    make_user_with_expenses([(500.0, "Bills", "2026-10-01", None)], email="b@example.com")
    result = get_category_breakdown(uid)
    assert [r["name"] for r in result] == ["Food"]
    assert result[0]["amount"] == pytest.approx(5.0)


def test_category_breakdown_unknown_category_badge_other():
    uid = make_user_with_expenses([(5.0, "Gadgets", "2026-10-01", None)])
    result = get_category_breakdown(uid)
    assert result[0]["name"] == "Gadgets"
    assert result[0]["badge"] == "other"


# --- DATE FILTER (Step 6) ---

# Dates: Sep 30 (outside), Oct 1, Oct 10, Oct 15 (inside), Oct 16 (outside)
DATE_FILTER_ROWS = [
    (100.0, "Bills", "2026-09-30", "before"),
    (10.0, "Food", "2026-10-01", "lower edge"),
    (20.0, "Food", "2026-10-10", "middle"),
    (5.0, "Transport", "2026-10-15", "upper edge"),
    (200.0, "Shopping", "2026-10-16", "after"),
]


def test_summary_stats_date_range_is_inclusive_on_both_bounds():
    from database.db import get_summary_stats

    uid = make_user_with_expenses(DATE_FILTER_ROWS, email="df1@example.com")
    stats = get_summary_stats(uid, date_from="2026-10-01", date_to="2026-10-15")
    assert stats["total_spent"] == pytest.approx(35.0)
    assert stats["transaction_count"] == 3


def test_summary_stats_none_dates_are_unfiltered():
    from database.db import get_summary_stats

    uid = make_user_with_expenses(DATE_FILTER_ROWS, email="df2@example.com")
    unfiltered = get_summary_stats(uid)
    explicit_none = get_summary_stats(uid, date_from=None, date_to=None)
    assert explicit_none == unfiltered
    assert unfiltered["transaction_count"] == 5
    assert unfiltered["total_spent"] == pytest.approx(335.0)


def test_summary_stats_empty_range_returns_zeroes():
    from database.db import get_summary_stats

    uid = make_user_with_expenses(DATE_FILTER_ROWS, email="df3@example.com")
    stats = get_summary_stats(uid, date_from="2025-01-01", date_to="2025-01-31")
    assert stats == {
        "total_spent": 0,
        "transaction_count": 0,
        "top_category": "—",
    }


def test_summary_stats_top_category_respects_range():
    from database.db import get_summary_stats

    uid = make_user_with_expenses(DATE_FILTER_ROWS, email="df4@example.com")
    # Unfiltered top is Shopping (200) / Bills (100); in range it is Food (30).
    assert get_summary_stats(uid)["top_category"] == "Shopping"
    stats = get_summary_stats(uid, date_from="2026-10-01", date_to="2026-10-15")
    assert stats["top_category"] == "Food"


def test_summary_stats_single_day_range():
    from database.db import get_summary_stats

    uid = make_user_with_expenses(DATE_FILTER_ROWS, email="df5@example.com")
    stats = get_summary_stats(uid, date_from="2026-10-10", date_to="2026-10-10")
    assert stats["transaction_count"] == 1
    assert stats["total_spent"] == pytest.approx(20.0)


def test_summary_stats_date_filter_still_scoped_to_user():
    from database.db import get_summary_stats

    uid = make_user_with_expenses(DATE_FILTER_ROWS, email="df6a@example.com")
    make_user_with_expenses(
        [(999.0, "Bills", "2026-10-05", "other user")], email="df6b@example.com"
    )
    stats = get_summary_stats(uid, date_from="2026-10-01", date_to="2026-10-15")
    assert stats["total_spent"] == pytest.approx(35.0)


def test_recent_transactions_date_range_is_inclusive_on_both_bounds():
    uid = make_user_with_expenses(DATE_FILTER_ROWS, email="df7@example.com")
    result = get_recent_transactions(
        uid, date_from="2026-10-01", date_to="2026-10-15"
    )
    assert [r["description"] for r in result] == [
        "upper edge", "middle", "lower edge"
    ]


def test_recent_transactions_none_dates_are_unfiltered():
    uid = make_user_with_expenses(DATE_FILTER_ROWS, email="df8@example.com")
    result = get_recent_transactions(uid, date_from=None, date_to=None)
    assert len(result) == 5
    assert result == get_recent_transactions(uid)


def test_recent_transactions_empty_range_returns_empty_list():
    uid = make_user_with_expenses(DATE_FILTER_ROWS, email="df9@example.com")
    result = get_recent_transactions(
        uid, date_from="2025-01-01", date_to="2025-01-31"
    )
    assert result == []


def test_recent_transactions_limit_applies_within_range():
    uid = make_user_with_expenses(DATE_FILTER_ROWS, email="df10@example.com")
    result = get_recent_transactions(
        uid, limit=2, date_from="2026-10-01", date_to="2026-10-15"
    )
    assert [r["description"] for r in result] == ["upper edge", "middle"]


def test_category_breakdown_date_range_only_includes_in_range_categories():
    uid = make_user_with_expenses(DATE_FILTER_ROWS, email="df11@example.com")
    result = get_category_breakdown(
        uid, date_from="2026-10-01", date_to="2026-10-15"
    )
    assert [r["name"] for r in result] == ["Food", "Transport"]
    assert result[0]["amount"] == pytest.approx(30.0)
    assert result[1]["amount"] == pytest.approx(5.0)


def test_category_breakdown_pct_sums_to_100_within_range():
    uid = make_user_with_expenses(DATE_FILTER_ROWS, email="df12@example.com")
    result = get_category_breakdown(
        uid, date_from="2026-10-01", date_to="2026-10-15"
    )
    assert sum(r["pct"] for r in result) == 100


def test_category_breakdown_none_dates_are_unfiltered():
    uid = make_user_with_expenses(DATE_FILTER_ROWS, email="df13@example.com")
    result = get_category_breakdown(uid, date_from=None, date_to=None)
    assert result == get_category_breakdown(uid)
    assert {r["name"] for r in result} == {"Bills", "Food", "Transport", "Shopping"}


def test_category_breakdown_empty_range_returns_empty_list():
    uid = make_user_with_expenses(DATE_FILTER_ROWS, email="df14@example.com")
    result = get_category_breakdown(
        uid, date_from="2025-01-01", date_to="2025-01-31"
    )
    assert result == []
