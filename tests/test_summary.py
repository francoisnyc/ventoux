"""The CI step's job summary, layer 13e (brief, D55, as amended in 13e).

On each pull request, for each package: what merging does (12a's digest, the merge commit
against its first parent), then the diff in the plain form; and the hash check with the base
commit's own promises. See docs/layers/13-diff.md (13e) and docs/guides/releases.md, "On each
pull request".
"""

import json
import shutil
from pathlib import Path
from typing import Any

from test_diff import LOOSE, ROOT, calling, refund

from ventoux.core.catalog import Catalog
from ventoux.core.contract_hash import contract_hash, promise_hash
from ventoux.core.promise import promise_of
from ventoux.testing import CATALOG
from ventoux.tooling.summary import Summary, summarize

PACKAGES = "examples/packages"
EXAMPLE = ROOT / PACKAGES / "refund"


def tree(root: Path, *cases: dict[str, Any]) -> Path:
    """A checkout at `root` holding a package per case under `examples/packages`, each case alone
    (a case with no plan steps), named by its `case`."""
    folder = root / PACKAGES
    folder.mkdir(parents=True)
    for case in cases:
        (folder / case["case"]).mkdir()
        (folder / case["case"] / "case.json").write_text(json.dumps(case))
    return root


def with_example(root: Path) -> Path:
    """A checkout at `root` holding the releases guide's refund package, as it is."""
    shutil.copytree(EXAMPLE, root / PACKAGES / "refund")
    return root


def summarized(base: Path, head: Path, catalog: Catalog = CATALOG) -> Summary:
    """The summary of merging `head` onto `base`, every contract of `catalog` recorded and given
    as the base's promise: its contracts match."""
    recorded = {c.reference: contract_hash(c) for c in catalog.contracts()}
    before: dict[str, object] = {c.reference: promise_of(c) for c in catalog.contracts()}
    return summarize(base, head, [PACKAGES], catalog, recorded, before)


# --- Slice 1: what merging does, per package -----------------------------------------------------


def test_a_package_only_in_the_base_is_said_removed(tmp_path: Path) -> None:
    # Never left out: a package the head drops is said, as one it adds is (13e, choice 65).
    base = with_example(tmp_path / "base")
    head = tree(tmp_path / "head")
    found = summarized(base, head)
    assert found.outcomes == (
        (
            "- **refund**: removed: merging it releases nothing; its records and the cases open on "
            "them are untouched."
        ),
    )
    assert found.code == 0


def edited(root: Path, change: Any) -> Path:
    """The refund package in `root`, its case changed by `change`."""
    path = root / PACKAGES / "refund" / "case.json"
    case = json.loads(path.read_text())
    change(case)
    path.write_text(json.dumps(case, indent=2))
    return root


def retitled(case: dict[str, Any]) -> None:
    case["steps"]["settle"]["display"]["title"] = "Pay the refund"


def unrequired(case: dict[str, Any]) -> None:
    case["steps"]["settle"]["requires"] = []  # settle no longer waits for the review


def test_what_merging_does_to_each_package(tmp_path: Path) -> None:
    # 12a's digest and wording, the merge commit against its first parent (brief, D50).
    base = with_example(tmp_path / "base")
    same = with_example(tmp_path / "same")
    reworded = edited(with_example(tmp_path / "reworded"), retitled)
    released = edited(with_example(tmp_path / "released"), unrequired)
    said = {
        "same": summarized(base, same).outcomes,
        "reworded": summarized(base, reworded).outcomes,
        "released": summarized(base, released).outcomes,
        "first": summarized(tree(tmp_path / "empty"), same).outcomes,
    }
    assert said == {
        "same": ("- **refund**: nothing to release.",),
        "reworded": ("- **refund**: a wording revision of its latest release.",),
        "released": (
            (
                "- **refund**: a new release, unless an earlier release has this behaviour "
                "(`ventoux release` decides on merge, from the records)."
            ),
        ),
        "first": ("- **refund**: a new package: its first release.",),
    }


def test_packages_are_matched_by_name_not_by_folder(tmp_path: Path) -> None:
    # A record names a package by its case's `case` (brief, D50): a folder moved is the same one.
    base = with_example(tmp_path / "base")
    head = tmp_path / "head"
    shutil.copytree(EXAMPLE, head / PACKAGES / "refunds")
    assert summarized(base, head).outcomes == ("- **refund**: nothing to release.",)


# --- Slice 2: the diff and the contracts ---------------------------------------------------------


def test_an_input_policy_loosened_reads_as_looser_in_the_summary(tmp_path: Path) -> None:
    # The curriculum's negative test, end to end: one character in the JSON, and a customer's
    # amount could reach the payment. The summary says so, in the diff's own words (13e, choice
    # 68).
    base = tree(tmp_path / "base", refund())
    head = tree(tmp_path / "head", calling("payments.refund@3"))
    found = summarized(base, head, LOOSE)
    assert found.code == 0  # a looser change is the reviewer's to judge, never a failure
    assert "- **refund**: a new release, unless an earlier release has this behaviour" in found.text
    assert (
        "- **Looser** (`steps.pay.activity`): payments.refund@2 -> payments.refund@3: input "
        "amount: was only from a system or a person, never from untrusted data; now any value "
        "(no input policy)."
    ) in found.text


def test_a_contract_changed_in_place_says_what_changed_and_fails(tmp_path: Path) -> None:
    # The base commit's own promise, checked against the lockfile, says each path (brief, D57).
    base, head = with_example(tmp_path / "base"), with_example(tmp_path / "head")
    before: dict[str, Any] = {c.reference: promise_of(c) for c in CATALOG.contracts()}
    before["orders.lookup@1"]["timeouts"]["start_to_close"] = 5
    recorded = {c.reference: contract_hash(c) for c in CATALOG.contracts()}
    recorded["orders.lookup@1"] = promise_hash(before["orders.lookup@1"])
    found = summarize(base, head, [PACKAGES], CATALOG, recorded, before)
    assert found.code == 1
    assert found.text.endswith(
        "## Contracts\n\n```\norders.lookup@1 changed without a new version: register it as "
        "orders.lookup@3.\n  timeouts.start_to_close: 5 -> 10\n```\n"
    )


def test_contracts_that_match_are_said_to(tmp_path: Path) -> None:
    found = summarized(with_example(tmp_path / "base"), with_example(tmp_path / "head"))
    assert found.text == (
        "# What merging changes\n\n## Packages\n\n- **refund**: nothing to release.\n\n"
        "## Contracts\n\nEvery contract matches `contracts.lock.json`.\n"
    )
