"""Pure query helpers for the profile page.

No Flask imports. Every function opens its own connection via get_db()
and closes it in a finally block before returning.
"""
from datetime import datetime

from database.db import get_db


def get_user_by_id(user_id):
    """Return {"name", "email", "member_since"} for user_id, or None if not found."""
    conn = get_db()
    try:
        row = conn.execute(
            "SELECT name, email, created_at FROM users WHERE id = ?", (user_id,)
        ).fetchone()
    finally:
        conn.close()
    if row is None:
        return None
    created_at = datetime.strptime(row["created_at"], "%Y-%m-%d %H:%M:%S")
    return {
        "name": row["name"],
        "email": row["email"],
        "member_since": created_at.strftime("%B %Y"),
    }


# --------------------------------------------------------------------- #
# STUB — Subagent B implements this. Do not touch any other function.   #
# --------------------------------------------------------------------- #
def get_summary_stats(user_id, date_from=None, date_to=None):
    """Return {"total_spent", "transaction_count", "top_category"} for user_id.
    No expenses -> {"total_spent": 0, "transaction_count": 0, "top_category": "—"}.
    When date_from and date_to are both given, results are scoped to that
    inclusive range.
    """
    conn = get_db()
    try:
        if date_from and date_to:
            totals = conn.execute(
                "SELECT COALESCE(SUM(amount), 0) AS total, COUNT(*) AS cnt "
                "FROM expenses WHERE user_id = ? AND date BETWEEN ? AND ?",
                (user_id, date_from, date_to),
            ).fetchone()
            top = conn.execute(
                "SELECT category, SUM(amount) AS cat_total FROM expenses "
                "WHERE user_id = ? AND date BETWEEN ? AND ? "
                "GROUP BY category ORDER BY cat_total DESC LIMIT 1",
                (user_id, date_from, date_to),
            ).fetchone()
        else:
            totals = conn.execute(
                "SELECT COALESCE(SUM(amount), 0) AS total, COUNT(*) AS cnt "
                "FROM expenses WHERE user_id = ?",
                (user_id,),
            ).fetchone()
            top = conn.execute(
                "SELECT category, SUM(amount) AS cat_total FROM expenses "
                "WHERE user_id = ? GROUP BY category ORDER BY cat_total DESC LIMIT 1",
                (user_id,),
            ).fetchone()
    finally:
        conn.close()

    return {
        "total_spent": totals["total"],
        "transaction_count": totals["cnt"],
        "top_category": top["category"] if top else "—",
    }


# --------------------------------------------------------------------- #
# STUB — Subagent A implements this. Do not touch any other function.   #
# --------------------------------------------------------------------- #
def get_recent_transactions(user_id, limit=10, date_from=None, date_to=None):
    """List of {"date","description","category","amount"}, newest-first, capped at limit.
    [] if no expenses. When date_from and date_to are both given, results are
    scoped to that inclusive range; the limit still applies.
    """
    conn = get_db()
    try:
        if date_from and date_to:
            rows = conn.execute(
                "SELECT date, description, category, amount FROM expenses "
                "WHERE user_id = ? AND date BETWEEN ? AND ? "
                "ORDER BY date DESC, id DESC LIMIT ?",
                (user_id, date_from, date_to, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT date, description, category, amount FROM expenses "
                "WHERE user_id = ? ORDER BY date DESC, id DESC LIMIT ?",
                (user_id, limit),
            ).fetchall()
    finally:
        conn.close()
    return [
        {"date": r["date"], "description": r["description"], "category": r["category"], "amount": r["amount"]}
        for r in rows
    ]


# --------------------------------------------------------------------- #
# STUB — Subagent C implements this. Do not touch any other function.   #
# --------------------------------------------------------------------- #
def get_category_breakdown(user_id, date_from=None, date_to=None):
    """List of {"name","amount","pct"} per category with >=1 expense, amount desc.
    pct values are ints summing to exactly 100 (rounding remainder goes to the
    largest category). [] if no expenses. When date_from and date_to are both
    given, results are scoped to that inclusive range.
    """
    conn = get_db()
    try:
        if date_from and date_to:
            rows = conn.execute(
                "SELECT category, SUM(amount) AS amount FROM expenses "
                "WHERE user_id = ? AND date BETWEEN ? AND ? "
                "GROUP BY category ORDER BY amount DESC",
                (user_id, date_from, date_to),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT category, SUM(amount) AS amount FROM expenses "
                "WHERE user_id = ? GROUP BY category ORDER BY amount DESC",
                (user_id,),
            ).fetchall()
    finally:
        conn.close()

    if not rows:
        return []

    total = sum(r["amount"] for r in rows)
    result = [
        {"name": r["category"], "amount": r["amount"], "pct": round(r["amount"] / total * 100)}
        for r in rows
    ]
    diff = 100 - sum(item["pct"] for item in result)
    result[0]["pct"] += diff  # largest category (first row, amount-desc) absorbs the rounding remainder
    return result
