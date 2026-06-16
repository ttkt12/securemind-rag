from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile


ROOT = Path(__file__).resolve().parents[1]
# teams_app/ carries the real deployment values, so the bare command produces an
# uploadable package. teams/ stays as a parametric template (use --bot-id/--domain).
DEFAULT_SOURCE = ROOT / "teams_app"
DEFAULT_OUTPUT = ROOT / "securemind-rag-teams-app.zip"

PLACEHOLDER_GUID = "00000000-0000-0000-0000-000000000000"
GUID_RE = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)


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


def _is_real_guid(value: str) -> bool:
    return bool(GUID_RE.match(value)) and value != PLACEHOLDER_GUID


def validate_manifest_values(manifest: dict) -> None:
    """Reject a manifest that would be rejected by the Teams upload validator.

    Catches the common failure mode: packaging a template whose id/botId/domain
    are still placeholders, which Teams refuses without a clear reason.
    """
    problems = []

    app_id = str(manifest.get("id", "")).strip()
    if not _is_real_guid(app_id):
        problems.append(
            f"manifest 'id' is not a real GUID (got {app_id or 'empty'!r}). "
            "Pass --bot-id, or build from a folder with real values."
        )

    bot_ids = [str(bot.get("botId", "")).strip() for bot in manifest.get("bots", [])]
    for bot_id in bot_ids:
        if not _is_real_guid(bot_id):
            problems.append(
                f"bots[].botId is not a real GUID (got {bot_id or 'empty'!r}). "
                "Pass --bot-id, or build from a folder with real values."
            )

    for domain in manifest.get("validDomains", []):
        clean = str(domain).strip()
        if not clean or "REPLACE" in clean.upper() or "://" in clean:
            problems.append(
                f"validDomains entry is invalid (got {clean or 'empty'!r}). "
                "Use the runtime hostname without https://, e.g. via --domain."
            )

    developer = manifest.get("developer", {})
    for key in ("websiteUrl", "privacyUrl", "termsOfUseUrl"):
        url = str(developer.get(key, "")).strip()
        if "REPLACE" in url.upper():
            problems.append(f"developer.{key} still contains a placeholder (got {url!r}).")

    if problems:
        raise ValueError(
            "Teams manifest is not ready to package:\n  - " + "\n  - ".join(problems)
        )

    # Non-fatal: Teams recommends (and this project's convention is) id == botId.
    if bot_ids and app_id not in bot_ids:
        print(
            f"Warning: manifest id ({app_id}) differs from botId ({bot_ids[0]}). "
            "Teams permits this, but the project convention uses the same GUID."
        )


def build_package(source_dir: Path, output_path: Path, bot_id: str = "", domain: str = "") -> None:
    validate_package_inputs(source_dir)
    manifest = load_manifest(source_dir / "manifest.json")
    manifest = replace_placeholders(manifest, bot_id=bot_id, domain=domain)
    validate_manifest_values(manifest)

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

    try:
        build_package(args.source, args.output, bot_id=args.bot_id, domain=args.domain)
    except (ValueError, FileNotFoundError) as error:
        print(f"Error: {error}")
        return 1
    print(f"Teams package written: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
