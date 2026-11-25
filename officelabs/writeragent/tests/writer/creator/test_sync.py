# WriterAgent - AI Writing Assistant for LibreOffice
#
# SPDX-License-Identifier: GPL-3.0-or-later
"""Unit tests for the Creator Studio two-way sync (pure core, fake binding)."""

from __future__ import annotations

from plugin.writer.creator.model import (
    CreatorArtifact,
    CreatorChapter,
    CreatorProject,
    CreatorProjectSettings,
)
from plugin.writer.creator.sync import (
    ChapterAnchor,
    IrWriterSync,
    PushOutcome,
    _group_prose,
    _merge_writer_prose_into_artifacts,
    heading_text_of,
    normalize_title,
)


class FakeBinding:
    """Simulates a live Writer document as a list of (text, is_heading) paragraphs."""

    def __init__(self, paras):
        self.paras = list(paras)
        self.writes: list[tuple[str, str, bool]] = []

    def read_prose(self, max_chars=None):
        return [dict(text=t, is_heading=h) for t, h in self.paras]

    def locate_anchor(self, chapter):
        for i, (t, h) in enumerate(self.paras):
            if h and t.strip() == chapter.title.strip():
                return ChapterAnchor(chapter.id, chapter.title, 1, i)
        return ChapterAnchor(chapter.id, chapter.title, 1, -1)

    def write_chapter(self, chapter, anchor, artifacts, *, on_chunk=None, chunks=None, text=None):
        body = text if text is not None else ("# " + chapter.title)
        if chunks is not None:
            joined = "".join(chunks)
        else:
            joined = body
        self.writes.append((chapter.title, joined[:24], chunks is not None))
        return PushOutcome(ok=True, message="ok", chars_written=len(joined), artifacts_written=1, anchors_updated=1)


def _project_with_one_empty_chapter(title="Chapter 1") -> CreatorProject:
    return CreatorProject(
        settings=CreatorProjectSettings(title="X", kind="novel"),
        chapters=[CreatorChapter(id="c0", title=title, status="planned")],
    )


def test_read_writer_into_ir() -> None:
    proj = _project_with_one_empty_chapter()
    binding = FakeBinding([("# Chapter 1", True), ("User typed this.", False), ("And this.", False)])
    sync = IrWriterSync(binding=binding)
    out = sync.load_into_project(proj)
    assert out.chapters_reconciled == 1
    assert proj.chapter("c0") is not None
    artifacts = proj.chapter("c0").scenes
    assert [a.body for a in artifacts] == ["User typed this.", "And this."]
    assert all(a.status == "drafted" for a in artifacts)


def test_load_does_not_touch_writer() -> None:
    binding = FakeBinding([("# Chapter 1", True), ("text", False)])
    sync = IrWriterSync(binding=binding)
    sync.load_into_project(_project_with_one_empty_chapter())
    assert binding.writes == []


def test_load_ignores_unmatched_headings() -> None:
    proj = _project_with_one_empty_chapter()
    binding = FakeBinding([("# Other Heading", True), ("not ours", False)])
    sync = IrWriterSync(binding=binding)
    out = sync.load_into_project(proj)
    assert out.chapters_reconciled == 0
    assert proj.chapter("c0").scenes == []


def test_push_chapter_streams_chunks() -> None:
    proj = _project_with_one_empty_chapter()
    proj.chapter("c0").scenes = [CreatorArtifact(id="a0", body="AI write", status="drafted")]
    binding = FakeBinding([("# Chapter 1", True)])

    class ConsumingBinding(binding.__class__):
        def write_chapter(self, chapter, anchor, artifacts, *, on_chunk=None, chunks=None, text=None):
            # Drain the iterator exactly like LoWriterBinding does.
            if chunks is not None:
                joined = "".join(chunks)
            else:
                joined = text or ("# " + chapter.title)
            self.writes.append((chapter.title, joined[:24], chunks is not None))
            return PushOutcome(ok=True, message="ok", chars_written=len(joined), artifacts_written=1, anchors_updated=1)

    sync = IrWriterSync(ConsumingBinding([("# Chapter 1", True)]))
    out = sync.push_chapter(proj.chapter("c0"), chunks=iter(["AI ", "write", " this."]))
    assert out.ok
    assert out.chars_written == len("AI write this.")
    assert sync.binding.writes[0][2] is True


def test_reconcile_store_persists_loaded_edits(tmp_path) -> None:
    from plugin.writer.creator.store import load_project_store

    proj = _project_with_one_empty_chapter()
    binding = FakeBinding([("# Chapter 1", True), ("fresh prose", False)])
    store = load_project_store(str(tmp_path / "p-creator.json"))
    sync = IrWriterSync(binding=binding, store=store)
    sync.project = proj
    sync.load_into_project(proj)
    record = sync.reconcile_store(proj, reason="after-load")
    assert record is not None
    reloaded = store.load().project
    assert reloaded.chapter("c0").scenes[0].body == "fresh prose"


def test_heading_parsing() -> None:
    assert heading_text_of("## A Heading") == "A Heading"
    assert heading_text_of("Chapter Title") is None
    assert normalize_title("  The   Door  ") == "the door"


def test_group_prose_skips_headings() -> None:
    group = [{"text": "# The Door", "is_heading": True}, {"text": "one", "is_heading": False}, {"text": "two", "is_heading": False}]
    assert _group_prose(group) == "one\n\ntwo"


def test_merge_writer_prose_into_artifacts_preserves_plan() -> None:
    artifacts = [CreatorArtifact(id="q1", body="", kind="quote", status="planned")]
    merged = _merge_writer_prose_into_artifacts(artifacts, ["quoted text"])
    assert merged[0].id == "q1"
    assert merged[0].body == "quoted text"
    assert merged[0].kind == "quote"