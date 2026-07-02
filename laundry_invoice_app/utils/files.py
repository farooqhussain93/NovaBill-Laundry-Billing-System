from __future__ import annotations

import os
import platform
import re
import shutil
import subprocess
from pathlib import Path


def safe_filename(name: str) -> str:
    name = re.sub(r"[^A-Za-z0-9._-]+", "-", name.strip())
    name = re.sub(r"-+", "-", name).strip("-._")
    return name or "file"


def ensure_unique_path(path: Path) -> Path:
    if not path.exists():
        return path
    stem, suffix = path.stem, path.suffix
    parent = path.parent
    counter = 2
    while True:
        candidate = parent / f"{stem}-{counter}{suffix}"
        if not candidate.exists():
            return candidate
        counter += 1


def open_file(path: str | Path) -> tuple[bool, str]:
    target = Path(path).expanduser().resolve()
    if not target.exists():
        return False, f"File not found: {target}"
    try:
        system = platform.system().lower()
        if system == "windows":
            os.startfile(str(target))  # type: ignore[attr-defined]
        elif system == "darwin":
            subprocess.Popen(["open", str(target)])
        else:
            subprocess.Popen(["xdg-open", str(target)])
        return True, "File opened."
    except Exception as exc:
        return False, f"Could not open file: {exc}"


def print_file(path: str | Path) -> tuple[bool, str]:
    target = Path(path).expanduser().resolve()
    if not target.exists():
        return False, f"File not found: {target}"
    try:
        system = platform.system().lower()
        if system == "windows":
            os.startfile(str(target), "print")  # type: ignore[attr-defined]
            return True, "Sent to default printer."
        if system == "darwin":
            subprocess.Popen(["lp", str(target)])
            return True, "Sent to printer."
        subprocess.Popen(["lp", str(target)])
        return True, "Sent to printer."
    except FileNotFoundError:
        return False, "Printing command was not found on this system. Open the PDF and print manually."
    except Exception as exc:
        return False, f"Could not print file: {exc}"


def _optimized_image_copy(src: Path, dst: Path, *, max_size: int = 512) -> bool:
    try:
        from PIL import Image  # type: ignore
        with Image.open(src) as img:
            img.thumbnail((max_size, max_size))
            if dst.suffix.lower() in {".jpg", ".jpeg"}:
                img = img.convert("RGB")
                img.save(dst, quality=88, optimize=True)
            else:
                img.save(dst, optimize=True)
        return True
    except Exception:
        return False


def copy_logo(source: str | Path, destination_dir: Path) -> str:
    src = Path(source).expanduser().resolve()
    if not src.exists():
        raise FileNotFoundError(f"Logo not found: {src}")
    if src.suffix.lower() not in {".png", ".jpg", ".jpeg"}:
        raise ValueError("Logo must be PNG, JPG, or JPEG for PDF export.")
    destination_dir.mkdir(parents=True, exist_ok=True)
    dst = ensure_unique_path(destination_dir / f"company_logo{src.suffix.lower()}")
    if not _optimized_image_copy(src, dst):
        shutil.copy2(src, dst)
    return str(dst)
