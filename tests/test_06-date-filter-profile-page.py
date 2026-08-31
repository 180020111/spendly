"""Tests for Step 6: date-range filter on the /profile page.

Spec: .claude/specs/06-date-filter-profile-page.md

These tests are written against the spec's Routes / Rules for implementation /
Definition of Done sections. They do not assume any implementation details
beyond what the spec states:
  - GET /profile reads optional `date_from` / `date_to` query params
    (ISO YYYY-MM-DD, inclusive bounds).
  - Missing/malformed/one-sided params -> fall back to unfiltered ("All Time").
  - date_from > date_to -> fall back to unfiltered AND show a flash error:
    "Start date must be before end date."
  - Four presets (This Month, Last 3 Months, Last 6 Months, All Time) are
    exposed as links in the rendered page; "This Month" is defined by the
    spec itself as "first day of current month" through today. The other two
    presets are exercised via whatever link the app actually renders, rather
    than by re-deriving the app's month-boundary arithmetic, so these tests
    stay valid regardless of the exact day-level cutoff the app chooses.
  - All three data sections (summary stats, recent transactions, category
    breakdown) must respect the active filter.
  - The Rupee symbol must always be present, filtered or not.

`app` and `client` fixtures come from tests/conftest.py: each test gets a
fresh, isolated on-disk SQLite DB (seeded with the demo user) via a
temp-file monkeypatched DB_PATH, so tests do not share state.
"""
import html
import re
from datetime import date, timedelta

import pytest

import database.db as db

DEMO_EMAIL = "demo@spendly.com"
DEMO_PASSWORD = "demo123"


# --------------------------------------------------------------------- #
# Helpers (parameterised SQL only; no behaviour assumptions beyond spec) #
# --------------------------------------------------------------------- #

def _register_and_login(client, email, name="Filter Test User", password="secret123"):
    client.post(
        "/register",
        data={
            "name": name,
            "email": email,
            "password": password,
            "confirm_password": password,
        },
    )
    client.post("/login", data={"email": email, "password": password})
    user = db.get_user_by_email(email)
    return user["id"]


def _create_expense(user_id, amount, category, expense_date, description):
    conn = db.get_db()
    try:
        conn.execute(
            "INSERT INTO expenses (user_id, amount, category, date, description) "
            "VALUES (?, ?, ?, ?, ?)",
            (user_id, amount, category, expense_date, description),
        )
        conn.commit()
    finally:
        conn.close()


def _count_expenses(user_id):
    conn = db.get_db()
    try:
        row = conn.execute(
            "SELECT COUNT(*) AS n FROM expenses WHERE user_id = ?", (user_id,)
        ).fetchone()
        return row["n"]
    finally:
        conn.close()


def _shift_months(d, n):
    """First day of the calendar month that is n months before d's month.

    Pure calendar arithmetic used only to place test fixture *data* at safe
    distances from "today" (e.g. "clearly two months ago") -- not an
    assumption about how the app itself computes preset boundaries.
    """
    total = d.year * 12 + (d.month - 1) - n
    year, month = divmod(total, 12)
    return date(year, month + 1, 1)


def _get_preset_href(body_text, label):
    """Extract (and HTML-unescape) the href of the preset link with this label.

    The spec requires each preset to be "a link ... with the appropriate
    date_from/date_to query params" — we simulate clicking that real link
    rather than re-deriving its date math ourselves.
    """
    pattern = r'<a href="([^"]+)"[^>]*>\s*' + re.escape(label) + r"\s*</a>"
    match = re.search(pattern, body_text)
    assert match, f"Expected a {label!r} preset link in the profile filter bar"
    return html.unescape(match.group(1))


# --------------------------------------------------------------------- #
# Fixtures                                                               #
# --------------------------------------------------------------------- #

class Expenses:
    """Container for a preset-testing dataset: one expense per era, each with
    a unique category/description so presence/absence is unambiguous."""

    TODAY = ("Food", 100.00, "Today Food Expense")
    TWO_MONTHS_AGO = ("Transport", 50.00, "Two Months Ago Transport Expense")
    FIVE_MONTHS_AGO = ("Bills", 25.00, "Five Months Ago Bills Expense")
    EIGHT_MONTHS_AGO = ("Entertainment", 10.00, "Eight Months Ago Entertainment Expense")


def _seed_preset_dataset(user_id):
    today = date.today()
    dated = {
        "today": (today, Expenses.TODAY),
        "two_months_ago": (_shift_months(today, 2), Expenses.TWO_MONTHS_AGO),
        "five_months_ago": (_shift_months(today, 5), Expenses.FIVE_MONTHS_AGO),
        "eight_months_ago": (_shift_months(today, 8), Expenses.EIGHT_MONTHS_AGO),
    }
    for _, (d, (category, amount, description)) in dated.items():
        _create_expense(user_id, amount, category, d.isoformat(), description)
    return dated


@pytest.fixture
def preset_client(client):
    """A logged-in client whose user has 4 expenses spread across "today",
    "2 months ago", "5 months ago" and "8 months ago"."""
    user_id = _register_and_login(client, email="presetuser@example.com")
    dated = _seed_preset_dataset(user_id)
    return client, user_id, dated


# --------------------------------------------------------------------- #
# Auth guard                                                             #
# --------------------------------------------------------------------- #

def test_profile_unauthenticated_no_filter_redirects_to_login(client):
    response = client.get("/profile")
    assert response.status_code == 302
    assert response.location == "/login"


def test_profile_unauthenticated_with_filter_params_redirects_to_login(client):
    response = client.get("/profile?date_from=2024-01-01&date_to=2024-01-31")
    assert response.status_code == 302, "Filter params must not bypass the login guard"
    assert response.location == "/login"


# --------------------------------------------------------------------- #
# DoD: no query params behaves like Step 5 (unfiltered)                 #
# --------------------------------------------------------------------- #

def test_profile_no_query_params_returns_unfiltered_seed_data(client):
    client.post("/login", data={"email": DEMO_EMAIL, "password": DEMO_PASSWORD})
    response = client.get("/profile")
    body = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "₹" in body, "Rupee symbol must be present"
    assert "288.94" in body, "Unfiltered total should match all 8 seed expenses"
    assert ">8<" in body, "Unfiltered transaction count should be 8"
    assert "Bills" in body


def test_rupee_symbol_present_in_unfiltered_view(client):
    client.post("/login", data={"email": DEMO_EMAIL, "password": DEMO_PASSWORD})
    response = client.get("/profile")
    assert "₹" in response.get_data(as_text=True)


# --------------------------------------------------------------------- #
# Presets                                                                #
# --------------------------------------------------------------------- #

def test_this_month_preset_filters_to_current_calendar_month(preset_client):
    client, _, dated = preset_client
    baseline = client.get("/profile")
    href = _get_preset_href(baseline.get_data(as_text=True), "This Month")

    response = client.get(href)
    body = response.get_data(as_text=True)

    assert response.status_code == 200
    assert Expenses.TODAY[2] in body, "Today's expense must be in the This Month view"
    assert Expenses.TWO_MONTHS_AGO[2] not in body
    assert Expenses.FIVE_MONTHS_AGO[2] not in body
    assert Expenses.EIGHT_MONTHS_AGO[2] not in body
    assert "Food" in body
    assert "Transport" not in body


def test_last_3_months_preset_filters_within_window(preset_client):
    client, _, dated = preset_client
    baseline = client.get("/profile")
    href = _get_preset_href(baseline.get_data(as_text=True), "Last 3 Months")

    response = client.get(href)
    body = response.get_data(as_text=True)

    assert response.status_code == 200
    assert Expenses.TODAY[2] in body
    assert Expenses.TWO_MONTHS_AGO[2] in body, "2-months-ago expense must be within a 3-month window"
    assert Expenses.FIVE_MONTHS_AGO[2] not in body
    assert Expenses.EIGHT_MONTHS_AGO[2] not in body


def test_last_6_months_preset_filters_within_window(preset_client):
    client, _, dated = preset_client
    baseline = client.get("/profile")
    href = _get_preset_href(baseline.get_data(as_text=True), "Last 6 Months")

    response = client.get(href)
    body = response.get_data(as_text=True)

    assert response.status_code == 200
    assert Expenses.TODAY[2] in body
    assert Expenses.TWO_MONTHS_AGO[2] in body
    assert Expenses.FIVE_MONTHS_AGO[2] in body, "5-months-ago expense must be within a 6-month window"
    assert Expenses.EIGHT_MONTHS_AGO[2] not in body, "8-months-ago expense must be outside a 6-month window"


def test_all_time_preset_link_has_no_query_params(preset_client):
    client, _, _ = preset_client
    filtered = client.get("/profile?date_from=2024-01-01&date_to=2024-01-02")
    href = _get_preset_href(filtered.get_data(as_text=True), "All Time")
    assert href == "/profile", "All Time preset must be a clean /profile URL with no query params"


def test_all_time_preset_shows_all_expenses_regardless_of_prior_filter(preset_client):
    client, _, _ = preset_client
    filtered = client.get("/profile?date_from=2024-01-01&date_to=2024-01-02")
    href = _get_preset_href(filtered.get_data(as_text=True), "All Time")

    response = client.get(href)
    body = response.get_data(as_text=True)

    assert response.status_code == 200
    for _, amount, description in (
        Expenses.TODAY,
        Expenses.TWO_MONTHS_AGO,
        Expenses.FIVE_MONTHS_AGO,
        Expenses.EIGHT_MONTHS_AGO,
    ):
        assert description in body, f"All Time must include: {description}"


# --------------------------------------------------------------------- #
# Custom date range                                                     #
# --------------------------------------------------------------------- #

def test_custom_date_range_filters_all_three_sections(client):
    user_id = _register_and_login(client, email="customrange@example.com")
    _create_expense(user_id, 10.00, "Food", "2024-01-01", "Before Range Expense")
    _create_expense(user_id, 20.00, "Transport", "2024-02-15", "Inside Range Expense")
    _create_expense(user_id, 30.00, "Bills", "2024-04-01", "After Range Expense")

    response = client.get("/profile?date_from=2024-02-01&date_to=2024-03-01")
    body = response.get_data(as_text=True)

    assert response.status_code == 200
    # Summary stats: only the in-range expense should be counted.
    assert "20.00" in body
    assert ">1<" in body
    # Recent transactions: only the in-range description should appear.
    assert "Inside Range Expense" in body
    assert "Before Range Expense" not in body
    assert "After Range Expense" not in body
    # Category breakdown: only the in-range category should appear.
    assert "Transport" in body
    assert "Food" not in body
    assert "Bills" not in body


def test_custom_date_range_boundaries_are_inclusive(client):
    user_id = _register_and_login(client, email="inclusive@example.com")
    _create_expense(user_id, 15.00, "Food", "2024-05-01", "Start Boundary Expense")
    _create_expense(user_id, 25.00, "Transport", "2024-05-31", "End Boundary Expense")
    _create_expense(user_id, 35.00, "Bills", "2024-04-30", "Just Before Start Expense")
    _create_expense(user_id, 45.00, "Health", "2024-06-01", "Just After End Expense")

    response = client.get("/profile?date_from=2024-05-01&date_to=2024-05-31")
    body = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "Start Boundary Expense" in body, "date_from bound must be inclusive"
    assert "End Boundary Expense" in body, "date_to bound must be inclusive"
    assert "Just Before Start Expense" not in body
    assert "Just After End Expense" not in body
    assert ">2<" in body


def test_active_custom_range_reflected_in_date_input_fields(client):
    """DoD: 'the active preset button or custom-range fields visually
    indicate which filter is currently applied.' We check this without
    assuming any particular CSS class name: the two <input type="date">
    fields the spec mandates must at least carry the active values."""
    _register_and_login(client, email="activestate@example.com")
    response = client.get("/profile?date_from=2024-02-01&date_to=2024-03-01")
    body = response.get_data(as_text=True)

    assert response.status_code == 200
    assert 'value="2024-02-01"' in body, "date_from input should reflect the active filter"
    assert 'value="2024-03-01"' in body, "date_to input should reflect the active filter"


# --------------------------------------------------------------------- #
# Validation errors / malformed input                                   #
# --------------------------------------------------------------------- #

def test_date_from_after_date_to_falls_back_to_unfiltered_with_error(preset_client):
    client, _, _ = preset_client
    response = client.get("/profile?date_from=2024-03-01&date_to=2024-01-01")
    body = response.get_data(as_text=True)

    assert response.status_code == 200, "Invalid range must not crash the app"
    assert "Start date must be before end date." in body
    for _, _, description in (
        Expenses.TODAY,
        Expenses.TWO_MONTHS_AGO,
        Expenses.FIVE_MONTHS_AGO,
        Expenses.EIGHT_MONTHS_AGO,
    ):
        assert description in body, "Invalid range must fall back to showing all expenses"


def test_malformed_date_string_falls_back_to_unfiltered_without_crashing(preset_client):
    client, _, _ = preset_client
    response = client.get("/profile?date_from=not-a-date&date_to=2024-01-01")
    body = response.get_data(as_text=True)

    assert response.status_code == 200, "Malformed date must not crash the app"
    for _, _, description in (
        Expenses.TODAY,
        Expenses.TWO_MONTHS_AGO,
        Expenses.FIVE_MONTHS_AGO,
        Expenses.EIGHT_MONTHS_AGO,
    ):
        assert description in body, "Malformed date must fall back to the unfiltered view"


def test_one_sided_date_range_falls_back_to_unfiltered(preset_client):
    client, _, _ = preset_client
    response = client.get("/profile?date_from=2024-01-01")
    body = response.get_data(as_text=True)

    assert response.status_code == 200
    for _, _, description in (
        Expenses.TODAY,
        Expenses.TWO_MONTHS_AGO,
        Expenses.FIVE_MONTHS_AGO,
        Expenses.EIGHT_MONTHS_AGO,
    ):
        assert description in body, "A one-sided range cannot drive a filter; must fall back to unfiltered"


def test_sql_injection_attempt_in_date_param_does_not_crash_or_leak(preset_client):
    client, _, _ = preset_client
    malicious = "2024-01-01' OR '1'='1"
    response = client.get(f"/profile?date_from={malicious}&date_to=2024-12-31")
    body = response.get_data(as_text=True)

    assert response.status_code == 200, "SQL-injection-shaped input must not crash the app"
    for _, _, description in (
        Expenses.TODAY,
        Expenses.TWO_MONTHS_AGO,
        Expenses.FIVE_MONTHS_AGO,
        Expenses.EIGHT_MONTHS_AGO,
    ):
        assert description in body, "Unparseable input must fall back to the unfiltered view"


def test_excessively_long_date_string_does_not_crash(preset_client):
    client, _, _ = preset_client
    long_value = "9" * 5000
    response = client.get(f"/profile?date_from={long_value}&date_to=2024-01-01")
    assert response.status_code == 200, "Very long malformed input must not crash the app"


# --------------------------------------------------------------------- #
# Zero-match range                                                      #
# --------------------------------------------------------------------- #

def test_zero_matching_expenses_in_range_shows_zero_state(preset_client):
    client, _, _ = preset_client
    future_from = (date.today() + timedelta(days=400)).isoformat()
    future_to = (date.today() + timedelta(days=410)).isoformat()

    response = client.get(f"/profile?date_from={future_from}&date_to={future_to}")
    body = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "₹" in body, "Rupee symbol must still be present with zero results"
    assert "0.00" in body, "Total spent should be ₹0.00"
    assert ">0<" in body, "Transaction count should be 0"
    assert "—" in body, "Top category should fall back to the em-dash placeholder"
    for _, _, description in (
        Expenses.TODAY,
        Expenses.TWO_MONTHS_AGO,
        Expenses.FIVE_MONTHS_AGO,
        Expenses.EIGHT_MONTHS_AGO,
    ):
        assert description not in body
    for category in ("Food", "Transport", "Bills", "Entertainment"):
        assert category not in body, "Category breakdown must be empty for a zero-match range"


def test_zero_matching_expenses_for_brand_new_user_with_filter(client):
    _register_and_login(client, email="brandnew@example.com")
    response = client.get("/profile?date_from=2024-01-01&date_to=2024-01-31")
    body = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "₹" in body
    assert "0.00" in body
    assert ">0<" in body


# --------------------------------------------------------------------- #
# DB side effects                                                       #
# --------------------------------------------------------------------- #

def test_filtering_does_not_mutate_database_rows(preset_client):
    client, user_id, _ = preset_client
    before = _count_expenses(user_id)

    client.get("/profile?date_from=2024-01-01&date_to=2024-01-31")  # zero-match custom range
    client.get("/profile?date_from=bad&date_to=bad")  # malformed
    client.get("/profile?date_from=2024-03-01&date_to=2024-01-01")  # swapped
    client.get("/profile")  # unfiltered

    after = _count_expenses(user_id)
    assert after == before, "Read-only filtering must never change the number of expense rows"


# --------------------------------------------------------------------- #
# Rupee symbol invariant across all filter states                       #
# --------------------------------------------------------------------- #

@pytest.mark.parametrize(
    "query_string",
    [
        "",
        "?date_from=2024-01-01&date_to=2024-12-31",
        "?date_from=2024-12-31&date_to=2024-01-01",
        "?date_from=not-a-date&date_to=also-not-a-date",
        "?date_from=2030-01-01&date_to=2030-01-31",
    ],
)
def test_rupee_symbol_always_present_regardless_of_filter_state(preset_client, query_string):
    client, _, _ = preset_client
    response = client.get(f"/profile{query_string}")
    assert response.status_code == 200
    assert "₹" in response.get_data(as_text=True)
