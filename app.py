import os
from datetime import date, datetime

from flask import Flask, render_template, request, redirect, url_for, session, abort
from werkzeug.security import generate_password_hash, check_password_hash

from database.db import get_db, init_db, seed_db, get_user_by_email, create_user, CATEGORIES
from database.queries import (
    get_user_by_id,
    get_summary_stats,
    get_recent_transactions,
    get_category_breakdown,
    insert_expense,
    get_expense_by_id,
    update_expense,
    delete_expense as delete_expense_row,
)

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret-key-change-in-production")

with app.app_context():
    init_db()
    seed_db()


def _compute_initials(name):
    parts = [p for p in name.strip().split() if p]
    if not parts:
        return ""
    if len(parts) == 1:
        return parts[0][0].upper()
    return (parts[0][0] + parts[1][0]).upper()


def _parse_date(value):
    """Parse a YYYY-MM-DD string into a date, or None if missing/invalid."""
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        return None


def _first_of_month_n_back(today, n):
    """The first day of the month that is n calendar months before today's month."""
    total_months = today.year * 12 + (today.month - 1) - n
    year, month = divmod(total_months, 12)
    return date(year, month + 1, 1)


def _preset_ranges():
    """Quick-select date ranges for the profile filter bar, as ISO strings."""
    today = date.today()
    iso = lambda d: d.strftime("%Y-%m-%d")
    return {
        "this_month": (iso(_first_of_month_n_back(today, 0)), iso(today)),
        "last_3_months": (iso(_first_of_month_n_back(today, 2)), iso(today)),
        "last_6_months": (iso(_first_of_month_n_back(today, 5)), iso(today)),
    }


# ------------------------------------------------------------------ #
# Routes                                                              #
# ------------------------------------------------------------------ #

@app.route("/")
def landing():
    return render_template("landing.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    if session.get("user_id"):
        return redirect(url_for("profile"))

    if request.method == "GET":
        return render_template("register.html")

    name = request.form.get("name", "").strip()
    email = request.form.get("email", "").strip()
    password = request.form.get("password", "")
    confirm_password = request.form.get("confirm_password", "")

    if not name or not email or not password or not confirm_password:
        return render_template(
            "register.html", error="All fields are required.", name=name, email=email
        )

    if password != confirm_password:
        return render_template(
            "register.html", error="Passwords do not match.", name=name, email=email
        )

    if get_user_by_email(email) is not None:
        return render_template(
            "register.html",
            error="An account with that email already exists.",
            name=name,
            email=email,
        )

    password_hash = generate_password_hash(password)
    create_user(name, email, password_hash)
    return redirect(url_for("login", registered=1))


@app.route("/login", methods=["GET", "POST"])
def login():
    if session.get("user_id"):
        return redirect(url_for("profile"))

    if request.method == "GET":
        registered = request.args.get("registered")
        success = "Account created successfully. Please sign in." if registered else None
        return render_template("login.html", success=success)

    email = request.form.get("email", "").strip()
    password = request.form.get("password", "")

    user = get_user_by_email(email)
    if user is not None and check_password_hash(user["password_hash"], password):
        session.clear()
        session["user_id"] = user["id"]
        return redirect(url_for("profile"))

    return render_template(
        "login.html", error="Invalid email or password.", email=email
    )


@app.route("/terms")
def terms():
    return render_template("terms.html")


@app.route("/privacy")
def privacy():
    return render_template("privacy.html")


# ------------------------------------------------------------------ #
# Placeholder routes — students will implement these                  #
# ------------------------------------------------------------------ #

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/profile")
def profile():
    if not session.get("user_id"):
        return redirect(url_for("login"))

    user_id = session["user_id"]
    db_user = get_user_by_id(user_id)
    user = {
        "name": db_user["name"],
        "email": db_user["email"],
        "initials": _compute_initials(db_user["name"]),
        "member_since": db_user["member_since"],
    }

    parsed_from = _parse_date(request.args.get("date_from"))
    parsed_to = _parse_date(request.args.get("date_to"))

    error = None
    if parsed_from and parsed_to and parsed_from > parsed_to:
        error = "Start date must be before end date."
        parsed_from = parsed_to = None
    elif (parsed_from is None) != (parsed_to is None):
        # A one-sided range can't drive a BETWEEN filter — treat it as absent.
        parsed_from = parsed_to = None

    date_from = parsed_from.strftime("%Y-%m-%d") if parsed_from else None
    date_to = parsed_to.strftime("%Y-%m-%d") if parsed_to else None

    presets = _preset_ranges()
    if date_from and date_to:
        active_preset = next(
            (name for name, rng in presets.items() if rng == (date_from, date_to)),
            None,
        )
    else:
        active_preset = "all_time"

    # === SUBAGENT-STATS START ===
    stats = get_summary_stats(user_id, date_from=date_from, date_to=date_to)
    # === SUBAGENT-STATS END ===

    # === SUBAGENT-TRANSACTIONS START ===
    transactions = get_recent_transactions(user_id, date_from=date_from, date_to=date_to)
    # === SUBAGENT-TRANSACTIONS END ===

    # === SUBAGENT-CATEGORIES START ===
    raw_categories = get_category_breakdown(user_id, date_from=date_from, date_to=date_to)
    categories = [
        {"name": c["name"], "total": c["amount"], "percent": c["pct"]}
        for c in raw_categories
    ]
    # === SUBAGENT-CATEGORIES END ===

    return render_template(
        "profile.html",
        user=user,
        stats=stats,
        transactions=transactions,
        categories=categories,
        date_from=date_from,
        date_to=date_to,
        presets=presets,
        active_preset=active_preset,
        error=error,
    )


@app.route("/analytics")
def analytics():
    if not session.get("user_id"):
        return redirect(url_for("login"))

    return render_template("analytics.html")


@app.route("/expenses/add", methods=["GET", "POST"])
def add_expense():
    if not session.get("user_id"):
        return redirect(url_for("login"))

    if request.method == "GET":
        return render_template(
            "add_expense.html",
            categories=CATEGORIES,
            today=date.today().strftime("%Y-%m-%d"),
        )

    user_id = session["user_id"]
    amount_raw = request.form.get("amount", "").strip()
    category = request.form.get("category", "").strip()
    date_raw = request.form.get("date", "").strip()
    description = request.form.get("description", "").strip()

    error = None
    amount = None
    if not amount_raw:
        error = "Amount is required."
    else:
        try:
            amount = float(amount_raw)
            if amount <= 0:
                error = "Amount must be greater than 0."
        except ValueError:
            error = "Amount must be a valid number."

    if error is None and category not in CATEGORIES:
        error = "Please select a valid category."

    parsed_date = None
    if error is None:
        parsed_date = _parse_date(date_raw)
        if parsed_date is None:
            error = "Please enter a valid date."

    if error is not None:
        return render_template(
            "add_expense.html",
            categories=CATEGORIES,
            error=error,
            amount=amount_raw,
            category=category,
            date=date_raw,
            description=description,
        )

    insert_expense(user_id, amount, category, parsed_date.strftime("%Y-%m-%d"), description or None)
    return redirect(url_for("profile"))


@app.route("/expenses/<int:id>/edit", methods=["GET", "POST"])
def edit_expense(id):
    if not session.get("user_id"):
        return redirect(url_for("login"))

    user_id = session["user_id"]
    expense = get_expense_by_id(id, user_id)
    if expense is None:
        abort(404)

    if request.method == "GET":
        return render_template(
            "edit_expense.html",
            expense=expense,
            categories=CATEGORIES,
        )

    amount_raw = request.form.get("amount", "").strip()
    category = request.form.get("category", "").strip()
    date_raw = request.form.get("date", "").strip()
    description = request.form.get("description", "").strip()

    error = None
    amount = None
    if not amount_raw:
        error = "Amount is required."
    else:
        try:
            amount = float(amount_raw)
            if amount <= 0:
                error = "Amount must be greater than 0."
        except ValueError:
            error = "Amount must be a valid number."

    if error is None and category not in CATEGORIES:
        error = "Please select a valid category."

    parsed_date = None
    if error is None:
        parsed_date = _parse_date(date_raw)
        if parsed_date is None:
            error = "Please enter a valid date."

    if error is not None:
        return render_template(
            "edit_expense.html",
            categories=CATEGORIES,
            error=error,
            expense={
                "id": id,
                "amount": amount_raw,
                "category": category,
                "date": date_raw,
                "description": description,
            },
        )

    update_expense(id, user_id, amount, category, parsed_date.strftime("%Y-%m-%d"), description or None)
    return redirect(url_for("profile"))


@app.route("/expenses/<int:id>/delete", methods=["POST"])
def delete_expense(id):
    if not session.get("user_id"):
        return redirect(url_for("login"))

    rows_deleted = delete_expense_row(id, session["user_id"])
    if rows_deleted == 0:
        abort(404)

    return redirect(url_for("profile"))


if __name__ == "__main__":
    app.run(debug=True, port=5001)
