from datetime import date, timedelta

import pytest

from expense_store import ExpenseStore


@pytest.fixture
def store(tmp_path):
    return ExpenseStore(tmp_path / "test.db")


def test_add_and_list(store):
    store.add(150, "Food", "lunch", "2026-09-01")
    store.add(60, "travel", "auto", "2026-09-02")
    rows = store.list("2026-09")
    assert len(rows) == 2
    assert rows[0]["category"] == "travel"  # newest first


def test_add_defaults_to_today(store):
    result = store.add(100, "food")
    assert result["spent_on"] == date.today().isoformat()


@pytest.mark.parametrize("amount", [0, -50, 2_000_000])
def test_rejects_bad_amount(store, amount):
    with pytest.raises(ValueError):
        store.add(amount, "food")


def test_rejects_bad_date(store):
    with pytest.raises(ValueError, match="YYYY-MM-DD"):
        store.add(100, "food", spent_on="2026-13-45")


def test_rejects_future_date(store):
    tomorrow = (date.today() + timedelta(days=1)).isoformat()
    with pytest.raises(ValueError, match="future"):
        store.add(100, "food", spent_on=tomorrow)


def test_rejects_unknown_category(store):
    with pytest.raises(ValueError, match="Unknown category"):
        store.add(100, "gadgets")


def test_totals(store):
    store.add(100, "food", spent_on="2026-09-01")
    store.add(50.5, "food", spent_on="2026-09-03")
    store.add(200, "books", spent_on="2026-09-04")
    store.add(999, "food", spent_on="2026-08-30")  # different month
    totals = store.totals("2026-09")
    assert totals["by_category"] == {"books": 200, "food": 150.5}
    assert totals["grand_total"] == 350.5


def test_delete(store):
    expense = store.add(100, "food")
    assert store.delete(expense["id"]) is True
    assert store.delete(expense["id"]) is False
    assert store.list() == []


def test_budget_warning(store):
    store.set_budget("food", 1000)
    assert "warning" not in store.add(500, "food")
    assert "80%" in store.add(300, "food")["warning"]
    assert "Over budget" in store.add(300, "food")["warning"]


def test_sql_injection_is_harmless(store):
    store.add(100, "food", note="'); DROP TABLE expenses; --")
    assert len(store.list()) == 1


def test_month_without_leading_zero(store):
    store.add(100, "food", spent_on="2026-09-01")
    assert len(store.list("2026-9")) == 1
    with pytest.raises(ValueError, match="YYYY-MM"):
        store.list("Sept 2026")
