# Shows that the step advisor is sent no case-file value, person or history line, that only a person's proposal reaches the case and its proposer can't approve it, and that the authoring loop takes nothing but the plan a step names (brief, D61, D62, D63). Reaches past the public names: `ventoux.authoring` and `ventoux.case.releases.package`, with recorded providers, no network and no key.
# Run: uv run python reviews/2026-11/probes/p1b_advisor_and_authoring_decide_nothing.py
import copy
import json
from typing import Any

from ventoux.testing import CATALOG, START, run_case

# Fictional people and their roles, as the trusted caller would state them (brief, D22).
PEOPLE = {
    "ana": ["support"],
    "sam": ["support", "support-lead"],
    "lee": ["support-lead"],
    "kim": ["support-lead"],
    "omar": ["operations"],
    "olga": ["operations"],
    "pia": ["platform"],
    "pat": ["platform"],
    "fay": ["fraud", "support-lead"],
}
FILE = {"order_id": "ord-1", "amount": 250}


def T(title: str) -> dict[str, str]:
    return {"title": title}


def refund() -> dict[str, Any]:
    """A small refund: a review that sets the amount, then a high-risk payment a lead approves."""
    return copy.deepcopy(
        {
            "case": "refund",
            "display": T("Refund"),
            "fields": {
                "order_id": {"type": "reference", "system": "orders", "display": T("Order")},
                "amount": {"type": "number", "display": T("Amount")},
                "approved_amount": {"type": "number", "display": T("Approved")},
            },
            "steps": {
                "review": {
                    "kind": "task",
                    "display": T("Review"),
                    "roles": ["support"],
                    "outcomes": {
                        "approve": {"display": T("Approve"), "sets": ["approved_amount"]},
                        "reject": {"display": T("Reject")},
                    },
                },
                "pay": {
                    "kind": "activity",
                    "display": T("Pay"),
                    "activity": "payments.refund@2",
                    "inputs": {
                        "order_id": {"var": "order_id"},
                        "amount": {"var": "approved_amount"},
                    },
                    "requires": ["review"],
                    "when": {"==": [{"var": "review.outcome"}, "approve"]},
                    "approval": {"roles": ["support-lead"], "display": {"reason": "A lead"}},
                },
            },
        }
    )


def attempt(label: str, play: Any) -> Any:
    """Play a script; say whether the engine took it or refused it, and return the run or None."""
    try:
        run = play()
    except Exception as refused:  # noqa: BLE001 (a probe reports every refusal)
        print(f"{label}\n    -> REFUSED ({type(refused).__name__}): {str(refused)[:260]}")
        return None
    print(f"{label}\n    -> ACCEPTED")
    return run


def tail(run: Any, lines: int = 6) -> None:
    for line in run.history[-lines:]:
        print(f"       | {line}")


def down(inputs: dict[str, Any]) -> dict[str, Any]:
    raise ConnectionError("provider unreachable")


_ = (CATALOG, START, json, run_case)  # used by some probes only

import asyncio

from ventoux.authoring.advisor import advise, shown_to_advisor
from ventoux.authoring.loop import author
from ventoux.authoring.provider import Recorded
from ventoux.case.releases import package
from ventoux.case.runtime import proposal_refused
from ventoux.testing import Proposal, propose, send
from ventoux.tooling.schema import plan_schema

wrong = []
CANARIES = ["ord-CANARY", "4242.42", "CANARY-note", "CANARY-national-id", "8181", "CANARY-call", "zed", "sam"]
case = refund()
case["fields"] |= {
    "note": {"type": "string", "display": T("Note"), "source": "untrusted:customer"},
    "national_id": {"type": "string", "display": T("National ID"), "sensitive": True, "visible_to": ["support"]},
    "risk": {"type": "number", "display": T("Risk"), "visible_to": ["support-lead"]},
}
case["events"] = {"called": {"display": T("Called"), "sent_by": {"roles": ["support"]}, "payload": {"said": {"type": "string", "display": T("Said")}}}}
case["steps"]["goodwill"] = {
    "kind": "activity", "display": T("Goodwill"), "activity": "payments.refund@2", "automatic": False, "proposed_by": ["support"],
    "requires": ["review"], "inputs": {"order_id": {"var": "order_id"}, "amount": {"var": "amount"}},
    "approval": {"roles": ["support-lead"], "display": {"reason": "A lead"}},
}
file = {"order_id": "ord-CANARY", "amount": "4242.42", "note": "CANARY-note", "national_id": "CANARY-national-id", "risk": 8181}
from decimal import Decimal  # noqa: E402

file["amount"] = Decimal("4242.42")
people = PEOPLE | {"zed": ["support"]}
run = run_case(case, file, [("review", "approve", "zed", {"approved_amount": Decimal("4242.42")}), send("called", {"said": "CANARY-call"}, "sam")], people, opened_by="sam")
shown = shown_to_advisor(run.definition, CATALOG, run.state, "ana", frozenset(["support"]), START)
sent = shown.request.system + "\n" + "\n".join(message.content for message in shown.request.messages)
found = [canary for canary in CANARIES if canary in sent]
lines = [line for line in run.history if line in sent]
print("1. of 8 canaries (every value, the opener's and the answerer's names) the request holds:", found or "none")
print("   history lines it holds:", lines or "none", "| risk, hidden from support, is said:", [f.state for f in shown.fields if f.name == "risk"])
if found or lines:
    wrong.append("1. the advisor is sent a value, a person or a history line")


async def refused(step: str) -> str | None:
    return proposal_refused(run.definition, CATALOG, run.state, step, "ana", frozenset(["support"]), START)


for label, answer, expect_step in (
    ("2. the model names a step and an amount", '{"step": "goodwill", "amount": 9999}', None),
    ("3. the model names a step admission refuses (pay starts by itself)", '{"step": "pay"}', None),
    ("4. the model answers in prose around the object", 'Sure! {"step": "goodwill"}', None),
    ("5. the model names goodwill", '{"step": "goodwill"}', "goodwill"),
):
    advice = asyncio.run(advise(shown, Recorded.answering(answer), refused))
    print(f"{label}: {advice.said()}")
    if advice.step != expect_step:
        wrong.append(label)
before = len(run.history)
print("   the case's history after five askings is unchanged:", len(run.history) == before and "advisor" not in " ".join(run.history))
script = [("review", "approve", "zed", {"approved_amount": 5})]
taken = attempt("6. ana proposes it as suggested, then approves the run herself (ana holds support-lead here)",
                lambda: run_case(case, file, [*script, propose("goodwill", "ana", "step-advisor"), ("goodwill", "approve", "ana")], people | {"ana": ["support", "support-lead"]}))
if taken is not None:
    wrong.append("6")
taken = attempt("7. a proposal whose suggested_by is a caller's own words",
                lambda: run_case(case, file, [*script, Proposal("goodwill", "ana", "the model said pay 9999")], people))  # type: ignore[arg-type]
if taken is not None:
    wrong.append("7")

# The authoring loop: only the plan the package's step names, checked as a release checks it.
PLAN = {
    "plan": "refund-order", "version": 1, "display": T("Refund an order"),
    "fields": {"order_id": {"type": "reference", "system": "orders"}, "amount": {"type": "number"}},
    "initial": "approve_refund",
    "states": {
        "approve_refund": {"approval": {"of": "pay", "roles": ["support-lead"]}, "on": {"approve": "pay", "reject": "failed"}},
        "pay": {"activity": "payments.refund@2", "inputs": {"order_id": {"var": "order_id"}, "amount": {"var": "amount"}}, "on": {"done": "paid", "declined": "failed"}},
        "paid": {"final": "succeeded"}, "failed": {"final": "failed"},
    },
}
with_plan = refund()
del with_plan["steps"]["pay"]
with_plan["steps"]["settle"] = {"kind": "plan", "display": T("Settle"), "plan": "refund-order@1", "requires": ["review"],
                                "inputs": {"order_id": {"var": "order_id"}, "amount": {"var": "approved_amount"}}}
released = package(json.dumps(with_plan), [json.dumps(PLAN)])
unapproved = json.loads(json.dumps(PLAN))
unapproved["initial"] = "pay"
smuggled = PLAN | {"case": with_plan}
other = PLAN | {"plan": "pay-everyone"}
for label, answer in (
    ("8. the model drafts a case, not a plan", json.dumps(with_plan)),
    ("9. the model drafts another plan than the step names", json.dumps(other)),
    ("10. the model drafts the plan with a case smuggled in a second key", json.dumps(smuggled)),
    ("11. the model drafts the plan paying with no approval", json.dumps(unapproved)),
):
    authored = asyncio.run(author("Pay refunds faster", released, "refund-order@1", CATALOG, plan_schema(), Recorded.answering(answer), rounds=1))
    said = authored.rounds[0].problems[0][:120] if authored.rounds and authored.rounds[0].problems else "no problem"
    print(f"{label}: {authored.verdict}\n       | {said}")
    if authored.verdict == "drafted":
        wrong.append(label)
if wrong:
    print("RESULT: BROKEN - " + "; ".join(wrong))
else:
    print("RESULT: HELD - the advisor read no value and decided nothing, its proposer approved nothing, and the loop drafted nothing but the named plan, checked")
