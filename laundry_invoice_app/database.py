from __future__ import annotations

import re
import sqlite3
from decimal import Decimal, ROUND_HALF_UP
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Iterator

from .config import DB_PATH, DATA_DIR, INVOICES_DIR, BACKUPS_DIR, ASSETS_DIR, LOGS_DIR

_DB_INITIALIZED = False
CURRENT_SCHEMA_VERSION = 3

DEFAULT_SETTINGS: dict[str, str] = {
    "shop_name": "NovaBill Laundry",
    "shop_tagline": "Billing, Payments & Customer Management",
    "shop_address": "Your business address here",
    "shop_phone": "+92 300 0000000",
    "shop_email": "info@example.com",
    "currency": "PKR",
    "invoice_prefix": "INV",
    "tax_rate": "0",
    "footer_note": "Thank you for choosing us. Please keep this invoice for your records.",
    "terms_note": "All prices are subject to verification at the counter. Clothes must be collected within the agreed time.",
    "logo_path": "",
    "paper_size": "A4",
    "service_items": "Shirt - Wash & Iron=100\nJeans / Pant - Wash & Iron=130\nKamiz / Shalwar / Shirt / Kurti - Wash & Iron=120\nBedsheet Single - Wash & Iron=120\nBedsheet Double - Wash & Iron=170\nBedcover - Wash & Iron=230\nPillow Cover - Wash & Iron=60\nBath Towel - Wash & Iron=110\nCurtains Normal Per Panel - Wash & Iron=500\nCurtains Fancy Per Panel - Wash & Iron=650\nSofa Cover Per Seat - Wash & Iron=290\nTable Cover - Wash & Iron=160\nShirt - Wash Only=80\nJeans / Pant - Wash Only=90\nKamiz / Shalwar / Shirt / Kurti - Wash Only=80\nBedsheet Single - Wash Only=80\nBedsheet Double - Wash Only=120\nBedcover - Wash Only=170\nPillow Cover - Wash Only=50\nBath Towel - Wash Only=80\nCurtains Normal Per Panel - Wash Only=350\nCurtains Fancy Per Panel - Wash Only=450\nCushion Cover - Wash Only=50\nSofa Cover Per Seat - Wash Only=210\nTable Cover - Wash Only=120\nBlanket / Comforter Single - Wash Only=700\nBlanket / Comforter Double - Wash Only=800\nRug Medium - Wash Only=350\nRug Large - Wash Only=600\nDoor Mat - Wash Only=250\nCar Cover Hatchback - Wash Only=500\nCar Cover Sedan - Wash Only=800\nCar Cover SUV - Wash Only=1000\nBags Cleaning - Wash Only=600\nHand Bag - Wash Only=300\nShirt - Iron Only=60\nJeans / Pant - Iron Only=60\nKamiz / Shalwar / Shirt / Kurti - Iron Only=60\nBedsheet Single - Iron Only=60\nBedsheet Double - Iron Only=90\nBedcover - Iron Only=120\nPillow Cover - Iron Only=50\nCurtains Normal Per Panel - Iron Only=300\nCurtains Fancy Per Panel - Iron Only=400\n2 Pcs Suit - Dry Clean=850\n3 Pcs Suit - Dry Clean=1200\nSafari Suit - Dry Clean=600\nSherwani - Dry Clean=1200\nWaist Coat - Dry Clean=500\nMaxi / Sharara / Gharara - Dry Clean=2200\nBridal Dress - Dry Clean=2300",
}

SCHEMA = r"""
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS schema_migrations (
    version INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    applied_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS customers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    phone TEXT,
    email TEXT,
    address TEXT,
    notes TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_customers_name ON customers(name);
CREATE INDEX IF NOT EXISTS idx_customers_phone ON customers(phone);

CREATE TABLE IF NOT EXISTS invoices (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    invoice_no TEXT NOT NULL UNIQUE,
    invoice_date TEXT NOT NULL,
    due_date TEXT,
    customer_id INTEGER,
    customer_name TEXT NOT NULL,
    customer_phone TEXT,
    customer_email TEXT,
    customer_address TEXT,
    subtotal REAL NOT NULL DEFAULT 0 CHECK(subtotal >= 0 AND subtotal = ROUND(subtotal)),
    discount REAL NOT NULL DEFAULT 0 CHECK(discount >= 0 AND discount = ROUND(discount)),
    tax_rate REAL NOT NULL DEFAULT 0 CHECK(tax_rate >= 0),
    tax_amount REAL NOT NULL DEFAULT 0 CHECK(tax_amount >= 0 AND tax_amount = ROUND(tax_amount)),
    total REAL NOT NULL DEFAULT 0 CHECK(total >= 0 AND total = ROUND(total)),
    paid_amount REAL NOT NULL DEFAULT 0 CHECK(paid_amount >= 0 AND paid_amount = ROUND(paid_amount)),
    balance REAL NOT NULL DEFAULT 0 CHECK(balance >= 0 AND balance = ROUND(balance)),
    payment_status TEXT NOT NULL DEFAULT 'Unpaid' CHECK(payment_status IN ('Unpaid', 'Partial', 'Paid')),
    payment_method TEXT,
    notes TEXT,
    pdf_path TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY(customer_id) REFERENCES customers(id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_invoices_no ON invoices(invoice_no);
CREATE INDEX IF NOT EXISTS idx_invoices_date ON invoices(invoice_date);
CREATE INDEX IF NOT EXISTS idx_invoices_customer ON invoices(customer_name);
CREATE INDEX IF NOT EXISTS idx_invoices_phone ON invoices(customer_phone);
CREATE INDEX IF NOT EXISTS idx_invoices_status ON invoices(payment_status);

CREATE TABLE IF NOT EXISTS invoice_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    invoice_id INTEGER NOT NULL,
    description TEXT NOT NULL,
    quantity REAL NOT NULL DEFAULT 1 CHECK(quantity >= 1 AND quantity = ROUND(quantity)),
    unit_price REAL NOT NULL DEFAULT 0 CHECK(unit_price >= 0 AND unit_price = ROUND(unit_price)),
    line_total REAL NOT NULL DEFAULT 0 CHECK(line_total >= 0 AND line_total = ROUND(line_total)),
    FOREIGN KEY(invoice_id) REFERENCES invoices(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS expenses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    expense_date TEXT NOT NULL,
    category TEXT NOT NULL,
    description TEXT,
    amount REAL NOT NULL DEFAULT 0 CHECK(amount >= 0 AND amount = ROUND(amount)),
    payment_method TEXT,
    notes TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_expenses_date ON expenses(expense_date);
CREATE INDEX IF NOT EXISTS idx_expenses_category ON expenses(category);
"""


def dict_factory(cursor: sqlite3.Cursor, row: tuple[Any, ...]) -> dict[str, Any]:
    return {col[0]: row[idx] for idx, col in enumerate(cursor.description)}


def get_connection() -> sqlite3.Connection:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = dict_factory
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


@contextmanager
def db() -> Iterator[sqlite3.Connection]:
    conn = get_connection()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def now_iso() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")



def normalize_phone_value(phone: str | None) -> str:
    """Normalize phone numbers so the same customer is not stored twice.

    Examples:
    +92 300 1234567 -> 03001234567
    0092-300-1234567 -> 03001234567
    3001234567 -> 03001234567
    """
    digits = re.sub(r"\D+", "", str(phone or ""))
    if not digits:
        return ""
    if digits.startswith("0092"):
        digits = digits[2:]
    if digits.startswith("92") and len(digits) >= 12:
        digits = "0" + digits[2:]
    elif digits.startswith("3") and len(digits) == 10:
        digits = "0" + digits
    return digits


def _migrate_phone_numbers(conn: sqlite3.Connection) -> None:
    """Normalize existing phone values and merge duplicate customer records safely."""
    customers = conn.execute("SELECT id, phone FROM customers ORDER BY id ASC").fetchall()
    seen: dict[str, int] = {}
    for customer in customers:
        customer_id = int(customer["id"])
        normalized = normalize_phone_value(customer.get("phone"))
        if not normalized:
            conn.execute("UPDATE customers SET phone = '' WHERE id = ?", (customer_id,))
            continue
        keeper_id = seen.get(normalized)
        if keeper_id is None:
            seen[normalized] = customer_id
            conn.execute("UPDATE customers SET phone = ? WHERE id = ?", (normalized, customer_id))
        else:
            conn.execute("UPDATE invoices SET customer_id = ? WHERE customer_id = ?", (keeper_id, customer_id))
            conn.execute("DELETE FROM customers WHERE id = ?", (customer_id,))

    invoices = conn.execute("SELECT id, customer_phone FROM invoices").fetchall()
    for invoice in invoices:
        normalized = normalize_phone_value(invoice.get("customer_phone"))
        conn.execute("UPDATE invoices SET customer_phone = ? WHERE id = ?", (normalized, int(invoice["id"])))

def _get_internal_setting(conn: sqlite3.Connection, key: str) -> str:
    row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    return str(row["value"] if row else "")


def _set_internal_setting(conn: sqlite3.Connection, key: str, value: str) -> None:
    conn.execute(
        "INSERT INTO settings(key, value) VALUES(?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, value),
    )


def _has_migration(conn: sqlite3.Connection, version: int) -> bool:
    row = conn.execute("SELECT 1 FROM schema_migrations WHERE version = ?", (version,)).fetchone()
    return bool(row)


def _mark_migration(conn: sqlite3.Connection, version: int, name: str) -> None:
    conn.execute(
        "INSERT OR IGNORE INTO schema_migrations(version, name, applied_at) VALUES(?, ?, ?)",
        (version, name, now_iso()),
    )
    try:
        current = int(_get_internal_setting(conn, "schema_version") or 0)
    except ValueError:
        current = 0
    _set_internal_setting(conn, "schema_version", str(max(version, current)))
    conn.execute(f"PRAGMA user_version = {CURRENT_SCHEMA_VERSION}")


def _run_schema_migrations(conn: sqlite3.Connection) -> None:
    """Run ordered, idempotent schema/data migrations.

    Older builds used individual settings flags. The schema_migrations table is now
    the authoritative migration ledger while the old flags are still written for
    backward compatibility with existing databases.
    """
    migrations = [
        (1, "normalize_phone_numbers_v1", _migrate_phone_numbers, "_phone_migration_v1"),
        (2, "repair_financial_records_v1", _repair_financial_records, "_financial_repair_v1"),
        (3, "repair_financial_records_v2_whole_pkr", _repair_financial_records, "_financial_repair_v2_whole_pkr"),
    ]
    for version, name, func, legacy_flag in migrations:
        if _has_migration(conn, version):
            continue
        func(conn)
        _set_internal_setting(conn, legacy_flag, "1")
        _mark_migration(conn, version, name)


def _whole_number(value: Any, default: int = 0) -> int:
    try:
        amount = Decimal(str(value if value not in [None, ""] else default))
        return int(amount.quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    except Exception:
        return int(default)


def _repair_financial_records(conn: sqlite3.Connection) -> None:
    """Repair legacy invoices created before validation hardening.

    This prevents negative balances, paid amounts above totals, discounts above
    subtotal, and stale line totals from remaining in an existing database.
    """
    invoices = conn.execute("SELECT * FROM invoices ORDER BY id").fetchall()
    for invoice in invoices:
        invoice_id = int(invoice["id"])
        items = conn.execute("SELECT id, quantity, unit_price FROM invoice_items WHERE invoice_id = ?", (invoice_id,)).fetchall()
        subtotal = 0
        for item in items:
            quantity = max(_whole_number(item.get("quantity"), 1), 1)
            unit_price = max(_whole_number(item.get("unit_price"), 0), 0)
            line_total = _whole_number(quantity * unit_price, 0)
            subtotal += line_total
            conn.execute(
                "UPDATE invoice_items SET quantity = ?, unit_price = ?, line_total = ? WHERE id = ?",
                (quantity, unit_price, line_total, int(item["id"])),
            )

        subtotal = max(_whole_number(subtotal if items else invoice.get("subtotal"), 0), 0)
        discount = min(max(_whole_number(invoice.get("discount"), 0), 0), subtotal)
        tax_rate = max(float(invoice.get("tax_rate") or 0), 0)
        taxable = max(subtotal - discount, 0)
        tax_amount = max(_whole_number(taxable * tax_rate / 100, 0), 0)
        total = _whole_number(taxable + tax_amount, 0)
        paid_amount = min(max(_whole_number(invoice.get("paid_amount"), 0), 0), total)
        balance = max(_whole_number(total - paid_amount, 0), 0)
        if total > 0 and balance <= 0:
            status = "Paid"
        elif paid_amount > 0:
            status = "Partial"
        else:
            status = "Unpaid"
        conn.execute(
            """
            UPDATE invoices
            SET subtotal = ?, discount = ?, tax_rate = ?, tax_amount = ?, total = ?,
                paid_amount = ?, balance = ?, payment_status = ?, updated_at = ?
            WHERE id = ?
            """,
            (subtotal, discount, tax_rate, tax_amount, total, paid_amount, balance, status, now_iso(), invoice_id),
        )


def init_db(*, force: bool = False) -> None:
    global _DB_INITIALIZED
    if not force and _DB_INITIALIZED and DB_PATH.exists():
        return
    for d in [DATA_DIR, INVOICES_DIR, BACKUPS_DIR, ASSETS_DIR, LOGS_DIR]:
        d.mkdir(parents=True, exist_ok=True)
    with db() as conn:
        conn.executescript(SCHEMA)
        for key, value in DEFAULT_SETTINGS.items():
            conn.execute(
                "INSERT OR IGNORE INTO settings(key, value) VALUES(?, ?)",
                (key, value),
            )
        _run_schema_migrations(conn)
        conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS uq_customers_phone ON customers(phone) WHERE phone IS NOT NULL AND phone != ''")
        _set_internal_setting(conn, "schema_version", str(CURRENT_SCHEMA_VERSION))
    _DB_INITIALIZED = True


def fetch_settings() -> dict[str, str]:
    init_db()
    with db() as conn:
        rows = conn.execute("SELECT key, value FROM settings").fetchall()
    settings = DEFAULT_SETTINGS.copy()
    settings.update({r["key"]: r["value"] for r in rows})
    return settings


def update_settings(values: dict[str, Any]) -> dict[str, str]:
    init_db()
    allowed = set(DEFAULT_SETTINGS.keys())
    with db() as conn:
        for key, value in values.items():
            if key in allowed:
                conn.execute(
                    "INSERT INTO settings(key, value) VALUES(?, ?) "
                    "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                    (key, "" if value is None else str(value)),
                )
    return fetch_settings()
