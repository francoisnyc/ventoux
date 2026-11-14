"""The case opens with its first values: each of its field's type, from a registered system,
and a sensitive one wrapped.
Moved from `case/runtime.py` (docs/layers/runtime-split.md).
"""

from collections.abc import Mapping

from ventoux.case.answers import (
    AnswerRefused,
)
from ventoux.case.definition import (
    CaseDefinition,
    form_fields,
    rule_fields,
)
from ventoux.case.engine import known
from ventoux.case.keeping import kept
from ventoux.case.runtime.runs import listed, marked
from ventoux.case.state import (
    CaseState,
    Holder,
    Moment,
    Obtained,
    Opened,
)
from ventoux.case.writers import OPENER
from ventoux.core.catalog import Catalog
from ventoux.core.checks import checked
from ventoux.core.form import fits, misfit
from ventoux.core.person import identifier_problem
from ventoux.core.references import unregistered
from ventoux.core.sensitive import Sensitive, plain


class CaseRefused(Exception):
    """A case the engine won't open: what is wrong with its first values."""


def open_case(case: CaseDefinition, catalog: Catalog, state: CaseState, event: Opened) -> None:
    """The case file's first values, each of its field's type and saying where it came from:
    the person who opened the case, or the system that did (brief, D12)."""
    if event.by is not None and (wrong := identifier_problem(event.by)) is not None:
        raise CaseRefused(wrong)
    refuse_to_open(case, catalog, event.file)
    refuse_unless_wrapped(case, event.file, CaseRefused)
    state.opened_by = event.by
    if event.by is not None:
        state.opener = Holder(event.by, event.roles, at=event.at)
    state.engine = known(event.engine)  # set once, here, never by itself after (brief, D51)
    state.release = event.release
    state.cases = dict(event.cases)  # the children its release pins (brief, D74)
    state.excluded = dict(event.excluded)  # a child's parent's exclusions cross (brief, D25)
    if event.release is not None:  # a draft's history is as it was before releases
        state.history.append(f"opened on {event.release}, engine {state.engine}")
    origin = OPENER if event.by is None else f"person:{event.by}"
    for name, value in event.file.items():
        state.values[name] = kept(case, name, value)
        # A child's value keeps the sources it had in its parent: a budget a person set is still
        # that person's (brief, D74).
        given = None if event.sources is None else event.sources.get(name)
        state.sources[name] = marked(case, name, origin) if given is None else given
        state.obtained[name] = Obtained(event.at, None)  # from the opening, by no step run
    opener = event.by or OPENER
    if event.parent is not None:  # opened by its parent case, never by a person (brief, D74)
        opener = f"{event.parent[0]}, from {event.parent[1]}"
    state.history.append(f"opened by {opener}, with {listed(sorted(event.file))}")
    state.moments.append(Moment("opened"))


def refuse_to_open(case: CaseDefinition, catalog: Catalog, file: Mapping[str, object]) -> None:
    """Refuse a case whose references name systems nobody registered, or whose fields are
    declared untrusted with labels nobody registered, and first values that aren't the case's
    fields, of their types, given at the opening."""
    setters = form_fields(case)
    computed = rule_fields(case)
    declared_types = {name: field.declared for name, field in case.fields.items()}
    problems = unregistered(declared_types, catalog.systems)
    # A label the engine doesn't know is refused, never taken as a new kind of untrusted
    # (brief, D12) (brief, D35).
    problems += [
        f"{name} is declared {field.source}, a label nobody registered"
        for name, field in case.fields.items()
        if field.source is not None
        and field.source.removeprefix("untrusted:") not in catalog.labels
    ]
    # So for what an event says of itself: its sender and its marks (brief, D30) (brief, D41).
    for name, event in case.events.items():
        if event.sent_by.system is not None and event.sent_by.system not in catalog.systems:
            problems.append(f"{name} is sent by {event.sent_by.system}, a system nobody registered")
        problems += [
            f"{name}.{field} is declared {carried.source}, a label nobody registered"
            for field, carried in event.payload.items()
            if carried.source is not None
            and carried.source.removeprefix("untrusted:") not in catalog.labels
        ]
    for name, value in file.items():
        if name not in case.fields:
            fields = listed(sorted(case.fields))
            problems.append(f"{name} is not a field of {case.case}: its fields are {fields}")
        # One source per field: a person's form sets it, so the opening never gives it.
        elif name in setters:
            problems.append(
                f"{name} is set by a person in {setters[name]}, never given at the opening"
            )
        elif name in computed:
            problems.append(
                f"{name} is set by rules, in {computed[name]}, never given at the opening"
            )
        elif (found := checked(declared := case.fields[name].declared)) is not None:
            # Nothing at the opening could check it: only a person's answer gives one
            # (brief, D67) (brief, D68).
            shape, system = found
            problems.append(
                f"{name} is {shape.of} {system}, and only a person's answer gives one, when it "
                "can be checked: leave it out of the opening"
            )
        elif not fits(plain(value), declared):
            # The type, never the value: refusals reach people who may not see it (brief, D30).
            problems.append(misfit(name, declared, plain(value), "the opening"))
    if problems:
        raise CaseRefused("\n".join(problems))


def refuse_unless_wrapped(
    case: CaseDefinition,
    values: Mapping[str, object],
    refused: type[CaseRefused] | type[AnswerRefused],
) -> None:
    """Refuse a sensitive field's value that arrived unwrapped: it has already crossed in plain
    text, so the case says so loudly. Checked here, on nothing the client did (brief, D31)."""
    for name, value in values.items():
        if name in case.fields and case.fields[name].sensitive and not isinstance(value, Sensitive):
            raise refused(
                f"{name} is sensitive and was given in plain text: send it through "
                "ventoux.temporal.cases, which encrypts it"
            )
