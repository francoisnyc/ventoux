"""A repeated step's runs, one for each item of its list (brief, D73).
Moved from `case/runtime.py` (docs/layers/runtime-split.md).
"""

from collections.abc import Mapping
from typing import Literal, cast

from ventoux.case.admission import (
    StepStopped,
    holds,
    latest_of_item,
    requirements_met,
)
from ventoux.case.called import called
from ventoux.case.closing import (
    close_held,
)
from ventoux.case.definition import (
    EACH,
    ActivityStep,
    CaseDefinition,
    TaskStep,
)
from ventoux.case.owed import owed
from ventoux.case.recording import decided_failure, decided_start, starting_rule
from ventoux.case.runtime.runs import fail
from ventoux.case.state import (
    CaseState,
    Command,
    Moment,
    Schedule,
    StepRun,
)
from ventoux.case.types import expression_problem, step_types
from ventoux.core.before_activity import (
    InputRefused,
    checked_inputs,
)
from ventoux.core.catalog import Catalog, NotInCatalog
from ventoux.core.provenance import provenance
from ventoux.core.sensitive import plain


def start_items(  # noqa: C901
    case: CaseDefinition,
    catalog: Catalog,
    state: CaseState,
    name: str,
    step: TaskStep | ActivityStep,
    required: tuple[str, ...],
    commands: list[Command],
) -> bool:
    """Start the repeated step's run for each item that has none, once its requirements are met:
    each named by the number its key was given, and read with its item as `each`. Whether any
    started (brief, D73)."""
    if close_held(case, state) and name not in owed(case, state):
        return False  # nothing new starts while the close is held (brief, D34)
    if not requirements_met(required, state):
        return False
    if any(run.step == name and run.item is None for run in state.runs):
        return False  # its items couldn't be told apart: it waits for a person (brief, D17)
    try:
        items = numbered_items(state, name, step)
    except StepStopped as error:
        fail(state, name, str(error))
        return True
    # Every expression it reads is checked over the case's types and its item's first, so a
    # misspelt outcome fails it instead of reading as false (brief, D35).
    if (problem := expression_problem(case, catalog, name, state.cases)) is not None:
        fail(state, name, problem)
        return True
    started = False
    for number, item in items:
        latest = latest_of_item(state, name, number)
        retried = latest if latest is not None and latest.status == "retrying" else None
        if latest is not None and retried is None:
            continue  # each item's run starts by itself at most once; again only when retried
        values, sources = with_item(case, state, step, item)
        try:
            if step.when is not None and not holds(step.when, values, f"{name}'s condition"):
                continue
            start_item(case, catalog, state, name, step, number, values, sources, commands, retried)
        except (StepStopped, InputRefused, NotInCatalog) as error:
            if retried is not None:  # the same run fails again, keeping its key (brief, D26)
                retried.status, retried.reason = "failed", str(error)
                state.history.append(f"{retried.entry} failed again: {error}")
                decided_failure(state, name, retried.entry, str(error))
            else:
                entry = f"{name}.{number}#1"
                run = StepRun(entry, name, "failed", reason=str(error), item=number)
                run.started = False
                state.runs.append(run)
                state.history.append(f"{run.entry} failed: {error}")
                decided_failure(state, name, run.entry, str(error))
        started = True
    return started


def ran(
    state: CaseState,
    name: str,
    entry: str,
    number: int,
    status: Literal["open", "running"],
    retried: StepRun | None,
) -> None:
    """The item's run is now `status`: the run an operator retried, the same run (brief, D26), or
    a new one, whose start is a moment for rules (brief, D38)."""
    if retried is not None:
        retried.status = status
        return
    state.runs.append(StepRun(entry, name, status, item=number))
    state.moments.append(Moment(f"started {name}", entry, entry))


def item_of(
    state: CaseState, name: str, step: TaskStep | ActivityStep, number: int
) -> dict[str, object]:
    """The item of the list `name` repeats over whose key was given `number` (brief, D73)."""
    assert step.for_each is not None
    numbers = state.items[name]
    items = cast(list[dict[str, object]], plain(state.values[step.for_each.over]))
    return next(item for item in items if numbers.get(str(item[step.for_each.key])) == number)


def numbered_items(
    state: CaseState, name: str, step: TaskStep | ActivityStep
) -> list[tuple[int, dict[str, object]]]:
    """The items of the list the step repeats over, each with the number its key was given the
    first time it was seen; or `StepStopped` if two items share a key: nothing guesses which is
    which (brief, D73)."""
    assert step.for_each is not None
    over, key = step.for_each.over, step.for_each.key
    if over not in state.values:
        raise StepStopped(f"{name} can't run: {over} holds no value")
    items = cast(list[dict[str, object]], plain(state.values[over]))
    keys = [str(item[key]) for item in items]
    if len(set(keys)) < len(keys):
        raise StepStopped(
            f"{name} can't run: two items of {over} have the same {key}: each item's key is its own"
        )
    first_seen = name not in state.items
    numbers = state.items.setdefault(name, {})
    for each in keys:
        numbers.setdefault(each, len(numbers) + 1)  # a number is never given again
    if first_seen and not items:
        state.history.append(f"{name}: {over} has no items, so it has no runs")
    return [(numbers[each], item) for each, item in zip(keys, items, strict=True)]


def with_item(
    case: CaseDefinition, state: CaseState, step: TaskStep | ActivityStep, item: dict[str, object]
) -> tuple[dict[str, object], dict[str, frozenset[str]]]:
    """The case file as one run of the repeated step reads it: its item's fields as `each.<field>`,
    each with the list's sources (brief, D12) (brief, D73)."""
    assert step.for_each is not None
    over = step.for_each.over
    values = {**state.values, **{f"{EACH}.{field}": value for field, value in item.items()}}
    listed_by = state.sources.get(over, frozenset())
    sources = {**state.sources, **{f"{EACH}.{field}": listed_by for field in item}}
    return values, sources


def start_item(
    case: CaseDefinition,
    catalog: Catalog,
    state: CaseState,
    name: str,
    step: TaskStep | ActivityStep,
    number: int,
    values: Mapping[str, object],
    sources: Mapping[str, frozenset[str]],
    commands: list[Command],
    retried: StepRun | None = None,
) -> None:
    """Open the item's task run, or schedule its activity with a key naming the case and the run
    (brief, D17) (brief, D73). A `retried` run starts again as the same run, with its entry and
    so its key (brief, D26)."""
    entry = f"{name}.{number}#1" if retried is None else retried.entry
    if isinstance(step, TaskStep):
        ran(state, name, entry, number, "open", retried)
        state.waiting[entry] = f"{name}.{number} by {' or '.join(step.roles)}"
        state.history.append(
            f"started {entry}: waiting for {' or '.join(step.outcomes)} by "
            f"{' or '.join(step.roles)}"
        )
        decided_start(state, name, step, entry, starting_rule(state, name, step))
        return
    contract = called(catalog, step)
    if contract.risk == "high":
        raise StepStopped(f"{contract.reference} is high risk, and {name} is repeated")
    key = f"{state.case}/{entry}"
    types = step_types(case, {f: declared.declared for f, declared in case.fields.items()}, name)
    inputs = checked_inputs(contract, step.inputs, values, sources, key, types, ())
    ran(state, name, entry, number, "running", retried)
    said = "; ".join(
        f"{field} from {', '.join(sorted(provenance(expression, sources))) or 'the case'}"
        for field, expression in step.inputs.items()
    )
    keyed = f", key {key}" if contract.idempotency_key is not None else ""
    state.history.append(f"scheduled {entry}: {contract.reference} ({said}){keyed}")
    decided_start(state, name, step, entry, starting_rule(state, name, step))
    commands.append(Schedule(entry, contract.reference, inputs))
