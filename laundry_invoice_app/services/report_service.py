from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from ..database import db, init_db


def _first_day_month(d: date) -> str:
    return d.replace(day=1).isoformat()


def get_dashboard() -> dict[str, Any]:
    init_db()
    today = date.today().isoformat()
    month_start = _first_day_month(date.today())
    with db() as conn:
        today_sales = conn.execute("SELECT COALESCE(SUM(total), 0) AS v, COUNT(*) AS c FROM invoices WHERE invoice_date = ?", (today,)).fetchone()
        month_sales = conn.execute("SELECT COALESCE(SUM(total), 0) AS v, COUNT(*) AS c FROM invoices WHERE invoice_date >= ?", (month_start,)).fetchone()
        month_expenses = conn.execute("SELECT COALESCE(SUM(amount), 0) AS v, COUNT(*) AS c FROM expenses WHERE expense_date >= ?", (month_start,)).fetchone()
        outstanding = conn.execute("SELECT COALESCE(SUM(balance), 0) AS v, COUNT(*) AS c FROM invoices WHERE balance > 0").fetchone()
        recent = conn.execute("SELECT * FROM invoices ORDER BY invoice_date DESC, id DESC LIMIT 8").fetchall()
        top_customers = conn.execute(
            """
            SELECT customer_name, customer_phone, COUNT(*) AS invoice_count, COALESCE(SUM(total), 0) AS total_spent
            FROM invoices
            GROUP BY customer_name, customer_phone
            ORDER BY total_spent DESC
            LIMIT 6
            """
        ).fetchall()
        daily_sales = conn.execute(
            """
            SELECT invoice_date AS label, COALESCE(SUM(total), 0) AS sales, COUNT(*) AS invoice_count
            FROM invoices
            WHERE invoice_date >= ?
            GROUP BY invoice_date
            ORDER BY invoice_date ASC
            """,
            ((date.today() - timedelta(days=29)).isoformat(),),
        ).fetchall()
        monthly_profit = float(month_sales["v"] or 0) - float(month_expenses["v"] or 0)
    return {
        "today_sales": today_sales,
        "month_sales": month_sales,
        "month_expenses": month_expenses,
        "monthly_profit": monthly_profit,
        "outstanding": outstanding,
        "recent_invoices": recent,
        "top_customers": top_customers,
        "daily_sales": daily_sales,
    }


def get_monthly_report(year: int | None = None) -> list[dict[str, Any]]:
    init_db()
    sales_where = ""
    expense_where = ""
    params: list[Any] = []
    if year:
        sales_where = "WHERE substr(invoice_date, 1, 4) = ?"
        expense_where = "WHERE substr(expense_date, 1, 4) = ?"
        params = [str(year), str(year)]

    query = f"""
        WITH sales AS (
            SELECT substr(invoice_date, 1, 7) AS month, COALESCE(SUM(total), 0) AS sales, COUNT(*) AS invoices
            FROM invoices {sales_where}
            GROUP BY substr(invoice_date, 1, 7)
        ), expense_totals AS (
            SELECT substr(expense_date, 1, 7) AS month, COALESCE(SUM(amount), 0) AS expenses, COUNT(*) AS expense_count
            FROM expenses {expense_where}
            GROUP BY substr(expense_date, 1, 7)
        )
        SELECT COALESCE(s.month, e.month) AS month,
               COALESCE(s.sales, 0) AS sales,
               COALESCE(s.invoices, 0) AS invoices,
               COALESCE(e.expenses, 0) AS expenses,
               COALESCE(e.expense_count, 0) AS expense_count,
               COALESCE(s.sales, 0) - COALESCE(e.expenses, 0) AS profit
        FROM sales s
        LEFT JOIN expense_totals e ON e.month = s.month
        UNION
        SELECT COALESCE(s.month, e.month) AS month,
               COALESCE(s.sales, 0) AS sales,
               COALESCE(s.invoices, 0) AS invoices,
               COALESCE(e.expenses, 0) AS expenses,
               COALESCE(e.expense_count, 0) AS expense_count,
               COALESCE(s.sales, 0) - COALESCE(e.expenses, 0) AS profit
        FROM expense_totals e
        LEFT JOIN sales s ON s.month = e.month
        ORDER BY month DESC
    """
    with db() as conn:
        return conn.execute(query, params).fetchall()
