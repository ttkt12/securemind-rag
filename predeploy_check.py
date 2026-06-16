from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


@dataclass
class CheckResult:
    status: str
    name: str
    detail: str


def env_is_configured(name: str) -> bool:
    value = os.getenv(name, "").strip()
    return bool(value and not value.startswith("your_"))


def add_result(results: list[CheckResult], status: str, name: str, detail: str) -> None:
    results.append(CheckResult(status=status, name=name, detail=detail))


def print_summary(results: list[CheckResult]) -> None:
    print("Pre-deployment readiness summary:")
    for result in results:
        print(f"{result.status}: {result.name} - {result.detail}")

    has_fail = any(result.status == "FAIL" for result in results)
    has_warn = any(result.status == "WARN" for result in results)
    if has_fail:
        print("Overall: FAIL")
    elif has_warn:
        print("Overall: WARN")
    else:
        print("Overall: PASS")


def main() -> int:
    load_dotenv()
    results: list[CheckResult] = []

    if env_is_configured("AI_PLATFORM_API_KEY"):
        add_result(results, "PASS", "AI_PLATFORM_API_KEY", "configured")
    else:
        add_result(results, "FAIL", "AI_PLATFORM_API_KEY", "missing")

    # Match teams_bot's credential resolution: MICROSOFT_APP_* is preferred, with
    # TEAMS_BOT_* / MS_* accepted as aliases. Checking only TEAMS_BOT_* gave a
    # false FAIL when the bot is configured via MICROSOFT_APP_*.
    bot_credentials = {
        "bot app id": ("MICROSOFT_APP_ID", "TEAMS_BOT_APP_ID", "MS_CLIENT_ID"),
        "bot app password": ("MICROSOFT_APP_PASSWORD", "TEAMS_BOT_APP_PASSWORD", "MS_CLIENT_SECRET"),
    }
    for label, names in bot_credentials.items():
        if any(env_is_configured(name) for name in names):
            add_result(results, "PASS", label, "configured")
        else:
            add_result(results, "FAIL", label, f"set one of: {', '.join(names)}")

    vector_dir = Path(os.getenv("VECTOR_DB_DIR", "vector_db"))
    index_file = vector_dir / "index.faiss"
    metadata_file = vector_dir / "index.pkl"
    vector_ready = index_file.exists() and metadata_file.exists()
    if vector_ready:
        add_result(results, "PASS", "vector_db", "index files found")
    else:
        add_result(
            results,
            "FAIL",
            "vector_db",
            "missing index.faiss or index.pkl; run python3 ingest.py first",
        )

    catalog_path = Path("document_catalog.json")
    catalog_total = None
    if catalog_path.exists():
        try:
            payload = json.loads(catalog_path.read_text(encoding="utf-8"))
            if isinstance(payload, dict):
                items = payload.get("documents") or payload.get("items") or payload.get("catalog") or []
            else:
                items = payload
            catalog_total = len([item for item in items if isinstance(item, dict)])
        except (OSError, json.JSONDecodeError):
            catalog_total = None
    min_docs = int(os.getenv("PREDEPLOY_MIN_CATALOG_DOCS", "1"))
    if catalog_total is None:
        add_result(
            results,
            "FAIL",
            "document_catalog.json",
            "missing or unreadable; run python build_document_catalog.py first",
        )
    elif catalog_total < min_docs:
        add_result(
            results,
            "FAIL",
            "document_catalog.json",
            f"only {catalog_total} documents (expected >= {min_docs}); rebuild the catalog",
        )
    else:
        add_result(results, "PASS", "document_catalog.json", f"{catalog_total} documents")

    try:
        import rag_core

        add_result(results, "PASS", "rag_core import", "ok")
    except Exception as exc:
        add_result(results, "FAIL", "rag_core import", exc.__class__.__name__)
        print_summary(results)
        return 1

    vector_store = None
    if vector_ready:
        try:
            vector_store = rag_core.load_vector_store()
            add_result(results, "PASS", "vector store load", "ok")
        except Exception as exc:
            add_result(results, "FAIL", "vector store load", exc.__class__.__name__)

    client = None
    if env_is_configured("AI_PLATFORM_API_KEY"):
        try:
            client = rag_core.make_client()
            add_result(results, "PASS", "LLM client", "created")
        except Exception as exc:
            add_result(results, "FAIL", "LLM client", exc.__class__.__name__)
    else:
        add_result(results, "WARN", "RAG health question", "skipped because API key is missing")

    if vector_store is not None and client is not None:
        try:
            answer, _sources, _usage = rag_core.answer_question("health check", vector_store, client)
            if answer:
                add_result(results, "PASS", "RAG health question", "completed")
            else:
                add_result(results, "WARN", "RAG health question", "completed with empty answer")
        except Exception as exc:
            add_result(results, "WARN", "RAG health question", exc.__class__.__name__)

    try:
        import teams_bot  # noqa: F401

        add_result(results, "PASS", "teams_bot import", "ok")
    except Exception as exc:
        add_result(results, "FAIL", "teams_bot import", exc.__class__.__name__)

    print_summary(results)
    return 1 if any(result.status == "FAIL" for result in results) else 0


if __name__ == "__main__":
    raise SystemExit(main())
