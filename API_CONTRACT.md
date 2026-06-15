# Backend API Contract

SecureMind RAG is served by `teams_bot.py` using `aiohttp`. The backend exposes the browser UI, JSON chat API, document catalog metadata, health check, and Microsoft Teams Bot Framework endpoint.

Base URL:

```text
https://endpoint-77ada21e-9fec-4ea0-96ff-f9f6e79fbe1a.agentbase-runtime.aiplatform.vngcloud.vn
```

## Endpoint Summary

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/` | SecureMind web chat UI. |
| `GET` | `/health` | Runtime health check. |
| `POST` | `/chat` | Chat API for RAG and catalog-aware answers. |
| `GET` | `/documents/count` | Safe document catalog count. |
| `GET` | `/documents` | Safe document catalog list. |
| `POST` | `/api/messages` | Microsoft Teams / Bot Framework endpoint. |

## `GET /health`

Response:

```json
{"status": "ok"}
```

Example:

```bash
curl "https://endpoint-77ada21e-9fec-4ea0-96ff-f9f6e79fbe1a.agentbase-runtime.aiplatform.vngcloud.vn/health"
```

## `GET /`

Purpose: serves the SecureMind RAG web UI.

Response body: `text/html`

## `POST /chat`

Purpose: answers user questions. Normal content questions use RAG over retrieved document chunks. Corpus/catalog questions such as document count or document list are answered from `document_catalog.json` metadata.

Headers:

```text
Content-Type: application/json
```

Request:

```json
{
  "question": "can you tell me scope of ZION-QT-08"
}
```

Optional session-aware request:

```json
{
  "question": "what about the scope?",
  "session_id": "local-browser-session-id",
  "history": [
    {"role": "user", "content": "can you tell me about ZION-QT-08"},
    {"role": "assistant", "content": "ZION-QT-08 is ..."}
  ]
}
```

Optional debug request:

```json
{
  "question": "quy dinh ve mat khau la gi?",
  "debug": true
}
```

RAG response:

```json
{
  "answer": "Theo ZION-QT-08, pham vi ap dung bao gom ...",
  "sources": [
    {
      "filename": "source-file.pdf",
      "page": 5,
      "label": "source-file.pdf page 5"
    }
  ],
  "session_id": null,
  "answer_type": "rag",
  "metadata": {
    "answer_type": "rag"
  }
}
```

Catalog response:

```json
{
  "answer": "Hien tai AI Agent nay co 52 tai lieu duy nhat trong document catalog.",
  "sources": [],
  "session_id": null,
  "answer_type": "catalog",
  "metadata": {
    "answer_type": "catalog",
    "question_type": "count",
    "total_documents": 52,
    "documents": [
      {
        "code": "ZION-QT-08",
        "title": "Quy Trinh Quan Ly Hoat Dong Kinh Doanh Lien Tuc",
        "filename": "ZION-QT-08 - Quy Trinh Quan Ly Hoat Dong Kinh Doanh Lien Tuc.pdf",
        "page_count": 12,
        "chunk_count": 18
      }
    ]
  }
}
```

Debug response extension:

When `debug` is `true`, the response may include safe retrieval and context
budget metadata. It must not include API keys, secrets, raw environment values,
raw prompts, or full confidential document chunks.

```json
{
  "debug": {
    "model_name": "configured-model-name",
    "retrieval_k": 6,
    "max_context_chars": 8000,
    "context_budget": {
      "max_chars": 8000,
      "used_chars": 5360,
      "estimated_tokens": 1420,
      "included_chunks": 4,
      "skipped_duplicates": 0,
      "skipped_empty": 0,
      "sources": [
        {
          "label": "ZION-QT-08.pdf page 2",
          "filename": "ZION-QT-08.pdf",
          "page": 2,
          "document_code": "ZION-QT-08",
          "char_count": 1320,
          "estimated_tokens": 350
        }
      ]
    }
  }
}
```

Error responses:

```json
{"error": "Content-Type must be application/json."}
```

```json
{"error": "Invalid JSON body."}
```

```json
{"error": "Question is required."}
```

Frontend notes:

- Render `answer` as sanitized text/Markdown-like formatting.
- Show source cards only when `answer_type` is `rag` and `sources` is non-empty.
- For `answer_type: "catalog"`, show a small "Document catalog" label and do not show source cards.
- Do not send API keys, passwords, or secrets in chat requests.

## `GET /documents/count`

Purpose: returns the total number of unique documents known to the document catalog.

Response:

```json
{
  "total_documents": 52
}
```

## `GET /documents`

Purpose: returns a safe document catalog list without local absolute paths or secrets.

Response:

```json
{
  "total_documents": 52,
  "documents": [
    {
      "code": "ZION-QT-08",
      "title": "Quy Trinh Quan Ly Hoat Dong Kinh Doanh Lien Tuc",
      "filename": "ZION-QT-08 - Quy Trinh Quan Ly Hoat Dong Kinh Doanh Lien Tuc.pdf",
      "page_count": 12,
      "chunk_count": 18
    }
  ]
}
```

## `POST /api/messages`

Purpose: receives Microsoft Teams / Bot Framework activity payloads.

Teams and Bot Framework should POST message activities to:

```text
https://endpoint-77ada21e-9fec-4ea0-96ff-f9f6e79fbe1a.agentbase-runtime.aiplatform.vngcloud.vn/api/messages
```

Do not call this endpoint from the browser UI. A direct `GET /api/messages` returns `405 Method Not Allowed`, which is expected.
