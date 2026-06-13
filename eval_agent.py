from __future__ import annotations

import json
import sys
from pathlib import Path

from document_intelligence import (
    catalog_document_label,
    find_catalog_candidates,
    load_document_catalog,
)
from rag_core import (
    analyze_question,
    answer_question,
    document_source_name,
    format_retrieval_score,
    load_vector_store,
    make_client,
)


TEST_QUESTIONS_PATH = Path("test_questions.json")


def configure_stdout() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")


def load_test_questions() -> list[dict]:
    if not TEST_QUESTIONS_PATH.exists():
        raise FileNotFoundError(f"Cannot find {TEST_QUESTIONS_PATH}")

    return json.loads(TEST_QUESTIONS_PATH.read_text(encoding="utf-8"))


def format_sources(documents: list) -> list[str]:
    seen = set()
    sources = []
    for document in documents:
        source = document_source_name(document)
        page = document.metadata.get("page")
        key = (source, page)
        if key in seen:
            continue
        seen.add(key)

        page_label = f" page {page + 1}" if isinstance(page, int) else ""
        score = format_retrieval_score(document)
        score_label = f" | score: {score}" if score else ""
        sources.append(f"{source}{page_label}{score_label}")

    return sources


def main() -> None:
    configure_stdout()
    questions = load_test_questions()
    catalog = load_document_catalog()
    vector_store = load_vector_store()
    client = make_client()

    for index, item in enumerate(questions, start=1):
        question = item["question"]
        expected_behavior = item.get("expected_behavior", "Manual review required.")
        analysis = analyze_question(question)
        detected_intent = analysis.intent
        if analysis.operational_intents:
            detected_intent += f" ({', '.join(analysis.operational_intents)})"
        candidate_documents = find_catalog_candidates(question, catalog, limit=5) if catalog else []

        print("=" * 80)
        print(f"Question {index}: {question}")
        print(f"Detected intent: {detected_intent}")
        print(
            "Detected process area: "
            + (", ".join(analysis.process_areas) if analysis.process_areas else "unknown")
        )
        print("Candidate documents from catalog:")
        if candidate_documents:
            for candidate in candidate_documents:
                area = candidate.get("process_area", "unknown")
                score = candidate.get("catalog_score", 0)
                print(f"- {catalog_document_label(candidate)} | area: {area} | catalog score: {score}")
        else:
            print("- none")
        print(f"Manual review note: {expected_behavior}")

        answer, documents, _usage = answer_question(question, vector_store, client)
        print("\nAnswer:")
        print(answer)

        sources = format_sources(documents)
        print("\nSources:")
        if sources:
            for source in sources:
                print(f"- {source}")
        else:
            print("- none")
        print()


if __name__ == "__main__":
    main()
