from __future__ import annotations

from datetime import date
from pathlib import Path
import sqlite3
from typing import Any

from ..database import db, fetch_settings, init_db, now_iso
from ..logger import get_logger
from ..utils.files import open_file, print_file
from ..utils.money import to_money, to_whole_number
from ..utils.numbering import next_invoice_number
from .customer_service import is_valid_phone, normalize_phone, upsert_customer
from .pdf_service import build_invoice_pdf

logger = get_logger()


def _calculate_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    clean: list[dict[str, Any]] = []
    for item in items:
        description = (item.get("description") or "").strip()
        raw_quantity = to_whole_number(item.get("quantity"), 1)
        raw_unit_price = to_whole_number(item.get("unit_price"), 0)

        # Empty default rows are ignored, but entered rows must be valid.
        if not description and raw_unit_price <= 0:
            continue
        if raw_quantity < 1:
            raise ValueError("Quantity must be at least 1.")
        if raw_unit_price < 0:
            raise ValueError("Unit price cannot be negative.")

        quantity = raw_quantity
        unit_price = raw_unit_price
        line_total = to_whole_number(quantity * unit_price, 0)
        clean.append({
            "description": description or "Laundry Service",
            "quantity": quantity,
            "unit_price": unit_price,
            "line_total": line_total,
        })
    if not clean:
        raise ValueError("At least one invoice item is required.")
    return clean


def _calculate_totals(payload: dict[str, Any], items: list[dict[str, Any]], settings: dict[str, Any]) -> dict[str, Any]:
    subtotal = to_whole_number(sum(item["line_total"] for item in items), 0)
    discount = to_whole_number(payload.get("discount"), 0)
    if discount < 0:
        raise ValueError("Discount cannot be negative.")
    if discount > subtotal:
        raise ValueError("Discount cannot be greater than subtotal.")

    tax_rate = to_money(payload.get("tax_rate") if payload.get("tax_rate") not in [None, ""] else settings.get("tax_rate", 0))
    if tax_rate < 0:
        raise ValueError("Tax rate cannot be negative.")

    taxable = max(subtotal - discount, 0)
    # NovaBill is a whole-PKR billing app: tax and invoice totals are rounded
    # to full rupees so invoices cannot get stuck with 0.25/0.50 balances.
    tax_amount = max(to_whole_number(taxable * tax_rate / 100, 0), 0)
    total = to_whole_number(taxable + tax_amount, 0)
    paid_amount = to_whole_number(payload.get("paid_amount"), 0)
    if paid_amount < 0:
        raise ValueError("Paid amount cannot be negative.")
    if paid_amount > total:
        raise ValueError("Paid amount cannot be greater than invoice total.")

    balance = max(to_whole_number(total - paid_amount, 0), 0)
    if total > 0 and balance <= 0:
        payment_status = "Paid"
    elif paid_amount > 0:
        payment_status = "Partial"
    else:
        payment_status = payload.get("payment_status") or "Unpaid"
        if payment_status not in {"Unpaid", "Partial", "Paid"}:
            payment_status = "Unpaid"

    return {
        "subtotal": subtotal,
        "discount": discount,
        "tax_rate": tax_rate,
        "tax_amount": tax_amount,
        "total": total,
        "paid_amount": paid_amount,
        "balance": balance,
        "payment_status": payment_status,
    }


def _validate_customer(payload: dict[str, Any]) -> tuple[str, str]:
    customer_name = (payload.get("customer_name") or "").strip()
    if not customer_name:
        raise ValueError("Customer name is required.")
    customer_phone = normalize_phone(payload.get("customer_phone"))
    if not customer_phone:
        raise ValueError("Customer phone number is required.")
    if not is_valid_phone(customer_phone):
        raise ValueError("Please enter a valid customer phone number.")
    return customer_name, customer_phone


def _remove_old_pdf(path: str | None) -> None:
    if not path:
        return
    try:
        target = Path(path)
        if target.exists() and target.is_file():
            target.unlink()
    except OSError:
        logger.warning("Could not remove old PDF: %s", path, exc_info=True)


def _load_invoice_with_items(invoice_id: int) -> dict[str, Any]:
    with db() as conn:
        invoice = conn.execute("SELECT * FROM invoices WHERE id = ?", (invoice_id,)).fetchone()
        if not invoice:
            raise ValueError("Invoice not found.")
        items = conn.execute("SELECT * FROM invoice_items WHERE invoice_id = ? ORDER BY id", (invoice_id,)).fetchall()
    return {"invoice": invoice, "items": items}


def _refresh_invoice_pdf(invoice_id: int, settings: dict[str, Any] | None = None, *, remove_existing: bool = True) -> dict[str, Any]:
    """Regenerate and persist an invoice PDF, then return a fresh invoice row.

    This centralizes the write → PDF regenerate → re-fetch pattern used after
    invoice create/edit/payment operations so future PDF behavior stays in one place.
    """
    settings = settings or fetch_settings()
    data = _load_invoice_with_items(invoice_id)
    invoice = data["invoice"]
    items = data["items"]
    if remove_existing:
        _remove_old_pdf(invoice.get("pdf_path"))
    pdf_path = build_invoice_pdf(invoice, items, settings)
    with db() as conn:
        conn.execute("UPDATE invoices SET pdf_path = ?, updated_at = ? WHERE id = ?", (pdf_path, now_iso(), invoice_id))
        invoice = conn.execute("SELECT * FROM invoices WHERE id = ?", (invoice_id,)).fetchone()
    return {"invoice": invoice, "items": items, "pdf_path": pdf_path}


def preview_next_invoice_no(invoice_date: str | None = None) -> str:
    init_db()
    settings = fetch_settings()
    with db() as conn:
        return next_invoice_number(conn, settings.get("invoice_prefix", "INV"), invoice_date)


def create_invoice(payload: dict[str, Any]) -> dict[str, Any]:
    init_db()
    settings = fetch_settings()
    invoice_date = payload.get("invoice_date") or date.today().isoformat()
    due_date = payload.get("due_date") or ""
    customer_name, customer_phone = _validate_customer(payload)

    items = _calculate_items(payload.get("items") or [])
    totals = _calculate_totals(payload, items, settings)

    customer_payload = {
        "name": customer_name,
        "phone": customer_phone,
        "email": payload.get("customer_email") or "",
        "address": payload.get("customer_address") or "",
    }
    customer_id = upsert_customer(customer_payload)
    now = now_iso()
    invoice_id: int | None = None
    max_attempts = 10

    with db() as conn:
        for attempt in range(max_attempts):
            invoice_no = next_invoice_number(conn, settings.get("invoice_prefix", "INV"), invoice_date)
            try:
                cur = conn.execute(
                    """
                    INSERT INTO invoices(
                        invoice_no, invoice_date, due_date, customer_id, customer_name, customer_phone,
                        customer_email, customer_address, subtotal, discount, tax_rate, tax_amount, total,
                        paid_amount, balance, payment_status, payment_method, notes, pdf_path, created_at, updated_at
                    ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        invoice_no, invoice_date, due_date, customer_id, customer_name,
                        customer_phone, payload.get("customer_email") or "",
                        payload.get("customer_address") or "", totals["subtotal"], totals["discount"], totals["tax_rate"], totals["tax_amount"],
                        totals["total"], totals["paid_amount"], totals["balance"], totals["payment_status"], payload.get("payment_method") or "Cash",
                        payload.get("notes") or "", "", now, now,
                    ),
                )
                invoice_id = int(cur.lastrowid)
                for item in items:
                    conn.execute(
                        """
                        INSERT INTO invoice_items(invoice_id, description, quantity, unit_price, line_total)
                        VALUES(?, ?, ?, ?, ?)
                        """,
                        (invoice_id, item["description"], item["quantity"], item["unit_price"], item["line_total"]),
                    )
                break
            except sqlite3.IntegrityError as exc:
                if "invoice_no" in str(exc).lower() and attempt < max_attempts - 1:
                    logger.warning("Invoice number collision for %s; retrying (%s/%s)", invoice_no, attempt + 1, max_attempts)
                    continue
                raise
        if invoice_id is None:
            raise ValueError("Could not reserve a unique invoice number. Please try again.")

    result = _refresh_invoice_pdf(invoice_id, settings, remove_existing=False)
    if payload.get("open_after_save"):
        open_file(result["pdf_path"])
    return result


def update_invoice(invoice_id: int, payload: dict[str, Any]) -> dict[str, Any]:
    """Edit an existing invoice while keeping its original invoice number."""
    init_db()
    settings = fetch_settings()
    invoice_date = payload.get("invoice_date") or date.today().isoformat()
    due_date = payload.get("due_date") or ""
    customer_name, customer_phone = _validate_customer(payload)
    items = _calculate_items(payload.get("items") or [])
    totals = _calculate_totals(payload, items, settings)

    customer_id = upsert_customer({
        "name": customer_name,
        "phone": customer_phone,
        "email": payload.get("customer_email") or "",
        "address": payload.get("customer_address") or "",
    })
    now = now_iso()

    with db() as conn:
        existing = conn.execute("SELECT * FROM invoices WHERE id = ?", (invoice_id,)).fetchone()
        if not existing:
            raise ValueError("Invoice not found.")
        old_pdf = existing.get("pdf_path") or ""
        conn.execute(
            """
            UPDATE invoices
            SET invoice_date = ?, due_date = ?, customer_id = ?, customer_name = ?, customer_phone = ?,
                customer_email = ?, customer_address = ?, subtotal = ?, discount = ?, tax_rate = ?,
                tax_amount = ?, total = ?, paid_amount = ?, balance = ?, payment_status = ?,
                payment_method = ?, notes = ?, updated_at = ?
            WHERE id = ?
            """,
            (
                invoice_date, due_date, customer_id, customer_name, customer_phone,
                payload.get("customer_email") or "", payload.get("customer_address") or "",
                totals["subtotal"], totals["discount"], totals["tax_rate"], totals["tax_amount"], totals["total"],
                totals["paid_amount"], totals["balance"], totals["payment_status"], payload.get("payment_method") or "Cash",
                payload.get("notes") or "", now, invoice_id,
            ),
        )
        conn.execute("DELETE FROM invoice_items WHERE invoice_id = ?", (invoice_id,))
        for item in items:
            conn.execute(
                "INSERT INTO invoice_items(invoice_id, description, quantity, unit_price, line_total) VALUES(?, ?, ?, ?, ?)",
                (invoice_id, item["description"], item["quantity"], item["unit_price"], item["line_total"]),
            )
        invoice = conn.execute("SELECT * FROM invoices WHERE id = ?", (invoice_id,)).fetchone()

    result = _refresh_invoice_pdf(invoice_id, settings, remove_existing=True)
    return result


def get_invoice(invoice_id: int) -> dict[str, Any] | None:
    init_db()
    with db() as conn:
        invoice = conn.execute("SELECT * FROM invoices WHERE id = ?", (invoice_id,)).fetchone()
        if not invoice:
            return None
        items = conn.execute("SELECT * FROM invoice_items WHERE invoice_id = ? ORDER BY id", (invoice_id,)).fetchall()
    return {"invoice": invoice, "items": items}


def list_invoices(search: str = "", start_date: str = "", end_date: str = "", status: str = "", limit: int = 300) -> list[dict[str, Any]]:
    init_db()
    params: list[Any] = []
    where = ["1=1"]
    if search:
        q = f"%{search}%"
        normalized_phone = normalize_phone(search)
        q_phone = f"%{normalized_phone}%" if normalized_phone else q
        where.append("(invoice_no LIKE ? OR customer_name LIKE ? OR customer_phone LIKE ?)")
        params.extend([q, q, q_phone])
    if start_date:
        where.append("invoice_date >= ?")
        params.append(start_date)
    if end_date:
        where.append("invoice_date <= ?")
        params.append(end_date)
    if status:
        where.append("payment_status = ?")
        params.append(status)
    params.append(max(int(limit or 300), 1))
    with db() as conn:
        return conn.execute(
            f"SELECT * FROM invoices WHERE {' AND '.join(where)} ORDER BY invoice_date DESC, id DESC LIMIT ?",
            params,
        ).fetchall()


def delete_invoice(invoice_id: int, delete_pdf: bool = True) -> None:
    init_db()
    with db() as conn:
        invoice = conn.execute("SELECT pdf_path FROM invoices WHERE id = ?", (invoice_id,)).fetchone()
        conn.execute("DELETE FROM invoices WHERE id = ?", (invoice_id,))
    if delete_pdf and invoice and invoice.get("pdf_path"):
        _remove_old_pdf(invoice.get("pdf_path"))


def regenerate_invoice_pdf(invoice_id: int) -> dict[str, Any]:
    return _refresh_invoice_pdf(invoice_id, remove_existing=True)


def _ensure_invoice_pdf(invoice_id: int) -> dict[str, Any]:
    data = get_invoice(invoice_id)
    if not data:
        raise ValueError("Invoice not found.")
    path = data["invoice"].get("pdf_path") or ""
    if not path or not Path(path).exists():
        return regenerate_invoice_pdf(invoice_id)
    return {"invoice": data["invoice"], "pdf_path": path}


def open_invoice_pdf(invoice_id: int) -> tuple[bool, str]:
    try:
        data = _ensure_invoice_pdf(invoice_id)
    except Exception as exc:
        return False, str(exc)
    return open_file(data["pdf_path"])


def print_invoice_pdf(invoice_id: int) -> tuple[bool, str]:
    try:
        data = _ensure_invoice_pdf(invoice_id)
    except Exception as exc:
        return False, str(exc)
    return print_file(data["pdf_path"])


def update_invoice_payment(invoice_id: int, amount_received: Any) -> dict[str, Any]:
    """Add a later payment to an existing unpaid/partial invoice."""
    init_db()
    payment = to_whole_number(amount_received, 0)
    if payment <= 0:
        raise ValueError("Payment amount must be greater than 0.")

    settings = fetch_settings()
    with db() as conn:
        invoice = conn.execute("SELECT * FROM invoices WHERE id = ?", (invoice_id,)).fetchone()
        if not invoice:
            raise ValueError("Invoice not found.")

        total = to_whole_number(invoice.get("total"), 0)
        paid_before = to_whole_number(invoice.get("paid_amount"), 0)
        current_balance = max(to_whole_number(invoice.get("balance"), 0), 0)
        if current_balance <= 0:
            raise ValueError("This invoice is already fully paid.")

        if payment > current_balance:
            raise ValueError("Payment cannot be greater than remaining balance.")

        paid_after = to_whole_number(paid_before + payment, 0)
        if paid_after > total:
            raise ValueError("Paid amount cannot be greater than invoice total.")
        balance_after = max(to_whole_number(total - paid_after, 0), 0)

        if balance_after <= 0 and total > 0:
            status = "Paid"
        elif paid_after > 0:
            status = "Partial"
        else:
            status = "Unpaid"

        conn.execute(
            """
            UPDATE invoices
            SET paid_amount = ?, balance = ?, payment_status = ?, updated_at = ?
            WHERE id = ?
            """,
            (paid_after, balance_after, status, now_iso(), invoice_id),
        )
        invoice = conn.execute("SELECT * FROM invoices WHERE id = ?", (invoice_id,)).fetchone()
        items = conn.execute("SELECT * FROM invoice_items WHERE invoice_id = ? ORDER BY id", (invoice_id,)).fetchall()

    result = _refresh_invoice_pdf(invoice_id, settings, remove_existing=True)
    return {
        "invoice": result["invoice"],
        "pdf_path": result["pdf_path"],
        "amount_received": payment,
    }
