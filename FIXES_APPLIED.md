# NovaBill Laundry — Audit Fixes Applied

This build follows the professional audit roadmap and focuses on safety, reliability, maintainability, and daily-use workflow.

## Critical fixes

- Safe restore flow: validates ZIP entries, blocks path traversal, validates SQLite integrity, checks required tables, and only replaces live DB after validation passes.
- Overpayment blocked: invoice creation, invoice edit, and later payment updates reject paid amounts above the invoice total/remaining balance.
- Negative balances prevented: backend and frontend now calculate balance with a zero floor after validation.
- Discount above subtotal blocked in frontend and backend.
- Negative expenses blocked in backend and frontend.

## Reliability improvements

- Added rotating app logging at `logs/app.log`.
- API now logs unexpected errors and returns user-safe messages.
- Backup/restore failures are logged clearly.
- PDF missing path is handled by automatic regeneration on open/print.
- Added manual Regenerate PDF action in invoice history for missing PDFs.

## Database/data-safety improvements

- Phone migration now runs once using an internal settings flag.
- Legacy financial repair migration runs once and fixes negative/overpaid records in existing DBs.
- New database schema includes CHECK constraints for non-negative money values and valid payment statuses.
- Customer deduplication now merges only by normalized phone number, not by name-only matches.

## Frontend/UI workflow improvements

- Added invoice edit workflow while preserving original invoice number.
- Updated invoice history actions: Edit, Update Payment, Open, Print, Regenerate PDF, Delete.
- Added Load More controls for invoice history, customers, and expenses.
- Removed fragile inline JSON click handlers and replaced with `data-action` event delegation.
- Improved invoice money validation feedback with input error highlighting.
- Kept the approved dark colorful UI theme intact.

## Settings/service catalog improvements

- Service Dropdown Prices are now validated in the backend.
- Invalid service item lines are rejected with clear messages instead of silently disappearing.

## Cleanup

- Removed `__pycache__` and `.pyc` files from the source package.
- Removed duplicate `company_logo.png` because it was identical to `default_logo.png`.
- Optimized oversized PNG assets.
- Removed duplicate build guide file; README remains the main guide.
- Added automated safety tests.

## Test command

```bash
python -m unittest -v tests/test_core_safety.py
```

Tested successfully:

- invoice totals
- overpayment blocking
- discount blocking
- negative expense blocking
- phone deduplication
- valid backup restore
- corrupt backup restore safety
