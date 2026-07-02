"""Run a dependency vulnerability audit for NovaBill Laundry.

This wrapper keeps pip-audit out of runtime requirements. Install it only in a
release/dev environment:
    python -m pip install pip-audit
    python scripts/run_pip_audit.py
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
REQ_FILE = PROJECT_ROOT / "requirements.txt"


def main() -> int:
    if not REQ_FILE.exists():
        print(f"requirements.txt not found: {REQ_FILE}", file=sys.stderr)
        return 1
    cmd = [sys.executable, "-m", "pip_audit", "-r", str(REQ_FILE)]
    result = subprocess.run(cmd, cwd=PROJECT_ROOT, text=True, capture_output=True)
    if result.stdout:
        print(result.stdout, end="")
    if result.stderr:
        print(result.stderr, end="", file=sys.stderr)
    combined = f"{result.stdout}\n{result.stderr}".lower()
    if "no module named pip_audit" in combined or "no module named pip-audit" in combined:
        print("\npip-audit is not installed in this environment.", file=sys.stderr)
        print("Install it in a dev/release environment with:", file=sys.stderr)
        print("  python -m pip install pip-audit", file=sys.stderr)
        print("Then run:", file=sys.stderr)
        print("  python scripts/run_pip_audit.py", file=sys.stderr)
        return 2
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
