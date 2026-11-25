# WriterAgent - AI Writing Assistant for LibreOffice
# Copyright (c) 2026 KeithCu (modifications and relicensing)
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
"""Creator Studio — agentic long-form writing into a live Writer document.

The Creator Studio is the AAF ``delta`` over the WriterAgent extension: it turns
the existing streamed ``WriterStreamedRewriteSession`` / ``WriterStreamedAppendSession``
and content tools into a document-level "writer studio".  The user watches the AI
type into the live Writer document while the Author (IR) representation stays the
source of truth and is two-way synced with the presentation.

Modules (dependency order, small on purpose):

- ``model``   — Author IR: schema-validated, serializable project model
                (novel / book / article / comics) split from presentation.
- ``store``   — revisioned project-store persistence for the Author IR.
- ``sync``    — two-way IR <-> live Writer sync (read Writer -> IR; push IR ->
                Writer paragraph by paragraph through the real binding; guards against
                clobbering the user's own edits).
- ``orchestrator`` — the agentic writing loop: pick the next chapter, run a writer
                agent with IR context, stream into the live Writer document, then
                reconcile the IR.
- ``inject``  — the user injection surface: pause / resume the stream, restyle the
                just-typed range, insert an image, or rewrite the paragraph with a
                different agent mid-stream.
- ``tools``   — expose the Creator Studio as WriterAgent chat / MCP tools.
- ``deck``    — the sidecar controller deck (watch typing + inject).

The IR and the Writer document are deliberately separate: the IR survives restarts
in its own store and is bidirectionally reconciled, so the model never chases a
transient presentation state.
"""

from .model import (
    CreatorArtifact,
    CreatorArtifactKind,
    CreatorChapter,
    CreatorProject,
    CreatorProjectSettings,
    CreatorSceneState,
    chapter_ready_to_draft,
    creator_project_from_mapping,
)
from .store import CreatorStore, CreatorStoreError, load_project_store, save_project_store
from .sync import (
    ChapterAnchor,
    IrWriterSync,
    LoadOutcome,
    PushOutcome,
)
from .orchestrator import (
    CreatorOrchestrator,
    CreatorRuntime,
)
from .inject import (
    pause_stream,
    resume_stream,
    rewrite_paragraph_with_agent,
    stop_stream,
)
from .deck import (
    CreatorDeckState,
    CreatorDeckView,
)
from .registry import (
    active_orchestrator,
    clear_orchestrator,
    get_orchestrator,
    set_orchestrator,
)

__all__ = [
    "CreatorArtifact",
    "CreatorArtifactKind",
    "CreatorChapter",
    "CreatorProject",
    "CreatorProjectSettings",
    "CreatorSceneState",
    "creator_project_from_mapping",
    "CreatorStore",
    "CreatorStoreError",
    "load_project_store",
    "save_project_store",
    "ChapterAnchor",
    "IrWriterSync",
    "LoadOutcome",
    "PushOutcome",
    "CreatorOrchestrator",
    "CreatorRuntime",
    "chapter_ready_to_draft",
    "pause_stream",
    "resume_stream",
    "rewrite_paragraph_with_agent",
    "stop_stream",
    "CreatorDeckState",
    "CreatorDeckView",
    "active_orchestrator",
    "clear_orchestrator",
    "get_orchestrator",
    "set_orchestrator",
]