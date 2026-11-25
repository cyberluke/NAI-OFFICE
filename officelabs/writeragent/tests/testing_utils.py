# WriterAgent - AI Writing Assistant for LibreOffice
#
# SPDX-License-Identifier: GPL-3.0-or-later
"""Shared utilities for the native (UNO) test runner.

``plugin/testing_runner.py`` imports this module to track cross-suite state that must
survive between native tests run in one LibreOffice process:

- ``_NATIVE_DOC_POOL`` — pooled native documents the runner may clear between suites so
  a test cannot leak a document into the next suite.
- ``set_harness_keeper_uid(uid, doc)`` — records the persistent "keeper" (template)
  document the harness keeps open, keyed by its UID.
- ``set_windows_notebook_host(on)`` — toggles the flag that isolates
  ``test_notebook_runner_uno`` / ``test_writer_importer_uno`` suites on a dedicated
  notebook host (a LibreOffice quirk where leftover HTML-paste Writers force Writer
  reuse into the notebook runner; see testing_runner line ~1505).
- ``NATIVE_TEST_SYS_MODULE_SNAPSHOT_KEYS`` — the ``sys.modules`` keys the runner
  snapshots between tests so a test cannot mutate extension module state and bleed it
  into the next test.

This is the canonical native-harness companion module this checkout requires; it
contains no product logic and is only imported by ``plugin/testing_runner.py``.
"""

from __future__ import annotations

import threading
from typing import Any

#: Pool of native Writer documents created for (and reused by) native tests.  The
#: native runner clears it between suites so a stray document cannot leak across suites.
_NATIVE_DOC_POOL: list[Any] = []

_lock = threading.Lock()

#: The persistent "keeper" document + its RuntimeUID, so the harness can identify the
#: document any repeated reuse is anchored to.
_harness_keeper_uid: str = ""
_harness_keeper_doc: Any = None


def set_harness_keeper_uid(uid: str, doc: Any) -> None:
    """Record the runtime's persistent keeper document (by UID) for the harness."""
    global _harness_keeper_uid, _harness_keeper_doc
    with _lock:
        _harness_keeper_uid = uid
        _harness_keeper_doc = doc


def get_harness_keeper_uid() -> str:
    with _lock:
        return _harness_keeper_uid


#: True while the harness is running a suite that must be isolated on the dedicated
#: Windows "notebook" document host (HTML-paste writer suites).  See testing_runner.
_wa_notebook_host = False


def set_windows_notebook_host(on: bool) -> None:
    """Toggle the dedicated notebook-host isolation flag for the current suite."""
    global _wa_notebook_host
    with _lock:
        _wa_notebook_host = bool(on)


def windows_notebook_host() -> bool:
    with _lock:
        return _wa_notebook_host


#: Keys the native runner snapshots in ``sys.modules`` before and restores after each
#: native test, so a test that mutates extension module state cannot bleed into the next
#: test.  The extension's own package roots plus the UNO bridge stays stable across runs.
NATIVE_TEST_SYS_MODULE_SNAPSHOT_KEYS: tuple[str, ...] = (
    "plugin",
    "plugin.framework",
    "plugin.writer",
    "plugin.writer.creator",
    "uno",
    "com.sun.star",
)