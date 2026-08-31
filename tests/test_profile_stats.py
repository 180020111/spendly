import database.db as db
import database.queries as queries


def test_get_summary_stats_seed_user(app):
    user = db.get_user_by_email("demo@spendly.com")
    stats = queries.get_summary_stats(user["id"])
    assert round(stats["total_spent"], 2) == 288.94
    assert stats["transaction_count"] == 8
    assert stats["top_category"] == "Bills"


def test_get_summary_stats_no_expenses(app):
    new_id = db.create_user("New User", "new@example.com", "hash")
    assert queries.get_summary_stats(new_id) == {
        "total_spent": 0, "transaction_count": 0, "top_category": "—",
    }
