# Spec: Registration

## Overview
This feature implements account creation for Spendly. The `/register` route currently only
renders a static form (`register.html`); this step wires that form up to a real `POST /register`
handler that validates input, prevents duplicate emails, hashes the password with `werkzeug`,
and inserts a new row into the `users` table created in Step 1. On success, user is shown a success message and then redirected to login page. Registration is the entry point into the app for every new user, and every later feature (login, profile, expenses) depends on accounts existing in the database.

## Depends on
- Step 1 — Database setup (`users` table, `get_db()`, `init_db()`) — complete.

Does **not** depend on Step 3 (login/logout), so this step does not create a session or log
the user in. On success, redirect to `GET /login` with a flash-style message so the user signs
in with their new credentials.

## Routes
- `GET /register` — render the registration form — public (already implemented, unchanged)
- `POST /register` — validate input, create the user, redirect to `/login` on success or
  re-render the form with an error on failure — public

## Database changes
No schema changes — the `users` table already has every column this feature needs.

New functions required in `database/db.py` (query logic must not live in `app.py`):
- `get_user_by_email(email)` — returns a row or `None`, used for the duplicate-email check
- `create_user(name, email, password_hash)` — inserts a new user, returns the new `user_id`

## Templates
- **Create:** none
- **Modify:** `templates/register.html`
  - Change the form's `action="/register"` to `action="{{ url_for('register') }}"` (currently
    hardcoded, violates the no-hardcoded-URLs rule)
  - Keep using the existing `{% if error %}` block to surface validation/duplicate-email errors
  - Repopulate `name`/`email` field values on redisplay after a failed submission so the user
    doesn't have to retype them

## Files to change
- `app.py` — add `POST` handling to the existing `register()` view
- `database/db.py` — add `get_user_by_email()` and `create_user()`
- `templates/register.html` — fix hardcoded form action, repopulate fields on error

## Files to create
None.

## New dependencies
No new dependencies.

## Rules for implementation
- No SQLAlchemy or ORMs
- Parameterised queries only
- Passwords hashed with werkzeug (`generate_password_hash`, never store plaintext)
- Use CSS variables — never hardcode hex values (no new CSS should be needed; reuse `.auth-*`
  classes already in `static/css/style.css`)
- All templates extend `base.html`
- Validate on the server even though the form has `required`/`type=email` attributes client-side
- Treat a duplicate email as a validation error (re-render the form with a message), not a 500
- Never put DB logic inline in `app.py` — all queries go through `database/db.py`

## Definition of done
- [ ] Submitting the form with valid name/email/password creates a row in `users` with a hashed
      (not plaintext) password
- [ ] Submitting with an email that already exists re-renders `register.html` with an error and
      does not create a duplicate row
- [ ] Submitting with a missing field re-renders the form with an error instead of crashing
- [ ] On success, the browser is redirected to `GET /login`
- [ ] The form's POST action uses `url_for('register')`, not a hardcoded string
- [ ] `python app.py` starts on port 5001 with no errors
- [ ] `pytest` passes for any new registration tests
