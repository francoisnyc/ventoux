"""The conformance suite: definitions with the validation results any implementation must give,
as data (layer 20a) (brief, D80).

The suite says what the engine decides about a definition, where the JSON Schema says only what it
looks like (brief, D60). Each entry is a package (a case, its plans, its child cases) or a plan
alone, the catalog it is read against, and what validation must give: the issues, each a path, a
code and a severity, or the paths it is refused at when read. Messages are wording, never
compared. This module runs the suite against this engine, with the one check `ventoux check`
uses (`issues_of`), never a second set of rules (brief, D50).
See docs/layers/20-deployment.md and docs/guides/deployment.md.
"""

import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from ventoux.case.checked import issues_of
from ventoux.case.definition import CaseInvalid, parse_case
from ventoux.case.releases import Package, PackageRefused, package, read_json
from ventoux.core.catalog import Catalog
from ventoux.core.plan import PlanInvalid, parse_plan
from ventoux.core.promise import promise_of
from ventoux.core.validate import ISSUE_CODES, validate
from ventoux.tooling.check import differs, shown
from ventoux.tooling.deployment import DEVELOPMENT, catalog_named
from ventoux.tooling.suite import (
    Child,
    Entry,
    Expected,
    Issues,
    PackageEntry,
    PlanEntry,
    Suite,
    path_of,
)

# The catalogs a suite names, each by the Python catalog its file is generated from. The suite's
# data names a catalog file, never a Python module: this map is the runner's.
CATALOGS = {"development": DEVELOPMENT}

SUITE = Path(__file__).parent.parent / "conformance"  # the suite the package ships

Found = tuple[str, str, str]  # one issue as compared: its path, its code, its severity


@dataclass(frozen=True)
class RefusedAt:
    """A definition refused when read, and the paths it was refused at."""

    paths: tuple[str, ...]


class SuiteUnreadable(Exception):
    """A suite that can't be read as the format says: it can't be run at all."""


class BrokenEntry(Exception):
    """An entry whose files read but can't be put together as a package (a plan missing, one given
    twice): those refusals have no path or code, so the entry is broken, never a result."""


def catalog_data(catalog: Catalog) -> dict[str, Any]:
    """`catalog` as data, for an implementation that can't read Python: everything validation
    reads from it. Each contract as `ventoux promises` writes it, by reference; each role with the
    highest risk it may approve and what else it may do; the systems and labels; each system's
    option check, and each document store's check (brief, D80)."""
    return {
        "contracts": {c.reference: promise_of(c) for c in catalog.contracts()},
        "roles": {
            role: {
                "approves": approves,
                "operates": role in catalog.operators,
                "forgets": role in catalog.forgetters,
                "edits": role in catalog.editors,
                "migrates": role in catalog.migrators,
                "assigns": role in catalog.assigners,
            }
            for role, approves in catalog.roles.items()
        },
        "systems": catalog.systems,
        "labels": catalog.labels,
        "option_checks": {
            system: check
            for system in catalog.systems
            if (check := catalog.option_check(system)) is not None
        },
        "document_stores": {
            system: check
            for system in catalog.systems
            if (check := catalog.document_store(system)) is not None
        },
    }


def catalog_files() -> dict[str, str]:
    """Each catalog file a suite names, by its path in the suite, as its Python catalog gives it:
    what `--write` writes and `--unchanged` compares, byte for byte, as the schema is (brief, D60)."""
    return {
        f"catalogs/{name}.json": json.dumps(
            catalog_data(catalog_named(module, None)), indent=2, sort_keys=True
        )
        + "\n"
        for name, module in CATALOGS.items()
    }


def read_suite(folder: Path) -> Suite:
    """The suite in `folder`, or `SuiteUnreadable` saying every problem with its path."""
    try:
        return Suite.model_validate(json.loads((folder / "suite.json").read_text()))
    except ValidationError as error:
        problems = "\n".join(f"{path_of(e['loc'])}: {e['msg']}" for e in error.errors())
        raise SuiteUnreadable(
            f"{folder / 'suite.json'} can't be read as a suite:\n{problems}"
        ) from None


def given(entry: Entry, folder: Path) -> list[Found] | RefusedAt:
    """What this engine gives for `entry`, a suite's entry whose files are in `folder`: the issues
    of the check `ventoux check` makes, or where its definition is refused when read."""
    if entry.catalog not in CATALOGS:
        raise BrokenEntry(
            f"a broken entry: it names the catalog {entry.catalog}, and this runner knows "
            f"{', '.join(sorted(CATALOGS))}"
        )
    catalog = catalog_named(CATALOGS[entry.catalog], None)
    if isinstance(entry, PlanEntry):
        return plan_given(entry, folder, catalog)
    return package_given(entry, folder, catalog)


def plan_given(entry: PlanEntry, folder: Path, catalog: Catalog) -> list[Found] | RefusedAt:
    """A plan alone: read, then checked as a package's plans are (layer 3)."""
    try:
        plan = parse_plan(read_json(text_of(folder, entry.plan), entry.plan))
    except PlanInvalid as invalid:
        return RefusedAt(invalid.paths)
    return [(issue.path, issue.code, issue.severity) for issue in validate(plan, catalog)]


def package_given(entry: PackageEntry, folder: Path, catalog: Catalog) -> list[Found] | RefusedAt:
    """A package: its case read, then put together with its plans and checked by `issues_of`, the
    one check `ventoux check` and `ventoux release` refuse on (brief, D50)."""
    text = text_of(folder, entry.case)
    try:
        parse_case(read_json(text, entry.case))
    except CaseInvalid as invalid:
        return RefusedAt(invalid.paths)
    try:
        released = put_together(folder, entry.case, entry.plans, entry.cases)
    except PackageRefused as refused:
        raise BrokenEntry(f"a broken entry, not a package: {refused}") from None
    return [(issue.path, issue.code, issue.severity) for issue in issues_of(released, catalog)]


def put_together(folder: Path, case: str, plans: list[str], cases: dict[str, Child]) -> Package:
    """The package of `case` with its `plans` and child `cases`, files in `folder`, as `ventoux
    release` puts one together; `PackageRefused` when it can't be."""
    children = {
        reference: package(
            text_of(folder, child.case), [text_of(folder, plan) for plan in child.plans]
        )
        for reference, child in cases.items()
    }
    return package(text_of(folder, case), [text_of(folder, p) for p in plans], children)


def text_of(folder: Path, name: str) -> str:
    """The file `name` of the suite in `folder`; a file an entry names that isn't there is a broken
    entry, said, never an error that stops the run."""
    path = folder / name
    if not path.is_file():
        raise BrokenEntry(f"a broken entry: {name} isn't in the suite")
    return path.read_text()


def mismatches(folder: Path) -> list[str]:
    """Every way this engine and the suite in `folder` disagree, one line each, naming the entry
    and both sides. Empty: the engine conforms."""
    found: list[str] = []
    for entry in read_suite(folder).entries:
        # Every entry is run, whatever the others give: one broken entry never hides another.
        try:
            lines = differences(entry, given(entry, folder))
        except BrokenEntry as broken:
            lines = [str(broken)]
        found += [f"{entry.name}: {line}" for line in lines]
    return found


def differences(entry: Entry, got: list[Found] | RefusedAt) -> list[str]:
    """How what this engine gave differs from what `entry` expects, both sides said."""
    expected = entry.expected
    if isinstance(expected, Issues):
        if isinstance(got, RefusedAt):
            return [f"expected to be read, refused when read at {', '.join(got.paths)}"]
        # Compared as a multiset: in any order, none missing, none extra.
        wanted = Counter[Found]((i.path, i.code, i.severity) for i in expected.issues)
        given_ = Counter(got)
        return [
            f"expected {path} {code} ({severity}), not given"
            for path, code, severity in sorted((wanted - given_).elements())
        ] + [
            f"given {path} {code} ({severity}), not expected"
            for path, code, severity in sorted((given_ - wanted).elements())
        ]
    at = ", ".join(sorted(expected.at))
    if not isinstance(got, RefusedAt):
        return [f"expected refused when read at {at}, read"]
    if sorted(expected.at) != sorted(got.paths):
        return [f"expected refused when read at {at}, refused at {', '.join(sorted(got.paths))}"]
    return []


def uncovered(folder: Path) -> list[str]:
    """Each listed issue code no entry of the suite in `folder` expects, one line each: a rule the
    suite says nothing about, so another implementation could leave it out and still conform
    (brief, D80)."""
    expected = {
        issue.code
        for entry in read_suite(folder).entries
        if isinstance(entry.expected, Issues)
        for issue in entry.expected.issues
    }
    suite = read_suite(folder)
    said = {refused.code for refused in suite.refused_first}
    return [
        f"{code}: listed, and no entry expects it" for code in sorted(ISSUE_CODES - expected - said)
    ]


def refused_first_problems(folder: Path) -> list[str]:
    """Each code the suite in `folder` says the package refuses first, whose package is put
    together all the same: the claim checked, never taken on trust."""
    found: list[str] = []
    for refused in read_suite(folder).refused_first:
        try:
            put_together(folder, refused.case, refused.plans, refused.cases)
        except PackageRefused:
            continue
        except BrokenEntry as broken:
            found.append(f"{refused.code}: said refused before validation: {broken}")
            continue
        found.append(
            f"{refused.code}: said refused before validation, and its package is put together: "
            "give an entry expecting it instead"
        )
    return found


def unrecorded(base: Suite, head: Suite) -> list[str]:
    """Each line of `base`'s changes `head` doesn't keep, and each entry whose expected result
    `head` changes or removes from `base` with no line of `head`'s changes saying so, exactly:
    what it was and what it is now. A new entry needs none (brief, D80)."""
    found = dropped_lines(base, head)
    now = {entry.name: entry.expected for entry in head.entries}
    for entry in base.entries:
        after = now.get(entry.name)
        if after is not None and same(entry.expected, after):
            continue
        said = any(
            line.entry == entry.name and same(line.was, entry.expected) and same(line.now, after)
            for line in head.changes
        )
        if not said:
            how = "removed" if after is None else "its expected result changed"
            found.append(
                f"{entry.name}: {how}, and no line of changes names it: add one saying what it "
                "was, what it is now, why and when"
            )
    return found


def dropped_lines(base: Suite, head: Suite) -> list[str]:
    """Each line of `base`'s changes that `head` doesn't keep where it was, unchanged: the record
    an implementer reads is never removed or rewritten, only added to (brief, D80)."""
    found: list[str] = []
    for number, line in enumerate(base.changes, start=1):
        kept = head.changes[number - 1] if number <= len(head.changes) else None
        if kept == line:
            continue
        how = "went" if kept is None else "changed"
        found.append(
            f"changes line {number} ({line.entry}, {line.date}) {how}: a line of changes is never "
            "removed or rewritten; put it back as it was"
        )
    return found


def same(one: Expected | None, other: Expected | None) -> bool:
    """Whether two expected results say the same: issues in any order, paths in any order."""
    return as_compared(one) == as_compared(other)


def as_compared(expected: Expected | None) -> object:
    """An expected result as it is compared: a sorted list of issues, or the sorted paths."""
    if expected is None:
        return None
    if isinstance(expected, Issues):
        return sorted((issue.path, issue.code, issue.severity) for issue in expected.issues)
    return ("refused when read", sorted(expected.at))


DONE = 0  # the suite conforms, or the catalog files were written
FAILED = 1  # a mismatch, a code uncovered, or a catalog file not as generated: each said
CANT_READ = 2  # the suite can't be read


def conformance_command(folder: Path, write: bool) -> int:
    """`ventoux conformance`: with `write`, write the catalog files, never an expected result,
    which a person writes; else check that this engine conforms to the suite in `folder`, its
    catalog files as generated, and every listed code expected by an entry."""
    files = catalog_files()
    if write:
        for name, text in files.items():
            (folder / name).parent.mkdir(parents=True, exist_ok=True)
            (folder / name).write_text(text)
            print(f"✓ {shown(folder / name)}: what the catalog gives")
        return DONE
    problems: list[str] = []
    for name, text in files.items():
        committed = folder / name
        if not committed.is_file():
            problems.append(f"{shown(committed)} is missing: ventoux conformance --write writes it")
        elif committed.read_text() != text:
            gives = f"what the {Path(name).stem} catalog gives"
            problems.append(differs(shown(committed), gives, committed.read_text(), text))
    try:
        problems += mismatches(folder) + uncovered(folder) + refused_first_problems(folder)
    except SuiteUnreadable as unreadable:
        print(unreadable)
        return CANT_READ
    for problem in problems:
        print(problem)
    if problems:
        return FAILED
    print(f"✓ this engine conforms to {shown(folder)}")
    return DONE


def since_command(base: Path, head: Path) -> int:
    """`ventoux conformance --since BASE`: each result the suite in `head` changes or removes from
    the one in `base` with no line of changes saying so. A base with no suite (before the suite
    existed) has no result to compare."""
    if not (base / "suite.json").is_file():
        print(f"{shown(base)} has no suite.json: no result to compare")
        return DONE
    try:
        problems = unrecorded(read_suite(base), read_suite(head))
    except SuiteUnreadable as unreadable:
        print(unreadable)
        return CANT_READ
    for problem in problems:
        print(problem)
    if problems:
        return FAILED
    print(f"✓ every result {shown(head)} changes is said in its changes")
    return DONE


def export_command(folder: Path, out: Path) -> int:
    """`ventoux conformance --export OUT`: the suite's files, byte for byte, into `out`, for an
    implementer who doesn't install Python. Never into a folder holding files, so an export is
    never mixed with something else."""
    if out.exists() and not out.is_dir():
        print(f"{shown(out)} is a file, not a folder: export into a new folder")
        return CANT_READ
    if out.exists() and any(out.iterdir()):
        print(f"{shown(out)} holds files already: export into a new folder")
        return CANT_READ
    files = [path for path in sorted(folder.rglob("*")) if path.is_file()]
    for path in files:
        target = out / path.relative_to(folder)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(path.read_bytes())
    print(f"✓ {len(files)} files of the conformance suite written into {shown(out)}")
    return DONE
