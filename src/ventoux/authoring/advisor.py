"""The step advisor: a model names the step it thinks should run next; admission decides.

It is asked on behalf of one person, and suggests to them; they propose it, or don't (brief, D61).
"""

import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from pydantic import TypeAdapter, ValidationError

from ventoux.authoring.provider import Message, Provider, Request
from ventoux.case.definition import CaseDefinition, Name
from ventoux.case.reading import kind_of
from ventoux.case.runtime import proposal_refused
from ventoux.case.state import CaseState
from ventoux.case.visibility import may_see
from ventoux.core.catalog import Catalog

# Why admission would refuse the person's proposal of a step, or None: `proposal_refused`, in
# memory or asked of a running case.
Refused = Callable[[str], Awaitable[str | None]]


@dataclass(frozen=True)
class FieldShown:
    """A field of the case file as the advisor sees it: never its value."""

    name: str
    kind: str  # its declared type, as people read it: `a number`, `a reference to orders`
    state: str  # `set` or `not set`, with `, sensitive` for a sensitive field; or `hidden`
    sources: tuple[str, ...]  # where its value came from, a person said only as `person`


@dataclass(frozen=True)
class RunShown:
    """A step's latest run: its entry, its status and its outcome, if it has one."""

    entry: str  # `review#1`
    status: str  # `open`, `running`, `done`, `failed`, …
    outcome: str | None  # one of the outcomes its step or contract declares, never a value


@dataclass(frozen=True)
class StepShown:
    """A step admission would accept from the person now, as the definition titles it."""

    name: str
    title: str
    description: str


@dataclass(frozen=True)
class Shown:
    """What the advisor is shown of a case, and the request that says it to the model: names,
    kinds and states, never a case-file value, a person's identifier or a history line
    (brief, D61)."""

    case: str  # the case definition's name
    title: str
    fields: tuple[FieldShown, ...]  # in the definition's order
    milestones: tuple[str, ...]  # reached, in order
    runs: tuple[RunShown, ...]  # each step's latest run, in the order the steps are written
    waiting_for: tuple[str, ...]  # what waits on people, as the inbox says it: roles, never names
    steps: tuple[StepShown, ...]  # the steps the person's proposal would be admitted for now

    @property
    def request(self) -> Request:
        """What the model is sent: the instructions, then what is shown, as JSON."""
        return Request(INSTRUCTIONS, (Message("user", json.dumps(self.said(), indent=2)),))

    def said(self) -> dict[str, Any]:
        """What is shown, as the JSON the model reads."""
        return {
            "case": self.case,
            "title": self.title,
            "fields": [vars(each) for each in self.fields],
            "milestones_reached": list(self.milestones),
            "latest_runs": [vars(each) for each in self.runs],
            "waiting_for": list(self.waiting_for),
            "steps_that_may_start_now": [vars(each) for each in self.steps],
        }


INSTRUCTIONS = """You advise on a case: work a team does step by step. Pick the one step, among \
those listed under steps_that_may_start_now, that should start next, or none.

You are shown the case's fields by name and kind, whether each is set, and where its value came \
from; never a value. A person decides whether to propose what you pick, and the engine checks it \
again.

Answer with one JSON object and nothing else: {"step": "<a step's name>"}, or {"step": null} if \
no step should start now."""


@dataclass(frozen=True)
class Advice:
    """What the advisor suggests: a step, or nothing and why."""

    step: str | None  # the step to suggest; None: nothing to suggest
    refused: str | None  # why nothing is suggested, or None
    by: str  # the provider that answered


def shown_to_advisor(
    case: CaseDefinition,
    catalog: Catalog,
    state: CaseState,
    by: str,
    roles: frozenset[str],
    at: int,
) -> Shown:
    """What the advisor is shown of `state`, asked at `at` on behalf of `by`, who holds
    `roles`: no more than they may see, and no value at all (brief, D61)."""
    fields = tuple(field_shown(case, catalog, state, name, roles) for name in case.fields)
    latest = {run.step: run for run in state.runs}  # runs are in order: the last one stays
    runs = tuple(
        RunShown(run.entry, run.status, outcome_of(state, step) if run.status == "done" else None)
        for step in case.steps
        if (run := latest.get(step)) is not None
    )
    steps = tuple(
        StepShown(name, step.display.title, step.display.description)
        for name, step in case.steps.items()
        if proposal_refused(case, catalog, state, name, by, roles, at) is None
    )
    return Shown(
        case.case,
        case.display.title,
        fields,
        tuple(state.milestones),
        runs,
        tuple(state.waiting.values()),
        steps,
    )


def field_shown(
    case: CaseDefinition, catalog: Catalog, state: CaseState, name: str, roles: frozenset[str]
) -> FieldShown:
    """The field `name` as the advisor sees it, for a person holding `roles`: hidden if they
    may not see it (brief, D30); otherwise whether it is set, and the kinds of its sources."""
    declared = case.fields[name]
    kind = kind_of(name, declared.declared)
    if not may_see(case, name, roles, catalog.roles):
        return FieldShown(name, kind, "hidden", ())
    is_set = "set" if name in state.values else "not set"
    sensitive = ", sensitive" if declared.sensitive else ""
    sources = tuple(sorted(source_kind(each) for each in state.sources.get(name, ())))
    return FieldShown(name, kind, is_set + sensitive, sources)


def source_kind(source: str) -> str:
    """A source as the advisor is shown it: a person's answer as `person`, never who gave it;
    a system or an untrusted label as written (`system:orders`, `untrusted:customer`)."""
    return "person" if source.startswith("person:") else source


def outcome_of(state: CaseState, step: str) -> str | None:
    """The outcome `step`'s run gave: one of the names its step or contract declares (`approve`,
    `declined`, `done`), the one value the advisor is shown, since it is the definition's word."""
    outcome = state.values.get(f"{step}.outcome")
    return outcome if isinstance(outcome, str) else None


async def advise(shown: Shown, provider: Provider, refused: Refused) -> Advice:
    """The step `provider`'s model suggests, once admission has checked it by `refused`."""
    answer = await provider.complete(shown.request)
    try:
        step = step_named(answer)
    except NotOneName:
        # Nothing is guessed from it, and nothing of it is quoted: it is the model's text
        # (brief, D61).
        return Advice(None, NOT_ONE_NAME, provider.name)
    if step is None:
        return Advice(None, "the advisor has no step to suggest", provider.name)
    # Checked as the person's own proposal would be: the model picks among steps, never whether
    # one admission refuses runs (brief, D61).
    if (why := await refused(step)) is not None:
        return Advice(None, why, provider.name)
    return Advice(step, None, provider.name)


NOT_ONE_NAME = "the advisor's answer is not one step name, so it suggests nothing"


class NotOneName(Exception):
    """The model's answer is not `{"step": <a name>}` or `{"step": null}`."""


# Pydantic: checks a value against a type outside any model, here the case's own way of writing
# a name, so an answer is read by the rule the definition is.
NAME = TypeAdapter(Name)


def step_named(answer: str) -> str | None:
    """The step `answer` names, or None for `{"step": null}`; `NotOneName` for anything else:
    prose, a second key, a value that isn't a name written as the case writes names."""
    try:
        read = json.loads(unfenced(answer), object_pairs_hook=no_key_twice)
    except (ValueError, NotOneName):  # not JSON, or a key given twice
        raise NotOneName() from None
    if not isinstance(read, dict) or list(read) != ["step"]:
        raise NotOneName()
    step = read["step"]
    if step is None:
        return None
    try:
        return NAME.validate_python(step, strict=True)
    except ValidationError:
        raise NotOneName() from None


def unfenced(answer: str) -> str:
    """`answer` without the one fenced block around it, if it is one: a model often writes
    ```json on the line before and ``` on the line after."""
    text = answer.strip()
    if not (text.startswith("```") and text.endswith("```") and "\n" in text):
        return text
    inside = text[: -len("```")]
    return inside[inside.index("\n") + 1 :]


def no_key_twice(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    """An object read from JSON, refusing a key given twice: Python's reader would keep the
    last one, silently."""
    keys = [key for key, _ in pairs]
    if len(set(keys)) != len(keys):
        raise NotOneName()
    return dict(pairs)
