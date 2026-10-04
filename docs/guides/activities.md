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

> **Coming from Temporal?** Three things work differently:
>
> - **Timeouts and retries live on the contract,** not where an activity is called. You set them
>   once, for every case; a case may make them stricter, never looser.
> - **Business failures are declared outcomes** (`declined`), not non-retryable errors. Cases read
>   them like task answers; anything undeclared that fails after its retries needs attention.
> - **Registering an activity on a worker is still how you deploy it.** That's *where* it runs (a
>   deployment binding). The catalog is *what* it promises, and the two never mix.
>
> And one surprise: the contract's hash covers the JSON Schema of its input and output, which
> includes each model's class name and docstring. Renaming `RefundInput` is a new version.

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
  fail loudly instead of waiting forever. Every timeout, interval and attempt count must be greater
  than 0 (to Temporal, `maximum_attempts=0` means "retry forever"), and the backoff at least 1.
- **`idempotency_key`**: the input field that carries the key the engine builds from the case, the
  step and the step's run (never Temporal's attempt number). Your adapter sends it to the system,
  and returns the original result when the system answers "duplicate request".
- **`outcomes`**: business failures (declined, account closed), which cases read like task
  outcomes: `pay.outcome == "declined"`. Their order doesn't matter. Anything else that goes wrong
  is a failure that needs attention.
- **`display`**: titles and descriptions for people. They are presentation: fixing a typo in them
  is not a new contract.

## What the catalog refuses

Every refusal says what was wrong; the catalog's own refusals also say what to do instead.

| You wrote | Ventoux says |
|---|---|
| `effect="write"` with no `idempotency_key` | `payments.refund@1` has effect `'write'`: a side-effecting activity must say which input carries its idempotency key, or a retry could do it twice. |
| `idempotency_key="request_id"`, not an input field | `payments.refund@1`: idempotency key `'request_id'` is not a field of its input (`RefundInput`), so the engine would have nowhere to put the key. |
| `queue="payments"` in a contract | A contract has no field `'queue'`. A contract says what an activity promises; where it runs (task queue, namespace, worker) belongs in a deployment binding. |
| `name="Payments Refund"`, or `version=0` | `'Payments Refund@1'`: no reference could name it. A name is dotted lowercase (`payments.refund`), and a version a whole number from 1. |
| `outcomes=["declined"]` with no title for it | `payments.refund@1`: outcomes and their display titles must match. |
| `RetryPolicy(maximum_attempts=0, …)` | `maximum_attempts`: Input should be greater than 0. |
| A second, different `payments.refund@1` | `payments.refund@1` is already registered with different content: register it as `payments.refund@2`. |
| `catalog.get("payments.refund@3")` | `payments.refund@3` is not in the catalog. Registered: `payments.refund@1`. |
| `catalog.get("payments.refund@1.0")` | `'payments.refund@1.0'` is not a reference: a reference is name@N, such as `payments.refund@1`, with a whole-number version. |

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
