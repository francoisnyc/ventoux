"""Checking a definition's assignment rules before anything runs (layer 17c).

A rule names who is asked when an entry opens (brief, D71). Validation refuses only what holds for
every case (brief, D37): an approval's rule that can only pick someone who may never approve it,
or that no one can follow. What may hold is a warning. See docs/layers/17-assignment.md (17c).
"""

from ventoux.case.definition import Assign, CallStep, CaseDefinition, TaskStep
from ventoux.case.guards import excluded, excluded_every_time
from ventoux.case.sequence import requirements
from ventoux.core.catalog import Catalog
from ventoux.core.provenance import answering
from ventoux.core.validate import Issue


def assignment_issues(case: CaseDefinition, catalog: Catalog) -> list[Issue]:
    """What every rule asks that can never be followed (errors), or may not be (warnings)."""
    issues: list[Issue] = []
    for name, step in case.steps.items():
        if isinstance(step, TaskStep) and step.assign is not None:
            issues += nobody_issues(case, f"steps.{name}.assign", name, step.assign)
        if isinstance(step, CallStep) and step.approval is not None and step.approval.assign:
            issues += approval_issues(case, catalog, name, step)
    return issues


def approval_issues(
    case: CaseDefinition, catalog: Catalog, name: str, step: CallStep
) -> list[Issue]:
    """An approval's rule: one no one can follow, or one picking someone it excludes."""
    assert step.approval is not None and step.approval.assign is not None
    rule, path = step.approval.assign, f"steps.{name}.approval.assign"
    # Nobody holds an entry collecting several people's approvals (brief, D47) (brief, D69), so
    # the rule could never be followed: that is the cause, said alone.
    if (count := step.approval.count) > 1:
        several = (
            f"{name}'s approval needs {count} people, so nobody holds it and a rule can't ask "
            "one; remove the rule, or its count"
        )
        return [Issue(path, "ASSIGNS_SEVERAL", several)]
    if (never := always_excluded(case, name, step, rule)) is not None:
        return [Issue(path, "ASSIGNS_EXCLUDED", never)]
    issues: list[Issue] = []
    if rule.step is not None and answering(rule.step) in excluded(case, step, catalog):
        why = (
            f"whoever answered {rule.step} may be excluded from approving {name}: their answer "
            f"can reach what {name} reads; then the approval goes to its queue"
        )
        issues.append(Issue(path, "ASSIGNS_MAY_BE_EXCLUDED", why, "warning"))
    return issues + nobody_issues(case, path, name, rule)


def always_excluded(case: CaseDefinition, name: str, step: CallStep, rule: Assign) -> str | None:
    """Why whoever the rule picks can never approve the step `name`, or None if that isn't proven.
    The opener approves none of a case's steps (brief, D11); whoever answered a task whose outcome
    the step reads is excluded in every run, as the semantic diff proves it (brief, D55)."""
    if rule.to == "opener":
        return (
            "whoever opened the case approves none of its steps; leave the approval to its queue, "
            "or ask whoever answered a task"
        )
    assert rule.step is not None  # `answered` names its task, checked when the definition is read
    if answering(rule.step) in excluded_every_time(case, step):
        return (
            f"whoever answered {rule.step} is excluded from approving {name} in every run, since "
            f"{name} reads {rule.step}.outcome; leave the approval to its queue, or ask whoever "
            "answered another task"
        )
    return None


def nobody_issues(case: CaseDefinition, path: str, name: str, rule: Assign) -> list[Issue]:
    """A rule asking whoever answered a task the step doesn't require, directly or through what it
    requires: it may not have been answered when the entry opens. Said, never refused."""
    if rule.step is None or rule.step in required_before(case, name):
        return []
    why = (
        f"{name} doesn't require {rule.step}, so it may not have been answered when {name} "
        f"opens; then {name} goes to its queue"
    )
    return [Issue(path, "MAY_ASSIGN_NOBODY", why, "warning")]


def required_before(case: CaseDefinition, name: str) -> set[str]:
    """Every step `name` requires, directly or through the steps it requires."""
    direct = requirements(case)
    found: set[str] = set()
    waiting = list(direct.get(name, ()))
    while waiting:
        here = waiting.pop()
        if here not in found:
            found.add(here)
            waiting += direct.get(here, ())
    return found
