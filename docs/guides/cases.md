# Cases: steps, a case file, and no position

> **For workflow developers.** A case is how Ventoux runs long work with people in it: one
> customer's refund, one claim. This guide shows a case as stored (the JSON `ventoux check`
> writes from your Python file), how it runs in memory, in tests, and how it runs on Temporal.
> Existing workflows as steps come next.

## A case, read aloud

The quickstart's refund, as `ventoux check` writes it to `build/refund.json`:

```json
{
  "case": "refund",
  "display": {"title": "Customer refund"},
  "fields": {
    "order_id": {"type": "reference", "system": "orders", "display": {"title": "Order"}},
    "amount": {"type": "number", "display": {"title": "Amount requested"}},
    "approved_amount": {"type": "number", "display": {"title": "Amount approved"}}
  },
  "steps": {
    "review": {
      "kind": "task",
      "display": {"title": "Review the refund request"},
      "roles": ["support"],
      "outcomes": {
        "approve": {"display": {"title": "Approve the refund"}, "sets": ["approved_amount"]},
        "reject": {"display": {"title": "Reject the refund"}}
      }
    },
    "pay": {
      "kind": "activity",
      "display": {"title": "Refund the customer"},
      "activity": "payments.refund@2",
      "inputs": {"order_id": {"var": "order_id"}, "amount": {"var": "approved_amount"}},
      "when": {"==": [{"var": "review.outcome"}, "approve"]},
      "approval": {
        "when": {">": [{"var": "approved_amount"}, 100]},
        "roles": ["support-lead"],
        "display": {"reason": "Refunds over 100 need a team lead"}
      }
    }
  },
  "sequence": ["review", "pay"]
}
```

Read aloud: a refund's case file holds the order, the amount asked for, and the amount approved.
Someone in support reviews the request and approves it, saying how much, or rejects it. Then, if
the review approved it, the customer is refunded the approved amount; above 100, a team lead
approves the payment first. Review first, then pay.

Every step, field and outcome has a business title, in its `display` block: what people read,
apart from what the engine does (brief, D5). A step without a title is refused when the
definition is read.

## No position: what may start now

A plan knows where it is ("in `approve_refund`"). A case doesn't: it holds its **case file**, the
**milestones** it has reached, and its **step runs** (`review#1`, open or done). After every event
(the case opening, an answer, a step completing), the engine asks again, for each step: may it
start now? That is **admission**:

- its `requires` are met: each names a milestone the case has reached, or a step whose latest run
  is done;
- its `when` holds, read from the case file;
- it isn't running, and it hasn't run yet (or it is `repeatable`, and a person proposes it).

`sequence` is a shorthand: `["review", "pay"]` means `pay` requires `review`. The expansion is
visible in `ventoux check`.

`when` is read only once `requires` are met. Before the review is done, `review.outcome` has no
value, and reading a field with no value is an error, never "false". So a step whose condition
reads an answer requires the step that gives it.

Here is the refund running, with nobody saying where the case is:

```
opened by system:opener, with amount and order_id
started review#1: waiting for approve or reject by support
ana answered review#1 approve as support, setting approved_amount
review#1 done
asked pay.approval#1: approval of pay by support-lead
sam answered pay.approval#1 approve as support-lead
scheduled pay#1: payments.refund@2 (order_id from system:opener; amount from person:ana), key memory/pay#1
pay#1 done, giving refund_id
closed: nothing left to do
```

Steps admitted at the same time start at the same time: two tasks with nothing required open
together, and the case waits for both.

## Steps that start by themselves, and steps a person proposes

A step **starts by itself** once it is admitted, once. A step with `"automatic": false` starts
only when a person **proposes** it; `proposed_by` names who may. The engine checks the proposal
against admission, so a person can't start a step whose requirements aren't met:

```json
"check_order": {
  "kind": "activity",
  "display": {"title": "Look the order up again"},
  "activity": "orders.lookup@1",
  "inputs": {"order_id": {"var": "order_id"}},
  "automatic": false,
  "proposed_by": ["support"],
  "requires": ["review"]
}
```

A **repeatable** step may run again, and only when proposed: it never starts itself a second time,
or it would never stop. A task's `outcome` is then its latest answer, and a field its form sets
holds the latest value (brief, D9). This is how a review is sent back for rework, with two keys
added to `review`:

```json
{"repeatable": true, "proposed_by": ["support"]}
```

A step may **reach milestones**: `"reaches": ["reviewed"]` on a step is reached when it completes,
and on a task's outcome when it is answered with that outcome. A milestone is a fact, never undone.

## The case file

A case opens with the fields a system (or a person) gives it. Each value is checked against its
field's type, and tagged with where it came from: `system:opener`, or the person who opened it.
A field declared `"source": "untrusted:customer"` keeps that mark too (brief, D12).

A field a task's outcome sets is **never given at the opening**: a person sets it, and the case
file says who (`person:ana`). The form has exactly the fields the outcome sets, each of its
declared type. Numbers are exact decimals: `250` is read as exactly 250, and a binary float such
as `0.1` is refused rather than guessed (brief, D20).

## Approvals in a case

An approval guards a step, and is asked when the step is about to start: its requirements are
met, its `when` holds, and the approval's own `when` holds now (`approved_amount > 100`).

**Someone else, computed** (brief, D11). Nobody lists who may not approve. Excluded are:
whoever's answer flows into the step's inputs or its `when`, the person who opened the case, and
the person who proposed this run of the step: asking for a payment and approving it are two
people's acts.

**An open approval follows the case file** (brief, D25). While it waits, if the step stops being
admitted, or a value it reads changes, the approval is withdrawn, and asked again with a new
entry when the step is admitted again. Suppose the review is sent back while Sam is reading the
approval sheet for 250, and Ana reworks it to 900:

```
asked pay.approval#1: approval of pay by support-lead
ana proposed review as support
started review#2: waiting for approve or reject by support
withdrew pay.approval#1: review started again
ana answered review#2 approve as support, setting approved_amount
review#2 done
asked pay.approval#2: approval of pay by support-lead
```

Sam's *approve* for `pay.approval#1` is now refused: it was withdrawn. Approving 900 takes an
answer to `pay.approval#2`, from someone who sees 900.

**A high-risk step has an approval.** A step calling a high-risk activity with no `approval`
stops before it is scheduled, even in a definition nobody checked.

**One approval, one run.** The approval is spent in the same step as the activity is scheduled:
`pay#1`, with its own idempotency key. A *reject* is an outcome: the step doesn't run, and the case
closes if nothing else is left.

## What a waiting case reports

A case closes when nothing is left to do (brief, D10). While a task or an approval is open, it
stays open, and `waiting_for` says what it waits for, in the order they opened (brief, D24):

```python
run = run_case(refund, file={"order_id": "ord-1", "amount": 250}, answers=[], people=PEOPLE)
assert run.waiting_for == ["review by support"]
assert not run.closed
```

## When a system says no

A business failure is an answer, not an error (brief, D17). `payments.refund@2` declares the
outcome `declined`; when the provider declines, `pay` is done with that outcome, and
`pay.outcome` reads `"declined"`, tagged with the contract that declares it
(`system:payments.refund@2`). A step can react to it:

```json
"call_customer": {
  "kind": "task",
  "display": {"title": "Call the customer about the declined refund"},
  "roles": ["support"],
  "requires": ["pay"],
  "when": {"==": [{"var": "pay.outcome"}, "declined"]},
  "outcomes": {"called": {"display": {"title": "Customer called"}}}
}
```

```
scheduled pay#1: payments.refund@2 (order_id from system:opener; amount from person:ana), key memory/pay#1
pay#1 gave declined
started call_customer#1: waiting for called by support
```

A step's milestones are reached only when it is done with `done`: a declined refund doesn't reach
`paid`. An outcome the contract doesn't declare is never read as one: it is a failure.

## When something breaks

Systems go down, and Temporal retries them with the contract's retry policy. When the retries run
out, or an activity gives an outcome its contract doesn't declare, or a condition can't be read,
the step run **fails** and the case **needs attention** (brief, D17). The failed step is pending
work, so the case doesn't close, and nothing is skipped: other steps go on, and the failed one
waits for an operator.

```python
calls = []

def down_once(inputs):
    calls.append(inputs["idempotency_key"])
    if len(calls) == 1:
        raise ConnectionError("provider unreachable")
    return {"refund_id": "refund-ord-1"}

failed = run_case(refund, file={"order_id": "ord-1", "amount": 40},
                  answers=[("review", "approve", "ana", {"approved_amount": 40})],
                  people=PEOPLE, activities={"payments.refund@2": down_once})
assert failed.needs_attention == ["pay#1: payments.refund@2 failed: provider unreachable"]
assert not failed.closed
```

An **operator** (a role the platform team registered as operating, such as `operations`) retries
the failed run, or closes the case. A retry is the same step run, with the same idempotency key,
so a payment that did go through before the failure is not made twice (brief, D26):

```python
calls.clear()
retried = run_case(refund, file={"order_id": "ord-1", "amount": 40},
                   answers=[("review", "approve", "ana", {"approved_amount": 40}),
                            retry("pay#1", "omar")],
                   people=PEOPLE, activities={"payments.refund@2": down_once})
assert calls == ["memory/pay#1", "memory/pay#1"]
assert retried.closed
```

## Closing a case

A case closes by itself when nothing is left to do (brief, D10). Two definition keys change that:
`"closes_when": ["paid"]` closes it as soon as the milestones are reached, and `"stays_open":
true` keeps it open until a person closes it. A case whose steps all wait to be proposed needs
`stays_open`: otherwise nothing is pending when it opens, and it closes at once. `closes_when`
never cancels a step that needs attention: the case waits until an operator retries it, or a person
closes the case with a reason.

A person closes a case with a **close reason** the definition declares, with who may use it:

```json
{"close_reasons": {"duplicate": {"display": {"title": "Duplicate request"}, "roles": ["support"]}}}
```

Closing puts the case in **closing**: open tasks and approvals are cancelled, saying why; nothing
new starts; activities already running finish, since a payment can't be safely cut off halfway.
Then the case is **closed**. If something completed while closing, the case is **flagged**, so a
person can decide whether to reverse it:

```
ana closed the case as duplicate, as support
pay#1 done, giving refund_id
flagged: pay#1 completed after the close was requested
closed: duplicate, by ana
```

## Plan steps

A **plan step** runs a plan (see the plans guide) as one step of the case: several calls and
waits that belong together, written as data (brief, D13). The case references the plan by name
and version; your deployment supplies its plans, as it supplies its catalog, and a case never
defines one (brief, D28). Here the refund's payment is the plans guide's `refund-order` plan,
which looks the order up, asks a team lead, and pays:

```json
"settle": {
  "kind": "plan",
  "display": {"title": "Settle the refund"},
  "plan": "refund-order@1",
  "inputs": {"order_id": {"var": "order_id"}, "amount": {"var": "approved_amount"}},
  "requires": ["review"],
  "when": {"==": [{"var": "review.outcome"}, "approve"]}
}
```

Its `inputs` give the plan its fields, read from the case file, each with where its value came
from, so the plan's checks see the real sources: an amount a customer typed is still refused at
`payments.refund@2`. The plan carries its own approvals, so a plan step has no `approval`. Who
may not approve crosses into the plan too: the person who opened the case, and the person who
proposed the step, approve nothing inside it (brief, D25).

How the plan ends decides how the step ends:

| The plan | The step |
|---|---|
| succeeds | is done, and reaches its milestones |
| ends in a failed final state (`"final": "failed"`) | gives the outcome `failed`, which a step can react to (`settle.outcome`) |
| stops (the engine can't go on) | fails, and the case needs attention |

In a test, `plans` gives the plans by reference, and `plan_answers` answers each plan step's
waits, in order, as a plan's script does (state, outcome, who):

```python
run = run_case(
    refund_with_plan,
    file={"order_id": "ord-1", "amount": 250},
    answers=[("review", "approve", "ana", {"approved_amount": 250})],
    plans={"refund-order@1": refund_order},
    plan_answers={"settle": [("approve_refund", "approve", "sam")]},
    people=PEOPLE,
)
assert run.reached("settle")
```

```
started settle#1: plan refund-order@1 (order_id from system:opener; amount from person:ana), run memory/settle#1
settle#1 done
closed: nothing left to do
```

The plan's activities are keyed by the step's run, then their own: `memory/settle#1/pay#1`. A
plan whose waits the script doesn't answer keeps the step running, and the case open.

When the case begins closing, a running plan step stops taking answers: its open waits are
cancelled, nothing new starts in it, and an activity already running inside it finishes. The
plan then ends, the history says `settle#1 cancelled: the case is closing`, and the case closes.
A team lead's approval that arrives after the close can't pay the refund (brief, D28).

## Testing a case

`run_case` opens the case, plays the script in order, and reports where it ended: `status`
(`open`, `closing` or `closed`), `closed`, `reached(step)`, `waiting_for`, `needs_attention`,
`flags` and `history`. A script holds answers, `(step, outcome, who)` or `(step, outcome, who,
form)`, and the other things people do: `propose(step, who)`, `retry(entry, who)` and
`close(reason, who)`. An answer to a step answers its open entry; naming the entry
(`"pay.approval#1"`) answers that one. `people` gives each person their roles, as the Ventoux API
does (brief, D22); `opened_by` says who opened the case, when a person did. `activities` replaces
the fake activities; an activity raises `Outcome("declined")` for a declared outcome. `held=["pay"]`
keeps `pay`'s runs running until the script says `finish("pay#1")`.

```python
run = run_case(
    refund_with_rework,
    file={"order_id": "ord-1", "amount": 250},
    answers=[
        ("review", "approve", "ana", {"approved_amount": 250}),
        propose("review", "ana"),
        ("review", "approve", "ana", {"approved_amount": 900}),
        ("pay", "approve", "sam"),
    ],
    people=PEOPLE,
)
assert run.reached("pay")
```

Anything the engine won't accept is refused, with the reason:

| Refused when | Example |
|---|---|
| the person has none of the task's roles | `review#1 is answered by support, and eve has no role` |
| the person opened the case | `ana opened the case, so cannot approve its steps` |
| the approval was withdrawn | `pay.approval#1 was withdrawn: review started again` |
| a proposed step's requirements aren't met | `check_order requires review, which hasn't completed` |
| nobody proposes a step that starts by itself | `pay starts by itself: nobody proposes it` |
| the opening gives a field a person sets | `approved_amount is set by a person in review, never given at the opening` |
| the person retrying has no operating role | `pay#1 is retried by an operating role (operations), and ana has support` |
| the run hasn't failed | `pay#1 has not failed: nothing to retry` |
| the close reason isn't declared | `refund has no close reason 'spam': its reasons are duplicate` |
| the person closing has none of the reason's roles | `duplicate is closed by support, and eve has no role` |
| the case is closing | `the case is closing: nothing waits for an answer` |

## Running a case on Temporal

On Temporal, the same engine runs the case as a workflow: one workflow per case, for as long as
the case lives. Your deployment names its catalog and its plans in a workflow of its own:

```python
from temporalio import workflow

from ventoux.temporal.cases import CaseStart, CaseWorkflow, CaseReport
from refunds.catalog import CATALOG, PLANS  # the contracts and plans this deployment allows


@workflow.defn(name="ventoux.case")
class RefundCases(CaseWorkflow):
    catalog = CATALOG
    plans = PLANS

    @workflow.run
    async def run(self, start: CaseStart) -> CaseReport:
        return await self.drive(start)
```

A worker serves it, the plan workflow its plan steps run as (`RefundPlans`, from the plans
guide), and the code behind each contract:

```python
from ventoux.temporal.worker import case_worker

worker = case_worker(client, "refunds", RefundCases, RefundPlans, {"payments.refund@2": refund, ...})
await worker.run()
```

The client opens a case with its first values, answers it, and reads how it is going. The case's
ID is the case: `refund-A-1001` names it for as long as it lives, and opening a second case with
the same ID is refused.

```python
from decimal import Decimal

from ventoux.temporal.cases import answer, report, start_case

case = await start_case(
    client, RefundCases, refund, file={"order_id": "ord-1", "amount": Decimal("250")},
    id="refund-A-1001", task_queue="refunds",
)
assert (await report(case)).waiting_at == ["review#1"]
await answer(case, "review#1", "approve", by="ana", roles=["support"],
             form={"approved_amount": Decimal("250")})
await answer(case, "pay.approval#1", "approve", by="sam", roles=["support", "support-lead"])
assert (await case.result()).status == "closed"
```

`propose(case, step, by, roles)`, `retry(case, entry, by, roles)` and `close(case, reason, by,
roles)` do what a script's `propose`, `retry` and `close` do. `report` gives what `run_case`
reports (`status`, `waiting_for`, `needs_attention`, `flags`, `history`), and `waiting_at`, the
entries open for an answer, in the same order as `waiting_for`.

What changes from memory, and what doesn't:

- **The decisions don't change.** The same events give the same history, line for line, except
  the keys, which name the case: `key refund-A-1001/<first run ID>/pay#1`.
- **Answers, proposals, retries and closes are signals.** An answer names the entry it answers,
  `review#1` or `pay.approval#1`, never a step: after a rework, an answer to "review" could
  approve a review its sender never saw. An answer counts only for the entry open when it
  arrives; a double click, or an answer sent before its entry opens, is refused.
- **Anything refused is recorded, and the case waits on.** In memory a refusal raises from
  `run_case`; on Temporal nobody is there to catch it, so the history says what was refused and
  why, and the case goes on as if it hadn't come:

  ```
  refused sam's answer approve to review#1: review#1 is closed
  refused ana's answer approve to review: name the entry it answers, such as review#1
  refused eve's proposal of check_order: check_order is proposed by support, and eve has no role
  refused ana's retry of pay#1: pay#1 is retried by an operating role (operations), and ana has support
  refused eve's close as duplicate: duplicate is closed by support, and eve has no role
  ```

- **Activities are retried as their contract says.** Its retry policy and timeouts are the ones
  Temporal uses; a declared outcome is never retried. An activity still failing after its
  retries fails the step, and the case needs attention; every attempt, and an operator's retry,
  sends the same key.
- **A plan step is a child workflow,** with the ID `<case ID>/<entry>`: `refund-A-1001/settle#1`.
  Its waits are answered on the child, as the plans guide shows; the case's history shows
  the step started (`started settle#1: plan …`), and the case waits for it until the plan ends.
  When the case begins closing, it signals the child to stop: an answer sent to the child after
  that is refused, or can no longer be given once the child has ended.

  ```python
  from ventoux.temporal import client as plans

  plan = client.get_workflow_handle("refund-A-1001/settle#1")
  assert (await plans.report(plan)).waiting_at == "approve_refund#1"
  await plans.answer(plan, "approve_refund#1", "approve", by="sam", roles=["support-lead"])
  ```

- **A long case continues as new.** Temporal keeps every event of a run, and a case lives for
  weeks. After enough events, at a moment when nothing is running, the case starts a fresh run
  carrying its whole state: case file, step runs, approvals, history (brief, D27). Nothing
  changes for you: the case keeps its ID, its keys and its open entries (`review#1` is still
  answered as `review#1`), and the client always reaches its latest run. An answer sent during
  the switch is decided by one run or the other, never lost and never kept for later. A
  `report` asked at the very moment of a switch can go unanswered, reaching the run that is
  ending: ask again, and it reaches the new one.
- **Replay holds the case to its history.** A worker can stop at any point and another replays
  the case from its history; code changed to ask for something else fails the replay,
  and Temporal holds the case until the code is fixed (brief, D17).
