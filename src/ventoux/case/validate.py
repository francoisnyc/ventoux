"""Case validation: what can be proven about a case definition by reading it, before any case
opens (layer 10). See docs/layers/10-case-validation.md and docs/guides/cases.md.
"""

from ventoux.case.definition import CaseDefinition
from ventoux.case.reach import can_happen, reached_by
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
    """A step left out of what the case can ever reach can never run, on any path."""
    can = can_happen(case)
    required = requirements(case)
    found: list[Issue] = []
    for name in case.steps:
        if name in can:
            continue
        # The fixpoint leaves no step out whose requirements are all in: one of them isn't.
        waits_on = next(r for r in required[name] if r not in can)
        found.append(Issue(f"steps.{name}.requires", "NEVER_RUNS", why_never(case, name, waits_on)))
    return found


def why_never(case: CaseDefinition, name: str, waits_on: str) -> str:
    """Why the step `name` can never run: the first of its requirements that can't be met."""
    if waits_on in case.milestones and not reached_by(case, waits_on):
        return (
            f"{name} can never run: it requires {waits_on}, which no step reaches: reach "
            f"{waits_on} from a step, or remove the requirement"
        )
    # Fail closed before it is refined: a dead step is always reported, whatever its cause.
    return f"{name} can never run: it requires {waits_on}, which can never happen"
