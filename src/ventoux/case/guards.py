"""Guards on people and runs: who may act, and when a step may run (layer 13b).

Each judges one kind of change between two versions of a package, as `case/diff.py`'s walk finds
it, and gives a verdict only where it is a proof for every case (brief, D55). A condition's
presence is judged, never the condition: an approval given a `when` is asked on no more runs, and
on fewer wherever it is false (13b, choice 19).
See docs/layers/13-diff.md (13b).
"""

from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from typing import Literal

from ventoux.case.changes import Change, DiffRefused, Leaf, Verdict, shown
from ventoux.case.definition import Approval, CallStep, CaseDefinition
from ventoux.case.sequence import requirements
from ventoux.case.writers import could_come_from
from ventoux.core.catalog import Catalog, NotInCatalog
from ventoux.core.contract import Contract
from ventoux.core.provenance import fields_read
from ventoux.core.roles import may_approve


@dataclass(frozen=True)
class Versions:
    """What a guard reads beside its leaf: both versions of the case, and the catalog."""

    before: CaseDefinition
    after: CaseDefinition
    catalog: Catalog

    def called(self, case: CaseDefinition, step: str) -> Contract | None:
        """The contract `step` calls in `case`; None if it calls none. One the catalog doesn't
        hold refuses the diff: what it would let through can't be told."""
        found = case.steps.get(step)
        if not isinstance(found, CallStep):
            return None
        try:
            return self.catalog.lookup(found.called)
        except NotInCatalog as missing:
            raise DiffRefused(f"{missing} The diff compares contracts from the catalog.") from None

    def registered(self, roles: Sequence[str]) -> tuple[str, ...]:
        """Of `roles`, those the catalog registers: another gives nobody anything (brief, D22)."""
        return tuple(role for role in roles if role in self.catalog.roles)


# --- An approval, its count and its condition ----------------------------------------------------


def approval_change(leaf: Leaf, versions: Versions) -> Change:
    """An approval added: stricter, every run it covers waits for a person; removed: looser. On a
    high-risk step neither: with no approval it never runs, as the runtime refuses it
    (brief, D11), so the version without one lets nothing through."""
    step = leaf.path.split(".")[1]
    old, new = leaf.before, leaf.after
    said = f"{approved_by(old)} -> {approved_by(new)}"
    # The version without an approval: whether its step can run at all.
    bare = versions.after if new is None else versions.before
    contract = versions.called(bare, step)
    if contract is not None and contract.risk == "high":
        never = "never runs" if new is None else "never ran"
        why = f"{contract.reference} is high risk: without an approval, {step} {never}"
        return Change(leaf.path, "not proven", f"{said} ({why})", entry=entered(new))
    verdict: Verdict = "looser" if new is None else "stricter"
    return Change(leaf.path, verdict, said, "approval", entry=entered(new))


def entered(new: object) -> Literal["added", "removed"]:
    """An approval removed, or added, is said whole: its wording with it."""
    return "removed" if new is None else "added"


def approved_by(approval: object) -> str:
    """`approved by support-lead`, or `approved by nobody`."""
    if not isinstance(approval, Approval):
        return "approved by nobody"
    return f"approved by {' or '.join(approval.roles)}"


def count_change(leaf: Leaf) -> Change:
    """Fewer people to approve: looser; more: stricter (brief, D47)."""
    old, new = leaf.before, leaf.after
    assert isinstance(old, int) and isinstance(new, int)
    step = leaf.path.split(".")[1]
    said = f"{old} -> {new} ({people(new)} {step}, where {number(old)} had to)"
    verdict: Verdict = "looser" if new < old else "stricter"
    return Change(leaf.path, verdict, said, "approval count")


NUMBERS = ("one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten")


def number(count: int) -> str:
    """`two`, as a sentence says a small number; `11` past ten."""
    return NUMBERS[count - 1] if 1 <= count <= len(NUMBERS) else str(count)


def people(count: int) -> str:
    """`one person approves`, `three people approve`."""
    return "one person approves" if count == 1 else f"{number(count)} people approve"


def approval_condition_change(leaf: Leaf) -> Change:
    """An approval's `when`: added, it is asked on no more runs than before, and on fewer wherever
    it is false: looser (13b, choice 19); removed: stricter; changed: not proven, both shown."""
    old, new = leaf.before, leaf.after
    if old is None:
        said = (
            f"asked on every run -> asked only if {shown(new)} (on no more runs, and on fewer "
            "wherever that is false)"
        )
        return Change(leaf.path, "looser", said, "approval condition")
    if new is None:
        said = f"asked only if {shown(old)} -> asked on every run"
        return Change(leaf.path, "stricter", said, "approval condition")
    return Change(leaf.path, "not proven", f"{shown(old)} -> {shown(new)}")


# --- Roles ---------------------------------------------------------------------------------------


def roles_change(leaf: Leaf, versions: Versions, comparison: str) -> Change:
    """A list of roles, as the catalog registers them (13b, choice 22): widened looser, narrowed
    stricter, replaced not proven. A role the catalog doesn't register counts for nothing, said so.
    One side with no list (an event sent by a system, then by roles) is not proven."""
    said = f"{shown(leaf.before)} -> {shown(leaf.after)}"
    if not isinstance(leaf.before, tuple) or not isinstance(leaf.after, tuple):
        return Change(leaf.path, "not proven", said)
    old, new = set(versions.registered(leaf.before)), set(versions.registered(leaf.after))
    unknown = [role for role in (*leaf.before, *leaf.after) if role not in versions.catalog.roles]
    if unknown:
        names = ", ".join(dict.fromkeys(unknown))
        one = len(set(unknown)) == 1
        said += f" ({names} {'isn' if one else 'aren'}'t registered: "
        said += f"{'it gives' if one else 'they give'} nobody anything)"
    return widened(leaf.path, said, old, new, comparison)


def widened(path: str, said: str, old: set[str], new: set[str], comparison: str) -> Change:
    """More and none fewer: looser; fewer and none more: stricter; else not proven."""
    if new > old:
        return Change(path, "looser", said, comparison)
    if new < old:
        return Change(path, "stricter", said, comparison)
    return Change(path, "not proven", said)


# --- What follows under a step -------------------------------------------------------------------


def step_guards(step: str, versions: Versions) -> Iterator[Change]:
    """What follows from a step's changes, said under it: who may approve it, and who is
    excluded from approving it."""
    yield from requirements_change(step, versions)
    yield from approvers(step, versions)
    yield from exclusions(step, versions)


def requirements_change(step: str, versions: Versions) -> Iterator[Change]:
    """What `step` requires, its `requires` with `sequence` folded in (13b, choice 24): fewer
    looser, it may start with less done; more stricter; replaced not proven."""
    old = requirements(versions.before)[step]
    new = requirements(versions.after)[step]
    path = f"steps.{step}.requires"
    said = f"{shown(old) if old else 'nothing'} -> {shown(new) if new else 'nothing'}"
    if set(old) != set(new):
        yield widened(path, said, set(new), set(old), "requirements")  # fewer is looser
    elif old != new:  # the same, written in another order
        yield Change(path, "not proven", said)


def exclusions(step: str, versions: Versions) -> Iterator[Change]:
    """Who is excluded from approving `step` for what it reads (13b, choice 23): whoever's answer
    can reach its inputs or its `when` (brief, D11). The rule is the engine's; which answers reach
    the step is the definition's. Fewer excluded: looser; more: stricter; both: not proven."""
    old, new = versions.before.steps[step], versions.after.steps[step]
    if not isinstance(old, CallStep) or not isinstance(new, CallStep):
        return
    if old.approval is None or new.approval is None:
        return  # an approval added or removed is said by `approval_change`
    excluded_before = excluded(versions.before, old, versions.catalog)
    excluded_after = excluded(versions.after, new, versions.catalog)
    if excluded_before == excluded_after:
        return
    path = f"steps.{step}.approval"
    gone, come = excluded_before - excluded_after, excluded_after - excluded_before
    if gone and not come:
        said = f"{whoever(gone)} {'is' if len(gone) == 1 else 'are'} no longer excluded from "
        yield Change(path, "looser", f"{said}approving {step}", "approval exclusions")
    elif come and not gone:
        said = f"{whoever(come)} {'is' if len(come) == 1 else 'are'} now excluded from "
        yield Change(path, "stricter", f"{said}approving {step}", "approval exclusions")
    else:
        said = f"excluded from approving {step}: {whoever(excluded_before)} -> "
        yield Change(path, "not proven", said + whoever(excluded_after))


def excluded(case: CaseDefinition, step: CallStep, catalog: Catalog) -> frozenset[str]:
    """The people whose answers can reach what `step` reads, as the static check names them
    (`person:answering review`), from the definition alone: through a field a task's form sets,
    a task's outcome, an event a person sends, or a rule that computes from them (brief, D42)."""
    sources = could_come_from(case, catalog, None)
    read = [*step.inputs.values(), *([step.when] if step.when is not None else [])]
    fields = {field for expression in read for field in fields_read(expression)}
    return frozenset(
        source
        for field in fields
        for source in sources.get(field, frozenset())
        if source.startswith("person:")
    )


# How the static check's sources name a person, and how a sentence says it.
DOING = {"person:answering ": "answers", "person:sending ": "sends"}


def whoever(people: frozenset[str]) -> str:
    """`whoever answers review and whoever sends noted`, from the static check's sources
    (`person:answering review`, `person:sending noted`)."""
    if not people:
        return "nobody"
    said = []
    for source in sorted(people):
        found = [
            (f"{does} {source.removeprefix(prefix)}")
            for prefix, does in DOING.items()
            if source.startswith(prefix)
        ]
        # Fail closed: a person the check names another way is said as it names them.
        said.append(f"whoever {found[0]}" if found else source)
    return " and ".join(said)


def approvers(step: str, versions: Versions) -> Iterator[Change]:
    """Who may approve `step` (13b, choice 23): the roles its approval lists that the catalog
    registers and lets approve its contract's risk (brief, D11). Compared whatever changed: the
    roles, or the contract, whose risk may let fewer approve."""
    old, new = versions.before.steps[step], versions.after.steps[step]
    if not isinstance(old, CallStep) or not isinstance(new, CallStep):
        return
    if old.approval is None or new.approval is None:
        return  # an approval added or removed is said by `approval_change`
    path = f"steps.{step}.approval.roles"
    first = versions.called(versions.before, step)
    second = versions.called(versions.after, step)
    assert first is not None and second is not None  # a call step calls a contract
    allowed_before = allowed(old.approval.roles, first, versions)
    allowed_after = allowed(new.approval.roles, second, versions)
    if allowed_before == allowed_after:
        if old.approval.roles != new.approval.roles:  # names changed, nobody who may approve
            refused = [r for r in new.approval.roles + old.approval.roles if r not in allowed_after]
            said = (
                f"{shown(old.approval.roles)} -> {shown(new.approval.roles)} (the same roles may "
                f"approve {second.reference}, {second.risk} risk: "
                f"{', '.join(dict.fromkeys(refused))} may not)"
            )
            yield Change(path, "not proven", said)
        return
    said = f"approved by {' or '.join(allowed_before) or 'nobody'} -> approved by "
    said += " or ".join(allowed_after) or "nobody"
    if old.approval.roles == new.approval.roles:
        said += f" (because {second.reference} is {second.risk} risk)"
    yield widened(path, said, set(allowed_before), set(allowed_after), "approvers")


def allowed(roles: Sequence[str], contract: Contract, versions: Versions) -> list[str]:
    """Of an approval's roles, those the catalog registers and lets approve `contract`'s risk."""
    able = [
        role
        for role in versions.registered(roles)
        if may_approve(versions.catalog.roles[role], contract.risk)
    ]
    return sorted(able)


# --- When a step may run -------------------------------------------------------------------------


def step_condition_change(leaf: Leaf) -> Change:
    """A step's `when`: removed, it runs on no fewer cases, and on more wherever it was false:
    looser (13b, choice 19); added, stricter; changed, not proven, both shown."""
    old, new = leaf.before, leaf.after
    whenever = "runs whenever it is admitted"
    if new is None:
        said = (
            f"runs only if {shown(old)} -> {whenever} (on no fewer cases, and on more wherever "
            "that was false)"
        )
        return Change(leaf.path, "looser", said, "step condition")
    if old is None:
        return Change(
            leaf.path, "stricter", f"{whenever} -> runs only if {shown(new)}", "step condition"
        )
    return Change(leaf.path, "not proven", f"{shown(old)} -> {shown(new)}")


# What turning each on lets a step do, said beside a looser verdict.
SWITCHES = {
    "automatic": "it starts by itself once admitted",
    "repeatable": "it may run again, when proposed",
}


def switch_change(leaf: Leaf, name: str) -> Change:
    """`automatic` or `repeatable`: turned on, looser; turned off, stricter (13b, choice 26)."""
    said = f"{shown(leaf.before)} -> {shown(leaf.after)}"
    if leaf.after is True:
        return Change(leaf.path, "looser", f"{said} ({SWITCHES[name]})", name)
    return Change(leaf.path, "stricter", said, name)
