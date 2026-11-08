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
from ventoux.case.releases import PackageRefused, package, read_json
from ventoux.core.catalog import Catalog
from ventoux.core.plan import PlanInvalid, parse_plan
from ventoux.core.promise import promise_of
from ventoux.core.validate import validate
from ventoux.tooling.deployment import DEVELOPMENT, catalog_named
from ventoux.tooling.suite import Entry, Issues, PackageEntry, PlanEntry, Suite, path_of

# The catalogs a suite names, each by the Python catalog its file is generated from. The suite's
# data names a catalog file, never a Python module: this map is the runner's.
CATALOGS = {"development": DEVELOPMENT}

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
    """`catalog` as data, for an implementation that can't read Python: each contract as `ventoux
    promises` writes it, by reference."""
    return {
        "contracts": {contract.reference: promise_of(contract) for contract in catalog.contracts()}
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
    catalog = catalog_named(CATALOGS[entry.catalog], None)
    if isinstance(entry, PlanEntry):
        return plan_given(entry, folder, catalog)
    return package_given(entry, folder, catalog)


def plan_given(entry: PlanEntry, folder: Path, catalog: Catalog) -> list[Found] | RefusedAt:
    """A plan alone: read, then checked as a package's plans are (layer 3)."""
    try:
        plan = parse_plan(read_json((folder / entry.plan).read_text(), entry.plan))
    except PlanInvalid as invalid:
        return RefusedAt(invalid.paths)
    return [(issue.path, issue.code, issue.severity) for issue in validate(plan, catalog)]


def package_given(entry: PackageEntry, folder: Path, catalog: Catalog) -> list[Found] | RefusedAt:
    """A package: its case read, then put together with its plans and checked by `issues_of`, the
    one check `ventoux check` and `ventoux release` refuse on (brief, D50)."""
    text = (folder / entry.case).read_text()
    try:
        parse_case(read_json(text, entry.case))
    except CaseInvalid as invalid:
        return RefusedAt(invalid.paths)
    plans = [(folder / plan).read_text() for plan in entry.plans]
    try:
        released = package(text, plans)
    except PackageRefused as refused:
        raise BrokenEntry(f"a broken entry, not a package: {refused}") from None
    return [(issue.path, issue.code, issue.severity) for issue in issues_of(released, catalog)]


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
