# Frontend Integration Guide

Use the backend `POST /chat` endpoint for the first custom web UI.

Current deployed backend:

```text
https://endpoint-77ada21e-9fec-4ea0-96ff-f9f6e79fbe1a.agentbase-runtime.aiplatform.vngcloud.vn
```

## Call `/chat`

Request:

```http
POST /chat
Content-Type: application/json
```

Body:

```json
{
  "question": "can you tell me scope of ZION-QT-08",
  "session_id": "optional-local-session-id",
  "history": [
    {"role": "user", "content": "previous question"},
    {"role": "assistant", "content": "previous answer"}
  ]
}
```

`session_id` and `history` are optional. The old payload with only `question` still works.

Response:

```json
{
  "answer": "Theo ZION-QT-08, ...",
  "sources": [
    {
      "filename": "ZION-QT-08.pdf",
      "page": 5,
      "label": "ZION-QT-08.pdf page 5"
    }
  ],
  "session_id": "optional-local-session-id"
}
```

## JavaScript Example

```js
const API_BASE_URL = "https://endpoint-77ada21e-9fec-4ea0-96ff-f9f6e79fbe1a.agentbase-runtime.aiplatform.vngcloud.vn";

export async function askSecureMind(question) {
  const response = await fetch(`${API_BASE_URL}/chat`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json"
    },
    body: JSON.stringify({ question })
  });

  const payload = await response.json().catch(() => ({}));

  if (!response.ok) {
    throw new Error(payload.error || "Chat request failed.");
  }

  return {
    answer: payload.answer || "",
    sources: Array.isArray(payload.sources) ? payload.sources : []
  };
}
```

For follow-up support, pass the current local session id and recent history:

```js
await fetch(`${API_BASE_URL}/chat`, {
  method: "POST",
  headers: {"Content-Type": "application/json"},
  body: JSON.stringify({
    question,
    session_id: activeSession.session_id,
    history: activeSession.messages.slice(-10).map(({role, content}) => ({role, content}))
  })
});
```

## Local Browser Sessions

The built-in web UI stores chat sessions in browser `localStorage`.

Session records contain:

* `session_id`
* `title`
* `created_at`
* `updated_at`
* local message history

The `New chat` button creates a fresh local session. Switching sessions reloads that session's local message history. The UI sends only recent messages to `/chat` so follow-up questions can refer to earlier turns without sending the entire conversation.

Do not store secrets, API keys, passwords, tokens, or confidential credentials in chat messages.

## UI Flow

1. User types a question.
2. Frontend appends the user message locally.
3. Frontend sends `POST /chat`.
4. For active sessions, frontend includes `session_id` and recent `history`.
5. Frontend shows loading state.
6. On success, frontend renders `answer` and optional `sources`.
7. On failure, frontend shows a friendly error bubble.

## Error Handling

Expected backend errors:

| Status | Meaning | Suggested UI response |
| --- | --- | --- |
| `400` | Invalid JSON or missing question. | Ask user to retry with a question. |
| `415` | Missing `Content-Type: application/json`. | Frontend bug; fix request headers. |
| `500` | Backend/RAG error. | Show friendly retry message. |
| Network error | Runtime unavailable or connectivity issue. | Show friendly retry message. |

## Health Check

Optional readiness check:

```js
const response = await fetch(`${API_BASE_URL}/health`);
const health = await response.json();
```

Expected:

```json
{
  "status": "ok"
}
```

## Do Not Use `/api/messages`

`POST /api/messages` is for Microsoft Teams / Bot Framework activities. A normal web frontend should not call it.

## Security Notes

* Do not place backend secrets in frontend code.
* Do not expose `.env` values.
* Do not send API keys, passwords, or tokens through `/chat`.
* Treat returned source names as internal document metadata.
