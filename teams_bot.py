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
