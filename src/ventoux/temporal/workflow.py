"""A plan as a Temporal workflow: the same interpreter, with Temporal's activities, signals and
timers (layer 6).

A workflow only decides; Temporal replays it from its history after a crash, so it must ask for
the same things in the same order every time. The interpreter reads no clock, randomness or I/O
(`tests/test_layers.py`), and everything it asks for goes through `call` and `wait` below.
"""

from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any, ClassVar

from temporalio import workflow
from temporalio.exceptions import ActivityError, ApplicationError, FailureError

# Temporal: the workflow sandbox imports a workflow's modules afresh for every run, to keep runs
# apart; modules passed through are imported once and shared. `core` is deterministic (the
# boundary test holds it to that), so it is shared.
with workflow.unsafe.imports_passed_through():
    from ventoux.core.catalog import Catalog
    from ventoux.core.history import Refused
    from ventoux.core.interpreter import (
        TIMEOUT,
        Answer,
        Outcome,
        PlanRun,
        RunRefused,
        interpret,
    )
    from ventoux.core.plan import PlanInvalid, parse_plan
    from ventoux.core.provenance import sourced
    from ventoux.core.sensitive import Sensitive
    from ventoux.temporal.activities import OUTCOME
    from ventoux.temporal.options import activity_options


# What each unit of a plan's duration (`48h`) is, as a Temporal timer reads it.
UNITS = {"s": "seconds", "m": "minutes", "h": "hours", "d": "days"}


def duration(text: str) -> timedelta:
    """A plan's duration, such as `48h`, as a timedelta. `parse_plan` checked its shape."""
    return timedelta(**{UNITS[text[-1]]: int(text[:-1])})


@dataclass
class Given:
    """A field's value, and where it came from."""

    value: Any  # the value: a number (exact), a text, a boolean
    sources: list[str]  # where it came from, such as `system:orders` (brief, D12)


@dataclass
class PlanStart:
    """What a run starts with."""

    plan: dict[str, Any]  # the plan, as stored data
    fields: dict[str, Given]  # every field the plan declares, with its sources
    # When a case runs the plan as a step, the case names the run in its keys
    # (`refund-1/<first run ID>/settle#1`) (brief, D28); None: the workflow's ID and run ID.
    run_name: str | None = None
    # Each person who approves nothing in this run, and why: the case's opener and the step's
    # proposer (brief, D25).
    excluded: dict[str, str] | None = None


@dataclass
class RunReport:
    """How a run went: what `run_plan` reports in memory."""

    # succeeded, failed, waiting or stopped; cancelled when the case running it as a step closed
    # (brief, D28); None while it runs.
    status: str | None
    reason: str | None  # why it stopped, if it did
    history: list[str]  # every event so far, one line each
    waiting_at: str | None = None  # the wait open for an answer, such as `approve_refund#1`
    # Each activity that finished or failed after the case running this plan began closing, for
    # the case to flag as it flags a step's run (brief, D10), never hidden (brief, D28):
    # `payments.refund@2 completed after the close was requested`.
    after_stop: list[str] = field(default_factory=list[str])


@dataclass
class Sent:
    """An answer, as a person sends it to a wait."""

    wait: str  # the entry it answers, such as `approve_refund#1`: its state and entry count
    outcome: str  # one of the wait's outcomes, such as `approve`
    by: str  # who answered
    # Their roles, as the Ventoux API states them; recorded in history with the signal, so a
    # replay decides as the first run did, whatever their roles are now (brief, D22).
    roles: list[str]
    form: dict[str, Any] | None = None  # the values the outcome sets, if any


class ActivityFailed(Exception):
    """An activity that still failed after the retries its contract allows."""


# Why a plan stopped by its case ends, and why it starts nothing new (brief, D28).
CASE_CLOSING = "the case is closing"


class CaseClosing(Exception):
    """An activity the plan would start after its case began closing: never scheduled."""


class PlanWorkflow:
    """The code of a plan workflow. A deployment subclasses it to name its catalog, and registers
    the subclass (Temporal's SDK wants `@workflow.run` on the class it registers):

        @workflow.defn(name="ventoux.plan")
        class RefundPlans(PlanWorkflow):
            catalog = CATALOG

            @workflow.run
            async def run(self, start: PlanStart) -> RunReport:
                return await self.interpret(start)
    """

    catalog: ClassVar[Catalog]  # the contracts this deployment's plans may call

    def __init__(self) -> None:
        self.record = PlanRun()  # the run and its history, written by the interpreter and here
        self.open: str | None = None  # the entry answers go to now, such as `approve_refund#1`
        self.opened: set[str] = set()  # every entry that has been open
        self.sent: list[Sent] = []  # answers to the open entry, not yet taken, in order
        self.waiting = False  # whether a wait is waiting for an answer now
        self.stopping = False  # whether the case running this plan as a step is closing
        self.cancelled = False  # whether the run ended because its case closed
        self.after_stop: list[str] = []  # activities that ended after the stop, for the case

    # Temporal: a signal is a message into a running workflow, recorded in its history, so replay
    # delivers it again at the same point.
    @workflow.signal(name="answer")
    def answer(self, sent: Sent) -> None:
        # An answer counts only for the entry open when it comes: one approval unlocks one run of
        # one step (brief, D11). Any other is refused, and recorded, never kept for a later wait:
        # a double click would approve the retry, an early click a wait nobody has seen.
        if self.stopping or sent.wait != self.open:
            self.refuse(sent)
        else:
            self.sent.append(sent)

    @workflow.signal(name="stop")
    def stop(self) -> None:
        """The case running this plan as a step is closing (brief, D28): the open wait is
        cancelled, answers are refused, and nothing new starts; an activity already running
        finishes (brief, D10)."""
        self.stopping = True

    def refuse(self, sent: Sent) -> None:
        """Record `sent` as refused: its entry is closed, or hasn't opened."""
        state = "is closed" if sent.wait in self.opened else "isn't open"
        self.record.history.append(Refused(sent.outcome, sent.by, f"{sent.wait} {state}"))

    def close(self) -> None:
        """Close the open entry: answers left for it are refused, and recorded."""
        self.open = None
        for sent in self.sent:
            self.refuse(sent)
        self.sent.clear()

    # Temporal: a query reads a workflow's state without changing it, and isn't recorded.
    @workflow.query(name="report")
    def report(self) -> RunReport:
        """How the run is going: its history so far, and the wait open for an answer, if any."""
        if self.cancelled:
            history = [str(event) for event in self.record.history]
            return RunReport("cancelled", CASE_CLOSING, history, after_stop=self.after_stop)
        status = self.record.status or ("waiting" if self.waiting else None)
        return RunReport(
            status,
            self.record.reason,
            [str(event) for event in self.record.history],
            self.open if self.waiting else None,
        )

    async def run(self, start: PlanStart) -> RunReport:
        return await self.interpret(start)

    async def interpret(self, start: PlanStart) -> RunReport:
        try:
            plan = parse_plan(start.plan)
            fields = {
                name: sourced(given.value, *given.sources) for name, given in start.fields.items()
            }
            await interpret(
                plan,
                fields,
                self.catalog,
                self.call,
                self.wait,
                run_name=start.run_name or self.name(),
                record=self.record,
                excluded=start.excluded,
            )
        except (RunRefused, PlanInvalid) as refused:
            # A run that can't start fails at once, saying why. Any other exception fails only the
            # workflow task, which Temporal retries until fixed code is deployed (brief, D17).
            raise ApplicationError(str(refused), type="RunRefused", non_retryable=True) from None
        self.close()  # an answer left for the last wait is refused, and recorded
        # Cut short by the close: neither a failure nor a wait anyone will answer.
        self.cancelled = self.stopping and self.record.status in ("waiting", "stopped")
        return self.report()

    def name(self) -> str:
        """This run's name in its idempotency keys: the workflow's ID and run ID (brief, D17)."""
        info = workflow.info()  # recorded in history, so the same on replay
        return f"{info.workflow_id}/{info.run_id}"

    async def call(self, reference: str, inputs: dict[str, Any]) -> dict[str, Any]:
        """Schedule the activity, retried and timed out as its contract says (brief, D17)."""
        self.close()  # the run has moved on from its last wait
        if self.stopping:
            raise CaseClosing(CASE_CLOSING)  # nothing new starts (brief, D10)
        contract = self.catalog.get(reference)
        # Temporal: the result is recorded in history; on replay it is read back, never called
        # again.
        try:
            output: dict[str, Any] = await workflow.execute_activity(
                reference, inputs, **activity_options(contract), result_type=dict
            )
        except ActivityError as error:
            # Past its retries: the interpreter stops the step (brief, D17). What the activity
            # said is never recorded: its reason reads `‹sensitive›` (brief, D31).
            cause = error.cause
            if isinstance(cause, ApplicationError) and cause.type == OUTCOME:
                self.ended_after_stop(f"{reference} completed")
                raise Outcome(cause.message) from None  # read as in memory: `declined`
            said = cause.message if isinstance(cause, FailureError) else str(error)
            self.ended_after_stop(f"{reference} failed", said)
            raise ActivityFailed(said) from None
        self.ended_after_stop(f"{reference} completed")
        return output

    def ended_after_stop(self, what: str, said: str | None = None) -> None:
        """Note an activity that ended after the case began closing: it ran on, since it may have
        moved money (brief, D10), and the case flags it, as it flags a step (brief, D28)."""
        if self.stopping:
            line = f"{what} after the close was requested"
            # What the activity said is never recorded: it may quote a sensitive value (brief, D31).
            self.after_stop.append(line if said is None else f"{line}: {Sensitive(said)}")

    async def wait(
        self, state: str, entry: str, outcomes: tuple[str, ...], timeout: str | None
    ) -> Answer | None:
        """The first answer sent to the open `entry`. The interpreter checks it, and asks again
        for the same entry if it refuses it (an outcome the wait doesn't offer)."""
        if entry != self.open:
            self.close()  # answers left for an earlier wait never count for this one
            self.open = entry
            self.opened.add(entry)
        if self.stopping:
            self.close()  # the case is closing: this wait is cancelled
            return None
        self.waiting = True
        try:
            # Temporal: `wait_condition` blocks until the condition holds, checked after each
            # signal. With a timeout, it is a durable Temporal timer: the server fires it and
            # history records it, so replay reads it back and no clock is read.
            await workflow.wait_condition(
                lambda: bool(self.sent) or self.stopping,
                timeout=None if timeout is None else duration(timeout),
            )
        except TimeoutError:
            self.close()
            return Answer(TIMEOUT, None)  # from the timer, never from a person
        finally:
            self.waiting = False
        if self.stopping:
            self.close()  # the case closed while this waited: cancelled, answers left refused
            return None
        sent = self.sent.pop(0)
        return Answer(sent.outcome, sent.by, frozenset(sent.roles), sent.form)
