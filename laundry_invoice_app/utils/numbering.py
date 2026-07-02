from __future__ import annotations

from datetime import date
import re
import sqlite3


def next_invoice_number(conn: sqlite3.Connection, prefix: str = "INV", invoice_date: str | None = None) -> str:
    """Generate a globally unique invoice number: INV-YYYYMMDD-0001."""
    clean_prefix = re.sub(r"[^A-Za-z0-9]+", "", prefix or "INV").upper()[:8] or "INV"
    day = invoice_date or date.today().isoformat()
    ymd = day.replace("-", "")[:8]
    base = f"{clean_prefix}-{ymd}"
    row = conn.execute(
        "SELECT invoice_no FROM invoices WHERE invoice_no LIKE ? ORDER BY invoice_no DESC LIMIT 1",
        (f"{base}-%",),
    ).fetchone()
    next_seq = 1
    if row and row.get("invoice_no"):
        try:
            next_seq = int(str(row["invoice_no"]).rsplit("-", 1)[-1]) + 1
        except Exception:
            next_seq = 1
    candidate = f"{base}-{next_seq:04d}"
    while conn.execute("SELECT 1 FROM invoices WHERE invoice_no = ?", (candidate,)).fetchone():
        next_seq += 1
        candidate = f"{base}-{next_seq:04d}"
    return candidate
