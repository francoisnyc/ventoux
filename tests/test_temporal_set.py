"""Layer 11e: rules that update the case file, in cases running as Temporal workflows, against
Temporal's test server.
See docs/layers/11-rules.md (11e) and docs/guides/cases.md, "Rules that update the case file".
"""

import asyncio
from decimal import Decimal
from typing import Any

from temporalio.client import Client, WorkflowHistory

# pytest puts tests/ on the import path (it has no __init__.py), so a test module imports by name.
from test_set import with_national_id
from test_temporal_case import QUEUE, SwitchingCases, on_temporal, replay, reported, runs_of

from ventoux.core.sensitive import Sensitive
from ventoux.temporal.cases import answer, send_event, start_case, view
from ventoux.testing import development_converter

FILE = {"order_id": "ord-1", "amount": Decimal(40), "fee": Decimal(5), "national_id": "190101-1"}


def refigured() -> dict[str, Any]:
    """The refund with what is owed and a risk band set from the national ID, and a rule that
    works out what is owed again when the portal sends a new fee."""
    definition = with_national_id()
    definition["steps"]["pay"]["inputs"]["amount"] = {"var": "owed"}
    definition["events"] = {
        "fee_changed": {
            "display": {"title": "The fee changes"},
            "sent_by": {"system": "portal"},
            "payload": {"fee": {"type": "number", "display": {"title": "The new fee"}}},
        }
    }
    definition["rules"]["refigure"] = {
        "display": {"title": "Work out what is owed again"},
        "on": {"event": "fee_changed"},
        "then": {"set": {"owed": {"-": [{"var": "approved_amount"}, {"var": "fee_changed.fee"}]}}},
    }
    return definition


def test_a_set_value_crosses_continue_as_new() -> None:
    # What a rule set, its sources and when it was obtained, are part of the case's state, so they
    # cross continue-as-new; a sensitive one crosses encrypted, and a rule sets again in the new
    # run as it would have in the old (brief, D27, D31, D42).
    async def scenario(
        client: Client,
    ) -> tuple[list[str], dict[str, Any], dict[str, Any], WorkflowHistory]:
        case = await start_case(client, SwitchingCases, refigured(), FILE, "refund-S-1", QUEUE)
        form = {"approved_amount": Decimal(500)}
        await answer(case, "review#1", "approve", by="ana", roles=["support"], form=form)
        for _ in range(100):  # until the case has continued as new
            first, last = await runs_of(client, "refund-S-1")
            if last != first:
                break
            await asyncio.sleep(0.05)
        assert last != first
        await send_event(case, "fee_changed", {"fee": Decimal(50)}, by="system:portal")
        now = await reported(case, lambda now: now.history[-1].startswith("asked pay.approval"))
        lead = await view(case, ["support-lead"])
        fraud = await view(case, ["fraud"])
        return now.history, dict(lead.values), dict(fraud.values), await case.fetch_history()

    converter = development_converter()
    history, lead, fraud, recorded = on_temporal(
        scenario, cases=SwitchingCases, converter=converter
    )
    assert [line for line in history if ": setting " in line] == [
        "band#1 on opened: setting risk_band, from system:opener",
        "work_out_owed#1 on answered review: setting owed, from person:ana, system:opener",
        "refigure#1 on event fee_changed: setting owed, from person:ana, system:portal",
    ]
    assert lead["owed"] == Decimal(450)  # exact, never a float
    # Shown wrapped to who may see it, opened with the case's key (brief, D31).
    assert fraud["risk_band"] == Sensitive("band-190101-1")
    assert "risk_band" not in lead
    # The new run, started from the carried state, replays the same: a set reads no clock,
    # randomness or I/O, and its sealed parts open with the case's key.
    replay(recorded, SwitchingCases, converter)
