"""An event from outside reaches the case, or a person is shown a record: refused unless its
sender, payload and moment are right (brief, D41).
Moved from `case/runtime.py` (docs/layers/runtime-split.md).
"""

from collections.abc import Mapping

from ventoux.case.audit import Decision
from ventoux.case.definition import (
    CaseDefinition,
    DeclaredEvent,
    WaitStep,
)
from ventoux.case.runtime.runs import flag, listed, reach_unless_steered
from ventoux.case.state import (
    CaseState,
    Moment,
    Obtained,
    Sent,
    Shown,
)
from ventoux.case.visibility import may_see, seen_by
from ventoux.core.catalog import Catalog
from ventoux.core.expressions import (
    ReferenceType,
)
from ventoux.core.form import fits, misfit, read_as
from ventoux.core.person import identifier_problem
from ventoux.core.roles import role_that_counts


class ShownRefused(Exception):
    """A record shown that the case won't record, because it couldn't have been: why."""


class EventRefused(Exception):
    """An event from outside the case won't take: why, naming the event and its sender, never a
    value it carries (brief, D41)."""


def receive(case: CaseDefinition, catalog: Catalog, state: CaseState, event: Sent) -> None:
    """An event from outside reaches the case (brief, D41)."""
    if event.event not in case.events:
        known = listed(list(case.events)) if case.events else "none"
        raise EventRefused(f"{event.event} is not an event of {case.case}: its events are {known}")
    declared = case.events[event.event]
    role = sender_role(catalog, event.event, declared, event)  # who sent it, before what it carries
    refuse_payload(event.event, declared, event.payload)
    # An event is never a way back into a closed case (brief, D41). On Temporal its workflow has
    # ended, so the client's send is refused first; this holds on nothing it did.
    if state.phase == "closed":
        raise EventRefused("the case is closed: it takes no more events")
    if state.phase == "closing":
        # Refused, and the case flagged: a signal has no reply, so nobody would hear of it
        # otherwise (brief, D41). Nothing it carries lands; no rule hears it.
        sender = event.by.removeprefix("system:")
        state.history.append(
            f"refused {event.event} from {sender}: the case is closing, so it takes no more events"
        )
        flag(
            state,
            f"{event.event} from {sender} arrived while the case was closing, and was refused",
        )
        return
    arrive(case, state, event, role)


def arrive(case: CaseDefinition, state: CaseState, event: Sent, role: str | None) -> None:
    """The event has arrived: an entry of its own, each value it carries in the case file as
    `<event>.<field>`, from its sender and the field's declared mark, obtained now and by this
    arrival (brief, D12) (brief, D33) (brief, D41). The arrival is a moment for rules."""
    name = event.event
    state.arrived[name] = state.arrived.get(name, 0) + 1
    entry = f"{name}#{state.arrived[name]}"
    # A system's own name, or the person who sent it: trusted as that sender is (brief, D41).
    sender = event.by if event.by.startswith("system:") else f"person:{event.by}"
    given: list[str] = []
    for field, declared in case.events[name].payload.items():
        value = f"{name}.{field}"
        # A date's text is read into the day it names, by its declared type (brief, D66).
        state.values[value] = read_as(event.payload[field], declared.declared)
        # A mark adds distrust, never removes it, whoever sends it (brief, D12).
        state.sources[value] = frozenset(
            {sender} | ({declared.source} if declared.source else set())
        )
        state.obtained[value] = Obtained(event.at, entry)
        given.append(f"{field} from {', '.join(sorted(state.sources[value]))}")
    who = (
        f"from {event.by.removeprefix('system:')}" if role is None else f"by {event.by}, as {role}"
    )
    giving = f", giving {'; '.join(given)}" if given else ""
    state.history.append(f"{entry} {who}{giving}")
    state.moments.append(Moment(f"event {name}", entry=entry))
    # Each wait open for it is done: only an arrival after a wait opens ends it (brief, D41).
    for run in state.runs:
        waits = case.steps[run.step]
        if run.status == "open" and isinstance(waits, WaitStep) and waits.event == name:
            run.status = "done"
            del state.waiting[run.entry]
            state.history.append(f"{run.entry} done: {entry} arrived")
            done = Decision("completed", step=run.step, entry=run.entry, rule=f"steps.{run.step}")
            state.deciding.append(done)
            reach_unless_steered(state, run, waits.reaches)


def sender_role(catalog: Catalog, name: str, declared: DeclaredEvent, event: Sent) -> str | None:
    """The role that lets a person send the event, None if a system sends it; or `EventRefused`.
    One sender, as declared: its system, or a person holding one of its roles, checked as for a
    close reason (brief, D22) (brief, D41)."""
    sent_by = declared.sent_by
    if sent_by.system is not None:
        if event.by != f"system:{sent_by.system}":
            raise EventRefused(
                f"{name} is sent by {sent_by.system}, and this one comes from {event.by}"
            )
        return None
    assert sent_by.roles is not None  # one sender: a system or people (`SentBy`)
    roles = " or ".join(sent_by.roles)
    if event.by.startswith("system:"):
        raise EventRefused(f"{name} is sent by {roles}, and this one comes from {event.by}")
    # Who sent it is written one way, before anything is checked against it (brief, D22).
    if (wrong := identifier_problem(event.by)) is not None:
        raise EventRefused(wrong)
    role = role_that_counts(sent_by.roles, event.roles, catalog.roles)
    if role is None:
        counted = sorted(r for r in event.roles if r in catalog.roles)
        known = listed(counted) if counted else "no role"
        raise EventRefused(f"{name} is sent by {roles}, and {event.by} has {known}")
    return role


def refuse_payload(name: str, declared: DeclaredEvent, payload: Mapping[str, object]) -> None:
    """Refuse a payload that isn't exactly the declared one: every field given, each of its type,
    and nothing else. The type, never the value: a refusal reaches people who may not see it
    (brief, D30) (brief, D41)."""
    problems = [
        f"{name}'s payload has no {field}" for field in declared.payload if field not in payload
    ]
    fields = listed(list(declared.payload)) if declared.payload else "none"
    problems += [
        f"{name}'s payload has no field {given}: its fields are {fields}"
        for given in payload
        if given not in declared.payload
    ]
    problems += [
        misfit(f"{name}.{field}", kind.declared, payload[field], "the event")
        for field, kind in declared.payload.items()
        if field in payload and not fits(payload[field], kind.declared)
    ]
    if problems:
        raise EventRefused("\n".join(problems))


def record_shown(case: CaseDefinition, catalog: Catalog, state: CaseState, event: Shown) -> None:
    """Record that `event.by` was shown the record behind a reference: its system and reference,
    never its content (brief, D16). Refused if it couldn't have happened (brief, D30)."""
    if (wrong := identifier_problem(event.by)) is not None:
        raise ShownRefused(wrong)
    if state.phase == "closed":
        raise ShownRefused("the case is closed: nothing records it any more")
    if event.field not in case.fields:
        raise ShownRefused(f"{event.field} is not a field of {case.case}")
    declared = case.fields[event.field].declared
    if not isinstance(declared, ReferenceType):
        raise ShownRefused(f"{event.field} is not a reference: there is no record to show")
    if not may_see(case, event.field, event.roles, catalog.roles):
        needs = " or ".join(seen_by(case, event.field))
        raise ShownRefused(f"{event.by} can't see {event.field}: it needs {needs}")
    if event.field not in state.values:
        raise ShownRefused(f"{event.field} is not set: there is no record to show")
    reference = state.values[event.field]
    state.history.append(f"{event.by} was shown {event.field} ({declared.system} {reference})")
