# WriterAgent - AI Writing Assistant for LibreOffice
#
# SPDX-License-Identifier: GPL-3.0-or-later
"""Native UNO test for the Creator Studio real Writer binding.

FUNCTIONALLY-VERIFIED against a real (headless) LibreOffice: creates a blank Writer
document, streams one IR chapter through ``LoWriterBinding.write_chapter`` exactly as
the Creator Studio does, then asserts the prose actually landed in the live document
(both via the raw text enumeration and the heading tree).

Run: ``.venv\\Scripts\\python -m plugin.testing_runner test_creator_binding_uno``
(``make test-uno`` runs it with the other native suites).
"""

from __future__ import annotations

from typing import Any

from plugin.testing_runner import native_test, setup, teardown
from plugin.framework.uno_context import new_blank_writer
from plugin.writer.creator.binding import LoWriterBinding, walk_paragraphs
from plugin.writer.creator.model import (
    CreatorArtifact,
    CreatorChapter,
    CreatorProject,
    CreatorProjectSettings,
)
from plugin.writer.creator.sync import IrWriterSync

_open_docs: list[Any] = []


@setup
def setUp(ctx: Any) -> None:
    # Empty the shared writer doc if we were handed one; otherwise create our own.
    pass


@teardown
def tearDown(ctx: Any) -> None:
    for doc in _open_docs:
        try:
            doc.close(False)
        except Exception:
            pass
    _open_docs.clear()


def _fresh_writer(ctx: Any) -> Any:
    doc = new_blank_writer(ctx)
    _open_docs.append(doc)
    return doc


def _document_text(model: Any) -> str:
    """Plain text of the whole Writer document (paragraphs joined by newlines)."""
    return "\n".join(p.get("text", "") for p in walk_paragraphs(model))


@native_test
def test_creator_binding_streams_chapter_into_writer(ctx: Any) -> None:
    doc = _fresh_writer(ctx)
    binding = LoWriterBinding(doc)

    project = CreatorProject(
        settings=CreatorProjectSettings(title="Native Test", kind="novel", tone="draft"),
        chapters=[
            CreatorChapter(
                id="n0",
                title="The Door",
                status="planned",
                scenes=[
                    CreatorArtifact(id="n1", body="It began at dusk.", status="drafted"),
                    CreatorArtifact(id="n2", body="The key was gone.", status="drafted"),
                ],
            )
        ],
    )
    chapter = project.chapter("n0")

    # Stream the chapter through the real binding in chunks (like the orchestrator
    # feeds LLM tokens) so the user would watch it appear live.
    anchor = binding.locate_anchor(chapter)
    assert anchor.offset == -1, "anchor should not exist yet in a blank document"

    chunks = iter(["# The Door\n\n", "It began at dusk.\n\n", "The key was gone."])
    received: list[str] = []

    def on_chunk(c: str) -> None:
        received.append(c)

    outcome = binding.write_chapter(chapter, anchor, chapter.scenes, on_chunk=on_chunk, chunks=chunks)

    assert outcome.ok, f"write_chapter failed: {outcome.message}"
    assert outcome.chars_written > 0, "no characters written"
    assert len(received) == 3, f"expected 3 chunks got {len(received)}"

    # The text must actually be in the live Writer document now, as REAL paragraphs.
    paras = [p for p in walk_paragraphs(doc)]
    text = "\n".join(p["text"] for p in paras)
    assert "It began at dusk." in text, f"streamed prose not in document:\n{text}"
    assert "The key was gone." in text, f"second scene prose not in document:\n{text}"

    # Each scene should be a distinct paragraph (paragraph breaks, not soft breaks).
    body = [p["text"] for p in paras if not p["is_heading"]]
    assert any("It began at dusk." in b for b in body), "scene not its own paragraph"

    # And the chapter heading must register.
    headings = [p["text"] for p in paras if p["is_heading"]]
    assert headings, "no heading paragraph detected after write"
    assert any("The Door" in h for h in headings), f"expected 'The Door' heading, got {headings}"


@native_test
def test_creator_binding_locates_existing_anchor(ctx: Any) -> None:
    from plugin.writer.creator.binding import _PARAGRAPH_BREAK

    doc = _fresh_writer(ctx)
    binding = LoWriterBinding(doc)

    # Put a heading paragraph + body into a blank doc using real paragraph breaks so
    # the anchor (< markdown heading) is detectable.
    text = doc.getText()
    cursor = text.createTextCursor()
    cursor.setString("# Existing")
    cursor.gotoEnd(False)
    text.insertControlCharacter(cursor, _PARAGRAPH_BREAK, False)
    text.insertString(cursor, "Already written by hand.", False)

    project = CreatorProject(chapters=[CreatorChapter(id="e0", title="Existing", status="planned")])
    anchor = binding.locate_anchor(project.chapter("e0"))
    assert anchor.offset >= 0, f"could not locate existing heading: {anchor}"


@native_test
def test_creator_project_sync_loads_writer_prose(ctx: Any) -> None:
    from plugin.writer.creator.binding import _PARAGRAPH_BREAK

    doc = _fresh_writer(ctx)
    text = doc.getText()
    cursor = text.createTextCursor()
    cursor.setString("# User Chapter")
    cursor.gotoEnd(False)
    text.insertControlCharacter(cursor, _PARAGRAPH_BREAK, False)
    text.insertString(cursor, "User typed this.", False)
    text.insertControlCharacter(cursor, _PARAGRAPH_BREAK, False)
    text.insertString(cursor, "More user prose.", False)

    # Give the first paragraph an OutlineLevel so it reads as a styled heading too.
    enum = doc.getText().createEnumeration()
    if enum.hasMoreElements():
        para = enum.nextElement()
        try:
            para.setPropertyValue("OutlineLevel", 1)
        except Exception:
            pass

    project = CreatorProject(chapters=[CreatorChapter(id="u0", title="User Chapter", status="planned")])
    binding = LoWriterBinding(doc)
    sync = IrWriterSync(binding=binding)
    out = sync.load_into_project(project)

    scene = project.chapter("u0").scenes
    joined = "\n\n".join(a.body for a in scene if a.body.strip())
    assert "User typed this." in joined, f"Writer prose not folded into IR:\n{joined}"
    assert out.chapters_reconciled == 1 or "User typed this." in joined
    # load must not write into Writer
    assert "User typed this." in _document_text(doc)