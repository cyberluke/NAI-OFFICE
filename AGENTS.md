# AGENTS.md — engineering rules for this repository

Rules that apply to every contributor and every automated agent working here.

## No scaffolding

- **No scaffolding.** Do not create placeholder, stub, mock, skeleton, or "scaffold"
  files, classes, functions, tests, harnesses, or UI resources that are not a real,
  working implementation.
- A scaffold is anything that looks like progress without delivering behavior: empty test
  modules, fake controllers, stubbed drawing surfaces, placeholder cards, "TODO later"
  handlers, synthetic mockups, or golden-image stand-ins that are not real captures.
- Every file added and every implementation step must be a concrete, functional,
  buildable part of the finished feature, and must be verified to work — not merely to
  compile.
- If a piece cannot be delivered as a real, verified implementation here, do not
  fabricate a scaffold for it. Report it as not implemented with the exact reason.

## Layering

- Keep document mutation in the application layer (`sw` for Writer, `sc` for Calc,
  `sd` for Draw/Impress). Keep reusable data structures and custom-drawn widgets in
  `svx`.
- Do not introduce circular dependencies between `sw` and `svx`.
- Features must consume the canonical document structures (paragraph/character styles,
  headings, tables, sections, images, footnotes) and the canonical dispatch path. No
  parallel document model.

## Framework APIs

- Do not use document-global "current shell" shortcuts
  (`SfxObjectShell::Current()`, `SwModule::GetFirstView()`, and equivalents). Resolve the
  owning frame explicitly.

## Logging and privacy

- Do not log user document text. Log operations, ids and counts only.

## Transactions

- Do not leave unbalanced `StartUndo`/`EndUndo` on exceptions.
- Never report a clean preset/apply when the operation failed.

## Honest status

Report exact status using these terms, and do not use them interchangeably:

- **COMPILED** — builds.
- **RUNTIME-WIRED** — code path is reachable at runtime.
- **FUNCTIONALLY-VERIFIED** — exercised against a real run.
- **VISUALLY-VERIFIED** — observed in the real UI.

If the build or test environment blocks verification, fix the blocker or report it as
blocked with the exact error. Do not claim PASS for anything not executed.
