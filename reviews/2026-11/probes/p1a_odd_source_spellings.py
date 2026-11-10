# Shows whether a source spelt oddly (wrong case, `trusted:`, empty, unknown origin) is ever taken as trusted (D12, fail closed).
"""Four doors a source can come in by, each tried with odd spellings:
1. a case field's declared `source` (a developer declares untrusted, never trusted);
2. a contract output's `source(...)`, when the catalog registers the contract;
3. a value handed to a plan with the public `sourced(...)`, sent to a trusted-only input and
   read by a transition (D49);
4. the policies themselves, asked directly.
Public names, `ventoux.testing`, and `parse_case` / `Catalog` to reach the two readers.
"""

from decimal import Decimal
from typing import Annotated, Any

from pydantic import BaseModel

from ventoux.case.definition import CaseInvalid, parse_case
from ventoux.core.catalog import Catalog
from ventoux.core.contract import ActivityContract, Display, RetryPolicy, Timeouts
from ventoux.core.output_sources import source
from ventoux.core.policy import only_from, trusted_only
from ventoux.core.provenance import sourced
from ventoux.testing import run_case, run_plan

ODD = [
    "trusted:customer",
    "Untrusted:customer",
    "UNTRUSTED:customer",
    " untrusted:customer",
    "untrusted:",
    "untrusted:Customer",
    "untrusted",
    "system:orders",
    "person:ana",
    "case:repair",
    "",
    "System:orders",
    "systemx:orders",
    "case",
]
taken: list[str] = []


def field_case(declared: str) -> dict[str, Any]:
    return {
        "case": "probe",
        "display": {"title": "Probe"},
        "fields": {"note": {"type": "string", "display": {"title": "Note"}, "source": declared}},
        "steps": {
            "letter": {
                "kind": "activity",
                "display": {"title": "Letter"},
                "activity": "letters.draft@2",
                "inputs": {"to_customer": {"var": "note"}, "template": "t"},
            }
        },
    }


print("=== 1. a field declared with an odd source")
for text in ODD:
    try:
        parse_case(field_case(text))
    except CaseInvalid as refused:
        print(f"  {text!r}: refused when read: {str(refused)[:90]}")
        continue
    try:
        run = run_case(field_case(text), file={"note": "x"}, answers=[], people={})
    except Exception as refused:  # noqa: BLE001 (the opening refuses an unregistered label)
        print(f"  {text!r}: refused at the opening: {str(refused)[:90]}")
        continue
    sent = any(line.startswith("scheduled letter#1") for line in run.history)
    print(
        f"  {text!r}: read; note's sources {sorted(run.state.sources['note'])}; letter sent: {sent}"
    )
    if sent:
        taken.append(f"field source {text!r}")
# An unregistered label, well spelt.
try:
    run_case(field_case("untrusted:fax"), file={"note": "x"}, answers=[], people={})
    taken.append("an unregistered label opened a case")
except Exception as refused:  # noqa: BLE001 (any refusal is the point)
    print(f"  'untrusted:fax': refused at the opening: {str(refused)[:90]}")

print("\n=== 2. a contract output declared with an odd source")


class Asked(BaseModel):
    order_id: str


def contract(declared: str) -> ActivityContract:
    class Given(BaseModel):
        status: Annotated[str, source(declared)]

    return ActivityContract(
        name="probe.read",
        version=1,
        input=Asked,
        output=Given,
        risk="low",
        effect="read",
        timeouts=Timeouts(start_to_close=10, schedule_to_start=60),
        retry=RetryPolicy(maximum_attempts=3, initial_interval=1, backoff_coefficient=2),
        idempotency_key=None,
        outcomes=[],
        display=Display(title="Read", description="Reads."),
    )


for text in [*ODD, "system:nowhere", "untrusted:fax"]:
    catalog = Catalog()
    catalog.register_label("customer")
    catalog.register_system("orders")
    try:
        catalog.register(contract(text))
    except Exception as refused:  # noqa: BLE001 (any refusal is the point)
        print(f"  {text!r}: refused: {str(refused)[:90]}")
        continue
    print(f"  {text!r}: registered")
    if text != "system:orders":
        taken.append(f"output source {text!r}")

print("\n=== 3. a value given to a plan with sourced(value, <odd>)")
PLAN = {
    "plan": "write",
    "version": 1,
    "display": {"title": "Write"},
    "fields": {"email": {"type": "string"}, "flag": {"type": "boolean"}},
    "initial": "letter",
    "states": {
        "letter": {
            "activity": "letters.draft@2",
            "inputs": {"to_customer": {"var": "email"}, "template": "t"},
            "on": {"done": "sent"},
        },
        "sent": {"final": "succeeded"},
    },
}
BRANCH = {
    "plan": "branch",
    "version": 1,
    "display": {"title": "Branch"},
    "fields": {"email": {"type": "string"}, "flag": {"type": "boolean"}},
    "initial": "look",
    "states": {
        "look": {
            "activity": "orders.lookup@1",
            "inputs": {"order_id": "ord-1"},
            "on": {"done": [{"when": {"var": "flag"}, "target": "yes"}, {"target": "no"}]},
        },
        "yes": {"final": "succeeded"},
        "no": {"final": "failed"},
    },
}
for text in ODD:
    if text.startswith(("system:", "person:", "case:")) or text == "case":
        continue  # the trusted origins, by D12 and D74 (`case` is the static check's stand-in)
    fields = {"email": sourced("a@example.com", text), "flag": sourced(True, text)}
    sent = run_plan(PLAN, fields, [])
    chose = run_plan(BRANCH, fields, [])
    print(f"  {text!r}: letter plan {sent.status}; branching plan {chose.status}")
    if sent.status != "stopped":
        taken.append(f"plan input from {text!r}")
    if chose.status != "stopped":
        taken.append(f"plan path chosen from {text!r}")

print("\n=== 4. the policies, asked directly")
for text in ODD:
    trusted = trusted_only().refuses(frozenset({text}))
    orders = only_from("orders").refuses(frozenset({text}))
    print(
        f"  {text!r}: trusted_only {'refuses' if trusted else 'TAKES'}; only_from(orders) {'refuses' if orders else 'TAKES'}"
    )
    if trusted is None and not text.startswith(("system:", "person:", "case:")) and text != "case":
        taken.append(f"trusted_only takes {text!r}")
    if orders is None and text != "system:orders":
        taken.append(f"only_from takes {text!r}")
print(
    "  no source at all: trusted_only",
    trusted_only().refuses(frozenset()),
    "| only_from:",
    only_from("orders").refuses(frozenset()),
)
print("  Decimal kept exact:", sourced(Decimal("0.1"), "system:orders").value)

print()
if taken:
    print("RESULT: BROKEN - taken as trusted or accepted: " + "; ".join(taken))
else:
    print("RESULT: HELD - every odd spelling is refused when read, or refused as unrecognised")
