# Activities: adding a capability to the catalog

> **For the platform team.** This guide describes layers 1, 4, 8d and 9a as if they already worked;
> the code that makes it true is built test-first in those layers. Case developers rarely need it: they meet
> contracts only through the activities they call and the errors `ventoux check` gives them.

**The rule of thumb:** a case definition can only *name* an activity (`payments.refund@2`). What
that name promises is a **contract** you write and register in the **catalog**. Nothing in a
definition, written by a person or drafted by an AI, can add a capability: it can only pick one
from the list.

## Three words

| Word | Question it answers | Example | Changes when… |
|---|---|---|---|
| **Catalog** | What can a definition call? | `payments.refund@1`, `risk.score@1` | a contract is added or retired |
| **Contract** | What does one entry promise? | schemas, input policies, output sources, risk, effect, retries, timeouts, idempotency, outcomes | never: a change is a new `@N` |
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
  the contract's hash covers. An input field may carry an **input policy**: see below. A case
  gives an input exactly what it holds, never converted: so an input is a `Decimal`, a `str`, a
  `bool` or a `Literal` of texts (`Literal["low", "high"]`), each possibly optional, and an output a
  `Decimal`, a `str` or a `bool`. The catalog refuses any other type, such as a `float`.
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

## Output sources: where each value an activity gives comes from

An activity's output lands in the case file, one value per output field: `pay.refund_id`, read like
any other field (see the cases guide). Each value needs a source, as every value in a case does,
and you are the one who knows it: you write it on the output field, as an input policy is written on
an input field (brief, D12).

```python
from ventoux.core.output_sources import source


class KycOutput(BaseModel):
    status: Annotated[str, source("system:kyc")]  # the KYC system decides it
    risk_score: Annotated[Decimal, source("system:kyc")]
    analyst_notes: Annotated[str, source("untrusted:llm")]  # a model writes it from documents
    contact_email: str  # nothing declared: untrusted:undeclared
```

- **`system:<name>`** says a system produced the value, and you vouch for it: it is trusted, and
  `only_from("<name>")` accepts it. Write the system that decides the content, not the one that
  carries it: an amount a customer typed into a portal is `untrusted:customer`, even when the
  portal returns it.
- **`untrusted:<label>`**, with a label you registered, says where untrusted content came from.
- **Nothing declared is untrusted,** read as `untrusted:undeclared` (brief, D6): forgetting a
  source can only make a value less trusted, never more. A step whose `trusted_only` input reads it
  stops before it starts, and the case needs attention.

`person:` is refused (an activity is never a person's answer), and so is `trusted:` (trust is what
a source earns, not a source). `undeclared` is the engine's own label: you can't register it.

The source goes into the output's JSON Schema, which the contract hash covers, so declaring or
changing one is a new version. A field with nothing declared adds nothing to the schema: the
contracts registered before output sources existed hash as they did, and read every output as
untrusted, the strictest reading. To make `payments.refund@2`'s `refund_id` trusted, you would
register `payments.refund@3` declaring it.

An output field can't be named `outcome`: `pay.outcome` is the step's outcome. And it holds a
value the case file holds exactly: a `Decimal`, a `str` (a reference is one) or a `bool`. A
`float` is refused, as everywhere else (brief, D20): `0.1` as a binary float isn't 0.1. So are an
`int` (use `Decimal`) and a nested model, which would put an object in the case file, not data.
The engine checks every value again when it arrives: one it can't hold fails the step, and nothing
the step gave lands.

## Workflow contracts: an existing workflow as one step

A team that already has the logic as Temporal code, in any SDK language, offers it to cases as a
**workflow contract** (brief, D6). It promises what an activity contract promises, except that a
workflow isn't retried as a whole (its own activities retry inside it) and runs for at most one
`timeout`:

```python
from ventoux.core.workflow_contract import WorkflowContract


class KycInput(BaseModel):
    customer_id: Annotated[str, trusted_only()]


kyc_check = WorkflowContract(
    name="kyc.check",
    version=1,
    input=KycInput,
    output=KycOutput,
    risk="low",
    effect="read",
    timeout=600,  # seconds: the longest the workflow may run
    idempotency_key=None,  # a write or notify workflow names its input for the key
    display=Display(title="Check a customer", description="Runs the KYC checks on a customer."),
)
catalog.register(kyc_check)
```

Activity and workflow contracts share one catalog, so a reference names one promise. Each lookup
says which kind it wants: `catalog.workflow("kyc.check@1")` gives the workflow contract, and
`catalog.get(...)`, which plans and activity steps use, gives only activity contracts. The hash,
the lock file and the rules above (idempotency, input policies, output sources) are the same.

What it doesn't have, and why:

- **No retry policy.** Temporal doesn't retry a child workflow; a workflow that fails, or runs past
  its `timeout`, fails its step, and the case needs attention until an operator retries it, with the
  same workflow ID and the same key (brief, D26).
- **No outcomes.** A business result is part of the output, with its source (`status`).
- **No waiting for people.** A workflow step is automated (brief, D6): human work is a task step
  before or after it, where it is routed and audited. Nothing can see inside your code to enforce
  this, so the `timeout` makes a workflow that waits fail loudly, and the contract test below
  catches it first.

**Cancellable, if you promise it.** A running workflow step finishes when its case closes, or
when a rule stops it, as an activity does. If your workflow can stop cleanly, declare
`cancellable=True`: the case then cancels it through Temporal and waits for it to end. It is a
promise in three parts, which your workflow's history must show:

- after the cancellation is requested, it schedules nothing new (no activity, timer or child);
- it ends only once everything it had started has ended;
- it ends cancelled only if nothing it started completed after the request; otherwise it
  completes or fails, and the case treats it so.

Leaving it out, or `cancellable=False`, changes nothing: the contract's hash and its line in
`contracts.lock.json` stay as they are. Declaring it true changes the hash, so it is a new version
(`kyc.check@3`).

Where it runs is a **binding**, given by the deployment, never the contract: its workflow type and
task queue (see "Running a case on Temporal" in the cases guide).

### The contract test

A contract is a promise, not a proof (brief, D6). Run your workflow against its contract on
Temporal's test server, with your own worker:

```python
from ventoux.temporal.bindings import Binding
from ventoux.testing import check_workflow_contract


async def test_kyc_check_keeps_its_contract(env):
    async with Worker(env.client, task_queue="kyc", workflows=[KycCheck]):
        problems = await check_workflow_contract(
            env.client, kyc_check, Binding(workflow="KycCheck", task_queue="kyc"),
            {"customer_id": "c-1"},
        )
    assert problems == []
```

It starts the bound workflow with an input the contract accepts, waits for it (time skips on the
test server, so a `timeout` of 600 costs nothing), and lists every way the result breaks the
promise:

| Your workflow | The contract test says |
|---|---|
| returns no `status` | `kyc.check@1 gave an output its contract doesn't declare: status: Field required` |
| returns a `score` the contract doesn't have | `kyc.check@1 gave score, which its contract doesn't declare` |
| waits for a signal | `kyc.check@1 didn't finish within its timeout of 600s: a workflow step must not wait for people` |
| raises `ApplicationError("documents unreadable")` | `kyc.check@1 failed: documents unreadable` |
| declares `cancellable=True`, and starts a timer after the cancellation is requested | `kyc.check@3 is cancellable, and started a timer after its cancellation was requested` |
| declares `cancellable=True`, and ends while an activity it started still runs | `kyc.check@3 is cancellable, and ended before everything it started had ended` |
| declares `cancellable=True`, and ends cancelled though its activity completed after the request | `kyc.check@3 is cancellable, and ended cancelled though an activity completed after the request` |
| declares `cancellable=True`, and ends before it can be cancelled | `kyc.check@3 is cancellable, and ended before its cancellation was requested, so the promise wasn't checked: give an input that keeps it running` |
| declares `cancellable=True`, and runs a local activity after the cancellation is requested | `kyc.check@3 is cancellable, and ran a local activity after its cancellation was requested` |

For a cancellable contract, the test also starts the workflow a second time, requests its
cancellation once it has started, and reads its history for the three parts of the promise: give
it an input that keeps the workflow running a while, or there is nothing to cancel.

It checks the shape of what the workflow gives, not where each value really comes from: whether
`risk_score` is the scoring system's is for code review. A field the case will never read still
breaks the test: in a case, a field the contract doesn't declare is dropped, but here it means the
contract is out of date.

## Reference inputs: a record from the right system

A case file holds **references** to records your systems own (`customer_id` in `crm`), and an
activity that needs the record takes the reference and fetches it itself (see the case data
guide). Say which system's reference an input takes, next to its type:

```python
from ventoux.core.references import reference


class LetterInput(BaseModel):
    customer: Annotated[str, trusted_only(), reference("crm")]  # the letter's addressee, by ID
    template: str
    idempotency_key: str
```

A step can then give `customer` only a reference field of a `crm` reference, read as it is
(`{"var": "customer_id"}`). A `policies` reference, a text field or a computed value fails the
step before your activity is called: an ID from the wrong system can look exactly like a right
one, and your activity would fetch the wrong record. The check runs in plans too.

`reference()` goes on a `str` field, names one registered system, and is part of the input's JSON
Schema (`x-reference`), so the hash covers it: adding one is a new version. An input without it
takes any text, a reference included, as before.

## Systems and resolvers

The systems references name are registered by you, like source labels, so a typo in a case or a
contract is caught:

```text
catalog.register_system("crm")
```

A person looking at a case sees `cus-7`; to see the customer, the inbox asks a **resolver**, which
you register for each system. A resolver is not an activity: it only reads, runs outside the case
(in the inbox, never in a workflow), and nothing it returns enters the case file or its history
(brief, D16). It calls your system **on behalf of the person looking**, so your system's own
permissions decide what they see:

```python
from ventoux.tooling.resolvers import Resolvers, Viewer


def crm_customer(reference: str, viewer: Viewer) -> dict[str, object]:
    # Your CRM client, asked as the person looking: it shows them what they may see.
    return crm.customer(reference, on_behalf_of=viewer.person)


resolvers = Resolvers(catalog)
resolvers.register("crm", crm_customer)
```

`resolvers.show(view, "customer_id", viewer)` shows the record behind a reference in a person's
case view: it reads the reference from the view, which Ventoux has already filtered for them, so a
field they can't see has no reference to resolve. A system with no resolver shows nothing, and
says so (`crm has no resolver: register one to show its records`).

## What the catalog refuses

Every refusal says what is wrong; the catalog's own refusals then say what to do instead. Pydantic's
messages for a single field (a number out of range, a value not in a list) are kept as Pydantic
writes them.

| You wrote | Ventoux says |
|---|---|
| `effect="write"` with no `idempotency_key` | `payments.refund@2` has effect `'write'`: a side-effecting activity must say which input carries its idempotency key, or a retry could do it twice. |
| `idempotency_key="request_id"`, not an input field | `payments.refund@2`: idempotency key `'request_id'` is not a field of its input (`RefundInput`), so the engine would have nowhere to put the key. Name one of its fields: amount, idempotency_key, order_id. |
| `queue="payments"` in a contract | A contract has no field `'queue'`. A contract says what an activity promises; where it runs (task queue, namespace, worker) belongs in a deployment binding. |
| `name="Payments Refund"`, or `version=0` | `'Payments Refund@2'`: no reference could name it. A name is dotted lowercase (`payments.refund`), and a version a whole number from 1. |
| `outcomes=["declined"]` with no title for it | `payments.refund@2`: outcomes and their display titles must match: outcomes ['declined'], titles for []. Give each outcome exactly one title in `display.outcomes`. |
| `RetryPolicy(maximum_attempts=0, …)` | `maximum_attempts`: Input should be greater than 0. |
| `catalog.register(payments_refund.model_copy(update={"risk": "hihg"}))` | `risk`: Input should be 'low', 'medium' or 'high'. |
| `only_from()`, naming no system | `only_from` names at least one system: with none, no value could ever pass. |
| A policy kind of your own, `class Unless(Policy)` on `amount` | `payments.refund@2`: input `amount` has a policy Ventoux doesn't know (`Unless`). The kinds are `trusted_only` and `only_from`; a new kind is added to the engine, never in a contract. |
| `source("person:ana")` or `source("trusted:kyc")` on an output field | `kyc.check@1`: output `status` has the source `'person:ana'`. An output's source is `system:<name>` or `untrusted:<label>`: an activity is never a person, and trust is earned, not declared. |
| `source("untrusted:fax")`, a label nobody registered | `kyc.check@1`: output `analyst_notes` is `untrusted:fax`, and `fax` is not a registered label. Register it first, or use one of: customer, document, email, llm, web. |
| An output field named `outcome` | `kyc.check@1`: an output can't be named `outcome`: `<step>.outcome` is the step's outcome. Rename the field. |
| An output field `score: float` | `kyc.check@1`: output `score` is `float`, which the case file can't hold exactly. An output is a decimal (Decimal), a text (str) or true or false (bool): numbers are exact decimals, never binary floats (brief, D20). |
| An input field `amount: float` | `payments.refund@2`: input `amount` is `float`, which no value of a case is. An input is a decimal (Decimal), a text (str), true or false (bool) or one of some texts (a Literal of str), each possibly optional: numbers are exact decimals, never binary floats (brief, D20). |
| `reference("sail")`, a system nobody registered | `letters.draft@3`: input `customer` is a reference to `sail`, which is not a registered system. Register it first, or use one of: crm, documents, orders, policies. |
| `reference("crm")` on a field that isn't a `str` | `letters.draft@3`: input `customer` is a reference, so it is a text (str), and this one is `Decimal`. |
| `catalog.register_system("CRM")` | `'CRM'` is not a system name: a system is lowercase, such as `crm` or `claims-archive`. |
| `resolvers.register("sail", …)`, a system nobody registered | `sail` is not a registered system: register it in the catalog first. |
| `catalog.register_label("undeclared")` | `undeclared` is the engine's label for an output nobody declared a source for: register another. |
| `catalog.register_label("LLM")` | `'LLM'` is not a label: a label is lowercase, such as `llm` or `customer-portal`. |
| A second, different `payments.refund@2` | `payments.refund@2` is already registered with different content: register it as `payments.refund@3`. |
| `catalog.get("payments.refund@3")` | `payments.refund@3` is not in the catalog. Registered: `payments.refund@2`. Use a registered version, or register this one first. |
| `retry=RetryPolicy(…)` on a workflow contract | A workflow contract has no retry policy: Temporal doesn't retry a workflow step as a whole (its own activities retry inside it), and an operator retries a failed one. |
| `catalog.get("kyc.check@1")`, a workflow contract | `kyc.check@1` is a workflow contract, not an activity: run it as a workflow step. |
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

`ventoux.testing` ships five activities and one workflow, with fake implementations that touch no
real system (all but `orders.lookup@2`, which each test that runs it gives its own), the source
labels `customer`, `document`, `email`, `llm` and `web`, and the systems `crm`, `documents`,
`orders` and `policies`:

| Activity | Effect | Risk | Input policies | Notes |
|---|---|---|---|---|
| `payments.refund@2` | write | high | `order_id`, `amount`: trusted only | outcome `declined`; nothing is paid |
| `orders.lookup@1` | read | low | none | no idempotency key needed |
| `orders.lookup@2` | read | low | none | as `@1`, and declares `status` from `system:orders` |
| `letters.draft@2` | write | low | `to_customer`: trusted only | only drafts, never sends |
| `letters.draft@3` | write | low | `customer`: trusted only, a `crm` reference | the contract above; fetches the address itself, only drafts |
| `kyc.check@1` (a workflow) | read | low | `customer_id`: trusted only | the contract above; its outputs as declared there |

Of the development activities, only `orders.lookup@2` declares an output source: its `status`
comes from `system:orders` (`kyc.check@1`, a workflow, declares its own, above). Every other output
the development activities give is `untrusted:undeclared`, as their
contracts were written before output sources existed. `orders.lookup@1` stays registered beside
`@2`: declaring a source is a new version (brief, D29), which a case adopts by naming it.

`payments.refund@1` and `letters.draft@1`, without policies, were retired when `@2` added them:
a version without the policy, left in the catalog, would let a definition step around it.
