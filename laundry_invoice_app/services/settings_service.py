from __future__ import annotations

from pathlib import Path
from typing import Any

from ..config import ASSETS_DIR, DEFAULT_LOGO_PATH
from ..database import fetch_settings, update_settings
from ..utils.files import copy_logo
from .catalog_service import parse_service_items


def get_settings() -> dict[str, str]:
    settings = fetch_settings()
    if not settings.get("logo_path") and DEFAULT_LOGO_PATH.exists():
        settings["logo_path"] = str(DEFAULT_LOGO_PATH)
    return settings


def save_settings(payload: dict[str, Any]) -> dict[str, str]:
    clean = dict(payload or {})
    if "service_items" in clean:
        normalized, _errors = parse_service_items(clean.get("service_items"), strict=True)
        if not normalized.strip():
            raise ValueError("Service dropdown prices must include at least one valid item.")
        clean["service_items"] = normalized
    if "tax_rate" in clean:
        try:
            if float(clean.get("tax_rate") or 0) < 0:
                raise ValueError
        except Exception as exc:
            raise ValueError("Default tax rate cannot be negative.") from exc
    return update_settings(clean)


def set_logo_from_path(path: str) -> dict[str, str]:
    copied = copy_logo(path, ASSETS_DIR)
    return update_settings({"logo_path": copied})
