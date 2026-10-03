# Activities: adding a capability to the catalog

> **For the platform team.** This guide describes layer 1 as if it already worked; the code that
> makes it true is built test-first in that layer. Case developers rarely need it: they meet
> contracts only through the activities they call and the errors `ventoux check` gives them.

**The rule of thumb:** a case definition can only *name* an activity (`payments.refund@1`). What
that name promises is a **contract** you write and register in the **catalog**. Nothing in a
definition, written by a person or drafted by an AI, can add a capability: it can only pick one
from the list.

## Three words

| Word | Question it answers | Example | Changes when… |
|---|---|---|---|
| **Catalog** | What can a definition call? | `payments.refund@1`, `risk.score@1` | a contract is added or retired |
| **Contract** | What does one entry promise? | schemas, risk, effect, retries, timeouts, idempotency, outcomes | never: a change is a new `@N` |
| **Binding** | Where does it run, here? | production: queue `payments` | operations move it; no version, no release |

The catalog lists contracts; each environment binds them. A contract has no field for a task
queue, a namespace or a worker: where an activity runs is a deployment binding, and moving it
changes no contract.

## Writing a contract

```python
from decimal import Decimal

from pydantic import BaseModel

from ventoux.core.catalog import ActivityContract, Display, RetryPolicy, Timeouts


class RefundInput(BaseModel):
    order_id: str
    amount: Decimal
    idempotency_key: str  # filled by the engine, never by a definition


class RefundOutput(BaseModel):
    refund_id: str


payments_refund = ActivityContract(
    name="payments.refund",
    version=1,
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
```

Then register it: `catalog.register(payments_refund)`, and look it up by reference:
`catalog.get("payments.refund@1")`.

What each part is for:

- **`name` and `version`.** Together they are the reference definitions use, `name@version`. The
  version is a whole number: there are no minor versions, because every change is a new contract.
- **`input` and `output`.** Pydantic models. Their JSON Schema is what the catalog publishes and what
  the contract's hash covers.
- **`risk`** (`low`, `medium`, `high`): how bad a mistake would be. High-risk steps need an approval
  on every path.
- **`effect`** (`read`, `compute`, `write`, `notify`): what the activity does to the world. `read`
  and `compute` change nothing, so retrying them is harmless.
- **`timeouts` and `retry`**, in seconds. You set them because you know the system's limits; a case
  may make them stricter, never looser. `schedule_to_start` makes an activity no worker picks up
  fail loudly instead of waiting forever.
- **`idempotency_key`**: the input field that carries the key the engine builds from the case, the
  step and the step's run (never Temporal's attempt number). Your adapter sends it to the system,
  and returns the original result when the system answers "duplicate request".
- **`outcomes`**: business failures (declined, account closed), which cases read like task
  outcomes: `pay.outcome == "declined"`. Anything else that goes wrong is a failure that needs
  attention.
- **`display`**: titles and descriptions for people. They are presentation: fixing a typo in them
  is not a new contract.

## What the catalog refuses

Every refusal says what was wrong and what to do instead.

| You wrote | Ventoux says |
|---|---|
| `effect="write"` with no `idempotency_key` | A side-effecting activity must say which input carries its idempotency key, or a retry could do it twice. |
| `idempotency_key="request_id"`, not an input field | The idempotency key must be a field of the input schema. |
| `queue="payments"` in a contract | Where an activity runs belongs in a deployment binding, not the contract. |
| A second, different `payments.refund@1` | `payments.refund@1` is already registered with different content: register it as `payments.refund@2`. |
| `catalog.get("payments.refund@3")` | `payments.refund@3` is not in the catalog. Registered: `payments.refund@1`. |
| `catalog.get("payments.refund@1.0")` | A reference is `name@N`, with a whole-number version. |

## Changing a contract

A contract never changes. To change one, register a new version next to the old one (`@2`). Cases
and packages that reference `@1` keep it until they adopt `@2`, which creates a release.

To catch an edit made in place, the catalog hashes each contract (everything except `display`) and
`contracts.lock.json` records each hash. A test in CI compares them:

- a recorded contract whose hash changed fails: "`payments.refund@1` changed without a new
  version: register it as `@2`";
- a contract that isn't recorded yet fails with the line to add.

## Development activities

`ventoux.testing` ships three activities, with fake implementations that touch no real system:

| Activity | Effect | Risk | Notes |
|---|---|---|---|
| `payments.refund@1` | write | high | outcome `declined`; nothing is paid |
| `orders.lookup@1` | read | low | no idempotency key needed |
| `letters.draft@1` | write | low | only drafts, never sends |
