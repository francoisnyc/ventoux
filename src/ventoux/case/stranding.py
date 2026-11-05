"""What may strand a required step: `REQUIRED_MAY_STRAND`, a warning of `ventoux check`
(brief, D72).

A required step is owed until its latest run is done. A run that ends without being done (a rule
stopped it, its approval was rejected) leaves it owed, and then only another run can do it. If
nothing can start one, only a person's close ends the case, so the check says so before any case
opens. A warning, never an error: the rule may never fire, the approval may be given, so it
doesn't hold for every case (brief, D37). One issue per step: the first of these it meets.
"""

from typing import Literal

from ventoux.case.definition import CallStep, CaseDefinition
from ventoux.case.reach import reached_by, rules_reaching
from ventoux.case.sequence import requirements
from ventoux.core.validate import Issue

FIX = "make {step} repeatable and proposed_by a role, or start it from a rule"


def may_strand_issues(case: CaseDefinition, refused: set[str]) -> list[Issue]:
    """A warning for each required step, not already `refused` by an error, that may be left
    owed with nothing able to start it: one cause, one issue."""
    return [
        Issue(f"steps.{name}", "REQUIRED_MAY_STRAND", message, "warning")
        for name, step in case.steps.items()
        if step.required and name not in refused and (message := may_strand(case, name)) is not None
    ]


def may_strand(case: CaseDefinition, name: str) -> str | None:
    """Why the required step `name` may be left owed with nothing able to start it, or None."""
    ending = may_end(case, name)
    if ending is not None and not runs_again(case, name):
        said = f"a rule may stop {name}" if ending == "stopped" else "its approval may be rejected"
        return f"{said}, and it is required, so it might never run again: {FIX.format(step='it')}"
    for requirement in requirements(case)[name]:
        if requirement not in case.steps:
            continue
        ending = may_end(case, requirement)
        if ending is not None and not runs_again(case, requirement):
            said = (
                "which a rule may stop" if ending == "stopped" else "whose approval may be rejected"
            )
            return (
                f"{name} requires {requirement}, {said}, and which might never run again; {name} "
                f"is required, so it might never start: {FIX.format(step=requirement)}"
            )
    for milestone in case.closes_when:
        for requirement in requirements(case)[name]:
            if requirement in case.steps and not done_before(case, requirement, milestone):
                return (
                    f"{name} requires {requirement}, which may not be done when {milestone} is "
                    f"reached, and nothing but {name} starts then; {name} is required, so it "
                    f"might never start: make what reaches {milestone} require {requirement}, "
                    f"or remove {milestone} from closes_when"
                )
    return None


def may_end(case: CaseDefinition, name: str) -> Literal["stopped", "rejected"] | None:
    """How a run of the step may end without being done, or None: a rule may stop it
    (brief, D40), or its approval may be rejected."""
    if any(name in rule.then.stop for rule in case.rules.values()):
        return "stopped"
    step = case.steps[name]
    if isinstance(step, CallStep) and step.approval is not None:
        return "rejected"
    return None


def runs_again(case: CaseDefinition, name: str) -> bool:
    """Whether the step may run again once a run has ended: it is repeatable, and a role may
    propose it or a rule in the definition starts it. Proven from the definition, never guessed;
    a step that starts by itself does so at most once (brief, D40)."""
    step = case.steps[name]
    started_by_a_rule = any(name in rule.then.start for rule in case.rules.values())
    return step.repeatable and (bool(step.proposed_by) or started_by_a_rule)


def done_before(case: CaseDefinition, step: str, milestone: str) -> bool:
    """Whether `step` is surely done whenever `milestone` is reached: no rule reaches it, and
    every step that does is `step` or requires it, directly or through the steps it requires."""
    if rules_reaching(case, milestone):
        return False  # a rule may reach it on a moment that waits for nothing: doubt warns
    return all(
        reacher == step or step in required_before(case, reacher)
        for reacher in reached_by(case, milestone)
    )


def required_before(case: CaseDefinition, name: str) -> set[str]:
    """Every step that is done before `name` starts: the steps it requires, and theirs in turn."""
    found: set[str] = set()
    waiting = [name]
    while waiting:
        for requirement in requirements(case)[waiting.pop()]:
            if requirement in case.steps and requirement not in found:
                found.add(requirement)
                waiting.append(requirement)
    return found
