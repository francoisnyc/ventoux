"""`ventoux draft-sheet DRAFT --package FOLDER`: "Approve this plan" for a draft in the drafts
folder, to standard output (brief, D64).

The draft must be what `ventoux draft` wrote (its record's digest), and its record must be about
it and its package; whether it passes is checked again by the sheet, never taken from the record.
Exit 0 when it rendered, 2 when it couldn't read, check or render, never with a traceback.
"""

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, ValidationError

from ventoux.authoring.approve import Drafted, NotApprovable, approve_this_plan, reference_of
from ventoux.case.releases import PackageRefused, PackageUnreadable
from ventoux.core.catalog import Catalog
from ventoux.core.plan import problem
from ventoux.tooling.check import shown
from ventoux.tooling.releases import read_package

RENDERED = 0
CANT = 2  # a file, the record, the package or the draft's check refused it


class SheetRefused(Exception):
    """The draft can't be shown for approval; the message says why, then what to do."""


class Round(BaseModel):
    """One round of the loop, as the record keeps it. Never shown: it is the model's text."""

    # Pydantic: a field the record doesn't declare is refused, never ignored.
    model_config = ConfigDict(extra="forbid")

    answer: str  # the model's answer
    problems: list[str]  # what the check found in it


class Record(BaseModel):
    """A draft's record, as `ventoux draft` writes it beside the draft (brief, D63)."""

    model_config = ConfigDict(extra="forbid")

    plan: str  # the plan drafted: `refund-order@1`
    package: str  # the name of the package it was drafted for
    goal: str  # the goal, in the person's words
    asked_by: str  # who asked
    provider: str  # the provider, as it names itself
    rounds: list[Round]  # each round's answer and problems
    verdict: Literal["drafted", "abandoned", "no answer"]
    reason: str | None  # why there is no plan
    warnings: list[str]  # the drafted package's warnings, when drafted
    draft_sha256: str | None  # the SHA-256 of the plan file's bytes, as written


def draft_sheet_command(arguments: argparse.Namespace, catalog: Catalog) -> int:
    """Print "Approve this plan" for the draft at `arguments.draft`, of `arguments.package`."""
    try:
        page = sheet_of(arguments.draft, arguments.package, catalog)
    except (SheetRefused, NotApprovable, PackageRefused, PackageUnreadable, OSError) as refused:
        print(refused, file=sys.stderr)
        return CANT
    print(page, end="")
    return RENDERED


def sheet_of(draft: Path, folder: Path, catalog: Catalog) -> str:
    """The page for `draft`, once every link between it, its record and its package holds."""
    written = draft.read_bytes()
    record = record_of(draft)
    if record.verdict != "drafted":
        raise SheetRefused(
            f"{shown(record_file(draft))} says the draft was {record.verdict}: only a draft that "
            "passed is shown for approval"
        )
    # Only what `ventoux draft` wrote is shown as its draft: an edit makes it a plan written by
    # hand, reviewed as one (brief, D64).
    if hashlib.sha256(written).hexdigest() != record.draft_sha256:
        raise SheetRefused(
            f"{shown(draft)} was changed after it was drafted: its record holds another digest. "
            "A plan edited by hand is reviewed as one: copy it into the package and open a pull "
            "request"
        )
    text = text_of(written, draft)
    if (reference := reference_of(text)) != record.plan:
        raise SheetRefused(
            f"{shown(record_file(draft))} is the record of {record.plan}, and {shown(draft)} is "
            f"{reference}: draft it again"
        )
    before = read_package(folder)
    if before.name != record.package:
        raise SheetRefused(
            f"{shown(record_file(draft))} is a draft for the package {record.package}, and "
            f"{shown(folder)} is {before.name}: give the package it was drafted for"
        )
    # The record's word is taken for provenance only; whether the draft passes is checked again
    # by `approve_this_plan` (brief, D64).
    drafted = Drafted(
        text,
        asked_by=record.asked_by,
        provider=record.provider,
        goal=record.goal,
        rounds=len(record.rounds),
    )
    return approve_this_plan(drafted, before, shown(folder), catalog)


def record_file(draft: Path) -> Path:
    """The record beside the draft: `refund-order@1.record.json` for `refund-order@1.json`."""
    return draft.with_name(f"{draft.stem}.record.json")


def record_of(draft: Path) -> Record:
    """The draft's record, every field required and none extra; refused, saying which, if it
    is missing or doesn't read. Its problems name fields, never quote what they hold."""
    path = record_file(draft)
    if not path.is_file():
        raise SheetRefused(
            f"{shown(draft)} has no record beside it ({shown(path)}): only a plan `ventoux "
            "draft` wrote is shown for approval"
        )
    try:
        return Record.model_validate(json.loads(path.read_text(encoding="utf-8")))
    except ValueError as unread:  # not JSON, or not UTF-8: said by kind, quoting nothing
        if isinstance(unread, ValidationError):
            lines = "; ".join(problem(error) for error in unread.errors())
            raise SheetRefused(f"{shown(path)} doesn't read as a draft's record: {lines}") from None
        raise SheetRefused(f"{shown(path)} doesn't read as a draft's record: not JSON") from None


def text_of(written: bytes, draft: Path) -> str:
    """The draft's bytes as text."""
    try:
        return written.decode("utf-8")
    except UnicodeDecodeError:
        raise SheetRefused(f"{shown(draft)} isn't UTF-8 text: a draft is JSON") from None
