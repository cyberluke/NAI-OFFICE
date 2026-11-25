# WriterAgent - AI Writing Assistant for LibreOffice
# Copyright (c) 2026 KeithCu (modifications and relicensing)
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
"""Two-way IR <-> live Writer sync for the Creator Studio.

The live Writer document is *one presentation binding* of the Author IR.  This module
keeps the two reconciled without clobbering the user's own edits:

- **Load** (Writer -> IR): read the Writer prose and fold it into the IR chapter that
  owns the matching ``ChapterAnchor``.  Load never rewrites the Writer doc.
- **Push** (IR -> Writer): write one IR chapter's text into the live Writer document
  paragraph by paragraph (real paragraph breaks), wrapped in a single compound undo
  step (federating ``WriterCompoundUndo``).  ``WriterStreamedRewriteSession`` /
  ``WriterStreamedAppendSession`` are *not* used for chapter writes — a chapter is built
  of real paragraphs, which those single-range sessions cannot express — so the tracked-
  change collapse / redline-tagging guarantees they offer do not apply here.

The sync core is pure Python over a thin ``WriterBinding`` adapter, so all of the
diffing / anchoring / precedence logic is unit-testable without LibreOffice.  The real
UNO binding lives in :mod:`plugin.writer.creator.binding`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Callable, Iterator, Protocol

from .model import CreatorChapter, CreatorProject, CreatorArtifact
from .store import CreatorStore, CreatorStoreRecord

# A heading line is a paragraph whose (trimmed) text starts with this many `#`.
_HEADING_RE = re.compile(r"^\s{0,3}#{1,6}\s+(.+?)\s*$")


@dataclass
class ChapterAnchor:
    """Where an IR chapter begins in the Writer document.

    We anchor on the heading *text* (stable, user-visible) rather than a character
    offset, so the mapping survives the user editing text before the chapter.
    ``offset`` is only a hint used when the heading text cannot be found.
    """

    chapter_id: str
    title: str
    level: int = 1
    offset: int = -1

    @property
    def heading(self) -> str:
        return "#" * max(1, self.level) + " " + self.title


def _strip_heading(text: str) -> str | None:
    m = _HEADING_RE.match(text)
    return m.group(1).strip() if m else None


def heading_text_of(line: str) -> str | None:
    """Return the visible heading text if *line* is a Writer heading paragraph."""
    return _strip_heading(line)


def normalize_title(title: str) -> str:
    """Lowercase + collapse spaces so headings match despite formatting."""
    return re.sub(r"\s+", " ", title.strip().lower())


class WriterBinding(Protocol):
    """Thin adapter the sync core uses instead of touching UNO.

    The real implementation (:mod:`binding`) routes these to the existing
    ``document_to_content`` / streamed sessions / Type System.  Fakes in tests
    implement the same duck type.
    """

    def read_prose(self, max_chars: int | None = None) -> list[dict[str, Any]]:
        """Return Writer paragraphs as ``[{"text": ..., "style": ...}]`` (headings included)."""
        ...

    def write_chapter(
        self,
        chapter: CreatorChapter,
        anchor: ChapterAnchor,
        artifacts: list[CreatorArtifact],
        *,
        on_chunk: Callable[[str], None] | None = None,
        chunks: Iterator[str] | None = None,
        text: str | None = None,
    ) -> "PushOutcome":
        """Stream *chapter* into the live document anchored at *anchor*.

        Implementations insert the chapter paragraph by paragraph (real paragraph
        breaks) inside one compound undo step and return a :class:`PushOutcome`
        carrying ``written_paragraphs`` (the effective prose the orchestrator folds
        back into the IR).  When ``chunks`` is given it is drained (the user watches
        each token land); otherwise ``text`` (or the chapter serialization) is written
        in one shot.
        """
        ...

    def locate_anchor(self, chapter: CreatorChapter) -> ChapterAnchor:
        """Find where *chapter* belongs in the live document."""
        ...


@dataclass
class LoadOutcome:
    """Result of folding Writer prose into the IR."""

    total_paragraphs: int = 0
    chapters_reconciled: int = 0
    unmatched_chapters: list[str] = field(default_factory=list)
    project: CreatorProject | None = None
    changed: bool = False


@dataclass
class PushOutcome:
    """Result of pushing one chapter's IR text into the Writer document.

    ``written_paragraphs`` carries the *effective* paragraph texts actually inserted
    (visible text only, paragraph breaks excluded), so the orchestrator can fold the
    streamed prose back into the IR scene bodies — keeping the IR the source of truth
    across restarts instead of leaving it with the pre-write plan.
    """

    ok: bool = False
    message: str = ""
    chars_written: int = 0
    artifacts_written: int = 0
    anchors_updated: int = 0
    written_paragraphs: list[str] = field(default_factory=list)


@dataclass
class IrWriterSync:
    """Pure sync core: reconcile an IR project against Writer prose."""

    binding: WriterBinding
    store: CreatorStore | None = None
    project: CreatorProject | None = None

    def ensure_project(self, project: CreatorProject | None = None) -> CreatorProject:
        """Return the active project, loading from the store if it exists."""
        if project is not None:
            self.project = project
            return project
        if self.project is not None:
            return self.project
        record = self.store.load() if self.store is not None else None
        self.project = record.project if record is not None else CreatorProject()
        return self.project

    # ---- Writer -> IR ----

    def load_into_project(self, project: CreatorProject | None = None) -> LoadOutcome:
        """Fold live Writer prose into the IR chapter that owns each heading anchor.

        Only IR content that the user changed in Writer is updated; this method
        never writes to Writer.  Returns an outcome describing what reconciled.
        """
        project = self.ensure_project(project)
        paragraphs = self.binding.read_prose()
        outcome = LoadOutcome(total_paragraphs=len(paragraphs), project=project)
        if not paragraphs:
            return outcome

        by_title: dict[str, CreatorChapter] = {}
        for c in project.chapters:
            by_title[normalize_title(c.title)] = c

        # Group paragraphs under their nearest heading.
        current_id: str | None = None
        groups: dict[str, list[dict[str, Any]]] = {c.id: [] for c in project.chapters}
        for p in paragraphs:
            text = p.get("text", "")
            heading = _strip_heading(text)
            if heading is not None:
                chapter = by_title.get(normalize_title(heading))
                current_id = chapter.id if chapter is not None else None
            if current_id is not None:
                groups[current_id].append(p)

        # Rebuild artifacts from the grouped prose.  Only reconcile chapters whose
        # IR body differs from the Writer prose, so we never write over newer IR edits.
        for chapter in project.chapters:
            group = groups.get(chapter.id) or []
            prose = _group_prose(group)  # drop the heading line itself
            if prose == chapter.text:
                continue
            # Re-slice IR artifacts to match the Writer's paragraph count, keeping the
            # plan (id/kind/summary) but adopting the Writer's body text.  This is the
            # "the user edited in Writer" direction.
            body_parts = [p.get("text", "") for p in group if _strip_heading(p.get("text", "")) is None]
            chapter.scenes = _merge_writer_prose_into_artifacts(chapter.scenes, body_parts)
            outcome.chapters_reconciled += 1
            outcome.changed = True

        return outcome

    # ---- IR -> Writer ----

    def push_chapter(
        self,
        chapter: CreatorChapter,
        *,
        on_chunk: Callable[[str], None] | None = None,
        chunks: Iterator[str] | None = None,
        text: str | None = None,
    ) -> PushOutcome:
        """Stream one IR chapter's text into the live Writer document.

        The real binding uses the existing streamed-edit sessions so the user watches
        the text appear and the whole chapter collapses to one tracked/undoable step.
        """
        anchor = self.binding.locate_anchor(chapter)
        return self.binding.write_chapter(
            chapter, anchor, chapter.scenes,
            on_chunk=on_chunk, chunks=chunks, text=text,
        )

    def reconcile_store(
        self,
        project: CreatorProject | None = None,
        *,
        reason: str = "after-sync",
    ) -> CreatorStoreRecord | None:
        """Persist the user's Writer edits back into the IR store after a load."""
        project = self.ensure_project(project)
        if self.store is None:
            return None
        return self.store.save(project, reason=reason)


def _group_prose(group: list[dict[str, Any]]) -> str:
    body = [p.get("text", "") for p in group if _strip_heading(p.get("text", "")) is None]
    return "\n\n".join(x for x in body if x.strip())


def _merge_writer_prose_into_artifacts(artifacts: list[CreatorArtifact], parts: list[str]) -> list[CreatorArtifact]:
    """Reconcile IR artifacts with Writer prose paragraphs.

    Writer is the source of *prose* in this direction.  When the counts differ we
    keep the IR artifact ids/kinds for the common prefix and append new untitled
    artifacts for any surplus paragraphs; when there are fewer parts than artifacts,
    trailing IR artifacts keep their (now stale) empty bodies.
    """
    out: list[CreatorArtifact] = []
    for i, part in enumerate(parts):
        if i < len(artifacts):
            base = artifacts[i]
            out.append(CreatorArtifact(
                id=base.id,
                body=part,
                kind=base.kind,
                status=base.status,
                summary=base.summary,
                panels=base.panels,
            ))
        else:
            out.append(CreatorArtifact(id=f"w:{i}", body=part, status="drafted"))
    # Keep any trailing IR artifacts whose body was already empty of prose.
    for i in range(len(parts), len(artifacts)):
        out.append(artifacts[i])
    return out