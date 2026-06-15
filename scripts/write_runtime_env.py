from __future__ import annotations

import os
from pathlib import Path

RUNTIME_ENV_NAMES = [
    "AI_PLATFORM_API_KEY",
    "AI_PLATFORM_BASE_URL",
    "AI_PLATFORM_MODEL",
    "PAPERS_DIR",
    "VECTOR_DB_DIR",
    "EMBEDDING_MODEL",
    "CHUNK_SIZE",
    "CHUNK_OVERLAP",
    "SEMANTIC_CHUNKING_ENABLED",
    "SEMANTIC_CHUNK_MIN_CHARS",
    "SEMANTIC_CHUNK_MAX_CHARS",
    "SEMANTIC_CHUNK_SIMILARITY_THRESHOLD",
    "RETRIEVAL_K",
    "RETRIEVAL_FETCH_K",
    "MIN_RELEVANCE_SCORE",
    "MAX_TOKENS",
    "MAX_CONTEXT_CHARS",
    "SHOW_USAGE",
    "DEBUG_RETRIEVAL",
    "ANSWER_LANGUAGE",
    "TEAMS_BOT_APP_ID",
    "TEAMS_BOT_APP_PASSWORD",
    "TEAMS_BOT_HOST",
    "TEAMS_BOT_PORT",
    "PORT",
    "MS_TENANT_ID",
    "MICROSOFT_APP_ID",
    "MICROSOFT_APP_PASSWORD",
    "MICROSOFT_APP_TYPE",
    "MICROSOFT_APP_TENANT_ID",
    "ENABLE_AGENTBASE_MEMORY",
    "MEMORY_ID",
    "MEMORY_STRATEGY_ID",
    "MEMORY_ACTOR_ID",
    "MEMORY_SEARCH_LIMIT",
    "MEMORY_MAX_CONTEXT_CHARS",
]


def main() -> None:
    output = Path(os.getenv("RUNTIME_ENV_OUTPUT", ".agentbase/runtime.env"))
    output.parent.mkdir(parents=True, exist_ok=True)
    lines = []
    for name in RUNTIME_ENV_NAMES:
        value = os.getenv(name)
        if value is None:
            continue
        lines.append(f"{name}={value}")
    output.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Runtime environment file written: {output}")
    print(f"Runtime variables included: {len(lines)}")


if __name__ == "__main__":
    main()
