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
from ventoux.case.releases import package, read_json
from ventoux.core.catalog import Catalog
from ventoux.core.promise import promise_of
from ventoux.tooling.deployment import DEVELOPMENT, catalog_named
from ventoux.tooling.suite import Entry, Issues, Suite

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
        problems = "\n".join(
            f"{'.'.join(str(part) for part in e['loc'])}: {e['msg']}" for e in error.errors()
        )
        raise SuiteUnreadable(f"{folder / 'suite.json'} can't be read as a suite:\n{problems}")


def given(entry: Entry, folder: Path) -> list[Found] | RefusedAt:
    """What this engine gives for `entry`, a suite's entry whose files are in `folder`: the issues
    of the one check (`issues_of`), or where its definition is refused when read."""
    catalog = catalog_named(CATALOGS[entry.catalog], None)
    text = (folder / entry.case).read_text()
    try:
        parse_case(read_json(text, entry.case))
    except CaseInvalid as invalid:
        return RefusedAt(invalid.paths)
    released = package(text, [])
    return [(issue.path, issue.code, issue.severity) for issue in issues_of(released, catalog)]


def mismatches(folder: Path) -> list[str]:
    """Every way this engine and the suite in `folder` disagree, one line each, naming the entry
    and both sides. Empty: the engine conforms."""
    found: list[str] = []
    for entry in read_suite(folder).entries:
        found += [f"{entry.name}: {line}" for line in differences(entry, given(entry, folder))]
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
