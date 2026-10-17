"""Where each value a step reads comes from, and whether it may go there (layer 10c).

Every writer stamps what it writes with sources that don't depend on what it read, so a value's
sources are known in one pass (brief, D34) (brief, D36). See docs/layers/10-case-validation.md
(10c) and docs/guides/cases.md.
"""

from collections.abc import Collection, Mapping

from ventoux.case.definition import CallStep, CaseDefinition, PlanStep, TaskStep, WorkflowStep
from ventoux.case.types import case_types
from ventoux.case.visibility import may_see, seen_by
from ventoux.core.before_activity import not_a_reference_to
from ventoux.core.catalog import Catalog
from ventoux.core.contract import Contract, held_input
from ventoux.core.expressions import (
    BooleanType,
    FieldType,
    NumberType,
    OutcomeType,
    ReferenceType,
    StringType,
    check,
)
from ventoux.core.expressions.check import a_type
from ventoux.core.output_sources import output_sources
from ventoux.core.plan import Plan, set_by
from ventoux.core.policy import OnlyFrom, Policy, refusal
from ventoux.core.provenance import answering, fields_read, provenance
from ventoux.core.references import references
from ventoux.core.validate import Issue, refused_inputs

# Who opens a case is the one writer the check can't know: a system, recorded as `system:opener`,
# or a person, recorded as `person:<who>`. The check reads the case both ways.
BY_A_SYSTEM = "system:opener"
BY_A_PERSON = "person:opening"  # a stand-in for whoever opens it: a person, trusted


def named(source: str) -> str:
    """A source as a message says it: the opening's, whoever opened, is `the opener`."""
    return "the opener" if source in (BY_A_SYSTEM, BY_A_PERSON) else source


def what_to_do(policy: Policy) -> str:
    """What the case's author can do about a refused input."""
    if isinstance(policy, OnlyFrom):
        return f"use a value {' or '.join(policy.systems)} gave"
    return "use a value a system or a person gave"


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


def reference_issues(
    case: CaseDefinition,
    contracts: Mapping[str, Contract],
    plans: Mapping[str, Plan],
    said: Collection[str],
) -> list[Issue]:
    """Each reference a step gives, to a contract's reference input or a plan's reference field:
    only a reference field of its system, read as it is, never another system's, a text or a
    computed value (brief, D30). Read with the runtime's own `not_a_reference_to`, over the
    case's declared fields, so the two can't disagree: an output is never a reference field."""
    types = {name: field.declared for name, field in case.fields.items()}
    expected: list[tuple[str, str, str, str]] = []  # step, what it calls, the input, its system
    for name, contract in contracts.items():
        expected += [
            (name, contract.reference, field, system)
            for field, system in references(contract.input).items()
        ]
    for name, plan in plans.items():
        expected += [
            (name, f"{plan.plan}@{plan.version}", field, declared.system)
            for field, declared in plan.fields.items()
            if isinstance(declared, ReferenceType)
        ]
    issues: list[Issue] = []
    for name, reference, field, system in expected:
        step = case.steps[name]
        assert isinstance(step, CallStep | PlanStep)  # only these call a contract or a plan
        path = f"steps.{name}.inputs.{field}"
        if field not in step.inputs or path in said:
            continue
        wrong = not_a_reference_to(system, step.inputs[field], types)
        if wrong is not None:
            issues.append(
                Issue(
                    path,
                    "REFERENCE",
                    f"{reference} takes {field} as a reference to {system}, and is given {wrong}: "
                    f"give it a reference to {system}, read as it is",
                )
            )
    return issues


def no_sources_issues(
    case: CaseDefinition, plans: Mapping[str, Plan], said: Collection[str]
) -> list[Issue]:
    """Each plan field given only values written in the definition: they come from nobody, so the
    plan refuses to start (brief, D28) (brief, D36). A contract's input takes a literal: no
    sources pass `trusted_only`, and `only_from` refuses them as its own refusal."""
    issues: list[Issue] = []
    for name, plan in plans.items():
        step = case.steps[name]
        assert isinstance(step, PlanStep)  # only a plan step runs a plan
        for field, expression in step.inputs.items():
            path = f"steps.{name}.inputs.{field}"
            if path not in said and field in plan.fields and not fields_read(expression):
                issues.append(
                    Issue(
                        path,
                        "NO_SOURCES",
                        f"{step.plan} takes {field} from the case, and is given only values "
                        "written in the definition, which come from nobody: give it a field of "
                        "the case file",
                    )
                )
    return issues


def as_said(wanted: FieldType) -> str:
    """The type an input takes, as a message says it: `a number`, `one of low or high`."""
    if isinstance(wanted, OutcomeType):
        return f"one of {' or '.join(wanted.outcomes)}"
    return a_type(wanted)


def fits_type(given: FieldType, wanted: FieldType) -> bool | None:
    """Whether a value of the type `given` always fits `wanted` (True), never does (False), or
    only depends on the value (None), as the runtime's `fits` and strict validation read it."""
    if isinstance(wanted, StringType):
        # A string, an outcome and a reference are all texts.
        return isinstance(given, StringType | OutcomeType | ReferenceType)
    if isinstance(wanted, OutcomeType):
        if isinstance(given, OutcomeType):
            # Every outcome it may give is one the field takes, or some aren't.
            return True if set(given.outcomes) <= set(wanted.outcomes) else None
        # A text, or a reference, may be one of them or not: that depends on the value.
        return None if isinstance(given, StringType | ReferenceType) else False
    if isinstance(wanted, NumberType | BooleanType):
        return type(given) is type(wanted)
    # Fail closed: a type the runtime's `fits` doesn't know (a list, for now) fits nothing.
    return False


def type_issues(
    case: CaseDefinition,
    catalog: Catalog,
    contracts: Mapping[str, Contract],
    plans: Mapping[str, Plan],
    said: Collection[str],
) -> list[Issue]:
    """Each input given a value of another type than it takes: a contract's (strict validation,
    G6) or a plan's field (the plan's start, G7). Never converted (brief, D36). A reference is
    `REFERENCE`'s, an input already refused isn't asked again (one cause, one issue)."""
    types = case_types(case, catalog)
    wanted: list[tuple[str, str, str, FieldType | None, str]] = []
    for name, contract in contracts.items():
        refs = references(contract.input)
        for field, info in contract.input.model_fields.items():
            if field != contract.idempotency_key and field not in refs:
                kind = getattr(info.annotation, "__name__", str(info.annotation))
                wanted.append((name, contract.reference, field, held_input(info.annotation), kind))
    for name, plan in plans.items():
        for field, declared in plan.fields.items():
            if not isinstance(declared, ReferenceType):
                wanted.append((name, f"{plan.plan}@{plan.version}", field, declared, ""))
    issues: list[Issue] = []
    for name, reference, field, wanted_type, kind in wanted:
        step = case.steps[name]
        assert isinstance(step, CallStep | PlanStep)  # only these call a contract or a plan
        path = f"steps.{name}.inputs.{field}"
        if field not in step.inputs or path in said:
            continue
        if wanted_type is None:
            # Fail closed: registration refuses such an input, and checks every contract again
            # when it is registered (learning question 31), so this can't come from a catalog
            # used as it is meant to be; if it does, it is an error, never a pass.
            issues.append(
                Issue(
                    path,
                    "INPUT_TYPE",
                    f"{reference} takes {field} as {kind}, which no value of a case is, and which "
                    "registration refuses: register the contract through the catalog",
                )
            )
            continue
        expression = step.inputs[field]
        given = check(expression, types)
        if isinstance(wanted_type, OutcomeType) and isinstance(expression, str):
            # A text written in the definition is one of them or not: if not, it is the mistake,
            # so the message names it (brief, D35).
            fits = expression in wanted_type.outcomes
            said_given = f'"{expression}"'
        else:
            fits = fits_type(given, wanted_type) is not False
            said_given = a_type(given)
        if not fits:
            issues.append(
                Issue(
                    path,
                    "INPUT_TYPE",
                    f"{reference} takes {field} as {as_said(wanted_type)}, and is given "
                    f"{said_given}: give it {as_said(wanted_type)}",
                )
            )
    return issues


def sensitive_issues(
    case: CaseDefinition, contracts: Mapping[str, Contract], said: Collection[str]
) -> list[Issue]:
    """Each workflow step's input reading a sensitive field: its worker belongs to another team
    and doesn't hold the case's key, so the step fails whenever it runs (brief, D31). A sensitive
    field's value always arrives wrapped, so reading the definition proves it."""
    issues: list[Issue] = []
    for name, contract in contracts.items():
        step = case.steps[name]
        if not isinstance(step, WorkflowStep):
            continue
        for field, expression in step.inputs.items():
            path = f"steps.{name}.inputs.{field}"
            read = [f for f in fields_read(expression) if f in case.fields]
            sensitive = [f for f in read if case.fields[f].sensitive]
            if path not in said and sensitive:
                issues.append(
                    Issue(
                        path,
                        "SENSITIVE_TO_WORKFLOW",
                        f"{contract.reference} is a workflow step and can't be given "
                        f"{sensitive[0]}, a sensitive field: its worker doesn't hold the case's "
                        "key; give it a value that isn't sensitive",
                    )
                )
    return issues


def approver_issues(
    case: CaseDefinition, catalog: Catalog, contracts: Mapping[str, Contract]
) -> list[Issue]:
    """An approval role that, held alone, can't see a value its step reads: its inputs, its
    `when`, its approval's `when`. A warning: a person approving holds all their roles, so one who
    also holds a role that sees it may approve, and the check can't know who holds which roles
    (brief, D16) (brief, D34). One issue per role and value; a role nobody registered is
    `UNKNOWN_ROLE`'s. When the case runs, an approval from anyone who can't see it is refused."""
    issues: list[Issue] = []
    for name in contracts:
        step = case.steps[name]
        assert isinstance(step, CallStep)  # only a call step has a contract
        if step.approval is None:
            continue
        read = list(step.inputs.values())
        read += [when for when in (step.when, step.approval.when) if when is not None]
        fields = sorted({field for expression in read for field in fields_read(expression)})
        for role in step.approval.roles:
            if role not in catalog.roles:
                continue
            issues += [
                Issue(
                    f"steps.{name}.approval.roles",
                    "APPROVER_CANT_SEE",
                    f"{role} can't see {field}, which {name} reads: a person approving {name} "
                    f"needs {' or '.join(seen_by(case, field))} as well; let {role} see {field}, "
                    "or approve with a role that does",
                    "warning",
                )
                for field in fields
                if not may_see(case, field, [role], catalog.roles)
            ]
    return issues


def policy_issue(
    path: str, message: str, policy: Policy, field: str, refused: tuple[bool, bool]
) -> Issue | None:
    """The issue for an input whose value `policy` refuses (`message`) when a system, then a
    person, opens the case: an error if refused both times, a warning if only who opens it
    decides, which the check can't know (brief, D34) (brief, D36)."""
    if all(refused):
        return Issue(path, "INPUT_POLICY", f"{message}: {what_to_do(policy)}")
    if any(refused):
        return Issue(
            path,
            "OPENER_DECIDES",
            f"{message}, which is refused when a person opens the case: open it only from a "
            f"system, or give {field} a value a system gave",
            "warning",
        )
    return None


def policy_issues(
    case: CaseDefinition, contracts: Mapping[str, Contract], said: Collection[str]
) -> list[Issue]:
    """Each activity and workflow step's input against its contract's input policies, which say
    where it may come from (brief, D21). An input at a path in `said` already has its issue (one
    cause, one issue)."""
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
                refused = (
                    policy.refuses(provenance(expression, by_a_system)) is not None,
                    policy.refuses(provenance(expression, by_a_person)) is not None,
                )
                message = refusal(contract.reference, field, policy, expression, by_a_person, named)
                issue = policy_issue(path, message, policy, field, refused)
                if issue is not None:
                    issues.append(issue)
                    break  # one issue per input: the first the runtime meets
    return issues


def plan_fields_sources(
    step: PlanStep, plan: Plan, sources: Mapping[str, frozenset[str]]
) -> dict[str, frozenset[str]]:
    """Where each of the plan's fields comes from: what the case gives it, with the sources of
    what it read (brief, D28), or whoever answers the wait that sets it. The plan's own marks are
    left out: a plan refusing its own field is the plan's issue (layer 3)."""
    setters = set_by(plan)
    return {
        field: frozenset({answering(setters[field])})
        if field in setters
        else provenance(step.inputs[field], sources)
        for field in plan.fields
    }


def plan_policy_issues(
    case: CaseDefinition,
    catalog: Catalog,
    contracts: Mapping[str, Contract],
    plans: Mapping[str, Plan],
    said: Collection[str],
) -> list[Issue]:
    """Each plan step's inputs carried into its plan: each activity in the plan checked with the
    sources the case gives its fields, at the case's input, before the plan runs (brief, D36). A
    step with an input issue already is left out (one cause, one issue)."""
    by_a_system = case_sources(case, contracts, BY_A_SYSTEM)
    by_a_person = case_sources(case, contracts, BY_A_PERSON)
    issues: list[Issue] = []
    for name, plan in plans.items():
        step = case.steps[name]
        assert isinstance(step, PlanStep)  # only a plan step runs a plan
        if any(path.startswith(f"steps.{name}.inputs") for path in said):
            continue
        when_a_system_opens = plan_fields_sources(step, plan, by_a_system)
        when_a_person_opens = plan_fields_sources(step, plan, by_a_person)
        refused_anyway = {
            (r.state, r.field) for r in refused_inputs(plan, catalog, when_a_system_opens)
        }
        given: set[str] = set()
        # A person opening refuses whatever a system opening does, and more.
        for refused in refused_inputs(plan, catalog, when_a_person_opens):
            reference, field, policy = refused.contract.reference, refused.field, refused.policy
            message = refusal(
                reference, field, policy, refused.expression, when_a_person_opens, named
            )
            refused_when = ((refused.state, field) in refused_anyway, True)  # system, person
            # At each case input that feeds a refused field of the plan, once.
            for plan_field in fields_read(refused.expression):
                path = f"steps.{name}.inputs.{plan_field}"
                if plan_field not in step.inputs or plan_field in given:
                    continue
                if policy.refuses(when_a_person_opens[plan_field]) is None:
                    continue
                issue = policy_issue(
                    path,
                    f"{step.plan}, in its state {refused.state}: {message}",
                    policy,
                    plan_field,
                    refused_when,
                )
                if issue is not None:
                    given.add(plan_field)
                    issues.append(issue)
    return issues


def trigger_issues(case: CaseDefinition, contracts: Mapping[str, Contract]) -> list[Issue]:
    """A rule whose condition reads a value from an untrusted source whoever writes it: the
    runtime refuses to let it act every time, so it never does (`UNTRUSTED_TRIGGER`). Untrusted
    data informs; it never decides (brief, D38). In 11a every value is untrusted always or never
    (a field's mark stays whoever writes it, an output carries its contract's source), so any
    untrusted source is a proof; a field only some writers make untrusted comes with `set`."""
    sources = case_sources(case, contracts, BY_A_SYSTEM)  # who opens it changes no trust
    found: list[Issue] = []
    for name, rule in case.rules.items():
        for field in [] if rule.when is None else fields_read(rule.when):
            untrusted = sorted(s for s in sources.get(field, ()) if s.startswith("untrusted:"))
            if untrusted:
                found.append(
                    Issue(
                        f"rules.{name}.when",
                        "UNTRUSTED_TRIGGER",
                        f"{name}'s condition reads {field}, which comes from "
                        f"{', '.join(untrusted)} whoever writes it, and untrusted data can't "
                        f"decide, so it never reaches {' and '.join(rule.then.reach)}: read a "
                        "value a person or a trusted system gives, such as a task's answer",
                    )
                )
                break  # one cause, one issue
    return found
