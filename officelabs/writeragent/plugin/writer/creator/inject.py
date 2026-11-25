# WriterAgent - AI Writing Assistant for LibreOffice
# Copyright (c) 2026 KeithCu (modifications and relicensing)
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
"""The Creator Studio injection surface.

While the AI is typing a chapter into the live Writer document, the user can inject:

- **pause / resume / stop** the stream (through the orchestrator runtime),
- **rewrite a paragraph with another AI (Writer Agent)** on the fly.

Restyle and image insertion are handled by the existing style / image tools directly
(the tool surface calls ``ApplyStyle`` / ``insert_image_at_locator``), so this module
owns only stream control and paragraph re-rewrite.  These are synchronous affordances
the deck and the chat/MCP tools call between chunks; the deck / MCP resolve the live
``CreatorOrchestrator`` from :mod:`plugin.writer.creator.registry`.
"""

from __future__ import annotations

from typing import Any, Callable, Iterator

from .orchestrator import CreatorOrchestrator, StopRequested


def pause_stream(orch: CreatorOrchestrator) -> dict[str, Any]:
    """Pause the current write stream (no-op when idle)."""
    if orch.runtime.active:
        orch.pause()
        return {"status": "ok", "paused": True}
    return {"status": "ok", "paused": False, "message": "no active write stream"}


def resume_stream(orch: CreatorOrchestrator) -> dict[str, Any]:
    orch.resume()
    return {"status": "ok", "paused": False}


def stop_stream(orch: CreatorOrchestrator) -> dict[str, Any]:
    orch.stop()
    return {"status": "ok", "stopped": True}


def rewrite_paragraph_with_agent(
    orch: CreatorOrchestrator,
    *,
    paragraph: str,
    agent_cb: Callable[[str], Iterator[str]],
    apply_rewrite_cb: Callable[[str], Any],
) -> dict[str, Any]:
    """Rewrite *paragraph* with a different writer agent on the fly.

    This is the "rewrite paragraph using another AI" injection: it runs a second agent
    over the paragraph text and applies the result through ``apply_rewrite_cb`` (which,
    in production, is a ``WriterStreamedRewriteSession`` bound to the paragraph's range).
    The main write stream keeps its own undo context; this rewrite lands in its own.
    """
    if not paragraph.strip():
        return {"status": "error", "message": "empty paragraph"}

    chunks = agent_cb(paragraph)
    pieces: list[str] = []
    try:
        for c in chunks:
            if c:
                pieces.append(c)
    except StopRequested:
        return {"status": "stopped", "rewritten": "".join(pieces)}

    rewritten = "".join(pieces).strip()
    if not rewritten:
        return {"status": "error", "message": "agent produced no rewrite"}

    result = apply_rewrite_cb(rewritten)
    return {"status": "ok", "rewritten": rewritten, "result": result}