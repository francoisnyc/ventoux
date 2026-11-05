"""How a case that owes says so: in `waiting_for`, with who may start the owed step, or in
`needs_attention`, when nothing can start it any more (brief, D72).

What is owed is `owed.py`'s. This file reads it against the case as it is now: a step that can
still start waits, saying for what; one that can't needs a person, since only a person's close
ends it. Nothing starts that nobody asked for.
"""

from ventoux.case.admission import latest_counted, requirements_met
from ventoux.case.closing import close_held, needs_attention, pending
from ventoux.case.definition import CaseDefinition
from ventoux.case.owed import owed
from ventoux.case.reach import reached_by
from ventoux.case.sequence import requirements
from ventoux.case.state import CaseState

# A run in one of these is on its way, and shown by the case: open, running, failed or retried.
ON_ITS_WAY = ("open", "running", "failed", "retrying")


def waiting_for(case: CaseDefinition, state: CaseState) -> list[str]:
    """What the case waits for from people (brief, D24): each open entry, in the order it
    opened, then each owed step that can still start, with who may start it (brief, D72). A case
    closing or closed waits for nothing it owes: nothing starts any more."""
    lines = list(state.waiting.values())
    if state.phase != "open":
        return lines
    for name in owed(case, state):
        if on_its_way(state, name) or stranded(case, state, name) is not None:
            continue  # shown as its run, or in needs_attention
        if not requirements_met(requirements(case)[name], state):
            # Waiting for a requirement: said only once nothing else is pending, since before
            # then the case isn't waiting on it.
            if not pending(state):
                unmet = next(
                    r for r in requirements(case)[name] if not requirements_met((r,), state)
                )
                lines.append(f"{name}, required, after {unmet}")
            continue
        step = case.steps[name]
        if step.proposed_by:
            lines.append(f"{name}, required, proposed by {' or '.join(step.proposed_by)}")
        elif started_by_a_rule(case, name):
            lines.append(f"{name}, required, started by a rule")
    return lines


def attention(case: CaseDefinition, state: CaseState) -> list[str]:
    """What waits for an operator (brief, D17), then each owed step nothing can start any more,
    with why and the way out: only a person's close ends it (brief, D72)."""
    lines = needs_attention(state)
    if state.phase != "open":
        return lines
    for name in owed(case, state):
        if (why := stranded(case, state, name)) is not None:
            lines.append(
                f"{name}: required, and it can't start: {why}: close the case with a reason"
            )
    return lines


def stranded(
    case: CaseDefinition, state: CaseState, name: str, seen: frozenset[str] = frozenset()
) -> str | None:
    """Why the owed step `name` can never start now, or None if it still can: nothing can start
    it again; a step it requires ended and can't run again; or, while the close is held, a
    requirement is unmet with nothing on its way to meet it, since nothing else starts."""
    if on_its_way(state, name):
        return None
    held = close_held(case, state)
    if (why := cannot_start_again(case, state, name, held)) is not None:
        return why
    for requirement in requirements(case)[name]:
        if requirements_met((requirement,), state) or on_its_way(state, requirement):
            continue
        if requirement not in case.steps:
            if held and not reaching_on_its_way(case, state, requirement, seen | {name}):
                return f"{name} requires {requirement}, which hasn't been reached"
            continue  # a milestone something may still reach
        if held and not owed_and_able(case, state, requirement, seen | {name}):
            return f"{name} requires {requirement}, which hasn't completed"
        if not held and cannot_start_again(case, state, requirement, held) is not None:
            return f"{name} requires {requirement}, which hasn't completed"
    return None


def reaching_on_its_way(
    case: CaseDefinition, state: CaseState, milestone: str, seen: frozenset[str]
) -> bool:
    """Whether a step that reaches `milestone` is on its way: its run is under way (an open task
    answered, a running step completing, a failed one retried), or it is owed and can still start,
    since the held close lets it (brief, D72). `seen` guards a circle, as in `owed_and_able`."""
    return any(
        on_its_way(state, step) or owed_and_able(case, state, step, seen)
        for step in reached_by(case, milestone)
    )


def owed_and_able(
    case: CaseDefinition, state: CaseState, requirement: str, seen: frozenset[str]
) -> bool:
    """Whether `requirement` may still start under a held close: it is owed itself, so the close
    lets it start, and it isn't stranded. A step already asked about on the way (`seen`) counts
    as stranded, so a circle of requirements ends (brief, D72)."""
    if requirement in seen or requirement not in owed(case, state):
        return False
    return stranded(case, state, requirement, seen) is None


def cannot_start_again(case: CaseDefinition, state: CaseState, name: str, held: bool) -> str | None:
    """Why nothing can start the step `name` again, or None: it may start itself (once), a
    person may propose it, or a rule in the definition starts it, proven from the definition,
    never guessed (brief, D37). A step that has run starts again only if repeatable."""
    step = case.steps[name]
    latest = latest_counted(state, name)
    if latest is None and step.automatic:
        return None
    if latest is not None and not step.repeatable:
        return f"{name} has run, and is not repeatable"
    if step.proposed_by:
        return None
    if started_by_a_rule(case, name):
        # No rule acts while the close is held (brief, D34).
        return (
            f"{name} is started only by a rule, and no rule acts while the close is held"
            if held
            else None
        )
    return f"nothing can start {name} again"  # fail closed: no way to start it is a way out


def started_by_a_rule(case: CaseDefinition, name: str) -> bool:
    """Whether some rule in the definition starts the step, whatever its moment."""
    return any(name in rule.then.start for rule in case.rules.values())


def on_its_way(state: CaseState, step: str) -> bool:
    """Whether the step's latest run is under way, and so shown by the case already."""
    latest = latest_counted(state, step)
    return latest is not None and latest.status in ON_ITS_WAY
