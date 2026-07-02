from __future__ import annotations

from datetime import date
from typing import Any

from ..database import db, init_db, now_iso
from ..utils.money import to_whole_number


def add_expense(payload: dict[str, Any]) -> dict[str, Any]:
    init_db()
    expense_date = payload.get("expense_date") or date.today().isoformat()
    category = (payload.get("category") or "General").strip()
    if not category:
        raise ValueError("Expense category is required.")
    description = (payload.get("description") or "").strip()
    amount = to_whole_number(payload.get("amount"), 0)
    if amount < 0:
        raise ValueError("Expense amount cannot be negative.")
    payment_method = (payload.get("payment_method") or "Cash").strip()
    notes = (payload.get("notes") or "").strip()
    now = now_iso()
    with db() as conn:
        cur = conn.execute(
            """
            INSERT INTO expenses(expense_date, category, description, amount, payment_method, notes, created_at, updated_at)
            VALUES(?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (expense_date, category, description, amount, payment_method, notes, now, now),
        )
        expense_id = int(cur.lastrowid)
        return conn.execute("SELECT * FROM expenses WHERE id = ?", (expense_id,)).fetchone()


def list_expenses(search: str = "", start_date: str = "", end_date: str = "", limit: int = 200) -> list[dict[str, Any]]:
    init_db()
    params: list[Any] = []
    where = ["1=1"]
    if search:
        q = f"%{search}%"
        where.append("(category LIKE ? OR description LIKE ? OR notes LIKE ?)")
        params.extend([q, q, q])
    if start_date:
        where.append("expense_date >= ?")
        params.append(start_date)
    if end_date:
        where.append("expense_date <= ?")
        params.append(end_date)
    params.append(max(int(limit or 200), 1))
    with db() as conn:
        return conn.execute(
            f"SELECT * FROM expenses WHERE {' AND '.join(where)} ORDER BY expense_date DESC, id DESC LIMIT ?",
            params,
        ).fetchall()


def delete_expense(expense_id: int) -> None:
    init_db()
    with db() as conn:
        conn.execute("DELETE FROM expenses WHERE id = ?", (expense_id,))
