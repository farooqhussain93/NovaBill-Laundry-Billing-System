from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path


def _is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


APP_NAME = "NovaBill Laundry"
APP_VERSION = "1.0.0"

# In development, project files live in the source folder.
# In EXE mode, bundled read-only files live in sys._MEIPASS, while user data
# should be created beside the EXE so invoices/database/backups stay editable.
if _is_frozen():
    BUNDLE_ROOT = Path(getattr(sys, "_MEIPASS", Path(sys.executable).resolve().parent))
    PROJECT_ROOT = Path(sys.executable).resolve().parent
else:
    BUNDLE_ROOT = Path(__file__).resolve().parents[1]
    PROJECT_ROOT = Path(os.environ.get("NOVABILL_PROJECT_ROOT", BUNDLE_ROOT)).resolve()

DATA_DIR = PROJECT_ROOT / "data"
INVOICES_DIR = PROJECT_ROOT / "invoices"
BACKUPS_DIR = PROJECT_ROOT / "backups"
ASSETS_DIR = PROJECT_ROOT / "assets"
LOGS_DIR = PROJECT_ROOT / "logs"

# Web files are served from PROJECT_ROOT/laundry_invoice_app/web. In EXE mode
# they are copied there from the PyInstaller bundle on startup.
WEB_DIR = PROJECT_ROOT / "laundry_invoice_app" / "web"
DB_PATH = DATA_DIR / "laundry_invoice.db"
DEFAULT_LOGO_PATH = ASSETS_DIR / "default_logo.png"


def _copy_file_if_needed(src: Path, dst: Path, *, overwrite: bool = False) -> None:
    if not src.exists() or not src.is_file():
        return
    dst.parent.mkdir(parents=True, exist_ok=True)
    if overwrite or not dst.exists():
        shutil.copy2(src, dst)


def _sync_runtime_files() -> None:
    """Prepare writable runtime folders and web/assets files for EXE mode.

    PyInstaller one-folder/one-file builds keep bundled files in a temporary
    internal folder. The app serves HTML/CSS/JS through a local server, so in
    frozen mode we copy the bundled web frontend beside the EXE. Database,
    invoices, backups and uploaded logos also live beside the EXE.
    """
    for directory in [DATA_DIR, INVOICES_DIR, BACKUPS_DIR, ASSETS_DIR, LOGS_DIR]:
        directory.mkdir(parents=True, exist_ok=True)

    if not _is_frozen():
        return

    bundled_web = BUNDLE_ROOT / "laundry_invoice_app" / "web"
    if bundled_web.exists():
        WEB_DIR.mkdir(parents=True, exist_ok=True)
        for src in bundled_web.rglob("*"):
            if src.is_file():
                dst = WEB_DIR / src.relative_to(bundled_web)
                _copy_file_if_needed(src, dst, overwrite=True)

    bundled_assets = BUNDLE_ROOT / "assets"
    if bundled_assets.exists():
        for name in ["default_logo.png", "app_icon.png", "app_icon.ico"]:
            _copy_file_if_needed(bundled_assets / name, ASSETS_DIR / name, overwrite=(name.startswith("default_") or name.startswith("app_icon")))


_sync_runtime_files()
