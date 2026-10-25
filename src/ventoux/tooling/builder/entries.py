"""What a case is made of, as the builder hands it back: steps, milestones, events and moments, an
approval, an outcome, and what a rule does (layer 14b) (brief, D58).

Each is a name and how expressions and other entries read it: `review.outcome`, `paid.reached`,
`cancelled.text("note")`. Only `Case` writes entries; these only name them.
See docs/layers/14-builder.md.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from ventoux.tooling.builder.expressions import (
    BoolExpr,
    Expr,
    NumberExpr,
    OutcomeExpr,
    ReferenceExpr,
    TextExpr,
)
from ventoux.tooling.builder.fields import FieldType


class Moment:
    """A moment a rule reacts to, as the JSON writes it (brief, D38): `"opened"`,
    `{"started": "review"}`, `{"reached": "paid"}`, `{"answered": "review"}`, `{"event": …}`."""

    def __init__(self, data: object) -> None:
        self.data = data


# The moment the case opened.
OPENED = Moment("opened")


class Timer:
    """Time passing after a moment, once: `after("2d", since=review.started)` (brief, D44). Not a
    `Moment`, so a timer is never set on another timer."""

    def __init__(self, age: str, since: Moment) -> None:
        self.data = {"after": age, "since": since.data}


def after(age: str, since: Moment) -> Timer:
    """A timer: `age` (`30m`, `12h`, `2d`) after the moment `since`, firing once (brief, D44)."""
    return Timer(age, since)


class Milestone:
    """A fact the case has reached, such as `paid`: never undone (brief, D48)."""

    def __init__(self, name: str) -> None:
        self.name = name

    @property
    def reached(self) -> Moment:
        """The moment it is reached."""
        return Moment({"reached": self.name})


class Step:
    """A step: its answer, its outputs and its start, as expressions and moments read them."""

    def __init__(self, name: str) -> None:
        self.name = name

    @property
    def outcome(self) -> OutcomeExpr:
        """The outcome of the step's latest run: `review.outcome == "approve"`."""
        return OutcomeExpr({"var": f"{self.name}.outcome"})

    def output[E: Expr[Any]](self, name: str, kind: FieldType[E]) -> E:
        """The output `name` of the step's latest run, typed as the developer declares it. The
        contract is the catalog's: whether it gives `name`, so typed, is `ventoux check`'s to
        say, never the builder's guess (choice 20)."""
        return kind.reads_as({"var": f"{self.name}.{name}"})

    @property
    def started(self) -> Moment:
        """The moment a run of the step starts: each run (brief, D38)."""
        return Moment({"started": self.name})


class Task(Step):
    """A task: a step a person answers."""

    @property
    def answered(self) -> Moment:
        """The moment a run of the task is answered, whatever the outcome (brief, D39)."""
        return Moment({"answered": self.name})


class Event:
    """An event from outside, declared in the case: its arrival, and the values it carries, read as
    `<event>.<field>` and typed as the payload declares them (brief, D41)."""

    def __init__(self, name: str, declared: Mapping[str, str]) -> None:
        self.name = name
        self.declared = declared  # each payload field's type: `{"note": "string"}`

    @property
    def arrived(self) -> Moment:
        """The moment the event arrives: each arrival."""
        return Moment({"event": self.name})

    def number(self, name: str) -> NumberExpr:
        return NumberExpr(self.carried(name, "number"))

    def text(self, name: str) -> TextExpr:
        return TextExpr(self.carried(name, "string"))

    def boolean(self, name: str) -> BoolExpr:
        return BoolExpr(self.carried(name, "boolean"))

    def reference(self, name: str) -> ReferenceExpr:
        return ReferenceExpr(self.carried(name, "reference"))

    def carried(self, name: str, kind: str) -> dict[str, str]:
        """`{"var": "<event>.<name>"}`, refused unless the payload declares `name` as a `kind`:
        read otherwise, it would write another definition than the one declared."""
        if name not in self.declared:
            raise TypeError(f"{self.name} carries no field {name}")
        if self.declared[name] != kind:
            raise TypeError(f"{self.name} carries {name} as a {self.declared[name]}, not a {kind}")
        return {"var": f"{self.name}.{name}"}


@dataclass(frozen=True)
class Outcome:
    """A task's answer: what people read, the fields its form sets, and the milestones answering
    with it reaches (brief, D9)."""

    title: str
    sets: Sequence[Expr[Any]] = ()  # fields, such as `approved`
    reaches: Sequence[Milestone] = ()
    description: str | None = None


@dataclass(frozen=True)
class Approval:
    """A step's approval: who approves, how many, when it is needed, and why (brief, D11)."""

    roles: Sequence[str]  # who may approve; every approver holds one of them
    reason: str  # what an approver reads
    when: Expr[bool] | None = None  # None: every run needs it
    count: int | None = None  # how many distinct people must approve; left out, 1 (brief, D47)


def four_eyes(roles: Sequence[str], reason: str, when: Expr[bool] | None = None) -> Approval:
    """Two distinct people approve: the builder's name for `"count": 2` (brief, D47)."""
    return Approval(roles=roles, reason=reason, when=when, count=2)


@dataclass(frozen=True)
class Then:
    """What a rule does when it fires, as the JSON's `then` writes it (brief, D38): set fields,
    reach milestones, start steps, stop steps."""

    # Each field set, from an expression, as pairs: `[(approved, amount)]`, written by the field's
    # name. Pairs, since an `Expr` can't be a dict key: its `==` builds an expression.
    set: Sequence[tuple[Expr[Any], Expr[Any]]] = ()
    reach: Sequence[Milestone] = ()
    start: Sequence[Step] = ()
    stop: Sequence[Step] = ()


@dataclass(frozen=True)
class SentBy:
    """Who may send an event: one system, or people holding one of some roles (brief, D41)."""

    system: str | None = None
    roles: Sequence[str] | None = None


@dataclass(frozen=True)
class Payload:
    """One value an event carries: its type, what people read, and a declared untrusted source."""

    kind: FieldType[Any]
    title: str
    source: str | None = None
    description: str | None = None
