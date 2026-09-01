import database.db as db
import database.queries as queries


def test_get_recent_transactions_seed_user_returns_all_ordered_newest_first(app):
    user = db.get_user_by_email("demo@spendly.com")
    txns = queries.get_recent_transactions(user["id"])
    assert len(txns) == 8
    dates = [t["date"] for t in txns]
    assert dates == sorted(dates, reverse=True)
    for t in txns:
        assert set(t.keys()) == {"id", "date", "description", "category", "amount"}


def test_get_recent_transactions_respects_limit(app):
    user = db.get_user_by_email("demo@spendly.com")
    assert len(queries.get_recent_transactions(user["id"], limit=3)) == 3


def test_get_recent_transactions_no_expenses_returns_empty_list(app):
    new_id = db.create_user("New User", "new@example.com", "hash")
    assert queries.get_recent_transactions(new_id) == []
