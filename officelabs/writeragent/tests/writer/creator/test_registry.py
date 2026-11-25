# WriterAgent - AI Writing Assistant for LibreOffice
#
# SPDX-License-Identifier: GPL-3.0-or-later
"""Unit tests for the document-keyed orchestrator registry + injection steering."""

from __future__ import annotations

import pytest

from plugin.writer.creator.registry import (
    _document_key,
    active_orchestrator,
    clear_orchestrator,
    get_orchestrator,
    set_orchestrator,
)


class _Model:
    def __init__(self, url="", uid=""):
        self._url = url
        self._uid = uid

    def getURL(self):
        return self._url

    @property
    def RuntimeUID(self):
        return self._uid


class _RT:
    def __init__(self, active):
        self.active = active
        self.cancel_event = _Evt()
        self.pause_event = _Evt()

    @property
    def running(self):
        return self.active

    def checkpoint(self):
        pass

    def reset(self):
        self.active = False


class _Evt:
    def __init__(self):
        self._set = False

    def is_set(self):
        return self._set

    def set(self):
        self._set = True

    def clear(self):
        self._set = False


class _Orch:
    def __init__(self, active=False):
        self.runtime = _RT(active)


def _reset_registry():
    import plugin.writer.creator.registry as reg
    reg._by_doc.clear()


@pytest.fixture(autouse=True)
def _isolate_registry():
    _reset_registry()
    yield
    _reset_registry()


def test_document_key_uses_url_then_uid_then_id() -> None:
    assert _document_key(_Model(url="file:///a.odt")) == "file:///a.odt"
    assert _document_key(_Model(uid="u1")).startswith("uid:u1")
    assert _document_key(_Model()).startswith("obj:")


def test_set_get_clear_roundtrip() -> None:
    m = _Model(url="file:///x.odt")
    orch = _Orch()
    set_orchestrator(m, orch)  # type: ignore[arg-type]
    assert get_orchestrator(m) is orch
    clear_orchestrator(m)
    assert get_orchestrator(m) is None


def test_active_orchestrator_returns_only_running() -> None:
    m = _Model(url="file:///x.odt")
    idle = _Orch(active=False)
    running = _Orch(active=True)
    set_orchestrator(m, idle)  # type: ignore[arg-type]
    assert active_orchestrator(m) is None
    set_orchestrator(m, running)  # type: ignore[arg-type]
    assert active_orchestrator(m) is running


def test_active_orchestrator_falls_back_to_first_active() -> None:
    idle = _Orch(active=False)
    running = _Orch(active=True)
    set_orchestrator(_Model(url="file:///a.odt"), idle)  # type: ignore[arg-type]
    set_orchestrator(_Model(url="file:///b.odt"), running)  # type: ignore[arg-type]
    # Ask for a doc that has no orchestrator -> should find the active one.
    assert active_orchestrator(_Model(url="file:///c.odt")) is running