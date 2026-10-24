"""Guards on people and runs: who may act, and when a step may run (layer 13b).

Each judges one kind of change between two versions of a package, as `case/diff.py`'s walk finds
it, and gives a verdict only where it is a proof for every case (brief, D55). A condition's
presence is judged, never the condition: an approval given a `when` is asked on no more runs, and
on fewer wherever it is false (13b, choice 19).
See docs/layers/13-diff.md (13b).
"""

from dataclasses import dataclass
from typing import Literal

from ventoux.case.changes import Change, DiffRefused, Leaf, Verdict, shown
from ventoux.case.definition import Approval, CallStep, CaseDefinition
from ventoux.core.catalog import Catalog, NotInCatalog
from ventoux.core.contract import Contract


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
