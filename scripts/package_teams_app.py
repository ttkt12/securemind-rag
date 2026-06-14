from __future__ import annotations

import argparse
import json
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE = ROOT / "teams"
DEFAULT_OUTPUT = ROOT / "securemind-rag-teams-template.zip"


def load_manifest(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def write_manifest(path: Path, manifest: dict) -> None:
    path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def replace_placeholders(manifest: dict, bot_id: str, domain: str) -> dict:
    if bot_id:
        manifest["id"] = bot_id
        for bot in manifest.get("bots", []):
            bot["botId"] = bot_id

    if domain:
        clean_domain = domain.removeprefix("https://").removeprefix("http://").rstrip("/")
        base_url = f"https://{clean_domain}"
        manifest["developer"]["websiteUrl"] = base_url
        manifest["developer"]["privacyUrl"] = base_url
        manifest["developer"]["termsOfUseUrl"] = base_url
        manifest["validDomains"] = [clean_domain]

    return manifest


def validate_package_inputs(source_dir: Path) -> None:
    required = ["manifest.json", "color.png", "outline.png"]
    missing = [name for name in required if not (source_dir / name).exists()]
    if missing:
        raise FileNotFoundError(f"Missing Teams package file(s): {', '.join(missing)}")

    load_manifest(source_dir / "manifest.json")


def build_package(source_dir: Path, output_path: Path, bot_id: str = "", domain: str = "") -> None:
    validate_package_inputs(source_dir)
    manifest = load_manifest(source_dir / "manifest.json")
    manifest = replace_placeholders(manifest, bot_id=bot_id, domain=domain)

    build_dir = source_dir / ".package_build"
    build_dir.mkdir(exist_ok=True)
    write_manifest(build_dir / "manifest.json", manifest)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(output_path, "w", ZIP_DEFLATED) as archive:
        archive.write(build_dir / "manifest.json", "manifest.json")
        archive.write(source_dir / "color.png", "color.png")
        archive.write(source_dir / "outline.png", "outline.png")


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the SecureMind RAG Teams app package.")
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--bot-id", default="", help="Microsoft Bot App ID to place in the manifest.")
    parser.add_argument(
        "--domain",
        default="",
        help="AgentBase runtime domain without path. https:// is accepted and removed for validDomains.",
    )
    args = parser.parse_args()

    build_package(args.source, args.output, bot_id=args.bot_id, domain=args.domain)
    print(f"Teams package written: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
