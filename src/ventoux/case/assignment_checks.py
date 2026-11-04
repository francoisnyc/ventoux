"""Checking a definition's assignment rules before anything runs (layer 17c).

A rule names who is asked when an entry opens (brief, D71). Validation refuses only what holds for
every case (brief, D37): an approval's rule that can only pick someone who may never approve it.
What may hold is a warning. See docs/layers/17-assignment.md (17c).
"""

from ventoux.case.definition import CallStep, CaseDefinition
from ventoux.case.guards import excluded_every_time
from ventoux.core.provenance import answering
from ventoux.core.validate import Issue


def assignment_issues(case: CaseDefinition) -> list[Issue]:
    """Every approval's rule that can never be followed: on an approval needing several people,
    or picking someone it excludes in every run."""
    issues: list[Issue] = []
    for name, step in case.steps.items():
        if not isinstance(step, CallStep) or step.approval is None:
            continue
        rule = step.approval.assign
        if rule is None:
            continue
        path = f"steps.{name}.approval.assign"
        # Nobody holds an entry collecting several people's approvals (brief, D47) (brief, D69),
        # so the rule could never be followed: that is the cause, said alone.
        if (count := step.approval.count) > 1:
            issues.append(
                Issue(
                    path,
                    "ASSIGNS_SEVERAL",
                    f"{name}'s approval needs {count} people, so nobody holds it and a rule "
                    "can't ask one; remove the rule, or its count",
                )
            )
        elif (why := always_excluded(case, name, step, rule.to, rule.step)) is not None:
            issues.append(Issue(path, "ASSIGNS_EXCLUDED", why))
    return issues


def always_excluded(
    case: CaseDefinition, name: str, step: CallStep, to: str, task: str | None
) -> str | None:
    """Why whoever the rule picks can never approve the step `name`, or None if that isn't proven.
    The opener approves none of a case's steps (brief, D11); whoever answered a task whose outcome
    the step reads is excluded in every run, as the semantic diff proves it (brief, D55)."""
    if to == "opener":
        return (
            "whoever opened the case approves none of its steps; leave the approval to its queue, "
            "or ask whoever answered a task"
        )
    assert task is not None  # `answered` names its task, checked when the definition is read
    if answering(task) in excluded_every_time(case, step):
        return (
            f"whoever answered {task} is excluded from approving {name} in every run, since "
            f"{name} reads {task}.outcome; leave the approval to its queue, or ask whoever "
            "answered another task"
        )
    return None
