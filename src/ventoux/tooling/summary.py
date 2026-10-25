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

from ventoux.case.changes import DiffRefused
from ventoux.case.diff import diff
from ventoux.case.markdown import block, code, text
from ventoux.case.plain import plain
from ventoux.case.reading import ReadingRefused
from ventoux.case.releases import Package, PackageRefused, PackageUnreadable, digest, wording
from ventoux.core.catalog import Catalog
from ventoux.core.hash_check import check_hashes
from ventoux.core.validate import Issue
from ventoux.tooling.releases import is_error, issues_of, read_package
from ventoux.tooling.releases import said as as_release_says

# How the step ends: as `ventoux diff` does, a looser change fails nothing (brief, D55).
COMPARED = 0  # every package compared, every contract as the lockfile records
REFUSED = 1  # a package, the diff or a contract refused: said why
CANT_READ = 2  # a checkout can't be read

# What merging does to a package, as the summary says it.
# Each line says only what the two trees show: the summary reads no records, so which release
# the base is, and what merging releases, are `ventoux release`'s to say (13e, choice 78).
NOTHING = "the same behaviour and wording as the base."
REWORDED = (
    "the same behaviour as the base, other wording: a wording revision, if the base's behaviour "
    "is the latest release's (`ventoux release` decides on merge, from the records)."
)
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
# A package in the head `ventoux release` would refuse, changed or not: never said released
# (fix-summary-validation, choice 3).
CANT_RELEASE = "can't be released as it is: `ventoux release` refuses it (below)."
# The most a step's job summary may hold: GitHub shows none of a larger one.
LIMIT = 1024 * 1024

# The contracts' line when every one matches the lockfile.
MATCHED = "Every contract matches `contracts.lock.json`."


@dataclass(frozen=True)
class Summary:
    """What the summary says, and how the step ends."""

    outcomes: tuple[str, ...]  # one line per package: what merging does
    code: int  # COMPARED, REFUSED or CANT_READ: how the step ends
    text: str  # the whole summary, in Markdown
    contracts: str = MATCHED  # the contracts' status, in one line
    failures: tuple[str, ...] = ()  # why the step fails, if it does
    commits: tuple[str, str] | None = None  # the base's and the merge commit's, as CI names them


def summarize(
    base: Path,
    head: Path,
    packages: Sequence[str],
    catalog: Catalog,
    recorded: Mapping[str, str],
    before: Mapping[str, object],
    commits: tuple[str, str] | None = None,
) -> Summary:
    """What merging `head` onto `base` does to each package under `packages`, in either tree,
    each changed one's diff in the plain form (brief, D56), then the contracts: the hash check
    against `recorded`, with `before`, the base commit's promises (brief, D57). Anything it can't
    read or compare fails the step, said last; never read as nothing changed (fail closed)."""
    for tree, which in ((base, "base"), (head, "head")):
        if not tree.is_dir():
            return cant_be_read(f"the {which} can't be read: {tree} isn't a folder")
    old, unread_old = found_in(base, packages, "base")
    new, unread_new = found_in(head, packages, "head")
    failures = [*unread_old, *unread_new]
    outcomes: list[str] = []
    diffs: list[str] = []
    for name in sorted(old.keys() | new.keys()):
        earlier, later = old.get(name), new.get(name)
        unread = unread_new if earlier is not None and later is None else unread_old
        if (earlier is None or later is None) and unread:
            # A package only one tree shows may be the one the other tree can't read: never
            # said removed, or new, on a guess.
            other = "head" if later is None else "base"
            outcomes.append(
                f"- **{text(name)}**: not compared: a package in the {other} can't be read (below)."
            )
            continue
        # Every package in the head is checked as `ventoux release` checks it, changed or not;
        # the base never is (fix-summary-validation, choice 1).
        issues = issues_of(later, catalog) if later is not None else []
        errors = [issue for issue in issues if is_error(issue)]
        failures += [f"{name}, in the head: {as_release_says(issue)}" for issue in errors]
        line = CANT_RELEASE if errors else what_merging_does(earlier, later)
        outcomes.append(f"- **{text(name)}**: {line}")
        if earlier is not None and later is not None and changed_at_all(earlier, later):
            try:
                diffs.append(plain(diff(earlier, later, catalog), earlier, later, catalog))
            except (DiffRefused, ReadingRefused) as refused:
                failures.append(f"{name}: the diff can't be made: {refused}")
        warnings = [issue for issue in issues if not is_error(issue)]
        if warnings and (earlier is None or changed_at_all(earlier, later)):
            # Shown, failing nothing, for a package merging changes; an unchanged package's
            # aren't this pull request's (fix-summary-validation, choice 4).
            diffs.append(warned(name, warnings))
    problems = check_hashes(catalog, recorded, before)
    ending = REFUSED if failures or problems else COMPARED
    said = said_as(outcomes, diffs, problems, failures, commits)
    return Summary(
        tuple(outcomes), ending, said, contracts_line(problems), tuple(failures), commits
    )


def warned(name: str, warnings: Sequence[Issue]) -> str:
    """What `ventoux release` warns about the package `name`, each as it says it."""
    lines = [f"## {text(name)}: what `ventoux release` warns", ""]
    lines += [f"- {text(as_release_says(issue))}" for issue in warnings]
    return "\n".join(lines) + "\n"


def cant_be_read(why: str) -> Summary:
    """A summary that can't be made: why, and nothing else (exit 2)."""
    said = "\n".join(["# What merging changes", "", "## Why the step fails", "", f"- {text(why)}"])
    return Summary((), CANT_READ, said + "\n", "", (why,))


def said_as(
    outcomes: Sequence[str],
    diffs: Sequence[str],
    problems: Sequence[str],
    failures: Sequence[str],
    commits: tuple[str, str] | None = None,
) -> str:
    """The whole summary, in Markdown: the commits compared, the packages, their diffs, the
    contracts, then why the step fails, if it does."""
    lines = [*heading(commits), "## Packages", "", *outcomes]
    for said in diffs:
        lines += ["", said.rstrip("\n")]
    lines += ["", "## Contracts", ""]
    if problems:
        # Kept as the hash check prints them, each changed path indented under its contract, in
        # a block no backtick in them can close: the head's own code writes the catalog.
        lines += block([line for problem in problems for line in problem.splitlines()])
    else:
        lines.append(MATCHED)
    if failures:
        lines += ["", "## Why the step fails", ""]
        lines += [f"- {text(failure)}" for failure in failures]
    return "\n".join(lines) + "\n"


def heading(commits: tuple[str, str] | None) -> list[str]:
    """The summary's title, and the commits compared when CI names them: the tool never reads
    git (brief, D50)."""
    if commits is None:
        return ["# What merging changes", ""]
    base, merged = commits
    return [
        "# What merging changes",
        "",
        f"The merge commit {code(merged)}, against its base {code(base)}.",
        "",
    ]


def contracts_line(problems: Sequence[str]) -> str:
    """The contracts' status in one line, as the short summary says it."""
    if not problems:
        return MATCHED
    return f"{len(problems)} contract{'s' if len(problems) > 1 else ''} not as `contracts.lock.json` records: see the log."


def changed_at_all(before: Package, after: Package) -> bool:
    """Whether merging changes the package's behaviour or its wording: what the diff says."""
    return digest(before) != digest(after) or wording(before) != wording(after)


def found_in(
    tree: Path, packages: Sequence[str], which: str
) -> tuple[dict[str, Package], list[str]]:
    """Each package in `tree`, by name: every folder holding a `case.json` under `packages`; and
    each that can't be read or is refused, said with its folder (fail closed)."""
    found: dict[str, Package] = {}
    unread: list[str] = []
    for root in packages:
        folder = tree / root
        if not folder.is_dir():
            continue
        for candidate in sorted(folder.iterdir()):
            if not (candidate / "case.json").is_file():
                continue
            where = f"{root}/{candidate.name}, in the {which}"
            try:
                read = read_package(candidate)
            except (PackageRefused, PackageUnreadable, OSError) as refused:
                unread.append(f"{where}: {refused}")
                continue
            if read.name in found:
                unread.append(f"{where}: another folder holds {read.name} too")
                continue
            found[read.name] = read
    return found, unread


def what_merging_does(before: Package | None, after: Package | None) -> str:
    """A package's line: what merging does to it, from 12a's digest and wording (brief, D50)."""
    if after is None:
        return REMOVED
    if before is None:
        return FIRST
    if digest(before) != digest(after):
        return RELEASED
    return NOTHING if wording(before) == wording(after) else REWORDED


def for_summary_file(found: Summary, limit: int = LIMIT) -> str:
    """What goes in the job summary: the whole text when it fits in `limit` bytes; else one line
    per package, the contracts' status, why the step fails, and where the whole text is. Never
    cut silently (13e, choice 69)."""
    size = len(found.text.encode())
    if size <= limit:
        return found.text
    lines = [*heading(found.commits), "## Packages", "", *found.outcomes]
    lines += ["", "## Contracts", "", found.contracts]
    if found.failures:
        lines += ["", "## Why the step fails", ""]
        lines += [f"- {text(failure)}" for failure in found.failures]
    lines += [
        "",
        (
            f"The whole summary is {size} bytes, past the job summary's limit of {limit} bytes: it "
            "is in this step's log, under `ventoux summary`."
        ),
    ]
    return "\n".join(lines) + "\n"
