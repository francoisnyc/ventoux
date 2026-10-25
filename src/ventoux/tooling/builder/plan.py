"""A plan, built in Python: its fields, where it starts, and its states (layer 14b) (brief, D58).

One-to-one with the JSON a plan is stored as (brief, D13): `plan.activity("pay", …)` writes
`states.pay`. A state's `on` names its targets by name, as the JSON does, since a plan may loop back
to a state made later. Whether the plan holds together (a target that exists, a path to a final
state, an untrusted condition) is validation's to say, never the builder's.
See docs/layers/14-builder.md.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Literal

from ventoux.tooling.builder.common import called_from, display, field_name, given
from ventoux.tooling.builder.expressions import Expr
from ventoux.tooling.builder.fields import Data, FieldType


@dataclass(frozen=True)
class Transition:
    """Where a state goes next, if `when` holds (or always, with no `when`)."""

    target: str  # a state's name
    when: Expr[bool] | None = None


# Where an outcome leads: a state's name (the shorthand), or transitions tried in order.
type Targets = str | Transition | Sequence[Transition]


class Plan:
    """A plan, built one state at a time, its states in the order the calls are made."""

    def __init__(self, name: str, version: int, title: str, description: str | None = None) -> None:
        self.name = name
        self.version = version
        self.display = display(title, description)
        self.fields: dict[str, Data] = {}
        self.states: dict[str, Data] = {}
        self.start: str | None = None  # `initial`: the state it starts in
        # Where each entry was written, by its path in the plan (`states.pay`), `""` the plan.
        self.where: dict[str, str] = {"": called_from()}

    @property
    def reference(self) -> str:
        """How a case's plan step names it: `refund-order@1` (brief, D28)."""
        return f"{self.name}@{self.version}"

    def field[E: Expr[Any]](self, name: str, kind: FieldType[E], source: str | None = None) -> E:
        """A field of the plan, `fields.<name>`: its type, and a declared untrusted source."""
        entry: Data = dict(kind.declared)
        if source is not None:
            entry["source"] = source  # `untrusted:<label>`, never trusted (brief, D12)
        self.fields[self.new_name(name, self.fields, "field")] = entry
        self.where[f"fields.{name}"] = called_from()
        return kind.reads_as({"var": name})

    def activity(
        self,
        name: str,
        activity: str,
        on: Mapping[str, Targets],
        inputs: Mapping[str, Expr[Any]] | None = None,
    ) -> str:
        """Call `activity`, then move on by what happened: `done` or an outcome."""
        state: Data = {"activity": activity}
        if inputs:
            state["inputs"] = {key: given(value).data for key, value in inputs.items()}
        state["on"] = moves(on)
        return self.add(name, state)

    def wait(
        self,
        name: str,
        outcomes: Sequence[str],
        roles: Sequence[str],
        on: Mapping[str, Targets],
        sets: Mapping[str, Sequence[Expr[Any]]] | None = None,
        timeout: str | None = None,
    ) -> str:
        """Wait for a person holding one of `roles` to answer with one of `outcomes`."""
        asked: Data = {"outcomes": list(outcomes), "roles": list(roles)}
        if sets is not None:
            asked["sets"] = {
                key: [field_name(f, "the plan") for f in fields] for key, fields in sets.items()
            }
        if timeout is not None:
            asked["timeout"] = timeout
        return self.add(name, {"wait": asked, "on": moves(on)})

    def approval(
        self,
        name: str,
        of: str,
        roles: Sequence[str],
        on: Mapping[str, Targets],
        timeout: str | None = None,
    ) -> str:
        """Ask a person holding one of `roles` to approve running the activity state `of`: its own
        act, answered `approve` or `reject` (brief, D23)."""
        asked: Data = {"of": of, "roles": list(roles)}
        if timeout is not None:
            asked["timeout"] = timeout
        return self.add(name, {"approval": asked, "on": moves(on)})

    def final(self, name: str, outcome: Literal["succeeded", "failed"]) -> str:
        """The plan has ended, and how."""
        return self.add(name, {"final": outcome})

    def initial(self, state: str) -> None:
        """The state the plan starts in: said once."""
        if self.start is not None:
            raise ValueError(f"{self.name} already starts in {self.start}: say it once")
        self.start = state
        self.where["initial"] = called_from()

    def add(self, name: str, state: Data) -> str:
        self.states[self.new_name(name, self.states, "state")] = state
        self.where[f"states.{name}"] = called_from()
        return name

    def new_name(self, name: str, taken: Mapping[str, object], what: str) -> str:
        """`name`, refused if this plan already has a `what` of that name: a second entry would
        replace the first without a word."""
        if name in taken:
            raise ValueError(
                f"{self.name} already has a {what} named {name}: give this one another"
            )
        return name

    def definition(self) -> Data:
        """The plan's JSON, as plain data, its keys in the order the format writes them."""
        data: Data = {"plan": self.name, "version": self.version, "display": self.display}
        if self.fields:
            data["fields"] = self.fields
        if self.start is not None:
            data["initial"] = self.start
        data["states"] = self.states
        return data


def moves(on: Mapping[str, Targets]) -> Data:
    """A state's `on`: each outcome's targets as written, a bare name as the shorthand."""
    return {outcome: targets(written) for outcome, written in on.items()}


def targets(written: Targets) -> object:
    if isinstance(written, str):
        return written
    transitions = [written] if isinstance(written, Transition) else list(written)
    return [transition(each) for each in transitions]


def transition(each: Transition) -> Data:
    data: Data = {"target": each.target}
    if each.when is not None:
        data["when"] = given(each.when).data
    return data
