"""`ventoux draft-sheet` (layer 15d): "Approve this plan" for a draft in the drafts folder, from
its record and its package; exit 0 when it rendered, 2 when it couldn't, never with a traceback.

See docs/layers/15-authoring.md (15d) and brief D64.
"""

import hashlib
import json
from collections.abc import Callable
from pathlib import Path

import pytest
from test_authoring import TO_THE_EMAIL, TO_THE_NOTE
from test_drafting import PLAN, draft, project, recorded

from ventoux.tooling.cli import main

DRAFT = f"drafts/{PLAN}.json"


def drafted(root: Path, monkeypatch: pytest.MonkeyPatch, *answers: str) -> None:
    """The refund project at `root`, and its plan drafted by `ventoux draft` from `answers`."""
    project(root)
    session = recorded(root, *answers)
    monkeypatch.chdir(root)
    assert main(draft(root, "--by", "omar", "--recording", str(session))) == 0


def sheet(*more: str) -> list[str]:
    return ["draft-sheet", DRAFT, "--package", "packages/refund", *more]


def test_a_draft_edited_after_it_was_drafted_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    drafted(tmp_path, monkeypatch, TO_THE_NOTE, TO_THE_EMAIL)
    edited = tmp_path / DRAFT
    edited.write_text(edited.read_text().replace("refund-sent", "refund-sent "))
    capsys.readouterr()
    assert main(sheet()) == 2
    said = capsys.readouterr()
    assert said.out == ""  # never shown for approval
    assert said.err == (
        f"{DRAFT} was changed after it was drafted: its record holds another digest. A plan "
        "edited by hand is reviewed as one: copy it into the package and open a pull request\n"
    )


RECORD = f"drafts/{PLAN}.record.json"
EVERGREEN = TO_THE_EMAIL.replace('"plan": "refund-order"', '"plan": "evergreen"', 1)


def edit_record(root: Path, **changes: object) -> None:
    """The draft's record with `changes`; a change to None removes the field."""
    path = root / RECORD
    record = json.loads(path.read_text())
    for key, value in changes.items():
        if value is None:
            del record[key]
        else:
            record[key] = value
    path.write_text(json.dumps(record))


def evergreen(root: Path) -> None:
    """The draft rewritten as a plan no step of the package names, its record made to match."""
    (root / DRAFT).write_text(EVERGREEN)
    digest = hashlib.sha256((root / DRAFT).read_bytes()).hexdigest()
    edit_record(root, plan="evergreen@1", draft_sha256=digest)


@pytest.mark.parametrize(
    ("breaking", "said"),
    [
        pytest.param(
            lambda root: (root / RECORD).unlink(),
            f"{DRAFT} has no record beside it ({RECORD}): only a plan `ventoux draft` wrote is "
            "shown for approval",
            id="no record",
        ),
        pytest.param(
            lambda root: (root / RECORD).write_text("{"),
            f"{RECORD} doesn't read as a draft's record: not JSON",
            id="not JSON",
        ),
        pytest.param(
            lambda root: edit_record(root, draft_sha256=None),
            f"{RECORD} doesn't read as a draft's record: draft_sha256: required",
            id="no digest",
        ),
        pytest.param(
            lambda root: edit_record(root, verdict="abandoned"),
            f"{RECORD} says the draft was abandoned: only a draft that passed is shown for "
            "approval",
            id="abandoned",
        ),
        pytest.param(
            lambda root: edit_record(root, plan="evergreen@1"),
            f"{RECORD} is the record of evergreen@1, and {DRAFT} is {PLAN}: draft it again",
            id="another plan",
        ),
        pytest.param(
            lambda root: edit_record(root, package="claims"),
            f"{RECORD} is a draft for the package claims, and packages/refund is refund: give "
            "the package it was drafted for",
            id="another package",
        ),
        pytest.param(
            evergreen,
            "evergreen@1 doesn't fit refund: ",
            id="a plan no step names",
        ),
    ],
)
def test_a_draft_whose_record_or_package_doesnt_match_is_refused(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    breaking: Callable[[Path], None],
    said: str,
) -> None:
    drafted(tmp_path, monkeypatch, TO_THE_NOTE, TO_THE_EMAIL)
    breaking(tmp_path)
    capsys.readouterr()
    assert main(sheet()) == 2
    out = capsys.readouterr()
    assert out.out == ""
    assert out.err.startswith(said)
    assert "Traceback" not in out.err


def test_a_drafts_folder_is_never_a_package(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # It holds no case.json, so nothing in it can be released, and a draft runs nowhere
    # (brief, D64).
    drafted(tmp_path, monkeypatch, TO_THE_NOTE, TO_THE_EMAIL)
    (tmp_path / "releases").mkdir()
    capsys.readouterr()
    assert main(["release", "drafts", "--releases", "releases", "--commit", "abc123"]) == 2
    assert capsys.readouterr().err == (
        "drafts: drafts has no case.json: a package is a folder holding one\n"
    )
    assert list((tmp_path / "releases").iterdir()) == []
    assert main(["draft-sheet", DRAFT, "--package", "drafts"]) == 2
    said = capsys.readouterr()
    assert said.out == ""
    assert said.err == "drafts has no case.json: a package is a folder holding one\n"
