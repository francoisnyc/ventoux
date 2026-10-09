"""Run cases in memory, in tests: no Temporal server, scripted answers, fake activities."""

import asyncio
import json
from collections.abc import Iterable, Mapping
from decimal import Decimal
from pathlib import Path
from typing import Annotated, Any

from pydantic import BaseModel
from temporalio import workflow

from ventoux.case.definition import parse_case
from ventoux.case.runner import Activity, AnswerRefused, Run, run
from ventoux.core.before_activity import InputRefused
from ventoux.core.catalog import Catalog
from ventoux.core.contract import ActivityContract, Display, RetryPolicy, Timeouts
from ventoux.core.interpreter import Answer, PlanRun, interpret
from ventoux.core.plan import parse_plan
from ventoux.core.policy import trusted_only
from ventoux.core.provenance import Sourced
from ventoux.temporal.workflow import PlanStart, PlanWorkflow, RunReport

__all__ = [
    "Activity",
    "AnswerRefused",
    "DevelopmentPlans",
    "InputRefused",
    "load_definition",
    "run_case",
    "run_plan",
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

# The development catalog: what a case can call in tests and the quickstart.
CATALOG = Catalog()
for contract in (payments_refund, orders_lookup, letters_draft):
    CATALOG.register(contract)
# The labels fields may be declared untrusted with: `untrusted:llm`.
for label in ("customer", "document", "email", "llm", "web"):
    CATALOG.register_label(label)
# The roles waits and approvals may name: support answers tasks, a team lead approves refunds.
CATALOG.register_role("support")
CATALOG.register_role("support-lead", approves="high")


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
}


# Temporal: a workflow class is registered with a worker under its name; this one runs plans
# against the development catalog, in tests and the development worker.
@workflow.defn(name="ventoux.plan")
class DevelopmentPlans(PlanWorkflow):
    catalog = CATALOG

    @workflow.run
    async def run(self, start: PlanStart) -> RunReport:
        return await self.interpret(start)


def load_definition(path: Path) -> dict[str, Any]:
    """Read a case definition from its JSON file (I/O, so here and not in `case`)."""
    # Numbers as exact decimals, never binary floats (brief, D20). Its shape is checked when a
    # case runs (`parse_case`); case validation, provenance and deadlocks, is layer 10's.
    definition: dict[str, Any] = json.loads(path.read_text(), parse_float=Decimal)
    return definition


def run_case(
    definition: dict[str, Any],
    file: dict[str, Any],
    answers: list[tuple[Any, ...]],
    people: Mapping[str, Iterable[str]],
) -> Run:
    """Open a case with `file`, play the scripted `answers`, and report where it ended. `people`
    gives each person their roles, as the Ventoux API states them with every answer (brief, D22);
    someone not listed has none."""
    parse_case(definition)  # fail closed: a definition that can't be read runs nothing
    return run(definition, file, answers, CATALOG, FAKES, people)


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
    script = list(answers)
    roles = people or {}  # the test plays the API: it states each person's roles

    async def call(reference: str, inputs: dict[str, Any]) -> dict[str, Any]:
        return activities[reference](inputs)

    async def wait(
        state: str, entry: str, outcomes: tuple[str, ...], timeout: str | None
    ) -> Answer | None:
        """The next scripted answer to `state`, or None once the script has none left for it.
        A script answers a state, whatever its entry: it runs in order, with no one clicking."""
        for answer in script:
            if answer[0] == state:
                script.remove(answer)
                by = answer[2] if len(answer) > 2 else None
                stated = frozenset(roles.get(by, ())) if by else frozenset[str]()
                return Answer(answer[1], by, stated, answer[3] if len(answer) > 3 else None)
        return None

    # asyncio: `interpret` is async, as a Temporal workflow is; `asyncio.run` runs it to the end.
    return asyncio.run(interpret(parse_plan(data), fields, CATALOG, call, wait, run_name=run))
