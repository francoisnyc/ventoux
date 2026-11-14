"""A person answers a task or an approval, or names an open entry to claim; and an option's or
attachment's check comes back, so the answer it held lands or is refused (brief, D67) (brief, D68).
Moved from `case/runtime.py` (docs/layers/runtime-split.md).
"""

from typing import cast

from ventoux.case.admission import (
    latest_run,
)
from ventoux.case.answers import (
    AnswerRefused,
    judge_approval,
    judge_task,
    refuse_unless,
)
from ventoux.case.approvals import (
    tally,
    waiting_line,
)
from ventoux.case.audit import Decision, DecisionKind
from ventoux.case.claims import (
    ClaimRefused,
    held_by_another,
)
from ventoux.case.definition import (
    CallStep,
    CaseDefinition,
    TaskStep,
    WaitStep,
)
from ventoux.case.keeping import kept
from ventoux.case.migrations import Moved
from ventoux.case.recording import facts
from ventoux.case.requests import answer_change
from ventoux.case.rules import reach
from ventoux.case.runtime.opening import refuse_unless_wrapped
from ventoux.case.runtime.outcomes import outcome_problem
from ventoux.case.runtime.runs import fail, listed, marked, next_entry, proposal_spent
from ventoux.case.state import (
    Answered,
    Assigned,
    CaseState,
    Claimed,
    Command,
    Completed,
    Failed,
    GivenApproval,
    GivenBack,
    HeldAnswer,
    Holder,
    Moment,
    Obtained,
    OpenApproval,
    Schedule,
    StepRun,
    Unassigned,
)
from ventoux.core.approval import inputs_digest
from ventoux.core.catalog import Catalog
from ventoux.core.checks import OPTION, Shape, checked
from ventoux.core.expressions import (
    ExpressionError,
    a_kind,
)
from ventoux.core.person import identifier_problem
from ventoux.core.plan import APPROVE
from ventoux.core.sensitive import Sensitive, plain


def answer(
    case: CaseDefinition,
    catalog: Catalog,
    state: CaseState,
    event: Answered,
    commands: list[Command],
) -> Moved | None:
    """Record a person's answer, once judged (brief, D23); or `AnswerRefused`. An approved
    migration gives the release the case moved to (brief, D53)."""
    # Who answered is written one way, before anything is checked against it (brief, D22).
    if (wrong := identifier_problem(event.by)) is not None:
        raise AnswerRefused(wrong)
    if (request := state.changes.get(event.entry)) is not None:
        return answer_change(case, catalog, state, request, event, as_worded(state, event))
    found = open_entry(state, event.entry)
    # While someone holds an entry, only they answer it (brief, D69).
    refuse_unless(held_by_another(state, found.entry, event.by))
    if isinstance(found, StepRun) and isinstance(waits := case.steps[found.step], WaitStep):
        # Only its event ends it, sent by its sender: nobody answers it (brief, D41).
        raise AnswerRefused(sent_never_answered(found.entry, waits))
    if isinstance(found, StepRun) and (held := state.checking.get(found.entry)) is not None:
        # One answer at a time: the held one is taken or refused first (brief, D67).
        systems = listed(list(dict.fromkeys(checked_by(case, n)[1] for n in held.waiting)))
        raise AnswerRefused(
            f"{found.entry} is being checked: its answer is taken, or refused, once {systems} "
            "answers"
        )
    if isinstance(found, StepRun):
        answer_task(case, catalog, state, found, event, commands)
    else:
        answer_approval(case, catalog, state, found, event)
    return None


def sent_never_answered(entry: str, waits: WaitStep) -> str:
    """Why nobody answers, or holds, a run waiting for an event: only its sender ends it."""
    return f"{entry} waits for {waits.event}: it is sent, never answered"


def entry_to_hold(
    case: CaseDefinition, state: CaseState, event: Claimed | GivenBack | Assigned | Unassigned
) -> StepRun | OpenApproval:
    """The open task run or approval a claim or a give-back names; or `ClaimRefused`, saying what
    an answer to it would be refused with. Fail closed: only a task or an approval is held
    (brief, D69)."""
    if state.phase != "open":
        raise ClaimRefused(f"the case is {state.phase}: nothing waits for an answer")
    # Who claims is written one way, before anything is checked against it (brief, D22).
    if (wrong := identifier_problem(event.by)) is not None:
        raise ClaimRefused(wrong)
    # So is whoever an assignment names (brief, D70).
    if isinstance(event, Assigned) and (wrong := identifier_problem(event.to)) is not None:
        raise ClaimRefused(wrong)
    if event.entry in state.changes:
        raise ClaimRefused(f"{event.entry} is a change request: nobody holds one")
    try:
        found = open_entry(state, event.entry)
    except AnswerRefused as refused:
        raise ClaimRefused(str(refused)) from None
    if isinstance(found, StepRun) and isinstance(waits := case.steps[found.step], WaitStep):
        raise ClaimRefused(sent_never_answered(found.entry, waits))
    return found


def open_entry(state: CaseState, entry: str) -> StepRun | OpenApproval:
    """The open task run or approval `entry` names; a step's name names its open one."""
    for run in state.runs:
        if run.status == "open" and entry in (run.entry, run.step):
            return run
    for approval in state.approvals.values():
        if entry in (approval.entry, approval.step):
            return approval
    if entry in state.withdrawn:
        raise AnswerRefused(f"{entry} was withdrawn: {state.withdrawn[entry]}")
    # Which it was, as on a plan's waits (layer 6): an entry that has been open is closed (a
    # double click, a late answer); one that hasn't isn't open (an answer sent too early).
    if has_been_open(state, entry):
        raise AnswerRefused(f"{entry} is closed")
    raise AnswerRefused(f"{entry} isn't open")


def has_been_open(state: CaseState, entry: str) -> bool:
    """Whether `entry` names a step run the case has had, or an approval it has asked for."""
    if any(run.entry == entry for run in state.runs):
        return True
    _, _, number = entry.partition("case.change#")  # a change request (brief, D52)
    if number.isdigit() and 1 <= int(number) <= state.requested:
        return True
    step, _, count = entry.partition(".approval#")  # `pay.approval#2`: `pay`, `2`
    return count.isdigit() and 1 <= int(count) <= state.asked.get(step, 0)


def answer_task(
    case: CaseDefinition,
    catalog: Catalog,
    state: CaseState,
    run: StepRun,
    event: Answered,
    commands: list[Command],
) -> None:
    """The task run is done; its outcome, and the fields its form sets, land in the case file. An
    answer setting an option or an attachment is held, and each checked first (brief, D67)
    (brief, D68)."""
    step = case.steps[run.step]
    assert isinstance(step, TaskStep)  # only a task's run is ever open
    role = judge_task(case, catalog, run.entry, run.step, step, event)
    refuse_unless_wrapped(case, event.form or {}, AnswerRefused)
    given = checked_set(case, step, event)
    if given:
        # Nothing it sets lands, nor its outcome, until each field's system has vouched for it.
        state.checking[run.entry] = HeldAnswer(event, role, list(given))
        for name, value in given.items():
            shape, _ = checked_by(case, name)
            check = check_of(case, catalog, name)
            commands.append(Schedule(f"{run.entry}.{name}", check, {shape.asked: value}))
        return
    take_answer(case, state, run, event, role, ())


def checked_set(case: CaseDefinition, step: TaskStep, event: Answered) -> dict[str, object]:
    """Each option or attachment the answer's outcome sets, and the value its check is asked
    with, in the form's order: each waits for its system's check."""
    sets = step.outcomes[event.outcome].sets
    form = event.form or {}
    return {
        name: asked_with(case, name, str(plain(form[name])))
        for name in sets
        if checked(case.fields[name].declared) is not None
    }


def asked_with(case: CaseDefinition, name: str, value: str) -> object:
    """The value a check is asked with: a sensitive field's stays wrapped, so its check's input
    crosses Temporal sealed under the case's key, as any sensitive input does, and is forgotten
    with it (brief, D31) (brief, D68). The check's code is given the plain value."""
    return Sensitive(value) if case.fields[name].sensitive else value


def checked_by(case: CaseDefinition, name: str) -> tuple[Shape, str]:
    """The kind of check the field `name` waits for, and the system it asks."""
    found = checked(case.fields[name].declared)
    assert found is not None, f"{name} is checked by nothing"
    return found


def check_of(case: CaseDefinition, catalog: Catalog, name: str) -> str:
    """The reference of the check the field `name` waits for: its system's option check, or its
    store's."""
    shape, system = checked_by(case, name)
    check = catalog.option_check(system) if shape is OPTION else catalog.document_store(system)
    # Validation refuses a field nothing could check (UNCHECKED_OPTION, NOT_A_STORE).
    assert check is not None, f"{system} has no check for {name}"
    return check


def take_answer(
    case: CaseDefinition,
    state: CaseState,
    run: StepRun,
    event: Answered,
    role: str,
    checked_by: tuple[str, ...],
) -> None:
    """The answer, judged and, if it sets an option, vouched for, lands: the run is done."""
    step = case.steps[run.step]
    assert isinstance(step, TaskStep)
    worded = as_worded(state, event)
    run.status = "done"
    del state.waiting[run.entry]
    rule = f"steps.{run.step}.outcomes.{event.outcome}"  # what the outcome sets and reaches
    state.deciding.append(Decision("answered", step=run.step, entry=run.entry, rule=rule))
    if run.item is not None:
        # A repeated task's answer is its run's alone: it sets no field and no outcome under its
        # step's name, which each answer would overwrite (brief, D73).
        state.history.append(f"{event.by} answered {run.entry} {event.outcome} as {role}{worded}")
        state.history.append(f"{run.entry} done")
        state.moments.append(Moment(f"answered {run.step}", entry=run.entry))  # (brief, D39)
        return
    # Whom a rule asking whoever answered this task asks next, with these roles (brief, D71).
    state.answerers[run.step] = Holder(event.by, event.roles, at=event.at)
    who = f"person:{event.by}"
    # The latest answer is the outcome (brief, D9), and a form's values replace earlier ones.
    state.values[f"{run.step}.outcome"] = event.outcome
    state.sources[f"{run.step}.outcome"] = frozenset({who})
    state.obtained[f"{run.step}.outcome"] = Obtained(event.at, None)  # from a person, not a run
    sets = step.outcomes[event.outcome].sets
    for name in sets:
        state.values[name] = kept(case, name, (event.form or {})[name])
        state.sources[name] = marked(case, name, who) | vouched_for(case, name, checked_by)
        state.obtained[name] = Obtained(event.at, None)
    setting = f", setting {listed(list(sets))}" if sets else ""
    checked = f", checked by {listed(list(checked_by))}" if checked_by else ""
    state.history.append(
        f"{event.by} answered {run.entry} {event.outcome} as {role}{setting}{checked}{worded}"
    )
    state.history.append(f"{run.entry} done")
    # Each answer, whatever the outcome (brief, D39).
    state.moments.append(Moment(f"answered {run.step}", entry=run.entry))
    outcome = f"steps.{run.step}.outcomes.{event.outcome}"
    reach(state, step.outcomes[event.outcome].reaches, run.entry, outcome)
    reach(state, step.reaches, run.entry, f"steps.{run.step}.reaches")


def as_worded(state: CaseState, event: Answered) -> str:
    """What an answer's line adds when its sender says which wording its person read: `, as
    worded in refund 1, wording 2`. A draft has no wording revisions, so one naming a revision
    is refused (brief, D51)."""
    if event.wording is None:
        return ""
    if state.release is None:
        raise AnswerRefused(f"wording {event.wording} names no wording of this case: it is a draft")
    return f", as worded in {state.release}, wording {event.wording}"


def answer_approval(
    case: CaseDefinition,
    catalog: Catalog,
    state: CaseState,
    approval: OpenApproval,
    event: Answered,
) -> None:
    """An approval given, tied to the inputs it saw; or a rejection: the step won't run."""
    step = case.steps[approval.step]
    assert isinstance(step, CallStep)  # only an activity or a workflow is asked for one
    assert step.approval is not None  # only a step with an approval is asked for one
    role = judge_approval(case, catalog, state, approval.entry, approval.step, step, event)
    worded = as_worded(state, event)
    # What the approver saw: the approval's condition, then the inputs (brief, D11).
    kind: DecisionKind = "approved" if event.outcome == APPROVE else "rejected"
    read = facts(state, [step.approval.when, *step.inputs.values()])
    rule = f"steps.{approval.step}.approval"
    state.deciding.append(
        Decision(kind, step=approval.step, entry=approval.entry, rule=rule, read=read)
    )
    if event.outcome == APPROVE:
        # One entry collects the answers: it stays open until `count` different people have
        # approved it (brief, D47).
        approval.approved[event.by] = role
        if len(approval.approved) < approval.count:
            state.waiting[approval.entry] = waiting_line(approval, " or ".join(step.approval.roles))
            state.history.append(
                f"{event.by} answered {approval.entry} approve as {role}: {tally(approval)}{worded}"
            )
            return
    del state.approvals[approval.step]
    del state.waiting[approval.entry]
    given_so_far = f": {tally(approval)}" if approval.count > 1 and event.outcome == APPROVE else ""
    state.history.append(
        f"{event.by} answered {approval.entry} {event.outcome} as {role}{given_so_far}{worded}"
    )
    if event.outcome == APPROVE:
        try:
            digest = inputs_digest(step.inputs, state.values)
        except ExpressionError as error:
            # Fail closed: an approval of inputs nobody can read approves nothing.
            fail(state, approval.step, f"the inputs of {approval.step} can't be read: {error}")
            return
        first, *others = approval.approved
        state.given[approval.step] = GivenApproval(
            approval.entry, first, digest, approval.seen, tuple(others)
        )
        return
    # One rejection rejects the entry, whatever was approved before (brief, D23) (brief, D47).
    rejected = f"{event.by} rejected {approval.entry}"
    if approval.approved:
        rejected += f", which {len(approval.approved)} of {approval.count} had approved"
    latest = latest_run(state, approval.step)
    if latest is not None and latest.status == "retrying":
        # A rejected rescue resolves nothing: the failed run may or may not have acted, so it
        # needs attention again, as the run it is, never a new one (brief, D17) (brief, D26).
        latest.status = "failed"
        latest.reason = (
            f"{event.by} rejected {approval.entry}, the approval of its retry: retry it to ask "
            "again, or close the case"
        )
        state.history.append(f"{latest.entry} won't run: {rejected}, so it needs attention again")
        return
    # A rejection is an outcome: the step doesn't run (brief, D23).
    entry = next_entry(state, approval.step)
    proposal_spent(state, approval.step)  # the proposed run is over
    state.runs.append(StepRun(entry, approval.step, "rejected", started=False))
    state.history.append(f"{entry} won't run: {rejected}")


def not_taken(held: HeldAnswer, entry: str, why: str) -> str:
    """The line saying the held answer at `entry` is not taken: a check couldn't say whether its
    system vouches for the value. Never read as vouched for (fail closed), and the case doesn't
    need attention: answering again fixes it, so the task waits for an answer (brief, D67)."""
    return (
        f"{held.answered.by}'s answer {held.answered.outcome} to {entry} is not taken: {why}; "
        "the task waits for an answer"
    )


def vouched_for(case: CaseDefinition, name: str, checks: tuple[str, ...]) -> frozenset[str]:
    """The system that vouched for the option or attachment `name`, as a source beside the
    person who gave it; none for any other field (brief, D67) (brief, D68)."""
    found = checked(case.fields[name].declared)
    if found is None:
        return frozenset()
    # Only a value its check vouched for is ever taken: one that wasn't checked is a bug.
    assert checks, f"{name} is checked, and was taken with no check"
    return frozenset({f"system:{found[1]}"})


def checked_answer(state: CaseState, entry: str) -> tuple[str, str] | None:
    """The held answer's entry and the option field `entry` checks, if `entry` is a check's run,
    `assess#1.branch`; else None."""
    held, _, name = entry.rpartition(".")
    if held in state.checking and name in state.checking[held].waiting:
        return held, name
    return None


def check_answered(
    case: CaseDefinition,
    catalog: Catalog,
    state: CaseState,
    checking: tuple[str, str],
    event: Completed,
) -> None:
    """A check answered: what it says of the value is noted, and the held answer is decided once
    every check it waits for is back (brief, D67) (brief, D68)."""
    entry, name = checking
    held = state.checking[entry]
    shape, system = checked_by(case, name)
    check = catalog.get(check_of(case, catalog, name))
    answered = event.output.get(shape.answer)
    # Read by its contract first, as every output is: an answer it doesn't describe says nothing,
    # neither vouched for nor refused (fail closed) (brief, D67).
    if (problem := outcome_problem(check, event)) is not None:
        held.problems[name] = not_taken(held, entry, problem)
    # Read by its exact type too: Pydantic reads "yes" and 1 as true, and "no" as false, so a
    # garbled answer would vouch, or speak for the system. Only `true` or `false` answers.
    elif type(answered) is not bool:
        held.problems[name] = not_taken(
            held,
            entry,
            f"{check.reference} gave {shape.answer} as {a_kind(answered)}, and {shape.kind} "
            "answers true or false",
        )
    elif answered is not True:
        # Refused, and the refusal recorded: the field and the system, never the value, which may
        # be hidden from whoever reads the history (brief, D30).
        refused = shape.refused.format(system=system)
        held.problems[name] = (
            f"refused {held.answered.by}'s answer {held.answered.outcome}: {name} {refused}"
        )
    check_back(case, catalog, state, entry, name)


def check_back(
    case: CaseDefinition, catalog: Catalog, state: CaseState, entry: str, name: str
) -> None:
    """`name`'s check is back. Until every check is, the answer stays held, so a second answer is
    refused and a late check never speaks for a new one; then it is decided (brief, D67)."""
    held = state.checking[entry]
    held.waiting.remove(name)
    if held.waiting:
        return  # another check isn't back yet
    del state.checking[entry]
    run = next(run for run in state.runs if run.entry == entry)
    if run.status == "cancelled":
        # The close waited for the checks (brief, D10); the task it cancelled takes nothing.
        state.history.append(
            f"{held.answered.by}'s answer {held.answered.outcome} to {entry} is not taken: the "
            "case closed while it was checked"
        )
        return
    step = cast(TaskStep, case.steps[run.step])
    fields = checked_set(case, step, held.answered)
    # The first problem in the answer's own order, so the line never depends on which check
    # came back first. The task stays open for a new answer.
    problems = [held.problems[field] for field in fields if field in held.problems]
    if problems:
        state.history.append(problems[0])
        return
    checks = tuple(dict.fromkeys(check_of(case, catalog, field) for field in fields))
    take_answer(case, state, run, held.answered, held.role, checks)


def check_failed(case: CaseDefinition, catalog: Catalog, state: CaseState, event: Failed) -> bool:
    """Whether the failed activity was a check: then nothing it would have said is known, so the
    held answer won't be taken, once its other checks are back; the task waits for an answer
    (brief, D67)."""
    if (checking := checked_answer(state, event.entry)) is None:
        return False
    entry, name = checking
    held = state.checking[entry]
    held.problems[name] = not_taken(held, entry, event.reason)
    check_back(case, catalog, state, entry, name)
    return True
