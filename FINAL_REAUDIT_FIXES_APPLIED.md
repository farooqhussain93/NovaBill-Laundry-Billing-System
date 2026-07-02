# NovaBill Laundry — Final Re-Audit Fixes Applied

This build applies the final one-go fixes requested after the Claude re-audit and the UI screenshots.

## Scope decision
- Kept the app as a **single-PC / single-user** desktop app.
- Did not add multi-user, cloud, login, or shared database behavior.

## Financial safety
- Fixed the fractional-tax / whole-payment mismatch by keeping NovaBill as a **whole-PKR billing app**.
- Tax amount, grand total, paid amount, balance, item totals, and expenses are now rounded/stored/displayed as whole PKR values.
- Added backend protection so fractional tax rates no longer create unpayable `0.25` or `0.50` balances.
- Negative unit price is now rejected instead of being silently changed to zero.
- Quantity below 1 is rejected in backend validation.
- Negative discount and negative paid amount are rejected.
- Existing financial repair migration now has a v2 whole-PKR pass.

## Customer safety
- Customer phone number is now hard-required at service layer.
- Very short/garbage phone values are rejected.
- Customer deduplication remains based on normalized phone number.

## Security / architecture
- Scoped the local static server so it serves only the web frontend and `/assets/`.
- Runtime folders such as `data/`, `backups/`, `logs/`, and `invoices/` are no longer exposed through the local HTTP server.
- Added an init guard so repeated `init_db()` calls return quickly after initialization, while still reinitializing if the DB is missing or restore calls force init.

## UI polish requested by user
- Removed the top-left red/yellow/green decorative dots.
- Removed the visible `Connected • SQLite ready` sidebar badge.
- Kept the pink/yellow promo card, moved it into a cleaner bottom placement, and changed its copy to app-relevant billing text.
- The promo card button now says `Create Invoice` and opens the invoice page.
- Added dark colorful themed scrollbars/seekbars to match the approved UI.
- Strengthened number spinner hiding so only custom stepper controls are visible.
- Polished steppers with stronger theme integration.
- Added invoice save loading/disabled state to reduce double-click/double-save risk.

## Maintainability / tests
- Reduced duplicated service catalog defaults in frontend; service items now come from backend settings after startup.
- CSV importer now validates phone and total values, skips invalid rows with clear messages, and adds matching legacy item rows.
- Expanded `.gitignore` with build/dist/spec rules.
- Added frontend money-logic tests (`tests/test_frontend_logic.js`).
- Expanded Python safety tests to cover fractional tax rounding, negative price rejection, required phone, and static-server scoping.

## Verified in this environment
- `python3 tests/test_core_safety.py` → 10 tests passed.
- `node tests/test_frontend_logic.js` → passed.
- `node --check laundry_invoice_app/web/script.js` → passed.
- `python3 -m compileall -q .` → passed.

## Not verified here
- Windows PyWebView runtime window.
- Windows print/open PDF integration.
- PyInstaller EXE build.

Those must be checked on the user's Windows system with `run.bat` and then `build_exe.bat`.
