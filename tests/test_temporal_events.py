"""Layer 11d: events from outside, sent to cases running as Temporal workflows, against
Temporal's test server.

See docs/layers/11-rules.md (11d) and docs/guides/cases.md, "Events from outside".
"""

import asyncio
import copy
from decimal import Decimal
from typing import Any

import pytest
from temporalio.client import Client

# pytest puts tests/ on the import path (it has no __init__.py), so a test module imports by name.
from test_events import CANCELLED, RECEIPT_SENT, WAIT_FOR_RECEIPT, WITHDRAW
from test_temporal_case import (
    QUEUE,
    REFUND,
    SMALL,
    Case,
    SwitchingCases,
    on_temporal,
    reported,
    runs_of,
)

from ventoux.temporal.cases import answer, case_handle, send_event, start_case, view
from ventoux.testing import DevelopmentCases, EventRefused


def cancellable() -> dict[str, Any]:
    """The quickstart's refund, with the guide's `cancelled` event and its rule."""
    definition = copy.deepcopy(REFUND)
    definition["events"] = {"cancelled": copy.deepcopy(CANCELLED)}
    definition["rules"] = {"withdraw_on_cancel": copy.deepcopy(WITHDRAW)}
    return definition


async def opened(client: Client, definition: dict[str, Any], id: str) -> Case:
    return await start_case(client, DevelopmentCases, definition, SMALL, id=id, task_queue=QUEUE)


def test_a_closed_case_refuses_an_event_at_the_client() -> None:
    async def scenario(client: Client) -> None:
        case = await opened(client, cancellable(), "refund-E-1")
        await answer(case, "review#1", "reject", by="ana", roles=["support"])
        assert (await case.result()).status == "closed"
        # Addressed by its ID alone, as the API does: never a way back in (brief, D41).
        again = case_handle(client, DevelopmentCases, "refund-E-1")
        with pytest.raises(EventRefused, match="^refund-E-1 is closed: it takes no more events$"):
            await send_event(again, "cancelled", {"note": "please cancel"}, by="system:portal")

    on_temporal(scenario)


def test_an_event_on_temporal_is_decided_as_in_memory() -> None:
    async def scenario(client: Client) -> None:
        case = await opened(client, cancellable(), "refund-E-2")
        # Refused, recorded, and the case waits on as if it hadn't come (layer 8b).
        await send_event(case, "cancelled", {"note": "please cancel"}, by="system:crm")
        refused = await reported(case, lambda now: "refused" in now.history[-1])
        assert refused.history[-1] == (
            "refused cancelled from system:crm: cancelled is sent by portal, and this one comes "
            "from system:crm"
        )
        await send_event(case, "cancelled", {"note": "please cancel"}, by="system:portal")
        ended = await case.result()
        assert ended.history[-4:] == [
            "cancelled#1 from portal, giving note from system:portal, untrusted:customer",
            "withdraw_on_cancel#1 on event cancelled: stopping review",
            "cancelled review#1: stopped by withdraw_on_cancel#1",
            "closed: nothing left to do",
        ]

    on_temporal(scenario)


def waiting_for_a_receipt() -> dict[str, Any]:
    """The refund waiting, after its review, for the customer's receipt, before it pays."""
    definition = copy.deepcopy(REFUND)
    definition["events"] = {"receipt_sent": copy.deepcopy(RECEIPT_SENT)}
    definition["steps"]["wait_for_receipt"] = copy.deepcopy(WAIT_FOR_RECEIPT)
    definition["steps"]["pay"]["requires"] = ["wait_for_receipt"]
    return definition


def test_a_wait_on_temporal_holds_the_case_until_its_event_arrives() -> None:
    async def scenario(client: Client) -> None:
        case = await opened(client, waiting_for_a_receipt(), "refund-E-3")
        form = {"approved_amount": Decimal(40)}
        await answer(case, "review#1", "approve", by="ana", roles=["support"], form=form)
        waiting = await reported(case, lambda now: now.waiting_at == ["wait_for_receipt#1"])
        assert waiting.waiting_for == ["receipt_sent from portal"]
        assert waiting.status == "open"
        await send_event(case, "receipt_sent", {"receipt": "doc-7"}, by="system:portal")
        ended = await case.result()
        assert "wait_for_receipt#1 done: receipt_sent#1 arrived" in ended.history
        assert ended.status == "closed"

    on_temporal(scenario)


def test_a_persons_event_crosses_with_exact_values() -> None:
    definition = copy.deepcopy(REFUND)
    definition["events"] = {
        "amount_corrected": {
            "display": {"title": "Support corrects the amount"},
            "sent_by": {"roles": ["support"]},
            "payload": {"amount": {"type": "number", "display": {"title": "Corrected amount"}}},
        }
    }

    async def scenario(client: Client) -> None:
        case = await opened(client, definition, "refund-E-4")
        await send_event(
            case, "amount_corrected", {"amount": Decimal("35.10")}, by="ana", roles=["support"]
        )
        now = await reported(case, lambda now: now.history[-1].startswith("amount_corrected#1"))
        assert now.history[-1] == (
            "amount_corrected#1 by ana, as support, giving amount from person:ana"
        )
        seen = await view(case, ["support"])
        assert seen.values["amount_corrected.amount"] == Decimal("35.10")  # exact, never a float

    on_temporal(scenario)


def test_arrivals_cross_continue_as_new() -> None:
    # The opening and the first arrival make two events, and the case switches: the next arrival
    # is the second, in the new run, as every count carries on (brief, D27) (brief, D41).
    listening = cancellable()
    listening["rules"] = {}

    async def scenario(client: Client) -> tuple[list[str], tuple[str, str]]:
        case = await start_case(client, SwitchingCases, listening, SMALL, "refund-E-5", QUEUE)
        await send_event(case, "cancelled", {"note": "first"}, by="system:portal")
        for _ in range(100):  # until the case has continued as new
            first, last = await runs_of(client, "refund-E-5")
            if last != first:
                break
            await asyncio.sleep(0.05)
        await send_event(case, "cancelled", {"note": "second"}, by="system:portal")
        now = await reported(case, lambda now: now.history[-1].startswith("cancelled#2"))
        return now.history, await runs_of(client, "refund-E-5")

    history, (first, last) = on_temporal(scenario, cases=SwitchingCases)
    assert last != first  # it continued as new between the two
    assert [line.split(", giving")[0] for line in history if line.startswith("cancelled#")] == [
        "cancelled#1 from portal",
        "cancelled#2 from portal",
    ]
