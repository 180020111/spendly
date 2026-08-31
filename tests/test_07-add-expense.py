"""Tests for Step 7: Add Expense.

Spec: .claude/specs/07-add-expense.md

Written against the spec's Routes / Rules for implementation / Tests to
write / Definition of Done sections. These tests do not assume any
implementation detail beyond what the spec states:

  - GET/POST /expenses/add require a logged-in session; unauthenticated
    requests to either verb redirect to /login.
  - GET renders a form with amount / category / date / description fields,
    a <select> with the 7 fixed categories, and a POST form.
  - POST validates:
      * amount: required, float() > 0
      * category: required, must be one of the 7 fixed categories
      * date: required, must be a valid YYYY-MM-DD date
      * description: optional; stripped; stored as NULL when blank
    On any validation failure the form is re-rendered (200, not a redirect)
    with the previously submitted values retained, and the new expense is
    NOT written to the database.
  - On success, a row is inserted for session["user_id"] and the response
    redirects to /profile (never re-renders the form on success).

Exact validation-error copy is not specified by the spec, so failure is
verified behaviourally (200 status + no DB write + values retained) rather
than by asserting on invented wording. As a secondary signal we also check
for the "error" CSS-class convention already used elsewhere in this
codebase (see templates/register.html's `class="auth-error"`), without
requiring that specific class name.

`app` and `client` fixtures come from tests/conftest.py: each test gets a
fresh, isolated on-disk SQLite DB (seeded with the demo user) via a
temp-file monkeypatched DB_PATH, so tests do not share state.
"""
from datetime import date

import pytest

import database.db as db
import database.queries as queries

ADD_EXPENSE_URL = "/expenses/add"
PROFILE_URL = "/profile"
LOGIN_URL = "/login"

DEMO_EMAIL = "demo@spendly.com"
DEMO_PASSWORD = "demo123"

CATEGORIES = ["Food", "Transport", "Bills", "Health", "Entertainment", "Shopping", "Other"]


# --------------------------------------------------------------------- #
# Helpers (parameterised SQL only; no behaviour assumptions beyond spec) #
# --------------------------------------------------------------------- #

def _register_and_login(client, email, name="Add Expense Test User", password="secret123"):
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


def _count_expenses(user_id):
    conn = db.get_db()
    try:
        return conn.execute(
            "SELECT COUNT(*) AS n FROM expenses WHERE user_id = ?", (user_id,)
        ).fetchone()["n"]
    finally:
        conn.close()


def _get_expenses(user_id):
    conn = db.get_db()
    try:
        return conn.execute(
            "SELECT * FROM expenses WHERE user_id = ? ORDER BY id DESC", (user_id,)
        ).fetchall()
    finally:
        conn.close()


def _valid_payload(**overrides):
    payload = {
        "amount": "123.45",
        "category": "Bills",
        "date": "2026-03-20",
        "description": "Lunch Meeting",
    }
    payload.update(overrides)
    return payload


def _assert_validation_failed(response, user_id, count_before):
    """Shared assertion for a rejected POST: form re-rendered (200), and
    the invalid submission was never written to the database."""
    assert response.status_code == 200, "Validation failure must re-render the form, not redirect"
    assert _count_expenses(user_id) == count_before, "Invalid submission must not create a row"


# --------------------------------------------------------------------- #
# Unit tests: database/queries.py::insert_expense                       #
# --------------------------------------------------------------------- #

def test_insert_expense_valid_data_row_is_queryable_in_db(app):
    user_id = db.get_user_by_email(DEMO_EMAIL)["id"]

    new_id = queries.insert_expense(
        user_id=user_id,
        amount=50.0,
        category="Food",
        date="2026-03-20",
        description="Lunch",
    )

    conn = db.get_db()
    try:
        row = conn.execute(
            "SELECT * FROM expenses WHERE id = ?", (new_id,)
        ).fetchone()
    finally:
        conn.close()

    assert row is not None, "insert_expense must persist a queryable row"
    assert row["user_id"] == user_id
    assert row["amount"] == 50.0
    assert row["category"] == "Food"
    assert row["date"] == "2026-03-20"
    assert row["description"] == "Lunch"


def test_insert_expense_none_description_stored_as_null(app):
    user_id = db.get_user_by_email(DEMO_EMAIL)["id"]

    new_id = queries.insert_expense(
        user_id=user_id,
        amount=10.0,
        category="Other",
        date="2026-03-21",
        description=None,
    )

    conn = db.get_db()
    try:
        row = conn.execute(
            "SELECT description FROM expenses WHERE id = ?", (new_id,)
        ).fetchone()
    finally:
        conn.close()

    assert row["description"] is None, "A None description must be stored as NULL"


# --------------------------------------------------------------------- #
# GET /expenses/add — auth guard                                        #
# --------------------------------------------------------------------- #

def test_get_add_expense_unauthenticated_redirects_to_login(client):
    response = client.get(ADD_EXPENSE_URL)
    assert response.status_code == 302
    assert response.location == LOGIN_URL


# --------------------------------------------------------------------- #
# GET /expenses/add — authenticated                                     #
# --------------------------------------------------------------------- #

def test_get_add_expense_authenticated_returns_200(client):
    _login_demo(client)
    response = client.get(ADD_EXPENSE_URL)
    assert response.status_code == 200


def test_get_add_expense_authenticated_shows_all_seven_categories(client):
    _login_demo(client)
    response = client.get(ADD_EXPENSE_URL)
    body = response.get_data(as_text=True)

    assert "<select" in body, "Expected a <select> element for category"
    for category in CATEGORIES:
        assert category in body, f"Expected category option {category!r} in the form"


def test_get_add_expense_authenticated_form_posts_to_add_expense(client):
    _login_demo(client)
    response = client.get(ADD_EXPENSE_URL)
    body = response.get_data(as_text=True).lower()

    assert "<form" in body
    assert 'method="post"' in body, "Expected the add-expense form to submit via POST"


def test_get_add_expense_authenticated_date_defaults_to_today(client):
    _login_demo(client)
    response = client.get(ADD_EXPENSE_URL)
    body = response.get_data(as_text=True)

    today = date.today().isoformat()
    assert today in body, "Date field should default to today's date"


# --------------------------------------------------------------------- #
# POST /expenses/add — auth guard                                       #
# --------------------------------------------------------------------- #

def test_post_add_expense_unauthenticated_redirects_to_login(client):
    response = client.post(ADD_EXPENSE_URL, data=_valid_payload())
    assert response.status_code == 302
    assert response.location == LOGIN_URL


def test_post_add_expense_unauthenticated_does_not_insert_row(client):
    user_id = _login_demo(client)
    client.get("/logout")

    before = _count_expenses(user_id)
    client.post(ADD_EXPENSE_URL, data=_valid_payload())
    after = _count_expenses(user_id)

    assert after == before, "Unauthenticated POST must never write to the database"


# --------------------------------------------------------------------- #
# POST /expenses/add — happy path                                       #
# --------------------------------------------------------------------- #

def test_post_add_expense_valid_data_redirects_to_profile(client):
    _login_demo(client)
    response = client.post(ADD_EXPENSE_URL, data=_valid_payload())
    assert response.status_code == 302
    assert response.location == PROFILE_URL


def test_post_add_expense_valid_data_inserts_row_for_current_user(client):
    user_id = _login_demo(client)
    before = _count_expenses(user_id)

    client.post(
        ADD_EXPENSE_URL,
        data=_valid_payload(amount="99.99", category="Health", date="2026-04-15", description="Checkup"),
    )

    rows = _get_expenses(user_id)
    assert _count_expenses(user_id) == before + 1, "A new row must be inserted for the logged-in user"

    newest = rows[0]
    assert newest["user_id"] == user_id
    assert newest["amount"] == 99.99
    assert newest["category"] == "Health"
    assert newest["date"] == "2026-04-15"
    assert newest["description"] == "Checkup"


def test_post_add_expense_valid_data_does_not_rerender_form(client):
    """On success the spec requires a redirect — the form must not be shown again."""
    _login_demo(client)
    response = client.post(ADD_EXPENSE_URL, data=_valid_payload())
    assert response.status_code != 200


# --------------------------------------------------------------------- #
# POST /expenses/add — amount validation                                #
# --------------------------------------------------------------------- #

@pytest.mark.parametrize(
    "bad_amount",
    ["", "0", "-10", "-0.01", "abc", "twelve"],
    ids=["missing", "zero", "negative", "small_negative", "non_numeric", "words"],
)
def test_post_add_expense_invalid_amount_rerenders_form_without_inserting(client, bad_amount):
    user_id = _login_demo(client)
    before = _count_expenses(user_id)

    response = client.post(ADD_EXPENSE_URL, data=_valid_payload(amount=bad_amount))

    _assert_validation_failed(response, user_id, before)


# --------------------------------------------------------------------- #
# POST /expenses/add — category validation                              #
# --------------------------------------------------------------------- #

@pytest.mark.parametrize(
    "bad_category",
    ["", "Groceries", "food", "Invalid Category"],
    ids=["missing", "not_in_list", "wrong_case", "arbitrary_string"],
)
def test_post_add_expense_invalid_category_rerenders_form_without_inserting(client, bad_category):
    user_id = _login_demo(client)
    before = _count_expenses(user_id)

    response = client.post(ADD_EXPENSE_URL, data=_valid_payload(category=bad_category))

    _assert_validation_failed(response, user_id, before)


# --------------------------------------------------------------------- #
# POST /expenses/add — date validation                                  #
# --------------------------------------------------------------------- #

@pytest.mark.parametrize(
    "bad_date",
    ["", "not-a-date", "2026-13-40", "20-03-2026", "2026/03/20"],
    ids=["blank", "garbage_text", "invalid_calendar_date", "wrong_order", "wrong_separator"],
)
def test_post_add_expense_invalid_date_rerenders_form_without_inserting(client, bad_date):
    user_id = _login_demo(client)
    before = _count_expenses(user_id)

    response = client.post(ADD_EXPENSE_URL, data=_valid_payload(date=bad_date))

    _assert_validation_failed(response, user_id, before)


# --------------------------------------------------------------------- #
# POST /expenses/add — optional description                             #
# --------------------------------------------------------------------- #

def test_post_add_expense_blank_description_redirects_and_stores_null(client):
    user_id = _login_demo(client)

    response = client.post(ADD_EXPENSE_URL, data=_valid_payload(description=""))

    assert response.status_code == 302
    assert response.location == PROFILE_URL
    newest = _get_expenses(user_id)[0]
    assert newest["description"] is None, "Blank description must be stored as NULL"


def test_post_add_expense_whitespace_only_description_stored_as_null(client):
    user_id = _login_demo(client)

    response = client.post(ADD_EXPENSE_URL, data=_valid_payload(description="   "))

    assert response.status_code == 302
    newest = _get_expenses(user_id)[0]
    assert newest["description"] is None, "Whitespace-only description must be stripped to NULL"


def test_post_add_expense_missing_description_field_stores_null(client):
    """description is optional — omitting the form field entirely must not
    be treated as a validation error."""
    user_id = _login_demo(client)
    payload = _valid_payload()
    del payload["description"]

    response = client.post(ADD_EXPENSE_URL, data=payload)

    assert response.status_code == 302
    assert response.location == PROFILE_URL
    newest = _get_expenses(user_id)[0]
    assert newest["description"] is None


# --------------------------------------------------------------------- #
# POST /expenses/add — form repopulation on error                       #
# --------------------------------------------------------------------- #

def test_post_add_expense_invalid_category_repopulates_amount_date_description(client):
    _login_demo(client)

    response = client.post(
        ADD_EXPENSE_URL,
        data=_valid_payload(
            amount="77.77",
            category="NotARealCategory",
            date="2026-05-05",
            description="Repopulation Check Description",
        ),
    )
    body = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "77.77" in body, "Previously entered amount must be retained"
    assert "2026-05-05" in body, "Previously entered date must be retained"
    assert "Repopulation Check Description" in body, "Previously entered description must be retained"


def test_post_add_expense_invalid_amount_repopulates_category_and_date(client):
    _login_demo(client)

    response = client.post(
        ADD_EXPENSE_URL,
        data=_valid_payload(amount="not-a-number", category="Shopping", date="2026-06-06"),
    )
    body = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "2026-06-06" in body, "Previously entered date must be retained"
    assert "Shopping" in body, "Previously selected category must still appear in the form"


def test_post_add_expense_invalid_date_repopulates_amount_and_category(client):
    _login_demo(client)

    response = client.post(
        ADD_EXPENSE_URL,
        data=_valid_payload(amount="55.00", category="Entertainment", date="not-a-date"),
    )
    body = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "55.00" in body or "55" in body, "Previously entered amount must be retained"
    assert "Entertainment" in body, "Previously selected category must still appear in the form"


@pytest.mark.parametrize(
    "invalid_field, invalid_value",
    [("amount", "abc"), ("category", "Bogus"), ("date", "bogus-date")],
    ids=["bad_amount", "bad_category", "bad_date"],
)
def test_post_add_expense_validation_error_shows_error_indicator(client, invalid_field, invalid_value):
    """The Tests-to-write section of the spec requires the response body to
    contain an error message. Exact copy is unspecified, so we assert on
    the lower-cased word 'error', which matches this codebase's existing
    validation-error convention (see templates/register.html's
    `class="auth-error"`)."""
    _login_demo(client)
    response = client.post(ADD_EXPENSE_URL, data=_valid_payload(**{invalid_field: invalid_value}))
    body_lower = response.get_data(as_text=True).lower()

    assert response.status_code == 200
    assert "error" in body_lower, "Expected some error indicator when validation fails"


# --------------------------------------------------------------------- #
# DB isolation between users                                            #
# --------------------------------------------------------------------- #

def test_post_add_expense_inserts_only_for_session_user_not_other_users(client):
    other_user_id = _register_and_login(client, email="otheruser@example.com")
    client.get("/logout")

    demo_user_id = _login_demo(client)
    client.post(ADD_EXPENSE_URL, data=_valid_payload())

    assert _count_expenses(other_user_id) == 0, "Expense must be scoped to the logged-in user only"
    assert _count_expenses(demo_user_id) >= 1
