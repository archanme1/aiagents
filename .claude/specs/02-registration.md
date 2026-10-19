# Spec: Registration

## Overview
Turn the static `/register` page into a working sign-up flow. A visitor submits their name, email and password; the server validates the input, hashes the password with werkzeug, stores a new row in `users`, and redirects to the login page. This is the first authentication step on the Spendly roadmap: login, logout and the profile page all need real user accounts to exist. Registration does not log the user in — sessions arrive with the login step.

## Depends on
- Database setup (`.claude/specs/01-database-setup.md`): `users` table, `get_db()` and `init_db()` must exist (they do).

## Routes
- `GET /register` — render the registration form — public (already exists)
- `POST /register` — validate the form, create the user, redirect to `/login` on success; re-render the form with an error message on failure — public

## Database changes
No database changes. The existing `users` table (`id`, `name`, `email UNIQUE NOT NULL`, `password_hash`, `created_at`) is sufficient. Duplicate emails are rejected by the `UNIQUE` constraint on `email`.

A new helper is added to `database/db.py` (no schema change):
- `create_user(name, email, password)` — hashes the password with `generate_password_hash`, inserts the row with a parameterised query, returns the new user id, and raises `sqlite3.IntegrityError` on a duplicate email.
- `get_user_by_email(email)` — returns the matching `sqlite3.Row` or `None`.

## Templates
- **Create:** none
- **Modify:**
  - `templates/register.html` — change `action="/register"` to `action="{{ url_for('register') }}"`; re-populate `name` and `email` inputs after a failed submit; keep the existing `{% if error %}` block. Never re-populate the password.
  - `templates/login.html` — optionally show a success flash/message after registration (only if the template already supports it; otherwise leave unchanged).

## Files to change
- `app.py` — make `register` accept `GET` and `POST`; add form handling that calls the db helpers
- `database/db.py` — add `create_user()` and `get_user_by_email()`
- `templates/register.html` — see above
- `static/css/style.css` — only if the existing `.auth-error` / form styles need a small addition

## Files to create
- `tests/test_registration.py` — pytest coverage for the cases in the Definition of done

## New dependencies
No new dependencies. `werkzeug.security` and `pytest-flask` are already in `requirements.txt`.

## Rules for implementation
- No SQLAlchemy or ORMs
- Parameterised queries only — never f-strings in SQL
- Passwords hashed with werkzeug (`generate_password_hash`); never store or log plaintext
- Use CSS variables — never hardcode hex values
- All templates extend `base.html`
- DB logic lives in `database/db.py`, not in the route function
- Use `url_for()` for every internal link and redirect
- Route function: read form, validate, call db helper, redirect or re-render — nothing more
- Use `abort()` for HTTP errors, not bare strings
- Validation (server-side, in this order):
  1. `name`, `email`, `password` are present after `.strip()` (password is not stripped)
  2. `email` contains `@` and a `.` after it
  3. `password` is at least 8 characters
  4. Email is stored lowercased; duplicate check is case-insensitive
- Do not implement `/login`, `/logout` or `/profile` behaviour in this step

## Definition of done
- [ ] `GET /register` renders the form with name, email and password fields
- [ ] Submitting valid details creates a row in `users` with a hashed `password_hash` (not the plaintext) and redirects to `/login`
- [ ] Submitting an email that already exists (any letter case) re-renders the form with an error and does not create a second row
- [ ] Submitting with any empty field re-renders the form with an error
- [ ] Submitting a password shorter than 8 characters re-renders the form with an error
- [ ] Submitting a malformed email re-renders the form with an error
- [ ] After a failed submit the name and email fields keep their values; the password field is empty
- [ ] The form action uses `url_for('register')`, not a hardcoded URL
- [ ] `pytest tests/test_registration.py` passes
- [ ] The app starts on port 5001 without errors
