from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.request


def get_json(url: str, timeout: int = 30) -> dict:
    with urllib.request.urlopen(url, timeout=timeout) as response:
        body = response.read().decode("utf-8")
        return json.loads(body)


def post_json(url: str, payload: dict, timeout: int = 180) -> dict:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        body = response.read().decode("utf-8")
        return json.loads(body)


def assert_true(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> None:
    parser = argparse.ArgumentParser(description="Verify deployed SecureMind RAG endpoint.")
    parser.add_argument("--base-url", required=True)
    args = parser.parse_args()

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    base_url = args.base_url.rstrip("/")
    last_error = None
    for _ in range(24):
        try:
            health = get_json(f"{base_url}/health")
            assert_true(health.get("status") == "ok", "health status is not ok")
            break
        except Exception as exc:  # noqa: BLE001 - CI verifier should retry broadly.
            last_error = exc
            time.sleep(5)
    else:
        raise RuntimeError(f"Health check failed: {last_error}")

    count = get_json(f"{base_url}/documents/count")
    assert_true(int(count.get("total_documents", 0)) > 0, "documents count is empty")

    catalog_count = post_json(
        f"{base_url}/chat",
        {"question": "có tất cả bao nhiêu document trong AI Agent này?", "debug": True},
    )
    count_meta = catalog_count.get("metadata", {})
    assert_true(count_meta.get("answer_type") == "catalog", "catalog count did not route to catalog")
    assert_true(count_meta.get("retrieval_used") is False, "catalog count used retrieval")
    assert_true(count_meta.get("llm_used") is False, "catalog count used LLM")
    assert_true(catalog_count.get("sources") == [], "catalog count returned sources")

    catalog_list = post_json(
        f"{base_url}/chat",
        {
            "question": "kể tên tất cả tài liệu đó ra",
            "history": [
                {"role": "user", "content": "có tất cả bao nhiêu document trong AI Agent này?"},
                {"role": "assistant", "content": catalog_count.get("answer", "")},
            ],
            "debug": True,
        },
    )
    list_meta = catalog_list.get("metadata", {})
    assert_true(list_meta.get("catalog_intent") == "list", "catalog list did not route to catalog list")
    assert_true(list_meta.get("retrieval_used") is False, "catalog list used retrieval")
    assert_true(list_meta.get("llm_used") is False, "catalog list used LLM")

    scope = post_json(
        f"{base_url}/chat",
        {"question": "can you tell me scope of ZION-QT-08", "debug": True},
    )
    scope_meta = scope.get("metadata", {})
    assert_true(scope_meta.get("answer_type") == "rag", "scope did not route to RAG")
    assert_true(scope_meta.get("retrieval_used") is True, "scope retrieval flag missing")
    assert_true(scope_meta.get("llm_used") is True, "scope LLM flag missing")
    assert_true(bool(scope.get("sources")), "scope sources missing")

    password = post_json(
        f"{base_url}/chat",
        {"question": "password policy requirements là gì?", "debug": True},
    )
    password_meta = password.get("metadata", {})
    assert_true(password_meta.get("answer_type") == "rag", "password did not route to RAG")
    assert_true(bool(password.get("sources")), "password sources missing")

    print("Production verification passed.")
    print(f"Document count: {count.get('total_documents')}")


if __name__ == "__main__":
    main()
