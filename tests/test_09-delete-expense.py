"""Tests for Step 9: Delete Expense.

Spec: .claude/specs/09-delete-expense.md

Written against the spec's Routes / Rules for implementation / Tests to
write / Definition of Done sections. These tests do not assume any
implementation detail beyond what the spec states:

  - POST /expenses/<id>/delete requires a logged-in session; an
    unauthenticated request redirects to /login (302) and the row is not
    deleted.
  - The route only accepts POST — a bare GET must return 405 (Method Not
    Allowed), for both logged-out and logged-in users, and must not delete
    anything.
  - The handler looks the expense up scoped to the current user (ownership
    guard, reusing get_expense_by_id semantics from Step 8). If the
    expense does not exist, or belongs to another user, the route returns
    404 and the row is left untouched.
  - On success the row is permanently removed from the database and the
    response redirects to /profile (never renders a template).
  - database/queries.py::delete_expense(expense_id, user_id) issues a
    parameterised DELETE scoped to id AND user_id: for the correct owner
    the row is removed; for a non-owner or a non-existent id, 0 rows are
    affected, no error is raised, and the database is left unchanged.
  - Each transaction row on the profile page renders both an Edit action
    and a Delete action (a POST form) per the "Actions" column
    requirement carried over from Step 8 and extended by this spec.

`app` and `client` fixtures come from tests/conftest.py: each test gets a
fresh, isolated on-disk SQLite temp DB (seeded with the demo user) via a
temp-file monkeypatched DB_PATH, so tests do not share state.
"""
import database.db as db
import database.queries as queries

PROFILE_URL = "/profile"
LOGIN_URL = "/login"

DEMO_EMAIL = "demo@spendly.com"
DEMO_PASSWORD = "demo123"

NONEXISTENT_EXPENSE_ID = 999999


# --------------------------------------------------------------------- #
# Helpers (parameterised SQL only; no behaviour assumptions beyond spec) #
# --------------------------------------------------------------------- #

def _delete_url(expense_id):
    return f"/expenses/{expense_id}/delete"


def _edit_url(expense_id):
    return f"/expenses/{expense_id}/edit"


def _register_and_login(client, email, name="Delete Expense Test User", password="secret123"):
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


def _assert_row_unchanged(expense_id, original_row):
    """Shared assertion: the row in the DB must exactly match its
    pre-request snapshot after a rejected/blocked delete attempt."""
    current = _get_expense_row(expense_id)
    assert current is not None, "Row must still exist"
    assert current["amount"] == original_row["amount"]
    assert current["category"] == original_row["category"]
    assert current["date"] == original_row["date"]
    assert current["description"] == original_row["description"]


# --------------------------------------------------------------------- #
# Unit tests: database/queries.py::delete_expense                       #
# --------------------------------------------------------------------- #

def test_delete_expense_correct_user_removes_row_from_db(app):
    user_id = db.get_user_by_email(DEMO_EMAIL)["id"]
    expense_id = _insert_expense(user_id, amount=25.5, category="Transport")

    queries.delete_expense(expense_id, user_id)

    assert _get_expense_row(expense_id) is None, "Row must be removed for the owning user"


def test_delete_expense_wrong_user_leaves_row_and_raises_no_error(app, client):
    owner_id = db.get_user_by_email(DEMO_EMAIL)["id"]
    expense_id = _insert_expense(owner_id, amount=10.0, category="Food")
    original_row = _get_expense_row(expense_id)

    other_user_id = _register_and_login(client, email="other-unit-delete@example.com")

    # Must not raise, and must affect 0 rows.
    result = queries.delete_expense(expense_id, other_user_id)

    _assert_row_unchanged(expense_id, original_row)
    if result is not None:
        assert result == 0, "delete_expense must report 0 rows affected for a non-owner"


def test_delete_expense_nonexistent_id_no_error_db_unchanged(app):
    user_id = db.get_user_by_email(DEMO_EMAIL)["id"]
    expense_id = _insert_expense(user_id)
    before_count = _count_expenses(user_id)

    # Must not raise for an id that doesn't exist at all.
    result = queries.delete_expense(NONEXISTENT_EXPENSE_ID, user_id)

    assert _count_expenses(user_id) == before_count, "DB must be unchanged when the id doesn't exist"
    assert _get_expense_row(expense_id) is not None, "Unrelated existing row must be untouched"
    if result is not None:
        assert result == 0, "delete_expense must report 0 rows affected for a non-existent id"


# --------------------------------------------------------------------- #
# POST /expenses/<id>/delete — auth guard                               #
# --------------------------------------------------------------------- #

def test_post_delete_expense_unauthenticated_redirects_to_login(client):
    user_id = _login_demo(client)
    expense_id = _insert_expense(user_id)
    client.get("/logout")

    response = client.post(_delete_url(expense_id))

    assert response.status_code == 302
    assert response.location == LOGIN_URL


def test_post_delete_expense_unauthenticated_does_not_delete_row(client):
    user_id = _login_demo(client)
    expense_id = _insert_expense(user_id)
    original_row = _get_expense_row(expense_id)
    client.get("/logout")

    client.post(_delete_url(expense_id))

    _assert_row_unchanged(expense_id, original_row)


# --------------------------------------------------------------------- #
# POST /expenses/<id>/delete — happy path                               #
# --------------------------------------------------------------------- #

def test_post_delete_expense_own_expense_redirects_to_profile(client):
    user_id = _login_demo(client)
    expense_id = _insert_expense(user_id)

    response = client.post(_delete_url(expense_id))

    assert response.status_code == 302
    assert response.location == PROFILE_URL


def test_post_delete_expense_own_expense_removes_row_from_db(client):
    user_id = _login_demo(client)
    expense_id = _insert_expense(user_id, amount=77.0, category="Health", description="Pharmacy")

    client.post(_delete_url(expense_id))

    assert _get_expense_row(expense_id) is None, "Expense row must no longer exist after deletion"


def test_post_delete_expense_does_not_rerender_a_template(client):
    """On success the spec requires a redirect — no template is rendered."""
    user_id = _login_demo(client)
    expense_id = _insert_expense(user_id)

    response = client.post(_delete_url(expense_id))

    assert response.status_code != 200


def test_post_delete_expense_only_removes_target_row_not_other_expenses(client):
    user_id = _login_demo(client)
    expense_a = _insert_expense(user_id, amount=10.0, category="Food", date="2026-01-01", description="A")
    expense_b = _insert_expense(user_id, amount=20.0, category="Bills", date="2026-01-02", description="B")

    client.post(_delete_url(expense_a))

    assert _get_expense_row(expense_a) is None, "Deleted expense must be gone"
    row_b = _get_expense_row(expense_b)
    assert row_b is not None, "Deleting expense A must not affect expense B"
    assert row_b["amount"] == 20.0
    assert row_b["category"] == "Bills"
    assert row_b["date"] == "2026-01-02"
    assert row_b["description"] == "B"


def test_post_delete_expense_only_deletes_for_session_user_not_other_users(client):
    other_user_id = _register_and_login(client, email="other-isolation-delete@example.com")
    other_expense_id = _insert_expense(other_user_id, amount=5.0, category="Other")
    other_original_row = _get_expense_row(other_expense_id)
    client.get("/logout")

    demo_user_id = _login_demo(client)
    demo_expense_id = _insert_expense(demo_user_id, amount=15.0, category="Food")

    response = client.post(_delete_url(demo_expense_id))

    assert response.status_code == 302
    assert _get_expense_row(demo_expense_id) is None, "The demo user's own expense should have been deleted"
    _assert_row_unchanged(other_expense_id, other_original_row)


def test_post_delete_expense_removes_from_profile_transaction_list(client):
    user_id = _login_demo(client)
    expense_id = _insert_expense(user_id, amount=88.0, category="Shopping", date="2026-02-02")

    client.post(_delete_url(expense_id))
    response = client.get(PROFILE_URL)
    body = response.get_data(as_text=True)

    assert response.status_code == 200
    assert _delete_url(expense_id) not in body, (
        "The deleted expense's delete-form action must no longer appear in the transaction list"
    )


# --------------------------------------------------------------------- #
# POST /expenses/<id>/delete — ownership / 404                          #
# --------------------------------------------------------------------- #

def test_post_delete_expense_other_users_expense_returns_404(client):
    owner_id = _register_and_login(client, email="owner-delete@example.com")
    expense_id = _insert_expense(owner_id, amount=10.0, category="Food")
    original_row = _get_expense_row(expense_id)
    client.get("/logout")

    _register_and_login(client, email="intruder-delete@example.com")
    response = client.post(_delete_url(expense_id))

    assert response.status_code == 404


def test_post_delete_expense_other_users_expense_row_untouched(client):
    owner_id = _register_and_login(client, email="owner-delete2@example.com")
    expense_id = _insert_expense(owner_id, amount=10.0, category="Food")
    original_row = _get_expense_row(expense_id)
    client.get("/logout")

    _register_and_login(client, email="intruder-delete2@example.com")
    client.post(_delete_url(expense_id))

    _assert_row_unchanged(expense_id, original_row)


def test_post_delete_expense_nonexistent_id_returns_404(client):
    _login_demo(client)

    response = client.post(_delete_url(NONEXISTENT_EXPENSE_ID))

    assert response.status_code == 404


# --------------------------------------------------------------------- #
# GET /expenses/<id>/delete — method not allowed                        #
# --------------------------------------------------------------------- #

def test_get_delete_expense_authenticated_returns_405(client):
    user_id = _login_demo(client)
    expense_id = _insert_expense(user_id)

    response = client.get(_delete_url(expense_id))

    assert response.status_code == 405


def test_get_delete_expense_unauthenticated_returns_405(client):
    user_id = _login_demo(client)
    expense_id = _insert_expense(user_id)
    client.get("/logout")

    response = client.get(_delete_url(expense_id))

    assert response.status_code == 405, "GET must be rejected at the routing level regardless of auth state"


def test_get_delete_expense_does_not_delete_row(client):
    user_id = _login_demo(client)
    expense_id = _insert_expense(user_id)
    original_row = _get_expense_row(expense_id)

    client.get(_delete_url(expense_id))

    _assert_row_unchanged(expense_id, original_row)


# --------------------------------------------------------------------- #
# profile.html — Delete control presence (Templates / Definition of     #
# Done)                                                                  #
# --------------------------------------------------------------------- #

def test_profile_page_shows_delete_form_for_each_transaction(client):
    user_id = _login_demo(client)
    expense_id = _insert_expense(user_id, amount=33.0, category="Food", date="2026-02-02")

    response = client.get(PROFILE_URL)
    body = response.get_data(as_text=True)

    assert response.status_code == 200
    assert _delete_url(expense_id) in body, (
        "Expected the profile page's transaction table to contain a delete "
        "form whose action points to the expense's delete URL"
    )
    assert "POST" in body.upper(), "Expected the delete form to submit via POST"


def test_profile_page_shows_delete_button(client):
    user_id = _login_demo(client)
    expense_id = _insert_expense(user_id, amount=33.0, category="Food", date="2026-02-02")

    response = client.get(PROFILE_URL)
    body = response.get_data(as_text=True)

    assert "Delete" in body, "Expected a Delete button/label in the transaction row's Actions column"


def test_profile_page_shows_both_edit_and_delete_actions_per_row(client):
    user_id = _login_demo(client)
    expense_id = _insert_expense(user_id, amount=44.0, category="Bills", date="2026-03-03")

    response = client.get(PROFILE_URL)
    body = response.get_data(as_text=True)

    assert response.status_code == 200
    assert _edit_url(expense_id) in body, "Expected an Edit action for the transaction row"
    assert _delete_url(expense_id) in body, "Expected a Delete action for the transaction row"


def test_profile_page_delete_forms_do_not_leak_across_users(client):
    other_user_id = _register_and_login(client, email="other-profile-delete@example.com")
    other_expense_id = _insert_expense(other_user_id, amount=9.0, category="Other")
    client.get("/logout")

    demo_user_id = _login_demo(client)
    demo_expense_id = _insert_expense(demo_user_id, amount=19.0, category="Food")

    response = client.get(PROFILE_URL)
    body = response.get_data(as_text=True)

    assert _delete_url(demo_expense_id) in body, "Expected the demo user's own expense to have a delete form"
    assert _delete_url(other_expense_id) not in body, (
        "Another user's expense must not appear (or expose a delete form) on this user's profile page"
    )
