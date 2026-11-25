# WriterAgent - AI Writing Assistant for LibreOffice
#
# SPDX-License-Identifier: GPL-3.0-or-later
"""Unit tests for the Creator Studio injection surface (pure, fake callables)."""

from __future__ import annotations

from plugin.writer.creator.inject import (
    pause_stream,
    resume_stream,
    rewrite_paragraph_with_agent,
    stop_stream,
)


class _IdleOrch:
    class _RT:
        active = False

    def __init__(self) -> None:
        self.runtime = _IdleOrch._RT()
        self.paused = False
        self.stopped = False

    def pause(self) -> None:
        self.paused = True

    def resume(self) -> None:
        self.paused = False

    def stop(self) -> None:
        self.stopped = True


def test_pause_idle_is_ok() -> None:
    orch = _IdleOrch()
    res = pause_stream(orch)  # type: ignore[arg-type]
    assert res["status"] == "ok"
    assert res["paused"] is False


def test_stop_and_resume() -> None:
    orch = _IdleOrch()
    res = stop_stream(orch)  # type: ignore[arg-type]
    assert res["stopped"] is True
    resume_stream(orch)  # type: ignore[arg-type]
    assert orch.paused is False


def test_rewrite_paragraph_with_agent_ok() -> None:
    def agent_cb(paragraph):
        assert paragraph == "old text"
        yield "new "
        yield "text"

    def apply_rewrite(text):
        return {"applied": True, "text": text}

    orch = _IdleOrch()
    res = rewrite_paragraph_with_agent(orch, paragraph="old text", agent_cb=agent_cb, apply_rewrite_cb=apply_rewrite)  # type: ignore[arg-type]
    assert res["status"] == "ok"
    assert res["rewritten"] == "new text"
    assert res["result"]["applied"] is True


def test_rewrite_empty_paragraph_is_error() -> None:
    res = rewrite_paragraph_with_agent(_IdleOrch(), paragraph="   ", agent_cb=lambda p: iter([]), apply_rewrite_cb=lambda t: {})  # type: ignore[arg-type]
    assert res["status"] == "error"


def test_rewrite_agent_empty_result_is_error() -> None:
    res = rewrite_paragraph_with_agent(
        _IdleOrch(),
        paragraph="has text",
        agent_cb=lambda p: iter(["", " "]),
        apply_rewrite_cb=lambda t: {},
    )  # type: ignore[arg-type]
    assert res["status"] == "error"