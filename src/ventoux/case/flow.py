"""Where each value a step reads comes from, and whether it may go there (layer 10c).

Every writer stamps what it writes with sources that don't depend on what it read, so a value's
sources are known in one pass (brief, D34) (brief, D36). See docs/layers/10-case-validation.md
(10c) and docs/guides/cases.md.
"""

from collections.abc import Collection, Mapping

from ventoux.case.definition import CallStep, CaseDefinition, PlanStep, TaskStep
from ventoux.core.contract import Contract
from ventoux.core.output_sources import output_sources
from ventoux.core.policy import refusal
from ventoux.core.provenance import answering, provenance
from ventoux.core.validate import Issue, what_to_do

# Who opens a case is the one writer the check can't know: a system, recorded as `system:opener`,
# or a person, recorded as `person:<who>`. The check reads the case both ways.
BY_A_SYSTEM = "system:opener"
BY_A_PERSON = "person:opening"  # a stand-in for whoever opens it: a person, trusted


def named(source: str) -> str:
    """A source as a message says it: the opening's, whoever opened, is `the opener`."""
    return "the opener" if source in (BY_A_SYSTEM, BY_A_PERSON) else source


def case_sources(
    case: CaseDefinition, contracts: Mapping[str, Contract], opener: str
) -> dict[str, frozenset[str]]:
    """Where each value of `case` comes from, by the name an expression reads it with, when
    `opener` opens it: the union of what each of its writers stamps (brief, D34)."""
    # A field a task's form sets comes from whoever answers; any other, from the opening, which
    # never gives a field a form sets.
    answered: dict[str, set[str]] = {}
    for name, step in case.steps.items():
        if isinstance(step, TaskStep):
            for outcome in step.outcomes.values():
                for set_field in outcome.sets:
                    answered.setdefault(set_field, set()).add(answering(name))
    sources: dict[str, frozenset[str]] = {}
    for name, field in case.fields.items():
        writers = answered.get(name, {opener})
        # A mark adds distrust, never removes it, whoever writes the field (brief, D12).
        sources[name] = frozenset(writers | ({field.source} if field.source else set()))
    for name, step in case.steps.items():
        if isinstance(step, TaskStep):
            sources[f"{name}.outcome"] = frozenset({answering(name)})
        elif isinstance(step, PlanStep):
            sources[f"{name}.outcome"] = frozenset({f"system:{step.plan}"})
        elif name in contracts:
            contract = contracts[name]
            sources[f"{name}.outcome"] = frozenset({f"system:{contract.reference}"})
            # An output carries its contract's source, never one the activity sends (brief, D29).
            for output, source in output_sources(contract.output).items():
                sources[f"{name}.{output}"] = frozenset({source})
        # A step whose contract is missing gives nothing: reading it is already an issue (10b).
    return sources


def policy_issues(
    case: CaseDefinition, contracts: Mapping[str, Contract], said: Collection[str]
) -> list[Issue]:
    """Each activity and workflow step's input against its contract's input policies: refused
    whoever opens the case, an error; refused only when a person opens it, a warning (brief, D21).
    An input at a path in `said` already has its issue (one cause, one issue)."""
    by_a_system = case_sources(case, contracts, BY_A_SYSTEM)
    by_a_person = case_sources(case, contracts, BY_A_PERSON)
    issues: list[Issue] = []
    for name, contract in contracts.items():
        step = case.steps[name]
        assert isinstance(step, CallStep)  # only a call step has a contract
        for field, expression in step.inputs.items():
            path = f"steps.{name}.inputs.{field}"
            if path in said:
                continue
            for policy in contract.policies(field):
                refused = [
                    policy.refuses(provenance(expression, sources)) is not None
                    for sources in (by_a_system, by_a_person)
                ]
                if not any(refused):
                    continue
                message = refusal(contract.reference, field, policy, expression, by_a_person, named)
                if all(refused):
                    issues.append(Issue(path, "INPUT_POLICY", f"{message}: {what_to_do(policy)}"))
                else:
                    # Only who opens the case decides, which the check can't know: a warning
                    # (brief, D34) (brief, D36).
                    issues.append(
                        Issue(
                            path,
                            "OPENER_DECIDES",
                            f"{message}, which is refused when a person opens the case: open it "
                            f"only from a system, or give {field} a value a system gave",
                            "warning",
                        )
                    )
                break  # one issue per input: the first the runtime meets
    return issues
