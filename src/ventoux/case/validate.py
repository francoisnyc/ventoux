"""Case validation: what can be proven about a case definition by reading it, before any case
opens (layer 10). See docs/layers/10-case-validation.md and docs/guides/cases.md.
"""

from collections.abc import Mapping
from typing import Any

from ventoux.case.calls import (
    approval_issues,
    called_contracts,
    contract_input_issues,
    expression_issues,
    plan_input_issues,
    supplied_plans,
)
from ventoux.case.definition import AnsweredTask, CaseDefinition, Reached, Started, TaskStep
from ventoux.case.flow import (
    approver_issues,
    condition_issues,
    no_sources_issues,
    plan_policy_issues,
    policy_issues,
    reference_issues,
    sensitive_issues,
    trigger_issues,
    type_issues,
)
from ventoux.case.loops import endless_loops
from ventoux.case.reach import (
    Through,
    acts_after_close,
    can_happen,
    can_start,
    on_own_moment,
    opening_fired,
    opening_reaches,
    reachable,
    reached_before,
    reached_by,
    rules_reaching,
    shortest_circle,
    start_refused,
    starters,
    waited_on,
)
from ventoux.case.registered import role_issues_of, source_issues_of, system_issues_of
from ventoux.case.rules import said
from ventoux.case.runtime import listed
from ventoux.case.sequence import requirements
from ventoux.case.types import case_types
from ventoux.case.warnings import warning_issues
from ventoux.core.catalog import Catalog
from ventoux.core.validate import Issue


def validate_case(
    case: CaseDefinition, catalog: Catalog, plans: Mapping[str, Any] | None = None
) -> list[Issue]:
    """Every problem in `case`, a parsed case definition, read against `catalog` and the `plans`
    the deployment supplies, stored data by reference (`refund-order@1`), as the runtime is given
    them. No plans means none: a plan step's plan is then missing (fail closed)."""
    # Fail closed: anything but a parsed definition is refused, never read as one with no problems.
    if not isinstance(case, CaseDefinition):
        raise TypeError(
            f"validate_case takes a parsed case definition (see parse_case), not "
            f"{type(case).__name__}"
        )
    can = can_happen(case, catalog)
    found: list[Issue] = []
    # A case that stays open with nobody to close it is said once, loop or not: one cause, one
    # issue.
    closing = never_closes(case, catalog, can) or loop_issues(case, catalog, can)
    nobody_closes = any(issue.code == "NEVER_CLOSES" for issue in closing)
    found += never_run(case, catalog, can) + never_fires(case, catalog, can) + closing
    found += never_starts(case, catalog, can)
    contracts, unknown_contracts = called_contracts(case, catalog)
    supplied, unknown_plans = supplied_plans(case, plans or {})
    found += unknown_contracts + unknown_plans
    found += contract_input_issues(case, contracts) + plan_input_issues(case, supplied)
    calling = {name for name, step in case.steps.items() if not isinstance(step, TaskStep)}
    missing = calling - set(contracts) - set(supplied)
    found += expression_issues(case, case_types(case, catalog), missing)
    found += approval_issues(case, catalog, contracts)
    # Where each value comes from (10c), in the order the runtime meets it: an input already
    # refused isn't asked again (one cause, one issue).
    found += reference_issues(case, contracts, supplied, {issue.path for issue in found})
    said = {issue.path for issue in found}
    found += policy_issues(case, contracts, said) + no_sources_issues(case, supplied, said)
    # Only an error on the input is the cause: a warning (OPENER_DECIDES) never hides the
    # condition's refusal, which holds whoever opens the case.
    found += condition_issues(case, contracts, {i.path for i in found if i.severity == "error"})
    found += type_issues(case, catalog, contracts, supplied, {issue.path for issue in found})
    found += plan_policy_issues(case, catalog, contracts, supplied, {i.path for i in found})
    found += sensitive_issues(case, contracts, {issue.path for issue in found})
    found += approver_issues(case, catalog, contracts)
    found += trigger_issues(case, contracts)
    found += role_issues_of(case, catalog, can, closing=not nobody_closes)
    found += source_issues_of(case, catalog) + system_issues_of(case, catalog)
    found += close_unreachable(case, can) + unreachable_milestones(case)
    # What a definition may mean but surprises its author when a case runs (10d).
    # A step an error refuses gets no warning, nor does what it would give: one cause, one issue.
    # A step that can never run is refused too, though its group's DEADLOCK may name another.
    refused = {i.path.split(".")[1] for i in found if i.severity == "error" and "." in i.path}
    refused |= {name for name in case.steps if name not in can}
    said = {issue.path for issue in found}
    found += warning_issues(case, contracts, supplied, said, missing | refused)
    # Steps the structure lets run are still kept out if the case closes when it opens. If every
    # step is dead anyway, their own issues say why; and a rule on the opening with its own issue
    # may fail, so the case may need attention instead of closing: one cause, one issue. Said
    # first, as the first thing the case would do.
    with_issue = {i.path.split(".")[1] for i in found if i.path.startswith("rules.")}
    own_issue = bool(with_issue & set(opening_fired(case)))
    if closes_at_opening(case) and any(name in can for name in case.steps) and not own_issue:
        found.insert(
            0,
            Issue(
                "steps",
                "CLOSES_AT_OPENING",
                f"nothing starts by itself when {case.case} opens, so it closes at once and every "
                "proposal is refused: let a step start by itself with nothing required, start one "
                "from a rule on the opening, or add stays_open",
            ),
        )
    return found


def unreachable_milestones(case: CaseDefinition) -> list[Issue]:
    """A milestone no step, outcome or rule reaches: a warning, since nothing waits for it. One a step
    requires is said by that step's issue, one in `closes_when` by its own: one cause, one issue."""
    required = {r for step_requires in requirements(case).values() for r in step_requires}
    return [
        Issue(
            f"milestones.{name}",
            "UNREACHABLE_MILESTONE",
            f"no step or rule reaches {name}: reach it from a step, an outcome or a rule, or "
            "remove it",
            "warning",
        )
        for name in case.milestones
        if not reached_by(case, name)
        and not rules_reaching(case, name)  # a rule may reach it too (brief, D38)
        and name not in required
        and name not in case.closes_when
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
    never be met, nothing in its work or its close reasons can (brief, D10). A role nobody
    registered counts for nothing (brief, D22)."""
    closers = {role for reason in case.close_reasons.values() for role in reason.roles}
    if not case.stays_open or closers & set(catalog.roles):
        return []
    if case.closes_when and all(name in can for name in case.closes_when):
        return []  # closes_when closes it
    # The roles are named here, so no UNKNOWN_ROLE repeats them: one cause, one issue.
    roles = ", ".join(sorted(closers))
    return [
        Issue(
            "close_reasons",
            "NEVER_CLOSES",
            f"{case.case} stays open, none of its close reasons' roles ({roles}) is registered, "
            f"and closes_when never closes it, so {only_forgetting(case, catalog)}: name a "
            "registered role in a close reason",
        )
    ]


def loop_issues(case: CaseDefinition, catalog: Catalog, can: set[str]) -> list[Issue]:
    """Each loop of starts nothing in the case ends (brief, D39): `NEVER_CLOSES` if no close
    reason names a registered role and `closes_when` can never be met, since nothing in the case
    could close it then; `LOOPS_UNTIL_CLOSED`, a warning, if one of them can (brief, D10)."""
    closers = {role for reason in case.close_reasons.values() for role in reason.roles}
    closes_when = bool(case.closes_when) and all(name in can for name in case.closes_when)
    found: list[Issue] = []
    for loop in endless_loops(case):
        path = f"rules.{loop.rules[0]}.then.start"
        starts = "starts" if len(loop.rules) == 1 else "start"  # "send_back starts review"
        endless = (
            f"{listed(list(loop.rules))} {starts} {listed(list(loop.steps))} again on every "
            "answer, and nothing ends it"
        )
        which = loop.rules[0] if len(loop.rules) == 1 else "one of the rules"
        fix = f"give {which} a when that ends the loop"
        if closers & set(catalog.roles) or closes_when:
            found.append(
                Issue(
                    path,
                    "LOOPS_UNTIL_CLOSED",
                    f"{endless}: {case.case} closes only through a close reason or closes_when: "
                    f"{fix}",
                    "warning",
                )
            )
            continue
        # The roles are named here, so no UNKNOWN_ROLE repeats them: one cause, one issue.
        if closers:
            nobody = (
                f"none of its close reasons' roles ({', '.join(sorted(closers))}) is registered"
            )
        else:
            nobody = f"{case.case} has no close reason"
        found.append(
            Issue(
                path,
                "NEVER_CLOSES",
                f"{endless}: {nobody}, and closes_when never closes it, so "
                f"{only_forgetting(case, catalog)}: {fix}",
            )
        )
    return found


def only_forgetting(case: CaseDefinition, catalog: Catalog) -> str:
    """What could still close a case nothing in its work or close reasons can: a forget request,
    if its definition lets it be forgotten while open and a role that forgets is registered
    (brief, D32); otherwise nothing."""
    if case.forgetting != "never" and catalog.forgetters:
        return "nothing but a forget request could close it"
    return "nothing could ever close it"


def closes_at_opening(case: CaseDefinition) -> bool:
    """Whether the case closes the moment it opens: only what rules on the opening may reach is
    reached yet, so only a step that starts by itself, or that one of those rules starts, with
    every requirement among those can start, and with none, nothing is pending (brief, D10)
    (brief, D39). A case that stays open waits for a person instead. So does one whose rule on
    the opening has a condition: it may fail, whatever the check says of what it reads (the
    opener may leave a field out), and then the case needs attention instead of closing
    (brief, D34)."""
    fired = opening_fired(case)
    if any(case.rules[rule].when is not None for rule in fired):
        return False
    required = requirements(case)
    reached = opening_reaches(case)
    started = {step for rule in fired for step in case.rules[rule].then.start}
    return not case.stays_open and not any(
        (step.automatic or name in started) and set(required[name]) <= reached
        for name, step in case.steps.items()
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
        if can_start(case, catalog, name, can)
        and (unmet := [r for r in required[name] if r not in can])
    }
    waits = {name: waited_on(case, first[name]) if name in first else [] for name in dead}
    found: list[Issue] = []
    in_a_circle: set[str] = set()
    for name in dead:
        if name in in_a_circle:
            continue  # one cause, one issue: its group's DEADLOCK names it
        path = f"steps.{name}.requires"
        if not can_start(case, catalog, name, can):
            found.append(nobody_starts(case, name))
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


def nobody_starts(case: CaseDefinition, name: str) -> Issue:
    """Why nobody can ever start the step `name`: none of its `proposed_by` roles is registered,
    and each rule starting it can't, as its own issue says, or fires only once the step has run.
    That last is one cause, said here only, with no `NEVER_FIRES` beside it (brief, D39)."""
    roles, rules = case.steps[name].proposed_by, starters(case, name)
    own = [rule for rule in rules if on_own_moment(case, rule, name)]
    others = [rule for rule in rules if rule not in own]
    how = {(True, False): "proposed", (False, True): "a rule starts it"}.get(
        (bool(roles), bool(rules)), "proposed or a rule starts it"
    )
    why, fixes = [], []
    if roles:
        why.append(f"none of its proposed_by roles ({', '.join(roles)}) is registered")
        fixes.append("name a registered role")
    for rule in own:
        why.append(
            f"{rule} fires on {said(case.rules[rule].on)}, which comes only once {name} has run"
        )
    if own:
        fixes.append("start it from a rule on another moment")
    if len(others) == 1:
        why.append(f"{others[0]} can never start it")
    elif others:
        why.append(f"none of {listed(others)} can ever start it")
    if others:
        fixes.append(f"fix {others[0]} first")
    path = f"steps.{name}.proposed_by" if roles else f"steps.{name}"
    message = f"{name} can never run: it starts only when {how}, and {joined(why)}"
    return Issue(path, "NEVER_RUNS", f"{message}: {', or '.join(fixes)}")


def never_starts(case: CaseDefinition, catalog: Catalog, can: set[str]) -> list[Issue]:
    """A rule's start refused every time the rule fires (brief, D39). Said only for a rule that
    can fire, of a step whose own issue doesn't already say why it never runs: one cause, one
    issue."""
    found: list[Issue] = []
    for rule, written in case.rules.items():
        if rule not in can:
            continue
        for name in written.then.start:
            if name not in can and can_start(case, catalog, name, can):
                continue  # its requirements are the cause, and its own issue says so
            if (why := start_refused(case, rule, name)) is not None:
                found.append(Issue(f"rules.{rule}.then.start", "NEVER_STARTS", why))
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
    reachers = reached_by(case, waits_on) + rules_reaching(case, waits_on)
    if not reachers:
        return (
            f"{name} can never run: it requires {waits_on}, which no step or rule reaches: reach "
            f"{waits_on} from a step or a rule, or remove the requirement"
        )
    # Every step reaching a milestone nothing can reach can never run itself.
    one = len(reachers) == 1
    reach, they = ("reaches", reachers[0]) if one else ("reach", "they")
    return (
        f"{name} can never run: it requires {waits_on}, which only {listed(reachers)} {reach}, "
        f"and {they} can never run: fix {reachers[0]} first"
    )


def never_fires(case: CaseDefinition, catalog: Catalog, can: set[str]) -> list[Issue]:
    """A rule left out of `can`: its moment can never come, or comes only once every
    `closes_when` milestone is reached, when nothing new is decided (brief, D38). An error, not
    the teaching warning "rules that can never fire" (brief, D7): it is proven for every case
    (brief, D34). A rule that would start the step whose own run brings its moment, which nothing
    else starts, is said by that step's issue: one cause, one issue (brief, D39)."""
    found: list[Issue] = []
    for name, rule in case.rules.items():
        if name in can or any(
            on_own_moment(case, name, step) and not can_start(case, catalog, step, can)
            for step in rule.then.start
        ):
            continue
        on = rule.on
        moment = said(on)  # fail closed: a moment Ventoux doesn't know is refused here
        if acts_after_close(case, name):
            assert isinstance(on, Reached)
            why = (
                f"{name} can never act: it fires on {moment}, and {case.case} closes once "
                f"{on.reached} is reached, when nothing new is decided: fire it on an earlier "
                f"moment, or remove {on.reached} from closes_when"
            )
        elif isinstance(on, Started | AnsweredTask):
            step = on.started if isinstance(on, Started) else on.answered
            why = (
                f"{name} can never fire: it fires on {moment}, which can never run: fix {step} "
                "first"
            )
        else:
            assert isinstance(on, Reached)  # the opening always comes, and said() knows no other
            reachers = reached_by(case, on.reached) + rules_reaching(case, on.reached)
            if reachers:
                one = len(reachers) == 1
                why = (
                    f"{name} can never fire: it fires on {moment}, which only {listed(reachers)} "
                    f"{'reaches' if one else 'reach'}, and "
                    f"{'it can never' if one else 'none of them can ever'} happen: fix "
                    f"{reachers[0]} first"
                )
            else:
                why = (
                    f"{name} can never fire: it fires on {moment}, which no step or rule reaches: "
                    f"reach {on.reached} from a step or a rule, or fire it on another moment"
                )
        found.append(Issue(f"rules.{name}.on", "NEVER_FIRES", why))
    return found
