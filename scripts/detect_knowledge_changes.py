from __future__ import annotations

import argparse
import json
import os
from pathlib import Path


def load_manifest(path: Path) -> dict | None:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def canonical_manifest(manifest: dict | None) -> list[dict]:
    if not manifest:
        return []
    files = manifest.get("files", [])
    normalized = []
    for item in files:
        if not isinstance(item, dict):
            continue
        normalized.append(
            {
                "drive_item_id": item.get("drive_item_id") or "",
                "name": item.get("name") or "",
                "relative_path": item.get("relative_path") or "",
                "size": item.get("size"),
                "lastModifiedDateTime": item.get("lastModifiedDateTime") or "",
                "eTag": item.get("eTag") or "",
                "cTag": item.get("cTag") or "",
                "sha256": item.get("sha256") or "",
            }
        )
    normalized.sort(key=lambda item: (item["relative_path"], item["drive_item_id"], item["name"]))
    return normalized


def write_github_output(values: dict[str, str]) -> None:
    output_path = os.getenv("GITHUB_OUTPUT")
    if not output_path:
        return
    with open(output_path, "a", encoding="utf-8") as handle:
        for key, value in values.items():
            handle.write(f"{key}={value}\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Compare SharePoint knowledge manifests.")
    parser.add_argument("--current", default="knowledge_manifest.json")
    parser.add_argument("--previous", default="last_deployed_manifest.json")
    args = parser.parse_args()

    current = load_manifest(Path(args.current))
    previous = load_manifest(Path(args.previous))
    current_files = canonical_manifest(current)
    previous_files = canonical_manifest(previous)
    changed = current_files != previous_files

    if previous is None:
        reason = "previous manifest missing"
    elif changed:
        reason = "SharePoint manifest changed"
    else:
        reason = "SharePoint manifest unchanged"

    print(f"knowledge_changed={str(changed).lower()}")
    print(f"change_reason={reason}")
    print(f"current_files={len(current_files)}")
    print(f"previous_files={len(previous_files)}")
    write_github_output(
        {
            "knowledge_changed": str(changed).lower(),
            "change_reason": reason,
            "current_files": str(len(current_files)),
            "previous_files": str(len(previous_files)),
        }
    )


if __name__ == "__main__":
    main()
