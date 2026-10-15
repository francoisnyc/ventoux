"""Case validation: what can be proven about a case definition by reading it, before any case
opens (layer 10). See docs/layers/10-case-validation.md and docs/guides/cases.md.
"""

from ventoux.case.definition import CaseDefinition
from ventoux.case.reach import (
    Through,
    can_happen,
    can_start,
    reachable,
    reached_before,
    reached_by,
    shortest_circle,
    waited_on,
)
from ventoux.case.runtime import listed
from ventoux.case.sequence import requirements
from ventoux.core.catalog import Catalog
from ventoux.core.validate import Issue


def validate_case(case: CaseDefinition, catalog: Catalog) -> list[Issue]:
    """Every problem in `case`, a parsed case definition, read against `catalog`."""
    # Fail closed: anything but a parsed definition is refused, never read as one with no problems.
    if not isinstance(case, CaseDefinition):
        raise TypeError(
            f"validate_case takes a parsed case definition (see parse_case), not "
            f"{type(case).__name__}"
        )
    can = can_happen(case, catalog)
    found: list[Issue] = []
    # Steps the structure lets run are still kept out if the case closes when it opens. If every
    # step is dead anyway, their own issues say why: one cause, one issue.
    if closes_at_opening(case) and any(name in can for name in case.steps):
        found.append(
            Issue(
                "steps",
                "CLOSES_AT_OPENING",
                f"nothing starts by itself when {case.case} opens, so it closes at once and every "
                "proposal is refused: let a step start by itself with nothing required, or add "
                "stays_open",
            )
        )
    found += never_run(case, catalog, can) + never_closes(case, catalog, can)
    return found + close_unreachable(case, can) + unreachable_milestones(case)


def unreachable_milestones(case: CaseDefinition) -> list[Issue]:
    """A milestone no step or outcome reaches: a warning, since nothing waits for it. One a step
    requires is said by that step's issue, one in `closes_when` by its own: one cause, one issue."""
    required = {r for step_requires in requirements(case).values() for r in step_requires}
    return [
        Issue(
            f"milestones.{name}",
            "UNREACHABLE_MILESTONE",
            f"no step reaches {name}: reach it from a step or an outcome, or remove it",
            "warning",
        )
        for name in case.milestones
        if not reached_by(case, name) and name not in required and name not in case.closes_when
    ]


def close_unreachable(case: CaseDefinition, can: set[str]) -> list[Issue]:
    """A `closes_when` milestone that can never be reached: a warning, as the case still closes
    another way (brief, D10)."""
    unreached = [name for name in case.closes_when if name not in can]
    if not unreached:
        return []
    if len(unreached) == 1:
        fix = f"reach {unreached[0]} from a step that can run, or remove it from closes_when"
    else:
        fix = "reach them from steps that can run, or remove them from closes_when"
    # How it closes instead: by a person only, if it stays open.
    if case.stays_open:
        instead = "only a person can close it"
    else:
        instead = "it closes when nothing is left to do"
    return [
        Issue(
            "closes_when",
            "CLOSE_UNREACHABLE",
            f"{listed(unreached)} can never be reached, so closes_when never closes {case.case}, "
            f"and {instead}: {fix}",
            "warning",
        )
    ]


def never_closes(case: CaseDefinition, catalog: Catalog, can: set[str]) -> list[Issue]:
    """A case that stays open closes when a person closes it with a reason, or by `closes_when`,
    which closes it too (layer 8b). If no reason names a registered role and `closes_when` can
    never be met, nobody ever can (brief, D10). A role nobody registered counts for nothing
    (brief, D22)."""
    closers = {role for reason in case.close_reasons.values() for role in reason.roles}
    if not case.stays_open or closers & set(catalog.roles):
        return []
    if case.closes_when and all(name in can for name in case.closes_when):
        return []  # closes_when closes it
    return [
        Issue(
            "close_reasons",
            "NEVER_CLOSES",
            f"{case.case} stays open, no close reason names a registered role, and closes_when "
            "never closes it, so nobody could ever close it: name a registered role in a close "
            "reason",
        )
    ]


def closes_at_opening(case: CaseDefinition) -> bool:
    """Whether the case closes the moment it opens: nothing is reached yet, so only a step that
    starts by itself with nothing required can start, and with none, nothing is pending
    (brief, D10). A case that stays open waits for a person instead."""
    required = requirements(case)
    return not case.stays_open and not any(
        step.automatic and not required[name] for name, step in case.steps.items()
    )


def never_run(case: CaseDefinition, catalog: Catalog, can: set[str]) -> list[Issue]:
    """A step left out of `can`, what the case can ever reach, can never run, on any path: one
    `DEADLOCK` for each group of steps that wait on each other, a `NEVER_RUNS` for any other."""
    required = requirements(case)
    dead = [name for name in case.steps if name not in can]
    # A dead step with a requirement that can't be met waits on the first such, and on the dead
    # steps that could meet it. One whose requirements can all be met was kept out by the close.
    # A step nobody can start waits on nothing: its roles are the cause.
    first = {
        name: unmet[0]
        for name in dead
        if can_start(case.steps[name], catalog.roles)
        and (unmet := [r for r in required[name] if r not in can])
    }
    waits = {name: waited_on(case, first[name]) if name in first else [] for name in dead}
    found: list[Issue] = []
    in_a_circle: set[str] = set()
    for name in dead:
        if name in in_a_circle:
            continue  # one cause, one issue: its group's DEADLOCK names it
        path = f"steps.{name}.requires"
        if not can_start(step := case.steps[name], catalog.roles):
            roles = ", ".join(step.proposed_by)
            found.append(
                Issue(
                    f"steps.{name}.proposed_by",
                    "NEVER_RUNS",
                    f"{name} can never run: it starts only when proposed, and none of its "
                    f"proposed_by roles ({roles}) is registered: name a registered role",
                )
            )
            continue
        if name not in first:
            found.append(Issue(path, "NEVER_RUNS", after_close(case, catalog, name)))
            continue
        circle = shortest_circle(name, waits)
        if circle is None:
            found.append(Issue(path, "NEVER_RUNS", why_never(case, name, first[name])))
            continue
        # Its group: the steps it waits on that wait on it in turn.
        in_a_circle |= {name} | {
            other for other in reachable(name, waits) if name in reachable(other, waits)
        }
        found.append(Issue(path, "DEADLOCK", deadlock(case, circle, first)))
    return found


def deadlock(case: CaseDefinition, circle: list[str], first: dict[str, str]) -> str:
    """The steps of `circle` (its first step at both ends), and what each waits on in turn."""
    steps = circle[:-1]
    if len(steps) == 1:
        who, fix = f"{steps[0]} waits on itself", "remove this requirement"
    else:
        who, fix = f"{listed(steps)} wait on each other", "remove one of these requirements"
    hops = [waiting(case, name, first[name]) for name in steps]
    return f"{who}: {'; '.join(hops)}: {fix}"


def waiting(case: CaseDefinition, name: str, requirement: str) -> str:
    """One step waiting on the next: `pay requires assessed, which only assess reaches`."""
    if requirement in case.steps:
        # A requirement the step doesn't write itself comes from `sequence`.
        if requirement not in case.steps[name].requires:
            return f"{name} comes after {requirement} in sequence"
        return f"{name} requires {requirement}"
    reachers = reached_by(case, requirement)
    reach = "reaches" if len(reachers) == 1 else "reach"
    return f"{name} requires {requirement}, which only {listed(reachers)} {reach}"


def after_close(case: CaseDefinition, catalog: Catalog, name: str) -> str:
    """Why a step whose requirements can all be met still never runs: before it can start, every
    milestone `closes_when` names is reached, and nothing new starts once they are. Says which it
    requires itself and which the steps it waits for reach, naming those steps."""
    before = reached_before(case, catalog, name)
    written = [m for m in case.closes_when if before[m] is None]
    reached = [m for m in case.closes_when if before[m] is not None]
    steps = list(dict.fromkeys(by[0] for m in reached if (by := before[m]) is not None))
    once = f"{case.closes_when[0]} is" if len(case.closes_when) == 1 else "they are"
    waits = []
    if written:
        waits.append(f"requires {listed(written)}")
    if steps:
        waits.append(
            f"runs only after {joined([through(before, step, reached) for step in steps])}"
        )
    # A fix that names one thing to change only where changing it would let the step run.
    if len(written) > 1 and not steps:
        # Removing one from closes_when would leave the step requiring another, which still
        # closes the case: only its requires can change.
        fix = "remove one of them from its requires"
    elif not steps:
        fix = f"remove {written[0]} from its requires, or from closes_when"
    elif len(steps) == 1 and not written:
        fix = f"run {name} before {steps[0]}, or remove {listed(reached)} from closes_when"
    else:
        fix = "change what it requires, or closes_when"
    return (
        f"{name} can never run: it {' and '.join(waits)}, and {case.case} closes once {once} "
        f"reached, before {name} could start: {fix}"
    )


def through(before: dict[str, Through | None], step: str, milestones: list[str]) -> str:
    """How the waited-for `step` makes some of `milestones` sure: `notify, which requires paid and
    reaches notified`."""
    required = [m for m in milestones if before[m] == (step, "requires")]
    reached = [m for m in milestones if before[m] == (step, "reaches")]
    parts = [f"requires {listed(required)}"] if required else []
    if reached:
        parts.append(f"reaches {listed(reached)}")
    return f"{step}, which {' and '.join(parts)}"


def joined(clauses: list[str]) -> str:
    """Clauses that hold commas themselves, joined so each stays apart: `a, …, and b, …`."""
    return clauses[0] if len(clauses) == 1 else f"{', '.join(clauses[:-1])}, and {clauses[-1]}"


def why_never(case: CaseDefinition, name: str, waits_on: str) -> str:
    """Why the step `name` can never run: the first of its requirements that can't be met."""
    if waits_on in case.steps:
        return (
            f"{name} can never run: it requires {waits_on}, which can never run: fix {waits_on} "
            "first"
        )
    reachers = reached_by(case, waits_on)
    if not reachers:
        return (
            f"{name} can never run: it requires {waits_on}, which no step reaches: reach "
            f"{waits_on} from a step, or remove the requirement"
        )
    # Every step reaching a milestone nothing can reach can never run itself.
    one = len(reachers) == 1
    reach, they = ("reaches", reachers[0]) if one else ("reach", "they")
    return (
        f"{name} can never run: it requires {waits_on}, which only {listed(reachers)} {reach}, "
        f"and {they} can never run: fix {reachers[0]} first"
    )
