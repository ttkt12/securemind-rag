from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_sync_manifest(download_dir: Path) -> dict:
    manifest_path = download_dir / "sharepoint_manifest.json"
    if not manifest_path.exists():
        return {"files": []}
    return json.loads(manifest_path.read_text(encoding="utf-8"))


def normalize_entry(entry: dict, download_dir: Path, include_hash: bool = True) -> dict:
    local_path = Path(entry.get("local_path") or "")
    if not local_path.is_absolute():
        local_path = Path(local_path)
    if not local_path.exists() and not local_path.is_absolute():
        local_path = download_dir / local_path

    try:
        relative_path = local_path.relative_to(download_dir).as_posix()
    except ValueError:
        relative_path = Path(entry.get("relative_path") or entry.get("name") or local_path.name).as_posix()

    normalized = {
        "drive_item_id": entry.get("drive_item_id") or entry.get("sharepoint_item_id") or "",
        "name": entry.get("name") or local_path.name,
        "relative_path": relative_path,
        "size": entry.get("size"),
        "lastModifiedDateTime": entry.get("lastModifiedDateTime")
        or entry.get("last_modified_datetime")
        or "",
        "eTag": entry.get("eTag") or "",
        "cTag": entry.get("cTag") or "",
        "webUrl": entry.get("webUrl") or entry.get("web_url") or "",
    }
    if include_hash and local_path.exists() and local_path.is_file():
        normalized["sha256"] = sha256_file(local_path)
    else:
        normalized["sha256"] = ""
    return normalized


def build_manifest(download_dir: Path, include_hash: bool = True) -> dict:
    sync_manifest = load_sync_manifest(download_dir)
    entries = [
        normalize_entry(entry, download_dir, include_hash=include_hash)
        for entry in sync_manifest.get("files", [])
        if isinstance(entry, dict)
    ]
    entries.sort(key=lambda item: (item.get("relative_path", ""), item.get("drive_item_id", "")))
    return {"schema_version": 1, "source": "sharepoint", "files": entries}


def main() -> None:
    parser = argparse.ArgumentParser(description="Build deterministic SharePoint knowledge manifest.")
    parser.add_argument("--download-dir", default="sharepoint_downloads")
    parser.add_argument("--output", default="knowledge_manifest.json")
    parser.add_argument("--no-hash", action="store_true", help="Skip sha256 file hashing.")
    args = parser.parse_args()

    download_dir = Path(args.download_dir)
    manifest = build_manifest(download_dir, include_hash=not args.no_hash)
    Path(args.output).write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Manifest files: {len(manifest['files'])}")
    print(f"Manifest saved: {args.output}")


if __name__ == "__main__":
    main()
