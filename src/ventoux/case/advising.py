"""What the step advisor is shown of a case: names, kinds and states, never a value (brief, D61).

Pure, so it is computed where the case's state is: in memory, or in the worker on Temporal, where a
view is filtered so nothing hidden leaves it (brief, D30) (brief, D62). The request a model reads is
built from it in `ventoux.authoring`, which the worker never imports.
"""

from dataclasses import dataclass

from ventoux.case.definition import CaseDefinition
from ventoux.case.reading import kind_of
from ventoux.case.runtime import proposal_refused
from ventoux.case.state import CaseState
from ventoux.case.visibility import may_see
from ventoux.core.catalog import Catalog


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
class AdvisorView:
    """What the advisor is shown of a case: never a case-file value, a person's identifier or a
    history line (brief, D61)."""

    case: str  # the case definition's name
    title: str
    fields: tuple[FieldShown, ...]  # in the definition's order
    milestones: tuple[str, ...]  # reached, in order
    runs: tuple[RunShown, ...]  # each step's latest run, in the order the steps are written
    waiting_for: tuple[str, ...]  # what waits on people, as the inbox says it: roles, never names
    steps: tuple[StepShown, ...]  # the steps the person's proposal would be admitted for now


def advisor_view(
    case: CaseDefinition,
    catalog: Catalog,
    state: CaseState,
    by: str,
    roles: frozenset[str],
    at: int,
) -> AdvisorView:
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
    return AdvisorView(
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
