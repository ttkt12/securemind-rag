from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv

REQUIRED_CONFIG = (
    "PAPERS_DIR",
    "VECTOR_DB_DIR",
    "SHAREPOINT_DOWNLOAD_DIR",
    "MS_AUTH_FLOW",
    "SHAREPOINT_HOSTNAME",
    "SHAREPOINT_SITE_PATH",
    "SHAREPOINT_FOLDER_PATH",
)


def configured(value: str | None) -> bool:
    if value is None:
        return False
    value = value.strip().strip('"').strip("'").strip()
    return bool(value and not value.startswith("your_"))


def validate_config() -> None:
    missing = [name for name in REQUIRED_CONFIG if not configured(os.getenv(name))]
    print("Config validation:")
    for name in REQUIRED_CONFIG:
        print(f"- {name}: {'OK' if name not in missing else 'MISSING'}")
    if missing:
        raise RuntimeError("Missing required local refresh configuration. Update .env and try again.")


def run_step(label: str, command: list[str]) -> None:
    print(f"\n== {label} ==")
    result = subprocess.run(command, cwd=PROJECT_ROOT)
    if result.returncode != 0:
        print(f"\nERROR: Step failed: {label}")
        print(f"Exit code: {result.returncode}")
        print("Suggested next action: fix the error above, then rerun this refresh command.")
        raise SystemExit(result.returncode)


def safe_remove(path: Path) -> None:
    if not path.exists():
        return
    if path.is_dir():
        shutil.rmtree(path)
    else:
        path.unlink()


def confirm_clean(paths: list[Path], assume_yes: bool) -> None:
    existing = [path for path in paths if path.exists()]
    if not existing or assume_yes:
        return
    print("The following generated files/folders will be deleted before rebuild:")
    for path in existing:
        print(f"- {path.relative_to(PROJECT_ROOT)}")
    response = input("Continue? Type 'yes' to proceed: ").strip().lower()
    if response not in {"yes", "y"}:
        raise SystemExit("Clean cancelled.")


def catalog_count(path: Path) -> int | None:
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if isinstance(payload, list):
        return len([item for item in payload if isinstance(item, dict)])
    if isinstance(payload, dict):
        for key in ("documents", "items", "catalog"):
            value = payload.get(key)
            if isinstance(value, list):
                return len([item for item in value if isinstance(item, dict)])
    return None


def print_summary(sync_status: str, tests_passed: bool) -> None:
    vector_dir = PROJECT_ROOT / os.getenv("VECTOR_DB_DIR", "vector_db")
    catalog_path = PROJECT_ROOT / "document_catalog.json"
    count = catalog_count(catalog_path)

    print("\nLocal knowledge refresh summary:")
    print(f"- SharePoint sync: {sync_status}")
    print(f"- vector_db exists: {'yes' if vector_dir.exists() else 'no'}")
    print(f"- document_catalog.json exists: {'yes' if catalog_path.exists() else 'no'}")
    print(f"- catalog document count: {count if count is not None else 'unknown'}")
    print(f"- tests passed: {'yes' if tests_passed else 'skipped'}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Refresh SecureMind RAG local knowledge base.")
    parser.add_argument("--skip-sync", action="store_true", help="Skip SharePoint sync.")
    parser.add_argument("--skip-tests", action="store_true", help="Run sync/build steps only.")
    parser.add_argument("--clean", action="store_true", help="Delete vector_db and document_catalog.json first.")
    parser.add_argument("--catalog-only", action="store_true", help="Run only catalog build and catalog smoke test after ingest.")
    parser.add_argument("--yes", action="store_true", help="Do not prompt before deleting generated files with --clean.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    os.chdir(PROJECT_ROOT)
    load_dotenv(PROJECT_ROOT / ".env")
    validate_config()

    python = sys.executable
    vector_dir = PROJECT_ROOT / os.getenv("VECTOR_DB_DIR", "vector_db")
    catalog_path = PROJECT_ROOT / "document_catalog.json"

    if args.clean:
        clean_paths = [vector_dir, catalog_path]
        confirm_clean(clean_paths, args.yes)
        for path in clean_paths:
            safe_remove(path)

    sync_status = "skipped"
    tests_passed = False

    if not args.skip_sync:
        run_step("A. SharePoint sync", [python, "sharepoint_sync.py"])
        sync_status = "completed"

    run_step("B. Rebuild vector database", [python, "ingest.py"])
    run_step("C. Rebuild document catalog", [python, "build_document_catalog.py"])

    if not args.skip_tests:
        if args.catalog_only:
            run_step("E. Run catalog smoke test", [python, "scripts/ci_smoke_test.py", "--catalog-only"])
        else:
            run_step("D. Run security audit", [python, "scripts/security_audit.py"])
            run_step("E. Run catalog smoke test", [python, "scripts/ci_smoke_test.py", "--catalog-only"])
            run_step("F. Run full smoke test", [python, "scripts/ci_smoke_test.py"])
            run_step("G. Run golden regression test", [python, "scripts/golden_regression_test.py"])
        tests_passed = True

    print_summary(sync_status, tests_passed)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
