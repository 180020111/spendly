import database.db as db
import database.queries as queries


def test_get_category_breakdown_seed_user(app):
    user = db.get_user_by_email("demo@spendly.com")
    cats = queries.get_category_breakdown(user["id"])
    assert len(cats) == 7
    amounts = [c["amount"] for c in cats]
    assert amounts == sorted(amounts, reverse=True)
    assert sum(c["pct"] for c in cats) == 100
    assert all(isinstance(c["pct"], int) for c in cats)
    assert cats[0]["name"] == "Bills"


def test_get_category_breakdown_no_expenses(app):
    new_id = db.create_user("New User", "new@example.com", "hash")
    assert queries.get_category_breakdown(new_id) == []
