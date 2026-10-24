"""The semantic diff: two packages compared by what they do, never by their text (layer 13a).

`diff(before, after, catalog)` lists every behaviour change, each at its path as the JSON writes
it, with a verdict: looser, stricter, or not proven. A verdict comes only from a closed list of
comparisons (`COMPARISONS`), each a proof for every case; anything else is said and not proven,
which counts as what may loosen (brief, D55). It is given no case file, so it can't quote a value
from one. Pure: no clock, no I/O, the same list in the same order every time.
See docs/layers/13-diff.md (13a) and docs/guides/releases.md, "What changed: the diff".
"""

import json
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Literal, cast

from pydantic import BaseModel

from ventoux.case.definition import CallStep, CaseDefinition, TaskStep
from ventoux.case.releases import (
    WRITTEN_BESIDE,
    WRITTEN_ON_FIELDS,
    Package,
    behaviour_of,
    canonical,
    joined,
    key_of,
    wording,
)
from ventoux.case.visibility import roles_named, seen_by
from ventoux.core.catalog import Catalog, NotInCatalog
from ventoux.core.contract import Contract
from ventoux.core.expressions import Expression, render
from ventoux.core.expressions.model import Node
from ventoux.core.plan import Plan
from ventoux.core.policy import Policy, UnknownPolicy, compared

type Verdict = Literal["looser", "stricter", "not proven"]

# The comparisons that may give a verdict, a closed list: each has a witness, a run where one
# version refuses what the other lets through (brief, D55). 13b adds the guards on people and runs.
COMPARISONS = (
    "input policy",  # what an input of a step's contract accepts (brief, D21)
    "untrusted mark",  # an `untrusted:` mark on a field (brief, D12)
    "sensitive",  # a field's value wrapped, and never given to a workflow step (brief, D31)
    "readers",  # the roles that see a field, or every outcome and output (brief, D30)
)


class DiffRefused(Exception):
    """A diff that can't be made whole: a comparison it can't make. Never a change left out."""


@dataclass(frozen=True)
class Change:
    """One behaviour change: where, its verdict, and what it was and is."""

    path: str  # where, as the JSON writes it: `steps.pay.activity`
    verdict: Verdict
    said: str  # what it was and is, in the definition's terms: `48h -> 72h`
    comparison: str | None = None  # which of COMPARISONS proved the verdict; None: not proven
    because: str = ""  # for a change derived from another: what caused it
    entry: Literal["added", "removed", ""] = ""  # an entry only one version has, said whole

    def __str__(self) -> str:
        why = f" (because {self.because})" if self.because else ""
        return f"{self.verdict:<10} {self.path}: {self.said}{why}"


@dataclass(frozen=True)
class Reworded:
    """A piece of wording changed: never behaviour (brief, D5)."""

    path: str
    before: str | None  # None: it wasn't written
    after: str | None

    def __str__(self) -> str:
        return f"{'wording':<10} {self.path}: {quoted(self.before)} -> {quoted(self.after)}"


@dataclass(frozen=True)
class Diff:
    """Every behaviour change between two versions of a package, and its wording apart."""

    name: str  # the package: `refund`
    changes: tuple[Change, ...]
    wording: tuple[Reworded, ...]

    def __str__(self) -> str:
        lines = [self.summary(), *map(str, self.changes), *map(str, self.wording)]
        return "\n".join(lines) + "\n"

    def summary(self) -> str:
        """One line: how many changes, what may loosen first, then what is stricter."""
        if not self.changes and not self.wording:
            return f"{self.name}: nothing changed"
        verdicts = [change.verdict for change in self.changes]
        looser, unproven = verdicts.count("looser"), verdicts.count("not proven")
        # Every doubt reads as looser: what isn't proven is counted with it (brief, D55).
        behaviour = (
            f"{counted(len(verdicts), 'behaviour change')}: {looser + unproven} may loosen "
            f"({looser} looser, {unproven} not proven), {verdicts.count('stricter')} stricter"
            if verdicts
            else "no behaviour change"
        )
        reworded = (
            counted(len(self.wording), "wording change") if self.wording else "no wording change"
        )
        return f"{self.name}: {behaviour}; {reworded}"


def counted(number: int, noun: str) -> str:
    """`1 behaviour change`, `2 behaviour changes`."""
    return f"{number} {noun}{'' if number == 1 else 's'}"


def quoted(text: str | None) -> str:
    """A piece of wording as the diff shows it: in quotes, or `none`."""
    return "none" if text is None else json.dumps(text, ensure_ascii=False)


def diff(before: Package, after: Package, catalog: Catalog) -> Diff:
    """Every behaviour change from `before` to `after`, in the package's order, with wording
    apart. Refused (`DiffRefused`) if a comparison can't be made: a contract the catalog doesn't
    hold, a policy of a kind it doesn't know (brief, D55)."""
    changes = list(case_changes(before.case, after.case, catalog))
    for reference in merged(list(before.plans), list(after.plans)):
        path = f"plans.{reference}"
        changes += judged(
            leaves(before.plans.get(reference, MISSING), after.plans.get(reference, MISSING), path),
            catalog,
        )
    return Diff(after.name, tuple(changes), reworded(before, after, changes))


# --- Walking the two versions --------------------------------------------------------------------

MISSING = object()  # an entry one version doesn't have


@dataclass(frozen=True)
class Leaf:
    """Where the two versions behave differently, as deep as a reader needs: an expression whole,
    an entry added or removed whole."""

    path: str
    before: object  # MISSING: added
    after: object  # MISSING: removed


def leaves(before: object, after: object, path: str) -> list[Leaf]:
    """Every place `before` and `after` behave differently, named as 12a's release notes name
    them (`changed`, brief, D50), in the new version's order, a removed entry where it was."""
    if before is MISSING or after is MISSING:
        return [Leaf(path, before, after)]  # an entry only one version has
    if canonical(before) == canonical(after):
        return []
    retyped = isinstance(before, BaseModel) and type(before) is not type(after)
    if retyped and isinstance(before, BaseModel) and "type" in type(before).model_fields:
        where = joined(path, "type")  # a field's type, written `"type": "number"`
        return [Leaf(where, cast(Any, before).type, getattr(after, "type", MISSING))]
    if (
        isinstance(before, BaseModel)
        and type(before) is type(after)
        and not isinstance(before, Node)
    ):
        assert isinstance(after, BaseModel)
        found: list[Leaf] = []
        for name in type(before).model_fields:
            if behaviour_of(before, name) == behaviour_of(after, name):
                continue
            old, new = getattr(before, name), getattr(after, name)
            if name in WRITTEN_ON_FIELDS and isinstance(before, Plan):
                found += sources_leaves(old, new, path)
                continue
            # A field's declared type is written beside its display, not under a key.
            where = path if name in WRITTEN_BESIDE else joined(path, key_of(before, name))
            found += leaves(old, new, where) or [Leaf(where, old, new)]
        return found
    if isinstance(before, Mapping) and isinstance(after, Mapping):
        found = []
        for key in merged(list(before), list(after)):
            old, new = before.get(key, MISSING), after.get(key, MISSING)
            where = joined(path, str(key))
            if old is MISSING or new is MISSING:
                found.append(Leaf(where, old, new))
            else:
                found += leaves(old, new, where)
        return found or [Leaf(path, before, after)]  # the same entries, in another order
    return [Leaf(path, before, after)]


def sources_leaves(before: Mapping[str, str], after: Mapping[str, str], path: str) -> list[Leaf]:
    """Each plan field whose mark changed, named where the JSON writes it: on the field."""
    return [
        Leaf(joined(path, f"fields.{name}.source"), before.get(name), after.get(name))
        for name in merged(list(before), list(after))
        if before.get(name) != after.get(name)
    ]


def merged(before: Sequence[str], after: Sequence[str]) -> list[str]:
    """The keys of both, in `after`'s order, each key only `before` has right after the key that
    came before it there (first, if none did)."""
    order = list(after)
    for index, key in enumerate(before):
        if key in order:
            continue
        kept = [earlier for earlier in before[:index] if earlier in order]
        order.insert(order.index(kept[-1]) + 1 if kept else 0, key)
    return order


# --- The case ------------------------------------------------------------------------------------


def case_changes(
    before: CaseDefinition, after: CaseDefinition, catalog: Catalog
) -> Iterator[Change]:
    """The case's changes, its sections in the order the format writes them."""
    for name in type(before).model_fields:
        old, new = getattr(before, name), getattr(after, name)
        if name == "fields":
            for field in merged(list(old), list(new)):
                path = f"fields.{field}"
                yield from judged(
                    leaves(old.get(field, MISSING), new.get(field, MISSING), path), catalog
                )
                if field in old and field in new:
                    yield from readers(before, after, field)
        else:
            if name == "steps":
                yield from outcome_readers(before, after)
            if behaviour_of(before, name) != behaviour_of(after, name):
                where = key_of(before, name)
                yield from judged(leaves(old, new, where) or [Leaf(where, old, new)], catalog)


# --- Judging a leaf ------------------------------------------------------------------------------

# Where a leaf is judged, by the parts of its path; `*` stands for any one name.
MARKS = (
    ("fields", "*", "source"),
    ("events", "*", "payload", "*", "source"),
    ("plans", "*", "fields", "*", "source"),
)
SENSITIVE = ("fields", "*", "sensitive")
READERS = ("fields", "*", "visible_to")
CONTRACTS = (
    ("steps", "*", "activity"),
    ("steps", "*", "workflow"),
    ("plans", "*", "states", "*", "activity"),
)


def at(path: str, pattern: Sequence[str]) -> bool:
    """Whether `path` is written as `pattern`: `fields.amount.source` is `fields.*.source`."""
    parts = path.split(".")
    return len(parts) == len(pattern) and all(p in ("*", part) for part, p in zip(parts, pattern))


def judged(found: list[Leaf], catalog: Catalog) -> Iterator[Change]:
    """Each leaf as changes: judged by its comparison where one applies, else said, not proven."""
    for leaf in found:
        if leaf.before is MISSING or leaf.after is MISSING:
            yield entry_change(leaf, found)
        elif any(at(leaf.path, pattern) for pattern in CONTRACTS):
            yield from contract_changes(leaf, catalog)
        elif any(at(leaf.path, pattern) for pattern in MARKS):
            yield mark_change(leaf)
        elif at(leaf.path, SENSITIVE):
            yield sensitive_change(leaf)
        elif at(leaf.path, READERS):
            continue  # said by `readers`, which compares who sees it, under its field
        else:
            yield Change(leaf.path, "not proven", f"{shown(leaf.before)} -> {shown(leaf.after)}")


def entry_change(leaf: Leaf, found: list[Leaf]) -> Change:
    """An entry added or removed: never judged. An added one that behaves exactly as a removed
    one of the same map says so: the diff can't know a rename was meant (brief, D53)."""
    if leaf.after is MISSING:
        return Change(leaf.path, "not proven", "removed", entry="removed")
    parent, _, name = leaf.path.rpartition(".")
    for other in found:
        other_parent, _, other_name = other.path.rpartition(".")
        if (
            other.after is MISSING
            and other_parent == parent
            and canonical(other.before) == canonical(leaf.after)
        ):
            return Change(
                leaf.path,
                "not proven",
                f"added: behaves as the removed {other_name} did: open cases need a migration "
                f"mapping {other_name} to {name} (brief, D53)",
                entry="added",
            )
    return Change(leaf.path, "not proven", "added", entry="added")


def shown(value: object) -> str:
    """A value written in the definition, as the diff shows it: an expression as the renderer
    writes it (brief, D20), a list joined, a map by its keys, nothing quoted from a case."""
    if value is MISSING or value is None:
        return "none"
    if isinstance(value, Node):
        return render(cast(Expression, value))  # Node is every operator's base
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, str | int | Decimal):
        return str(value)
    if isinstance(value, tuple | list):
        return ", ".join(shown(item) for item in value) or "none"
    if isinstance(value, Mapping):
        return ", ".join(str(key) for key in value) or "none"
    if isinstance(value, BaseModel):
        written = value.model_dump(mode="json", by_alias=True, exclude_defaults=True)
        return json.dumps(written, ensure_ascii=False)
    # Fail closed: a kind of value this code doesn't know is never left unsaid.
    raise DiffRefused(f"the diff can't show a {type(value).__name__}")


# --- Input policies ------------------------------------------------------------------------------

VERDICTS: dict[str, Verdict] = {"wider": "looser", "narrower": "stricter", "neither": "not proven"}


def contract_changes(leaf: Leaf, catalog: Catalog) -> Iterator[Change]:
    """A step, or a plan's activity state, calling another contract: each input whose policies
    changed, judged; the rest of the contract said, not proven (brief, D55)."""
    old, new = contract(catalog, str(leaf.before)), contract(catalog, str(leaf.after))
    called = f"{old.reference} -> {new.reference}"
    said = False
    inputs_before, inputs_after = old.input.model_fields, new.input.model_fields
    for name in merged(list(inputs_before), list(inputs_after)):
        if name not in inputs_before or name not in inputs_after:
            which = old.reference if name in inputs_before else new.reference
            yield Change(leaf.path, "not proven", f"{called}: input {name} only in {which}")
            said = True
            continue
        try:
            how = compared(old.policies(name), new.policies(name))
        except UnknownPolicy as unknown:
            raise DiffRefused(f"{leaf.path}: {unknown}") from None
        if how != "same":
            yield Change(
                leaf.path,
                VERDICTS[how],
                f"{called}: input {name}: was {described(old.policies(name))}; "
                f"now {described(new.policies(name))}",
                "input policy",
            )
            said = True
    other = differing(old, new)
    if other or not said:
        also = f": its contract also differs: {', '.join(other)}" if other else ""
        yield Change(leaf.path, "not proven", f"{called}{also}")


def contract(catalog: Catalog, reference: str) -> Contract:
    """The contract `reference` names; one the catalog doesn't hold refuses the diff."""
    try:
        return catalog.lookup(reference)
    except NotInCatalog as missing:
        raise DiffRefused(f"{missing} The diff compares contracts from the catalog.") from None


def described(policies: Sequence[Policy]) -> str:
    """An input's policies as one reads them (brief, D21)."""
    if not policies:
        return "any value (no input policy)"
    return " and ".join(policy.describe() for policy in policies)


def differing(old: Contract, new: Contract) -> list[str]:
    """What else two contracts promise differently, by name: everything their hash covers but
    their name, their version and their inputs' policies, compared above."""
    first, second = promised(old), promised(new)
    return sorted(key for key in first.keys() | second.keys() if first.get(key) != second.get(key))


def promised(contract: Contract) -> dict[str, object]:
    """A contract's promise, as its hash reads it, without its name, version and policies."""
    promise = contract.model_dump(
        mode="json", exclude={"display", "input", "output", "name", "version"}
    )
    promise["input"] = without_policies(contract.input.model_json_schema())
    promise["output"] = contract.output.model_json_schema()
    return promise


def without_policies(schema: object) -> object:
    """A JSON Schema with every input policy taken out (`x-input-policies`, brief, D21)."""
    if isinstance(schema, dict):
        return {
            key: without_policies(value)
            for key, value in schema.items()
            if key != "x-input-policies"
        }
    if isinstance(schema, list):
        return [without_policies(item) for item in schema]
    return schema


# --- Marks and sensitive values ------------------------------------------------------------------


def mark_change(leaf: Leaf) -> Change:
    """An `untrusted:` mark: removed, values written there no longer carry the distrust an input
    policy refuses, looser; added, stricter; relabelled, not proven (brief, D55)."""
    said = f"{shown(leaf.before)} -> {shown(leaf.after)}"
    if leaf.before is None:
        return Change(leaf.path, "stricter", said, "untrusted mark")
    if leaf.after is None:
        return Change(leaf.path, "looser", said, "untrusted mark")
    return Change(leaf.path, "not proven", said)


def sensitive_change(leaf: Leaf) -> Change:
    """`sensitive` removed: the value is no longer wrapped, and may go to a workflow step, looser;
    added, stricter (brief, D31)."""
    verdict: Verdict = "stricter" if leaf.after else "looser"
    return Change(leaf.path, verdict, f"{shown(leaf.before)} -> {shown(leaf.after)}", "sensitive")


# --- Who sees what -------------------------------------------------------------------------------


def readers(before: CaseDefinition, after: CaseDefinition, field: str) -> Iterator[Change]:
    """Who sees `field`, as the case computes it: its `visible_to`, or every role the case names
    (brief, D30). Compared, never the key as written: a role named anywhere new sees every field
    without one, and the JSON says nothing about the field (brief, D55)."""
    path = f"fields.{field}.visible_to"
    old, new = seen_by(before, field), seen_by(after, field)
    declared = before.fields[field].visible_to != after.fields[field].visible_to
    if old == new:
        if declared:  # written differently, seen by the same roles today
            written = before.fields[field].visible_to, after.fields[field].visible_to
            yield Change(path, "not proven", f"{shown(written[0])} -> {shown(written[1])}")
        return
    because = "" if declared else caused(before, after, old, new)
    yield Change(path, roles_verdict(old, new), seen(old, new), "readers", because)


def outcome_readers(before: CaseDefinition, after: CaseDefinition) -> Iterator[Change]:
    """Every outcome and output is seen by every role the case names (brief, D30): said once."""
    old, new = roles_named(before), roles_named(after)
    if old != new:
        said = f"every outcome and output: {seen(old, new)}"
        yield Change(
            "steps", roles_verdict(old, new), said, "readers", caused(before, after, old, new)
        )


def roles_verdict(old: Sequence[str], new: Sequence[str]) -> Verdict:
    """More roles and none fewer, looser; fewer and none more, stricter; both, not proven."""
    added, removed = set(new) - set(old), set(old) - set(new)
    if added and not removed:
        return "looser"
    return "stricter" if removed and not added else "not proven"


def seen(old: Sequence[str], new: Sequence[str]) -> str:
    """`seen by support -> fraud, support`."""
    return f"seen by {shown(list(old))} -> {shown(list(new))}"


def caused(
    before: CaseDefinition, after: CaseDefinition, old: Sequence[str], new: Sequence[str]
) -> str:
    """What made a role named, or no longer: the first place each is named."""
    named_before, named_after = naming(before), naming(after)
    reasons = [f"{named_after[role]} names {role}" for role in new if role not in old]
    reasons += [f"{named_before[role]} no longer names {role}" for role in old if role not in new]
    return "; ".join(reasons)


def naming(case: CaseDefinition) -> dict[str, str]:
    """The first path naming each role, in the order `roles_named` reads the case."""
    found: dict[str, str] = {}

    def note(path: str, roles: Sequence[str] | None) -> None:
        for role in roles or ():
            found.setdefault(role, path)

    for name, step in case.steps.items():
        note(f"steps.{name}.proposed_by", step.proposed_by)
        if isinstance(step, TaskStep):
            note(f"steps.{name}.roles", step.roles)
        elif isinstance(step, CallStep) and step.approval is not None:
            note(f"steps.{name}.approval.roles", step.approval.roles)
    for name, reason in case.close_reasons.items():
        note(f"close_reasons.{name}.roles", reason.roles)
    for name, event in case.events.items():
        note(f"events.{name}.sent_by.roles", event.sent_by.roles)
    for name, field in case.fields.items():
        note(f"fields.{name}.visible_to", field.visible_to)
    return found


# --- Wording -------------------------------------------------------------------------------------


def reworded(before: Package, after: Package, changes: Sequence[Change]) -> tuple[Reworded, ...]:
    """Every piece of wording that changed, by path, in the new version's order (brief, D5). The
    wording of an entry added or removed is part of that change, not listed apart."""
    old, new = wording(before), wording(after)
    whole = [change.path for change in changes if change.entry]
    return tuple(
        Reworded(path, text(old.get(path)), text(new.get(path)))
        for path in merged(list(old), list(new))
        if text(old.get(path)) != text(new.get(path))
        and not any(path.startswith(f"{entry}.") for entry in whole)
    )


def text(value: object) -> str | None:
    """A piece of wording: a text, or None where it isn't written. An empty description is none,
    as written out or left at its default."""
    return None if value is None or value == "" else str(value)
