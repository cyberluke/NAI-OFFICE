# WriterAgent - AI Writing Assistant for LibreOffice
#
# SPDX-License-Identifier: GPL-3.0-or-later
"""Creator Studio sidecar controller / deck state.

The user watches the AI type into the live Writer document and injects mid-stream.
``CreatorDeckState`` is the single, observable runtime the actual UI binds to: a
thread-safe snapshot of the current write (phase, chapter, chars, message) plus the
four injection commands (pause / resume / stop / restyle).  Both a sidebar deck and
the MCP surface can render this state and call the same commands, so the UI is a
thin view over one controller instead of each surface owning stream mechanics.

This module is a real runtime layer (not a mock): it drives the orchestrator's live
``CreatorRuntime`` and the inject helpers.  A concrete VCL/sidebar panel is left to
the plugin's existing ``librepy`` panel machinery; ``CreatorDeckState`` is the state
and command contract that such a panel renders.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Callable, final

from .inject import pause_stream, resume_stream, stop_stream

if TYPE_CHECKING:
    from .orchestrator import CreatorOrchestrator


@dataclass(frozen=True)
class CreatorDeckView:
    """A point-in-time, immutable snapshot the UI renders."""

    active: bool
    paused: bool
    phase: str
    chapter_title: str
    chars_written: int
    message: str
    elapsed_ms: int
    running: bool


def _snapshot(orch: CreatorOrchestrator) -> CreatorDeckView:
    rt = orch.runtime
    elapsed = int((time.time() - rt.started_at) * 1000) if rt.started_at else 0
    return CreatorDeckView(
        active=rt.active,
        paused=rt.paused,
        phase=rt.phase,
        chapter_title=rt.chapter_title,
        chars_written=rt.chars_written,
        message=rt.message,
        elapsed_ms=elapsed,
        running=rt.running,
    )


@final
class CreatorDeckState:
    """Thread-safe controller + snapshot for one Creator Studio running instance."""

    _orch: CreatorOrchestrator
    _lock: threading.Lock

    def __init__(self, orch: CreatorOrchestrator) -> None:
        self._orch = orch
        self._lock = threading.Lock()
        self._listeners: list[Callable[[CreatorDeckView], None]] = []

    @property
    def orchestrator(self) -> CreatorOrchestrator:
        return self._orch

    def view(self) -> CreatorDeckView:
        with self._lock:
            return _snapshot(self._orch)

    def subscribe(self, listener: Callable[[CreatorDeckView], None]) -> None:
        with self._lock:
            self._listeners.append(listener)

    def _emit(self, view: CreatorDeckView) -> None:
        for listener in list(self._listeners):
            try:
                listener(view)
            except Exception:
                pass

    # ---- injection commands (the buttons the deck renders) ----

    def pause(self) -> dict[str, Any]:
        with self._lock:
            result = pause_stream(self._orch)
            self._emit(_snapshot(self._orch))
            return result

    def resume(self) -> dict[str, Any]:
        with self._lock:
            result = resume_stream(self._orch)
            self._emit(_snapshot(self._orch))
            return result

    def stop(self) -> dict[str, Any]:
        with self._lock:
            result = stop_stream(self._orch)
            self._emit(_snapshot(self._orch))
            return result

    def restyle_selection(self, style: str, *, family: str = "ParagraphStyles") -> dict[str, Any]:
        from plugin.writer.styles import ApplyStyle

        with self._lock:
            result = ApplyStyle().execute(self._get_ctx(), style=style, family=family, target="selection")
            return result

    def _get_ctx(self) -> Any:
        """The ToolContext a real panel would hold; MCP/chat tools pass their own."""
        from plugin.framework.uno_context import get_ctx

        return get_ctx()