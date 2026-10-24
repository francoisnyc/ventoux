"""What the semantic diff says: a change, its verdict, and the closed list of comparisons that
may give one (layers 13a and 13b).

A verdict is a proof for every case, given only by a comparison on the list, each with a witness:
a run where one version refuses what the other lets through (brief, D55). Shared by the walk
(`case/diff.py`) and the guards on people and runs (`case/guards.py`).
See docs/layers/13-diff.md.
"""

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal
from typing import Literal, cast

from pydantic import BaseModel

from ventoux.core.expressions import Expression, render
from ventoux.core.expressions.model import Node

type Verdict = Literal["looser", "stricter", "not proven"]

MISSING = object()  # an entry one version doesn't have

# The comparisons that may give a verdict, a closed list: each has a witness, a run where one
# version refuses what the other lets through (brief, D55).
COMPARISONS = (
    "input policy",  # what an input of a step's contract accepts (brief, D21)
    "untrusted mark",  # an `untrusted:` mark on a field (brief, D12)
    "sensitive",  # a field's value wrapped, and never given to a workflow step (brief, D31)
    "readers",  # the roles that see a field, or every outcome and output (brief, D30)
    "output source",  # where a step's contract says an output comes from (brief, D29)
    # 13b: who may act, and when a step may run.
    "approval",  # whether a step's runs wait for an approval (brief, D11)
    "approval condition",  # whether an approval has a `when`, never what it says (13b, choice 19)
    "approval count",  # how many distinct people must approve (brief, D47)
    "approvers",  # the roles that may approve a step's contract's risk (brief, D11)
    "approval exclusions",  # whose answers a step reads, who may not approve it (brief, D11)
    "answerers",  # who may answer a task (brief, D22)
    "proposers",  # who may propose a step (brief, D25)
    "senders",  # who may send an event (brief, D41)
    "closers",  # who may close a case with a reason (brief, D10)
    "requirements",  # what a step waits for, `sequence` folded in (13b, choice 24)
    "step condition",  # whether a step has a `when`, never what it says (13b, choice 19)
    "automatic",  # whether a step starts by itself once admitted (13b, choice 26)
    "repeatable",  # whether a step may run again, when proposed (13b, choice 26)
    "close reasons",  # the ways people may close a case (brief, D10)
    "freshness",  # how old a fact a step reads may be (brief, D18)
    "forgetting",  # when a case may be forgotten (brief, D32)
    "plan approvals",  # which of a plan's activities an approval state approves (13b, choice 30)
    "plan approvers",  # who may approve in a plan, as its activity's risk allows (brief, D11)
    "plan answerers",  # who may answer a plan's wait (brief, D22)
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

    # Dataclass: `__post_init__` runs once the fields are set, every time a change is made.
    def __post_init__(self) -> None:
        # A verdict is a proof: looser or stricter only from a comparison on the closed list, and
        # "not proven" from none (brief, D55).
        proven = self.verdict != "not proven"
        if proven != (self.comparison in COMPARISONS):
            raise ValueError(f"{self.path}: {self.verdict} needs one of COMPARISONS, and only it")

    def __str__(self) -> str:
        why = f" (because {self.because})" if self.because else ""
        return f"{self.verdict:<10} {self.path}: {self.said}{why}"


@dataclass(frozen=True)
class Rewritten:
    """Written otherwise, deciding the same for every case: no verdict, never counted as what may
    loosen, and only where the diff proves it (13c, choice 38)."""

    path: str  # where, as the JSON writes it
    said: str  # what it was and is, and what differs, if anything, in what the history says

    def __str__(self) -> str:
        return f"{'rewritten':<10} {self.path}: {self.said}"


@dataclass(frozen=True)
class Leaf:
    """Where the two versions behave differently, as deep as a reader needs: an expression whole,
    an entry added or removed whole."""

    path: str  # where, as the JSON writes it
    before: object  # what the old version has there; MISSING: added
    after: object  # what the new version has there; MISSING: removed


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


@dataclass(frozen=True)
class Reworded:
    """A piece of wording changed: never behaviour (brief, D5)."""

    path: str  # where: `steps.settle.display.title`
    before: str | None  # the old text; None: it wasn't written
    after: str | None  # the new text; None: it isn't written any more

    def __str__(self) -> str:
        return f"{'wording':<10} {self.path}: {quoted(self.before)} -> {quoted(self.after)}"


def quoted(text: str | None) -> str:
    """A piece of wording as the diff shows it: in quotes, or `none`."""
    return "none" if text is None else json.dumps(text, ensure_ascii=False)


@dataclass(frozen=True)
class Against:
    """The record a release's notes compare with: a release and one of its wordings."""

    release: int
    wording: int  # 1 for the release itself


@dataclass(frozen=True)
class Notes:
    """A release's notes: the semantic diff against the record before it, kept as data, so a
    reader renders it in the same verdict words as the diff, never judged again (brief, D57)."""

    against: Against | None  # None: the first release, compared with nothing
    changes: tuple[Change, ...] = ()
    rewritten: tuple[Rewritten, ...] = ()  # written otherwise, the same decisions
    wording: tuple[Reworded, ...] = ()
