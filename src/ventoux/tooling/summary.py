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

from ventoux.case.diff import diff
from ventoux.case.plain import plain
from ventoux.case.releases import Package, digest, wording
from ventoux.core.catalog import Catalog
from ventoux.core.hash_check import check_hashes
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
# The contracts' line when every one matches the lockfile.
MATCHED = "Every contract matches `contracts.lock.json`."


@dataclass(frozen=True)
class Summary:
    """What the summary says, and how the step ends."""

    outcomes: tuple[str, ...]  # one line per package: what merging does
    code: int  # 0 compared, 1 refused, 2 can't be read
    text: str = ""  # the whole summary, in Markdown


def summarize(
    base: Path,
    head: Path,
    packages: Sequence[str],
    catalog: Catalog,
    recorded: Mapping[str, str],
    before: Mapping[str, object],
) -> Summary:
    """What merging `head` onto `base` does to each package under `packages`, in either tree,
    each changed one's diff in the plain form (brief, D56), then the contracts: the hash check
    against `recorded`, with `before`, the base commit's promises (brief, D57)."""
    old, new = found_in(base, packages), found_in(head, packages)
    outcomes: list[str] = []
    diffs: list[str] = []
    for name in sorted(old.keys() | new.keys()):
        earlier, later = old.get(name), new.get(name)
        outcomes.append(f"- **{name}**: {what_merging_does(earlier, later)}")
        if earlier is not None and later is not None and changed_at_all(earlier, later):
            diffs.append(plain(diff(earlier, later, catalog), earlier, later, catalog))
    problems = check_hashes(catalog, recorded, before)
    lines = ["# What merging changes", "", "## Packages", "", *outcomes]
    for said in diffs:
        lines += ["", said.rstrip("\n")]
    lines += ["", "## Contracts", ""]
    if problems:
        # Kept as the hash check prints them: each changed path indented under its contract.
        lines += ["```", *problems, "```"]
    else:
        lines.append(MATCHED)
    return Summary(tuple(outcomes), 1 if problems else 0, "\n".join(lines) + "\n")


def changed_at_all(before: Package, after: Package) -> bool:
    """Whether merging changes the package's behaviour or its wording: what the diff says."""
    return digest(before) != digest(after) or wording(before) != wording(after)


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
