r"""Optional legacy importer.

Use this only if you have an old CSV invoice history file from the older app.
Because old CSV formats can differ, this script imports basic customer/invoice totals when matching columns exist.

Usage:
    python scripts/import_legacy_csv.py path\to\old\invoices.csv
"""
from __future__ import annotations

import csv
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from laundry_invoice_app.database import db, init_db, now_iso  # noqa: E402
from laundry_invoice_app.services.customer_service import normalize_phone, upsert_customer  # noqa: E402
from laundry_invoice_app.utils.money import to_whole_number  # noqa: E402


def first(row: dict[str, str], *names: str) -> str:
    lowered = {k.lower().strip(): v for k, v in row.items()}
    for name in names:
        if name.lower() in lowered:
            return lowered[name.lower()] or ""
    return ""


def main(path: str) -> None:
    init_db()
    csv_path = Path(path)
    if not csv_path.exists():
        raise SystemExit(f"CSV not found: {csv_path}")
    imported = 0
    skipped = 0
    with csv_path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            customer_name = first(row, "customer_name", "customer", "name") or "Imported Customer"
            customer_phone = first(row, "customer_phone", "phone", "mobile")
            invoice_no = first(row, "invoice_no", "invoice", "id") or f"LEGACY-{imported+1:04d}"
            invoice_date = first(row, "invoice_date", "date") or now_iso()[:10]
            customer_phone = normalize_phone(customer_phone)
            total = to_whole_number(first(row, "total", "grand_total", "amount"), 0)
            if not customer_phone:
                skipped += 1
                print(f"Skipping {invoice_no}: customer phone is required.")
                continue
            if total < 0:
                skipped += 1
                print(f"Skipping {invoice_no}: total cannot be negative.")
                continue
            try:
                customer_id = upsert_customer({"name": customer_name, "phone": customer_phone})
            except ValueError as exc:
                skipped += 1
                print(f"Skipping {invoice_no}: {exc}")
                continue
            with db() as conn:
                exists = conn.execute("SELECT id FROM invoices WHERE invoice_no = ?", (invoice_no,)).fetchone()
                if exists:
                    continue
                cur = conn.execute(
                    """
                    INSERT INTO invoices(invoice_no, invoice_date, customer_id, customer_name, customer_phone,
                    subtotal, discount, tax_rate, tax_amount, total, paid_amount, balance, payment_status, payment_method,
                    notes, pdf_path, created_at, updated_at)
                    VALUES(?, ?, ?, ?, ?, ?, 0, 0, 0, ?, 0, ?, 'Unpaid', 'Cash', 'Imported from legacy CSV', '', ?, ?)
                    """,
                    (invoice_no, invoice_date, customer_id, customer_name, customer_phone, total, total, total, now_iso(), now_iso()),
                )
                invoice_id = int(cur.lastrowid)
                conn.execute(
                    "INSERT INTO invoice_items(invoice_id, description, quantity, unit_price, line_total) VALUES(?, ?, 1, ?, ?)",
                    (invoice_id, "Legacy imported invoice", total, total),
                )
                imported += 1
    print(f"Imported {imported} legacy invoice records. Skipped {skipped} invalid rows.")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        raise SystemExit("Usage: python scripts/import_legacy_csv.py path/to/invoices.csv")
    main(sys.argv[1])
