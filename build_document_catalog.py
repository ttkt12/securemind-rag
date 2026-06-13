from __future__ import annotations

from collections import Counter
import sys

from document_intelligence import CATALOG_PATH, build_document_catalog, save_document_catalog


def configure_stdout() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")


def main() -> None:
    configure_stdout()
    catalog = build_document_catalog()
    save_document_catalog(catalog, CATALOG_PATH)
    process_counts = Counter(entry.get("process_area", "unknown") for entry in catalog)

    print(f"Documents cataloged: {len(catalog)}")
    print(f"Catalog saved: {CATALOG_PATH}")
    print("Process areas detected:")
    for area, count in sorted(process_counts.items()):
        print(f"- {area}: {count}")


if __name__ == "__main__":
    main()
