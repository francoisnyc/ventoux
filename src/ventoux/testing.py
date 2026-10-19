"""Run cases in memory, in tests: no Temporal server, scripted answers, fake activities."""

import asyncio
import json
import shutil
import tempfile
from collections.abc import Iterable, Mapping, Sequence
from decimal import Decimal
from pathlib import Path
from typing import Annotated, Any, NamedTuple

from pydantic import BaseModel
from temporalio import workflow
from temporalio.converter import DataConverter

from ventoux.case.admission import ProposalRefused, RetryRefused, StepStopped
from ventoux.case.answers import AnswerRefused
from ventoux.case.closing import CloseRefused
from ventoux.case.definition import CaseDefinition, parse_case
from ventoux.case.freshness import seconds_in
from ventoux.case.memory import Activity, CaseRun, Finish, PlanRunner, run_case_in_memory
from ventoux.case.plan_step import PlanNotSupplied, supplied, wrong_references
from ventoux.case.runtime import CaseRefused, EventRefused
from ventoux.case.state import (
    Answered,
    CloseAsked,
    Completed,
    Event,
    Failed,
    ForgetApproved,
    Opened,
    Proposed,
    Retried,
    Sent,
    Shown,
    StartPlan,
)
from ventoux.core.before_activity import InputRefused
from ventoux.core.catalog import Catalog
from ventoux.core.contract import ActivityContract, Display, RetryPolicy, Timeouts
from ventoux.core.interpreter import Answer, Outcome, PlanRun, RunRefused, Wait, interpret
from ventoux.core.output_sources import source
from ventoux.core.plan import parse_plan
from ventoux.core.policy import trusted_only
from ventoux.core.provenance import Sourced
from ventoux.core.references import reference
from ventoux.core.sensitive import Sensitive, unwrapped
from ventoux.core.workflow_contract import WorkflowContract
from ventoux.temporal.cases import CaseReport, CaseStart, CaseWorkflow
from ventoux.temporal.contract_check import check_workflow_contract
from ventoux.temporal.forget import ForgetReport, ForgetStart, ForgetWorkflow
from ventoux.temporal.workflow import PlanStart, PlanWorkflow, RunReport

# Temporal: this module defines workflows, so the workflow sandbox imports it afresh for each run;
# the converter and the key provider are passed through, imported once: `cryptography` is compiled
# code, which can't be imported twice.
with workflow.unsafe.imports_passed_through():
    from ventoux.temporal.converter import data_converter
    from ventoux.tooling.keys import FileKeys

__all__ = [
    "Activity",
    "AnswerRefused",
    "CaseRefused",
    "CloseRefused",
    "DevelopmentCases",
    "DevelopmentPlans",
    "EventRefused",
    "InputRefused",
    "Outcome",
    "ProposalRefused",
    "RetryRefused",
    "StepStopped",
    "check_workflow_contract",
    "close",
    "finish",
    "load_definition",
    "propose",
    "retry",
    "run_case",
    "run_plan",
    "send",
    "shown",
]


# The activities guide's contract, word for word: its test checks the two hash the same.
class RefundInput(BaseModel):
    # Python typing: `Annotated[type, …]` is the type, plus something attached to it for whoever
    # reads the field. Here Ventoux reads the input policy (brief, D21).
    order_id: Annotated[str, trusted_only()]  # never an order chosen by an AI or a customer
    amount: Annotated[Decimal, trusted_only()]  # never an amount typed by a customer
    idempotency_key: str  # filled by the engine, never by a definition


class RefundOutput(BaseModel):
    refund_id: str


# @2 added the input policies; @1, without them, is retired (docs/layers/04-provenance.md).
payments_refund = ActivityContract(
    name="payments.refund",
    version=2,
    input=RefundInput,
    output=RefundOutput,
    risk="high",
    effect="write",
    timeouts=Timeouts(start_to_close=30, schedule_to_start=60),
    retry=RetryPolicy(maximum_attempts=5, initial_interval=1, backoff_coefficient=2),
    idempotency_key="idempotency_key",
    outcomes=["declined"],
    display=Display(
        title="Refund a customer",
        description="Refunds an order through the payment provider.",
        outcomes={"declined": "The payment provider declined the refund"},
    ),
)


class LookupInput(BaseModel):
    order_id: str


class LookupOutput(BaseModel):
    status: str


orders_lookup = ActivityContract(
    name="orders.lookup",
    version=1,
    input=LookupInput,
    output=LookupOutput,
    risk="low",
    effect="read",  # reads only, so no idempotency key
    timeouts=Timeouts(start_to_close=10, schedule_to_start=60),
    retry=RetryPolicy(maximum_attempts=3, initial_interval=1, backoff_coefficient=2),
    idempotency_key=None,
    outcomes=["not_found"],
    display=Display(
        title="Look up an order",
        description="Reads an order's status from the orders system.",
        outcomes={"not_found": "No such order"},
    ),
)


class DraftInput(BaseModel):
    to_customer: Annotated[str, trusted_only()]  # never an address chosen by an AI
    template: str
    idempotency_key: str


class DraftOutput(BaseModel):
    draft_id: str


# @2 added the input policy on `to_customer`; @1 is retired.
letters_draft = ActivityContract(
    name="letters.draft",
    version=2,
    input=DraftInput,
    output=DraftOutput,
    risk="low",  # it only drafts: a person reviews and sends
    effect="write",
    timeouts=Timeouts(start_to_close=30, schedule_to_start=60),
    retry=RetryPolicy(maximum_attempts=5, initial_interval=1, backoff_coefficient=2),
    idempotency_key="idempotency_key",
    outcomes=[],
    display=Display(
        title="Draft a letter",
        description="Drafts a letter to a customer for a person to review. Never sends.",
    ),
)


# The activities guide's letter, word for word: it takes the customer's reference, a crm record,
# and fetches the address itself, so the address never enters the case (brief, D8) (brief, D30).
class LetterInput(BaseModel):
    customer: Annotated[str, trusted_only(), reference("crm")]  # the letter's addressee, by ID
    template: str
    idempotency_key: str


# @3 takes a reference where @2 takes an address: a different input, not @2 made stricter, so @2
# stays (docs/layers/09-case-data.md, 9a).
letters_draft_3 = ActivityContract(
    name="letters.draft",
    version=3,
    input=LetterInput,
    output=DraftOutput,
    risk="low",  # it only drafts: a person reviews and sends
    effect="write",
    timeouts=Timeouts(start_to_close=30, schedule_to_start=60),
    retry=RetryPolicy(maximum_attempts=5, initial_interval=1, backoff_coefficient=2),
    idempotency_key="idempotency_key",
    outcomes=[],
    display=Display(
        title="Draft a letter to a customer",
        description="Looks up the customer's address in the CRM and drafts a letter for a "
        "person to review. Never sends.",
    ),
)


# The activities guide's workflow contract, word for word: an existing Temporal workflow run as one
# step (brief, D6). Its outputs say where each value comes from (brief, D29).
class KycInput(BaseModel):
    customer_id: Annotated[str, trusted_only()]


class KycOutput(BaseModel):
    status: Annotated[str, source("system:kyc")]  # the KYC system decides it
    risk_score: Annotated[Decimal, source("system:kyc")]
    analyst_notes: Annotated[str, source("untrusted:llm")]  # a model writes it from documents
    contact_email: str  # nothing declared: untrusted:undeclared


kyc_check = WorkflowContract(
    name="kyc.check",
    version=1,
    input=KycInput,
    output=KycOutput,
    risk="low",
    effect="read",
    timeout=600,  # seconds: the longest the workflow may run
    idempotency_key=None,  # a write or notify workflow names its input for the key
    display=Display(title="Check a customer", description="Runs the KYC checks on a customer."),
)


class LookupOutputFromOrders(BaseModel):
    status: Annotated[str, source("system:orders")]  # the orders system says it


# @2 declares where `status` comes from, so a case may decide on it (brief, D29) (brief, D39); @1, which
# declares nothing, stays: a case adopts @2 by naming it. No fake implements it: each test that
# runs it says what it returns, so one left on @1 fails loudly.
orders_lookup_2 = ActivityContract(
    name="orders.lookup",
    version=2,
    input=LookupInput,
    output=LookupOutputFromOrders,
    risk="low",
    effect="read",  # reads only, so no idempotency key
    timeouts=Timeouts(start_to_close=10, schedule_to_start=60),
    retry=RetryPolicy(maximum_attempts=3, initial_interval=1, backoff_coefficient=2),
    idempotency_key=None,
    outcomes=["not_found"],
    display=Display(
        title="Look up an order",
        description="Reads an order's status from the orders system.",
        outcomes={"not_found": "No such order"},
    ),
)

# The development catalog: what a case can call in tests and the quickstart.
CATALOG = Catalog()
# The labels fields and outputs may be declared untrusted with: `untrusted:llm`. First, since a
# contract's outputs may name them.
for label in ("customer", "document", "email", "llm", "web"):
    CATALOG.register_label(label)
# The systems references may name, before the contracts whose inputs name them (brief, D30).
for system in ("crm", "documents", "orders", "policies"):
    CATALOG.register_system(system)
for contract in (
    payments_refund,
    orders_lookup,
    orders_lookup_2,
    letters_draft,
    letters_draft_3,
    kyc_check,
):
    CATALOG.register(contract)
# The roles waits and approvals may name: support answers tasks, a team lead approves refunds.
CATALOG.register_role("support")
CATALOG.register_role("support-lead", approves="high")
# The case data guide's claim: an adjuster assesses it, and only fraud sees its fraud score.
CATALOG.register_role("adjuster")
CATALOG.register_role("fraud")
# Only claims-sensitive sees the claim's national ID (layer 9b).
CATALOG.register_role("claims-sensitive")
# Operations acts on a case's failed steps: retries them, or closes the case (brief, D26).
CATALOG.register_role("operations", operates=True)
CATALOG.register_role("privacy", forgets=True)  # the guide's data protection role (layer 9c)


# Fake implementations, against no real system: nothing is paid, read or sent.
def fake_refund(inputs: dict[str, Any]) -> dict[str, Any]:
    return {"refund_id": f"refund-{inputs['order_id']}"}


def fake_lookup(inputs: dict[str, Any]) -> dict[str, Any]:
    return {"status": "delivered"}


def fake_draft(inputs: dict[str, Any]) -> dict[str, Any]:
    return {"draft_id": f"draft-{inputs['template']}"}


FAKES: dict[str, Activity] = {
    "payments.refund@2": fake_refund,
    "orders.lookup@1": fake_lookup,
    "letters.draft@2": fake_draft,
    "letters.draft@3": fake_draft,
}


def fake_kyc(inputs: dict[str, Any]) -> dict[str, Any]:
    """The KYC workflow, in memory: a clear customer, as the KYC team's code would say."""
    return {
        "status": "clear",
        "risk_score": Decimal(12),
        "analyst_notes": "No concerns in the documents.",
        "contact_email": f"{inputs['customer_id']}@example.com",
    }


# The workflows a case's workflow steps run in memory, by contract: each one bound (brief, D29).
WORKFLOW_FAKES: dict[str, Activity] = {"kyc.check@1": fake_kyc}


# Temporal: a workflow class is registered with a worker under its name; this one runs plans
# against the development catalog, in tests and the development worker.
@workflow.defn(name="ventoux.plan")
class DevelopmentPlans(PlanWorkflow):
    catalog = CATALOG

    @workflow.run
    async def run(self, start: PlanStart) -> RunReport:
        return await self.interpret(start)


# Temporal: the development case workflow, for tests and the development worker: the development
# catalog, and no plans (a test gives its own).
@workflow.defn(name="ventoux.case")
class DevelopmentCases(CaseWorkflow):
    catalog = CATALOG

    @workflow.run
    async def run(self, start: CaseStart) -> CaseReport:
        return await self.drive(start)


# Temporal: the development request to forget a case: the development catalog, whose `privacy`
# role may forget (layer 9c).
@workflow.defn(name="ventoux.forget")
class DevelopmentForget(ForgetWorkflow):
    catalog = CATALOG

    @workflow.run
    async def run(self, start: ForgetStart) -> ForgetReport:
        return await self.drive(start)


def development_converter() -> DataConverter:
    """Ventoux's data converter with a fresh development key file, for one test server: tests
    reuse workflow IDs, and a case's key is never made twice (brief, D31)."""
    # Python: `mkdtemp` makes a new, empty directory under the system's temporary one.
    return data_converter(FileKeys(Path(tempfile.mkdtemp()) / "keys.json"))


def fixture_converter(history: Path) -> DataConverter:
    """Ventoux's data converter with the development key file recorded beside a history fixture
    (`<name>.keys.json`), copied, so a fixture whose answers are sealed replays (brief, D31)."""
    keys = Path(tempfile.mkdtemp()) / "keys.json"
    shutil.copy(history.with_suffix(".keys.json"), keys)
    return data_converter(FileKeys(keys))


def load_definition(path: Path) -> dict[str, Any]:
    """Read a case definition from its JSON file (I/O, so here and not in `case`)."""
    # Numbers as exact decimals, never binary floats (brief, D20). Its shape is checked when a
    # case runs (`parse_case`); case validation, provenance and deadlocks, is layer 10's.
    definition: dict[str, Any] = json.loads(path.read_text(), parse_float=Decimal)
    return definition


# When a test's case opens unless it says otherwise: 1 January 2026, 00:00 UTC, in seconds since the
# epoch. Tests give the time; the engine never supplies one (brief, D33).
START = 1_767_225_600
DAY = 24 * 60 * 60  # a day, in seconds: `START + 3 * DAY`


def run_case(
    definition: dict[str, Any],
    file: dict[str, Any],
    answers: Sequence[Any],
    people: Mapping[str, Iterable[str]],
    opened_by: str | None = None,
    activities: Mapping[str, Activity] = FAKES,
    held: Iterable[str] = (),
    plans: Mapping[str, Any] | None = None,
    plan_answers: Mapping[str, Sequence[tuple[Any, ...]]] | None = None,
    catalog: Catalog = CATALOG,
    workflows: Mapping[str, Activity] = WORKFLOW_FAKES,
    at: int = START,
) -> CaseRun:
    """Open a case with `file`, play the scripted `answers` in order, and report where it ended.
    Each answer is `(step or entry, outcome, who)` or `(step or entry, outcome, who, form)`.
    `people` gives each person their roles, as the Ventoux API states them with every answer
    (brief, D22); someone not listed has none. `opened_by` is the person who opened the case, if
    a person did; otherwise a system did. `activities` replaces fake activities by reference.
    The runs of the steps in `held` keep running until the script says `finish(entry)`.
    `plans` gives the plans plan steps run, as stored data, by reference (`refund-order@1`);
    `plan_answers` answers each plan step's waits, in order, by state: `(state, outcome, who)`.
    `catalog` replaces the development catalog, for a test's own contracts. `workflows` binds each
    workflow contract to a function from its inputs to its output, by reference, replacing the
    fake workflows; a workflow contract with none is not bound, and its step fails. The case opens
    at `at`, seconds since the epoch; `later("3d")` in the script moves time on, and every event
    after it happens then."""
    case = parse_case(definition)  # fail closed: a definition that can't be read runs nothing
    now = at
    events: list[Event | Finish] = [Opened(wrapped(case, as_json(file)), opened_by, at=now)]
    for item in answers:
        if isinstance(item, Later):
            now += item.seconds
            continue
        if isinstance(item, Finishing):
            events.append(Finish(item.entry, at=now))
            continue
        if isinstance(item, Proposal):
            events.append(Proposed(item.step, item.by, frozenset(people.get(item.by, ())), at=now))
            continue
        if isinstance(item, Retry):
            events.append(Retried(item.entry, item.by, frozenset(people.get(item.by, ())), at=now))
            continue
        if isinstance(item, Sending):
            # The test plays the API: it states who sent it, and a person's roles (brief, D19).
            roles = frozenset(people.get(item.by, ()))
            events.append(Sent(item.event, as_json(item.payload), item.by, roles, at=now))
            continue
        if isinstance(item, ShownTo):
            events.append(Shown(item.field, item.by, frozenset(people.get(item.by, ())), at=now))
            continue
        if isinstance(item, Close):
            roles = frozenset(people.get(item.by, ()))
            events.append(CloseAsked(item.reason, item.by, roles, at=now))
            continue
        if isinstance(item, Forget):
            events.append(
                ForgetApproved(
                    item.proposed_by,
                    frozenset(people.get(item.proposed_by, ())),
                    item.approved_by,
                    frozenset(people.get(item.approved_by, ())),
                    at=now,
                )
            )
            continue
        entry, outcome, who, *form = item
        # The test plays the API: it states who answered and their roles.
        roles = frozenset(people.get(who, ()))
        # Every value of a form wrapped, as the client sends it: it can't tell which fields are
        # sensitive (brief, D31).
        given = (
            {name: Sensitive(value) for name, value in as_json(form[0]).items()} if form else None
        )
        events.append(Answered(entry, outcome, who, roles, given, at=now))
    implementations = {**FAKES, **activities}
    runner = plan_runner(plans or {}, plan_answers or {}, implementations, people)
    bound = {**WORKFLOW_FAKES, **workflows}
    return run_case_in_memory(
        case, catalog, implementations, events, held=held, plans=runner, workflows=bound
    )


def plan_runner(
    plans: Mapping[str, Any],
    plan_answers: Mapping[str, Sequence[tuple[Any, ...]]],
    activities: Mapping[str, Activity],
    people: Mapping[str, Iterable[str]],
) -> PlanRunner:
    """Runs a plan step's plan in memory, to its end or its first wait nobody answers, and says
    how it ended as an event (brief, D28)."""
    scripts = {step: list(answers) for step, answers in plan_answers.items()}

    async def call(reference: str, inputs: dict[str, Any]) -> dict[str, Any]:
        return activities[reference](unwrapped(inputs))  # plain values, as on Temporal

    def run(command: StartPlan, at: int) -> Completed | Failed | None:
        try:
            plan = supplied(plans, command.plan)
        except PlanNotSupplied as missing:
            return Failed(command.entry, str(missing), at=at)
        if (wrong := wrong_references(plan, command)) is not None:
            return Failed(command.entry, wrong, at=at)  # fail closed, before the plan starts
        script = scripts.setdefault(command.entry.split("#")[0], [])
        try:
            # asyncio: `interpret` is async, as a Temporal workflow is; `asyncio.run` runs it.
            ran = asyncio.run(
                interpret(
                    plan,
                    command.fields,
                    CATALOG,
                    call,
                    scripted(script, people),
                    run_name=command.run,
                    excluded=command.excluded,
                    steered=command.steered,
                )
            )
        except RunRefused as refused:
            return Failed(command.entry, f"{command.plan} can't start: {refused}", at=at)
        if ran.status == "succeeded":
            return Completed(command.entry, {}, at=at)
        if ran.status == "failed":
            return Completed(command.entry, {}, "failed", at=at)  # a failed final state: an outcome
        if ran.status == "stopped":
            return Failed(command.entry, f"{command.plan} stopped: {ran.reason}", at=at)
        return None  # waiting for an answer the script doesn't give: the step runs on

    return run


def scripted(script: list[tuple[Any, ...]], people: Mapping[str, Iterable[str]]) -> Wait:
    """A plan's waits, answered from `script`: each takes the next answer to its state, or None
    once the script has none left for it. A script answers a state, whatever its entry: it runs
    in order, with no one clicking. `people` gives each person their roles, as the API states
    them with every answer (brief, D22)."""

    async def wait(
        state: str, entry: str, outcomes: tuple[str, ...], timeout: str | None
    ) -> Answer | None:
        for answer in script:
            if answer[0] == state:
                script.remove(answer)
                by = answer[2] if len(answer) > 2 else None
                stated = frozenset(people.get(by, ())) if by else frozenset[str]()
                # Every value of a form wrapped, as the client sends it (brief, D31).
                form = (
                    {name: Sensitive(v) for name, v in answer[3].items()}
                    if len(answer) > 3
                    else None
                )
                return Answer(answer[1], by, stated, form)
        return None

    return wait


class Proposal(NamedTuple):
    """A scripted proposal: `who` proposes starting `step`."""

    step: str
    by: str


class Retry(NamedTuple):
    """A scripted retry: `who` retries the failed step run `entry`."""

    entry: str
    by: str


def retry(entry: str, who: str) -> Retry:
    """A script's retry by an operator: `retry("pay#1", "omar")` (brief, D26)."""
    return Retry(entry, who)


class Close(NamedTuple):
    """A scripted close: `who` closes the case with the declared `reason`."""

    reason: str
    by: str


class Finishing(NamedTuple):
    """A scripted finish: the held run `entry` finishes, at the script's time."""

    entry: str


def finish(entry: str) -> Finishing:
    """A script's step: let the held activity run `entry` finish now: `finish("pay#1")`."""
    return Finishing(entry)


class Later(NamedTuple):
    """A scripted pause: time moves on by `seconds` before the next event."""

    seconds: int


def later(age: str) -> Later:
    """A script's pause: `later("3d")`, so the next event happens three days on (brief, D33)."""
    return Later(seconds_in(age))


def close(reason: str, who: str) -> Close:
    """A script's close: `close("duplicate", "ana")` (brief, D10)."""
    return Close(reason, who)


class Forget(NamedTuple):
    """A scripted request to forget the case, as approved: who proposed it, who approved it."""

    proposed_by: str
    approved_by: str


def forget(proposed_by: str, approved_by: str) -> Forget:
    """A script's approved request to forget the case: `forget("pia", "olu")` (brief, D32). On
    Temporal it is its own workflow, `<case ID>/forget`; here it reaches the case as approved."""
    return Forget(proposed_by, approved_by)


class ShownTo(NamedTuple):
    """A scripted record shown: `who` was shown the record behind the reference `field`."""

    field: str
    by: str


def shown(field: str, who: str) -> ShownTo:
    """A script's record shown: `shown("customer_id", "ana")`, recorded in the case's history,
    as the API records it after asking the system's resolver (brief, D16)."""
    return ShownTo(field, who)


class Sending(NamedTuple):
    """A scripted event from outside: `event`, carrying `payload`, sent by `by`."""

    event: str
    payload: Mapping[str, Any]
    by: str  # `system:portal`, or a person, whose roles come from `people`


def send(event: str, payload: Mapping[str, Any], by: str) -> Sending:
    """A script's event from outside: `send("cancelled", {"note": "…"}, "system:portal")`, or
    sent by a person, `send("customer_called", {}, "ana")` (brief, D41)."""
    return Sending(event, payload, by)


def propose(step: str, who: str) -> Proposal:
    """A script's proposal: `propose("check_order", "ana")`, played in order with the answers."""
    return Proposal(step, who)


def as_json(values: Mapping[str, Any]) -> dict[str, Any]:
    """`values` as the API would pass them on from JSON, whose numbers are exact decimals
    (brief, D20): a whole number in a test is one. A float is passed on as it is, and refused by
    the type check, since it may already have lost its exact value."""
    return {
        name: Decimal(value) if isinstance(value, int) and not isinstance(value, bool) else value
        for name, value in values.items()
    }


def wrapped(case: CaseDefinition, file: Mapping[str, Any]) -> dict[str, Any]:
    """`file` as the client sends it: each sensitive field's value wrapped (brief, D31)."""
    return {
        name: Sensitive(value) if name in case.fields and case.fields[name].sensitive else value
        for name, value in file.items()
    }


def run_plan(
    data: object,
    fields: Mapping[str, Sourced],
    answers: list[tuple[Any, ...]],
    activities: Mapping[str, Activity] = FAKES,
    run: str = "memory",
    people: Mapping[str, Iterable[str]] | None = None,
) -> PlanRun:
    """Run the plan stored as `data` in memory, with `fields`, playing the scripted `answers`,
    calling the fake `activities` by reference. `run` names the run in its idempotency keys
    (`memory/pay#1`). `people` gives each person their roles, as the Ventoux API states them with
    every answer (brief, D22); someone not listed has none.

    The plan's shape is checked (`parse_plan`); `validate` is not called: the runtime checks
    depend on nothing it did (docs/layers/05-interpreter.md).
    """

    # Each answer is (state, outcome, who), (state, outcome, who, form), or (state, "timeout").
    wait = scripted(list(answers), people or {})  # the test plays the API, stating roles

    async def call(reference: str, inputs: dict[str, Any]) -> dict[str, Any]:
        return activities[reference](unwrapped(inputs))  # plain values, as on Temporal

    # asyncio: `interpret` is async, as a Temporal workflow is; `asyncio.run` runs it to the end.
    return asyncio.run(interpret(parse_plan(data), fields, CATALOG, call, wait, run_name=run))
