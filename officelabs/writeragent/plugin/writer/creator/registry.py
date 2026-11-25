# WriterAgent - AI Writing Assistant for LibreOffice
#
# SPDX-License-Identifier: GPL-3.0-or-later
"""Document-keyed registry for live Creator Studio orchestrators.

The injection surface (pause / resume / stop / restyle / image) and the chunk
streaming path must steer the *same* running chapter write the user is watching.  A
per-document registry holds the live ``CreatorOrchestrator`` so the deck / MCP worker
and the tool surface resolve one instance per document instead of building throwaway
sync objects that cannot affect an in-flight stream.

The registry is a module-level singleton keyed by a document identity string (the
document's URL, falling back to its ``RuntimeUID``).  Callers are responsible for
clearing an entry when the document is closed; a stale entry is a no-op for a gone
document (the orchestrator's runtime guards on the active flag).
"""

from __future__ import annotations

import threading
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .orchestrator import CreatorOrchestrator

_lock = threading.Lock()
_by_doc: dict[str, "CreatorOrchestrator"] = {}


def _document_key(model: Any) -> str:
    """A stable, per-document key.  Prefer the URL; fall back to RuntimeUID so an
    unsaved document still gets its own orchestrator (never a shared global)."""
    key: str | None = None
    try:
        key = str(getattr(model, "getURL", lambda: None)() or "")
    except Exception:
        key = None
    if not key:
        try:
            uid = getattr(model, "RuntimeUID", None)
            if uid:
                key = f"uid:{uid}"
        except Exception:
            key = None
    if not key:
        key = f"obj:{id(model)}"
    return key


def get_orchestrator(model: Any) -> CreatorOrchestrator | None:
    with _lock:
        for existing in _by_doc.values():
            if existing.runtime.active:
                return existing
    return _by_doc.get(_document_key(model))


def set_orchestrator(model: Any, orch: CreatorOrchestrator) -> None:
    with _lock:
        _by_doc[_document_key(model)] = orch


def clear_orchestrator(model: Any) -> None:
    with _lock:
        _by_doc.pop(_document_key(model), None)


def active_orchestrator(model: Any) -> CreatorOrchestrator | None:
    """Return the live orchestrator for *model*, or the first active one if the key
    is stale.  Returns None when no live stream is running."""
    orch = get_orchestrator(model)
    if orch is not None and orch.runtime.active:
        return orch
    with _lock:
        for existing in _by_doc.values():
            if existing.runtime.active:
                return existing
    return None