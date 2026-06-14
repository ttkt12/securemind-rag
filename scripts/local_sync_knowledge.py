from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def run_step(label: str, command: list[str]) -> None:
    print(f"\n== {label} ==")
    subprocess.run(command, cwd=PROJECT_ROOT, check=True)


def count_downloaded_files(download_dir: Path) -> int:
    if not download_dir.exists():
        return 0
    return sum(1 for path in download_dir.rglob("*") if path.is_file() and path.name != "sharepoint_manifest.json")


def catalog_count() -> int:
    from catalog_service import load_document_catalog

    return len(load_document_catalog())


def main() -> int:
    os.chdir(PROJECT_ROOT)
    load_dotenv(PROJECT_ROOT / ".env")
    os.environ["MS_AUTH_FLOW"] = "device_code"
    os.environ.setdefault("PAPERS_DIR", os.getenv("SHAREPOINT_DOWNLOAD_DIR", "sharepoint_downloads"))

    python = sys.executable
    download_dir = PROJECT_ROOT / os.getenv("SHAREPOINT_DOWNLOAD_DIR", "sharepoint_downloads")
    vector_dir = PROJECT_ROOT / os.getenv("VECTOR_DB_DIR", "vector_db")

    print("SecureMind local knowledge update")
    print("- SharePoint sync mode: device_code")
    print("- SharePoint sync is local-only; GitHub Actions does not access SharePoint.")

    run_step("Sync SharePoint documents locally", [python, "sharepoint_sync.py"])
    run_step("Rebuild FAISS vector database", [python, "ingest.py"])
    run_step("Rebuild document catalog", [python, "build_document_catalog.py"])
    run_step("Run catalog smoke test", [python, "scripts/ci_smoke_test.py", "--catalog-only"])

    print("\nLocal knowledge update complete.")
    print(f"- Documents in catalog: {catalog_count()}")
    print(f"- Downloaded files: {count_downloaded_files(download_dir)}")
    print(f"- Vector DB path: {vector_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
