"""The interpreter: runs a plan, state by state, and records what happened (layer 5).

Pure, like all of `ventoux.core`: no clock, no randomness, no I/O. See
docs/layers/05-interpreter.md.
"""

from collections import Counter
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field
from typing import Any, Literal

from pydantic import ValidationError

from ventoux.core.before_activity import InputRefused, checked_inputs, one_line
from ventoux.core.catalog import Catalog, NotInCatalog
from ventoux.core.expressions import Expression, ExpressionError, evaluate, render
from ventoux.core.form import form_problem
from ventoux.core.history import (
    Answered,
    Ended,
    Entered,
    Event,
    Gave,
    Moved,
    Refused,
    Scheduled,
    Started,
    Stopped,
    Waiting,
)
from ventoux.core.plan import (
    ActivityState,
    ApprovalState,
    FinalState,
    Plan,
    Transition,
    WaitState,
    asked,
    set_by,
)
from ventoux.core.plan import Wait as Question
from ventoux.core.provenance import CASE, Sourced, provenance
from ventoux.core.roles import no_role, role_that_counts

# How a run ends (docs/guides/plans.md, "Running a plan").
Status = Literal["succeeded", "failed", "waiting", "stopped"]


class RunRefused(ValueError):
    """A run that can't start: what is wrong, then what to do."""


# How the interpreter asks for an activity: its reference and inputs in, its output back. In tests a
# fake; on Temporal, `workflow.execute_activity` (layer 6). The interpreter calls nothing itself.
type Call = Callable[[str, dict[str, Any]], Awaitable[dict[str, Any]]]


@dataclass(frozen=True)
class Answer:
    """An answer to a wait: one of its outcomes from a person, or its timeout."""

    outcome: str  # what was answered, such as `approve`, or `timeout`
    by: str | None  # who answered; None for a timeout
    # The roles the person has, as the trusted caller states them; never looked up (brief, D22).
    roles: frozenset[str] = frozenset()
    form: Mapping[str, object] | None = None  # the values given with the outcome, if any


# How the interpreter waits: the state, the entry it waits in (`approve_refund#1`: the state and how
# many times the run has entered it), the outcomes it accepts and its timeout in; an answer back, or
# None when none will come. In tests a script; on Temporal, a signal or a timer (layer 6).
type Wait = Callable[[str, str, tuple[str, ...], str | None], Awaitable[Answer | None]]

# How many states a run may enter without a wait taking an answer. A count, never a clock, so
# replay decides the same way; past it, a plan looping on activities alone is stopped, not spun on.
ENTRIES_WITHOUT_A_WAIT = 1000

# The event of a wait's timeout, never one of its outcomes (layer 3's RESERVED_OUTCOME).
TIMEOUT = "timeout"


class Outcome(Exception):
    """Raised by an activity for one of the outcomes its contract declares, such as `declined`."""

    def __init__(self, name: str) -> None:
        super().__init__(name)
        self.name = name  # the outcome, as the contract declares it


class Stop(Exception):
    """Raised inside a step the engine won't go on with; the loop records it as `Stopped`."""


@dataclass
class PlanRun:
    """How a run ended, and what happened on the way."""

    status: Status | None = None  # None while it runs
    reason: str | None = None  # why it stopped, if it did
    history: list[Event] = field(default_factory=list[Event])  # every event, in order


async def interpret(
    plan: Plan,
    fields: Mapping[str, Sourced],
    catalog: Catalog,
    call: Call,
    wait: Wait,
    *,
    run_name: str,
    record: PlanRun | None = None,
) -> PlanRun:
    """Run `plan` from its `initial` state, with the `fields` the case gives it.

    `run_name` names this run in every idempotency key: on Temporal, the workflow's ID and run ID.
    It has no default: two runs sharing a name would share their keys (brief, D17).

    `record` is the run to write into, when the driver records events of its own in the same
    history: on Temporal, an answer refused because its wait isn't open.
    """
    refuse_to_start(plan, fields)
    run = PlanRun() if record is None else record
    run.history.append(Started(plan.plan, plan.version))
    # The run's fields: what the case gave, then what people's forms set (brief, D9).
    values = {name: given.value for name, given in fields.items()}
    # Where each value really came from, plus what the plan declared: a mark adds distrust, never
    # removes it (non-negotiables: stricter downstream, never looser).
    sources = {
        name: given.sources | ({plan.sources[name]} if name in plan.sources else set())
        for name, given in fields.items()
    }
    entries: Counter[str] = Counter()  # how many times the run has entered each state
    since_a_wait = 0  # states entered since a wait last took an answer
    here = plan.initial
    try:
        while run.status is None:
            if here not in plan.states:
                states = ", ".join(sorted(plan.states))
                raise Stop(f"{here} is not a state of {plan.plan}: the states are {states}")
            if since_a_wait >= ENTRIES_WITHOUT_A_WAIT:
                raise Stop(
                    f"entered {ENTRIES_WITHOUT_A_WAIT:,} states without waiting for anyone: a plan "
                    "that loops needs a wait or an end"
                )
            run.history.append(Entered(here))
            entries[here] += 1
            since_a_wait += 1
            state = plan.states[here]
            if isinstance(state, FinalState):
                run.history.append(Ended(state.final))
                run.status = "succeeded" if state.final == "succeeded" else "failed"
            elif isinstance(state, ActivityState):
                # The step's run: the run, the state, and how many times the run has entered it,
                # so a retry reuses the key and another pass or another run never does (brief, D17).
                key = f"{run_name}/{here}#{entries[here]}"
                gave = await run_activity(state, values, sources, key, catalog, call, run)
                run.history.append(gave)
                here = choose(here, state.on, gave.event, values)
                run.history.append(Moved(gave.event, here))
            elif isinstance(state, WaitState | ApprovalState):
                taken = await take_answer(
                    here, f"{here}#{entries[here]}", state, plan, catalog, wait, run
                )
                if taken is None:
                    run.status = "waiting"  # nothing more will come, for now
                    break
                answer, role = taken
                setting = asked(state).sets.get(answer.outcome, ())
                run.history.append(Answered(answer.outcome, answer.by, role, setting))
                # A form's values land in the run's fields, tagged with who answered (brief, D9);
                # the latest answer replaces an earlier pass's.
                for name in setting:
                    values[name] = (answer.form or {})[name]
                    sources[name] = frozenset({f"person:{answer.by}"})
                since_a_wait = 0  # someone answered: a loop through a wait isn't spinning
                here = choose(here, state.on, answer.outcome, values)
                run.history.append(Moved(answer.outcome, here))
            else:
                # Fail closed: a kind of state this loop has no case for stops the step, never
                # spun on or passed over. A new kind lands here until the loop says how it runs.
                kind = type(state).__name__
                raise Stop(f"{here} is a kind of state this engine doesn't know: {kind}")
    except Stop as stop:
        # Fail closed: the engine never guesses past what it can't do; a person decides
        # (brief, D17).
        run.history.append(Stopped(here, str(stop)))
        run.status, run.reason = "stopped", str(stop)
    return run


async def run_activity(
    state: ActivityState,
    values: Mapping[str, object],
    sources: Mapping[str, frozenset[str]],
    key: str,
    catalog: Catalog,
    call: Call,
    run: PlanRun,
) -> Gave:
    """Call the state's activity with its inputs, and say what it gave."""
    try:
        contract = catalog.get(state.activity)
    except NotInCatalog as missing:
        raise Stop(str(missing)) from None
    try:
        inputs = checked_inputs(contract, state.inputs, values, sources, key)
    except InputRefused as refused:
        raise Stop(str(refused)) from None
    found = {name: provenance(expression, sources) for name, expression in state.inputs.items()}
    run.history.append(Scheduled(contract.reference, inputs, found))
    try:
        output = await call(contract.reference, inputs)
    except Outcome as outcome:
        # A business failure is an outcome, and only those the contract declares (brief, D17).
        if outcome.name not in contract.outcomes:
            raise Stop(
                f"{contract.reference} gave the outcome {outcome.name}, which its contract "
                f"doesn't declare: its outcomes are {', '.join(contract.outcomes) or 'none'}"
            ) from None
        return Gave(contract.reference, outcome.name, None)
    # Every other failure, whatever its kind: none is read as an outcome or ignored; a person looks
    # at it (brief, D17).
    except Exception as error:  # noqa: BLE001 (catching every kind is the rule here)
        raise Stop(f"{contract.reference} failed: {error}") from None
    try:
        # Pydantic: `model_validate` checks a dict against the model's fields, or raises.
        contract.output.model_validate(output)
    except ValidationError as error:
        raise Stop(
            f"{contract.reference} gave an output its contract doesn't declare: {one_line(error)}"
        ) from None
    return Gave(contract.reference, "done", output)


async def take_answer(
    here: str,
    entry: str,
    state: WaitState | ApprovalState,
    plan: Plan,
    catalog: Catalog,
    wait: Wait,
    run: PlanRun,
) -> tuple[Answer, str | None] | None:
    """The first answer the state accepts, and the role that let its person answer; each one it
    doesn't accept is refused, and it waits on. A wait and an approval are asked the same way."""
    question = asked(state)
    of = state.approval.of if isinstance(state, ApprovalState) else None
    run.history.append(Waiting(entry, question.outcomes, question.roles, question.timeout, of))
    while (answer := await wait(here, entry, question.outcomes, question.timeout)) is not None:
        reason = why_not(here, question, answer)
        if reason is None and answer.by is not None:
            # Every answer is judged the same way, wait or approval (brief, D23).
            role = role_that_counts(question.roles, answer.roles, catalog.roles)
            sets = question.sets.get(answer.outcome, ())
            if role is None:
                reason = no_role(entry, question.roles, answer.by, answer.roles, catalog.roles)
            elif (
                problem := form_problem(answer.outcome, sets, answer.form, plan.fields)
            ) is not None:
                reason = problem
            else:
                return answer, role
        if reason is None:
            return answer, None  # the timeout, which no person gives
        run.history.append(Refused(answer.outcome, answer.by, reason))
    return None


def why_not(here: str, question: Question, answer: Answer) -> str | None:
    """Why the state won't take `answer`, or None if it will. Its outcomes are a closed list
    (brief, D9), and its timeout comes from its timer, never from a person."""
    if answer.outcome == TIMEOUT:
        if answer.by is not None:
            return "a timeout comes from the wait's timer, never from a person"
        if question.timeout is None:
            return f"{here} has no timeout"
        return None
    if answer.outcome not in question.outcomes:
        return f"{here} offers {' or '.join(question.outcomes)}"
    if answer.by is None:
        return "an answer comes from a person, and this one names nobody"
    return None


def choose(
    here: str,
    on: Mapping[str, tuple[Transition, ...]],
    event: str,
    values: Mapping[str, object],
) -> str:
    """Where `on` says to go from `here` on `event`: the first transition that holds."""
    # Fail closed: an event the plan doesn't handle is never read as "stay" or "end".
    if event not in on:
        raise Stop(f"on {event}, {here} says nowhere to go")
    for transition in on[event]:
        if transition.when is None or holds(transition.when, event, values):
            return transition.target
    raise Stop(f"on {event}, no transition holds")


def holds(when: Expression, event: str, values: Mapping[str, object]) -> bool:
    """Whether the condition `when` is true. Fail closed: a condition that can't be evaluated
    stops the step, and the next transition is never tried (it may skip an approval)."""
    try:
        decided = evaluate(when, values)
    except ExpressionError as error:
        raise Stop(f"on {event}, {render(when)} can't be evaluated: {error}") from None
    # Nothing is truthy: anything but true or false stops the step, never read as false.
    if not isinstance(decided, bool):
        raise Stop(
            f"on {event}, the condition {render(when)} gives {decided!r}: a condition gives true "
            "or false"
        )
    return decided


def refuse_to_start(plan: Plan, fields: Mapping[str, Sourced]) -> None:
    """Refuse a run not given exactly the plan's fields a person doesn't set, each saying where
    its value came from."""
    setters = set_by(plan)
    given_at_start = [name for name in plan.fields if name not in setters]
    declared = ", ".join(sorted(given_at_start))
    problems = [
        f"{name} is missing: give every field the plan declares ({declared})"
        for name in given_at_start
        if name not in fields
    ]
    for name, given in fields.items():
        if name not in plan.fields:
            problems.append(f"{name} is not a field of {plan.plan}: its fields are {declared}")
        # One source per field: a person's form sets it, so the case never gives it.
        elif name in setters:
            problems.append(
                f"{name} is set by a person in {setters[name]}, never given at the start"
            )
        # Fail closed: no sources would read as a value written in the plan, which policies trust.
        elif not given.sources:
            problems.append(
                f"{name} comes with no sources: say where its value came from, such as "
                "system:opener"
            )
        # `case` is the static check's stand-in for "the case vouches for it", never an origin:
        # accepted here, it would pass `trusted_only` on the case's word
        # (docs/layers/05-interpreter.md).
        elif CASE in given.sources:
            problems.append(
                f"{name} comes from case, which only the static check uses: give the source its "
                "value really came from"
            )
    if problems:
        raise RunRefused("\n".join(problems))
