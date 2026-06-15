"""Shared document-code detection and normalization.

The catalog uses several code orderings (for example ``ZION-QT-04`` and
``QT-ZION-04`` are *different* documents, while ``ZION-TC-13`` has no reversed
twin). Users also type shorthand such as ``QT-04`` or ``TC-13``. This module
resolves a code typed in a question against the *actual* codes present in
``document_catalog.json`` so the rest of the pipeline can rely on canonical
values.

Resolution rules:
  1. Exact ordered match wins (``ZION-QT-04`` -> ``ZION-QT-04`` even when
     ``QT-ZION-04`` also exists).
  2. Otherwise an order-insensitive match (``TC-ZION-13`` -> ``ZION-TC-13``).
  3. Otherwise a shorthand match ignoring the ``ZION`` org token
     (``TC-13`` -> ``ZION-TC-13``).
  4. If a step matches more than one catalog code the request is *ambiguous*
     and ``None`` is returned (callers should ask the user to disambiguate).
"""

from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

CATALOG_PATH = Path("document_catalog.json")

# Code-like substrings inside free text: ZION-QT-04, QT-ZION-14, QT-04, TC-13...
_CODE_CANDIDATE_RE = re.compile(
    r"\b([A-Za-z]{2,5}(?:[-_ ][A-Za-z]{2,5})?[-_ ]\d{1,4})\b"
)

# Org token that may be dropped when matching shorthand codes.
_ORG_TOKEN = "ZION"


def _load_catalog_items(catalog=None) -> list[dict]:
    if catalog is not None:
        items = catalog
    else:
        try:
            payload = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return []
        if isinstance(payload, dict):
            items = payload.get("documents") or payload.get("items") or payload.get("catalog") or []
        else:
            items = payload
    return [item for item in items if isinstance(item, dict)]


def load_catalog_codes(catalog=None) -> list[str]:
    """Return the distinct, non-empty document codes present in the catalog."""
    codes = []
    for item in _load_catalog_items(catalog):
        code = str(item.get("document_code") or item.get("code") or "").strip()
        if code:
            codes.append(code)
    return list(dict.fromkeys(codes))


def _parse_code(raw: str):
    """Return ``(tokens, num)`` for a code-like string, or ``None``.

    ``tokens`` is the list of uppercase alpha parts and ``num`` is the numeric
    part with leading zeros stripped (so ``04`` and ``4`` match).
    """
    if not raw:
        return None
    parts = [p for p in re.split(r"[-_ ]+", raw.strip()) if p]
    if len(parts) < 2:
        return None
    num_part = parts[-1]
    alpha = parts[:-1]
    if not num_part.isdigit() or not alpha or not all(p.isalpha() for p in alpha):
        return None
    return [p.upper() for p in alpha], str(int(num_part))


def build_code_index(catalog=None) -> dict:
    """Build lookup maps from the catalog codes."""
    exact: dict[str, str] = {}
    unordered: dict[tuple, set] = {}
    short: dict[tuple, set] = {}
    for code in load_catalog_codes(catalog):
        parsed = _parse_code(code)
        if not parsed:
            continue
        tokens, num = parsed
        canon = "-".join(tokens) + "-" + num
        exact.setdefault(canon, code)
        unordered.setdefault((frozenset(tokens), num), set()).add(code)
        non_org = frozenset(t for t in tokens if t != _ORG_TOKEN)
        if non_org:
            short.setdefault((non_org, num), set()).add(code)
    return {"exact": exact, "unordered": unordered, "short": short}


@lru_cache(maxsize=1)
def _default_index() -> dict:
    return build_code_index(None)


def _get_index(catalog=None) -> dict:
    if catalog is None:
        return _default_index()
    return build_code_index(catalog)


def resolve_code(raw: str, catalog=None):
    """Resolve a raw code to its canonical catalog code.

    Returns ``(resolved_code_or_None, candidate_codes)``. When the code is
    ambiguous ``resolved_code`` is ``None`` and ``candidate_codes`` lists the
    competing catalog codes. When nothing matches both are empty/None.
    """
    parsed = _parse_code(raw)
    if not parsed:
        return None, []
    tokens, num = parsed
    index = _get_index(catalog)

    canon = "-".join(tokens) + "-" + num
    exact = index["exact"].get(canon)
    if exact:
        return exact, [exact]

    matches = index["unordered"].get((frozenset(tokens), num))
    if matches:
        if len(matches) == 1:
            code = next(iter(matches))
            return code, [code]
        return None, sorted(matches)

    non_org = frozenset(t for t in tokens if t != _ORG_TOKEN)
    short_matches = index["short"].get((non_org, num)) if non_org else None
    if short_matches:
        if len(short_matches) == 1:
            code = next(iter(short_matches))
            return code, [code]
        return None, sorted(short_matches)

    return None, []


def normalize_document_code(code: str, catalog=None):
    """Return the canonical catalog code for ``code`` or ``None``."""
    return resolve_code(code, catalog)[0]


def find_code_candidates(text: str) -> list[str]:
    """Return raw code-like substrings found in free text."""
    return [match.group(1) for match in _CODE_CANDIDATE_RE.finditer(text or "")]


def extract_document_codes(text: str, catalog=None) -> list[str]:
    """Return distinct canonical catalog codes referenced in ``text``."""
    resolved = []
    for raw in find_code_candidates(text):
        code = normalize_document_code(raw, catalog)
        if code:
            resolved.append(code)
    return list(dict.fromkeys(resolved))
