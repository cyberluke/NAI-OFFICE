# WriterAgent - AI Writing Assistant for LibreOffice
# Copyright (c) 2026 KeithCu (modifications and relicensing)
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
"""Revisioned project-store persistence for the Creator Studio IR.

The Author IR must survive LibreOffice restarts and the Writer document being closed
and reopened, otherwise the user's outline/characters/scene-states would live only in
the transient presentation.  We store the IR as JSON alongside the document and keep
a small revision counter + checksum so the two-way sync can tell *who changed what*.

This module is presentation-free (no UNO imports at module import time); the store
path comes from the caller so tests run without LibreOffice.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from dataclasses import dataclass
from typing import Any, final

from .model import CreatorProject, creator_project_from_mapping

_STORE_EXT = "creator.json"


class CreatorStoreError(Exception):
    """Raised for store I/O or validation problems."""


@dataclass
class CreatorStoreRecord:
    project: CreatorProject
    revision: int
    checksum: str

    @property
    def summary(self) -> dict[str, Any]:
        return {**self.project.summary(), "revision": self.revision, "checksum": self.checksum[:8]}


def _checksum(mapping: dict[str, Any]) -> str:
    body = json.dumps(mapping, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


def _write_atomic(path: str, text: str) -> None:
    directory = os.path.dirname(path) or "."
    fd, tmp = tempfile.mkstemp(suffix=".tmp", dir=directory)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


@final
class CreatorStore:
    """On-disk, revisioned store for one CreatorStudio project."""

    path: str

    def __init__(self, path: str) -> None:
        self.path = path
        self._next_revision = 0
        self._record: CreatorStoreRecord | None = None

    def ensure_dir(self) -> None:
        directory = os.path.dirname(self.path) or "."
        if directory and not os.path.isdir(directory):
            os.makedirs(directory, exist_ok=True)

    def load(self) -> CreatorStoreRecord | None:
        """Load the latest IR, or None when the store does not exist yet."""
        if not os.path.exists(self.path):
            return None
        try:
            with open(self.path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
        except (OSError, ValueError) as exc:
            raise CreatorStoreError(f"creator store unreadable: {exc}") from exc
        if not isinstance(data, dict) or not isinstance(data.get("project"), dict):
            raise CreatorStoreError("creator store malformed: missing 'project'")
        mapping = data["project"]
        try:
            project = creator_project_from_mapping(mapping)
        except ValueError as exc:
            raise CreatorStoreError(f"creator store validation failed: {exc}") from exc
        revision = int(data.get("revision") or 0)
        checksum = _checksum(project.to_mapping())
        self._record = CreatorStoreRecord(project=project, revision=revision, checksum=checksum)
        self._next_revision = revision + 1
        return self._record

    def save(self, project: CreatorProject, *, reason: str = "") -> CreatorStoreRecord:
        """Persist the project as a new revision. Always succeeds atomically."""
        self.ensure_dir()
        mapping = project.to_mapping()
        checksum = _checksum(mapping)
        revision = self._next_revision
        self._next_revision += 1
        payload = {
            "schema_version": 1,
            "revision": revision,
            "checksum": checksum,
            "reason": reason,
            "project": mapping,
        }
        _write_atomic(self.path, json.dumps(payload, ensure_ascii=False, indent=1))
        record = CreatorStoreRecord(project=project, revision=revision, checksum=checksum)
        self._record = record
        return record


def load_project_store(path: str) -> CreatorStore:
    """Open a CreatorStore at *path* (does not read the file until :meth:`load`)."""
    return CreatorStore(path)


def save_project_store(path: str, project: CreatorProject, *, reason: str = "") -> CreatorStoreRecord:
    """Convenience: open, save, return the record."""
    return CreatorStore(path).save(project, reason=reason)