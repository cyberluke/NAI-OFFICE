# WriterAgent - AI Writing Assistant for LibreOffice
#
# SPDX-License-Identifier: GPL-3.0-or-later
"""Unit tests for the Creator Studio IR model (pure Python, no UNO).

Run with ``make pytest`` (or ``pytest tests/writer/creator`` — the test runner
installs the ``crosshair`` stub via conftest so ``plugin.writer`` can import).
"""

from __future__ import annotations

import pytest

from plugin.writer.creator.model import (
    CreatorArtifact,
    CreatorArtifactKind,
    CreatorChapter,
    CreatorProject,
    CreatorProjectSettings,
    CreatorSceneState,
    chapter_ready_to_draft,
    creator_project_from_mapping,
)


def _sample_project() -> CreatorProject:
    return CreatorProject(
        settings=CreatorProjectSettings(title="A Locked Room", kind="novel", genre="fantasy", tone="dark", target_words=50000),
        chapters=[
            CreatorChapter(
                id="c0",
                title="The Door",
                status="planned",
                summary="They enter the house at dusk.",
                scenes=[CreatorArtifact(id="a0", body="It began at dusk.", kind=CreatorArtifactKind.SCENE.value)],
                characters=["Ada"],
            )
        ],
        characters=[{"name": "Ada", "role": "protagonist"}],
        brief="Someone dies in a locked room; Ada must not be the killer.",
    )


def test_model_roundtrip() -> None:
    p = _sample_project()
    p2 = creator_project_from_mapping(p.to_mapping())
    assert p2.settings.title == "A Locked Room"
    assert p2.settings.kind == "novel"
    assert p2.chapters[0].title == "The Door"
    assert p2.chapters[0].scenes[0].body == "It began at dusk."
    assert p2.chapters[0].scenes[0].kind == "scene"
    assert p2.characters[0]["name"] == "Ada"
    assert p2.brief == "Someone dies in a locked room; Ada must not be the killer."


def test_duplicate_chapter_id_rejected() -> None:
    data = {"chapters": [{"id": "x"}, {"id": "x"}]}
    with pytest.raises(ValueError, match="duplicate chapter id"):
        creator_project_from_mapping(data)


def test_duplicate_artifact_id_rejected() -> None:
    data = {
        "chapters": [
            {
                "id": "c1",
                "scenes": [{"id": "a"}, {"id": "a"}],
            }
        ]
    }
    with pytest.raises(ValueError, match="duplicate artifact id"):
        creator_project_from_mapping(data)


def test_missing_chapter_id_rejected() -> None:
    with pytest.raises(ValueError, match="missing id"):
        creator_project_from_mapping({"chapters": [{"title": "No id"}]})


def test_valid_empty_project() -> None:
    p = creator_project_from_mapping({})
    assert p.chapters == []
    assert p.summary()["chapters"] == 0


def test_chapter_text_joins_scenes() -> None:
    ch = CreatorChapter(
        id="c1",
        title="T",
        scenes=[
            CreatorArtifact(id="a1", body="first"),
            CreatorArtifact(id="a2", body="second"),
        ],
    )
    assert ch.text == "first\n\nsecond"


def test_chapter_ready_to_draft() -> None:
    planned = CreatorChapter(id="c1", title="The Door", status="planned")
    assert chapter_ready_to_draft(planned)
    drafting = CreatorChapter(id="c2", title="X", status="drafting")
    assert not chapter_ready_to_draft(drafting)
    final = CreatorChapter(id="c3", title="X", status="final")
    assert not chapter_ready_to_draft(final)


def test_scene_state_roundtrip() -> None:
    st = CreatorSceneState(id="s1", chapter_id="c1", entering=["locked room"], exit=["key"], forbidden=["notebook"])
    m = st.to_mapping()
    st2 = CreatorSceneState.from_mapping(m)
    assert st2.entering == ["locked room"]
    assert st2.forbidden == ["notebook"]


def test_chapter_ready_to_draft_only() -> None:
    # Selection of the next chapter is owned by the orchestrator; model keeps only the
    # readiness predicate (no duplicate next_drafts that could drift).
    assert chapter_ready_to_draft(CreatorChapter(id="c1", title="T", status="planned"))
    assert not chapter_ready_to_draft(CreatorChapter(id="c2", title="X", status="final"))


def test_clone_not_needed_removed() -> None:
    # clone_project/deep-copy helper was removed as dead code; the IR round-trip through
    # to_mapping/from_mapping remains the supported deep-copy mechanism.
    p = _sample_project()
    p2 = creator_project_from_mapping(p.to_mapping())
    assert p2.chapters[0].title == "The Door"