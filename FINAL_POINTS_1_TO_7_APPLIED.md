# NovaBill Laundry — Final Points 1 to 7 Applied

This pass only addressed the remaining audit items requested by the user and avoided unrelated UI/functionality changes.

## Completed items

1. **N-01 CSV importer fix**
   - `scripts/import_legacy_csv.py` now catches `ValueError` from stricter customer phone validation.
   - Invalid short phone rows are skipped with a clear message instead of crashing the full import.

2. **Dead `.sidebar-foot` CSS cleanup**
   - Removed obsolete `.sidebar-foot` rules from `web/style.css`.
   - No visible UI changes were made beyond removing dead CSS.

3. **Invoice-number retry safety**
   - `create_invoice()` now retries invoice-number reservation if a `UNIQUE(invoice_no)` collision occurs.
   - This keeps the app safer if a preview number becomes stale.

4. **Frontend tests now use real shared money logic**
   - Added `web/money_logic.js` as the shared frontend money module.
   - `script.js` now uses `NovaBillMoney` from that module.
   - `tests/test_frontend_logic.js` imports and tests the actual shared module instead of a copied reimplementation.

5. **PDF regeneration helper**
   - Added `_refresh_invoice_pdf()` in `invoice_service.py`.
   - `create_invoice()`, `update_invoice()`, `update_invoice_payment()`, and `regenerate_invoice_pdf()` now share the same PDF refresh/re-fetch flow.

6. **Schema migration ledger**
   - Added `schema_migrations` table and ordered migration tracking.
   - Existing repair/phone migrations now have a proper versioned ledger while keeping legacy settings flags for compatibility.

7. **Dependency audit wrapper**
   - Added `scripts/run_pip_audit.py`, `run_pip_audit.bat`, and `run_pip_audit.sh`.
   - README now includes the release-time `pip-audit` command.

## Tests run

```text
python -m unittest tests/test_core_safety.py
node --check laundry_invoice_app/web/money_logic.js
node --check laundry_invoice_app/web/script.js
node tests/test_frontend_logic.js
python -m compileall laundry_invoice_app scripts tests
```

`pip-audit` itself was not installed in this sandbox, so the wrapper was checked for graceful instructions when the tool is missing.
