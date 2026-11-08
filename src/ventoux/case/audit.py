"""Audit records: each act a case decides, as data, with the decisions it caused (layer 19a).

A history line is for people, and never quotes a value (brief, D30). A record is for an auditor,
years later: who did what, what the engine decided because of it, under which rule, and on which
facts, each with its sources and value (brief, D15). Records are made by the engine beside its
lines, never by reading them back (brief, D76). Only data here, so the state can hold records;
`ventoux.case.recording` makes them. See docs/layers/19-audit-keys.md (19a).
"""

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Literal

# What an act was, by the event that brought it to the case.
type ActKind = Literal[
    "opened",
    "answered",
    "proposed",
    "completed",
    "failed",
    "retried",
    "closed",
    "plan cancelled",
    "child ended",
    "child rang",
    "child not ended",
    "closed by parent",
    "workflow cancelled",
    "shown",
    "forget approved",
    "change proposed",
    "event",
    "timer",
    "claimed",
    "given back",
    "assigned",
    "unassigned",
    "export failed",
    "export retried",
    # A request to forget a case writes its own stream (brief, D77): proposed, answered, and once
    # the case has ended, its key destroyed.
    "forget proposed",
    "key destroyed",
]

# What the engine decided, as an auditor asks about it (brief, D76).
type DecisionKind = Literal[
    "answered",
    "approved",
    "rejected",
    "refused",
    "admitted",
    "started",
    "completed",
    "failed",
    "retried",
    "skipped",
    "reached",
    "set",
    "closed",
    "stopped",
    "edited",
    "migrated",
    "forgotten",
]


@dataclass(frozen=True)
class Fact:
    """A fact a decision read: its field, where its value came from, and the value."""

    field: str  # the case file's field, such as `approved_amount`
    sources: tuple[str, ...]  # where the value came from, sorted: `person:ana` (brief, D12)
    # The value as the state holds it: an exact decimal, a text, or a `Sensitive`, never
    # unwrapped (brief, D31).
    value: object


@dataclass(frozen=True)
class Decision:
    """One thing the engine decided because of an act."""

    kind: DecisionKind
    step: str | None = None  # the step it concerns, if any: `pay`
    entry: str | None = None  # its run or entry, if any: `pay#1`, `pay.approval#1`
    # Where in the definition it was decided: `steps.pay.when`, `steps.pay.approval`.
    rule: str | None = None
    read: tuple[Fact, ...] = ()  # the facts it read, in the order read
    # What it wrote, if anything: the field a rule set or an edit changed, with its new value and
    # sources, sensitive ones wrapped.
    wrote: Fact | None = None
    target: str | None = None  # what it reached or stopped, if anything: `owed_known`, `pay#1`
    # Why, for a refusal or a failure: its own words, which never quote a value (brief, D30).
    reason: str | None = None
    # Who decided it, when not the act's own: a person answering a wait inside a plan step's plan,
    # whose answer reaches the case with the step's end (brief, D77).
    by: str | None = None
    # What it gave, when the decision carries one: a plan's activity's outcome (`done`,
    # `declined`), the answer given to a plan's wait (`approve`).
    outcome: str | None = None


@dataclass(frozen=True)
class Act:
    """An act that reached the case, as it came."""

    kind: ActKind
    by: str | None = None  # who: a person, `system:portal`; None for the engine's own
    roles: tuple[str, ...] = ()  # their roles, as the trusted caller stated them, sorted
    # What it names, if anything: an entry or run (`review#1`), a step proposed (`pay`), a field
    # shown or edited (`customer_id`), an event sent (`cancelled`), a timer's rule (`chase`).
    entry: str | None = None
    # What it gives, if anything: an outcome (`approve`), a close reason (`duplicate`), a change's
    # kind (`edit`), how a child's workflow ended (`it was terminated`).
    outcome: str | None = None
    # The values it gave, by field, as the state holds them: sensitive ones wrapped.
    values: Mapping[str, object] = field(default_factory=dict[str, object])


@dataclass(frozen=True)
class AuditRecord:
    """One act, the decisions it caused in order, and the history lines it wrote (brief, D76)."""

    number: int  # its place in its stream, from 1: never a time, never random
    at: int  # when the act reached the case, in seconds since the epoch (brief, D33)
    release: str | None  # the release the case decided on, `refund 1`; None for a draft
    engine: int  # the engine version it decided as (brief, D51)
    act: Act
    decisions: list[Decision]
    lines: list[str]  # the lines it added to the history, for people: never parsed
