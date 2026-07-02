from __future__ import annotations

from typing import Any

from ..database import db, init_db, now_iso, normalize_phone_value


def normalize_phone(phone: str | None) -> str:
    return normalize_phone_value(phone)


def is_valid_phone(phone: str) -> bool:
    digits = normalize_phone(phone)
    return len(digits) >= 7


def upsert_customer(payload: dict[str, Any]) -> int | None:
    name = (payload.get("name") or payload.get("customer_name") or "").strip()
    if not name:
        raise ValueError("Customer name is required.")
    phone = normalize_phone(payload.get("phone") or payload.get("customer_phone"))
    if not phone:
        raise ValueError("Customer phone number is required.")
    if not is_valid_phone(phone):
        raise ValueError("Please enter a valid customer phone number.")
    email = (payload.get("email") or payload.get("customer_email") or "").strip()
    address = (payload.get("address") or payload.get("customer_address") or "").strip()
    notes = (payload.get("notes") or "").strip()
    now = now_iso()
    init_db()
    with db() as conn:
        existing = None
        # Only merge customers when a normalized phone number is present.
        # Name-only merging can incorrectly combine different customers with common names.
        if phone:
            existing = conn.execute("SELECT id FROM customers WHERE phone = ?", (phone,)).fetchone()
        if existing:
            customer_id = int(existing["id"])
            conn.execute(
                """
                UPDATE customers
                SET name = ?, phone = ?, email = ?, address = ?, notes = COALESCE(NULLIF(?, ''), notes), updated_at = ?
                WHERE id = ?
                """,
                (name, phone, email, address, notes, now, customer_id),
            )
            return customer_id
        cur = conn.execute(
            """
            INSERT INTO customers(name, phone, email, address, notes, created_at, updated_at)
            VALUES(?, ?, ?, ?, ?, ?, ?)
            """,
            (name, phone, email, address, notes, now, now),
        )
        return int(cur.lastrowid)


def list_customers(search: str = "", limit: int = 200) -> list[dict[str, Any]]:
    init_db()
    raw = (search or '').strip()
    q = f"%{raw}%"
    normalized = normalize_phone(raw)
    q_phone = f"%{normalized}%" if normalized else q
    with db() as conn:
        rows = conn.execute(
            """
            SELECT c.*,
                   COUNT(i.id) AS invoice_count,
                   COALESCE(SUM(i.total), 0) AS lifetime_value,
                   MAX(i.invoice_date) AS last_invoice_date
            FROM customers c
            LEFT JOIN invoices i ON i.customer_id = c.id
            WHERE (? = '%%' OR c.name LIKE ? OR c.phone LIKE ? OR c.email LIKE ?)
            GROUP BY c.id
            ORDER BY c.updated_at DESC, c.id DESC
            LIMIT ?
            """,
            (q, q, q_phone, q, max(int(limit or 200), 1)),
        ).fetchall()
    return rows


def get_customer(customer_id: int) -> dict[str, Any] | None:
    init_db()
    with db() as conn:
        return conn.execute("SELECT * FROM customers WHERE id = ?", (customer_id,)).fetchone()


def delete_customer(customer_id: int) -> None:
    init_db()
    with db() as conn:
        conn.execute("DELETE FROM customers WHERE id = ?", (customer_id,))
