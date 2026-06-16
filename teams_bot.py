from __future__ import annotations

import asyncio
import hmac
import os
import time
from pathlib import Path
from urllib.parse import urlparse

from aiohttp import web
from botbuilder.core import (
    ActivityHandler,
    BotFrameworkAdapter,
    BotFrameworkAdapterSettings,
    MessageFactory,
    TurnContext,
)
from botbuilder.schema import Activity, ActivityTypes
from dotenv import load_dotenv

from answer_engine import answer_chat
from catalog_service import catalog_count_payload, catalog_documents_payload, derive_code
from config import (
    AI_BASE_URL,
    AI_MODEL,
    APP_ACCESS_TOKEN,
    EMBEDDING_MODEL,
    MAX_CONTEXT_CHARS,
    REQUIRE_APP_ACCESS_TOKEN,
    RETRIEVAL_FETCH_K,
    RETRIEVAL_K,
    VECTOR_DB_DIR,
)
from rag_core import document_source_name, load_vector_store, make_client

STATIC_DIR = Path(__file__).resolve().parent / "static"

WEB_CHAT_HTML = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>SecureMind RAG</title>
  <style>
    :root {
      color-scheme: light;
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      color: #17202a;
      background: #eef2f6;
    }
    * {
      box-sizing: border-box;
    }
    body {
      margin: 0;
      min-height: 100vh;
      display: flex;
      flex-direction: column;
      background: #eef2f6;
    }
    header {
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 16px 24px;
      border-bottom: 1px solid #d8dee8;
      background: #ffffff;
    }
    h1 {
      margin: 0;
      font-size: 18px;
      font-weight: 700;
      letter-spacing: 0;
    }
    main {
      width: min(960px, 100%);
      margin: 0 auto;
      flex: 1;
      display: flex;
      flex-direction: column;
      padding: 24px;
      gap: 16px;
    }
    #messages {
      flex: 1;
      overflow-y: auto;
      display: flex;
      flex-direction: column;
      gap: 12px;
      padding-bottom: 8px;
    }
    .message {
      max-width: min(760px, 92%);
      padding: 12px 14px;
      border-radius: 8px;
      line-height: 1.5;
      white-space: pre-wrap;
      overflow-wrap: anywhere;
      border: 1px solid #d8dee8;
      background: #ffffff;
    }
    .user {
      align-self: flex-end;
      background: #dfeeff;
      border-color: #bdd8f5;
    }
    .bot {
      align-self: flex-start;
    }
    .sources {
      margin-top: 10px;
      color: #516071;
      font-size: 13px;
    }
    form {
      display: grid;
      grid-template-columns: 1fr auto;
      gap: 10px;
      padding: 12px;
      border: 1px solid #d8dee8;
      border-radius: 8px;
      background: #ffffff;
    }
    textarea {
      min-height: 52px;
      max-height: 150px;
      resize: vertical;
      border: 0;
      outline: 0;
      font: inherit;
      line-height: 1.4;
    }
    button {
      min-width: 84px;
      border: 0;
      border-radius: 8px;
      background: #146c5f;
      color: #ffffff;
      font: inherit;
      font-weight: 700;
      cursor: pointer;
    }
    button:disabled {
      cursor: wait;
      opacity: 0.62;
    }
    @media (max-width: 640px) {
      header,
      main {
        padding-left: 14px;
        padding-right: 14px;
      }
      form {
        grid-template-columns: 1fr;
      }
      button {
        height: 44px;
      }
    }
  </style>
</head>
<body>
  <header>
    <h1>SecureMind RAG</h1>
  </header>
  <main>
    <section id="messages" aria-live="polite"></section>
    <form id="chat-form">
      <textarea id="question" name="question" placeholder="Ask about an ISMS, policy, procedure, or security document" required></textarea>
      <button id="send" type="submit">Send</button>
    </form>
  </main>
  <script>
    const form = document.getElementById("chat-form");
    const input = document.getElementById("question");
    const button = document.getElementById("send");
    const messages = document.getElementById("messages");

    function appendMessage(text, className, sources) {
      const bubble = document.createElement("article");
      bubble.className = `message ${className}`;
      bubble.textContent = text;
      if (sources && sources.length) {
        const sourceList = document.createElement("div");
        sourceList.className = "sources";
        sourceList.textContent = `Sources: ${sources.join("; ")}`;
        bubble.appendChild(sourceList);
      }
      messages.appendChild(bubble);
      messages.scrollTop = messages.scrollHeight;
    }

    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      const question = input.value.trim();
      if (!question) return;

      appendMessage(question, "user");
      input.value = "";
      button.disabled = true;

      try {
        const response = await fetch("/chat", {
          method: "POST",
          headers: {"Content-Type": "application/json"},
          body: JSON.stringify({question})
        });
        const payload = await response.json();
        appendMessage(payload.answer || payload.error || "No response returned.", "bot", payload.sources || []);
      } catch (error) {
        appendMessage("The chat service could not be reached.", "bot");
      } finally {
        button.disabled = false;
        input.focus();
      }
    });
  </script>
</body>
</html>
"""

ERROR_MESSAGE = "Xin lỗi, bot gặp lỗi khi xử lý câu hỏi. Vui lòng thử lại hoặc liên hệ admin."

# Web API routes that require X-App-Access-Token when REQUIRE_APP_ACCESS_TOKEN=true.
# GET /, GET /health, static assets, and Teams /api/messages stay outside this set.
PROTECTED_API_PATHS = frozenset({"/chat", "/documents", "/documents/count"})


def access_token_matches(provided: str) -> bool:
    if not APP_ACCESS_TOKEN:
        return False
    return hmac.compare_digest(provided.strip(), APP_ACCESS_TOKEN)


@web.middleware
async def access_token_middleware(request: web.Request, handler):
    if REQUIRE_APP_ACCESS_TOKEN and request.path in PROTECTED_API_PATHS:
        provided = request.headers.get("X-App-Access-Token", "").strip()
        if not provided:
            return web.json_response(
                {"error": "Access token required. Set the X-App-Access-Token header."},
                status=401,
            )
        if not access_token_matches(provided):
            return web.json_response(
                {"error": "Invalid access token."},
                status=403,
            )
    return await handler(request)


def env_is_configured(name: str) -> bool:
    value = os.getenv(name, "").strip()
    return bool(value and not value.startswith("your_"))


def first_env(*names: str) -> str:
    for name in names:
        value = os.getenv(name, "").strip()
        if value:
            return value
    return ""


def teams_app_id() -> str:
    return first_env("MICROSOFT_APP_ID", "TEAMS_BOT_APP_ID", "MS_CLIENT_ID")


def teams_app_password() -> str:
    return first_env("MICROSOFT_APP_PASSWORD", "TEAMS_BOT_APP_PASSWORD", "MS_CLIENT_SECRET")


def teams_tenant_id() -> str:
    return first_env("MICROSOFT_APP_TENANT_ID", "MS_TENANT_ID")


def validate_startup_config() -> None:
    print("Teams bot config validation:")
    credential_checks = {
        "MICROSOFT_APP_ID or TEAMS_BOT_APP_ID": bool(teams_app_id()),
        "MICROSOFT_APP_PASSWORD or TEAMS_BOT_APP_PASSWORD": bool(teams_app_password()),
    }
    for label, configured in credential_checks.items():
        print(f"- {label}: {'OK' if configured else 'MISSING'}")

    index_file = VECTOR_DB_DIR / "index.faiss"
    metadata_file = VECTOR_DB_DIR / "index.pkl"
    if not index_file.exists() or not metadata_file.exists():
        raise RuntimeError(
            "Vector database not found. Run python3 ingest.py before starting "
            "the bot or provide vector_db in the deployment artifact."
        )

    if not all(credential_checks.values()):
        print("- Microsoft Teams endpoint: DISABLED until bot credentials are configured")

    if REQUIRE_APP_ACCESS_TOKEN:
        if APP_ACCESS_TOKEN:
            print("- Web API access token: ENFORCED on /chat, /documents, /documents/count")
        else:
            print(
                "- Web API access token: ENFORCED but APP_ACCESS_TOKEN is empty -> all "
                "protected requests will be rejected. Set APP_ACCESS_TOKEN."
            )
    else:
        print("- Web API access token: not enforced (REQUIRE_APP_ACCESS_TOKEN=false)")


def source_identity(source: str) -> str:
    """Canonical identity for a chunk's source, so duplicate file copies of the
    same document (e.g. a clean export and a "...Mac mini.pdf" copy) collapse to
    one entry via their shared document code."""
    return derive_code(source) or source


def source_label(source: str, page_number) -> str:
    base = derive_code(source) or source
    return f"{base} page {page_number}" if page_number is not None else base


def format_sources(sources: list, limit: int = 3) -> str:
    entries = []
    seen = set()
    for document in sources:
        if isinstance(document, dict):
            label = str(document.get("label") or document.get("filename") or "").strip()
            key = label
        else:
            source = document_source_name(document)
            page = document.metadata.get("page")
            page_number = page + 1 if isinstance(page, int) else None
            label = source_label(source, page_number)
            key = (source_identity(source), page_number)
        if not label or key in seen:
            continue
        seen.add(key)
        entries.append(label)
        if len(entries) >= limit:
            break

    if not entries:
        return ""

    return "\n\nNguồn:\n\n" + "\n".join(f"* {entry}" for entry in entries)


def clean_teams_message_text(turn_context: TurnContext) -> str:
    text = TurnContext.remove_recipient_mention(turn_context.activity) or turn_context.activity.text or ""
    text = text.replace("&nbsp;", " ")
    text = text.replace("\u00a0", " ")
    text = " ".join(text.split())
    return text.strip()


class SecureMindTeamsBot(ActivityHandler):
    def __init__(self, vector_store, client) -> None:
        self.vector_store = vector_store
        self.client = client

    async def on_message_activity(self, turn_context: TurnContext) -> None:
        user_text = clean_teams_message_text(turn_context)
        if not user_text:
            await turn_context.send_activity("Vui lòng nhập câu hỏi về tài liệu ISMS, bảo mật hoặc tuân thủ.")
            return

        started = time.perf_counter()
        answer_task = asyncio.ensure_future(
            asyncio.to_thread(answer_chat, user_text, self.vector_store, self.client)
        )

        # The LLM call can take a long time on a busy model endpoint. Keep a
        # typing indicator alive so the user sees the bot is working instead of
        # staring at silence (Teams typing indicators expire after a few seconds).
        try:
            while True:
                await turn_context.send_activity(Activity(type=ActivityTypes.typing))
                done, _ = await asyncio.wait({answer_task}, timeout=4.0)
                if done:
                    break
            result = answer_task.result()
        except Exception:
            answer_task.cancel()
            await turn_context.send_activity(ERROR_MESSAGE)
            return

        elapsed = time.perf_counter() - started
        usage = result.get("usage")
        completion_tokens = getattr(usage, "completion_tokens", None)
        print(
            f"[teams] answered in {elapsed:.1f}s "
            f"(answer_type={result.get('answer_type')}, completion_tokens={completion_tokens})"
        )

        answer = result.get("answer", "")
        sources = result.get("sources", [])
        response_text = f"{answer}{format_sources(sources, limit=3)}"
        await turn_context.send_activity(MessageFactory.text(response_text))


async def health(_request: web.Request) -> web.Response:
    return web.json_response({"status": "ok"})


async def web_chat_home(_request: web.Request) -> web.StreamResponse:
    # Always revalidate the HTML so browsers pick up new ?v= asset references
    # immediately (the static assets themselves stay cache-busted by ?v=).
    no_cache = {"Cache-Control": "no-cache"}
    index_file = STATIC_DIR / "index.html"
    if index_file.exists():
        return web.FileResponse(index_file, headers=no_cache)
    return web.Response(text=WEB_CHAT_HTML, content_type="text/html", headers=no_cache)


def web_source_records(sources: list) -> list[dict]:
    records = []
    seen = set()
    for document in sources:
        source = document_source_name(document)
        page = document.metadata.get("page")
        page_number = page + 1 if isinstance(page, int) else None
        # Collapse duplicate file copies of the same document via its code.
        key = (source_identity(source), page_number)
        if key in seen:
            continue
        seen.add(key)
        records.append(
            {
                "filename": source,
                "page": page_number,
                "label": source_label(source, page_number),
            }
        )
    return records


def safe_chat_debug_payload(retrieval_debug: dict) -> dict:
    base_host = urlparse(AI_BASE_URL).netloc or AI_BASE_URL
    return {
        "model_name": AI_MODEL,
        "ai_base_url_host": base_host,
        "embedding_model": EMBEDDING_MODEL,
        "retrieval_k": RETRIEVAL_K,
        "retrieval_fetch_k": RETRIEVAL_FETCH_K,
        "max_context_chars": MAX_CONTEXT_CHARS,
        **retrieval_debug,
    }


def public_chat_metadata(metadata: dict) -> dict:
    if not metadata:
        return {"answer_type": "rag"}
    answer_type = metadata.get("answer_type", "rag")
    public_metadata = {
        "answer_type": answer_type,
        "intent": metadata.get("intent"),
        "retrieval_used": bool(metadata.get("retrieval_used", answer_type == "rag")),
        "llm_used": bool(metadata.get("llm_used", answer_type == "rag")),
    }
    if answer_type == "catalog":
        public_metadata["catalog_intent"] = metadata.get("catalog_intent")
        public_metadata["total_documents"] = metadata.get("total_documents", 0)
    if answer_type == "metadata":
        public_metadata["metadata_source"] = metadata.get("metadata_source")
        public_metadata["normalized_document_code"] = metadata.get("normalized_document_code")
        public_metadata["query_aspect"] = metadata.get("query_aspect")
    return public_metadata


def create_documents_count_handler():
    async def documents_count(_request: web.Request) -> web.Response:
        return web.json_response(catalog_count_payload())

    return documents_count


def create_documents_handler():
    async def documents(_request: web.Request) -> web.Response:
        return web.json_response(catalog_documents_payload())

    return documents


def create_web_chat_handler(vector_store, client):
    async def chat(request: web.Request) -> web.Response:
        if "application/json" not in request.headers.get("Content-Type", ""):
            return web.json_response({"error": "Content-Type must be application/json."}, status=415)

        try:
            body = await request.json()
        except ValueError:
            return web.json_response({"error": "Invalid JSON body."}, status=400)

        question = str(body.get("question") or body.get("message") or "").strip()
        if not question:
            return web.json_response({"error": "Question is required."}, status=400)
        session_id = str(body.get("session_id") or "").strip()
        history = body.get("history")
        if history is not None and not isinstance(history, list):
            return web.json_response({"error": "History must be an array when provided."}, status=400)
        debug_requested = body.get("debug") is True
        try:
            result = await asyncio.to_thread(
                answer_chat,
                question,
                vector_store,
                client,
                history=history,
                session_id=session_id or None,
                debug=debug_requested,
            )
        except Exception:
            return web.json_response({"error": ERROR_MESSAGE}, status=500)

        sources = result.get("sources", [])
        public_metadata = public_chat_metadata(result.get("metadata", {}))
        answer_type = public_metadata.get("answer_type")
        if answer_type == "catalog":
            out_sources = []
        elif answer_type == "metadata":
            # Metadata answers already carry normalized source records (plain dicts).
            out_sources = sources if isinstance(sources, list) else []
        else:
            out_sources = web_source_records(sources)
        payload = {
            "answer": result.get("answer", ""),
            "sources": out_sources,
            "session_id": result.get("session_id"),
            "answer_type": public_metadata.get("answer_type", "rag"),
            "metadata": public_metadata,
        }
        if debug_requested:
            payload["debug"] = safe_chat_debug_payload(result.get("debug", {}))

        return web.json_response(payload)

    return chat


def create_messages_handler(adapter: BotFrameworkAdapter, bot: SecureMindTeamsBot, teams_enabled: bool):
    async def messages(request: web.Request) -> web.Response:
        if not teams_enabled:
            return web.Response(status=503, text="Microsoft Teams bot credentials are not configured.")

        if "application/json" not in request.headers.get("Content-Type", ""):
            return web.Response(status=415)

        body = await request.json()
        activity = Activity().deserialize(body)
        if activity.type != ActivityTypes.message:
            return web.Response(status=201)

        auth_header = request.headers.get("Authorization", "")
        try:
            response = await adapter.process_activity(activity, auth_header, bot.on_turn)
        except PermissionError:
            return web.Response(status=401, text="Unauthorized")
        except Exception:
            return web.Response(status=500, text=ERROR_MESSAGE)

        if response:
            return web.json_response(data=response.body, status=response.status)

        return web.Response(status=201)

    return messages


def create_app() -> web.Application:
    load_dotenv()
    validate_startup_config()

    print("Loading vector database...")
    vector_store = load_vector_store()
    print("Creating LLM client...")
    client = make_client()

    app_id = teams_app_id()
    app_password = teams_app_password()
    teams_enabled = bool(app_id and app_password)
    settings = BotFrameworkAdapterSettings(
        app_id,
        app_password,
        channel_auth_tenant=teams_tenant_id() or None,
    )
    adapter = BotFrameworkAdapter(settings)
    bot = SecureMindTeamsBot(vector_store, client)

    app = web.Application(middlewares=[access_token_middleware])
    app.router.add_get("/", web_chat_home)
    app.router.add_static("/static/", path=str(STATIC_DIR), name="static")
    app.router.add_post("/chat", create_web_chat_handler(vector_store, client))
    app.router.add_get("/documents/count", create_documents_count_handler())
    app.router.add_get("/documents", create_documents_handler())
    app.router.add_get("/health", health)
    app.router.add_post("/api/messages", create_messages_handler(adapter, bot, teams_enabled))
    return app


def main() -> None:
    load_dotenv()
    host = os.getenv("TEAMS_BOT_HOST", "0.0.0.0")
    port = int(os.getenv("PORT") or os.getenv("TEAMS_BOT_PORT", "3978"))
    app = create_app()
    print(f"SecureMind Teams bot listening on http://{host}:{port}/api/messages")
    web.run_app(app, host=host, port=port)


if __name__ == "__main__":
    main()
