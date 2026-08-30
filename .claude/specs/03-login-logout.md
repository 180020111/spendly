# Spec: Login and Logout

## Overview
This feature implements session-based authentication for Spendly. The `/login` route currently
only renders a static form (`login.html`); this step wires that form up to a real `POST /login`
handler that verifies the submitted email/password against the `users` table (created in Step 1,
populated via Step 2 registration), and starts a logged-in session on success. It also implements
the `GET /logout` stub, which ends that session. Login/logout is the gate between the public
marketing pages and every account-scoped feature that follows (profile, expenses), so this step
also updates the shared navbar in `base.html` to reflect signed-in state.

## Depends on
- Step 1 — Database setup (`users` table, `get_db()`, `init_db()`) — complete.
- Step 2 — Registration (`get_user_by_email()`, accounts exist to log into) — complete.

## Routes
- `GET /login` — render the login form — public (already implemented, unchanged)
- `POST /login` — verify credentials, start session on success, redirect to `/` (landing) — public
- `GET /logout` — clear the session, redirect to `/login` — logged-in

## Database changes
No schema changes and no new functions in `database/db.py` — `get_user_by_email(email)` from
Step 2 is sufficient to fetch the row needed for password verification.

## Templates
- **Create:** none
- **Modify:**
  - `templates/login.html` — repopulate the `email` field value on redisplay after a failed
    login attempt (mirrors the pattern already used in `register.html`)
  - `templates/base.html` — nav links become conditional on session state: show "Sign in" /
    "Get started" when logged out (current behavior, unchanged), show a "Log out" link
    (`url_for('logout')`) when `session.get('user_id')` is set

## Files to change
- `app.py`:
  - Set `app.secret_key` (required for Flask sessions) — read from `SECRET_KEY` env var with a
    hardcoded fallback for local dev
  - Add `POST` handling to the existing `login()` view: fetch user via `get_user_by_email()`,
    verify password with `check_password_hash`, set `session["user_id"]` on success, redirect to
    `/` (landing); on failure re-render `login.html` with an error and the submitted email
  - Implement `logout()`: `session.clear()`, redirect to `/login`
- `templates/login.html` — repopulate email field on error
- `templates/base.html` — conditional nav links based on session

## Files to create
None.

## New dependencies
No new dependencies. Uses `werkzeug.security.check_password_hash` (already installed) and
Flask's built-in `session`.

## Rules for implementation
- No SQLAlchemy or ORMs
- Parameterised queries only
- Passwords hashed with werkzeug (verify with `check_password_hash`; never compare plaintext)
- Use CSS variables — never hardcode hex values (no new CSS should be needed; reuse existing
  `.auth-*` and `.nav-links` classes)
- All templates extend `base.html`
- Never put DB logic inline in `app.py` — all queries go through `database/db.py`
- Treat a missing user or wrong password identically ("Invalid email or password") — don't leak
  which one was wrong
- Do not implement `/profile` — it stays a stub for Step 4; it is out of scope for this step

## Definition of done
- [ ] Submitting `/login` with the seeded demo account (`demo@spendly.com` / `demo123`) redirects
      to `/` (landing)
- [ ] Submitting `/login` with a wrong password re-renders `login.html` with an error, email
      field prefilled, and does not start a session
- [ ] Submitting `/login` with an email that doesn't exist shows the same generic error as a
      wrong password
- [ ] Visiting `/logout` while logged in clears the session and redirects to `/login`
- [ ] After logging in, the navbar shows a "Log out" link instead of "Sign in" / "Get started"
- [ ] After logging out, the navbar reverts to showing "Sign in" / "Get started"
- [ ] `python app.py` starts on port 5001 with no errors
- [ ] `pytest` passes for any new login/logout tests
