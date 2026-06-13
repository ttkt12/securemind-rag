from __future__ import annotations

import asyncio
import os
from pathlib import Path

from aiohttp import web
from botbuilder.core import (
    ActivityHandler,
    BotFrameworkAdapter,
    BotFrameworkAdapterSettings,
    MessageFactory,
    TurnContext,
)
from botbuilder.schema import Activity
from dotenv import load_dotenv

from config import VECTOR_DB_DIR
from rag_core import answer_question, load_vector_store, make_client

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


def env_is_configured(name: str) -> bool:
    value = os.getenv(name, "").strip()
    return bool(value and not value.startswith("your_"))


def validate_startup_config() -> None:
    print("Teams bot config validation:")
    missing = []
    for name in ("TEAMS_BOT_APP_ID", "TEAMS_BOT_APP_PASSWORD"):
        configured = env_is_configured(name)
        print(f"- {name}: {'OK' if configured else 'MISSING'}")
        if not configured:
            missing.append(name)

    index_file = VECTOR_DB_DIR / "index.faiss"
    metadata_file = VECTOR_DB_DIR / "index.pkl"
    if not index_file.exists() or not metadata_file.exists():
        raise RuntimeError(
            "Vector database not found. Run python3 ingest.py before starting "
            "the bot or provide vector_db in the deployment artifact."
        )

    if missing:
        raise RuntimeError("Missing required Teams bot .env values.")


def format_sources(sources: list, limit: int = 5) -> str:
    entries = []
    seen = set()
    for document in sources:
        source = Path(document.metadata.get("source", "unknown")).name
        page = document.metadata.get("page")
        page_label = f" page {page + 1}" if isinstance(page, int) else ""
        label = f"{source}{page_label}"
        if label in seen:
            continue
        seen.add(label)
        entries.append(label)
        if len(entries) >= limit:
            break

    if not entries:
        return ""

    return "\n\nNguồn:\n\n" + "\n".join(f"* {entry}" for entry in entries)


class SecureMindTeamsBot(ActivityHandler):
    def __init__(self, vector_store, client) -> None:
        self.vector_store = vector_store
        self.client = client

    async def on_message_activity(self, turn_context: TurnContext) -> None:
        user_text = (turn_context.activity.text or "").strip()
        if not user_text:
            await turn_context.send_activity("Vui lòng nhập câu hỏi.")
            return

        try:
            answer, sources, _usage = await asyncio.to_thread(
                answer_question,
                user_text,
                self.vector_store,
                self.client,
            )
            response_text = f"{answer}{format_sources(sources)}"
            await turn_context.send_activity(MessageFactory.text(response_text))
        except Exception:
            await turn_context.send_activity(ERROR_MESSAGE)


async def health(_request: web.Request) -> web.Response:
    return web.json_response({"status": "ok"})


async def web_chat_home(_request: web.Request) -> web.Response:
    return web.Response(text=WEB_CHAT_HTML, content_type="text/html")


def web_source_labels(sources: list, limit: int = 5) -> list[str]:
    labels = []
    seen = set()
    for document in sources:
        source = Path(document.metadata.get("source", "unknown")).name
        page = document.metadata.get("page")
        page_label = f" page {page + 1}" if isinstance(page, int) else ""
        label = f"{source}{page_label}"
        if label in seen:
            continue
        seen.add(label)
        labels.append(label)
        if len(labels) >= limit:
            break
    return labels


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

        try:
            answer, sources, _usage = await asyncio.to_thread(
                answer_question,
                question,
                vector_store,
                client,
            )
        except Exception:
            return web.json_response({"error": ERROR_MESSAGE}, status=500)

        return web.json_response(
            {
                "answer": answer,
                "sources": web_source_labels(sources),
            }
        )

    return chat


def create_messages_handler(adapter: BotFrameworkAdapter, bot: SecureMindTeamsBot):
    async def messages(request: web.Request) -> web.Response:
        if "application/json" not in request.headers.get("Content-Type", ""):
            return web.Response(status=415)

        body = await request.json()
        activity = Activity().deserialize(body)
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

    app_id = os.getenv("TEAMS_BOT_APP_ID", "").strip()
    app_password = os.getenv("TEAMS_BOT_APP_PASSWORD", "").strip()
    settings = BotFrameworkAdapterSettings(app_id, app_password)
    adapter = BotFrameworkAdapter(settings)
    bot = SecureMindTeamsBot(vector_store, client)

    app = web.Application()
    app.router.add_get("/", web_chat_home)
    app.router.add_post("/chat", create_web_chat_handler(vector_store, client))
    app.router.add_get("/health", health)
    app.router.add_post("/api/messages", create_messages_handler(adapter, bot))
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
