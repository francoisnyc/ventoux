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
from dataclasses import dataclass, replace
from typing import Any, cast

from pydantic import BaseModel

from ventoux.case.changes import (
    MISSING,
    Change,
    DiffRefused,
    Leaf,
    Verdict,
    merged,
    shown,
)
from ventoux.case.definition import CallStep, CaseDefinition, TaskStep
from ventoux.case.guards import (
    Versions,
    approval_change,
    approval_condition_change,
    close_reason_change,
    count_change,
    forgetting_change,
    plan_approvals,
    plan_approvers_change,
    roles_change,
    step_condition_change,
    step_guards,
    switch_change,
)
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
from ventoux.core.catalog import Catalog
from ventoux.core.contract import Contract
from ventoux.core.expressions.model import Node
from ventoux.core.output_sources import output_sources
from ventoux.core.plan import Plan
from ventoux.core.policy import Policy, UnknownPolicy, compared
from ventoux.core.provenance import is_trusted


@dataclass(frozen=True)
class Reworded:
    """A piece of wording changed: never behaviour (brief, D5)."""

    path: str  # where: `steps.settle.display.title`
    before: str | None  # the old text; None: it wasn't written
    after: str | None  # the new text; None: it isn't written any more

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
    versions = Versions(before.case, after.case, catalog, before.plans, after.plans)
    changes = list(case_changes(versions))
    for reference in merged(list(before.plans), list(after.plans)):
        path = f"plans.{reference}"
        changes += judged(
            leaves(before.plans.get(reference, MISSING), after.plans.get(reference, MISSING), path),
            versions,
        )
        if reference in before.plans and reference in after.plans:
            changes += plan_approvals(reference, versions)
    return Diff(after.name, tuple(changes), reworded(before, after, changes))


# --- Walking the two versions --------------------------------------------------------------------


def leaves(before: object, after: object, path: str) -> list[Leaf]:
    """Every place `before` and `after` behave differently, named as 12a's release notes name
    them (`changed`) (brief, D50), in the new version's order, a removed entry where it was."""
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


# --- The case ------------------------------------------------------------------------------------


def case_changes(versions: Versions) -> Iterator[Change]:
    """The case's changes, its sections in the order the format writes them."""
    before, after = versions.before, versions.after
    for name in type(before).model_fields:
        old, new = getattr(before, name), getattr(after, name)
        if name == "fields":
            for field in merged(list(old), list(new)):
                path = f"fields.{field}"
                yield from judged(
                    leaves(old.get(field, MISSING), new.get(field, MISSING), path), versions
                )
                if field in old and field in new:
                    yield from readers(versions, field)
        elif name == "steps":
            yield from outcome_readers(versions)
            yield from step_changes(versions)
        elif behaviour_of(before, name) != behaviour_of(after, name):
            where = key_of(before, name)
            yield from judged(leaves(old, new, where) or [Leaf(where, old, new)], versions)


def step_changes(versions: Versions) -> Iterator[Change]:
    """Each step's changes, then what follows from them under it: who may approve it (and, from
    later slices, what it requires and reads)."""
    old, new = versions.before.steps, versions.after.steps
    found = leaves(old, new, "steps")
    yield from judged([leaf for leaf in found if leaf.path == "steps"], versions)  # reordered
    for step in merged(list(old), list(new)):
        path = f"steps.{step}"
        own = [leaf for leaf in found if leaf.path == path or leaf.path.startswith(f"{path}.")]
        yield from judged(own, versions, peers=found)
        if step in old and step in new:
            yield from step_guards(step, versions)


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
# 13b's guards on people and runs (case/guards.py).
APPROVAL = ("steps", "*", "approval")
APPROVAL_COUNT = ("steps", "*", "approval", "count")
APPROVAL_WHEN = ("steps", "*", "approval", "when")
APPROVERS = ("steps", "*", "approval", "roles")
REQUIRES = ("steps", "*", "requires")
CLOSE_REASON = ("close_reasons", "*")
FORGETTING = ("forgetting",)


def under_max_age(path: str) -> bool:
    """Whether `path` is in a step's `max_age`, whose keys name facts with dots in them."""
    parts = path.split(".")
    return len(parts) >= 3 and parts[0] == "steps" and parts[2] == "max_age"


STEP_WHEN = ("steps", "*", "when")
SWITCHES = ("automatic", "repeatable")


def switched(path: str) -> str | None:
    """`automatic` or `repeatable`, if `path` is a step's; None otherwise."""
    return next((name for name in SWITCHES if at(path, ("steps", "*", name))), None)


# Each list of roles, and the comparison that judges it (13b, choice 22).
ROLES = {
    ("steps", "*", "roles"): "answerers",
    ("steps", "*", "proposed_by"): "proposers",
    ("events", "*", "sent_by", "roles"): "senders",
    ("close_reasons", "*", "roles"): "closers",
    ("plans", "*", "states", "*", "wait", "roles"): "plan answerers",
}
PLAN_APPROVERS = ("plans", "*", "states", "*", "approval", "roles")


def roles_compared(path: str) -> str | None:
    """The comparison judging the list of roles at `path`; None if it isn't one."""
    return next((name for pattern, name in ROLES.items() if at(path, pattern)), None)


def at(path: str, pattern: Sequence[str]) -> bool:
    """Whether `path` is written as `pattern`: `fields.amount.source` is `fields.*.source`."""
    parts = path.split(".")
    return len(parts) == len(pattern) and all(p in ("*", part) for part, p in zip(parts, pattern))


def judged(
    found: list[Leaf], versions: Versions, peers: list[Leaf] | None = None
) -> Iterator[Change]:
    """Each leaf as changes: judged by its comparison where one applies, else said, not proven.
    An entry added is matched against the entries removed among `peers` (`found` by default)."""
    for leaf in found:
        others = found if peers is None else peers
        if under_max_age(leaf.path):
            continue  # said by `step_guards`, which compares each fact's age as a duration
        elif at(leaf.path, CLOSE_REASON) and not renamed(leaf, others):
            yield close_reason_change(leaf)  # a way to close added or removed
        elif leaf.before is MISSING or leaf.after is MISSING:
            yield entry_change(leaf, others)
        elif at(leaf.path, FORGETTING):
            yield forgetting_change(leaf)
        elif any(at(leaf.path, pattern) for pattern in CONTRACTS):
            yield from contract_changes(leaf, versions)
        elif at(leaf.path, APPROVAL):
            yield approval_change(leaf, versions)
        elif at(leaf.path, APPROVAL_COUNT):
            yield count_change(leaf)
        elif at(leaf.path, APPROVAL_WHEN):
            yield approval_condition_change(leaf)
        elif at(leaf.path, APPROVERS) or at(leaf.path, REQUIRES):
            continue  # said by `step_guards`, which compares them as the case reads them
        elif at(leaf.path, STEP_WHEN):
            yield step_condition_change(leaf)
        elif (switch := switched(leaf.path)) is not None:
            yield switch_change(leaf, switch)
        elif (comparison := roles_compared(leaf.path)) is not None:
            yield roles_change(leaf, versions, comparison)
        elif at(leaf.path, PLAN_APPROVERS):
            yield plan_approvers_change(leaf, versions)
        elif any(at(leaf.path, pattern) for pattern in MARKS):
            yield mark_change(leaf)
        elif at(leaf.path, SENSITIVE):
            yield sensitive_change(leaf)
        elif at(leaf.path, READERS):
            continue  # said by `readers`, which compares who sees it, under its field
        else:
            yield Change(leaf.path, "not proven", f"{shown(leaf.before)} -> {shown(leaf.after)}")


def renamed(leaf: Leaf, found: list[Leaf]) -> bool:
    """Whether `leaf` is an entry added or removed whose counterpart, removed or added in the same
    map, behaves exactly as it does: a rename, never judged (brief, D53)."""
    if leaf.before is not MISSING and leaf.after is not MISSING:
        return False
    parent = leaf.path.rpartition(".")[0]
    mine = leaf.after if leaf.before is MISSING else leaf.before
    return any(
        other.path.rpartition(".")[0] == parent
        and (other.before is MISSING) != (leaf.before is MISSING)
        and canonical(other.after if other.before is MISSING else other.before) == canonical(mine)
        for other in found
    )


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


# --- Input policies ------------------------------------------------------------------------------

# How `compared`'s answer reads as a verdict: an input that accepts more is looser.
VERDICTS: dict[str, Verdict] = {"wider": "looser", "narrower": "stricter", "neither": "not proven"}


def contract_changes(leaf: Leaf, versions: Versions) -> Iterator[Change]:
    """A step, or a plan's activity state, calling another contract: each input whose policies
    changed, judged; the rest of the contract said, not proven (brief, D55)."""
    old, new = versions.lookup(str(leaf.before)), versions.lookup(str(leaf.after))
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
                None if how == "neither" else "input policy",
            )
            said = True
    for change in output_changes(leaf.path, called, old, new):
        yield change
        said = True
    other = differing(old, new)
    if other or not said:
        also = f": its contract also differs: {', '.join(other)}" if other else ""
        yield Change(leaf.path, "not proven", f"{called}{also}")


def described(policies: Sequence[Policy]) -> str:
    """An input's policies as one reads them (brief, D21)."""
    if not policies:
        return "any value (no input policy)"
    return " and ".join(policy.describe() for policy in policies)


def differing(old: Contract, new: Contract) -> list[str]:
    """What else two contracts promise differently, by name: everything their hash covers but
    their name, their version, their inputs' policies and their outputs' sources, compared
    above."""
    first, second = promised(old), promised(new)
    return sorted(key for key in first.keys() | second.keys() if first.get(key) != second.get(key))


def promised(contract: Contract) -> dict[str, object]:
    """A contract's promise, as its hash reads it, without its name, version, policies and
    output sources."""
    promise = contract.model_dump(
        mode="json", exclude={"display", "input", "output", "name", "version"}
    )
    promise["input"] = without_policies(contract.input.model_json_schema())
    promise["output"] = without(contract.output.model_json_schema(), "x-source")
    return promise


def without_policies(schema: object) -> object:
    """A JSON Schema with every input policy taken out (`x-input-policies`) (brief, D21)."""
    return without(schema, "x-input-policies")


def without(schema: object, taken: str) -> object:
    """A JSON Schema with every key `taken` taken out, at any depth."""
    if isinstance(schema, dict):
        return {key: without(value, taken) for key, value in schema.items() if key != taken}
    if isinstance(schema, list):
        return [without(item, taken) for item in schema]
    return schema


def output_changes(path: str, called: str, old: Contract, new: Contract) -> Iterator[Change]:
    """Each output whose source changed, from what the old contract declares to the new one's
    (an undeclared one is untrusted:undeclared) (brief, D29): from untrusted to a system, a case
    may now decide on it, looser; the reverse, stricter; one system or label for another, not
    proven. An output only one of them gives is said, not proven."""
    before, after = output_sources(old.output), output_sources(new.output)
    for name in merged(list(before), list(after)):
        if name not in before or name not in after:
            which = old.reference if name in before else new.reference
            yield Change(path, "not proven", f"{called}: output {name} only in {which}")
            continue
        if before[name] == after[name]:
            continue
        said = f"{called}: output {name}: was {before[name]}; now {after[name]}"
        trusted_before, trusted_after = is_trusted(before[name]), is_trusted(after[name])
        if path.startswith("plans."):
            # A plan keeps no activity's outputs: its fields come from the case and from answers,
            # and a plan step gives none (brief, D28). A widening there guards nothing: said, never
            # judged (13b, choice 31).
            yield Change(path, "not proven", f"{said} (a plan keeps no activity's outputs)")
        elif trusted_after and not trusted_before:
            yield Change(path, "looser", said, "output source")
        elif trusted_before and not trusted_after:
            yield Change(path, "stricter", said, "output source")
        else:
            yield Change(path, "not proven", said)


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


def readers(versions: Versions, field: str) -> Iterator[Change]:
    """Who sees `field`, as the case computes it: its `visible_to`, or every role the case names
    (brief, D30), and of those only the roles the catalog registers, since another gives sight of
    nothing (brief, D22). Compared, never the key as written: a role named anywhere new sees every
    field without one, and the JSON says nothing about the field (brief, D55)."""
    before, after = versions.before, versions.after
    path = f"fields.{field}.visible_to"
    old = versions.registered(seen_by(before, field))
    new = versions.registered(seen_by(after, field))
    declared = before.fields[field].visible_to != after.fields[field].visible_to
    if old == new:
        if declared:  # written differently, seen by the same roles today
            written = before.fields[field].visible_to, after.fields[field].visible_to
            yield Change(path, "not proven", f"{shown(written[0])} -> {shown(written[1])}")
        return
    because = "" if declared else caused(before, after, old, new)
    yield readers_change(path, old, new, because)


def outcome_readers(versions: Versions) -> Iterator[Change]:
    """Every outcome and output is seen by every role the case names (brief, D30): said once."""
    old = versions.registered(roles_named(versions.before))
    new = versions.registered(roles_named(versions.after))
    if old != new:
        because = caused(versions.before, versions.after, old, new)
        change = readers_change("steps", old, new, because)
        yield replace(change, said=f"every outcome and output: {change.said}")


def readers_change(path: str, old: Sequence[str], new: Sequence[str], because: str) -> Change:
    """Seen by more roles and none fewer, looser; fewer and none more, stricter; both, not
    proven, and no comparison named."""
    said = f"seen by {shown(list(old))} -> {shown(list(new))}"
    added, removed = set(new) - set(old), set(old) - set(new)
    if added and not removed:
        return Change(path, "looser", said, "readers", because)
    if removed and not added:
        return Change(path, "stricter", said, "readers", because)
    return Change(path, "not proven", said, because=because)


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
