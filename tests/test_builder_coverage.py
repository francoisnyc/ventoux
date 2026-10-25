"""Every key of the format is one the builder writes (layer 14b, choice 17).

The keys are read from the format's own models, the Pydantic classes the engine parses with, never
from a list written here: a key added to the format later fails this test until the builder writes
it and an example uses it (brief, D58). See docs/layers/14-builder.md.
"""

import inspect
import json
import runpy
from collections.abc import Callable, Iterator
from decimal import Decimal
from pathlib import Path
from types import UnionType
from typing import Annotated, Any, Literal, TypeAliasType, Union, get_args, get_origin

from pydantic import BaseModel

from ventoux.case.definition import (
    ActivityStep,
    CaseDefinition,
    CaseField,
    CloseReason,
    DeclaredEvent,
    Milestone,
    PayloadField,
    PlanStep,
    ReminderRule,
    Rule,
    SlaRule,
    TaskStep,
    WaitStep,
    WorkflowStep,
    parse_case,
)
from ventoux.core.plan import ActivityState, ApprovalState, Plan, WaitState, parse_plan
from ventoux.tooling.builder import Case
from ventoux.tooling.builder import Plan as BuiltPlan
from ventoux.tooling.builder.written import package

ROOT = Path(__file__).parent.parent

# Every builder file in the repository: the packages' and the builder guide's examples.
BUILDER_FILES = sorted(
    [
        *(ROOT / "examples" / "quickstart" / "cases").glob("*.py"),
        *(ROOT / "examples" / "cases").glob("*.py"),
        *(ROOT / "examples" / "builder").glob("*.py"),
    ]
)

# Where a model keeps a key otherwise than the JSON writes it. A field's `declared` is written
# flat, as its type's own keys (`"type": "number"`), which the walk finds in the type's model; a
# plan's `sources` is written on each field, as `source`.
WRITTEN_OTHERWISE: dict[tuple[type[BaseModel], str], tuple[str, str] | None] = {
    (CaseField, "declared"): None,
    (PayloadField, "declared"): None,
    (Plan, "sources"): ("plan.Plan field", "source"),
}

type Key = tuple[str, str]  # a model's name and a key the JSON writes for it: ("Approval", "count")


def owner(model: type[BaseModel], name: str) -> str:
    """The model that declares the field `name`: `Step` for a step's `requires`, whichever kind of
    step holds it. Each kind's own call is checked to take every key of its model elsewhere
    (`test_every_step_call_takes_every_key_of_its_kind`)."""
    declaring = model
    for base in model.__mro__[1:]:
        if isinstance(base, type) and issubclass(base, BaseModel) and name in base.model_fields:
            declaring = base
    return named(declaring)


def named(model: type[BaseModel]) -> str:
    """A model's name with its module, since a case and a plan each have an `Approval`:
    `definition.Approval`, `plan.Approval`."""
    return f"{model.__module__.rsplit('.', 1)[-1]}.{model.__name__}"


def json_key(model: type[BaseModel], name: str) -> str:
    """The key the JSON writes the field `name` under: its alias (`rules`, `==`), or its name."""
    alias = model.model_fields[name].alias
    return alias if alias is not None else name


def inside(annotation: object) -> Iterator[object]:
    """Every type `annotation` holds, through aliases, `Annotated`, unions and containers, down to
    models and literals; the models themselves are not opened here."""
    if isinstance(annotation, TypeAliasType):
        yield from inside(annotation.__value__)
        return
    origin = get_origin(annotation)
    if origin is Annotated:
        yield from inside(get_args(annotation)[0])
    elif origin in (Union, UnionType) or origin in (tuple, dict, list):
        for argument in get_args(annotation):
            if argument is not Ellipsis:
                yield from inside(argument)
    else:
        yield annotation


def format_keys() -> tuple[set[Key], set[tuple[str, str, str]]]:
    """Every key the format has, and every value that picks a shape (`kind`, `type`, `final`,
    `forgetting`, the `"opened"` moment), read from the models reachable from a case and a plan."""
    keys: set[Key] = set()
    values: set[tuple[str, str, str]] = set()
    waiting: list[type[BaseModel]] = [CaseDefinition, Plan]
    seen: set[type[BaseModel]] = set()
    while waiting:
        model = waiting.pop()
        if model in seen:
            continue
        seen.add(model)
        for name, info in model.model_fields.items():
            if (model, name) in WRITTEN_OTHERWISE:
                instead = WRITTEN_OTHERWISE[(model, name)]
                if instead is not None:
                    keys.add(instead)
            else:
                keys.add((owner(model, name), json_key(model, name)))
            for held in inside(info.annotation):
                if isinstance(held, type) and issubclass(held, BaseModel):
                    waiting.append(held)
                elif get_origin(held) is Literal:
                    for value in get_args(held):
                        values.add((owner(model, name), json_key(model, name), value))
    return keys, values


def given_keys(found: object, keys: set[Key], values: set[tuple[str, str, str]]) -> None:
    """Every key `found`, a parsed definition or a part of one, was given (never a default), and
    every shape-picking value it holds."""
    if isinstance(found, BaseModel):
        model = type(found)
        for name in found.model_fields_set:
            value = getattr(found, name)
            if model is Plan and name == "sources":
                if value:
                    keys.add(("plan.Plan field", "source"))
            elif (model, name) not in WRITTEN_OTHERWISE:
                keys.add((owner(model, name), json_key(model, name)))
            if isinstance(value, str):
                values.add((owner(model, name), json_key(model, name), value))
            given_keys(value, keys, values)
    elif isinstance(found, dict):
        for item in found.values():
            given_keys(item, keys, values)
    elif isinstance(found, tuple | list):
        for item in found:
            given_keys(item, keys, values)
    elif not isinstance(found, str | bool | int | Decimal) and found is not None:
        raise TypeError(f"the coverage test can't read a {type(found).__name__}")


def written_by_the_builder() -> list[CaseDefinition | Plan]:
    """Every case and plan the repository's builder files write, read back as the engine reads
    them: their JSON, never the builder's objects."""
    found: list[CaseDefinition | Plan] = []
    for path in BUILDER_FILES:
        # Python: `run_path` runs a file as a script and gives back its top-level names. These are
        # the repository's own builder files, code reviewed like any code (brief, D58).
        for value in runpy.run_path(str(path)).values():
            if isinstance(value, Case):
                for name, text in package(value).items():
                    data = parse_json(text)
                    found.append(parse_case(data) if name == "case.json" else parse_plan(data))
    return found


def parse_json(text: str) -> Any:
    return json.loads(text, parse_float=Decimal)


def test_the_builder_writes_every_key_of_the_format() -> None:
    expected_keys, expected_values = format_keys()
    keys: set[Key] = set()
    values: set[tuple[str, str, str]] = set()
    for definition in written_by_the_builder():
        given_keys(definition, keys, values)
    missing = sorted(expected_keys - keys) + sorted(expected_values - values)
    assert not missing, "\n".join(
        ["keys of the format no builder file in the repository writes:"]
        + [" ".join(map(str, key)) for key in missing]
    )


def test_every_key_written_otherwise_is_a_field_of_its_model() -> None:
    # A line above naming a field no model has would hide a key from the test.
    for model, name in WRITTEN_OTHERWISE:
        assert name in model.model_fields, f"{model.__name__} has no field {name}"


# Each kind of entry, and the call that writes it. Its keys are read from its model.
CALLS: dict[type[BaseModel], Callable[..., object]] = {
    TaskStep: Case.task,
    ActivityStep: Case.activity,
    WorkflowStep: Case.workflow,
    WaitStep: Case.wait,
    PlanStep: Case.plan_step,
    CaseField: Case.field,
    Milestone: Case.milestone,
    DeclaredEvent: Case.event,
    CloseReason: Case.close_reason,
    Rule: Case.rule,
    SlaRule: Case.sla,
    ReminderRule: Case.reminder,
    ActivityState: BuiltPlan.activity,
    WaitState: BuiltPlan.wait,
    ApprovalState: BuiltPlan.approval,
}
# A key a call takes under another name, or says by being the call it is: `display` is `title`
# (and `description`), a step's `kind` is which call writes it, a field's type is its `kind`.
SAID_OTHERWISE = {"display": "title", "kind": None, "declared": "kind"}


def test_every_call_takes_every_key_of_its_kind() -> None:
    # The coverage test counts a key on the model that declares it (`Step requires`); this one
    # checks each kind's own call takes it, so no kind drops a key the others write.
    for model, call in CALLS.items():
        taken = set(inspect.signature(call).parameters)
        for key in keys_taken(model, taken):
            assert key in taken, f"{call.__qualname__} takes no {key}, which {model.__name__} has"


def keys_taken(model: type[BaseModel], taken: set[str]) -> Iterator[str]:
    """Each key of `model` its call takes. A nested object the call takes flat, an sla's `sla`
    (`step=`, `within=`) or a wait state's `wait`, gives its own keys instead."""
    for name, info in model.model_fields.items():
        key = SAID_OTHERWISE.get(name, json_key(model, name))
        if key is None or key in taken:
            continue
        nested = info.annotation
        if isinstance(nested, type) and issubclass(nested, BaseModel):
            yield from keys_taken(nested, taken)
        else:
            yield key
