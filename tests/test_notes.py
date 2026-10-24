"""Release notes in the record, layer 13d (brief, D57; D50 as amended).

A release's notes are the semantic diff against the record before it, made from the stored
packages when the record is, kept as data, and never rewritten. See docs/layers/13-diff.md (13d)
and docs/guides/releases.md.
"""

import inspect
import json
from dataclasses import replace
from pathlib import Path

import pytest
from test_releases import copied, edited, requiring, retitled

from ventoux.case.changes import Against, Change, Notes, Reworded
from ventoux.case.diff import Diff, diff
from ventoux.case.notes import NotesRefused, notes_for
from ventoux.case.releases import Package, Record, RecordRefused, stored
from ventoux.core.catalog import Catalog
from ventoux.testing import CATALOG
from ventoux.tooling.cli import main
from ventoux.tooling.releases import FolderStore, release

# --- Slice 3: notes in the record ----------------------------------------------------------------


def test_a_contract_whose_promise_isnt_the_earlier_records_refuses_the_release(
    tmp_path: Path,
) -> None:
    # The notes would compare a promise release 1 never ran: refused, and nothing written
    # (brief, D57).
    folder, store = copied(tmp_path), FolderStore(tmp_path / "releases")
    release(folder, store, "a1", CATALOG)
    first = tmp_path / "releases" / "refund" / "1.json"
    kept = json.loads(first.read_text())
    kept["contracts"]["payments.refund@2"]["sha256"] = "0" * 64
    first.write_text(json.dumps(kept, indent=2, sort_keys=True) + "\n")
    edited(folder, requiring())
    with pytest.raises(
        NotesRefused,
        match=(
            "^refund 2's notes can't be made: payments.refund@2's promise in the catalog isn't "
            "the one refund 1 recorded$"
        ),
    ):
        release(folder, store, "a2", CATALOG)
    assert [path.name for path in first.parent.iterdir()] == ["1.json"]


def released_twice(tmp_path: Path) -> tuple[FolderStore, list[Record]]:
    """The example package released, then released again with settle no longer requiring the
    review: two records, and the store keeping them."""
    folder, store = copied(tmp_path), FolderStore(tmp_path / "releases")
    release(folder, store, "a1", CATALOG)
    edited(folder, requiring())
    release(folder, store, "a2", CATALOG)
    return store, store.records("refund")


def test_a_releases_notes_are_the_diff_of_the_stored_packages(tmp_path: Path) -> None:
    _, (first, second) = released_twice(tmp_path)
    assert first.notes == Notes(None)  # the first release: nothing to compare
    assert second.notes is not None and second.notes.against == Against(1, 1)
    # From the two records alone, never the working tree: the same notes.
    found = diff(stored(first, "refund"), stored(second, "refund"), CATALOG)
    assert second.notes == Notes(Against(1, 1), found.changes, found.rewritten, found.wording)
    assert [str(change) for change in second.notes.changes] == [
        "looser     steps.settle.requires: review -> nothing"
    ]


def test_a_wording_revisions_notes_hold_wording_only(tmp_path: Path) -> None:
    folder, store = copied(tmp_path), FolderStore(tmp_path / "releases")
    release(folder, store, "a1", CATALOG)
    edited(folder, retitled("Pay the refund"))
    release(folder, store, "a2", CATALOG)
    (_, reworded) = store.records("refund")
    assert reworded.notes == Notes(
        Against(1, 1),
        wording=(Reworded("steps.settle.display.title", "Settle the refund", "Pay the refund"),),
    )


def test_nothing_is_written_without_its_notes(tmp_path: Path) -> None:
    # The store refuses a record with no notes: only one written before layer 13d has none.
    store, (first, _) = released_twice(tmp_path)
    bare = replace(first, release=3, notes=None)
    with pytest.raises(RecordRefused, match="^refund 3 has no notes: nothing is recorded without"):
        store.write(bare)


def test_a_record_from_before_13d_reads_with_no_notes(tmp_path: Path) -> None:
    store, _ = released_twice(tmp_path)
    first = tmp_path / "releases" / "refund" / "1.json"
    kept = json.loads(first.read_text())
    del kept["notes"]  # as 12a wrote it
    first.write_text(json.dumps(kept))
    assert store.records("refund")[0].notes is None


def test_notes_that_arent_a_proof_are_refused_when_read(tmp_path: Path) -> None:
    # A looser verdict must name a comparison (brief, D55): a record saying otherwise is refused,
    # never read as it says.
    released_twice(tmp_path)
    second = tmp_path / "releases" / "refund" / "2.json"
    kept = json.loads(second.read_text())
    kept["notes"]["changes"][0]["comparison"] = None
    second.write_text(json.dumps(kept))
    with pytest.raises(RecordRefused, match="can't be read as a release record"):
        FolderStore(tmp_path / "releases").records("refund")


def test_notes_are_given_no_case_file() -> None:
    # Two records and the catalog: nothing a case holds (brief, D57).
    assert list(inspect.signature(notes_for).parameters) == ["kept", "records", "catalog"]


def test_notes_that_say_less_than_the_digest_refuse_the_release(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # A diff that left a change out would be a bug: the release is refused, naming the path,
    # never recorded shorter (brief, D55) (brief, D57). The diff is made to say nothing here.
    def saying_nothing(before: Package, after: Package, catalog: Catalog) -> Diff:
        return Diff(after.name, (), ())

    monkeypatch.setattr("ventoux.case.notes.diff", saying_nothing)
    with pytest.raises(
        NotesRefused,
        match=(
            "^refund 2's notes can't be made: they don't say steps.settle.requires, which the "
            "digest saw change$"
        ),
    ):
        released_twice(tmp_path)


def test_a_wording_revisions_diff_saying_more_refuses_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Its digest is its release's: a behaviour change in its notes is a bug, said.
    folder, store = copied(tmp_path), FolderStore(tmp_path / "releases")
    release(folder, store, "a1", CATALOG)
    edited(folder, retitled("Pay the refund"))

    def saying_more(before: Package, after: Package, catalog: Catalog) -> Diff:
        return Diff(after.name, (Change("steps.settle.when", "not proven", "a -> b"),), ())

    monkeypatch.setattr("ventoux.case.notes.diff", saying_more)
    with pytest.raises(NotesRefused, match="a wording revision's diff says more than wording$"):
        release(folder, store, "a2", CATALOG)


# --- Slice 4: the commands -----------------------------------------------------------------------


def test_the_release_command_refuses_when_the_notes_cant_be_made(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    folder, releases = copied(tmp_path), tmp_path / "releases"
    assert main(["release", str(folder), "--releases", str(releases), "--commit", "a1"]) == 0
    first = releases / "refund" / "1.json"
    kept = json.loads(first.read_text())
    kept["contracts"]["payments.refund@2"]["sha256"] = "0" * 64
    first.write_text(json.dumps(kept, indent=2, sort_keys=True) + "\n")
    edited(folder, requiring())
    capsys.readouterr()
    assert main(["release", str(folder), "--releases", str(releases), "--commit", "a2"]) == 1
    assert capsys.readouterr().err == (
        f"{folder}: refund 2's notes can't be made: payments.refund@2's promise in the catalog "
        "isn't the one refund 1 recorded\n"
    )


def test_the_release_command_prints_the_notes_after_what_it_did(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # The same words as `ventoux diff` (brief, D57); a first release has nothing to compare.
    folder, releases = copied(tmp_path), tmp_path / "releases"
    main(["release", str(folder), "--releases", str(releases), "--commit", "a1"])
    assert capsys.readouterr().out.count("\n") == 1
    edited(folder, requiring())
    main(["release", str(folder), "--releases", str(releases), "--commit", "a2"])
    (_, second) = FolderStore(releases).records("refund")
    # The package's own warning first (settle now reads review's outcome without waiting for it).
    assert capsys.readouterr().out == (
        "warning: steps.settle.when: MAY_BE_UNSET: settle reads review.outcome, and doesn't wait "
        "for review, which gives it: if settle runs first, it fails and needs attention: require "
        "review\n"
        f"refund 2 released: digest {second.digest.sha256[:12]} (method 1); behaviour changed at "
        "steps.settle.requires\n"
        "refund: 1 behaviour change: 1 may loosen (1 looser, 0 not proven), 0 stricter; no wording "
        "change\n"
        "looser     steps.settle.requires: review -> nothing\n"
    )


def test_the_notes_command_reads_a_records_notes(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    released_twice(tmp_path)
    releases = str(tmp_path / "releases")
    capsys.readouterr()
    assert main(["notes", "refund", "1", "--releases", releases]) == 0
    assert capsys.readouterr().out == "refund 1: the first release, nothing to compare\n"
    assert main(["notes", "refund", "2", "--releases", releases]) == 0
    assert capsys.readouterr().out == (
        "refund 2, against refund 1:\n"
        "refund: 1 behaviour change: 1 may loosen (1 looser, 0 not proven), 0 stricter; no wording "
        "change\n"
        "looser     steps.settle.requires: review -> nothing\n"
    )
    assert main(["notes", "refund", "2", "--releases", releases, "--plain"]) == 0
    said = capsys.readouterr().out
    assert said.startswith("## refund: what changes\n")
    assert "- **Looser** (`steps.settle.requires`): review -&gt; nothing." in said


def test_the_notes_command_says_a_record_has_none_and_refuses_one_it_lacks(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    released_twice(tmp_path)
    releases = tmp_path / "releases"
    first = releases / "refund" / "1.json"
    kept = json.loads(first.read_text())
    del kept["notes"]  # as 12a wrote it
    first.write_text(json.dumps(kept))
    capsys.readouterr()
    assert main(["notes", "refund", "1", "--releases", str(releases)]) == 0
    assert capsys.readouterr().out == "refund 1: no notes: recorded before layer 13d\n"
    assert main(["notes", "refund", "3", "--releases", str(releases)]) == 1
    assert capsys.readouterr().err == (
        f"refund 3 isn't released: no record of it in {releases / 'refund'}\n"
    )
