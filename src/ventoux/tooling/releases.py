"""The release tool's I/O: a package's folder, and the folder its records are kept in (layer 12a).

What to release is decided in `case.releases`, which reads no file; here the folder is read, the
package is checked, and the record is written once (brief, D50). See docs/guides/releases.md.
"""

import json
from collections.abc import Sequence
from dataclasses import dataclass, replace
from decimal import Decimal
from pathlib import Path
from typing import Any

from pydantic import TypeAdapter, ValidationError

from ventoux.case.changes import Notes
from ventoux.case.notes import notes_for
from ventoux.case.releases import (
    Hash,
    Outcome,
    Package,
    PackageRefused,
    PackageUnreadable,
    Record,
    RecordRefused,
    Released,
    Reworded,
    digest,
    next_release,
    package,
    record,
)
from ventoux.case.validate import validate_case
from ventoux.core.catalog import Catalog
from ventoux.core.validate import Issue, validate

# Pydantic: a `TypeAdapter` checks and converts plain data against any type, here the record's
# dataclasses, as a model would; `dump_python(mode="json")` gives it back as plain JSON values.
RECORD = TypeAdapter(Record)


def read_package(folder: Path) -> Package:
    """The package in `folder`: `case.json`, and each plan in `plans/` as a `.json` file. Any
    other file is refused, never ignored (brief, D50)."""
    if not (folder / "case.json").is_file():
        raise PackageUnreadable(f"{folder} has no case.json: a package is a folder holding one")
    problems: list[str] = []
    for entry in sorted(folder.iterdir()):
        if entry.name not in ("case.json", "plans"):
            problems.append(
                f"{entry.name} isn't part of a package: a package holds case.json and plans/"
            )
    plans = folder / "plans"
    texts: list[str] = []
    if plans.is_dir():
        for entry in sorted(plans.iterdir()):
            if entry.suffix != ".json" or not entry.is_file():
                problems.append(
                    f"plans/{entry.name} isn't a plan's file: each plan is a .json file"
                )
            else:
                texts.append(entry.read_text())
    if problems:
        raise PackageRefused("\n".join(problems))
    return package((folder / "case.json").read_text(), texts)


@dataclass(frozen=True)
class FolderStore:
    """Release records kept as files: `<root>/<package>/<n>.json`, and a wording revision as
    `<n>.wording-<k>.json`. Each is written once."""

    root: Path

    def records(self, name: str) -> list[Record]:
        """Every record of the package `name`, each checked against its file's name."""
        folder = self.root / name
        if not folder.is_dir():
            return []
        found: list[Record] = []
        for path in sorted(folder.iterdir()):
            kept = record_from(path)
            if path.name != file_name(kept):
                raise RecordRefused(f"{path} holds {file_name(kept)}'s record: put it back")
            found.append(kept)
        return found

    def get(self, name: str, release: int, wording: int = 1) -> Record:
        """The record of `name`'s release `release` (its wording revision `wording`), or
        `RecordRefused` if there is none."""
        for kept in self.records(name):
            if (kept.release, kept.wording) == (release, wording):
                return kept
        wanted = f"{name} {release}" + (f", wording {wording}" if wording > 1 else "")
        raise RecordRefused(f"{wanted} isn't released: no record of it in {self.root / name}")

    def write(self, kept: Record) -> bool:
        """Write `kept` as its file; False if that file already holds the same bytes. A file is
        never written over: other bytes are refused (brief, D50)."""
        if kept.notes is None:
            # Only a record written before layer 13d has none; a new one never goes without
            # (brief, D57).
            wording = f", wording {kept.wording}" if kept.wording > 1 else ""
            raise RecordRefused(
                f"{kept.name} {kept.release}{wording} has no notes: nothing is recorded without "
                "its notes"
            )
        path = self.root / kept.name / file_name(kept)
        text = record_text(kept)
        if path.exists():
            if path.read_text() == text:
                return False
            raise RecordRefused(
                f"{path} already exists, with other content: a record is never written over"
            )
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("x") as file:  # "x": create, and refuse if it appeared meanwhile
            file.write(text)
        return True


def file_name(kept: Record) -> str:
    """`3.json` for a release, `3.wording-2.json` for its second wording."""
    if kept.wording == 1:
        return f"{kept.release}.json"
    return f"{kept.release}.wording-{kept.wording}.json"


def record_text(kept: Record) -> str:
    """The record as the JSON its file holds."""
    return json.dumps(RECORD.dump_python(kept, mode="json"), indent=2, sort_keys=True) + "\n"


def record_from(path: Path) -> Record:
    """The record in `path`, or `RecordRefused` saying what is wrong with it."""
    try:
        return RECORD.validate_python(json.loads(path.read_text()))
    except (json.JSONDecodeError, ValidationError) as error:
        raise RecordRefused(f"{path} can't be read as a release record: {error}") from None


@dataclass(frozen=True)
class Run:
    """What one run of the tool did, and the warnings it printed."""

    package: str  # the package's name: `refund`
    digest: Hash  # its behaviour digest, now
    outcome: Outcome
    warnings: Sequence[Issue]
    written: bool  # a record was written now; False when it was already there, or nothing was due
    notes: Notes | None = None  # the notes of the record it made; None when it made none


def release(folder: Path, store: FolderStore, commit: str, catalog: Catalog) -> Run:
    """Release the package in `folder`, if its behaviour or wording changed: checked first, then
    compared with its records, then recorded once (brief, D50)."""
    released = read_package(folder)
    warnings = checked(released, catalog)
    records = store.records(released.name)
    outcome = next_release(released, records)
    wrote, notes = False, None
    if isinstance(outcome, Released | Reworded):
        made = record(released, outcome, commit, catalog)
        # Nothing is recorded without its notes, made from the stored packages (brief, D57).
        notes = notes_for(made, records, catalog)
        wrote = store.write(replace(made, notes=notes))
    return Run(released.name, digest(released), outcome, warnings, wrote, notes)


def checked(released: Package, catalog: Catalog) -> list[Issue]:
    """The package's warnings, once no error refuses it: each plan (layer 3), then the case
    (layer 10), against `catalog`. Only a package that passes is released (brief, D50)."""
    stored: dict[str, Any] = {
        reference: json.loads(text, parse_float=Decimal)
        for reference, text in released.written.plans.items()
    }
    issues = [
        Issue(f"plans.{reference}.{issue.path}", issue.code, issue.message, issue.severity)
        for reference, plan in released.plans.items()
        for issue in validate(plan, catalog)
    ]
    issues += validate_case(released.case, catalog, stored)
    errors = [issue for issue in issues if issue.severity != "warning"]  # neither is an error
    if errors:
        raise PackageRefused("\n".join(said(issue) for issue in errors))
    return issues


def said(issue: Issue) -> str:
    """An issue as a line: `steps.pay.when: EXPRESSION_INVALID: …`."""
    return f"{issue.path}: {issue.code}: {issue.message}"
