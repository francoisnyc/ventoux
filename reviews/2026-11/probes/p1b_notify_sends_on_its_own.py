# Shows whether anything in the engine or the validator enforces, or even checks, "anything that talks to people drafts by default; it never sends on its own" (CLAUDE.md non-negotiables; brief, D56).
# Run: uv run python reviews/2026-11/probes/p1b_notify_sends_on_its_own.py
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

from typing import Annotated

from pydantic import BaseModel

from ventoux.case.definition import parse_case
from ventoux.case.validate import validate_case
from ventoux.core.catalog import Catalog
from ventoux.core.contract import ActivityContract, Display, RetryPolicy, Timeouts
from ventoux.core.policy import trusted_only


class MailInput(BaseModel):
    to: Annotated[str, trusted_only()]  # the address
    body: str  # what is sent
    idempotency_key: str


class MailOutput(BaseModel):
    message_id: str


# A contract that sends a message to a person: effect `notify`, low risk, registered as any other.
mail_send = ActivityContract(
    name="mail.send",
    version=1,
    input=MailInput,
    output=MailOutput,
    risk="low",
    effect="notify",
    timeouts=Timeouts(start_to_close=30, schedule_to_start=60),
    retry=RetryPolicy(maximum_attempts=3, initial_interval=1, backoff_coefficient=2),
    idempotency_key="idempotency_key",
    outcomes=[],
    display=Display(title="Send an email", description="Sends an email to a customer, at once."),
)
catalog = Catalog()
catalog.register_system("orders")
catalog.register_role("support")
registered = attempt("the catalog registers mail.send@1: notify, low risk, no draft", lambda: catalog.register(mail_send) or True)
case = {
    "case": "welcome",
    "display": T("Welcome"),
    "fields": {"email": {"type": "string", "display": T("Email")}},
    "steps": {
        "send": {
            "kind": "activity",
            "display": T("Send the welcome email"),
            "activity": "mail.send@1",
            "inputs": {"to": {"var": "email"}, "body": "Welcome!"},
        }
    },
}
issues = validate_case(parse_case(case), catalog)
print("validation of a case whose only step sends, with no task and no approval:", [f"{i.code}: {i.message[:80]}" for i in issues] or "no issue")
sent = []


def send_now(inputs: dict[str, Any]) -> dict[str, Any]:
    sent.append(inputs["to"])
    return {"message_id": "m-1"}


run = run_case(case, {"email": "customer@example.com"}, [], {}, catalog=catalog, activities={"mail.send@1": send_now})
tail(run, 4)
print("  sent, with no person involved:", sent)
if registered and not issues and sent and run.closed:
    print(
        "RESULT: BROKEN - a `notify` contract runs by itself as soon as the case opens: no person "
        "drafted, reviewed, proposed or approved it, and neither the catalog, the validator nor the "
        "runtime says anything (the rule is carried only by what a contract's author writes in its description)"
    )
else:
    print("RESULT: HELD - something stopped a message being sent with no person")
