"""Releases: a package, its behaviour digest, its number and its record (layer 12a; brief, D50).

See docs/layers/12-releases.md (12a) and docs/guides/releases.md.
"""

import copy
import json
import shutil
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

from ventoux.case.releases import (
    METHOD,
    Changed,
    Outcome,
    Package,
    PackageRefused,
    Record,
    RecordRefused,
    Released,
    Reworded,
    SameAs,
    Unchanged,
    next_release,
    package,
    record,
)
from ventoux.core.contract_hash import contract_hash
from ventoux.testing import CATALOG
from ventoux.tooling.cli import main
from ventoux.tooling.releases import FolderStore, read_package, release

ROOT = Path(__file__).parent.parent
REFUND = ROOT / "examples" / "packages" / "refund"


def written(folder: Path = REFUND) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """The example package's case and plans, as data a test may change."""
    case = json.loads((folder / "case.json").read_text())
    plans = [json.loads(plan.read_text()) for plan in sorted((folder / "plans").iterdir())]
    return case, plans


def packed(case: dict[str, Any], plans: list[dict[str, Any]] | None = None) -> Package:
    """The package of `case` and `plans`, written as JSON text, as a folder holds them."""
    return package(json.dumps(case), [json.dumps(plan) for plan in plans or []])


def lettered(template: str) -> dict[str, Any]:
    """A case that drafts a letter with `template` passed as a literal input: the warm-up's
    letter (learning question 11)."""
    return {
        "case": "letter",
        "display": {"title": "A letter to a customer"},
        "fields": {"email": {"type": "string", "display": {"title": "Email"}}},
        "steps": {
            "draft": {
                "kind": "activity",
                "display": {"title": "Draft the letter"},
                "activity": "letters.draft@2",
                "inputs": {"to_customer": {"var": "email"}, "template": template},
            }
        },
    }


def record_of(released: Package, outcome: Outcome, commit: str = "4f2a9c1") -> Record:
    """The record CI would write for `outcome`, with the development catalog."""
    assert isinstance(outcome, Released | Reworded), f"{outcome}: nothing is recorded"
    return record(released, outcome, commit, CATALOG)


def released_once(case: dict[str, Any], plans: list[dict[str, Any]] | None = None) -> list[Record]:
    """The records of a package released once, as release 1."""
    first = packed(case, plans)
    outcome = next_release(first, [])
    assert outcome == Released(1, Changed())
    return [record_of(first, outcome)]


def test_a_literal_input_changed_is_a_release() -> None:
    # A literal passed to an activity is behaviour (brief, D5), however much it reads like words:
    # never wording only.
    records = released_once(lettered("Dear customer, we are pleased to confirm your refund."))
    changed = copy.deepcopy(lettered("Dear customer, we are happy to confirm your refund."))
    outcome = next_release(packed(changed), records)
    assert isinstance(outcome, Released) and outcome.release == 2
    assert outcome.changed.behaviour == ("steps.draft.inputs.template",)
    assert outcome.changed.wording == ()


def with_two_rules(first: str, second: str) -> dict[str, Any]:
    """The refund package's case with two rules on the review's answer, in the order given."""
    case, _ = written()
    case["milestones"] = {
        name: {"display": {"title": name.capitalize()}} for name in ("noted", "flagged")
    }
    rules = {
        "note": {
            "display": {"title": "Note the review"},
            "on": {"answered": "review"},
            "then": {"reach": ["noted"]},
        },
        "flag": {
            "display": {"title": "Flag the review"},
            "on": {"answered": "review"},
            "then": {"reach": ["flagged"]},
        },
    }
    case["rules"] = {first: rules[first], second: rules[second]}
    return case


def test_rules_reordered_are_a_release() -> None:
    # Rules on one moment act in the order written (brief, D38): reordering them is behaviour.
    _, plans = written()
    records = released_once(with_two_rules("note", "flag"), plans)
    outcome = next_release(packed(with_two_rules("flag", "note"), plans), records)
    assert outcome == Released(2, Changed(behaviour=("rules",)))


def test_steps_reordered_are_a_release() -> None:
    # Admission asks each step in the order written, so the commands come in that order.
    case, plans = written()
    records = released_once(case, plans)
    steps = case["steps"]
    case["steps"] = {name: steps[name] for name in ("settle", "review", "call_customer")}
    assert next_release(packed(case, plans), records) == Released(2, Changed(("steps",)))


def test_a_field_named_display_is_behaviour() -> None:
    # Wording is found by its type, never by a key's name: a case-file field called `display`
    # retyped is a release, never wording only.
    case, plans = written()
    case["fields"]["display"] = {"type": "number", "display": {"title": "Shown amount"}}
    records = released_once(case, plans)
    case["fields"]["display"]["type"] = "string"
    outcome = next_release(packed(case, plans), records)
    assert outcome == Released(2, Changed(behaviour=("fields.display.type",)))


def test_a_fields_type_changed_is_a_release() -> None:
    # A field's `type` names its shape, so it is kept even at its default.
    case, plans = written()
    records = released_once(case, plans)
    case["fields"]["amount"]["type"] = "string"
    outcome = next_release(packed(case, plans), records)
    assert outcome == Released(2, Changed(behaviour=("fields.amount.type",)))


def test_a_title_changed_is_wording_only() -> None:
    case, plans = written()
    records = released_once(case, plans)
    case["steps"]["settle"]["display"]["title"] = "Pay the refund"
    case["steps"]["review"]["outcomes"]["reject"]["display"]["title"] = "Turn the refund down"
    case["display"]["description"] = "A customer asks for their money back."
    outcome = next_release(packed(case, plans), records)
    paths = (
        "display.description",
        "steps.review.outcomes.reject.display.title",
        "steps.settle.display.title",
    )
    assert outcome == Reworded(1, 2, Changed(wording=paths))


def test_an_approval_reason_changed_is_wording_only() -> None:
    records = released_once(json.loads((ROOT / "examples/refund/refund.json").read_text()))
    case = json.loads((ROOT / "examples/refund/refund.json").read_text())
    case["steps"]["pay"]["approval"]["display"]["reason"] = "A team lead checks refunds over 100"
    outcome = next_release(packed(case), records)
    assert outcome == Reworded(1, 2, Changed(wording=("steps.pay.approval.display.reason",)))


def test_reformatting_changes_no_digest() -> None:
    case, plans = written()
    records = released_once(case, plans)
    # Another layout, and an object's keys in another order: the same definition.
    review = case["steps"]["review"]
    case["steps"]["review"] = dict(reversed(list(review.items())))
    texts = [json.dumps(plan, indent=4) for plan in plans]
    assert next_release(package(json.dumps(case, indent=1), texts), records) == Unchanged(1)


def test_an_explicit_default_changes_no_digest() -> None:
    case, plans = written()
    records = released_once(case, plans)
    case["stays_open"] = False
    case["steps"]["review"]["repeatable"] = False
    case["steps"]["settle"]["max_age"] = {}
    assert next_release(packed(case, plans), records) == Unchanged(1)


def refused(case: dict[str, Any], plans: list[dict[str, Any]]) -> str:
    """Why the package of `case` and `plans` is refused."""
    with pytest.raises(PackageRefused) as refusal:
        packed(case, plans)
    return str(refusal.value)


def test_a_missing_plan_is_refused() -> None:
    case, _ = written()
    assert refused(case, []) == "refund-order@1 is run by a plan step and isn't in plans/: add it"


def test_a_plan_nobody_runs_is_refused() -> None:
    # Shipped and never run: fail closed, as a plan supplied under another reference is (D28).
    case, plans = written()
    spare = {**plans[0], "version": 2}
    assert refused(case, [*plans, spare]) == (
        "refund-order@2 is run by no plan step: remove it, or name it in a step"
    )


def test_a_plan_given_twice_is_refused() -> None:
    case, plans = written()
    assert refused(case, [*plans, plans[0]]) == (
        "refund-order@1 is given twice: keep one file for it"
    )


def test_a_stray_file_is_refused(tmp_path: Path) -> None:
    folder = copied(tmp_path)
    (folder / "notes.txt").write_text("to do")
    (folder / "plans" / "draft.yaml").write_text("plan: draft")
    with pytest.raises(PackageRefused) as refusal:
        read_package(folder)
    assert str(refusal.value) == (
        "notes.txt isn't part of a package: a package holds case.json and plans/\n"
        "plans/draft.yaml isn't a plan's file: each plan is a .json file"
    )


def test_a_plans_change_is_a_release_of_its_package() -> None:
    case, plans = written()
    records = released_once(case, plans)
    plans[0]["states"]["approve_refund"]["approval"]["timeout"] = "72h"
    path = "plans.refund-order@1.states.approve_refund.approval.timeout"
    assert next_release(packed(case, plans), records) == Released(2, Changed(behaviour=(path,)))


def copied(tmp_path: Path) -> Path:
    """The example package, copied where a test may change it."""
    folder = tmp_path / "refund"
    shutil.copytree(REFUND, folder)
    return folder


def edited(folder: Path, change: Any) -> None:
    """Change the case in `folder` with `change`, which edits its data in place."""
    case = json.loads((folder / "case.json").read_text())
    change(case)
    (folder / "case.json").write_text(json.dumps(case, indent=2))


def retitled(title: str) -> Any:
    def change(case: dict[str, Any]) -> None:
        case["steps"]["settle"]["display"]["title"] = title

    return change


def requiring(*names: str) -> Any:
    def change(case: dict[str, Any]) -> None:
        case["steps"]["settle"]["requires"] = list(names)

    return change


def test_releases_are_numbered_from_1(tmp_path: Path) -> None:
    folder, store = copied(tmp_path), FolderStore(tmp_path / "releases")
    assert release(folder, store, "a1", CATALOG).outcome == Released(1, Changed())
    edited(folder, requiring())  # settle no longer waits for the review: behaviour
    second = release(folder, store, "a2", CATALOG)
    assert second.outcome == Released(2, Changed(behaviour=("steps.settle.requires",)))
    edited(folder, lambda case: case["steps"]["settle"].pop("when"))
    assert release(folder, store, "a3", CATALOG).outcome.release == 3
    names = sorted(path.name for path in (tmp_path / "releases" / "refund").iterdir())
    assert names == ["1.json", "2.json", "3.json"]


def test_a_digest_already_released_makes_none(tmp_path: Path) -> None:
    # One digest, one release: a revert merged is a rollback, which is activating it (brief, D50).
    folder, store = copied(tmp_path), FolderStore(tmp_path / "releases")
    release(folder, store, "a1", CATALOG)
    edited(folder, requiring())
    release(folder, store, "a2", CATALOG)
    edited(folder, requiring("review"))  # back to release 1's behaviour
    run = release(folder, store, "a3", CATALOG)
    assert run.outcome == SameAs(1) and not run.written
    assert len(store.records("refund")) == 2


def test_the_same_package_again_writes_nothing(tmp_path: Path) -> None:
    folder, store = copied(tmp_path), FolderStore(tmp_path / "releases")
    assert release(folder, store, "a1", CATALOG).written
    again = release(folder, store, "a1", CATALOG)
    assert again.outcome == Unchanged(1) and not again.written


def test_a_record_is_never_written_over(tmp_path: Path) -> None:
    folder, store = copied(tmp_path), FolderStore(tmp_path / "releases")
    first = release(folder, store, "a1", CATALOG)
    assert isinstance(first.outcome, Released)
    kept = store.records("refund")[0]
    assert store.write(kept) is False  # the same bytes again: a CI job run twice
    other = replace(kept, commit="b2")
    with pytest.raises(RecordRefused) as refusal:
        store.write(other)
    where = tmp_path / "releases" / "refund" / "1.json"
    assert str(refusal.value) == (
        f"{where} already exists, with other content: a record is never written over"
    )
    assert store.records("refund") == [kept]


def test_a_package_with_an_error_is_not_released(tmp_path: Path) -> None:
    folder, store = copied(tmp_path), FolderStore(tmp_path / "releases")

    def misspelt(case: dict[str, Any]) -> None:
        case["steps"]["settle"]["when"] = {"==": [{"var": "review.outcome"}, "aprove"]}

    edited(folder, misspelt)
    with pytest.raises(PackageRefused) as refusal:
        release(folder, store, "a1", CATALOG)
    assert str(refusal.value) == (
        'steps.settle.when: EXPRESSION_INVALID: ==[1]: review.outcome has no outcome "aprove"; '
        "its outcomes are approve, reject"
    )
    assert not (tmp_path / "releases").exists()


def test_a_warning_lets_a_release_through(tmp_path: Path) -> None:
    folder, store = copied(tmp_path), FolderStore(tmp_path / "releases")

    def unreached(case: dict[str, Any]) -> None:
        case["milestones"] = {"escalated": {"display": {"title": "Escalated"}}}

    edited(folder, unreached)
    run = release(folder, store, "a1", CATALOG)
    assert run.outcome == Released(1, Changed()) and run.written
    assert [issue.code for issue in run.warnings] == ["UNREACHABLE_MILESTONE"]


def test_the_record_holds_what_activation_needs(tmp_path: Path) -> None:
    folder, store = copied(tmp_path), FolderStore(tmp_path / "releases")
    release(folder, store, "a1", CATALOG)
    edited(folder, requiring())
    release(folder, store, "a2", CATALOG)
    second = json.loads((tmp_path / "releases" / "refund" / "2.json").read_text())
    assert second["name"] == "refund" and second["release"] == 2 and second["wording"] == 1
    assert second["commit"] == "a2"
    assert second["digest"]["method"] == 1 and len(second["digest"]["sha256"]) == 64
    # Every contract it needs, its plan's included, each with its hash (brief, D5).
    assert second["contracts"] == {
        reference: {"method": 1, "sha256": contract_hash(CATALOG.lookup(reference))}
        for reference in ("orders.lookup@1", "payments.refund@2")
    }
    # The package as written, read again exactly.
    assert second["written"]["case"] == (folder / "case.json").read_text()
    plan = (folder / "plans" / "refund-order.json").read_text()
    assert second["written"]["plans"] == {"refund-order@1": plan}
    assert second["changed"] == {"behaviour": ["steps.settle.requires"], "wording": []}


def test_wording_revisions_are_numbered_and_recorded_at_once(tmp_path: Path) -> None:
    folder, store = copied(tmp_path), FolderStore(tmp_path / "releases")
    release(folder, store, "a1", CATALOG)
    edited(folder, retitled("Pay the refund"))
    second = release(folder, store, "a2", CATALOG)
    assert second.outcome == Reworded(1, 2, Changed(wording=("steps.settle.display.title",)))
    assert second.written
    # Back to the first title: still a new revision, since people now read the second.
    edited(folder, retitled("Settle the refund"))
    assert release(folder, store, "a3", CATALOG).outcome == Reworded(
        1, 3, Changed(wording=("steps.settle.display.title",))
    )
    # A release after it is compared with the wording people read now, and is numbered on.
    edited(folder, requiring())
    edited(folder, retitled("Refund the order"))
    assert release(folder, store, "a4", CATALOG).outcome == Released(
        2, Changed(("steps.settle.requires",), ("steps.settle.display.title",))
    )
    names = sorted(path.name for path in (tmp_path / "releases" / "refund").iterdir())
    assert names == ["1.json", "1.wording-2.json", "1.wording-3.json", "2.json"]
    revision = json.loads((tmp_path / "releases" / "refund" / "1.wording-2.json").read_text())
    assert (revision["release"], revision["wording"], revision["commit"]) == (1, 2, "a2")


def kept_as(tmp_path: Path, change: Any) -> Path:
    """Release the example once, then change its record's data with `change`; the folder."""
    folder, store = copied(tmp_path), FolderStore(tmp_path / "releases")
    release(folder, store, "a1", CATALOG)
    path = tmp_path / "releases" / "refund" / "1.json"
    data = json.loads(path.read_text())
    change(data)
    path.write_text(json.dumps(data))
    return folder


def refusal_of(tmp_path: Path, folder: Path) -> str:
    with pytest.raises(RecordRefused) as refusal:
        release(folder, FolderStore(tmp_path / "releases"), "a2", CATALOG)
    return str(refusal.value)


def test_every_hash_records_its_method(tmp_path: Path) -> None:
    folder, store = copied(tmp_path), FolderStore(tmp_path / "releases")
    release(folder, store, "a1", CATALOG)
    (kept,) = store.records("refund")
    assert kept.digest.method == METHOD == 1
    assert {hash.method for hash in kept.contracts.values()} == {1}


def test_a_release_is_compared_by_recomputing_its_digest(tmp_path: Path) -> None:
    # A record whose digest its own package doesn't give is refused, never compared: the record
    # was changed, or the method was (design question 16).
    folder = kept_as(tmp_path, lambda data: data["digest"].update(sha256="0" * 64))
    assert refusal_of(tmp_path, folder) == (
        "refund 1's digest isn't what its own package gives under method 1: the record was "
        "changed, or the method was; it can't be compared"
    )


def test_a_record_of_an_unknown_method_is_refused(tmp_path: Path) -> None:
    folder = kept_as(tmp_path, lambda data: data["digest"].update(method=2))
    assert refusal_of(tmp_path, folder) == (
        "refund 1 was made with hash method 2, which this tool doesn't know (it computes "
        "method 1): run a tool that knows it"
    )


def test_a_record_out_of_place_is_refused(tmp_path: Path) -> None:
    folder = kept_as(tmp_path, lambda data: data.update(release=7))
    where = tmp_path / "releases" / "refund" / "1.json"
    assert refusal_of(tmp_path, folder) == f"{where} holds 7.json's record: put it back"


def command(folder: Path, releases: Path, commit: str, capsys: Any) -> tuple[int, str, str]:
    """`ventoux release` run on `folder`: its exit code, what it printed, and its errors."""
    code = main(["release", str(folder), "--releases", str(releases), "--commit", commit])
    printed = capsys.readouterr()
    return code, printed.out, printed.err


def test_the_command_says_what_it_did(tmp_path: Path, capsys: Any) -> None:
    folder, releases = copied(tmp_path), tmp_path / "releases"
    code, out, _ = command(folder, releases, "a1", capsys)
    (kept,) = FolderStore(releases).records("refund")
    assert (code, out) == (0, f"refund 1 released: digest {kept.digest.sha256[:12]} (method 1)\n")
    assert command(folder, releases, "a1", capsys)[:2] == (
        0,
        "refund: nothing changed since release 1; nothing written\n",
    )
    edited(folder, requiring())
    edited(folder, requiring("review"))
    edited(folder, retitled("Pay the refund"))
    assert command(folder, releases, "a2", capsys)[:2] == (
        0,
        "refund 1, wording 2: steps.settle.display.title changed; no release\n",
    )
    # Refused: exit 1, each problem said; unreadable: exit 2.
    (folder / "notes.txt").write_text("to do")
    assert command(folder, releases, "a3", capsys) == (
        1,
        "",
        f"{folder}: notes.txt isn't part of a package: a package holds case.json and plans/\n",
    )
    (folder / "notes.txt").unlink()
    (folder / "case.json").write_text("{")
    code, out, err = command(folder, releases, "a3", capsys)
    assert (code, out) == (2, "")
    assert err.startswith(f"{folder}: case.json isn't JSON: ")


def test_the_tool_names_paths_never_values(tmp_path: Path, capsys: Any) -> None:
    folder, releases = tmp_path / "letter", tmp_path / "releases"
    folder.mkdir()
    (folder / "case.json").write_text(json.dumps(lettered("We are pleased to confirm.")))
    command(folder, releases, "a1", capsys)
    (folder / "case.json").write_text(json.dumps(lettered("We are happy to confirm.")))
    code, out, _ = command(folder, releases, "a2", capsys)
    assert code == 0 and out.endswith("; behaviour changed at steps.draft.inputs.template\n")
    record = (releases / "letter" / "2.json").read_text()
    changed = json.loads(record)["changed"]
    assert changed == {"behaviour": ["steps.draft.inputs.template"], "wording": []}
    for value in ("pleased", "happy"):
        assert value not in out and value not in json.dumps(changed)


GUIDE = ROOT / "docs" / "guides" / "releases.md"


def guide_runs() -> list[tuple[list[str], str]]:
    """Each `$ ventoux release …` in the guide's "Running it", with what it prints."""
    section = GUIDE.read_text().split("## Running it")[1].split("\n## ")[0]
    runs = []
    for block in section.split("```\n")[1::2]:
        command_line, *printed = block.strip().splitlines()
        assert command_line.startswith("$ ventoux ")
        runs.append((command_line.removeprefix("$ ventoux ").split(), "\n".join(printed) + "\n"))
    return runs


def test_the_guides_example_runs_as_written(tmp_path: Path, capsys: Any, monkeypatch: Any) -> None:
    shutil.copytree(REFUND, tmp_path / "examples" / "packages" / "refund")
    monkeypatch.chdir(tmp_path)  # the guide's paths are relative, from the repository's root
    folder = tmp_path / "examples" / "packages" / "refund"
    # Between its runs the guide rewords a title, then gives the plan's approval 72 hours.
    changes: list[Callable[[], object]] = [
        lambda: None,
        lambda: edited(folder, retitled("Pay the refund")),
        lambda: (folder / "plans" / "refund-order.json").write_text(
            (folder / "plans" / "refund-order.json").read_text().replace('"48h"', '"72h"')
        ),
    ]
    runs = guide_runs()
    assert len(runs) == len(changes)
    for change, (arguments, printed) in zip(changes, runs, strict=True):
        change()
        assert main(arguments) == 0
        assert capsys.readouterr().out == printed


def test_a_revert_with_new_wording_is_refused(tmp_path: Path) -> None:
    # Only the latest release takes new wording: a behaviour reverted with the newer release's
    # titles kept would show them on the older release's open cases (brief, D51).
    folder, store = copied(tmp_path), FolderStore(tmp_path / "releases")
    release(folder, store, "a1", CATALOG)
    edited(folder, requiring())
    edited(folder, retitled("Pay once nothing else is needed"))
    release(folder, store, "a2", CATALOG)
    edited(folder, requiring("review"))  # release 1's behaviour, release 2's title
    with pytest.raises(PackageRefused) as refusal:
        release(folder, store, "a3", CATALOG)
    assert str(refusal.value) == (
        "same behaviour as refund 1, other wording: rewording an older release reaches its open "
        "cases; bring back its wording"
    )
    assert len(store.records("refund")) == 2
    # Its wording brought back too, as a revert does: nothing released.
    edited(folder, retitled("Settle the refund"))
    assert release(folder, store, "a4", CATALOG).outcome == SameAs(1)


def test_a_plan_fields_source_is_named_as_written() -> None:
    # A plan keeps each field's source beside its type; the JSON writes it on the field.
    case, plans = written()
    records = released_once(case, plans)
    plans[0]["fields"]["amount"]["source"] = "untrusted:customer"
    path = "plans.refund-order@1.fields.amount.source"
    assert next_release(packed(case, plans), records) == Released(2, Changed(behaviour=(path,)))


def test_every_record_is_read_again_not_only_the_latest(tmp_path: Path) -> None:
    folder, store = copied(tmp_path), FolderStore(tmp_path / "releases")
    release(folder, store, "a1", CATALOG)
    edited(folder, requiring())
    release(folder, store, "a2", CATALOG)
    first = tmp_path / "releases" / "refund" / "1.json"
    data = json.loads(first.read_text())
    data["digest"]["sha256"] = "0" * 64
    first.write_text(json.dumps(data))
    assert refusal_of(tmp_path, folder).startswith("refund 1's digest isn't what its own package")


def test_a_stray_file_in_the_releases_folder_refuses_the_run(tmp_path: Path) -> None:
    folder, store = copied(tmp_path), FolderStore(tmp_path / "releases")
    release(folder, store, "a1", CATALOG)
    stray = tmp_path / "releases" / "refund" / "notes.txt"
    stray.write_text("to do")
    assert refusal_of(tmp_path, folder).startswith(f"{stray} can't be read as a release record")
