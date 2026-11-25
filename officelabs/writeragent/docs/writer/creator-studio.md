# Creator Studio — agentic long-form writing into a live Writer document

The **Creator Studio** is the AAF delta over the WriterAgent extension: it turns the
existing streamed-edit infrastructure into a document-level "writer studio".  The user
watches the AI **type into the live Writer document** in real time, while the document's
**Author IR** (the structured representation of the novel / book / article / comics)
stays the source of truth and is **two-way synced** with the presentation.

> Why this design: the live Writer document is *one presentation binding*.  The IR
> survives restarts, keeps the outline/characters/scene-states the agents need, and is
> bidirectionally reconciled — so the studio never chases a transient presentation
> state, and the user can edit in Writer at any time without the next write stomping
> their words.

## Concepts

- **Author IR** (`plugin.writer.creator.model`) — schema-validated, serializable
  project model (project kind, chapters, scenes/artifacts, characters, scene-states,
  brief).  No fonts/colors/layout — those are presentation, owned by Writer + Type System.
- **CreatorStore** (`plugin.writer.creator.store`) — revisioned JSON persistence of the
  IR (checksummed, atomic writes) beside the document.
- **Two-way sync** (`plugin.writer.creator.sync` + `binding`) — read Writer prose into
  the IR (Writer→IR), and stream an IR chapter into the live Writer document (IR→Writer).
- **Orchestrator** (`plugin.writer.creator.orchestrator`) — the agentic writing loop:
  pick the next chapter, prompt the writer agent with IR context, stream the agent's
  output into Writer in chunks, then reconcile the IR.
- **Injection surface** (`plugin.writer.creator.inject`, `deck`) — pause/resume/stop the
  stream, restyle a range, insert an image, or rewrite a paragraph with another agent.
- **Tools** (`plugin.writer.creator.tools`) — expose the studio as chat/MCP tools.

## How it types into Writer

`LoWriterBinding.write_chapter` inserts the chapter **paragraph by paragraph** with real
Writer paragraph breaks (via `insertControlCharacter`, not `setString` which would create
soft line breaks).  Each generated token paints immediately — the user watches the AI type.
The whole chapter is wrapped in one **compound undo step** (federating
`WriterCompoundUndo`), so "one Ctrl+Z reverts the chapter" is preserved.

Chapters written with the `# Title` marker (or a Writer outline heading) register as
headings, so the sync can re-locate them later by heading text.

## Stream control / injection

A document-keyed **orchestrator registry** (`plugin.writer.creator.registry`) lets the
deck / MCP worker and the tool surface steer the *same* live write.  `CreatorInjectionTool`
resolves the retained orchestrator via `active_orchestrator` and calls
`orch.pause()/resume()/stop()`; `CreatorProvideChunksTool` drives the retained
orchestrator's `provide_chunks` so a fed chunk stream is pausable/steerable.

Between chunks the runtime checks a pause/cancel event pair:

```python
class CreatorRuntime:
    cancel_event  # stop
    pause_event   # pause / resume
```

`pause_stream` / `resume_stream` / `stop_stream` / `rewrite_paragraph_with_agent` are the
injection helpers; `CreatorDeckState` is the observable snapshot + command contract the UI
binds to.

### Safeguards

- **IR is the source of truth**: the streamed chapter prose is folded back into the IR
  scene bodies before persistence (`_reconcile_into_scenes`), so a restart does not lose
  what was typed.
- **Never clobber finished chapters**: `_pick_chapter` / `provide_chunks` refuse a
  `status == "final"` chapter; `creator_write` selects only from non-final chapters.
- **Image paths are confined**: `creator_inject` image requires a local path inside the
  document's own directory (rejects arbitrary model-supplied files).
- **Prompt injection guard**: IR/brief/character/chapter-summary content is wrapped in a
  `<untrusted_author_data>` block the writer agent treats strictly as data, not instructions.
- **Per-document stores**: an unsaved document's store is keyed by document identity, so
  two unsaved docs never collide on one shared JSON file.

## Enabling

The Creator Studio tools are auto-discovered with the Writer module
(`plugin.writer.__init__` → `services.tools.auto_discover_package("plugin.writer.creator")`):

| tool | purpose |
|---|---|
| `creator_project` | seed/update the IR (title, kind, tone, genre, brief, characters, chapter titles) |
| `creator_write` | prompt the writer agent for the next chapter (returns the prompt + project summary) |
| `creator_provide_chunks` | stream generated text into the live Writer doc as one tracked step |
| `creator_inject` | pause/resume/stop/restyle/image during a live write |

## Tests

- Pure IR/sync/orchestrator/inject/deck logic: `tests/writer/creator/test_*.py`
  (`make pytest`; they run under the `crosshair`-stub mechanism so no live LO is needed).
- Native Writer binding: `tests/writer/creator/test_creator_binding_uno.py`
  (`make test-uno`; creates a blank Writer and verifies streamed paragraphs land).
- Functional verification (no infra dependency): the flow in that `_uno` file was also
  driven against a headless LibreOffice in a standalone script that bootstraps via
  `officehelper`; see the commit message for the PASS result list (`RESULT: OK`).

## Layout

```
plugin/writer/creator/
  __init__.py      public exports (model, store, sync, binding, orchestrator, inject, deck, registry)
  model.py         Author IR (dataclasses + validation), novel/book/article/comics kinds
  store.py         revisioned JSON store (per-document)
  sync.py          pure two-way sync core over a WriterBinding adapter
  binding.py       real UNO WriterBinding (paragraph-aware streaming, single heading source)
  orchestrator.py  agentic writing loop + runtime state + provide_chunks
  inject.py        pause/resume/stop/rewrite-paragraph injection
  deck.py          observable deck state + command contract
  registry.py      document-keyed live-orchestrator registry (injection steering)
  tools.py         ToolBase surface for chat/MCP
```

## Invariants honoured

- No `SfxObjectShell::Current()` / document-global current-shell shortcuts; frame/model
  resolution comes through the caller's `ToolContext` / UNO model.
- Stream control is data-flow driven (no blocking UI thread); the binding runs on the
  UI/VCL thread like the rest of WriterAgent.
- The IR and the Writer document stay separate; a `load` never writes to Writer.
- No user-document text is logged (unchanged).