# Activities: adding a capability to the catalog

> **For the platform team.** This guide describes layers 1 and 4 as if they already worked; the
> code that makes it true is built test-first in those layers. Case developers rarely need it: they meet
> contracts only through the activities they call and the errors `ventoux check` gives them.

**The rule of thumb:** a case definition can only *name* an activity (`payments.refund@2`). What
that name promises is a **contract** you write and register in the **catalog**. Nothing in a
definition, written by a person or drafted by an AI, can add a capability: it can only pick one
from the list.

## Three words

| Word | Question it answers | Example | Changes when… |
|---|---|---|---|
| **Catalog** | What can a definition call? | `payments.refund@1`, `risk.score@1` | a contract is added or retired |
| **Contract** | What does one entry promise? | schemas, input policies, risk, effect, retries, timeouts, idempotency, outcomes | never: a change is a new `@N` |
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
from typing import Annotated

from pydantic import BaseModel

from ventoux.core.contract import ActivityContract, Display, RetryPolicy, Timeouts
from ventoux.core.policy import trusted_only


class RefundInput(BaseModel):
    order_id: Annotated[str, trusted_only()]  # never an order chosen by an AI or a customer
    amount: Annotated[Decimal, trusted_only()]  # never an amount typed by a customer
    idempotency_key: str  # filled by the engine, never by a definition


class RefundOutput(BaseModel):
    refund_id: str


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
```

Then register it: `catalog.register(payments_refund)`, and look it up by reference:
`catalog.get("payments.refund@2")`. The catalog checks every contract again when it is registered,
so a contract made some other way, such as a copy with `model_copy(update=...)`, can't skip a rule.

What each part is for:

- **`name` and `version`.** Together they are the reference definitions use, `name@version`. The
  version is a whole number: there are no minor versions, because every change is a new contract.
- **`input` and `output`.** Pydantic models. Their JSON Schema is what the catalog publishes and what
  the contract's hash covers. An input field may carry an **input policy**: see below.
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

## Input policies: where a value may come from

Every value in a case carries the sources it came from (brief, D12): a **system** (the system that
opened the case, or an activity whose contract says so), a **person** (who answered a task), or
something **untrusted** (`untrusted:llm`, `untrusted:customer`, …). A value computed by an
expression carries the sources of every field it reads, so wrapping an untrusted value in an
expression doesn't clean it.

An **input policy** says which sources one input accepts. (In the security literature, this is a
*sink policy*: the input is where data "sinks" into an action.) You write it on the input's field,
next to its type:

```text
to_customer: Annotated[str, trusted_only()]
account: Annotated[str, only_from("payments")]
```

(`Annotated[str, …]` is plain Python typing: the type `str`, plus something attached to it for
whoever reads the field. Here, Ventoux reads the policy.)

| Kind | What people read | Use it for |
|---|---|---|
| `trusted_only()` | only from a system or a person, never from untrusted data | most inputs that decide something: a recipient, an amount, an order |
| `only_from("payments", …)` | only from payments | the advanced form: the value must come from one of the systems named |

`ventoux check` refuses a definition whose value for the input could come from a source the policy
doesn't accept, with the policy's sentence in the message, and the engine checks again with the
real values before the activity is scheduled. A content filter judges what a value says; a policy
only asks where it came from, so no wording, however clever, gets an untrusted value past it.

The kinds are a closed list fixed by the engine: adding one is a design decision recorded in the
brief, like an expression operator (brief, D21). Every policy on an input applies. A policy is part
of the contract's promise (the hash covers it, through the input's JSON Schema), so adding one is a
new version.

### Source labels

The labels after `untrusted:` are registered by you, like roles, so a developer's typo is caught by
`ventoux check`:

```text
catalog.register_label("llm")
```

A developer may declare a field untrusted with a registered label; nobody can declare a field
trusted. Trust comes only from a contract you own, or a person's answer.

## What the catalog refuses

Every refusal says what is wrong; the catalog's own refusals then say what to do instead. Pydantic's
messages for a single field (a number out of range, a value not in a list) are kept as Pydantic
writes them.

| You wrote | Ventoux says |
|---|---|
| `effect="write"` with no `idempotency_key` | `payments.refund@2` has effect `'write'`: a side-effecting activity must say which input carries its idempotency key, or a retry could do it twice. |
| `idempotency_key="request_id"`, not an input field | `payments.refund@2`: idempotency key `'request_id'` is not a field of its input (`RefundInput`), so the engine would have nowhere to put the key. Name one of its fields: amount, idempotency_key, order_id. |
| `queue="payments"` in a contract | A contract has no field `'queue'`. A contract says what an activity promises; where it runs (task queue, namespace, worker) belongs in a deployment binding. |
| `name="Payments Refund"`, or `version=0` | `'Payments Refund@1'`: no reference could name it. A name is dotted lowercase (`payments.refund`), and a version a whole number from 1. |
| `outcomes=["declined"]` with no title for it | `payments.refund@2`: outcomes and their display titles must match: outcomes ['declined'], titles for []. Give each outcome exactly one title in `display.outcomes`. |
| `RetryPolicy(maximum_attempts=0, …)` | `maximum_attempts`: Input should be greater than 0. |
| `catalog.register(payments_refund.model_copy(update={"risk": "hihg"}))` | `risk`: Input should be 'low', 'medium' or 'high'. |
| `only_from()`, naming no system | `only_from` names at least one system: with none, no value could ever pass. |
| A policy kind of your own, `class Unless(Policy)` on `amount` | `payments.refund@2`: input `amount` has a policy Ventoux doesn't know (`Unless`). The kinds are `trusted_only` and `only_from`; a new kind is added to the engine, never in a contract. |
| `catalog.register_label("LLM")` | `'LLM'` is not a label: a label is lowercase, such as `llm` or `customer-portal`. |
| A second, different `payments.refund@2` | `payments.refund@2` is already registered with different content: register it as `payments.refund@3`. |
| `catalog.get("payments.refund@3")` | `payments.refund@3` is not in the catalog. Registered: `payments.refund@2`. Use a registered version, or register this one first. |
| `catalog.get("payments.refund@1.0")` | `'payments.refund@1.0'` is not a reference: a reference is name@N, such as `payments.refund@1`, with a whole-number version. |

## Changing a contract

A contract never changes. To change one, register a new version next to the old one (`@2`). Cases
and packages that reference `@1` keep it until they adopt `@2`, which creates a release.

To catch an edit made in place, the catalog hashes each contract (everything except `display`) and
`contracts.lock.json` records each hash. A test in CI compares them:

- a recorded contract whose hash changed fails: "`payments.refund@2` changed without a new
  version: register it as `@3`";
- a contract that isn't recorded yet fails with the line to add.

## Development activities

`ventoux.testing` ships three activities, with fake implementations that touch no real system, and
the source labels `customer`, `document`, `email`, `llm` and `web`:

| Activity | Effect | Risk | Input policies | Notes |
|---|---|---|---|---|
| `payments.refund@2` | write | high | `order_id`, `amount`: trusted only | outcome `declined`; nothing is paid |
| `orders.lookup@1` | read | low | none | no idempotency key needed |
| `letters.draft@2` | write | low | `to_customer`: trusted only | only drafts, never sends |

`payments.refund@1` and `letters.draft@1`, without policies, were retired when `@2` added them:
a version without the policy, left in the catalog, would let a definition step around it.
