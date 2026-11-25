# WriterAgent - AI Writing Assistant for LibreOffice
# Copyright (c) 2026 KeithCu (modifications and relicensing)
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
"""Author IR — the Creator Studio's schema-validated, presentation-independent model.

This is the "intermediate representation" the Creator Studio keeps as its source of
truth, deliberately split from the live Writer document.  A scene can be *planned*,
*drafting* (the AI is typing into Writer right now), *drafted*, or *final*; a chapter
holds an outline and a list of scenes.  Nothing here imports UNO, so the whole model
is unit-testable without a running LibreOffice.

Kinds:

- ``novel``  — a book of chapters (scenes optional).
- ``book``   — same shape as a novel but with an explicit part/volume structure via
  chapter ``part`` labels (kept as one kind for simplicity).
- ``article``— a single long-form piece with sections instead of chapters.
- ``comics`` — a script with pages/panels; prose text lives in ``scene.body`` with a
  ``medium`` marker and per-panel image prompts in ``scene.panels``.

The IR intentionally does not store fonts/colors/layout: that is presentation, owned
by the Writer document and the Type System.  The IR stores *what* is being written,
not *how* it looks on the page.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

_SCHEMA_VERSION = 1


class CreatorArtifactKind(str, Enum):
    """The presentational *map* of an artifact onto Writer styles."""

    SCENE = "scene"
    QUOTE = "quote"
    CAPTION = "caption"
    PANEL = "panel"
    BEAT = "beat"

    @classmethod
    def _missing_(cls, value: object) -> "CreatorArtifactKind":
        return cls.SCENE


@dataclass
class CreatorProjectSettings:
    """Project-level configuration that feeds the writer agents."""

    title: str = "Untitled"
    kind: str = "novel"  # '', 'novel', 'book', 'article', 'comics'
    language: str = ""
    target_words: int = 0  # 0 = no explicit target
    tone: str = "formal"
    genre: str = ""

    def to_mapping(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "kind": self.kind,
            "language": self.language,
            "target_words": self.target_words,
            "tone": self.tone,
            "genre": self.genre,
        }

    @classmethod
    def from_mapping(cls, data: Any) -> "CreatorProjectSettings":
        d = data if isinstance(data, dict) else {}
        return cls(
            title=str(d.get("title") or "Untitled"),
            kind=str(d.get("kind") or "novel"),
            language=str(d.get("language") or ""),
            target_words=int(d.get("target_words") or 0),
            tone=str(d.get("tone") or "formal"),
            genre=str(d.get("genre") or ""),
        )


Scenes = list["CreatorArtifact"]

# An "artifact" is a unit of authored content.  For prose kinds a chapter is a
# collection of scenes; for comics a "chapter" is an issue and each scene a page.
@dataclass
class CreatorArtifact:
    """A unit of authored content inside a chapter.

    ``body`` is plain prose (the IR text).  ``kind`` tags the artifact type so a
    presenter can map it onto Writer styles (Body Text, Quote, Caption, etc.) but
    the IR never stores the style itself.  ``panels`` is used for comics.
    """

    id: str
    body: str = ""
    kind: str = "scene"  # scene | quote | caption | panel | beat
    status: str = "planned"  # planned | drafting | drafted | final
    summary: str = ""
    panels: list[dict[str, Any]] = field(default_factory=list)  # comics only

    def to_mapping(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "body": self.body,
            "kind": self.kind,
            "status": self.status,
            "summary": self.summary,
            "panels": self.panels,
        }

    @classmethod
    def from_mapping(cls, data: Any) -> "CreatorArtifact":
        d = data if isinstance(data, dict) else {}
        return cls(
            id=str(d.get("id") or ""),
            body=str(d.get("body") or ""),
            kind=str(d.get("kind") or "scene"),
            status=str(d.get("status") or "planned"),
            summary=str(d.get("summary") or ""),
            panels=list(d.get("panels") or []),
        )


@dataclass
class CreatorChapter:
    """A chapter (novel/book), section (article) or issue (comics)."""

    id: str
    title: str = ""
    part: str = ""  # optional part/volume label for book kinds
    status: str = "planned"  # planned | drafting | drafted | final
    summary: str = ""
    scenes: Scenes = field(default_factory=list)
    characters: list[str] = field(default_factory=list)

    @property
    def text(self) -> str:
        """Concatenated prose of all scenes (the IR's canonical plain text)."""
        return "\n\n".join(a.body for a in self.scenes if a.body.strip())

    def to_mapping(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "part": self.part,
            "status": self.status,
            "summary": self.summary,
            "scenes": [a.to_mapping() for a in self.scenes],
            "characters": list(self.characters),
        }

    @classmethod
    def from_mapping(cls, data: Any) -> "CreatorChapter":
        d = data if isinstance(data, dict) else {}
        return cls(
            id=str(d.get("id") or ""),
            title=str(d.get("title") or ""),
            part=str(d.get("part") or ""),
            status=str(d.get("status") or "planned"),
            summary=str(d.get("summary") or ""),
            scenes=[CreatorArtifact.from_mapping(s) for s in (d.get("scenes") or [])],
            characters=[str(c) for c in (d.get("characters") or [])],
        )


@dataclass
class CreatorSceneState:
    """Author note about the world state entering/leaving a scene (mystery/continuity)."""

    id: str
    chapter_id: str = ""
    entering: list[str] = field(default_factory=list)
    exit: list[str] = field(default_factory=list)
    forbidden: list[str] = field(default_factory=list)

    def to_mapping(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "chapter_id": self.chapter_id,
            "entering": list(self.entering),
            "exit": list(self.exit),
            "forbidden": list(self.forbidden),
        }

    @classmethod
    def from_mapping(cls, data: Any) -> "CreatorSceneState":
        d = data if isinstance(data, dict) else {}
        return cls(
            id=str(d.get("id") or ""),
            chapter_id=str(d.get("chapter_id") or ""),
            entering=[str(x) for x in (d.get("entering") or [])],
            exit=[str(x) for x in (d.get("exit") or [])],
            forbidden=[str(x) for x in (d.get("forbidden") or [])],
        )


@dataclass
class CreatorProject:
    """The whole Author IR for one Creator Studio project."""

    schema_version: int = _SCHEMA_VERSION
    settings: CreatorProjectSettings = field(default_factory=CreatorProjectSettings)
    chapters: list[CreatorChapter] = field(default_factory=list)
    scene_states: list[CreatorSceneState] = field(default_factory=list)
    characters: list[dict[str, Any]] = field(default_factory=list)
    timeline: list[dict[str, Any]] = field(default_factory=list)
    brief: str = ""
    author_notes: str = ""

    def chapter(self, chapter_id: str) -> CreatorChapter | None:
        for c in self.chapters:
            if c.id == chapter_id:
                return c
        return None

    def summary(self) -> dict[str, Any]:
        return {
            "title": self.settings.title,
            "kind": self.settings.kind,
            "chapters": len(self.chapters),
            "words": sum(len(c.text.split()) for c in self.chapters),
        }

    def to_mapping(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "settings": self.settings.to_mapping(),
            "chapters": [c.to_mapping() for c in self.chapters],
            "scene_states": [s.to_mapping() for s in self.scene_states],
            "characters": list(self.characters),
            "timeline": list(self.timeline),
            "brief": self.brief,
            "author_notes": self.author_notes,
        }

    @classmethod
    def from_mapping(cls, data: Any) -> "CreatorProject":
        d = data if isinstance(data, dict) else {}
        return cls(
            schema_version=int(d.get("schema_version") or _SCHEMA_VERSION),
            settings=CreatorProjectSettings.from_mapping(d.get("settings")),
            chapters=[CreatorChapter.from_mapping(c) for c in (d.get("chapters") or [])],
            scene_states=[CreatorSceneState.from_mapping(s) for s in (d.get("scene_states") or [])],
            characters=[dict(r) for r in (d.get("characters") or [])],
            timeline=[dict(r) for r in (d.get("timeline") or [])],
            brief=str(d.get("brief") or ""),
            author_notes=str(d.get("author_notes") or ""),
        )


def creator_project_from_mapping(data: Any) -> CreatorProject:
    """Validate + construct a CreatorProject from arbitrary JSON-like input.

    Raises :class:`ValueError` on structural problems (missing chapter ids,
    duplicate ids, scenes without ids).
    """
    project = CreatorProject.from_mapping(data)
    seen: set[str] = set()
    for c in project.chapters:
        if not c.id:
            raise ValueError("creator: chapter missing id")
        if c.id in seen:
            raise ValueError(f"creator: duplicate chapter id {c.id!r}")
        seen.add(c.id)
        c_seen: set[str] = set()
        for a in c.scenes:
            if not a.id:
                raise ValueError("creator: artifact missing id")
            if a.id in c_seen:
                raise ValueError(f"creator: duplicate artifact id {a.id!r}")
            c_seen.add(a.id)
    return project


def chapter_ready_to_draft(chapter: CreatorChapter) -> bool:
    """A chapter can be drafted when it has an outline (title/summary) and no scene
    is currently drafting (only one stream at a time)."""
    if chapter.status == "final":
        return False
    if chapter.status == "drafting":
        return False
    return bool(chapter.title.strip()) or bool(chapter.summary.strip())