"""Static validation: what can be proven about a plan by reading it, before anything runs.

`parse_plan` checks a plan's shape; `validate` checks its meaning, reading the plan as a graph whose
arrows are the transitions in each state's `on`. It lists every problem at once. See
docs/guides/plans.md.
"""

from collections.abc import Mapping
from dataclasses import dataclass

from ventoux.core.catalog import Catalog, NotInCatalog
from ventoux.core.contract import ActivityContract
from ventoux.core.expressions import (
    BooleanType,
    Expression,
    ExpressionInvalid,
    FieldType,
    check,
)
from ventoux.core.expressions.check import a_type
from ventoux.core.graph import Arrow, arrows, reach, shortest_path
from ventoux.core.plan import ActivityState, FinalState, Plan, Transition, WaitState, set_by
from ventoux.core.policy import OnlyFrom, Policy, refusal
from ventoux.core.provenance import CASE, answering, provenance

TIMEOUT = "timeout"  # the event of a wait's timeout, so never one of its outcomes
# An approval is a wait offering exactly these two outcomes; `approve` is reserved for it
# (brief, D11).
APPROVE, REJECT = "approve", "reject"


@dataclass(frozen=True)
class Issue:
    """One problem in a plan: where it is, which kind it is, and what to do about it."""

    path: str  # where in the plan, as layer 2 writes it: `states.pay.on.done[1]`
    code: str  # which rule it breaks, such as `UNKNOWN_TARGET`
    message: str  # what is wrong, then what to do


def validate(plan: Plan, catalog: Catalog) -> list[Issue]:
    """Every problem in `plan`, a parsed plan, read against the activities in `catalog`."""
    # Fail closed: anything but a parsed plan is refused, never read as a plan with no problems.
    if not isinstance(plan, Plan):
        raise TypeError(f"validate takes a parsed plan (see parse_plan), not {type(plan).__name__}")
    issues: list[Issue] = source_issues(plan, catalog)
    if plan.initial not in plan.states:
        issues.append(Issue("initial", "UNKNOWN_TARGET", not_a_state(plan.initial, plan)))
    for name, state in plan.states.items():
        if isinstance(state, FinalState):
            continue  # a final state has no `on`: nowhere to go
        if isinstance(state, ActivityState):
            issues += activity_issues(f"states.{name}", state, catalog)
            for field, expression in state.inputs.items():
                path = f"states.{name}.inputs.{field}"
                problems = expression_issues(path, expression, plan.fields)
                # One cause, one issue: an input whose expression is refused isn't asked where its
                # value comes from.
                issues += problems or policy_issues(path, field, expression, state, plan, catalog)
        else:
            issues += wait_issues(f"states.{name}", name, state)
            issues += role_issues(f"states.{name}.wait.roles", state.wait.roles, catalog)
            issues += sets_issues(f"states.{name}.wait.sets", name, state, plan)
        for event, transitions in state.on.items():
            for path, transition in each_transition(f"states.{name}.on.{event}", transitions):
                if transition.target not in plan.states:
                    issues.append(
                        Issue(path, "UNKNOWN_TARGET", not_a_state(transition.target, plan))
                    )
                if transition.when is not None:
                    issues += expression_issues(
                        f"{path}.when", transition.when, plan.fields, condition=True
                    )
    return issues + graph_issues(plan, catalog)


def source_issues(plan: Plan, catalog: Catalog) -> list[Issue]:
    """Every declared source's label is one the platform team registered (brief, D12)."""
    issues = []
    for field, source in plan.sources.items():
        label = source.removeprefix("untrusted:")  # parse_plan let only `untrusted:` through
        if label not in catalog.labels:
            issues.append(
                Issue(
                    f"fields.{field}.source",
                    "UNKNOWN_SOURCE",
                    f"{source} has a label nobody registered: the labels are "
                    f"{', '.join(catalog.labels)}; use one of them, or ask the platform team to "
                    "register it",
                )
            )
    return issues


def role_issues(path: str, roles: tuple[str, ...], catalog: Catalog) -> list[Issue]:
    """Every role a wait names is one the platform team registered (brief, D22)."""
    return [
        Issue(
            path,
            "UNKNOWN_ROLE",
            f"{role} is a role nobody registered: the roles are {', '.join(catalog.roles)}; use "
            "one of them, or ask the platform team to register it",
        )
        for role in roles
        if role not in catalog.roles
    ]


def sets_issues(path: str, name: str, state: WaitState, plan: Plan) -> list[Issue]:
    """Each outcome a form is for is one the wait offers, and each field it sets is declared."""
    issues: list[Issue] = []
    for outcome, fields in state.wait.sets.items():
        if outcome not in state.wait.outcomes:
            issues.append(
                Issue(
                    f"{path}.{outcome}",
                    "UNKNOWN_EVENT",
                    f"the wait {name} never gives {outcome}: its outcomes are "
                    f"{', '.join(state.wait.outcomes)}",
                )
            )
        for field in fields:
            if field not in plan.fields:
                issues.append(
                    Issue(
                        f"{path}.{outcome}",
                        "UNKNOWN_FIELD",
                        f"{name}'s {outcome} sets {field}, which is not a field: the fields are "
                        f"{', '.join(sorted(plan.fields))}",
                    )
                )
    return issues


def policy_issues(
    path: str,
    field: str,
    expression: Expression,
    state: ActivityState,
    plan: Plan,
    catalog: Catalog,
) -> list[Issue]:
    """The input's value against each input policy on it: where it may come from (brief, D21)."""
    try:
        contract = catalog.get(state.activity)
    except NotInCatalog:
        return []  # no contract, no policy to read: already UNKNOWN_ACTIVITY
    # Each field's sources as the plan knows them: what it declared, or else the case's, which the
    # runtime checks again with the real sources before the activity runs (core/before_activity.py).
    # A field a person sets comes from whoever answers that wait: trusted, from no system.
    setters = set_by(plan)
    sources = {
        name: frozenset({answering(setters[name])})
        if name in setters
        else frozenset({plan.sources.get(name, CASE)})
        for name in plan.fields
    }
    found = provenance(expression, sources)
    issues = []
    for policy in contract.policies(field):
        if policy.refuses(found) is not None:
            issues.append(
                Issue(
                    path,
                    "INPUT_POLICY",
                    f"{refusal(contract.reference, field, policy, expression, sources)}: "
                    f"{what_to_do(policy)}",
                )
            )
    return issues


def what_to_do(policy: Policy) -> str:
    """What the plan's author can do about a refused input."""
    if isinstance(policy, OnlyFrom):
        # A plan only sees `case` for a field it is given: it can't tell which system it came from.
        return "a plan can't show which system a value came from, so give this input in a case step"
    return "use a value a system or a person gave"


def activity_issues(path: str, state: ActivityState, catalog: Catalog) -> list[Issue]:
    """What is wrong with an activity state, read against its contract in the catalog."""
    try:
        contract = catalog.get(state.activity)
    except NotInCatalog as missing:
        # The catalog's own message, which names the versions it does hold.
        return [Issue(f"{path}.activity", "UNKNOWN_ACTIVITY", str(missing))]
    # An activity gives `done`, or one of the business failures its contract declares (brief, D17).
    # Anything else that goes wrong needs a person, never a transition the plan takes on its own.
    events = ("done", *contract.outcomes)
    return input_issues(path, state, contract) + event_issues(
        path, state.on, events, gives=f"{contract.reference} never gives"
    )


def wait_issues(path: str, name: str, state: WaitState) -> list[Issue]:
    """What is wrong with a wait state: its outcomes, and the events its `on` handles."""
    issues: list[Issue] = []
    if TIMEOUT in state.wait.outcomes:
        issues.append(
            Issue(
                f"{path}.wait.outcomes",
                "RESERVED_OUTCOME",
                f"{TIMEOUT} is the event of a wait's timeout, not an outcome: "
                "name the outcome differently",
            )
        )
    if APPROVE in state.wait.outcomes and not is_approval(state):
        issues.append(
            Issue(
                f"{path}.wait.outcomes",
                "APPROVAL_OUTCOMES",
                f"a wait offering {APPROVE} is an approval, and offers exactly {APPROVE} and "
                f"{REJECT}; this one offers {', '.join(state.wait.outcomes)}: use another word "
                f"than {APPROVE}",
            )
        )
    # A wait gives one of its outcomes, or `timeout` when it declares one.
    timed = (
        (TIMEOUT,) if state.wait.timeout is not None and TIMEOUT not in state.wait.outcomes else ()
    )
    events = (*state.wait.outcomes, *timed)
    hint = "" if timed else f"; declare wait.timeout to wait for {TIMEOUT}"
    return issues + event_issues(
        path, state.on, events, gives=f"the wait {name} never gives", timeout_hint=hint
    )


def event_issues(
    path: str,
    on: Mapping[str, object],
    events: tuple[str, ...],
    gives: str,
    timeout_hint: str = "",
) -> list[Issue]:
    """`on` against the events a state can give: each handled, and nothing else."""
    issues: list[Issue] = []
    for event in on:
        if event not in events:
            hint = timeout_hint if event == TIMEOUT else ""
            issues.append(
                Issue(
                    f"{path}.on.{event}",
                    "UNKNOWN_EVENT",
                    f"{gives} {event}: its events are {', '.join(events)}{hint}",
                )
            )
    for event in events:
        if event not in on:
            issues.append(
                Issue(
                    f"{path}.on",
                    "MISSING_EVENT",
                    f"{event} is not handled: say where the plan goes on {event}",
                )
            )
    return issues


def input_issues(path: str, state: ActivityState, contract: ActivityContract) -> list[Issue]:
    """The state's inputs against the contract's input fields, the idempotency key aside."""
    issues: list[Issue] = []
    key = contract.idempotency_key
    # The engine fills the key, from the case, the step and its run, so retries reuse it and two
    # runs never share it (brief, D17). A plan may neither set it nor be asked for it.
    fields = {name: field for name, field in contract.input.model_fields.items() if name != key}
    for name in state.inputs:
        if name == key:
            issues.append(
                Issue(
                    f"{path}.inputs.{name}",
                    "ENGINE_INPUT",
                    f"{name} is filled by the engine, never by a plan: remove it",
                )
            )
        elif name not in fields:
            issues.append(
                Issue(
                    f"{path}.inputs.{name}",
                    "UNKNOWN_INPUT",
                    f"{contract.reference} has no input {name}: its inputs are "
                    f"{', '.join(sorted(fields))}",
                )
            )
    for name, field in fields.items():
        # Pydantic: `is_required()` is true for a field declared with no default.
        if field.is_required() and name not in state.inputs:
            issues.append(
                Issue(
                    f"{path}.inputs",
                    "MISSING_INPUT",
                    f"{contract.reference} needs the input {name}: add it to inputs",
                )
            )
    return issues


def expression_issues(
    path: str, expression: Expression, fields: Mapping[str, FieldType], condition: bool = False
) -> list[Issue]:
    """An expression checked against the plan's fields (layer 2's `check`); a condition must give a
    boolean. A plan binds no new values, so the fields are the same at every state."""
    try:
        found = check(expression, fields)
    except ExpressionInvalid as refused:
        # The check's own message, which starts with the path inside the expression (`>[1]`).
        return [Issue(path, "EXPRESSION_INVALID", str(refused))]
    if condition and not isinstance(found, BooleanType):
        # Nothing is truthy: a condition gives true or false, never a number read as one.
        return [
            Issue(
                path,
                "EXPRESSION_INVALID",
                f"a condition gives a boolean, and this gives {a_type(found)}: write a comparison, "
                "such as amount > 100",
            )
        ]
    return []


def graph_issues(plan: Plan, catalog: Catalog) -> list[Issue]:
    """What reading the plan as a graph proves: every state reachable, the plan able to end, and
    every high-risk activity behind an approval."""
    if plan.initial not in plan.states:
        return []  # already an issue; with no start, reachability would only repeat it
    issues: list[Issue] = []
    every = arrows(plan)
    reachable = reach({plan.initial}, every)
    finals = {name for name, state in plan.states.items() if isinstance(state, FinalState)}
    can_end = reach(finals, every, backwards=True)
    for name in plan.states:
        if name not in reachable:
            issues.append(
                Issue(
                    f"states.{name}",
                    "UNREACHABLE_STATE",
                    f"no path from {plan.initial} reaches {name}: "
                    "remove it, or add a transition to it",
                )
            )
        elif name not in can_end:
            # Only reachable states: an unreachable one is already an issue.
            issues.append(
                Issue(
                    f"states.{name}",
                    "NO_PATH_TO_FINAL",
                    f"the plan can never end from {name}: add a path to a final state",
                )
            )
    return issues + approval_issues(plan, catalog, every)


def is_approval(state: object) -> bool:
    """Whether `state` is an approval: a wait offering exactly `approve` and `reject` (brief, D11).
    A wait offering `approve` with anything else is an issue, and approves nothing (fail closed)."""
    return isinstance(state, WaitState) and sorted(state.wait.outcomes) == [APPROVE, REJECT]


def is_high_risk(state: object, catalog: Catalog) -> bool:
    """Whether `state` calls a high-risk activity. One the catalog doesn't hold is already an issue
    (UNKNOWN_ACTIVITY), so it adds no approval issue of its own."""
    if not isinstance(state, ActivityState):
        return False
    try:
        return catalog.get(state.activity).risk == "high"
    except NotInCatalog:
        return False


def approval_issues(plan: Plan, catalog: Catalog, every: list[Arrow]) -> list[Issue]:
    """Every high-risk activity behind an approval, on every path from `initial`."""
    # Follow every arrow except an approval's `approve`: what is reached this way runs unapproved.
    unapproved = [
        a for a in every if not (a.event == APPROVE and is_approval(plan.states[a.source]))
    ]
    reached = reach({plan.initial}, unapproved)
    issues: list[Issue] = []
    for name, state in plan.states.items():
        if name in reached and isinstance(state, ActivityState) and is_high_risk(state, catalog):
            path = " → ".join(shortest_path(plan.initial, name, unapproved))
            issues.append(
                Issue(
                    f"states.{name}",
                    "APPROVAL_REQUIRED",
                    f"{state.activity} is high risk, and {path} reaches it without an approval: "
                    f"route every path to {name} through an approval",
                )
            )
    # One approval unlocks one run (brief, D11): after a high-risk activity, any high-risk activity
    # reached without passing an approval, itself again in a loop included, would run on the
    # approval already spent.
    for name, state in plan.states.items():
        if not is_high_risk(state, catalog):
            continue
        after = reach({a.target for a in unapproved if a.source == name}, unapproved)
        again = [
            n for n, other in plan.states.items() if n in after and is_high_risk(other, catalog)
        ]
        if again:
            issues.append(
                Issue(
                    f"states.{name}",
                    "APPROVAL_REUSED",
                    f"one approval would unlock two high-risk runs: after {name}, "
                    f"{', '.join(again)} can run without a new approval: add an approval before "
                    f"{', '.join(again)}",
                )
            )
    return issues


def each_transition(path: str, transitions: tuple[Transition, ...]) -> list[tuple[str, Transition]]:
    """Each transition with its path: `on.done` when it was written as a bare state name, else
    `on.done[1]` by its position in the list."""
    if len(transitions) == 1 and transitions[0].when is None:
        return [(path, transitions[0])]
    return [(f"{path}[{position}]", t) for position, t in enumerate(transitions)]


def not_a_state(name: str, plan: Plan) -> str:
    return f'"{name}" is not a state: the states are {", ".join(sorted(plan.states))}'
