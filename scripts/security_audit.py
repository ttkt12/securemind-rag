from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

SENSITIVE_TRACKED_PATHS = {
    ".env",
    ".env.local",
    ".env.production",
    ".agentbase/runtime.env",
    ".greennode.json",
    "token_cache.bin",
}

SENSITIVE_TRACKED_PREFIXES = (
    "sharepoint_downloads/",
    "vector_db/",
)

ALLOWLISTED_TRACKED_PATHS = {
    ".env.example",
    "papers/.gitkeep",
}

SECRET_PATTERNS = {
    "private_key": re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    "openai_key": re.compile(r"\bsk-[A-Za-z0-9_-]{32,}\b"),
    "github_token": re.compile(r"\bgh[pousr]_[A-Za-z0-9_]{30,}\b"),
    "jwt": re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b"),
}

ASSIGNMENT_RE = re.compile(
    r"^\s*(?:export\s+)?"
    r"([A-Z0-9_]*(?:API_KEY|TOKEN|PASSWORD|SECRET|CLIENT_SECRET)[A-Z0-9_]*)"
    r"\s*=\s*['\"]?([^'\"\s#]+)"
)

PLACEHOLDER_PREFIXES = (
    "your_",
    "example",
    "placeholder",
    "replace_",
    "changeme",
    "none",
    "null",
    "false",
    "true",
)


def git_tracked_files() -> list[str]:
    output = subprocess.check_output(["git", "ls-files"], text=True)
    return [line.strip().replace("\\", "/") for line in output.splitlines() if line.strip()]


def is_sensitive_tracked_path(path: str) -> bool:
    if path in ALLOWLISTED_TRACKED_PATHS:
        return False
    if path in SENSITIVE_TRACKED_PATHS:
        return True
    return any(path.startswith(prefix) for prefix in SENSITIVE_TRACKED_PREFIXES)


def looks_like_real_assignment_secret(line: str) -> bool:
    match = ASSIGNMENT_RE.match(line)
    if not match:
        return False
    value = match.group(2).strip()
    if len(value) < 16:
        return False
    lowered = value.lower()
    if lowered.startswith(PLACEHOLDER_PREFIXES):
        return False
    if "$" in value or "{" in value or "}" in value:
        return False
    return True


def scan_text_file(path: Path) -> list[str]:
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return []

    hits: list[str] = []
    for label, pattern in SECRET_PATTERNS.items():
        if pattern.search(text):
            hits.append(label)

    if not str(path).replace("\\", "/").startswith(".agents/skills/"):
        for line in text.splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            if looks_like_real_assignment_secret(stripped):
                hits.append("secret_assignment")
                break

    return sorted(set(hits))


def main() -> int:
    tracked_files = git_tracked_files()
    failures: list[str] = []

    for path in tracked_files:
        if is_sensitive_tracked_path(path):
            failures.append(f"{path}: sensitive file should not be tracked")

    for path in tracked_files:
        if path in ALLOWLISTED_TRACKED_PATHS or is_sensitive_tracked_path(path):
            continue
        hits = scan_text_file(Path(path))
        for hit in hits:
            failures.append(f"{path}: potential {hit}")

    if failures:
        print("Security audit failed. Potential sensitive content was found:")
        for item in failures:
            print(f"- {item}")
        print("No secret values were printed. Remove tracked secrets or replace them with placeholders.")
        return 1

    print("Security audit passed. No tracked secrets or sensitive generated artifacts were detected.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
