"""The authoring loop: a model drafts a plan, the package's check refuses or passes it, and the
problems go back to the model, for a bounded number of rounds (brief, D63).

Nothing from a draft is executed, imported or built: it is JSON, read by Pydantic, and checked by
the function `ventoux release` checks a package with. The builder, the interpreter and Temporal
are out of reach of this module (a test proves it) (brief, D58).
"""

import json
from dataclasses import dataclass
from typing import Any, Literal

from ventoux.authoring.answers import NotOneObject, one_object, unfenced
from ventoux.authoring.provider import Message, Provider, ProviderFailed, Request
from ventoux.case.checked import is_error, issues_of, said
from ventoux.case.definition import PlanStep
from ventoux.case.releases import Package, package
from ventoux.case.writers import could_come_from
from ventoux.core.catalog import Catalog
from ventoux.core.plan import PlanInvalid, parse_plan
from ventoux.core.promise import promise_of
from ventoux.core.provenance import fields_read

ROUNDS = range(1, 6)  # how many rounds a loop may take: 1 to 5, never more (brief, D63)


class DraftRefused(Exception):
    """The loop can't start: a plan no step names, or a number of rounds out of bounds. Said
    before the model is asked anything."""


@dataclass(frozen=True)
class Round:
    """One round: what the model answered, and the problems the check found in it."""

    answer: str  # the model's answer, as text
    problems: tuple[str, ...]  # each as `path: CODE: message`; none: the draft passed


@dataclass(frozen=True)
class Authored:
    """What the loop made of a goal: a drafted plan, or why there is none."""

    verdict: Literal["drafted", "abandoned", "no answer"]
    plan: str | None  # the drafted plan's JSON text, as the model wrote it; only when drafted
    rounds: tuple[Round, ...]
    reason: str | None  # why there is no plan; None when drafted
    warnings: tuple[str, ...] = ()  # the drafted package's warnings, which refuse nothing


async def author(
    goal: str,
    released: Package,
    plan: str,
    catalog: Catalog,
    schema: dict[str, Any],
    provider: Provider,
    rounds: int = 3,
) -> Authored:
    """Draft the plan `plan` (`refund-order@1`) of `released` for `goal`, asking `provider` at
    most `rounds` times. `schema` is the published plan schema, given to the model as data."""
    if rounds not in ROUNDS:
        raise DraftRefused(f"--rounds is {rounds}: a loop takes 1 to 5 rounds")
    step = step_naming(released, plan)
    messages = [Message("user", first_message(goal, released, plan, step, catalog))]
    system = instructions(schema)
    done: list[Round] = []
    for _ in range(rounds):
        try:
            answer = await provider.complete(Request(system, tuple(messages)))
        except ProviderFailed as failed:  # asking again won't help (brief, D62)
            why = f"the authoring model gave no answer: {failed}"
            return Authored("no answer", None, tuple(done), why)
        problems, warnings = checked(answer, released, plan, catalog)
        done.append(Round(answer, tuple(problems)))
        if not problems:
            text = unfenced(answer).strip() + "\n"  # the JSON as the model wrote it
            return Authored("drafted", text, tuple(done), None, tuple(warnings))
        messages += [Message("assistant", answer), Message("user", fed_back(problems))]
    left = len(done[-1].problems)
    return Authored(
        "abandoned",
        None,
        tuple(done),
        f"abandoned after {rounds} rounds: the last draft still has {counted(left, 'problem')}",
    )


def step_naming(released: Package, plan: str) -> tuple[str, PlanStep]:
    """The step of `released` that runs `plan`: the loop drafts only a plan a step names
    (brief, D63)."""
    for name, step in released.case.steps.items():
        if isinstance(step, PlanStep) and step.plan == plan:
            return name, step
    raise DraftRefused(
        f"{plan} is run by no plan step of {released.name}: draft a plan one of its steps names"
    )


def checked(
    answer: str, released: Package, plan: str, catalog: Catalog
) -> tuple[list[str], list[str]]:
    """The problems the answer has as a draft of `plan`, each as `path: CODE: message`, and the
    package's warnings: read as one JSON object, as a plan, as `plan`, in its package, and by
    the package's own check (brief, D50) (brief, D63)."""
    try:
        draft = one_object(answer)
    except NotOneObject as not_one:
        return [f"answer: NOT_ONE_OBJECT: the answer is not one JSON object: {not_one}"], []
    try:
        parsed = parse_plan(draft)
    except PlanInvalid as invalid:
        return [shape_problem(line) for line in str(invalid).splitlines()], []
    drafted = f"{parsed.plan}@{parsed.version}"
    if drafted != plan:
        return [
            f"plan: WRONG_PLAN: the draft is {drafted}, and the package's step names {plan}"
        ], []
    # In its package, in place of the plan it drafts: read as a plan and named by a step, it is
    # all `package` checks, so the package's own check is what is left (brief, D50).
    others = [text for reference, text in released.written.plans.items() if reference != plan]
    issues = issues_of(package(released.written.case, [*others, unfenced(answer)]), catalog)
    errors = [said(issue) for issue in issues if is_error(issue)]
    warnings = [said(issue) for issue in issues if not is_error(issue)]
    return errors, warnings


def shape_problem(line: str) -> str:
    """One of `parse_plan`'s lines (`states.pay.on: required`) in the fixed form: its path, the
    code SHAPE, its message. A line with no path is about the whole plan."""
    path, colon, message = line.partition(": ")
    return f"{path}: SHAPE: {message}" if colon else f"plan: SHAPE: {line}"


FIXED = (
    "The draft was refused. Fix every problem below and answer with the whole plan, as one JSON "
    "object."
)


def fed_back(problems: list[str]) -> str:
    """The problems as the model reads them: the same first line every time, then one problem
    per line, as `ventoux check` writes them (brief, D63)."""
    return "\n".join([FIXED, *problems])


def counted(number: int, thing: str) -> str:
    return f"{number} {thing}" if number == 1 else f"{number} {thing}s"


def instructions(schema: dict[str, Any]) -> str:
    """The system text: what a plan is, the rules the check holds it to, and the answer's form;
    then the published plan schema, which a plan must match (brief, D60)."""
    return "\n\n".join([INSTRUCTIONS, "The plan's JSON Schema:", json.dumps(schema, indent=2)])


INSTRUCTIONS = """You draft a plan: a state machine written as JSON data, which a deterministic \
engine checks before anything runs, and a person reviews before it is kept. A plan is data: it \
is never run as code.

A plan may call only the contracts listed below, each by its name and version; it defines no \
capability. It decides no case's values: the values it is given come from the case, with the \
sources listed for each field.

The check refuses: untrusted data (any source marked untrusted:) reaching an input that takes \
only trusted data; a transition whose condition reads untrusted data; a high-risk activity \
reached without an approval, or reached again on an approval already spent. Prefer drafting to \
sending anything to people.

Answer with the whole plan as one JSON object, and nothing else."""


def first_message(
    goal: str, released: Package, plan: str, step: tuple[str, PlanStep], catalog: Catalog
) -> str:
    """What the model is shown, as JSON: the goal, the plan to draft, the step that names it with
    the sources of each field it gives, the catalog, and the plan as it is now. Never a case
    file, which the loop is never given, and never an implementation (brief, D63)."""
    name, plan_step = step
    sources = could_come_from(released.case, catalog, None)
    given = {
        field: sorted(
            {kind_of(source) for read in fields_read(value) for source in sources.get(read, ())}
        )
        for field, value in plan_step.inputs.items()
    }
    shown: dict[str, Any] = {
        "goal": goal,
        "plan_to_draft": {"plan": plan.partition("@")[0], "version": int(plan.partition("@")[2])},
        "the_step_that_runs_it": {
            "step": name,
            "title": plan_step.display.title,
            "fields_it_gives_and_their_sources": given,
        },
        "contracts": [promise_of(contract) for contract in catalog.contracts()],
        "roles_and_the_risk_each_may_approve": catalog.roles,
        "source_labels": catalog.labels,
        "systems": catalog.systems,
    }
    if plan in released.written.plans:
        shown["the_plan_as_it_is"] = json.loads(released.written.plans[plan])
    return json.dumps(shown, indent=2, default=str)


def kind_of(source: str) -> str:
    """A source as the model is shown it: a person as `person`, never who (brief, D61); a system
    or an untrusted label as written."""
    return "person" if source.startswith("person:") else source
