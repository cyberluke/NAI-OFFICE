# WriterAgent - AI Writing Assistant for LibreOffice
# Copyright (c) 2026 KeithCu (modifications and relicensing)
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
"""Real UNO ``WriterBinding`` for the Creator Studio two-way sync.

This implements :class:`~.sync.WriterBinding` by federating the WriterAgent
Writer primitives that already exist — the heading walk in
``plugin.doc.text_helpers.build_heading_tree`` (as a ready reference), the light
paragraph enumeration in ``plugin/doc/text_helpers.py``, and ``WriterCompoundUndo``
(compound-undo step) in ``plugin.writer.edit_review``.  The Creator Studio adds the
document-level "watch the AI type into the live document" layer; it does not
reimplement Writer DOM mechanics.

Threading: like the rest of WriterAgent, this binding runs on the UI/VCL thread.
The orchestrator supplies already-generated text chunks here; the binding inserts
them into the live document paragraph by paragraph (real paragraph breaks, so each
scene lands as a distinct Writer paragraph).  Each chunk paints immediately, so the
user watches the AI type.  The whole chapter is wrapped in one compound undo step.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Callable, Iterator

from plugin.framework.errors import WriterAgentException

from .sync import ChapterAnchor, PushOutcome, heading_text_of, normalize_title

if TYPE_CHECKING:
    from .model import CreatorArtifact, CreatorChapter

log = logging.getLogger("writeragent.creator.binding")

# com.sun.star.text.ControlCharacter.PARAGRAPH_BREAK
_PARAGRAPH_BREAK = 0


# Canonical `# Title` marker heading-text source lives in sync (`heading_text_of`);
# this alias keeps the binding's public name without re-implementing the regex.
heading_title = heading_text_of


def paragraph_is_heading(para: Any) -> bool:
    """True when a Writer paragraph is a heading.

    A paragraph is treated as a chapter/section heading when it carries an outline
    level (OutlineLevel > 0).  We also fall back to the Creator Studio's canonical
    marker convention (a paragraph whose text starts like ``# Title``), so chapters
    written before any paragraph style is applied still sync by heading text.
    """
    try:
        level = para.getPropertyValue("OutlineLevel")
        if isinstance(level, int) and level > 0:
            return True
    except Exception:
        pass
    return heading_title(paragraph_text(para)) is not None


def paragraph_text(para: Any) -> str:
    try:
        return str(para.getString() or "")
    except Exception:
        return ""


def walk_paragraphs(model: Any) -> Iterator[dict[str, Any]]:
    """Yield ``{"text": str, "is_heading": bool}`` for every Writer paragraph in order.

    Federates the same enumeration pattern as ``build_heading_tree`` but keeps the
    body text, which the IR sync needs (the heading tree only reports paragraph
    counts).  This is a read-only walk; it never writes to the document.
    """
    text = model.getText()
    enum = text.createEnumeration()
    while enum.hasMoreElements():
        element = enum.nextElement()
        if element.supportsService("com.sun.star.text.Paragraph"):
            yield {
                "text": paragraph_text(element),
                "is_heading": paragraph_is_heading(element),
            }


def _iter_paragraph_elements(text: Any):
    enum = text.createEnumeration()
    while enum.hasMoreElements():
        element = enum.nextElement()
        if element.supportsService("com.sun.star.text.Paragraph"):
            yield element


class LogIOError(WriterAgentException):
    """Raised when the Writer document could not be read/written."""


from typing import final as _final


@_final
class LoWriterBinding:
    """Implements :class:`~.sync.WriterBinding` for a live LibreOffice Writer document."""

    model: Any

    def __init__(self, model: Any) -> None:
        self.model = model
        # Visible text of the paragraph currently being typed across chunk calls, so a
        # paragraph split across several streamed chunks is folded back into the IR whole.
        self._pending_paragraph: list[str] = []

    def _flush_pending_paragraph(self, written_paragraphs: list[str]) -> None:
        if self._pending_paragraph:
            text = "".join(self._pending_paragraph)
            if text.strip():
                written_paragraphs.append(text)
            self._pending_paragraph = []

    # ---- read side (Writer -> IR) ----

    def read_prose(self, max_chars: int | None = None) -> list[dict[str, Any]]:
        try:
            paragraphs = list(walk_paragraphs(self.model))
        except Exception as exc:  # pragma: no cover - UNO path
            raise LogIOError(f"creator: could not read Writer paragraphs: {exc}") from exc
        if max_chars and max_chars > 0:
            # Keep leading paragraphs up to the budget (approximate, prose only).
            budget = int(max_chars)
            kept: list[dict[str, Any]] = []
            for p in paragraphs:
                kept.append(p)
                budget -= len(p.get("text", ""))
                if budget <= 0:
                    break
            paragraphs = kept
        return paragraphs

    def locate_anchor(self, chapter: CreatorChapter) -> ChapterAnchor:
        """Find the heading paragraph whose (heading) text matches *chapter.title*."""
        target = normalize_title(chapter.title)
        paragraphs = self.read_prose()
        for i, p in enumerate(paragraphs):
            if not p.get("is_heading"):
                continue
            text = p.get("text", "")
            title = heading_title(text)
            if title is None:
                title = text.strip()
            if title and normalize_title(title) == target:
                return ChapterAnchor(chapter_id=chapter.id, title=chapter.title, level=1, offset=i)
        return ChapterAnchor(chapter_id=chapter.id, title=chapter.title, level=1, offset=-1)

    # ---- write side (IR -> Writer) ----

    def write_chapter(
        self,
        chapter: CreatorChapter,
        anchor: ChapterAnchor,
        artifacts: list[CreatorArtifact],
        *,
        on_chunk: Callable[[str], None] | None = None,
        chunks: Iterator[str] | None = None,
        text: str | None = None,
    ) -> PushOutcome:
        """Stream *chapter* into the live document, paragraph by paragraph.

        ``chunks`` (when given) is an iterator of generated text tokens.  We stream them
        through a Writer cursor that inserts real paragraph breaks (via the paragraph
        control character), so the prose lands as distinct Writer paragraphs the user
        watches appear — not as a single string with soft line breaks.  The whole chapter
        is wrapped in one compound undo step (federating ``WriterCompoundUndo``), matching
        the "one Ctrl+Z reverts the chapter" behaviour a writer expects.

        ``text`` is the non-streamed single-shot form used by tests and tool calls.
        """
        if text is None and chunks is None:
            text = self._chapter_serial(chapter, artifacts)

        try:
            from plugin.writer.edit_review import WriterCompoundUndo
        except Exception as exc:  # pragma: no cover - UNO path
            raise LogIOError(f"creator: could not import undo helper: {exc}") from exc

        # The anchor's offset is already the located heading index (computed by
        # ``locate_anchor`` in one pass); avoid re-walking the whole document here.
        heading_index = anchor.offset if anchor.offset >= 0 else -1

        # Replace target: the block the chapter currently spans [heading_index, next heading).
        if heading_index >= 0:
            self._clear_block(heading_index)
            cursor = self._insertion_cursor_at_heading(heading_index)
        else:
            cursor = self._insertion_cursor_at_end()

        written = 0
        written_paragraphs: list[str] = []

        with WriterCompoundUndo(self.model, f"Creator Studio: {chapter.title or 'chapter'}"):
            try:
                if chunks is not None:
                    for chunk in chunks:
                        if not chunk:
                            continue
                        written += self._insert_streamed(cursor, chunk, on_chunk, written_paragraphs)
                else:
                    written += self._insert_streamed(cursor, text or "", on_chunk, written_paragraphs)
                # Flush any trailing partial paragraph (no terminal break) so the IR
                # receives the last written paragraph, not just break-terminated ones.
                self._flush_pending_paragraph(written_paragraphs)
            except Exception as exc:  # pragma: no cover - UNO path
                raise LogIOError(f"creator: chapter write failed: {exc}") from exc

        # Drop the heading marker paragraph we wrote (it is the chapter title, not prose).
        scene_prose = [p for p in written_paragraphs if p.strip() and not heading_title(p)]
        return PushOutcome(
            ok=True,
            message="ok",
            chars_written=written,
            artifacts_written=len([a for a in (artifacts or []) if a.body.strip()]),
            anchors_updated=1,
            written_paragraphs=scene_prose,
        )

    def _insert_streamed(
        self,
        cursor: Any,
        chunk: str,
        on_chunk: Callable[[str], None] | None,
        written_paragraphs: list[str],
    ) -> int:
        """Insert *chunk* at *cursor*, converting ``\\n\\n`` paragraph breaks into real
        Writer paragraph breaks so each scene writes as its own paragraph.  Flushes each
        completed paragraph (its visible text) into *written_paragraphs*; the trailing
        open paragraph is kept on the instance so a paragraph split across chunks stays
        whole.  Returns visible characters written (excludes control chars)."""
        text = cursor.getText()
        written = 0
        # Insert a leading paragraph break when a chunk begins a new paragraph block.
        if chunk.startswith("\n"):
            text.insertControlCharacter(cursor, _PARAGRAPH_BREAK, False)
            self._flush_pending_paragraph(written_paragraphs)
            chunk = chunk.lstrip("\n")
        parts = chunk.split("\n")
        for i, part in enumerate(parts):
            if part:
                text.insertString(cursor, part, False)
                written += len(part)
                self._pending_paragraph.append(part)
                if on_chunk is not None:
                    on_chunk(part)
            if i < len(parts) - 1:
                text.insertControlCharacter(cursor, _PARAGRAPH_BREAK, False)
                self._flush_pending_paragraph(written_paragraphs)
        cursor.gotoEnd(False)
        return written

    def _insertion_cursor_at_heading(self, heading_index: int) -> Any:
        """A collapsed Writer cursor at the located heading paragraph's start (single walk)."""
        text = self.model.getText()
        para_index = 0
        for element in _iter_paragraph_elements(text):
            if para_index == heading_index:
                return text.createTextCursorByRange(element.getStart())
            para_index += 1
        cursor = text.createTextCursor()
        cursor.gotoStart(False)
        return cursor

    def _insertion_cursor_at_end(self) -> Any:
        """A collapsed Writer cursor at the document end (append), on a fresh paragraph."""
        text = self.model.getText()
        cursor = text.createTextCursor()
        cursor.gotoEnd(False)
        # If the doc is non-empty, move to a fresh paragraph at the end so the new
        # chapter starts on its own paragraph (no trailing-text append).
        try:
            has_any = any(True for _ in _iter_paragraph_elements(text))
            if has_any:
                text.insertControlCharacter(cursor, _PARAGRAPH_BREAK, False)
                cursor.gotoEnd(False)
        except Exception:
            pass
        return cursor

    def _clear_block(self, heading_index: int) -> None:
        """Remove the chapter's old block paragraphs from the document when replacing.

        Walks the document once from the located heading to just before the next heading
        (or end of document), deleting in reverse so earlier paragraph indexes stay valid.
        """
        text = self.model.getText()
        paras = list(_iter_paragraph_elements(text))
        if not (0 <= heading_index < len(paras)):
            return
        end = len(paras)
        for i in range(heading_index + 1, len(paras)):
            if paragraph_is_heading(paras[i]):
                end = i
                break
        for i in range(end - 1, heading_index, -1):
            try:
                text.removeTextRange(paras[i])
            except Exception:
                continue

    def _chapter_serial(self, chapter: CreatorChapter, artifacts: list[CreatorArtifact]) -> str:
        lines = [f"# {chapter.title.strip() or 'Untitled'}"]
        for a in (artifacts or []):
            if a.body.strip():
                lines.append(a.body)
        return "\n\n".join(lines)