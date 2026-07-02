from __future__ import annotations

from typing import Any

from ..utils.money import to_whole_number

SERVICE_TYPES: tuple[str, ...] = ("Wash & Iron", "Wash Only", "Iron Only", "Dry Clean")


def parse_service_items(raw: Any, *, strict: bool = False) -> tuple[str, list[str]]:
    """Validate and normalize the service dropdown price text.

    Expected line format: Item Name - Service Type=Price
    Example: Shirt - Wash & Iron=100
    """
    lines = str(raw or "").splitlines()
    normalized: list[str] = []
    errors: list[str] = []
    seen: set[tuple[str, str]] = set()

    for line_no, line in enumerate(lines, 1):
        clean = line.strip()
        if not clean:
            continue
        if "=" not in clean:
            errors.append(f"Line {line_no}: missing '=' price separator.")
            continue
        label, price_raw = clean.rsplit("=", 1)
        label = label.strip()
        price_text = price_raw.strip().replace(",", "")
        service = next((name for name in SERVICE_TYPES if label.endswith(f" - {name}")), "")
        if not service:
            errors.append(f"Line {line_no}: service type must be one of: {', '.join(SERVICE_TYPES)}.")
            continue
        item_name = label[: -len(f" - {service}")].strip()
        if not item_name:
            errors.append(f"Line {line_no}: item name is missing.")
            continue
        price = to_whole_number(price_text, -1)
        if price < 0:
            errors.append(f"Line {line_no}: price must be zero or greater.")
            continue
        key = (service.lower(), item_name.lower())
        if key in seen:
            errors.append(f"Line {line_no}: duplicate item '{item_name}' under '{service}'.")
            continue
        seen.add(key)
        normalized.append(f"{item_name} - {service}={price}")

    if strict and errors:
        raise ValueError("Service dropdown prices have invalid lines:\n" + "\n".join(errors[:12]))
    return "\n".join(normalized), errors
