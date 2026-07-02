from __future__ import annotations

import os
import shutil
import sqlite3
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

PROJECT_ROOT_FOR_IMPORTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT_FOR_IMPORTS))
TEST_ROOT = Path(tempfile.mkdtemp(prefix="novabill-tests-"))
os.environ["NOVABILL_PROJECT_ROOT"] = str(TEST_ROOT)

from laundry_invoice_app.config import BACKUPS_DIR, DB_PATH, INVOICES_DIR, LOGS_DIR, WEB_DIR, ASSETS_DIR  # noqa: E402
from laundry_invoice_app.database import db, init_db, CURRENT_SCHEMA_VERSION  # noqa: E402
from laundry_invoice_app.services.backup_service import create_backup, restore_backup  # noqa: E402
from laundry_invoice_app.services.customer_service import upsert_customer  # noqa: E402
from laundry_invoice_app.services.expense_service import add_expense  # noqa: E402
from laundry_invoice_app.services.invoice_service import create_invoice, update_invoice_payment  # noqa: E402
from laundry_invoice_app.utils.numbering import next_invoice_number as original_next_invoice_number  # noqa: E402


class CoreSafetyTests(unittest.TestCase):
    def setUp(self) -> None:
        for folder in [TEST_ROOT / "data", INVOICES_DIR, BACKUPS_DIR, LOGS_DIR]:
            shutil.rmtree(folder, ignore_errors=True)
        init_db()

    def payload(self, **overrides):
        base = {
            "invoice_date": "2026-06-30",
            "customer_name": "Ali Test",
            "customer_phone": "03001234567",
            "discount": 0,
            "tax_rate": 5,
            "paid_amount": 0,
            "open_after_save": False,
            "items": [{"description": "Shirt - Wash & Iron", "quantity": 2, "unit_price": 100}],
        }
        base.update(overrides)
        return base

    def test_invoice_creation_uses_safe_totals(self):
        result = create_invoice(self.payload(paid_amount=50))
        inv = result["invoice"]
        self.assertEqual(inv["total"], 210.0)
        self.assertEqual(inv["paid_amount"], 50.0)
        self.assertEqual(inv["balance"], 160.0)
        self.assertEqual(inv["payment_status"], "Partial")

    def test_overpayment_is_blocked(self):
        with self.assertRaisesRegex(ValueError, "Paid amount cannot be greater"):
            create_invoice(self.payload(paid_amount=999999))

    def test_discount_above_subtotal_is_blocked(self):
        with self.assertRaisesRegex(ValueError, "Discount cannot be greater"):
            create_invoice(self.payload(discount=999999))

    def test_negative_expense_is_blocked(self):
        with self.assertRaisesRegex(ValueError, "Expense amount cannot be negative"):
            add_expense({"expense_date": "2026-06-30", "category": "Rent", "amount": -100})

    def test_phone_dedup_requires_unique_phone(self):
        first = upsert_customer({"name": "Ali", "phone": "+92 300 9999999"})
        second = upsert_customer({"name": "Ali Updated", "phone": "0300-9999999"})
        self.assertEqual(first, second)
        with self.assertRaisesRegex(ValueError, "phone number is required"):
            upsert_customer({"name": "Same Name", "phone": ""})
        with self.assertRaisesRegex(ValueError, "valid customer phone"):
            upsert_customer({"name": "Short Phone", "phone": "5"})

    def test_fractional_tax_rounds_to_whole_pkr_and_can_be_paid(self):
        result = create_invoice(self.payload(tax_rate=8.25, items=[{"description": "Test Item", "quantity": 1, "unit_price": 100}]))
        inv = result["invoice"]
        self.assertEqual(inv["tax_amount"], 8.0)
        self.assertEqual(inv["total"], 108.0)
        paid = update_invoice_payment(inv["id"], 108)
        self.assertEqual(paid["invoice"]["balance"], 0.0)
        self.assertEqual(paid["invoice"]["payment_status"], "Paid")

    def test_negative_unit_price_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "Unit price cannot be negative"):
            create_invoice(self.payload(items=[{"description": "Bad Item", "quantity": 1, "unit_price": -100}]))



    def test_legacy_csv_importer_skips_invalid_short_phone_and_continues(self):
        from scripts.import_legacy_csv import main as import_legacy_csv

        csv_path = TEST_ROOT / "legacy.csv"
        csv_path.write_text(
            "invoice_no,customer_name,customer_phone,total,invoice_date\n"
            "LEG-1,Good One,03001234567,100,2026-06-30\n"
            "LEG-2,Bad Short,123,200,2026-06-30\n"
            "LEG-3,Good Two,03007654321,300,2026-06-30\n",
            encoding="utf-8",
        )
        import_legacy_csv(str(csv_path))
        with db() as conn:
            invoice_nos = [r["invoice_no"] for r in conn.execute("SELECT invoice_no FROM invoices ORDER BY invoice_no").fetchall()]
        self.assertEqual(invoice_nos, ["LEG-1", "LEG-3"])

    def test_schema_migration_ledger_records_current_version(self):
        with db() as conn:
            rows = conn.execute("SELECT version FROM schema_migrations ORDER BY version").fetchall()
            schema_version = conn.execute("SELECT value FROM settings WHERE key = 'schema_version'").fetchone()
        self.assertEqual([int(r["version"]) for r in rows], list(range(1, CURRENT_SCHEMA_VERSION + 1)))
        self.assertEqual(schema_version["value"], str(CURRENT_SCHEMA_VERSION))

    def test_invoice_number_collision_retries_and_saves_next_number(self):
        first = create_invoice(self.payload(customer_phone="03002222222"))["invoice"]
        original = original_next_invoice_number
        calls = {"count": 0}

        def duplicate_then_real(conn, prefix="INV", invoice_date=None):
            calls["count"] += 1
            if calls["count"] == 1:
                return first["invoice_no"]
            return original(conn, prefix, invoice_date)

        with patch("laundry_invoice_app.services.invoice_service.next_invoice_number", duplicate_then_real):
            second = create_invoice(self.payload(customer_phone="03003333333"))["invoice"]
        self.assertNotEqual(first["invoice_no"], second["invoice_no"])
        self.assertGreaterEqual(calls["count"], 2)

    def test_static_handler_does_not_serve_runtime_data(self):
        from laundry_invoice_app.app import QuietStaticHandler
        handler = object.__new__(QuietStaticHandler)
        data_path = Path(handler.translate_path('/data/laundry_invoice.db')).resolve()
        asset_path = Path(handler.translate_path('/assets/default_logo.png')).resolve()
        self.assertEqual(data_path, (WEB_DIR / 'data' / 'laundry_invoice.db').resolve())
        self.assertNotEqual(data_path, DB_PATH.resolve())
        self.assertEqual(asset_path, (ASSETS_DIR / 'default_logo.png').resolve())

    def test_corrupt_backup_restore_does_not_replace_live_database(self):
        create_invoice(self.payload())
        conn = sqlite3.connect(DB_PATH)
        before = conn.execute("SELECT COUNT(*) FROM invoices").fetchone()[0]
        conn.close()

        corrupt = BACKUPS_DIR / "corrupt.zip"
        BACKUPS_DIR.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(corrupt, "w") as z:
            z.writestr("data/laundry_invoice.db", "not sqlite")

        with self.assertRaisesRegex(ValueError, "invalid|corrupted"):
            restore_backup(str(corrupt))

        conn = sqlite3.connect(DB_PATH)
        after = conn.execute("SELECT COUNT(*) FROM invoices").fetchone()[0]
        integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
        conn.close()
        self.assertEqual(before, after)
        self.assertEqual(integrity, "ok")

    def test_valid_backup_can_restore(self):
        create_invoice(self.payload(customer_phone="03001111111"))
        backup = create_backup()
        restore_backup(backup)
        conn = sqlite3.connect(DB_PATH)
        count = conn.execute("SELECT COUNT(*) FROM invoices").fetchone()[0]
        conn.close()
        self.assertEqual(count, 1)


if __name__ == "__main__":
    unittest.main()
