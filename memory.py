from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass

from config import (
    ENABLE_AGENTBASE_MEMORY,
    MEMORY_ACTOR_ID,
    MEMORY_ID,
    MEMORY_MAX_CONTEXT_CHARS,
    MEMORY_SEARCH_LIMIT,
    MEMORY_STRATEGY_ID,
)


SECRET_PATTERNS = (
    re.compile(r"\b(api[_-]?key|secret|password|passwd|token|bearer|client[_-]?secret)\b", re.I),
    re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b"),
    re.compile(r"\bvn-[A-Za-z0-9_-]{20,}\b"),
    re.compile(r"\b[A-Za-z0-9_=-]{48,}\b"),
)

MEMORY_TRIGGER_PATTERNS = (
    re.compile(r"\bremember that\s+(.+)", re.I),
    re.compile(r"\bplease remember\s+(.+)", re.I),
    re.compile(r"\bmy preference is\s+(.+)", re.I),
    re.compile(r"\bi prefer\s+(.+)", re.I),
    re.compile(r"\bcall me\s+(.+)", re.I),
    re.compile(r"\bmy name is\s+(.+)", re.I),
    re.compile(r"\bthis project is\s+(.+)", re.I),
    re.compile(r"\bproject context[:\s]+(.+)", re.I),
    re.compile(r"\bnh[oớ]\s+(?:r[aằ]ng|l[aà])\s+(.+)", re.I),
    re.compile(r"\bh[aã]y nh[oớ]\s+(.+)", re.I),
    re.compile(r"\bt[eê]n (?:t[oô]i|tui|m[iì]nh) l[aà]\s+(.+)", re.I),
    re.compile(r"\b(?:t[oô]i|tui|m[iì]nh) th[ií]ch\s+(.+)", re.I),
    re.compile(r"\b(?:t[oô]i|tui|m[iì]nh) mu[oố]n\s+(.+)", re.I),
)


@dataclass(frozen=True)
class MemorySettings:
    enabled: bool
    memory_id: str
    strategy_id: str
    actor_id: str
    search_limit: int
    max_context_chars: int

    @property
    def configured(self) -> bool:
        return bool(self.enabled and self.memory_id and self.strategy_id and self.actor_id)


def load_memory_settings() -> MemorySettings:
    return MemorySettings(
        enabled=ENABLE_AGENTBASE_MEMORY,
        memory_id=MEMORY_ID,
        strategy_id=MEMORY_STRATEGY_ID,
        actor_id=MEMORY_ACTOR_ID,
        search_limit=max(1, min(MEMORY_SEARCH_LIMIT, 20)),
        max_context_chars=max(500, MEMORY_MAX_CONTEXT_CHARS),
    )


def is_sensitive_text(text: str) -> bool:
    return any(pattern.search(text or "") for pattern in SECRET_PATTERNS)


def clean_memory_fact(text: str) -> str:
    fact = " ".join(str(text or "").split())
    fact = fact.strip(" .")
    return fact[:500]


def extract_memory_facts(question: str, answer: str) -> list[str]:
    if is_sensitive_text(question) or is_sensitive_text(answer):
        return []

    facts = []
    for pattern in MEMORY_TRIGGER_PATTERNS:
        match = pattern.search(question)
        if not match:
            continue
        fact = clean_memory_fact(match.group(1))
        if fact and not is_sensitive_text(fact):
            facts.append(fact)

    return list(dict.fromkeys(facts))


def run_async(coro):
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)

    # The CLI path has no running event loop. If a future caller invokes this
    # from async code, close the coroutine and skip rather than nesting loops.
    coro.close()
    raise RuntimeError("AgentBase Memory sync wrapper cannot run inside an active event loop.")


class AgentBaseMemory:
    def __init__(self, settings: MemorySettings | None = None) -> None:
        self.settings = settings or load_memory_settings()
        self._client = None
        self._warning_shown = False

    @property
    def enabled(self) -> bool:
        return self.settings.configured

    def status_message(self) -> str:
        if not self.settings.enabled:
            return "AgentBase Memory disabled."
        missing = []
        if not self.settings.memory_id:
            missing.append("MEMORY_ID")
        if not self.settings.strategy_id:
            missing.append("MEMORY_STRATEGY_ID")
        if not self.settings.actor_id:
            missing.append("MEMORY_ACTOR_ID")
        if missing:
            return f"AgentBase Memory unavailable; missing {', '.join(missing)}."
        return "AgentBase Memory enabled."

    def _warn_once(self, message: str) -> None:
        if self._warning_shown:
            return
        self._warning_shown = True
        print(f"Warning: AgentBase Memory skipped ({message}).")

    def _namespace(self) -> str:
        return f"/strategies/{self.settings.strategy_id}/actors/{self.settings.actor_id}"

    def _memory_client(self):
        if self._client is not None:
            return self._client
        try:
            from greennode_agentbase.memory import MemoryClient
        except ImportError as exc:
            raise RuntimeError("install greennode-agentbase or disable ENABLE_AGENTBASE_MEMORY") from exc

        self._client = MemoryClient()
        return self._client

    def recall(self, question: str) -> str:
        if not self.enabled:
            return ""
        if is_sensitive_text(question):
            return ""

        try:
            from greennode_agentbase.memory.models import MemoryRecordSearchRequest

            client = self._memory_client()
            results = run_async(
                client.search_memory_records_async(
                    id=self.settings.memory_id,
                    namespace=self._namespace(),
                    request=MemoryRecordSearchRequest(
                        query=question,
                        limit=self.settings.search_limit,
                    ),
                )
            )
        except Exception as exc:
            self._warn_once(exc.__class__.__name__)
            return ""

        memories = []
        for record in results or []:
            memory_text = clean_memory_fact(getattr(record, "memory", "") or getattr(record, "content", ""))
            if memory_text and not is_sensitive_text(memory_text):
                memories.append(f"- {memory_text}")

        context = "\n".join(memories)
        return context[: self.settings.max_context_chars]

    def remember(self, question: str, answer: str) -> None:
        if not self.enabled:
            return

        facts = extract_memory_facts(question, answer)
        if not facts:
            return

        try:
            client = self._memory_client()
            run_async(
                client.insert_memory_records_directly_async(
                    id=self.settings.memory_id,
                    namespace=self._namespace(),
                    request=facts,
                )
            )
        except Exception as exc:
            self._warn_once(exc.__class__.__name__)


def make_memory() -> AgentBaseMemory:
    return AgentBaseMemory()
