"""A case definition, built in Python: each call writes one entry of the JSON (layer 14a)
(brief, D58).

The builder is one-to-one with the JSON: `refund.task("review", …)` writes `steps.review`, with the
same names. It writes data and decides nothing: whether the definition holds together is
`ventoux check`'s, against the catalog, and running it is the engine's, on the JSON.
See docs/layers/14-builder.md and docs/QUICKSTART.md, section 2.
"""

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from ventoux.tooling.builder.expressions import Expr, NumberExpr

# A definition's JSON, as plain data: dicts, lists, texts, numbers and truth values.
type Data = dict[str, Any]


@dataclass(frozen=True)
class FieldType[E: Expr[Any]]:
    """A field's type: what the JSON declares, and the runtime expression the field reads as."""

    declared: Data  # `{"type": "number"}`, written beside the field's `display`
    reads_as: Callable[[object], E]  # `NumberExpr`: so `amount > 100` type-checks, `"x"` doesn't


class Field:
    """The types a field is declared with: `Field.number()`."""

    @staticmethod
    def number() -> FieldType[NumberExpr]:
        """A number: one type, an exact decimal (brief, D20)."""
        return FieldType({"type": "number"}, NumberExpr)


@dataclass(frozen=True)
class Outcome:
    """A task's answer: what people read, and the case-file fields its form sets (brief, D9)."""

    title: str
    sets: Sequence[Expr[Any]] = ()  # fields, such as `approved`


@dataclass(frozen=True)
class Approval:
    """A step's approval: who approves, when it is needed, and why (brief, D11)."""

    roles: Sequence[str]  # who may approve; every approver holds one of them
    reason: str  # what an approver reads
    when: Expr[bool] | None = None  # None: every run needs it


class Step:
    """A step the builder made: its name, and its answer as a runtime value."""

    def __init__(self, name: str) -> None:
        self.name = name

    @property
    def outcome(self) -> Expr[str]:
        """The outcome of the step's latest run: `review.outcome == "approve"`."""
        return Expr({"var": f"{self.name}.outcome"})


class Case:
    """A case definition, built one entry at a time, in the order the calls are made: steps are
    admitted in the order written (brief, D38)."""

    def __init__(self, name: str, title: str) -> None:
        self.name = name
        self.title = title
        self.fields: dict[str, Data] = {}
        self.steps: dict[str, Data] = {}
        self.order: list[str] = []  # `sequence`: each step requires the one before it

    def field[E: Expr[Any]](
        self, name: str, kind: FieldType[E], title: str, source: str | None = None
    ) -> E:
        """A field of the case file, `fields.<name>`, read in expressions as itself."""
        entry: Data = {**kind.declared, "display": {"title": title}}
        if source is not None:
            entry["source"] = source  # `untrusted:<label>`, never trusted (brief, D12)
        self.fields[self.new_name(name, self.fields, "field")] = entry
        return kind.reads_as({"var": name})

    def reference(self, name: str, system: str, title: str) -> Expr[str]:
        """A reference to a record kept in `system`: its ID, never a copy (brief, D8)
        (brief, D16)."""
        entry: Data = {"type": "reference", "system": system, "display": {"title": title}}
        self.fields[self.new_name(name, self.fields, "field")] = entry
        return Expr({"var": name})

    def task(
        self,
        name: str,
        title: str,
        roles: Sequence[str],
        outcomes: Mapping[str, Outcome],
        requires: Sequence[Step] = (),
        when: Expr[bool] | None = None,
    ) -> Step:
        """A task for a person holding one of `roles`, answered with one of `outcomes`."""
        entry: Data = {"kind": "task", "display": {"title": title}, "roles": list(roles)}
        entry |= starting(requires, when)
        entry["outcomes"] = {key: answer(outcome) for key, outcome in outcomes.items()}
        self.steps[self.new_name(name, self.steps, "step")] = entry
        return Step(name)

    def activity(
        self,
        name: str,
        activity: str,
        title: str,
        inputs: Mapping[str, Expr[Any]] | None = None,
        requires: Sequence[Step] = (),
        when: Expr[bool] | None = None,
        approval: Approval | None = None,
    ) -> Step:
        """A call to `activity` (`payments.refund@2`), a contract in the catalog, with `inputs`
        read from the case file."""
        entry: Data = {"kind": "activity", "display": {"title": title}, "activity": activity}
        if inputs:
            entry["inputs"] = {key: given(value).data for key, value in inputs.items()}
        entry |= starting(requires, when)
        if approval is not None:
            entry["approval"] = approved_by(approval)
        self.steps[self.new_name(name, self.steps, "step")] = entry
        return Step(name)

    def sequence(self, *steps: Step) -> None:
        """`steps` run in this order, each starting by itself when the one before is done."""
        if self.order:
            # One `sequence` per case: a second would replace the first without a word.
            raise ValueError(f"{self.name} already has a sequence: give it every step once")
        self.order = [step.name for step in steps]

    def new_name(self, name: str, taken: Mapping[str, object], what: str) -> str:
        """`name`, refused if this case already has a `what` of that name: a second entry would
        replace the first without a word."""
        if name in taken:
            raise ValueError(
                f"{self.name} already has a {what} named {name}: give this one another"
            )
        return name

    def definition(self) -> Data:
        """The case's JSON, as plain data, its keys in the order the format writes them."""
        data: Data = {"case": self.name, "display": {"title": self.title}}
        if self.fields:
            data["fields"] = self.fields
        data["steps"] = self.steps
        if self.order:
            data["sequence"] = self.order
        return data


def starting(requires: Sequence[Step], when: Expr[bool] | None) -> Data:
    """When a step may start: the steps it waits for, then the condition read once they are."""
    data: Data = {}
    if requires:
        data["requires"] = [step.name for step in requires]
    if when is not None:
        data["when"] = given(when).data
    return data


def answer(outcome: Outcome) -> Data:
    """An outcome's JSON: what people read, and the fields its form sets."""
    data: Data = {"display": {"title": outcome.title}}
    if outcome.sets:
        data["sets"] = [field_name(field) for field in outcome.sets]
    return data


def approved_by(approval: Approval) -> Data:
    """An approval's JSON: when, who, and the reason people read."""
    data: Data = {}
    if approval.when is not None:
        data["when"] = given(approval.when).data
    data["roles"] = list(approval.roles)
    data["display"] = {"reason": approval.reason}
    return data


def given(value: object) -> Expr[Any]:
    """`value`, where a runtime expression is required: refused if it is a Python value, which
    the type checker refuses first (brief, D58)."""
    if not isinstance(value, Expr):
        raise TypeError(
            f"{value!r} is a Python value where a runtime expression is required: give a field, "
            "an expression, or literal(…) for a constant"
        )
    return value


def field_name(field: object) -> str:
    """The name of `field`, a case-file field: anything else can't be set by a form."""
    data = field.data if isinstance(field, Expr) else None
    if isinstance(data, dict) and set(data) == {"var"} and "." not in data["var"]:
        name: str = data["var"]
        return name
    raise TypeError(f"{field!r} is not a field of the case file: a form sets fields only")
