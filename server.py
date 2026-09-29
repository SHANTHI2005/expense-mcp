"""Expense Tracker MCP server.

Run directly:      python server.py
Test in browser:   mcp dev server.py
"""
from pathlib import Path

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from expense_store import CATEGORIES, ExpenseStore

store = ExpenseStore(Path(__file__).parent / "expenses.db")
mcp = FastMCP("expense-tracker")

READ_ONLY = ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)
WRITE = ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=False)
DELETE = ToolAnnotations(readOnlyHint=False, destructiveHint=True, idempotentHint=True, openWorldHint=False)

CATEGORY_HELP = ", ".join(sorted(CATEGORIES))


@mcp.tool(
    annotations=WRITE,
    description=(
        f"Record an expense in rupees. category: one of {CATEGORY_HELP}. "
        "spent_on: date as YYYY-MM-DD, leave empty for today."
    ),
)
def add_expense(amount: float, category: str, note: str = "", spent_on: str = "") -> dict:
    return store.add(amount, category, note, spent_on)


@mcp.tool(annotations=READ_ONLY)
def list_expenses(month: str = "", category: str = "") -> list[dict]:
    """List expenses, newest first. month as YYYY-MM and category are optional filters."""
    return store.list(month, category)


@mcp.tool(annotations=READ_ONLY)
def total_by_category(month: str = "") -> dict:
    """Total spending per category plus grand total. month as YYYY-MM (optional)."""
    return store.totals(month)


@mcp.tool(annotations=DELETE)
def delete_expense(expense_id: int) -> str:
    """Delete one expense by its id. Use list_expenses first to find the id."""
    if store.delete(expense_id):
        return f"Deleted expense {expense_id}."
    return f"No expense with id {expense_id}."


@mcp.tool(annotations=WRITE)
def set_budget(category: str, monthly_limit: float) -> dict:
    """Set a monthly spending limit for a category. add_expense warns when spending reaches 80% of it."""
    return store.set_budget(category, monthly_limit)


if __name__ == "__main__":
    mcp.run()
