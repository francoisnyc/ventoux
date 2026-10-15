"""Case validation: what can be proven about a case definition by reading it, before any case
opens (layer 10). See docs/layers/10-case-validation.md and docs/guides/cases.md.
"""

from ventoux.case.definition import CaseDefinition
from ventoux.case.reach import can_happen, reachable, reached_by, shortest_circle, waited_on
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
    return never_run(case)


def never_run(case: CaseDefinition) -> list[Issue]:
    """A step left out of what the case can ever reach can never run, on any path: one
    `DEADLOCK` for each group of steps that wait on each other, a `NEVER_RUNS` for any other."""
    can = can_happen(case)
    required = requirements(case)
    dead = [name for name in case.steps if name not in can]
    # The fixpoint leaves no step out whose requirements are all in: one of them isn't. Each dead
    # step waits on the first, and on the dead steps that could meet it.
    first = {name: next(r for r in required[name] if r not in can) for name in dead}
    waits = {name: waited_on(case, first[name]) for name in dead}
    found: list[Issue] = []
    in_a_circle: set[str] = set()
    for name in dead:
        if name in in_a_circle:
            continue  # one cause, one issue: its group's DEADLOCK names it
        circle = shortest_circle(name, waits)
        path = f"steps.{name}.requires"
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
