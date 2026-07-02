from __future__ import annotations

import traceback
from typing import Any, Callable

from .database import init_db
from .logger import get_logger
from .services import backup_service, customer_service, expense_service, invoice_service, report_service, settings_service

logger = get_logger()


def ok(data: Any = None, message: str = "OK") -> dict[str, Any]:
    return {"success": True, "message": message, "data": data}


def fail(message: str, detail: str = "") -> dict[str, Any]:
    return {"success": False, "message": message, "detail": detail}


def guarded(fn: Callable[..., Any]) -> Callable[..., dict[str, Any]]:
    def wrapper(*args: Any, **kwargs: Any) -> dict[str, Any]:
        try:
            return ok(fn(*args, **kwargs))
        except ValueError as exc:
            logger.warning("Validation/API error in %s: %s", fn.__name__, exc)
            return fail(str(exc), "")
        except Exception as exc:
            detail = traceback.format_exc()
            logger.error("Unexpected API error in %s: %s\n%s", fn.__name__, exc, detail)
            return fail("Something went wrong. Please check logs/app.log for details.", detail)
    return wrapper


class AppAPI:
    def __init__(self) -> None:
        init_db()
        logger.info("App API initialized")

    @guarded
    def get_settings(self) -> dict[str, Any]:
        return settings_service.get_settings()

    @guarded
    def save_settings(self, payload: dict[str, Any]) -> dict[str, Any]:
        return settings_service.save_settings(payload or {})

    @guarded
    def get_next_invoice_no(self, invoice_date: str = "") -> str:
        return invoice_service.preview_next_invoice_no(invoice_date or None)

    @guarded
    def create_invoice(self, payload: dict[str, Any]) -> dict[str, Any]:
        return invoice_service.create_invoice(payload or {})

    @guarded
    def update_invoice(self, invoice_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        return invoice_service.update_invoice(int(invoice_id), payload or {})

    @guarded
    def list_invoices(self, filters: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        filters = filters or {}
        return invoice_service.list_invoices(
            search=filters.get("search", ""),
            start_date=filters.get("start_date", ""),
            end_date=filters.get("end_date", ""),
            status=filters.get("status", ""),
            limit=int(filters.get("limit") or 300),
        )

    @guarded
    def get_invoice(self, invoice_id: int) -> dict[str, Any] | None:
        return invoice_service.get_invoice(int(invoice_id))

    @guarded
    def delete_invoice(self, invoice_id: int) -> bool:
        invoice_service.delete_invoice(int(invoice_id))
        return True

    @guarded
    def open_invoice_pdf(self, invoice_id: int) -> dict[str, Any]:
        success, message = invoice_service.open_invoice_pdf(int(invoice_id))
        return {"success": success, "message": message}

    @guarded
    def print_invoice_pdf(self, invoice_id: int) -> dict[str, Any]:
        success, message = invoice_service.print_invoice_pdf(int(invoice_id))
        return {"success": success, "message": message}

    @guarded
    def regenerate_invoice_pdf(self, invoice_id: int) -> dict[str, Any]:
        return invoice_service.regenerate_invoice_pdf(int(invoice_id))

    @guarded
    def update_invoice_payment(self, invoice_id: int, amount_received: Any) -> dict[str, Any]:
        return invoice_service.update_invoice_payment(int(invoice_id), amount_received)

    @guarded
    def list_customers(self, search: Any = "") -> list[dict[str, Any]]:
        if isinstance(search, dict):
            return customer_service.list_customers(search.get("search", "") or "", int(search.get("limit") or 200))
        return customer_service.list_customers(str(search or ""))

    @guarded
    def get_customer(self, customer_id: int) -> dict[str, Any] | None:
        return customer_service.get_customer(int(customer_id))

    @guarded
    def delete_customer(self, customer_id: int) -> bool:
        customer_service.delete_customer(int(customer_id))
        return True

    @guarded
    def add_expense(self, payload: dict[str, Any]) -> dict[str, Any]:
        return expense_service.add_expense(payload or {})

    @guarded
    def list_expenses(self, filters: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        filters = filters or {}
        return expense_service.list_expenses(
            search=filters.get("search", ""),
            start_date=filters.get("start_date", ""),
            end_date=filters.get("end_date", ""),
            limit=int(filters.get("limit") or 200),
        )

    @guarded
    def delete_expense(self, expense_id: int) -> bool:
        expense_service.delete_expense(int(expense_id))
        return True

    @guarded
    def get_dashboard(self) -> dict[str, Any]:
        return report_service.get_dashboard()

    @guarded
    def get_monthly_report(self, year: int | None = None) -> list[dict[str, Any]]:
        return report_service.get_monthly_report(year)

    @guarded
    def create_backup(self) -> str:
        return backup_service.create_backup()

    @guarded
    def restore_backup(self, path: str = "") -> dict[str, Any]:
        if not path:
            path = self._select_file("Select backup ZIP", ("ZIP files (*.zip)",)) or ""
        return backup_service.restore_backup(path)

    @guarded
    def select_logo_file(self) -> dict[str, Any]:
        path = self._select_file("Select company logo", ("Image files (*.png;*.jpg;*.jpeg)",))
        if not path:
            return {"selected": False}
        settings = settings_service.set_logo_from_path(path)
        return {"selected": True, "settings": settings}

    def _select_file(self, title: str, file_types: tuple[str, ...]) -> str | None:
        try:
            import webview  # type: ignore
            windows = getattr(webview, "windows", [])
            if windows:
                result = windows[0].create_file_dialog(webview.OPEN_DIALOG, allow_multiple=False, file_types=file_types)
                if result:
                    return result[0]
        except Exception:
            logger.exception("File dialog failed: %s", title)
            return None
        return None
