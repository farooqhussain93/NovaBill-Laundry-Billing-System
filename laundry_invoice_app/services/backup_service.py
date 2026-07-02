from __future__ import annotations

import shutil
import sqlite3
import tempfile
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any

from ..config import ASSETS_DIR, BACKUPS_DIR, DATA_DIR, DB_PATH, INVOICES_DIR
from ..database import init_db
from ..logger import get_logger
from ..utils.files import ensure_unique_path

REQUIRED_TABLES = {"settings", "customers", "invoices", "invoice_items", "expenses"}
logger = get_logger()


def create_backup() -> str:
    init_db()
    BACKUPS_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    target = ensure_unique_path(BACKUPS_DIR / f"laundry-backup-{stamp}.zip")
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as z:
        if DB_PATH.exists():
            z.write(DB_PATH, "data/laundry_invoice.db")
        for base, folder_name in [(INVOICES_DIR, "invoices"), (ASSETS_DIR, "assets")]:
            if base.exists():
                for path in base.rglob("*"):
                    if path.is_file():
                        z.write(path, f"{folder_name}/{path.relative_to(base).as_posix()}")
    logger.info("Backup created: %s", target)
    return str(target)


def _validate_zip_members(z: zipfile.ZipFile) -> None:
    for member in z.infolist():
        name = member.filename.replace("\\", "/")
        parts = [part for part in name.split("/") if part]
        if not parts:
            continue
        if name.startswith("/") or any(part == ".." for part in parts) or ":" in parts[0]:
            raise ValueError(f"Backup contains an unsafe path: {member.filename}")
        if parts[0] not in {"data", "invoices", "assets"}:
            raise ValueError(f"Backup contains an unexpected folder: {parts[0]}")


def _safe_extract(z: zipfile.ZipFile, target_dir: Path) -> None:
    _validate_zip_members(z)
    for member in z.infolist():
        if member.is_dir():
            continue
        destination = (target_dir / member.filename).resolve()
        if not str(destination).startswith(str(target_dir.resolve())):
            raise ValueError(f"Backup contains an unsafe path: {member.filename}")
        destination.parent.mkdir(parents=True, exist_ok=True)
        with z.open(member, "r") as src, destination.open("wb") as dst:
            shutil.copyfileobj(src, dst)


def _validate_database(db_path: Path) -> None:
    if not db_path.exists() or not db_path.is_file():
        raise ValueError("Backup does not contain data/laundry_invoice.db")
    try:
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        try:
            integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
            if integrity != "ok":
                raise ValueError(f"Backup database integrity check failed: {integrity}")
            tables = {row["name"] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            missing = sorted(REQUIRED_TABLES - tables)
            if missing:
                raise ValueError("Backup database is missing required tables: " + ", ".join(missing))
            # Lightweight query check: confirms required tables are readable.
            for table in REQUIRED_TABLES:
                conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()
        finally:
            conn.close()
    except sqlite3.DatabaseError as exc:
        raise ValueError(f"Backup database is invalid or corrupted: {exc}") from exc


def _replace_folder_from_candidate(candidate: Path, destination: Path) -> None:
    if not candidate.exists():
        return
    backup_old = destination.with_name(f"{destination.name}-old-{datetime.now().strftime('%Y%m%d-%H%M%S')}")
    if destination.exists():
        if backup_old.exists():
            shutil.rmtree(backup_old, ignore_errors=True)
        destination.rename(backup_old)
    try:
        shutil.copytree(candidate, destination)
        if backup_old.exists():
            shutil.rmtree(backup_old, ignore_errors=True)
    except Exception:
        if destination.exists():
            shutil.rmtree(destination, ignore_errors=True)
        if backup_old.exists():
            backup_old.rename(destination)
        raise


def restore_backup(zip_path: str) -> dict[str, Any]:
    archive = Path(zip_path).expanduser().resolve()
    if not archive.exists() or archive.suffix.lower() != ".zip":
        raise ValueError("Please select a valid .zip backup file.")

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    safety_backup = create_backup()
    temp_root = Path(tempfile.mkdtemp(prefix=f"novabill-restore-{stamp}-", dir=str(DATA_DIR)))
    try:
        with zipfile.ZipFile(archive, "r") as z:
            _safe_extract(z, temp_root)

        db_candidate = temp_root / "data" / "laundry_invoice.db"
        # Critical safety rule: validate candidate DB before touching live DB.
        _validate_database(db_candidate)

        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        db_backup = DB_PATH.with_name(f"{DB_PATH.stem}-pre-restore-{stamp}{DB_PATH.suffix}")
        if DB_PATH.exists():
            shutil.copy2(DB_PATH, db_backup)
        try:
            shutil.copy2(db_candidate, DB_PATH)
            _replace_folder_from_candidate(temp_root / "invoices", INVOICES_DIR)
            if (temp_root / "assets").exists():
                ASSETS_DIR.mkdir(parents=True, exist_ok=True)
                for path in (temp_root / "assets").rglob("*"):
                    if path.is_file():
                        dst = ASSETS_DIR / path.relative_to(temp_root / "assets")
                        dst.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(path, dst)
            # Run schema/default initialization after the replacement is complete.
            init_db(force=True)
        except Exception:
            if db_backup.exists():
                shutil.copy2(db_backup, DB_PATH)
            raise
        finally:
            if db_backup.exists():
                try:
                    db_backup.unlink()
                except OSError:
                    pass

        logger.info("Backup restored from %s. Safety backup: %s", archive, safety_backup)
        return {"restored": True, "safety_backup": safety_backup}
    except Exception:
        logger.exception("Backup restore failed safely. Live data should remain unchanged. Archive=%s", archive)
        raise
    finally:
        if temp_root.exists():
            shutil.rmtree(temp_root, ignore_errors=True)
