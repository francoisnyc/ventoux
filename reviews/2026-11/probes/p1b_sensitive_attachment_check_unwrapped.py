# Shows whether a sensitive attachment's ID (and a sensitive option) stays wrapped in the command that asks its system's check, as every other sensitive input does (brief, D31, D67, D68). Reaches past the public names: it calls `ventoux.case.runtime.decide` to read the commands the engine asks for.
# Run: uv run python reviews/2026-11/probes/p1b_sensitive_attachment_check_unwrapped.py
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

from decimal import Decimal

from ventoux.case.runtime import decide
from ventoux.case.state import Answered
from ventoux.core.sensitive import Sensitive

case = refund()
hidden = {"sensitive": True, "visible_to": ["claims-sensitive", "support"]}
case["fields"]["receipt"] = {"type": "attachment", "store": "documents", "display": T("Receipt")} | hidden
case["fields"]["branch"] = {"type": "option", "system": "branches", "display": T("Branch")} | hidden
case["fields"]["national_id"] = {"type": "string", "display": T("National ID")} | hidden
case["steps"]["review"]["outcomes"]["approve"]["sets"] = ["approved_amount", "receipt", "branch"]
# Control: an ordinary activity given a sensitive field.
case["steps"]["tell"] = {
    "kind": "activity",
    "display": T("Draft a letter"),
    "activity": "letters.draft@2",
    "inputs": {"to_customer": {"var": "national_id"}, "template": "t"},
    "requires": ["review"],
}
opened = run_case(case, FILE | {"national_id": "AB123456C"}, [], PEOPLE)
# The answer as the client sends it: every form value wrapped (brief, D31).
form = {
    "approved_amount": Sensitive(Decimal(5)),
    "receipt": Sensitive("doc-7f3a"),
    "branch": Sensitive("BR-0142"),
}
answered = Answered("review", "approve", "ana", frozenset(["support"]), form, at=START)
state, commands = decide(opened.definition, CATALOG, opened.state, answered)
plain = []
for command in commands:
    for name, value in command.inputs.items():
        print(f"  {command.entry} asks {command.activity} with {name} = {type(value).__name__}({value})")
        if name in ("attachment", "option") and not isinstance(value, Sensitive):
            plain.append(f"{command.entry}.{name}")
# The checks answer; then the control step starts.
done = run_case(
    case,
    FILE | {"national_id": "AB123456C"},
    [("review", "approve", "ana", {"approved_amount": 5, "receipt": "doc-7f3a", "branch": "BR-0142"})],
    PEOPLE,
    held=["tell"],
)
print("  in the case file the two are kept as:", type(done.state.values["receipt"]).__name__, type(done.state.values["branch"]).__name__)
control = [
    line for line in done.history if line.startswith("scheduled tell#1")
]
print("  control:", control)
from ventoux.case.state import Completed  # noqa: E402

# The control's command, read the same way: the decision that takes the last check's answer.
replay = opened.state
replay, first = decide(opened.definition, CATALOG, replay, answered)
for check in first[:-1]:
    replay, _ = decide(opened.definition, CATALOG, replay, Completed(check.entry, {"issued": True} if "receipt" in check.entry else {"held": True}, at=START))
last = first[-1]
replay, after = decide(opened.definition, CATALOG, replay, Completed(last.entry, {"issued": True} if "receipt" in last.entry else {"held": True}, at=START))
for command in after:
    if command.entry == "tell#1":
        kind = type(command.inputs["to_customer"]).__name__
        print(f"  control: tell#1 asks letters.draft@2 with to_customer = {kind}({command.inputs['to_customer']})")
if plain:
    print(
        "RESULT: BROKEN - a sensitive attachment's ID and a sensitive option leave the engine in "
        f"plain text in their check's command ({', '.join(plain)}), where an ordinary sensitive "
        "input stays wrapped; on Temporal the worker passes a command's inputs to the activity as they are"
    )
else:
    print("RESULT: HELD - a sensitive option or attachment stays wrapped in its check's command")
