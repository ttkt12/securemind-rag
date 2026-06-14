# UI Requirements

This document describes the first web UI version for SecureMind RAG. Do not build the frontend until this contract is accepted.

## Product Goal

Create a focused chat interface for querying ISMS, security, compliance, policy, procedure, standard, and governance documents. The UI should feel like an internal enterprise assistant: clear, fast, readable, and source-aware.

## Primary Screen

The first screen is the chat experience. Do not make a marketing landing page.

Required regions:

* Header with product name: `SecureMind RAG`.
* Main scrollable conversation area.
* Empty state before the first question.
* Composer area with text input and send button.
* Answer bubble with optional sources.
* Error message state.

## Empty State

When no conversation exists, show a concise prompt such as:

```text
Ask about an ISMS, policy, procedure, or security document.
```

Optional example prompts:

* `can you tell me scope of ZION-QT-08`
* `which document should I check for access request?`
* `who approves this procedure?`

Do not show long feature descriptions.

## Chat Screen

Conversation layout:

* User messages aligned to the right or visually distinguished.
* Assistant answers aligned to the left or visually distinguished.
* Preserve line breaks and bullet lists from the backend answer.
* Keep content width readable on desktop.
* Use responsive layout on mobile.

## Input Box

Requirements:

* Multi-line text input.
* Placeholder: `Ask about a security, compliance, ISMS, policy, or procedure document`.
* Submit on send button.
* Optional keyboard behavior: Enter sends, Shift+Enter inserts a line break.
* Disable send when input is empty or whitespace-only.

## Send Button

Requirements:

* Clear primary action.
* Disabled while request is loading.
* Should not resize when state changes.
* Label can be `Send`; icon button is also acceptable if accessible.

## Loading State

While waiting for `POST /chat`:

* Add the user message immediately.
* Show an assistant loading bubble.
* Disable the send button.
* Keep the input available or disabled based on implementation preference, but avoid duplicate submissions.

Loading copy:

```text
Searching documents...
```

## Answer Bubble

Display `response.answer`.

Requirements:

* Preserve newlines.
* Support bullet-like text.
* Allow long answers to wrap.
* Do not show chain-of-thought or internal reasoning.
* Do not show raw debug metadata.

## Sources Display

If `response.sources` is non-empty:

* Show a compact `Sources` section under the answer bubble.
* Render each source as one line.
* Use smaller, muted text.
* Do not block the answer if sources are missing.

Example:

```text
Sources
ZION-QT-08.pdf page 5
ZION-QT-08.pdf page 4
```

## Error Message

Show a friendly error when `/chat` returns non-2xx, invalid JSON, or a network timeout.

Suggested copy:

```text
I could not get an answer right now. Please try again.
```

If backend returns an `error` field, show it only if it is user-safe. Do not show stack traces or raw HTML.

## Accessibility

Minimum requirements:

* Text input has an accessible label.
* Send button has accessible name.
* Loading state is announced or visible.
* Color contrast is readable.
* Focus remains predictable after sending.

## Frontend Data Model

Suggested message shape:

```ts
type ChatMessage = {
  id: string;
  role: "user" | "assistant";
  content: string;
  sources?: string[];
  status?: "loading" | "sent" | "error";
};
```

## Non-Goals For First Version

Do not include these yet:

* Authentication UI.
* File upload.
* SharePoint sync controls.
* Ingestion controls.
* Admin dashboard.
* Teams configuration UI.
* Memory management UI.
