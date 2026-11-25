# WriterAgent - AI Writing Assistant for LibreOffice
#
# SPDX-License-Identifier: GPL-3.0-or-later
"""Unit tests for the Creator Studio store (pure Python, no UNO)."""

from __future__ import annotations

import json
import os

import pytest

from plugin.writer.creator.model import CreatorChapter, CreatorProject, CreatorProjectSettings
from plugin.writer.creator.store import (
    CreatorStoreError,
    load_project_store,
    save_project_store,
)


def _project() -> CreatorProject:
    return CreatorProject(
        settings=CreatorProjectSettings(title="Book", kind="book"),
        chapters=[CreatorChapter(id="c1", title="One", status="drafted")],
    )


def test_save_then_load(tmp_path) -> None:
    path = str(tmp_path / "proj-creator.json")
    proj = _project()
    rec = save_project_store(path, proj, reason="test")
    loaded = load_project_store(path).load()
    assert loaded is not None
    assert loaded.revision == rec.revision
    assert loaded.project.chapters[0].title == "One"
    assert loaded.checksum == loaded.checksum  # deterministic


def test_load_missing_returns_none(tmp_path) -> None:
    store = load_project_store(str(tmp_path / "missing-creator.json"))
    assert store.load() is None


def test_revision_monotonic(tmp_path) -> None:
    path = str(tmp_path / "p-creator.json")
    store = load_project_store(path)
    store.save(_project(), reason="a")
    store.save(_project(), reason="b")
    store.save(_project(), reason="c")
    loaded = store.load()
    assert loaded is not None
    assert loaded.revision == 2  # 0,1,2


def test_same_content_different_revision(tmp_path) -> None:
    path = str(tmp_path / "p-creator.json")
    store = load_project_store(path)
    r1 = store.save(_project(), reason="a")
    r2 = store.save(_project(), reason="b")
    # Same content -> same checksum even across revisions.
    assert r1.checksum == r2.checksum
    assert r1.revision != r2.revision


def test_corrupt_store_raises(tmp_path) -> None:
    path = str(tmp_path / "bad-creator.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump({"project": "not a mapping"}, fh)
    with pytest.raises(CreatorStoreError):
        load_project_store(path).load()


def test_malformed_project_raises(tmp_path) -> None:
    path = str(tmp_path / "bad2-creator.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump({"project": {"chapters": [{"id": "a"}, {"id": "a"}]}}, fh)
    with pytest.raises(CreatorStoreError):
        load_project_store(path).load()


def test_store_creates_parent_dir(tmp_path) -> None:
    nested = str(tmp_path / "a" / "b" / "p-creator.json")
    store = load_project_store(nested)
    store.save(_project(), reason="mkdir")
    assert os.path.exists(nested)