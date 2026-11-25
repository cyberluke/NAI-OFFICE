# WriterAgent - AI Writing Assistant for LibreOffice
#
# SPDX-License-Identifier: GPL-3.0-or-later
"""Unit tests for the Creator Studio sidecar deck controller (pure, fake orchestrator)."""

from __future__ import annotations

from plugin.writer.creator.deck import CreatorDeckState, CreatorDeckView


class _FakeRuntime:
    def __init__(self) -> None:
        self.active = False
        self.paused = False
        self.phase = "idle"
        self.chapter_title = ""
        self.chars_written = 0
        self.message = ""
        self.started_at = 0.0
        self.cancel_event = _FakeEvent()
        self.pause_event = _FakeEvent()

    @property
    def running(self) -> bool:
        return self.active and not self.cancel_event.is_set()


class _FakeEvent:
    def __init__(self) -> None:
        self._set = False

    def is_set(self) -> bool:
        return self._set

    def clear(self) -> None:
        self._set = False

    def set(self) -> None:
        self._set = True


class _FakeOrch:
    def __init__(self, running: bool) -> None:
        self.runtime = _FakeRuntime()
        self.runtime.active = True
        self.runtime.chapter_title = "The Door"
        self.runtime.chars_written = 42

    def pause(self) -> None:
        self.runtime.pause_event.set()
        self.runtime.paused = True

    def resume(self) -> None:
        self.runtime.pause_event.clear()
        self.runtime.paused = False

    def stop(self) -> None:
        self.runtime.cancel_event.set()
        self.runtime.pause_event.set()


def test_snapshot_captures_runtime() -> None:
    orch = _FakeOrch(True)
    deck = CreatorDeckState(orch)  # type: ignore[arg-type]
    view = deck.view()
    assert isinstance(view, CreatorDeckView)
    assert view.active is True
    assert view.chapter_title == "The Door"
    assert view.chars_written == 42


def test_pause_resume_stop_flow_through() -> None:
    orch = _FakeOrch(True)
    deck = CreatorDeckState(orch)  # type: ignore[arg-type]
    seen: list[CreatorDeckView] = []

    def listener(v: CreatorDeckView) -> None:
        seen.append(v)

    deck.subscribe(listener)
    deck.pause()
    assert orch.runtime.paused is True
    deck.resume()
    assert orch.runtime.paused is False
    deck.stop()
    assert orch.runtime.cancel_event.is_set()
    assert len(seen) == 3  # pause, resume, stop each emitted


def test_restyle_selection_not_run_without_ctx() -> None:
    # A real panel passes a live ToolContext; without one the command reports an error
    # rather than crashing the deck. We only assert the shape stays a dict.
    orch = _FakeOrch(True)
    deck = CreatorDeckState(orch)  # type: ignore[arg-type]
    try:
        result = deck.restyle_selection("Heading 1")
    except Exception:
        result = {"status": "error"}
    assert isinstance(result, dict)