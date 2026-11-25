# WriterAgent - AI Writing Assistant for LibreOffice
# Copyright (c) 2026 KeithCu (modifications and relicensing)
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
"""Creator Studio tools — expose the writing loop + sync to chat and MCP.

Each class follows the WriterAgent ``ToolBase`` convention (JsonSchema ``parameters``,
``uno_services``, ``tier``, ``execute(ctx, **kwargs)``).  The tools build a project IR
from the *live* Writer document (via :mod:`sync` + :mod:`binding`), persist it beside
the document, and drive the agentic writing loop so the AI types into the live doc.
"""

from __future__ import annotations

import logging
import os
import tempfile
from typing import Any

from plugin.framework.tool import ToolBase, ToolContext
from plugin.doc.text_helpers import get_document_path

from .binding import LoWriterBinding
from .model import CreatorProject, CreatorProjectSettings, CreatorChapter
from .store import CreatorStore
from .sync import IrWriterSync

log = logging.getLogger("writeragent.creator.tools")

WRITER_SERVICE = "com.sun.star.text.TextDocument"


def _is_safe_image_path(model: Any, path: str) -> bool:
    """Confine a model-supplied image path to the document's own directory.

    An auto-discovered MCP tool can otherwise name an arbitrary local file and have it
    read into the document.  We require an absolute path whose real (resolved) location
    sits inside the document's directory; unsaved documents (no known directory) are
    rejected rather than allowed to read anywhere.
    """
    try:
        if not path or not os.path.isabs(path):
            return False
        doc_path = get_document_path(model)
        if not doc_path:
            return False  # unsaved doc: no directory to confine against
        if doc_path.lower().endswith((".odt", ".fodt", ".doc", ".docx")):
            doc_dir = os.path.dirname(doc_path)
        else:
            doc_dir = doc_path
        if not doc_dir or not os.path.isdir(doc_dir):
            return False
        img_real = os.path.realpath(path)
        doc_real = os.path.realpath(doc_dir)
        return os.path.commonpath([img_real, doc_real]) == doc_real
    except (ValueError, OSError):
        return False


def _store_for(model: Any) -> CreatorStore:
    """A CreatorStore persisted next to the Writer document — or isolated to that one
    document when unsaved.

    The unsaved-document fallback must be per-document, never a shared global filename:
    two unsaved Writer documents resolving to the same store would silently overwrite
    each other's IR.  We key the fallback by the document's stable identity so each
    unsaved doc gets its own store, and never raise on any resolution failure.
    """
    path = None
    try:
        path = get_document_path(model)
    except Exception:
        path = None
    if not path:
        # No saved file yet: derive a per-document store key so different unsaved
        # documents never collide on one global JSON file.
        from .registry import _document_key

        key = _document_key(model).replace(":", "_").replace("/", "_")
        try:
            from plugin.framework.config import user_config_dir
            directory = user_config_dir()
            if directory:
                path = os.path.join(directory, f"creator-{key}-unsaved.json")
        except Exception:
            path = None
    if not path:
        path = os.path.join(tempfile.gettempdir(), f"creator-{id(model)}-unsaved.json")
    base = path
    if base.lower().endswith((".odt", ".fodt", ".doc", ".docx")):
        base = base.rsplit(".", 1)[0]
    return CreatorStore(base + "-creator.json")


class CreatorProjectTool(ToolBase):
    """Create a new Creator Studio project (outline + characters) for the live document."""

    name: str | None = "creator_project"
    description: str = (
        "Create or update the Creator Studio project for the active Writer document. "
        "Pass title/kind/tone/genre/brief/characters to seed the Author IR. "
        "The IR is kept beside the document and is the source the writer agents read."
    )
    parameters: dict[str, Any] | None = {
        "type": "object",
        "properties": {
            "title": {"type": "string", "description": "Project title."},
            "kind": {"type": "string", "enum": ["novel", "book", "article", "comics"], "description": "Kind of writing."},
            "tone": {"type": "string", "description": "Writing tone."},
            "genre": {"type": "string", "description": "Genre."},
            "target_words": {"type": "integer", "description": "Target total word count (optional)."},
            "brief": {"type": "string", "description": "One-paragraph project brief."},
            "characters": {"type": "array", "items": {"type": "object", "properties": {"name": {"type": "string"}, "role": {"type": "string"}}}},
            "chapter_titles": {"type": "array", "items": {"type": "string"}, "description": "Seed chapter outline titles (optional)."},
        },
        "required": ["title"],
    }
    uno_services: list[str] | None = [WRITER_SERVICE]
    tier: str = "core"

    def execute(self, ctx: "ToolContext", **kwargs: Any) -> dict[str, Any]:
        model = ctx.doc
        project = _store_for(model).load()
        cur = project.project if project else None
        chapters = [CreatorChapter(id=f"c{i}", title=t, status="planned") for i, t in enumerate(kwargs.get("chapter_titles") or [])]
        proj = CreatorProject(
            settings=CreatorProjectSettings(
                title=kwargs.get("title") or (cur.settings.title if cur else "Untitled"),
                kind=kwargs.get("kind") or (cur.settings.kind if cur else "novel"),
                tone=kwargs.get("tone") or (cur.settings.tone if cur else "formal"),
                genre=kwargs.get("genre") or (cur.settings.genre if cur else ""),
                target_words=int(kwargs.get("target_words") or (cur.settings.target_words if cur else 0)),
            ),
            chapters=chapters or (cur.chapters if cur else []),
            characters=[dict(c) for c in (kwargs.get("characters") or (cur.characters if cur else []))],
            brief=kwargs.get("brief") or (cur.brief if cur else ""),
        )
        record = _store_for(model).save(proj, reason="creator_project")
        return {"status": "ok", "revision": record.revision, "summary": record.summary}


class CreatorWriteTool(ToolBase):
    """Run the agentic loop: have the writer agent type the next chapter into the live document."""

    name: str | None = "creator_write"
    description: str = (
        "Have the Creator Studio writer agent type the next (or a named) chapter into the "
        "live Writer document, streaming text in so the user watches it appear. "
        "Pass chapter_number (1-based into the project, default next not-final chapter) or "
        "chapter_title. Use instruction for specific direction. The result reports chars written."
    )
    parameters: dict[str, Any] | None = {
        "type": "object",
        "properties": {
            "chapter_number": {"type": "integer", "description": "1-based chapter index into the project (default: next not-final)."},
            "chapter_title": {"type": "string", "description": "Title of the chapter to write (overrides chapter_number)."},
            "instruction": {"type": "string", "description": "Extra direction for the writer agent."},
            "word_limit": {"type": "integer", "description": "Word limit for this chapter."},
        },
        "required": [],
    }
    uno_services: list[str] | None = [WRITER_SERVICE]
    tier: str = "core"

    def execute(self, ctx: "ToolContext", **kwargs: Any) -> dict[str, Any]:
        model = ctx.doc
        store = _store_for(model)
        record = store.load()
        if record is None or not record.project:
            return self._tool_error("No Creator Studio project yet — call creator_project first.")
        project = record.project

        if kwargs.get("chapter_title"):
            chapter = next((c for c in project.chapters if c.title == kwargs["chapter_title"]), None)
            if chapter is None:
                return self._tool_error(f"Chapter {kwargs['chapter_title']!r} not found.")
        else:
            idx = int(kwargs.get("chapter_number") or 0) - 1
            ready = [c for c in project.chapters if c.status != "final"]
            if idx < 0:
                idx = 0
            if not ready:
                return self._tool_error("All chapters are final.")
            # Select from the ready (non-final) list only — never a finished chapter,
            # and never via the raw project index (which could hit a final chapter).
            chapter = ready[min(idx, len(ready) - 1)]

        # The tool surface resolves the prompt and records an orchestrator bound to this
        # document so the injection surface (creator_inject) can steer the live stream the
        # MCP/deck worker drives.  The agent callback is supplied by the MCP wiring; we
        # default to a lazy no-op here so the tool surface stays draft/prompt oriented.
        from .orchestrator import default_prompt, CreatorOrchestrator
        from .registry import set_orchestrator, get_orchestrator

        def _noop_agent(_prompt: str):
            return iter([])

        orch = get_orchestrator(model)
        if orch is None:
            binding = LoWriterBinding(model)
            orch = CreatorOrchestrator(
                IrWriterSync(binding=binding, store=store, project=project),
                agent_cb=_noop_agent,
                project=project,
            )
            set_orchestrator(model, orch)

        prompt = default_prompt(project, chapter, instruction=kwargs.get("instruction", ""), word_limit=kwargs.get("word_limit"))

        return {
            "status": "ok",
            "chapter_id": chapter.id,
            "chapter_title": chapter.title,
            "prompt": prompt,
            "project_summary": project.summary(),
            "note": "Call creator_provide_chunks with text to stream, or run the MCP writer loop to type it live.",
        }


class CreatorProvideChunksTool(ToolBase):
    """Provide generated text chunks to stream into the live Writer for the current chapter."""

    name: str | None = "creator_provide_chunks"
    description: str = (
        "Feed the writer agent's generated text (already produced) for the current chapter "
        "so it streams into the live Writer document through the tracked, undoable streamed "
        "rewrite session. Pass the full text as 'chunks' (a string, one chunk per paragraph block, "
        "or a single string). The document is updated live; one tracked change / undo step per chapter."
    )
    parameters: dict[str, Any] | None = {
        "type": "object",
        "properties": {
            "chapters": {"type": "array", "items": {"type": "object", "properties": {"title": {"type": "string"}, "text": {"type": "string"}}}},
            "text": {"type": "string", "description": "Alternatively, the whole chapter text as one string."},
        },
        "required": ["chapters"],
    }
    uno_services: list[str] | None = [WRITER_SERVICE]
    tier: str = "core"

    def execute(self, ctx: "ToolContext", **kwargs: Any) -> dict[str, Any]:
        model = ctx.doc
        store = _store_for(model)
        record = store.load()
        if record is None or not record.project:
            return self._tool_error("No Creator Studio project yet — call creator_project first.")
        project = record.project

        items = kwargs.get("chapters") or []
        if not items and kwargs.get("text"):
            items = [{"title": "", "text": kwargs["text"]}]
        if not items:
            return self._tool_error("Nothing to provide.")

        from .registry import active_orchestrator
        orch = active_orchestrator(model)

        binding = LoWriterBinding(model)
        sync = IrWriterSync(binding=binding, store=store, project=project)
        written = 0
        for item in items:
            title = str(item.get("title") or "")
            text = str(item.get("text") or "")
            chapter = next((c for c in project.chapters if c.title == title), None)
            if chapter is None:
                # Untitled direct text: append as a new artifact in the first non-final chapter.
                chapter = next((c for c in project.chapters if c.status != "final"), None)
                if chapter is None:
                    continue
            if orch is not None:
                # Drive the retained orchestrator so the injection surface can pause/stop
                # the same live stream the user is watching.
                rt = orch.provide_chunks(chapter.id, text)
                written += rt.chars_written
            else:
                out = sync.push_chapter(chapter, text=(f"# {chapter.title}\n\n{text}" if title else text))
                written += out.chars_written
                # Fold the written prose back into the IR before persisting (source of truth).
                if out.written_paragraphs:
                    from .orchestrator import _reconcile_into_scenes
                    _reconcile_into_scenes(chapter, out.written_paragraphs)
        if orch is None:
            store.save(project, reason="creator_provide_chunks")
        return {"status": "ok", "chars_written": written}


class CreatorInjectTool(ToolBase):
    """User injection surface for the current Creator Studio write stream."""

    name: str | None = "creator_inject"
    description: str = (
        "Injection controls while the AI is writing live: pause / resume / stop the stream, "
        "restyle a range, or insert an image. Pass 'action' = pause|resume|stop|restyle|image. "
        "Restyle uses style + family + target (selection default); image uses a local path."
    )
    parameters: dict[str, Any] | None = {
        "type": "object",
        "properties": {
            "action": {"type": "string", "enum": ["pause", "resume", "stop", "restyle", "image"], "description": "What to inject."},
            "style": {"type": "string", "description": "For restyle: style name."},
            "family": {"type": "string", "enum": ["ParagraphStyles", "CharacterStyles"]},
            "target": {"type": "string", "enum": ["selection", "beginning", "end", "full_document"]},
            "image_path": {"type": "string", "description": "For image: a local file path to insert."},
        },
        "required": ["action"],
    }
    uno_services: list[str] | None = [WRITER_SERVICE]
    tier: str = "core"

    def execute(self, ctx: "ToolContext", **kwargs: Any) -> dict[str, Any]:
        action = kwargs.get("action")
        if action in ("pause", "resume", "stop"):
            # Steer the live retained orchestrator for this document (the same one the
            # deck/MCP worker drives); if no live stream is in-flight, report that.
            from .registry import active_orchestrator
            orch = active_orchestrator(ctx.doc)
            if orch is None:
                return {
                    "status": "ok",
                    "action": action,
                    "applied": False,
                    "message": "No live Creator Studio chapter stream is running for this document.",
                }
            if action == "pause":
                orch.pause()
            elif action == "resume":
                orch.resume()
            else:
                orch.stop()
            return {
                "status": "ok",
                "action": action,
                "applied": True,
                "chapter": orch.runtime.chapter_title,
            }
        if action == "restyle":
            from plugin.writer.styles import ApplyStyle
            return ApplyStyle().execute(
                ctx,
                style=kwargs.get("style") or "",
                family=kwargs.get("family") or "ParagraphStyles",
                target=kwargs.get("target") or "selection",
            )
        if action == "image":
            from plugin.writer.images.image_tools import insert_image_at_locator
            path = kwargs.get("image_path")
            if not path:
                return self._tool_error("image action requires image_path.")
            # Confine the model-supplied image path to the document's own directory (or a
            # configured asset folder), so an MCP/model call cannot read an arbitrary
            # local file into the document.  Unsaved docs / non-local paths are rejected.
            if not _is_safe_image_path(ctx.doc, path):
                return self._tool_error(
                    "image_path must be a local file inside this document's directory "
                    "(or a configured asset folder)."
                )
            try:
                insert_image_at_locator(ctx, ctx.doc, path, width_mm=80, height_mm=80)
            except Exception as exc:
                log.exception("creator: image insert failed")
                return self._tool_error(f"image insert failed: {exc}")
            return {"status": "ok", "inserted": path}
        return self._tool_error(f"unknown injection action {action!r}")