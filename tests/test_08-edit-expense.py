"""Tests for Step 8: Edit Expense.

Spec: .claude/specs/08-edit-expense.md

Written against the spec's Routes / Rules for implementation / Tests to
write / Definition of Done sections. These tests do not assume any
implementation detail beyond what the spec states:

  - GET/POST /expenses/<id>/edit require a logged-in session; unauthenticated
    requests to either verb redirect to /login.
  - GET loads the expense via ownership-scoped lookup (id + user_id) and
    renders a form pre-populated with its current values, including a
    <select> with the current category pre-selected. If the expense does
    not exist, or belongs to another user, the route returns 404.
  - POST validates (identical rules to Add Expense):
      * amount: required, float() > 0
      * category: required, must be one of the 7 fixed categories
      * date: required, must be a valid YYYY-MM-DD date
      * description: optional; stripped; stored as NULL when blank
    On any validation failure the form is re-rendered (200, not a redirect)
    with the submitted (not original) values retained, and the row in the
    database is left unchanged.
  - POST is also ownership-scoped: editing another user's expense (or a
    non-existent id) returns 404 and leaves the database unchanged.
  - On success, the row is updated in place for session["user_id"] and the
    response redirects to /profile (never re-renders the form on success).

Exact validation-error copy is not specified by the spec, so failure is
verified behaviourally (200 status + DB row unchanged + values retained)
rather than by asserting on invented wording. As a secondary signal we also
check for the "error" convention already used elsewhere in this codebase
and in tests/test_07-add-expense.py, without requiring a specific class name.

`app` and `client` fixtures come from tests/conftest.py: each test gets a
fresh, isolated on-disk SQLite temp DB (seeded with the demo user) via a
temp-file monkeypatched DB_PATH, so tests do not share state.
"""
from datetime import date

import pytest

import database.db as db
import database.queries as queries

PROFILE_URL = "/profile"
LOGIN_URL = "/login"

DEMO_EMAIL = "demo@spendly.com"
DEMO_PASSWORD = "demo123"

CATEGORIES = ["Food", "Transport", "Bills", "Health", "Entertainment", "Shopping", "Other"]

NONEXISTENT_EXPENSE_ID = 999999


# --------------------------------------------------------------------- #
# Helpers (parameterised SQL only; no behaviour assumptions beyond spec) #
# --------------------------------------------------------------------- #

def _edit_url(expense_id):
    return f"/expenses/{expense_id}/edit"


def _register_and_login(client, email, name="Edit Expense Test User", password="secret123"):
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
    return db.get_user_by_email(email)["id"]


def _login_demo(client):
    client.post("/login", data={"email": DEMO_EMAIL, "password": DEMO_PASSWORD})
    return db.get_user_by_email(DEMO_EMAIL)["id"]


def _insert_expense(user_id, **overrides):
    """Insert a known expense row directly via the query helper (not
    through the route under test) and return its id."""
    defaults = {
        "amount": 40.00,
        "category": "Food",
        "date": "2026-01-15",
        "description": "Original Description",
    }
    defaults.update(overrides)
    return queries.insert_expense(user_id=user_id, **defaults)


def _get_expense_row(expense_id):
    conn = db.get_db()
    try:
        return conn.execute(
            "SELECT * FROM expenses WHERE id = ?", (expense_id,)
        ).fetchone()
    finally:
        conn.close()


def _count_expenses(user_id):
    conn = db.get_db()
    try:
        return conn.execute(
            "SELECT COUNT(*) AS n FROM expenses WHERE user_id = ?", (user_id,)
        ).fetchone()["n"]
    finally:
        conn.close()


def _valid_payload(**overrides):
    payload = {
        "amount": "99.00",
        "category": "Bills",
        "date": "2026-03-20",
        "description": "Updated Description",
    }
    payload.update(overrides)
    return payload


def _assert_row_unchanged(expense_id, original_row):
    """Shared assertion: the row in the DB must exactly match its
    pre-request snapshot after a rejected/blocked POST."""
    current = _get_expense_row(expense_id)
    assert current is not None, "Row must still exist"
    assert current["amount"] == original_row["amount"]
    assert current["category"] == original_row["category"]
    assert current["date"] == original_row["date"]
    assert current["description"] == original_row["description"]


def _assert_validation_failed(response, expense_id, original_row):
    """Shared assertion for a rejected POST: form re-rendered (200), and
    the row in the database was left untouched."""
    assert response.status_code == 200, "Validation failure must re-render the form, not redirect"
    _assert_row_unchanged(expense_id, original_row)


# --------------------------------------------------------------------- #
# Unit tests: database/queries.py::get_expense_by_id                    #
# --------------------------------------------------------------------- #

def test_get_expense_by_id_correct_user_returns_matching_row(app):
    user_id = db.get_user_by_email(DEMO_EMAIL)["id"]
    expense_id = _insert_expense(
        user_id, amount=25.5, category="Transport", date="2026-02-01", description="Bus fare"
    )

    row = queries.get_expense_by_id(expense_id, user_id)

    assert row is not None, "Expected the owning user's lookup to succeed"
    assert row["id"] == expense_id
    assert row["amount"] == 25.5
    assert row["category"] == "Transport"
    assert row["date"] == "2026-02-01"
    assert row["description"] == "Bus fare"


def test_get_expense_by_id_wrong_user_returns_none(app, client):
    owner_id = db.get_user_by_email(DEMO_EMAIL)["id"]
    expense_id = _insert_expense(owner_id)

    other_user_id = _register_and_login(client, email="other-unit@example.com")

    row = queries.get_expense_by_id(expense_id, other_user_id)

    assert row is None, "A user must not be able to fetch another user's expense"


def test_get_expense_by_id_nonexistent_id_returns_none(app):
    user_id = db.get_user_by_email(DEMO_EMAIL)["id"]

    row = queries.get_expense_by_id(NONEXISTENT_EXPENSE_ID, user_id)

    assert row is None, "A non-existent expense_id must return None"


# --------------------------------------------------------------------- #
# Unit tests: database/queries.py::update_expense                       #
# --------------------------------------------------------------------- #

def test_update_expense_correct_user_updates_amount_in_db(app):
    user_id = db.get_user_by_email(DEMO_EMAIL)["id"]
    expense_id = _insert_expense(user_id, amount=10.0)

    queries.update_expense(
        expense_id, user_id, amount=99.0, category="Food", date="2026-01-15",
        description="Original Description",
    )

    row = _get_expense_row(expense_id)
    assert row["amount"] == 99.0, "update_expense must persist the new amount"


def test_update_expense_wrong_user_leaves_row_unchanged_and_raises_no_error(app, client):
    owner_id = db.get_user_by_email(DEMO_EMAIL)["id"]
    expense_id = _insert_expense(owner_id, amount=10.0, category="Food")
    original_row = _get_expense_row(expense_id)

    other_user_id = _register_and_login(client, email="other-update-unit@example.com")

    # Must not raise, and must affect 0 rows.
    result = queries.update_expense(
        expense_id, other_user_id, amount=500.0, category="Shopping",
        date="2099-01-01", description="Hijacked",
    )

    _assert_row_unchanged(expense_id, original_row)
    if result is not None:
        assert result == 0, "update_expense must report 0 rows affected for a non-owner"


# --------------------------------------------------------------------- #
# GET /expenses/<id>/edit — auth guard                                  #
# --------------------------------------------------------------------- #

def test_get_edit_expense_unauthenticated_redirects_to_login(client):
    user_id = _login_demo(client)
    expense_id = _insert_expense(user_id)
    client.get("/logout")

    response = client.get(_edit_url(expense_id))

    assert response.status_code == 302
    assert response.location == LOGIN_URL


# --------------------------------------------------------------------- #
# GET /expenses/<id>/edit — authenticated, own expense                  #
# --------------------------------------------------------------------- #

def test_get_edit_expense_own_expense_returns_200(client):
    user_id = _login_demo(client)
    expense_id = _insert_expense(user_id)

    response = client.get(_edit_url(expense_id))

    assert response.status_code == 200


def test_get_edit_expense_own_expense_prefills_current_values(client):
    user_id = _login_demo(client)
    expense_id = _insert_expense(
        user_id, amount=77.25, category="Health", date="2026-04-10", description="Pharmacy visit"
    )

    response = client.get(_edit_url(expense_id))
    body = response.get_data(as_text=True)

    assert "77.25" in body, "Expected the current amount to be pre-filled"
    assert "2026-04-10" in body, "Expected the current date to be pre-filled"
    assert "Pharmacy visit" in body, "Expected the current description to be pre-filled"


def test_get_edit_expense_own_expense_preselects_current_category(client):
    user_id = _login_demo(client)
    expense_id = _insert_expense(user_id, category="Entertainment")

    response = client.get(_edit_url(expense_id))
    body = response.get_data(as_text=True)

    assert "<select" in body, "Expected a <select> element for category"
    assert "Entertainment" in body, "Expected the current category to appear in the form"
    # The selected option should carry a selected marker alongside the value.
    assert (
        'value="Entertainment" selected' in body
        or 'selected value="Entertainment"' in body
        or ("Entertainment" in body and "selected" in body)
    ), "Expected the current category to be pre-selected in the <select>"


def test_get_edit_expense_own_expense_shows_all_seven_categories(client):
    user_id = _login_demo(client)
    expense_id = _insert_expense(user_id, category="Food")

    response = client.get(_edit_url(expense_id))
    body = response.get_data(as_text=True)

    for category in CATEGORIES:
        assert category in body, f"Expected category option {category!r} in the form"


# --------------------------------------------------------------------- #
# GET /expenses/<id>/edit — ownership / 404                             #
# --------------------------------------------------------------------- #

def test_get_edit_expense_other_users_expense_returns_404(client):
    owner_id = _register_and_login(client, email="owner-get@example.com")
    expense_id = _insert_expense(owner_id)
    client.get("/logout")

    _register_and_login(client, email="intruder-get@example.com")
    response = client.get(_edit_url(expense_id))

    assert response.status_code == 404


def test_get_edit_expense_nonexistent_id_returns_404(client):
    _login_demo(client)

    response = client.get(_edit_url(NONEXISTENT_EXPENSE_ID))

    assert response.status_code == 404


# --------------------------------------------------------------------- #
# POST /expenses/<id>/edit — auth guard                                 #
# --------------------------------------------------------------------- #

def test_post_edit_expense_unauthenticated_redirects_to_login(client):
    user_id = _login_demo(client)
    expense_id = _insert_expense(user_id)
    client.get("/logout")

    response = client.post(_edit_url(expense_id), data=_valid_payload())

    assert response.status_code == 302
    assert response.location == LOGIN_URL


def test_post_edit_expense_unauthenticated_does_not_modify_row(client):
    user_id = _login_demo(client)
    expense_id = _insert_expense(user_id)
    original_row = _get_expense_row(expense_id)
    client.get("/logout")

    client.post(_edit_url(expense_id), data=_valid_payload())

    _assert_row_unchanged(expense_id, original_row)


# --------------------------------------------------------------------- #
# POST /expenses/<id>/edit — happy path                                 #
# --------------------------------------------------------------------- #

def test_post_edit_expense_valid_data_redirects_to_profile(client):
    user_id = _login_demo(client)
    expense_id = _insert_expense(user_id)

    response = client.post(_edit_url(expense_id), data=_valid_payload())

    assert response.status_code == 302
    assert response.location == PROFILE_URL


def test_post_edit_expense_valid_data_updates_row_in_db(client):
    user_id = _login_demo(client)
    expense_id = _insert_expense(
        user_id, amount=10.0, category="Food", date="2026-01-01", description="Old"
    )

    client.post(
        _edit_url(expense_id),
        data=_valid_payload(amount="150.75", category="Shopping", date="2026-07-04", description="New Shoes"),
    )

    row = _get_expense_row(expense_id)
    assert row["amount"] == 150.75
    assert row["category"] == "Shopping"
    assert row["date"] == "2026-07-04"
    assert row["description"] == "New Shoes"


def test_post_edit_expense_valid_data_does_not_rerender_form(client):
    """On success the spec requires a redirect — the form must not be shown again."""
    user_id = _login_demo(client)
    expense_id = _insert_expense(user_id)

    response = client.post(_edit_url(expense_id), data=_valid_payload())

    assert response.status_code != 200


def test_post_edit_expense_updating_one_expense_does_not_affect_another(client):
    user_id = _login_demo(client)
    expense_a = _insert_expense(user_id, amount=10.0, category="Food", date="2026-01-01", description="A")
    expense_b = _insert_expense(user_id, amount=20.0, category="Bills", date="2026-01-02", description="B")

    client.post(
        _edit_url(expense_a),
        data=_valid_payload(amount="999.00", category="Shopping", date="2026-12-25", description="Changed A"),
    )

    row_a = _get_expense_row(expense_a)
    row_b = _get_expense_row(expense_b)

    assert row_a["amount"] == 999.00
    assert row_a["category"] == "Shopping"
    assert row_b["amount"] == 20.0, "Editing expense A must not affect expense B"
    assert row_b["category"] == "Bills"
    assert row_b["date"] == "2026-01-02"
    assert row_b["description"] == "B"


# --------------------------------------------------------------------- #
# POST /expenses/<id>/edit — ownership / 404                            #
# --------------------------------------------------------------------- #

def test_post_edit_expense_other_users_expense_returns_404(client):
    owner_id = _register_and_login(client, email="owner-post@example.com")
    expense_id = _insert_expense(owner_id, amount=10.0, category="Food")
    original_row = _get_expense_row(expense_id)
    client.get("/logout")

    _register_and_login(client, email="intruder-post@example.com")
    response = client.post(_edit_url(expense_id), data=_valid_payload())

    assert response.status_code == 404
    _assert_row_unchanged(expense_id, original_row)


def test_post_edit_expense_nonexistent_id_returns_404(client):
    _login_demo(client)

    response = client.post(_edit_url(NONEXISTENT_EXPENSE_ID), data=_valid_payload())

    assert response.status_code == 404


# --------------------------------------------------------------------- #
# POST /expenses/<id>/edit — amount validation                          #
# --------------------------------------------------------------------- #

@pytest.mark.parametrize(
    "bad_amount",
    ["", "0", "-10", "-0.01", "abc", "twelve"],
    ids=["missing", "zero", "negative", "small_negative", "non_numeric", "words"],
)
def test_post_edit_expense_invalid_amount_rerenders_form_without_updating(client, bad_amount):
    user_id = _login_demo(client)
    expense_id = _insert_expense(user_id)
    original_row = _get_expense_row(expense_id)

    response = client.post(_edit_url(expense_id), data=_valid_payload(amount=bad_amount))

    _assert_validation_failed(response, expense_id, original_row)


# --------------------------------------------------------------------- #
# POST /expenses/<id>/edit — category validation                        #
# --------------------------------------------------------------------- #

@pytest.mark.parametrize(
    "bad_category",
    ["", "Groceries", "food", "Invalid Category"],
    ids=["missing", "not_in_list", "wrong_case", "arbitrary_string"],
)
def test_post_edit_expense_invalid_category_rerenders_form_without_updating(client, bad_category):
    user_id = _login_demo(client)
    expense_id = _insert_expense(user_id)
    original_row = _get_expense_row(expense_id)

    response = client.post(_edit_url(expense_id), data=_valid_payload(category=bad_category))

    _assert_validation_failed(response, expense_id, original_row)


# --------------------------------------------------------------------- #
# POST /expenses/<id>/edit — date validation                            #
# --------------------------------------------------------------------- #

@pytest.mark.parametrize(
    "bad_date",
    ["", "not-a-date", "2026-13-40", "20-03-2026", "2026/03/20"],
    ids=["blank", "garbage_text", "invalid_calendar_date", "wrong_order", "wrong_separator"],
)
def test_post_edit_expense_invalid_date_rerenders_form_without_updating(client, bad_date):
    user_id = _login_demo(client)
    expense_id = _insert_expense(user_id)
    original_row = _get_expense_row(expense_id)

    response = client.post(_edit_url(expense_id), data=_valid_payload(date=bad_date))

    _assert_validation_failed(response, expense_id, original_row)


# --------------------------------------------------------------------- #
# POST /expenses/<id>/edit — validation error indicator + repopulation  #
# --------------------------------------------------------------------- #

@pytest.mark.parametrize(
    "invalid_field, invalid_value",
    [("amount", "abc"), ("category", "Bogus"), ("date", "bogus-date")],
    ids=["bad_amount", "bad_category", "bad_date"],
)
def test_post_edit_expense_validation_error_shows_error_indicator(client, invalid_field, invalid_value):
    """The Tests-to-write section of the spec requires the response body to
    contain an error message. Exact copy is unspecified, so we assert on
    the lower-cased word 'error', matching the convention already used in
    tests/test_07-add-expense.py for the Add Expense feature."""
    user_id = _login_demo(client)
    expense_id = _insert_expense(user_id)

    response = client.post(_edit_url(expense_id), data=_valid_payload(**{invalid_field: invalid_value}))
    body_lower = response.get_data(as_text=True).lower()

    assert response.status_code == 200
    assert "error" in body_lower, "Expected some error indicator when validation fails"


def test_post_edit_expense_invalid_category_repopulates_submitted_values_not_original(client):
    user_id = _login_demo(client)
    expense_id = _insert_expense(
        user_id, amount=10.0, category="Food", date="2026-01-01", description="Original Description"
    )

    response = client.post(
        _edit_url(expense_id),
        data=_valid_payload(
            amount="77.77",
            category="NotARealCategory",
            date="2026-05-05",
            description="Submitted Not Original",
        ),
    )
    body = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "77.77" in body, "Previously submitted amount must be retained, not the original"
    assert "2026-05-05" in body, "Previously submitted date must be retained, not the original"
    assert "Submitted Not Original" in body, "Previously submitted description must be retained"


def test_post_edit_expense_invalid_amount_repopulates_category_and_date(client):
    user_id = _login_demo(client)
    expense_id = _insert_expense(user_id)

    response = client.post(
        _edit_url(expense_id),
        data=_valid_payload(amount="not-a-number", category="Shopping", date="2026-06-06"),
    )
    body = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "2026-06-06" in body, "Previously entered date must be retained"
    assert "Shopping" in body, "Previously selected category must still appear in the form"


# --------------------------------------------------------------------- #
# POST /expenses/<id>/edit — optional description                      #
# --------------------------------------------------------------------- #

def test_post_edit_expense_blank_description_redirects_and_stores_null(client):
    user_id = _login_demo(client)
    expense_id = _insert_expense(user_id, description="Something to be cleared")

    response = client.post(_edit_url(expense_id), data=_valid_payload(description=""))

    assert response.status_code == 302
    assert response.location == PROFILE_URL
    row = _get_expense_row(expense_id)
    assert row["description"] is None, "Blank description must be stored as NULL"


def test_post_edit_expense_whitespace_only_description_stored_as_null(client):
    user_id = _login_demo(client)
    expense_id = _insert_expense(user_id, description="Something to be cleared")

    response = client.post(_edit_url(expense_id), data=_valid_payload(description="   "))

    assert response.status_code == 302
    row = _get_expense_row(expense_id)
    assert row["description"] is None, "Whitespace-only description must be stripped to NULL"


def test_post_edit_expense_missing_description_field_stores_null(client):
    """description is optional — omitting the form field entirely must not
    be treated as a validation error."""
    user_id = _login_demo(client)
    expense_id = _insert_expense(user_id, description="Something to be cleared")
    payload = _valid_payload()
    del payload["description"]

    response = client.post(_edit_url(expense_id), data=payload)

    assert response.status_code == 302
    assert response.location == PROFILE_URL
    row = _get_expense_row(expense_id)
    assert row["description"] is None


# --------------------------------------------------------------------- #
# DB isolation between users                                            #
# --------------------------------------------------------------------- #

def test_post_edit_expense_updates_only_for_session_user_not_other_users(client):
    other_user_id = _register_and_login(client, email="other-isolation@example.com")
    other_expense_id = _insert_expense(other_user_id, amount=5.0, category="Other")
    other_original_row = _get_expense_row(other_expense_id)
    client.get("/logout")

    demo_user_id = _login_demo(client)
    demo_expense_id = _insert_expense(demo_user_id, amount=15.0, category="Food")

    response = client.post(_edit_url(demo_expense_id), data=_valid_payload())

    assert response.status_code == 302
    demo_row = _get_expense_row(demo_expense_id)
    assert demo_row["amount"] != 15.0, "The demo user's own expense should have been updated"
    _assert_row_unchanged(other_expense_id, other_original_row)


# --------------------------------------------------------------------- #
# profile.html — Edit link presence (Definition of Done)                #
# --------------------------------------------------------------------- #

def test_profile_page_shows_edit_link_for_each_transaction(client):
    user_id = _login_demo(client)
    expense_id = _insert_expense(user_id, amount=33.0, category="Food", date="2026-02-02")

    response = client.get(PROFILE_URL)
    body = response.get_data(as_text=True)

    assert response.status_code == 200
    assert _edit_url(expense_id) in body, (
        "Expected the profile page's transaction table to contain an Edit "
        "link pointing to the expense's edit URL"
    )
