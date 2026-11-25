# WriterAgent - AI Writing Assistant for LibreOffice
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
"""pytest fixtures for the Creator Studio pure-IR unit tests.

``plugin.writer.__init__`` skips its eager UNO imports when ``crosshair`` is present
in ``sys.modules`` (the project's documented pure-python test mechanism, used by the
CrossHair build).  Installing a stub lets the pure IR modules (model, store, sync,
orchestrator, inject) import and run under pytest without a live LibreOffice.
"""

from __future__ import annotations

import sys
import types
from typing import Any


def pytest_configure(config: Any) -> None:
    # Minimal, truthful stand-in so ``plugin.writer`` (and the creator package that
    # imports nothing UNO at module level in the pure modules) can load in pytest.
    if "crosshair" not in sys.modules:
        sys.modules["crosshair"] = types.ModuleType("crosshair")
    # ``plugin.framework.tool`` guards on ``com.sun.star`` imports for tools; the pure
    # creator tools import ToolBase lazily only from the bound path, so no UNO needed.