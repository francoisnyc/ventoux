"""Where each value a step reads comes from, and whether it may go there (layer 10c).

Every writer stamps what it writes with sources that don't depend on what it read, so a value's
sources are known in one pass (brief, D34) (brief, D36). See docs/layers/10-case-validation.md
(10c) and docs/guides/cases.md.
"""

from collections.abc import Callable, Collection, Mapping

from ventoux.case.definition import (
    CallStep,
    CaseDefinition,
    PlanStep,
    Rule,
    Started,
    Then,
    WaitStep,
    WorkflowStep,
    anchor,
)
from ventoux.case.rules import said as said_moment
from ventoux.case.types import case_types, fits_type
from ventoux.case.visibility import may_see, seen_by
from ventoux.case.writers import (
    always,
    case_sources,
    how_started,
    rule_reads,
    start_of,
    steered_by_itself,
    untrusted_of,
    writer_decides,
)
from ventoux.core.before_activity import not_a_reference_to
from ventoux.core.catalog import Catalog
from ventoux.core.contract import Contract, held_input
from ventoux.core.expressions import (
    Expression,
    FieldType,
    OutcomeType,
    ReferenceType,
    check,
)
from ventoux.core.expressions.check import a_type
from ventoux.core.plan import Plan, set_by
from ventoux.core.policy import OnlyFrom, Policy, refusal
from ventoux.core.provenance import answering, fields_read, is_trusted, provenance
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


class Refusals:
    """Whether a policy refuses what an expression reads, for a case `opener` opens: whichever
    rule wrote each value it reads (`always`), or only when some did (`sometimes`) (brief, D42)."""

    def __init__(self, case: CaseDefinition, contracts: Mapping[str, Contract], opener: str):
        self.case, self.contracts, self.opener = case, contracts, opener
        self.sources = case_sources(case, contracts, opener)
        self.found: dict[int, frozenset[str]] = {}

    def refused(self, policy: Policy) -> Callable[[frozenset[str]], bool]:
        return lambda sources: policy.refuses(sources) is not None

    def always(self, policy: Policy, expression: Expression) -> bool:
        """Whether `policy` refuses `expression`'s value every time. A value read from nothing
        has no sources, which some policies refuse; any other comes from the union of what it
        reads, none of them empty, so it is refused whenever one of them always is."""
        read = fields_read(expression)
        if not read:
            return policy.refuses(frozenset()) is not None
        if id(policy) not in self.found:
            self.found[id(policy)] = always(
                self.case, self.contracts, self.opener, self.refused(policy)
            )
        return any(field in self.found[id(policy)] for field in read)

    def sometimes(self, policy: Policy, expression: Expression) -> str | None:
        """The first value `expression` reads that `policy` refuses only when some rules wrote
        it, said with which; None if there is none."""
        if self.always(policy, expression):
            return None
        for field in fields_read(expression):
            own = self.sources.get(field, frozenset())
            if policy.refuses(own) is not None:
                refused = self.refused(policy)
                labels = ", ".join(sorted(s for s in own if refused(frozenset({s}))))
                when = writer_decides(self.case, self.contracts, self.opener, field, refused)
                return (
                    f"{field} comes from {labels} {when}: whether {{step}} is refused "
                    f"depends on which rule set {field} last: set {field} only from values the "
                    "policy takes"
                )
        return None


def policy_issues(
    case: CaseDefinition, contracts: Mapping[str, Contract], said: Collection[str]
) -> list[Issue]:
    """Each activity and workflow step's input against its contract's input policies, which say
    where it may come from (brief, D21). An input at a path in `said` already has its issue (one
    cause, one issue)."""
    by_a_system = Refusals(case, contracts, BY_A_SYSTEM)
    by_a_person = Refusals(case, contracts, BY_A_PERSON)
    issues: list[Issue] = []
    for name, contract in contracts.items():
        step = case.steps[name]
        assert isinstance(step, CallStep)  # only a call step has a contract
        for field, expression in step.inputs.items():
            path = f"steps.{name}.inputs.{field}"
            if path in said:
                continue
            for policy in contract.policies(field):
                # Claimed only where refused whichever rule wrote what it reads (brief, D42).
                refused = (
                    by_a_system.always(policy, expression),
                    by_a_person.always(policy, expression),
                )
                message = refusal(
                    contract.reference, field, policy, expression, by_a_person.sources, named
                )
                issue = policy_issue(path, message, policy, field, refused)
                sometimes = by_a_person.sometimes(policy, expression)
                if issue is None and sometimes is not None:
                    issue = writer_issue(path, message, sometimes.format(step=name))
                if issue is not None:
                    issues.append(issue)
                    break  # one issue per input: the first the runtime meets
    return issues


def writer_issue(path: str, message: str, which: str) -> Issue:
    """A refusal that holds only when some rules wrote a value: whether the step is refused
    depends on which rule wrote last, which the check can't know (brief, D42)."""
    return Issue(path, "WRITER_DECIDES", f"{message}: {which}", "warning")


def condition_issues(
    case: CaseDefinition, contracts: Mapping[str, Contract], said: Collection[str]
) -> list[Issue]:
    """Each call step's input whose policy refuses the untrusted data a condition that lets the
    step start reads: untrusted data can't choose what is sent (brief, D39). Its own `when` is said
    at the input; a rule's, at the rule, as a failure. An input at a path in `said` already has
    its issue, which is the cause: one cause, one issue. The opener is trusted whoever it is, so
    who opens the case changes nothing; which rule wrote what the condition reads may, and then
    it is a warning, `WRITER_DECIDES` (brief, D42)."""
    steering = Steering(case, contracts)
    issues: list[Issue] = []
    for name, contract in contracts.items():
        step = case.steps[name]
        assert isinstance(step, CallStep)  # only a call step has a contract
        # Its own condition, and what steered the runs it requires (brief, D43).
        reads = sorted(steered_by_itself(case, name))
        for field in step.inputs:
            path = f"steps.{name}.inputs.{field}"
            if path not in said and (found := steering.issue(path, contract, field, name, reads)):
                issues.append(found)
    given = {*said, *(issue.path for issue in issues)}
    for rule, written in case.rules.items():
        if written.then.reach or written.then.stop:
            continue  # on untrusted data it doesn't act at all: UNTRUSTED_TRIGGER says so
        for name in written.then.start:
            if name not in contracts or any(p.startswith(f"steps.{name}.inputs.") for p in given):
                continue
            started = case.steps[name]
            assert isinstance(started, CallStep)  # only a call step has a contract
            # Its condition, and what steered the start it fires on (brief, D43).
            reads = sorted(rule_reads(written))
            for field in started.inputs:
                found = steering.issue(
                    f"rules.{rule}.then.start", contracts[name], field, rule, reads, name
                )
                if found:
                    issues.append(found)
                    break  # one issue per start: the first input the runtime meets
    return issues


class Steering:
    """Whether the untrusted data a condition reads is refused by an input's policy: whichever
    rule wrote it (an error), or only when some did (a warning) (brief, D39) (brief, D42)."""

    def __init__(self, case: CaseDefinition, contracts: Mapping[str, Contract]):
        self.case, self.contracts = case, contracts
        self.sources = case_sources(case, contracts, BY_A_SYSTEM)

    def issue(
        self,
        path: str,
        contract: Contract,
        field: str,
        who: str,
        reads: list[str],
        started: str | None = None,
    ) -> Issue | None:
        """The issue at `path`, if what steers `who` (a step, or a rule starting `started`), its
        condition's `reads` and what steered its moment or requirements, steers `field` into a
        policy that refuses it; None if it doesn't."""
        found = steered(self.case, contract, field, self.sources, who, reads)
        if found is None:
            return None
        said, to_do, value, policy = found
        why = f"{said}: {to_do}"

        def refused(sources: frozenset[str]) -> bool:
            untrusted = frozenset(source for source in sources if not is_trusted(source))
            return bool(untrusted) and policy.refuses(untrusted) is not None

        if value in always(self.case, self.contracts, BY_A_SYSTEM, refused):
            if started is None:
                return Issue(path, "INPUT_POLICY", why)
            return Issue(
                path,
                "INPUT_POLICY",
                f"{started} fails on its inputs every time {who} starts it: {why}",
            )
        when = writer_decides(self.case, self.contracts, BY_A_SYSTEM, value, refused)
        step = started if started is not None else who
        if value.startswith("started "):
            steered_step = value.removeprefix("started ")
            return Issue(
                path,
                "WRITER_DECIDES",
                f"{said} {when}: whether {step} is refused depends on how {steered_step} "
                f"started: {to_do}",
                "warning",
            )
        return Issue(
            path,
            "WRITER_DECIDES",
            f"{said}: {value} is untrusted {when}: whether {step} is refused depends on "
            f"which rule set {value} last: set {value} only from trusted values",
            "warning",
        )


def steered(
    case: CaseDefinition,
    contract: Contract,
    field: str,
    sources: Mapping[str, frozenset[str]],
    who: str,
    reads: list[str],
) -> tuple[str, str, str, Policy] | None:
    """Why the input `field` is refused by what steers `who`, as the runtime says it; what to do;
    the value read (a field, or a step's start); and the policy refusing it. None if it isn't.
    `reads` are what its condition reads, and the starts that steer it (brief, D43)."""
    read = {name: sources.get(name, frozenset()) for name in reads}
    for policy in contract.policies(field):
        for value, untrusted in untrusted_of(read).items():
            if policy.refuses(untrusted) is not None:
                labels = ", ".join(sorted(untrusted))
                said = f"{contract.reference} takes {field} {policy.describe()}, and "
                if not value.startswith("started "):
                    said += f"{who}'s condition reads {value} ({labels})"
                    to_do = (
                        "read a value a person or a trusted system gives, such as a task's answer"
                    )
                    return said, to_do, value, policy
                step = value.removeprefix("started ")
                rule = case.rules.get(who)
                on = None if rule is None else anchor(rule.on)
                if rule is not None and isinstance(on, Started) and on.started == step:
                    moment = said_moment(rule.on)  # a timer on the start says so
                    said += f"{who} fires on {moment}, which untrusted data steers ({labels})"
                else:
                    said += f"{who} requires {step}, which untrusted data steers ({labels})"
                return said, steered_to_do(step), value, policy
    return None


def steered_to_do(step: str) -> str:
    """What an author can do about a start untrusted data steers (brief, D43)."""
    return f"start {step} only on trusted data, or let a person decide in a task"


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
    by_a_system = Refusals(case, contracts, BY_A_SYSTEM)
    by_a_person = Refusals(case, contracts, BY_A_PERSON)
    issues: list[Issue] = []
    for name, plan in plans.items():
        step = case.steps[name]
        assert isinstance(step, PlanStep)  # only a plan step runs a plan
        if any(path.startswith(f"steps.{name}.inputs") for path in said):
            continue
        when_a_person_opens = plan_fields_sources(step, plan, by_a_person.sources)
        given: set[str] = set()
        # A person opening refuses whatever a system opening does, and more.
        for refused in refused_inputs(plan, catalog, when_a_person_opens):
            reference, field, policy = refused.contract.reference, refused.field, refused.policy
            message = refusal(
                reference, field, policy, refused.expression, when_a_person_opens, named
            )
            # At each case input that feeds a refused field of the plan, once.
            for plan_field in fields_read(refused.expression):
                path = f"steps.{name}.inputs.{plan_field}"
                if plan_field not in step.inputs or plan_field in given:
                    continue
                if policy.refuses(when_a_person_opens[plan_field]) is None:
                    continue
                # Claimed only where refused whichever rule wrote what it reads (brief, D42).
                expression = step.inputs[plan_field]
                refused_when = (
                    by_a_system.always(policy, expression),
                    by_a_person.always(policy, expression),
                )
                said_here = f"{step.plan}, in its state {refused.state}: {message}"
                issue = policy_issue(path, said_here, policy, plan_field, refused_when)
                sometimes = by_a_person.sometimes(policy, expression)
                if issue is None and sometimes is not None:
                    issue = writer_issue(path, said_here, sometimes.format(step=name))
                if issue is not None:
                    given.add(plan_field)
                    issues.append(issue)
    return issues


def never_does(then: Then) -> str:
    """What a rule that doesn't act never does, as its issue says it: `reaches high_risk or
    starts lead_check`, `stops review`."""
    acts = (
        ("reaches", then.reach),
        ("sets", tuple(then.set)),
        ("starts", then.start),
        ("stops", then.stop),
    )
    return " or ".join(f"{verb} {' and '.join(names)}" for verb, names in acts if names)


def trigger_issues(case: CaseDefinition, contracts: Mapping[str, Contract]) -> list[Issue]:
    """A rule that reaches a milestone or stops a step, whose condition reads a value from an
    untrusted source: the runtime refuses to let it act whenever it does. Untrusted data informs;
    it never decides (brief, D38) (brief, D40). An error (`UNTRUSTED_TRIGGER`) only for a value
    untrusted whichever writer wrote it, since it then never acts; a warning (`WRITER_DECIDES`)
    for a value only some rules make untrusted, since whether it acts depends on which rule wrote
    last (brief, D42)."""
    sources = case_sources(case, contracts, BY_A_SYSTEM)  # who opens it changes no trust
    untrusted = always(case, contracts, BY_A_SYSTEM, is_untrusted)
    found: list[Issue] = []
    for name, rule in case.rules.items():
        if not rule.then.reach and not rule.then.stop:
            continue  # a rule that only starts steps acts: its condition counts for their inputs
        said = len(found)
        for field in [] if rule.when is None else fields_read(rule.when):
            labels = ", ".join(sorted(s for s in sources.get(field, ()) if not is_trusted(s)))
            if not labels:
                continue
            path = f"rules.{name}.when"
            if field in untrusted:
                found.append(
                    Issue(
                        path,
                        "UNTRUSTED_TRIGGER",
                        f"{name}'s condition reads {field}, which comes from {labels} whoever "
                        f"writes it, and untrusted data can't decide, so it never "
                        f"{never_does(rule.then)}: read a value a person or a trusted system "
                        "gives, such as a task's answer",
                    )
                )
            else:
                when = writer_decides(case, contracts, BY_A_SYSTEM, field, is_untrusted)
                found.append(
                    Issue(
                        path,
                        "WRITER_DECIDES",
                        f"{name}'s condition reads {field}, which comes from {labels} {when}, and "
                        f"untrusted data can't decide, so whether it {never_does(rule.then)} "
                        f"depends on which rule set {field} last: set {field} only from trusted "
                        "values",
                        "warning",
                    )
                )
            break  # one cause, one issue
        if len(found) == said and isinstance(on := anchor(rule.on), Started):
            found += moment_issues(case, contracts, name, rule, on.started)
    return found + reach_issues(case, contracts)


def moment_issues(
    case: CaseDefinition, contracts: Mapping[str, Contract], name: str, rule: Rule, step: str
) -> list[Issue]:
    """A rule that reaches or stops, on the start of a step untrusted data steers: what steered
    the start counts as read by its condition, so it never acts on it (brief, D43). An error
    where every way the step starts is steered, whoever writes what it reads; a warning where
    only some are."""
    sources = case_sources(case, contracts, BY_A_SYSTEM)
    labels = ", ".join(sorted(sources.get(start_of(step), ())))
    if not labels:
        return []
    to_do = steered_to_do(step)
    if start_of(step) in always(case, contracts, BY_A_SYSTEM, is_untrusted):
        return [
            Issue(
                f"rules.{name}.on",
                "UNTRUSTED_TRIGGER",
                f"{name} fires on {said_moment(rule.on)}, which untrusted data steers however {step} "
                f"starts ({labels}), and untrusted data can't decide, so it never "
                f"{never_does(rule.then)}: {to_do}",
            )
        ]
    how = how_started(case, contracts, BY_A_SYSTEM, step, is_untrusted)
    return [
        Issue(
            f"rules.{name}.on",
            "WRITER_DECIDES",
            f"{name} fires on {said_moment(rule.on)}, which untrusted data steers ({labels}) {how}, and "
            f"untrusted data can't decide, so whether it {never_does(rule.then)} depends on how "
            f"{step} started: {to_do}",
            "warning",
        )
    ]


def reach_issues(case: CaseDefinition, contracts: Mapping[str, Contract]) -> list[Issue]:
    """A call, plan or wait step that reaches milestones, whose start untrusted data steers: its
    run reaches nothing (brief, D43). An error where every way it starts is steered, a warning
    where only some are. A task's answer is a person's, so its `reaches` stand."""
    sources = case_sources(case, contracts, BY_A_SYSTEM)
    untrusted = always(case, contracts, BY_A_SYSTEM, is_untrusted)
    found: list[Issue] = []
    for name, step in case.steps.items():
        if not step.reaches or not isinstance(step, CallStep | PlanStep | WaitStep):
            continue
        labels = ", ".join(sorted(sources.get(start_of(name), ())))
        if not labels:
            continue
        reaches = " and ".join(step.reaches)
        to_do = f"start {name} only on trusted data, or reach {reaches} from a task's answer"
        if start_of(name) in untrusted:
            found.append(
                Issue(
                    f"steps.{name}.reaches",
                    "UNTRUSTED_TRIGGER",
                    f"{name} reaches {reaches} when it is done, and untrusted data steers it "
                    f"however it starts ({labels}), and untrusted data can't decide, so it never "
                    f"reaches {reaches}: {to_do}",
                )
            )
            continue
        how = how_started(case, contracts, BY_A_SYSTEM, name, is_untrusted)
        found.append(
            Issue(
                f"steps.{name}.reaches",
                "WRITER_DECIDES",
                f"{name} reaches {reaches} when it is done, and untrusted data steers it "
                f"({labels}) {how}, and untrusted data can't decide, so whether it reaches "
                f"{reaches} depends on how it started: {to_do}",
                "warning",
            )
        )
    return found


def is_untrusted(sources: frozenset[str]) -> bool:
    """Whether `sources` hold one the engine doesn't trust: what lets no rule decide (brief, D38)."""
    return any(not is_trusted(source) for source in sources)
