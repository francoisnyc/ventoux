"""Releases: a package, its behaviour digest, its number and its record (layer 12a).

A package is a case definition and the plans its plan steps run. Its release is decided here,
never asked of a person: the behaviour digest hashes everything that can change a decision, and
leaves out only `display`, the wording (brief, D5). Every doubt is a release: a change of
behaviour taken for wording would reach every open case unreviewed (brief, D50).

Pure: reading the folder and writing records is `tooling.releases`'s. See docs/layers/12-releases.md
(12a) and docs/guides/releases.md.
"""

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Any, Literal, get_origin

from pydantic import BaseModel

from ventoux.case.changes import Notes
from ventoux.case.definition import (
    ApprovalDisplay,
    CallStep,
    CaseDefinition,
    CaseInvalid,
    PlanStep,
    parse_case,
)
from ventoux.core.catalog import Catalog
from ventoux.core.contract_hash import contract_hash
from ventoux.core.expressions.model import Node
from ventoux.core.plan import ActivityState, Display, Plan, PlanInvalid, parse_plan

# The hash method this code computes digests and contract hashes with (design question 16): a
# record says which method made each hash, so a later method is never mistaken for a change.
METHOD = 1

# What a definition shows people and nothing reads to decide: wording (brief, D5). Found by its
# type, never by a key's name, since a case-file field may be called `display`.
WORDING = (Display, ApprovalDisplay)


class PackageUnreadable(Exception):
    """A file of a package that isn't JSON: it can't be read at all."""


class PackageRefused(Exception):
    """A package that can't be released: one line per problem."""


class RecordRefused(Exception):
    """A record that can't be trusted to compare with: one line per problem."""


@dataclass(frozen=True)
class Hash:
    """A digest, and the method that made it."""

    method: int  # which hash method made it (design question 16)
    sha256: str  # the SHA-256, in hex


@dataclass(frozen=True)
class Written:
    """A package as its files say it, kept so a release can be read again exactly."""

    case: str  # case.json's text
    plans: Mapping[str, str]  # each plan's text, by its reference (`refund-order@1`)


@dataclass(frozen=True)
class Package:
    """A case definition and the plans it runs, parsed, and as written."""

    name: str  # its case's name: `refund`
    case: CaseDefinition
    plans: Mapping[str, Plan]  # by reference, in the order of their references
    written: Written


@dataclass(frozen=True)
class Changed:
    """What changed since the release before, by path, behaviour and wording apart. Paths only:
    never a value (brief, D50)."""

    behaviour: tuple[str, ...] = ()
    wording: tuple[str, ...] = ()


@dataclass(frozen=True)
class Released:
    """The behaviour changed: release `release`."""

    release: int
    changed: Changed


@dataclass(frozen=True)
class Reworded:
    """Only the wording changed: wording revision `wording` of release `release`."""

    release: int
    wording: int  # from 2: a release is its own first wording
    changed: Changed


@dataclass(frozen=True)
class SameAs:
    """The behaviour and wording of an earlier release, not the latest: nothing released."""

    release: int


@dataclass(frozen=True)
class Unchanged:
    """Nothing changed since the latest release: nothing written."""

    release: int


type Outcome = Released | Reworded | SameAs | Unchanged


@dataclass(frozen=True)
class Record:
    """A release, or a wording revision of one, as it is kept for good."""

    name: str  # the package
    release: int
    wording: int  # 1 for the release itself; from 2 for a wording revision of it
    digest: Hash
    commit: str  # the commit CI released from
    contracts: Mapping[str, Hash]  # every contract the package needs, its plans' included
    written: Written
    changed: Changed = field(default_factory=Changed)
    # Its notes, made with it (brief, D57); None in a record written before layer 13d.
    notes: Notes | None = None


def package(case: str, plans: Sequence[str]) -> Package:
    """The package of `case`, case.json's text, and `plans`, each plan file's text. Refused unless
    the plans are exactly those its plan steps name, each once (brief, D50)."""
    try:
        definition = parse_case(read_json(case, "case.json"))
    except CaseInvalid as invalid:
        raise PackageRefused(f"case.json can't be read as a case definition:\n{invalid}") from None
    found: dict[str, Plan] = {}
    texts: dict[str, str] = {}
    problems: list[str] = []
    for text in plans:
        try:
            plan = parse_plan(read_json(text, "a plan"))
        except PlanInvalid as invalid:
            raise PackageRefused(f"a plan can't be read as a plan:\n{invalid}") from None
        reference = f"{plan.plan}@{plan.version}"
        if reference in found:
            problems.append(f"{reference} is given twice: keep one file for it")
        found[reference] = plan
        texts[reference] = text
    named = {step.plan for step in definition.steps.values() if isinstance(step, PlanStep)}
    for reference in sorted(named - set(found)):
        problems.append(f"{reference} is run by a plan step and isn't in plans/: add it")
    for reference in sorted(set(found) - named):
        problems.append(f"{reference} is run by no plan step: remove it, or name it in a step")
    if problems:
        raise PackageRefused("\n".join(problems))
    order = sorted(found)  # a folder's plans have no order: their references give one
    return Package(
        definition.case,
        definition,
        {reference: found[reference] for reference in order},
        Written(case, {reference: texts[reference] for reference in order}),
    )


def read_json(text: str, what: str) -> Any:
    """`text` as JSON, numbers as exact decimals, as the engine reads a definition (brief, D20)."""
    try:
        return json.loads(text, parse_float=Decimal)
    except json.JSONDecodeError as error:
        raise PackageUnreadable(f"{what} isn't JSON: {error}") from None


# --- The behaviour digest -----------------------------------------------------------------------

# Fields a definition writes beside their neighbours, never under their own key: a case-file
# field's `declared` type is `"type": "number"` next to its `display`.
WRITTEN_BESIDE = {"declared"}

# A plan keeps each field's source in a map of its own; the JSON writes it on the field, as
# `fields.amount.source`, so a changed one is named there.
WRITTEN_ON_FIELDS = {"sources"}

ABSENT = object()  # a field the digest leaves out: wording, or a value at its default


def canonical(value: object) -> object:
    """`value`, a parsed definition or a part of one, as plain JSON data that says its behaviour
    and nothing else. Objects are dicts, whose keys `json.dumps` sorts; a map (steps, rules,
    fields) keeps its written order, as `{"#map": [[key, value], ...]}`, since the engine reads
    steps and rules in that order (brief, D38). A decimal is `{"#decimal": "100.0"}`, so a number
    and a text never meet; a date is `{"#date": "2026-10-31"}`, for the same reason. `#` starts no name in the format, so neither marker meets a field."""
    if isinstance(value, BaseModel):
        found: dict[str, object] = {}
        for name in type(value).model_fields:
            kept = behaviour_of(value, name)
            if kept is not ABSENT:
                found[key_of(value, name)] = kept
        return found
    if isinstance(value, Mapping):
        return {"#map": [[key, canonical(item)] for key, item in value.items()]}
    if isinstance(value, tuple | list):
        return [canonical(item) for item in value]
    if isinstance(value, Decimal):
        return {"#decimal": str(value)}
    if type(value) is date:
        # A day, as `{"#date": "2026-10-31"}`: never the text "2026-10-31", which it isn't. No
        # package digested before 16a holds one, so method 1 gives them all the same digest
        # (brief, D51) (brief, D66).
        return {"#date": value.isoformat()}
    if value is None or isinstance(value, str | bool | int):
        return value
    # Fail closed: a kind of value this code doesn't know is never left out of the digest.
    raise TypeError(f"the behaviour digest can't read a {type(value).__name__}")


def behaviour_of(model: BaseModel, name: str) -> object:
    """The field `name` of `model` as the digest reads it, or ABSENT: wording, or a value at its
    default. A field naming which shape its object is (`"type": "number"`) is always kept, even
    at its default: left out, a number field and a text field would digest alike."""
    value = getattr(model, name)
    if isinstance(value, WORDING):
        return ABSENT
    declared = type(model).model_fields[name]
    names_its_shape = get_origin(declared.annotation) is Literal
    at_default = not declared.is_required() and (
        value == declared.get_default(call_default_factory=True)
    )
    if at_default and not names_its_shape:
        return ABSENT  # written or not, the same behaviour
    return canonical(value)


def key_of(model: BaseModel, name: str) -> str:
    """The key the field `name` is written under: its alias (`rules`, `==`), or its name."""
    alias = type(model).model_fields[name].alias
    return alias if alias is not None else name


def behaviour(case: CaseDefinition, plans: Mapping[str, Plan]) -> object:
    """A package's behaviour, as plain data: its case, then its plans in their references' order."""
    return {
        "case": canonical(case),
        "plans": {"#map": [[ref, canonical(plans[ref])] for ref in sorted(plans)]},
    }


def digest(released: Package) -> Hash:
    """The behaviour digest: SHA-256 of the behaviour written canonically (brief, D50)."""
    return behaviour_digest(released.case, released.plans)


def behaviour_digest(case: CaseDefinition, plans: Mapping[str, Plan]) -> Hash:
    """The digest of a case and its plans, however they were read."""
    text = json.dumps(behaviour(case, plans), sort_keys=True, separators=(",", ":"))
    return Hash(METHOD, hashlib.sha256(text.encode()).hexdigest())


def is_release(case: CaseDefinition, plans: Mapping[str, object], given: Hash) -> bool:
    """Whether `case` and `plans`, stored data by reference as a case's start holds them, are the
    package whose digest is `given`: a method this code knows, each plan under its own reference,
    and the same digest. A case checks it when it opens, depending on nothing the client did
    (brief, D51)."""
    if given.method != METHOD:
        return False
    try:
        parsed = {reference: parse_plan(data) for reference, data in plans.items()}
    except PlanInvalid:
        return False
    if any(f"{plan.plan}@{plan.version}" != reference for reference, plan in parsed.items()):
        return False
    return behaviour_digest(case, parsed) == given


# --- What changed --------------------------------------------------------------------------------


def wording(released: Package) -> dict[str, object]:
    """Every piece of wording in the package, by its path: `steps.pay.display.title`."""
    found: dict[str, object] = {}
    collect_wording(released.case, "", found)
    for reference, plan in released.plans.items():
        collect_wording(plan, f"plans.{reference}", found)
    return found


def collect_wording(value: object, path: str, found: dict[str, object]) -> None:
    """Add the wording under `value`, at `path`, to `found`."""
    if isinstance(value, WORDING):
        for name in type(value).model_fields:
            found[joined(path, name)] = getattr(value, name)
    elif isinstance(value, BaseModel):
        for name in type(value).model_fields:
            collect_wording(getattr(value, name), joined(path, key_of(value, name)), found)
    elif isinstance(value, Mapping):
        for key, item in value.items():
            collect_wording(item, joined(path, str(key)), found)
    elif isinstance(value, tuple | list):
        for index, item in enumerate(value):
            collect_wording(item, f"{path}[{index}]", found)


def joined(path: str, name: str) -> str:
    """`steps` and `pay` make `steps.pay`; the root's children have no dot before them."""
    return f"{path}.{name}" if path else name


def changed(before: Package, after: Package) -> Changed:
    """What changed from `before` to `after`, by path: behaviour where the digest reads it, and
    wording. A path names where; it never quotes a value."""
    paths = differences(before.case, after.case, "")
    for reference in sorted(set(before.plans) | set(after.plans)):
        if reference not in before.plans or reference not in after.plans:
            paths.append(f"plans.{reference}")
        else:
            paths += differences(
                before.plans[reference], after.plans[reference], f"plans.{reference}"
            )
    old, new = wording(before), wording(after)
    reworded = sorted(path for path in set(old) | set(new) if old.get(path) != new.get(path))
    return Changed(tuple(paths), tuple(reworded))


def differences(before: object, after: object, path: str) -> list[str]:
    """The paths where `before` and `after` behave differently, as deep as a reader needs: an
    expression is named whole (`steps.pay.when`), a map's added, removed or reordered entries by
    the map, its changed ones by their own paths."""
    if canonical(before) == canonical(after):
        return []
    retyped = isinstance(before, BaseModel) and type(before) is not type(after)
    if retyped and isinstance(before, BaseModel) and "type" in type(before).model_fields:
        return [joined(path, "type")]  # a field's type, written `"type": "number"`
    both_objects = isinstance(before, BaseModel) and type(before) is type(after)
    if both_objects and not isinstance(before, Node):
        assert isinstance(before, BaseModel) and isinstance(after, BaseModel)
        found: list[str] = []
        for name in type(before).model_fields:
            old, new = behaviour_of(before, name), behaviour_of(after, name)
            if old != new:
                old_value, new_value = getattr(before, name), getattr(after, name)
                if name in WRITTEN_ON_FIELDS and isinstance(before, Plan):
                    found += sources_changed(old_value, new_value, path)
                    continue
                # A field's declared type is written beside its display, not under a key.
                where = path if name in WRITTEN_BESIDE else joined(path, key_of(before, name))
                found += differences(old_value, new_value, where) or [where]
        return found
    if isinstance(before, Mapping) and isinstance(after, Mapping):
        found = []
        for key in [*before, *(key for key in after if key not in before)]:
            if key not in before or key not in after:
                found.append(joined(path, str(key)))
            else:
                found += differences(before[key], after[key], joined(path, str(key)))
        return found or [path]  # the same entries, in another order
    return [path]


def sources_changed(before: Mapping[str, str], after: Mapping[str, str], path: str) -> list[str]:
    """Each plan field whose source changed, named where the JSON writes it."""
    names = [*before, *(name for name in after if name not in before)]
    return [
        joined(path, f"fields.{name}.source")
        for name in names
        if before.get(name) != after.get(name)
    ]


# --- The next release ----------------------------------------------------------------------------


def next_release(released: Package, records: Sequence[Record]) -> Outcome:
    """What the tool does with `released`, given the package's `records`: a release, a wording
    revision, or nothing (brief, D50). Every record is read again first, from the package it
    stored (`stored`), so a record that can't be trusted is refused, never compared."""
    kept = [(record, stored(record, released.name)) for record in records]
    releases = [record for record, _ in kept if record.wording == 1]
    if not releases:
        return Released(1, Changed())
    # Each release's latest wording: the package people see for it now.
    latest = {
        record.release: max(
            ((r, p) for r, p in kept if r.release == record.release), key=lambda rp: rp[0].wording
        )
        for record in releases
    }
    newest = max(latest)
    target = digest(released)
    same = [record.release for record in releases if record.digest == target]
    if not same:
        return Released(newest + 1, changed(latest[newest][1], released))
    number = same[0]
    record, before = latest[number]
    if wording(before) != wording(released):
        if number != newest:
            # Only the latest release takes new wording: an older one's open cases would read it
            # at once, and a behaviour reverted with the newer release's titles is how one gets
            # here (brief, D51).
            raise PackageRefused(
                f"same behaviour as {released.name} {number}, other wording: rewording an older "
                "release reaches its open cases; bring back its wording"
            )
        return Reworded(number, record.wording + 1, changed(before, released))
    return Unchanged(number) if number == newest else SameAs(number)


def stored(record: Record, name: str) -> Package:
    """The package `record` stored, read again and checked: of this package, made by a method
    this code knows, and giving the digest the record says. Otherwise `RecordRefused`."""
    where = f"{record.name} {record.release}" + (
        f", wording {record.wording}" if record.wording > 1 else ""
    )
    if record.name != name:
        raise RecordRefused(f"{where} is a record of {record.name}, not of {name}")
    if record.digest.method != METHOD:
        raise RecordRefused(
            f"{where} was made with hash method {record.digest.method}, which this tool doesn't "
            f"know (it computes method {METHOD}): run a tool that knows it"
        )
    try:
        kept = package(record.written.case, list(record.written.plans.values()))
    except (PackageRefused, PackageUnreadable) as refused:
        raise RecordRefused(f"{where}'s package can't be read again: {refused}") from None
    if digest(kept) != record.digest:
        raise RecordRefused(
            f"{where}'s digest isn't what its own package gives under method {METHOD}: the "
            f"record was changed, or the method was; it can't be compared"
        )
    return kept


def record(
    released: Package, outcome: Released | Reworded, commit: str, catalog: Catalog
) -> Record:
    """The record of a release or a wording revision, as it is kept for good."""
    revision = outcome.wording if isinstance(outcome, Reworded) else 1
    number, said = outcome.release, outcome.changed
    return Record(
        released.name,
        number,
        revision,
        digest(released),
        commit,
        contracts_of(released, catalog),
        released.written,
        said,
    )


def contracts_of(released: Package, catalog: Catalog) -> dict[str, Hash]:
    """Every contract the package calls, its plans' included, each with its hash: what
    activation checks the environment's workers serve (brief, D5)."""
    called = {step.called for step in released.case.steps.values() if isinstance(step, CallStep)}
    for plan in released.plans.values():
        called |= {s.activity for s in plan.states.values() if isinstance(s, ActivityState)}
    return {
        reference: Hash(METHOD, contract_hash(catalog.lookup(reference)))
        for reference in sorted(called)
    }
