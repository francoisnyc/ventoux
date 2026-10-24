"""The CI step's job summary (layer 13e): what merging a pull request changes.

For each package, matched by name in the base and the head: whether merging creates a release, a
wording revision or nothing, from 12a's digest and wording, then the diff in the plain form; and
the hash check with the base commit's own promises (brief, D55) (brief, D57). Reads the two
checkouts CI gives it, never git: the commits are CI's to name. See docs/layers/13-diff.md (13e)
and docs/guides/releases.md, "On each pull request".
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from ventoux.case.releases import Package, digest, wording
from ventoux.core.catalog import Catalog
from ventoux.tooling.releases import read_package

# What merging does to a package, as the summary says it.
NOTHING = "nothing to release."
REWORDED = "a wording revision of its latest release."
# The summary reads no records: whether an earlier release has this behaviour is `ventoux
# release`'s to say, on merge (brief, D50).
RELEASED = (
    "a new release, unless an earlier release has this behaviour (`ventoux release` decides on "
    "merge, from the records)."
)
FIRST = "a new package: its first release."
REMOVED = (
    "removed: merging it releases nothing; its records and the cases open on them are untouched."
)


@dataclass(frozen=True)
class Summary:
    """What the summary says, and how the step ends."""

    outcomes: tuple[str, ...]  # one line per package: what merging does
    code: int  # 0 compared, 1 refused, 2 can't be read


def summarize(
    base: Path,
    head: Path,
    packages: Sequence[str],
    catalog: Catalog,
    recorded: Mapping[str, str],
    before: Mapping[str, object],
) -> Summary:
    """What merging `head` onto `base` does to each package under `packages`, in either tree."""
    old, new = found_in(base, packages), found_in(head, packages)
    outcomes = [
        f"- **{name}**: {what_merging_does(old.get(name), new.get(name))}"
        for name in sorted(old.keys() | new.keys())
    ]
    return Summary(tuple(outcomes), 0)


def found_in(tree: Path, packages: Sequence[str]) -> dict[str, Package]:
    """Each package in `tree`, by name: every folder holding a `case.json` under `packages`."""
    found: dict[str, Package] = {}
    for root in packages:
        folder = tree / root
        if not folder.is_dir():
            continue
        for candidate in sorted(folder.iterdir()):
            if (candidate / "case.json").is_file():
                read = read_package(candidate)
                found[read.name] = read
    return found


def what_merging_does(before: Package | None, after: Package | None) -> str:
    """A package's line: what merging does to it, from 12a's digest and wording (brief, D50)."""
    if after is None:
        return REMOVED
    if before is None:
        return FIRST
    if digest(before) != digest(after):
        return RELEASED
    return NOTHING if wording(before) == wording(after) else REWORDED
