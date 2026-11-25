# WriterAgent - AI Writing Assistant for LibreOffice
#
# SPDX-License-Identifier: GPL-3.0-or-later
"""Unit tests for the Creator Studio tools' store resolution (pure, no UNO).

The tool surface resolves the IR store to a document-adjacent JSON file.  When the
document has no path yet (unsaved), it must fall back gracefully (user config dir or a
per-session temp dir) and never raise — otherwise a first-run document cannot start a
Creator Studio.
"""

from __future__ import annotations

import os

from plugin.writer.creator import tools


def _model_with_path(path: str):
    class _Model:
        pass

    m = _Model()
    m._path = path
    # get_document_path in production reads the model's URL; here we patch it.
    return m


def _patch_get_document_path(monkeypatch, result, *, exc=False):
    from plugin.writer.creator import tools as t

    def _fake(model):
        if exc:
            raise RuntimeError("no path")
        return result if result else None

    monkeypatch.setattr(t, "get_document_path", _fake)


def test_store_for_resolves_document_adjacent(monkeypatch, tmp_path) -> None:
    doc_path = str(tmp_path / "book.odt")
    _patch_get_document_path(monkeypatch, doc_path)
    store = tools._store_for(object())
    assert store.path == str(tmp_path / "book-creator.json")


def test_store_for_unsaved_falls_back_to_config(monkeypatch, tmp_path) -> None:
    from plugin.writer.creator.registry import _document_key

    _patch_get_document_path(monkeypatch, None)
    cfg_dir = str(tmp_path / "profile")
    os.makedirs(cfg_dir, exist_ok=True)

    def _user_config_dir():
        return cfg_dir

    monkeypatch.setattr("plugin.framework.config.user_config_dir", _user_config_dir)

    model = object()
    key = _document_key(model).replace(":", "_").replace("/", "_")
    store = tools._store_for(model)
    assert store.path == os.path.join(cfg_dir, f"creator-{key}-unsaved.json-creator.json")

    # Two distinct unsaved documents must NOT resolve to the same store path.
    store2 = tools._store_for(object())
    assert store2.path != store.path


def test_store_for_never_raises_when_config_fails(monkeypatch) -> None:

    _patch_get_document_path(monkeypatch, None, exc=True)

    def _fail():
        raise RuntimeError("no config dir")

    monkeypatch.setattr("plugin.framework.config.user_config_dir", _fail)

    model = object()
    store = tools._store_for(model)
    # Falls back to a per-document temp-dir store; must not raise into a shared filename.
    assert f"creator-{id(model)}-unsaved.json" in store.path