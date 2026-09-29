"""SQLite storage and validation for expenses.

Kept separate from server.py so the logic can be tested without MCP.
"""
import sqlite3
from datetime import date, datetime
from pathlib import Path

CATEGORIES = {"food", "travel", "books", "rent", "shopping", "bills", "health", "entertainment", "other"}


def _check_date(value: str) -> str:
    if not value:
        return date.today().isoformat()
    try:
        parsed = datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        raise ValueError(f"Invalid date '{value}'. Use YYYY-MM-DD, e.g. 2026-09-29.")
    if parsed > date.today():
        raise ValueError("Date cannot be in the future.")
    return parsed.isoformat()


def _check_month(value: str) -> str:
    if not value:
        return ""
    try:
        parsed = datetime.strptime(value.strip(), "%Y-%m")
    except ValueError:
        raise ValueError(f"Invalid month '{value}'. Use YYYY-MM, e.g. 2026-09.")
    return parsed.strftime("%Y-%m")  # "2026-9" -> "2026-09" so the LIKE filter matches


def _check_category(value: str) -> str:
    cat = value.lower().strip()
    if cat not in CATEGORIES:
        raise ValueError(f"Unknown category '{value}'. Choose one of: {', '.join(sorted(CATEGORIES))}.")
    return cat


class ExpenseStore:
    def __init__(self, db_path: Path):
        self.db_path = db_path
        with self._connect() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS expenses (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    amount REAL NOT NULL CHECK (amount > 0),
                    category TEXT NOT NULL,
                    note TEXT DEFAULT '',
                    spent_on TEXT NOT NULL
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS budgets (
                    category TEXT PRIMARY KEY,
                    monthly_limit REAL NOT NULL CHECK (monthly_limit > 0)
                )
            """)

    def _connect(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def add(self, amount: float, category: str, note: str = "", spent_on: str = "") -> dict:
        if amount <= 0:
            raise ValueError("Amount must be greater than 0.")
        if amount > 1_000_000:
            raise ValueError("Amount looks too large. Check the value.")
        category = _check_category(category)
        spent_on = _check_date(spent_on)

        with self._connect() as conn:
            cur = conn.execute(
                "INSERT INTO expenses (amount, category, note, spent_on) VALUES (?, ?, ?, ?)",
                (round(amount, 2), category, note.strip(), spent_on),
            )
            expense_id = cur.lastrowid

        result = {"id": expense_id, "amount": round(amount, 2), "category": category, "spent_on": spent_on}
        warning = self._budget_warning(category, spent_on[:7])
        if warning:
            result["warning"] = warning
        return result

    def list(self, month: str = "", category: str = "") -> list[dict]:
        month = _check_month(month)
        query = "SELECT id, amount, category, note, spent_on FROM expenses WHERE spent_on LIKE ?"
        params = [f"{month}%"]
        if category:
            query += " AND category = ?"
            params.append(_check_category(category))
        query += " ORDER BY spent_on DESC, id DESC"
        with self._connect() as conn:
            return [dict(r) for r in conn.execute(query, params)]

    def totals(self, month: str = "") -> dict:
        month = _check_month(month)
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT category, SUM(amount) AS total FROM expenses WHERE spent_on LIKE ? "
                "GROUP BY category ORDER BY total DESC",
                (f"{month}%",),
            ).fetchall()
        by_category = {r["category"]: round(r["total"], 2) for r in rows}
        return {"month": month or "all", "by_category": by_category, "grand_total": round(sum(by_category.values()), 2)}

    def delete(self, expense_id: int) -> bool:
        with self._connect() as conn:
            cur = conn.execute("DELETE FROM expenses WHERE id = ?", (expense_id,))
            return cur.rowcount > 0

    def set_budget(self, category: str, monthly_limit: float) -> dict:
        if monthly_limit <= 0:
            raise ValueError("Budget must be greater than 0.")
        category = _check_category(category)
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO budgets (category, monthly_limit) VALUES (?, ?) "
                "ON CONFLICT(category) DO UPDATE SET monthly_limit = excluded.monthly_limit",
                (category, round(monthly_limit, 2)),
            )
        return {"category": category, "monthly_limit": round(monthly_limit, 2)}

    def _budget_warning(self, category: str, month: str) -> str | None:
        with self._connect() as conn:
            budget = conn.execute("SELECT monthly_limit FROM budgets WHERE category = ?", (category,)).fetchone()
            if not budget:
                return None
            spent = conn.execute(
                "SELECT COALESCE(SUM(amount), 0) FROM expenses WHERE category = ? AND spent_on LIKE ?",
                (category, f"{month}%"),
            ).fetchone()[0]
        limit = budget["monthly_limit"]
        if spent > limit:
            return f"Over budget for {category} in {month}: spent {spent:.2f} of {limit:.2f}."
        if spent >= 0.8 * limit:
            return f"Used {spent / limit:.0%} of the {category} budget for {month}."
        return None
