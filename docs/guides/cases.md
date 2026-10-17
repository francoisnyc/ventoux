# Cases: steps, a case file, and no position

> **For workflow developers.** A case is how Ventoux runs long work with people in it: one
> customer's refund, one claim. This guide shows a case as stored (the JSON `ventoux check`
> writes from your Python file), how it runs in memory, in tests, and how it runs on Temporal,
> with plans and existing Temporal workflows as steps.

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
    },
    "call_customer": {
      "kind": "task",
      "display": {"title": "Call the customer about the declined refund"},
      "roles": ["support"],
      "requires": ["pay"],
      "when": {"==": [{"var": "pay.outcome"}, "declined"]},
      "outcomes": {"called": {"display": {"title": "Customer called"}}}
    }
  },
  "sequence": ["review", "pay"]
}
```

Read aloud: a refund's case file holds the order, the amount asked for, and the amount approved.
Someone in support reviews the request and approves it, saying how much, or rejects it. Then, if
the review approved it, the customer is refunded the approved amount; above 100, a team lead
approves the payment first. Review first, then pay. If the payment provider declines the refund,
someone in support calls the customer.

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
pay#1 done, giving refund_id from untrusted:undeclared
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

**Approvers see what they approve** (brief, D16). A field may be hidden from some roles (the
case data guide's `visible_to`). A person who can't see a value the step reads, in its inputs,
its `when` or the approval's `when`, can't approve it: `lee can't see approved_amount, which pay
reads: it needs support`.

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
(`system:payments.refund@2`). The refund reacts to it with its third step:

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
`paid`. An outcome the contract doesn't declare is never read as one: it is a failure. Without
`call_customer`, a declined refund would close the case, `closed: nothing left to do`, with
nobody told; `ventoux check` warns about an outcome no condition reads (`OUTCOME_UNREAD`, below).

## What a step gives: outputs in the case file

When an activity is done, each field of its output lands in the case file under the step's name,
as its outcome does: `pay.refund_id`, `kyc.risk_score`. Nothing to declare on the case: the
contract says what the activity gives, and of which type. The latest run's values are the ones
read, and a step done with a declared outcome (`declined`) gives no output.

Each value carries the source its contract declares for that field (brief, D12), never one the
activity sends back. A field the contract declares no source for is `untrusted:undeclared`
(brief, D6), and the history says so:

```
scheduled pay#1: payments.refund@2 (order_id from system:opener; amount from person:ana), key memory/pay#1
pay#1 done, giving refund_id from untrusted:undeclared
```

`pay.refund_id` can be shown to people and put in a draft, but an input that accepts only trusted
data refuses it, and its step fails before it starts. The fix is in the contract, not the case:
the platform team declares `refund_id`'s source in `payments.refund@3`, and the case adopts it. A
field the contract doesn't declare at all never reaches the case file.

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
assert failed.needs_attention == ["pay#1: payments.refund@2 failed with ConnectionError: ‹sensitive›"]
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
true` keeps it open when nothing is left to do, until a person closes it or `closes_when` does. A
case whose steps all wait to be proposed needs `stays_open`: otherwise nothing is pending when it
opens, and it closes at once. `closes_when` never cancels a step that needs attention: the case
waits until an operator retries it, or a person closes the case with a reason. Meanwhile nothing
new starts: a step waiting for `paid` doesn't start, a proposal is refused (`paid is reached, so
the case closes once notify#1 is retried, or a person closes it: nothing new starts`), and an
approval given meanwhile starts nothing; the retried run still runs, and closes the case when it
completes.

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
pay#1 done, giving refund_id from untrusted:undeclared
flagged: pay#1 completed after the close was requested
closed: duplicate, by ana
```

## Plan steps

A **plan step** runs a plan (see the plans guide) as one step of the case: several calls and
waits that belong together, written as data (brief, D13). The case references the plan by name
and version; your deployment supplies its plans, as it supplies its catalog, and a case never
defines one (brief, D28). Here the refund's payment is the plans guide's `refund-order` plan,
which looks the order up, asks a team lead, and pays. `settle` takes `pay`'s place, and
`call_customer` then requires `settle` and runs when `settle.outcome` is `failed`:

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
A team lead's approval that arrives after the close can't pay the refund (brief, D28). An activity
that was already running, and finished or failed after the close, flags the case, as a step does:
`settle#1: payments.refund@2 completed after the close was requested`.

## Workflow steps

A **workflow step** runs an existing Temporal workflow, written by another team in any SDK
language, as one step of the case (brief, D6). The case names its **workflow contract**, which the
platform team registered in the catalog (see the activities guide); the deployment binds it to a
workflow type and a task queue. Here the refund also checks the customer, alongside the review:

```json
"kyc": {
  "kind": "workflow",
  "display": {"title": "Check the customer"},
  "workflow": "kyc.check@1",
  "inputs": {"customer_id": {"var": "customer_id"}}
}
```

It is checked like an activity step: its requirements and condition, an `approval` if it has one
(a high-risk workflow needs one), and its inputs against the contract's input policies, with the
real sources. Its run is named `memory/kyc#1` (on Temporal, its child workflow's ID); a workflow
that writes gets that name as its key, in the input its contract names for it. When it is done,
its output lands in the case file with the sources its contract declares:

```
started kyc#1: workflow kyc.check@1 (customer_id from system:opener), run memory/kyc#1
kyc#1 done, giving analyst_notes from untrusted:llm; contact_email from untrusted:undeclared; risk_score from system:kyc; status from system:kyc
```

So a later step can require an approval when `kyc.risk_score` is over 70, which the KYC system
decided; but `kyc.analyst_notes`, written by a model, can't decide anything, and only goes where
an input accepts untrusted data, such as a draft a person reviews. Nobody declared where
`contact_email` comes from, so a welcome letter can't be addressed with it:

```
welcome#1 failed: letters.draft@2 takes to_customer only from a system or a person, never from untrusted data, and this value comes from kyc.contact_email (untrusted:undeclared)
```

The case needs attention, and nothing is drafted. The KYC team declares the field's source in
`kyc.check@2`, or the case takes the address from somewhere it trusts.

A workflow step that fails, or runs past its contract's `timeout`, fails: the case needs attention,
and an operator retries it, with the same key. A workflow contract the deployment hasn't bound, or
a step naming an activity contract (or an activity step naming a workflow contract), fails the
step too: nothing guesses where to run it. When the case begins closing, a running workflow step
finishes, as an activity does; if it completes after the close, its output still lands, and the
case is flagged.

A workflow step never waits for people: put the human work in a task step before or after it.

## Rules

A step asks "may I start now?" after every event, and starts as soon as the answer is yes: it
reacts to how the case *is*. Some things a case should react to are moments instead: the
customer has just been checked, and the score says high risk. A **rule** says it: *on* a moment,
*when* a condition holds, *then* act on the case.

Give the refund's KYC check (above) `"reaches": ["checked"]`, and add a rule and a step for the
fraud team:

```json
"rules": {
  "flag_high_risk": {
    "display": {"title": "Flag a high-risk customer"},
    "on": {"reached": "checked"},
    "when": {">": [{"var": "kyc.risk_score"}, 70]},
    "then": {"reach": ["high_risk"]}
  }
}
```

```json
"review_risk": {
  "kind": "task",
  "display": {"title": "Review a high-risk customer"},
  "roles": ["fraud"],
  "requires": ["high_risk"],
  "outcomes": {"cleared": {"display": {"title": "Customer cleared"}}}
}
```

Read aloud: once the customer is checked, if the risk score is over 70, the customer is high risk,
and someone in fraud reviews them. `high_risk` is declared under `milestones`, like any other.

```
kyc#1 done, giving analyst_notes from untrusted:llm; contact_email from untrusted:undeclared; risk_score from system:kyc; status from system:kyc
reached checked
flag_high_risk#1 on reached checked: reaching high_risk
reached high_risk
started review_risk#1: waiting for cleared by fraud
```

A rule's `on` names one moment:

| `on` | The rule fires |
|---|---|
| `"opened"` | once, when the case opens, with its first values in the case file |
| `{"reached": "checked"}` | once, when the milestone is reached: a milestone is never undone |
| `{"started": "assess"}` | each time a run of the step starts: a task opening, an activity or workflow scheduled, a plan started, a stale fact fetched again. A retry is the same run, so it doesn't start again |

`when` is optional, and reads the case file as it is at that moment, as a step's `when` does: it
is checked against the case's values first, so a misspelt outcome is an error, never false. With
its `when` false, a rule does nothing, and the history says so: `flag_high_risk#1 on reached
checked: its condition is false`. `then` lists the milestones it reaches.

**A rule reacts to a moment, never to a state.** It remembers nothing: when its moment comes, it
reads the case file then, once. To start something as soon as a state holds, and whenever it
holds again, write a step's `requires` and `when`, which are read after every event.

**Rules run in order, before the case settles.** Moments are taken as they happen, and the rules
on one moment in the order they are written. A milestone a rule reaches is a moment too, so rules
can follow rules, and a step that requires it starts in the same decision. The case closes, if
nothing is left to do, only after all of that.

**A rule that can't be read needs attention.** If its `when` reads a value nobody set, or one of
the wrong type, it reaches nothing, the case needs attention and doesn't close. Fire the same rule
`"on": "opened"`, before the check has run:

```
flag_high_risk#1 failed: flag_high_risk's condition kyc.risk_score > 70 can't be evaluated: kyc.risk_score has no value
```

An operator retries it, `retry("flag_high_risk#1", "omar")`, which reads its condition again, on
the case file as it is then; or closes the case.

**Untrusted data can't decide.** Reaching a milestone decides something for the case. A rule
whose `when` reads a value from an untrusted source reaches nothing, and says why, never quoting
the value. Here the rule reads what a model wrote about the customer:

```json
"when": {"==": [{"var": "kyc.analyst_notes"}, "high risk"]}
```

```
flag_high_risk#1 on reached checked: reaches nothing: its condition reads kyc.analyst_notes, from untrusted:llm, and untrusted data can't decide
```

Read the notes in a task instead, and let a person's answer reach the milestone: a person's answer
is trusted, and the history shows who.

**Rules stop with the close.** Once every `closes_when` milestone is reached, no rule acts, even
on the moment that reached the last one, and even while a failed step holds the close. Each rule
that would have fired says so. With `"closes_when": ["checked"]`:

```
flag_high_risk#1 on reached checked: not applied: checked is reached, so the case closes and nothing new is decided
```

**What the check says about rules.** `ventoux check` reads rules too: a milestone a rule may
reach counts as reachable, every `when` taken as possibly true, but proves nothing about what is
set; a rule's `when` is type-checked; and two codes are its own:

| Code | Kind | What is wrong | Example message |
|---|---|---|---|
| `NEVER_FIRES` | error | a rule's moment can never come, or comes only once every `closes_when` milestone is reached | `flag_high_risk can never act: it fires on reached checked, and refund closes once checked is reached, when nothing new is decided: fire it on an earlier moment, or remove checked from closes_when` |
| `UNTRUSTED_TRIGGER` | error | a rule's `when` reads a value that is untrusted whoever writes it, so it never acts | `flag_high_risk's condition reads kyc.analyst_notes, which comes from untrusted:llm whoever writes it, and untrusted data can't decide, so it never reaches high_risk: read a value a person or a trusted system gives, such as a task's answer` |

## Testing a case

`run_case` opens the case, plays the script in order, and reports where it ended: `status`
(`open`, `closing` or `closed`), `closed`, `reached(step)`, `waiting_for`, `needs_attention`,
`flags` and `history`, and `view(roles=...)`, the case file as people with those roles see it
(the case data guide). A script holds answers, `(step, outcome, who)` or `(step, outcome, who,
form)`, and the other things people do: `propose(step, who)`, `retry(entry, who)`,
`close(reason, who)` and `shown(field, who)`, which records that a referenced record was shown.
An answer to a step answers its open entry; naming the entry (`"pay.approval#1"`) answers that
one. `people` gives each person their roles, as the Ventoux API
does (brief, D22); `opened_by` says who opened the case, when a person did. `activities` replaces
the fake activities; an activity raises `Outcome("declined")` for a declared outcome. `workflows`
replaces the fake workflows in the same way, a function from the inputs to the output, by
reference: `workflows={"kyc.check@1": lambda inputs: {...}}`. A workflow contract with no function
there is not bound, and its step fails. `held=["pay"]`
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
| the approver can't see a value the step reads | `lee can't see approved_amount, which pay reads: it needs support` |

## Running a case on Temporal

On Temporal, the same engine runs the case as a workflow: one workflow per case, for as long as
the case lives. Your deployment names its catalog, its plans and where each workflow contract runs (its
**binding**: the workflow type and task queue) in a workflow of its own:

```python
from temporalio import workflow

from ventoux.temporal.bindings import Binding
from ventoux.temporal.cases import CaseStart, CaseWorkflow, CaseReport
from refunds.catalog import CATALOG, PLANS  # the contracts and plans this deployment allows


@workflow.defn(name="ventoux.case")
class RefundCases(CaseWorkflow):
    catalog = CATALOG
    plans = PLANS
    workflows = {"kyc.check@1": Binding(workflow="KycCheck", task_queue="kyc")}

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
the same ID is refused. An ID has no `/`, and opening a case makes its key: the client connects
with `data_converter(keys)`, as the case data guide shows.

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
entries open for an answer, in the same order as `waiting_for`; once the case has closed, it is
the report the case returned then, read without replaying it. `view(case, roles)` gives the
case file as people with those roles see it, filtered inside the worker, and `shown(case, field,
by, roles)` records that a referenced record was shown.

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
  retries fails the step, and the case needs attention (`pay#1: payments.refund@2 failed with
  ConnectionError: ‹sensitive›`: the type of what it raised, never what it said, which stays
  encrypted in Temporal; the case data guide says why); every
  attempt, and an operator's retry, sends the same key.
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

- **A workflow step is a child workflow** of the type and on the task queue its binding names,
  with the ID `<case ID>/<entry>`: `refund-A-1001/kyc#1`. Its team's worker serves it; yours
  doesn't need to. It runs for at most its contract's `timeout`, and a retry starts it again under
  the same ID, with the same key.
- **A long case continues as new.** Temporal keeps every event of a run, and a case lives for
  weeks. After enough events, at a moment when nothing is running, the case starts a fresh run
  carrying its whole state: case file, step runs, approvals, history (brief, D27). Nothing
  changes for you: the case keeps its ID, its keys and its open entries (`review#1` is still
  answered as `review#1`), and the client always reaches its latest run. An answer sent during
  the switch is decided by one run or the other, never lost and never kept for later. A
  query asked at the very moment of a switch can go unanswered, reaching the run that is
  ending; asked again, it reaches the new one. `report` does so itself: it waits a short while
  for each answer, asks again up to ten times, then raises `CaseUnanswered`. A query of your
  own (`view`, or one you send) should do the same.
- **Replay holds the case to its history.** A worker can stop at any point and another replays
  the case from its history; code changed to ask for something else fails the replay,
  and Temporal holds the case until the code is fixed (brief, D17).

## What `ventoux check` proves about a case

`ventoux check` reads the whole definition before any case opens and lists every problem at once,
each with its path, a code and a message saying what is wrong, then what to do. Nothing runs. The
command arrives with the Python builder (layer 14); today, call `validate_case(case, catalog)`
from `ventoux.case.validate`, which gives the same list.

An **error** is something proven wrong for every case of the definition, or something the check
can't read: the definition is refused. A **warning** may be what you meant, or depends on things
the check can't know: the definition is accepted, and you are told. A warning lets a definition
through, never a run: the engine still checks every event as the case runs, whether or not the
definition was ever checked.

### Steps that can never run

Here is a claim: check the customer, then an adjuster assesses the claim, then it is paid,
behind a team lead's approval. If the payment is declined, the adjuster calls the customer.

```json
{
  "case": "claim",
  "display": {"title": "Insurance claim"},
  "fields": {
    "customer_id": {"type": "reference", "system": "crm", "display": {"title": "Customer"}},
    "order_id": {"type": "reference", "system": "orders", "display": {"title": "Insured order"}},
    "payout": {"type": "number", "display": {"title": "Payout"}}
  },
  "milestones": {
    "checked": {"display": {"title": "Customer checked"}},
    "assessed": {"display": {"title": "Claim assessed"}},
    "paid": {"display": {"title": "Claim paid"}}
  },
  "steps": {
    "check": {
      "kind": "workflow",
      "display": {"title": "Check the customer"},
      "workflow": "kyc.check@1",
      "inputs": {"customer_id": {"var": "customer_id"}},
      "reaches": ["checked"]
    },
    "assess": {
      "kind": "task",
      "display": {"title": "Assess the claim"},
      "roles": ["adjuster"],
      "requires": ["checked"],
      "outcomes": {
        "accept": {
          "display": {"title": "Accept the claim"},
          "sets": ["payout"],
          "reaches": ["assessed"]
        },
        "deny": {"display": {"title": "Deny the claim"}}
      }
    },
    "pay": {
      "kind": "activity",
      "display": {"title": "Pay the claim"},
      "activity": "payments.refund@2",
      "requires": ["assessed"],
      "inputs": {"order_id": {"var": "order_id"}, "amount": {"var": "payout"}},
      "approval": {"roles": ["support-lead"], "display": {"reason": "Every payout needs a team lead"}},
      "reaches": ["paid"]
    },
    "call_customer": {
      "kind": "task",
      "display": {"title": "Call the customer about the declined payout"},
      "roles": ["adjuster"],
      "requires": ["pay"],
      "when": {"==": [{"var": "pay.outcome"}, "declined"]},
      "outcomes": {"called": {"display": {"title": "Customer called"}}}
    }
  },
  "closes_when": ["paid"]
}
```

Change `assess` to also require `paid`:

```json
"requires": ["checked", "paid"]
```

Run as it is, the case checks the customer, and then nothing can start: `assess` waits for `paid`,
which only `pay` reaches, and `pay` waits for `assessed`, which only `assess` reaches; and
`call_customer` waits for `pay`. Nothing is left to do, so the case closes, `closed: nothing left
to do`, and nobody hears why. The check says so before any case opens:

```
steps.assess.requires  DEADLOCK  assess and pay wait on each other: assess requires paid, which
only pay reaches; pay requires assessed, which only assess reaches: remove one of these
requirements
steps.call_customer.requires  NEVER_RUNS  call_customer can never run: it requires pay, which can
never run: fix pay first
closes_when  CLOSE_UNREACHABLE (warning)  paid can never be reached, so closes_when never
closes claim, and it closes when nothing is left to do: reach paid from a step that can run, or
remove it from closes_when
```

**How it knows.** The check works out everything the case could ever reach. It starts from
nothing, and adds every step whose `requires` (the `sequence` included) could all be met, with
every milestone that step, or any of its outcomes, could reach; then again, until a round adds
nothing. Whatever is left out can never happen. The order steps are written in doesn't matter: a
case has no position.

**What it can't see.** The check reads `requires`, `reaches`, who may propose a step and how the
case closes. It treats every `when` as possibly true, and every outcome as possible. So it proves
what can *never* happen, and says nothing about what depends on values:

| The check proves | It can't tell, since it depends on values or people |
|---|---|
| steps that wait on each other | a `when` that real data never makes true |
| a step requiring a milestone nothing reaches | a review answered `deny`, so `paid` is never reached: that is a path, not a deadlock |
| a step that waits for every milestone `closes_when` names, which the case closes on before the step could start: nothing new starts once they are reached, even while a failed step holds the close. It may require them, or steps that surely reach them, or come after such a step in `sequence`: `thank can never run: it runs only after draft, which reaches sent, …` | a rejected approval, or whether an operator retries a failed step; a step that only *may* reach a milestone (an activity that can end `declined`, a plan that can fail) |
| a case that closes the moment it opens | whether anyone eligible is there to answer or approve |
| a case nobody could ever close | |

### What the check says about structure

| Code | Kind | What is wrong | Example message |
|---|---|---|---|
| `DEADLOCK` | error | steps wait on each other, so none of them can run | as above |
| `NEVER_RUNS` | error | a step's requirements can never all be met, or nobody may propose it | `approve can never run: it requires reviewed, which no step or rule reaches: reach reviewed from a step or a rule, or remove the requirement` |
| `CLOSES_AT_OPENING` | error | no step starts by itself when the case opens, so it closes at once and every proposal is refused | `nothing starts by itself when claim opens, so it closes at once and every proposal is refused: let a step start by itself with nothing required, or add stays_open` |
| `NEVER_CLOSES` | error | the case stays open, no close reason names a registered role, and `closes_when` is empty or can never be met | `claim stays open, none of its close reasons' roles (supprt) is registered, and closes_when never closes it, so nobody could ever close it: name a registered role in a close reason` |
| `CLOSE_UNREACHABLE` | warning | a `closes_when` milestone can never be reached | as above |
| `UNREACHABLE_MILESTONE` | warning | no step, outcome or rule reaches a milestone, and nothing requires it | `no step or rule reaches reviewed: reach it from a step, an outcome or a rule, or remove it` |

A role nobody registered counts for nothing, as when the case runs (brief, D22): a step that
starts only when proposed, by roles none of which is registered, can never run.

### What each step calls

The check also reads each step against what it calls: the contract in the catalog, or the plan
your deployment supplies. Give it the plans as you give them to `run_case` and to your case
workflow, by reference: `validate_case(case, catalog, plans={"refund-order@1": refund_order})`.
A plan step whose plan isn't given is an error, as it would fail when the case runs.

Change the claim's `pay` to run only once the claim is accepted, with one letter wrong:

```json
"when": {"==": [{"var": "assess.outcome"}, "acept"]}
```

Run as it is, the adjuster accepts, the condition is false, and the claim is never paid. The check
reads every expression against the values the case can hold, each with its type, so it says so
before any case opens:

```
steps.pay.when  EXPRESSION_INVALID  ==[1]: assess.outcome has no outcome "acept"; its outcomes
are accept, deny
```

A message quotes a value only when it is what you wrote wrong, as here: never a title, an
approval's reason or anything from a case file.

**The values a case's expressions read**, and their types:

| Value | Type |
|---|---|
| a field of the case file | its declared type |
| a task's outcome, `assess.outcome` | one of its outcomes |
| an activity step's outcome, `pay.outcome` | `done`, or one of its contract's outcomes (`declined`) |
| a workflow step's outcome | `done` |
| a plan step's outcome, `settle.outcome` | `done` or `failed` |
| an output, `check.status` | the type its contract declares |

Anything else is not a value: reading it is an error.

| Code | Kind | What is wrong | Example message |
|---|---|---|---|
| `UNKNOWN_CONTRACT` | error | a step calls a contract the catalog doesn't hold | `payments.refund@3 is not in the catalog. Registered: payments.refund@2. Use a registered version, or register this one first.` |
| `WRONG_KIND` | error | an activity step calls a workflow contract, or a workflow step an activity | `kyc.check@1 is a workflow contract, not an activity: run it as a workflow step.` |
| `UNKNOWN_PLAN` | error | a plan step names a plan that isn't supplied, or can't be read | `no plan refund-order@2 is available: supply it with the deployment's plans` |
| `UNKNOWN_INPUT` | error | a step gives an input its contract or plan doesn't take | `payments.refund@2 has no input amout: its inputs are amount, order_id` |
| `MISSING_INPUT` | error | a step doesn't give an input its contract or plan needs | `payments.refund@2 needs the input amount: add it to inputs` |
| `ENGINE_INPUT` | error | a step gives the input the engine fills: the idempotency key | `idempotency_key is filled by the engine, never by a definition: remove it` |
| `UNKNOWN_ROLE` | error | a role nobody registered: it counts for nothing when the case runs | `supprt is a role nobody registered: the roles are adjuster, claims-sensitive, fraud, operations, privacy, support, support-lead; use one of them, or ask the platform team to register it` |
| `UNKNOWN_SOURCE` | error | a field is declared untrusted with a label nobody registered | `untrusted:custmer has a label nobody registered: the labels are customer, document, email, llm, web; use one of them, or ask the platform team to register it` |
| `UNKNOWN_SYSTEM` | error | a reference names a system nobody registered | `order_id is a reference to ordrs, which is not a registered system: the systems are crm, documents, orders, policies; use one of them, or ask the platform team to register it` |
| `EXPRESSION_INVALID` | error | an expression reads something that isn't a value, mixes types, or names an outcome that can't happen | as above |
| `APPROVAL_REQUIRED` | error | a high-risk step has no approval | `payments.refund@2 is high risk, and pay has no approval: add one` |
| `APPROVAL_ROLE` | error | a role on an approval may not approve the step's risk | `adjuster may approve no risk, and payments.refund@2 is high risk: name a role that may approve high risk` |

An approval with a `when` is fine on a high-risk step: the quickstart's refund asks a team lead
only above 100. Each of these is met when the case runs too, whether or not the definition was
checked: the step fails, the answer, proposal or opening is refused, or the role counts for
nothing (it answers, approves and sees nothing). A misspelt outcome fails the step that reads it,
never reading as false.

### Where each value comes from

The check then follows each value a step reads to where it goes: whether it may go there, and
whether it is the kind of value the step takes. Every value in the case file comes from someone
who stamps it, whatever they read to make it:

| Who writes it | Where the check says it comes from |
|---|---|
| the opening | the opener: a system, or the person who opens the case |
| a task's answer, its outcome and its form | the person who answers |
| an activity, a workflow or a plan step's outcome | the contract or plan |
| an output | the source its contract declares for it, or `untrusted:undeclared` |

A field declared `untrusted:<label>` keeps that label whoever writes it. An input reading several
fields comes from all of them, a condition inside it included. That is exactly what the runtime
records as the case runs, so a value the check refuses is refused every time the step runs.

Say the claim records the customer's own estimate, and the payout should be the lesser of the
adjuster's payout and that estimate:

```json
"estimate": {"type": "number", "source": "untrusted:customer",
             "display": {"title": "Customer's own estimate"}}
```

```json
"amount": {"if": [{"<": [{"var": "estimate"}, {"var": "payout"}]},
                  {"var": "estimate"}, {"var": "payout"}]}
```

Taking the lesser still lets the customer choose the amount: type 1 as the estimate, and 1 is
paid. `payments.refund@2` takes `amount` only from a system or a person, so the check refuses it:

```
steps.pay.inputs.amount  INPUT_POLICY  payments.refund@2 takes amount only from a system or a
person, never from untrusted data, and this value comes from estimate (the opener,
untrusted:customer): use a value a system or a person gave
```

Run as it is, the step fails with the same reason, before the payment is called. The adjuster can
read the estimate and set `payout` from it: a person's answer is trusted, and the history shows
who.

A plan step is followed into its plan: each of the plan's fields comes from what the case gives
it, and each activity in the plan is checked with that. Sending the estimate through
`refund-order@1` is refused in the same words, at the plan step's input, before the plan asks
anyone to approve a payment it could never make.

| Code | Kind | What is wrong | Example message |
|---|---|---|---|
| `REFERENCE` | error | an input that takes a reference to one system is given another system's reference, a text, or a computed value | `letters.draft@3 takes customer as a reference to crm, and is given order_id, a reference to orders: give it a reference to crm, read as it is` |
| `INPUT_POLICY` | error | an input is given a value from a source its policy refuses, whoever opens the case | as above |
| `OPENER_DECIDES` | warning | an input's policy takes a value given at the opening only when a system opens the case | `ledger.record@1 takes amount only from opener, and this value comes from amount (the opener), which is refused when a person opens the case: open it only from a system, or give amount a value a system gave` |
| `INPUT_TYPE` | error | an input is given a value of another type than it takes | `payments.refund@2 takes amount as a number, and is given a string: give it a number` |
| `NO_SOURCES` | error | a plan step gives a plan's field only values written in the definition, which come from nobody | `refund-order@1 takes amount from the case, and is given only values written in the definition, which come from nobody: give it a field of the case file` |
| `SENSITIVE_TO_WORKFLOW` | error | a workflow step is given a sensitive value: its worker doesn't hold the case's key | `kyc.check@1 is a workflow step and can't be given national_id, a sensitive field: its worker doesn't hold the case's key; give it a value that isn't sensitive` |
| `APPROVER_CANT_SEE` | warning | a role on an approval can't see a value its step reads | `support-lead can't see fraud_score, which pay reads: a person approving pay needs fraud as well; let support-lead see fraud_score, or approve with a role that does` |

`APPROVER_CANT_SEE` is a warning: a person approving holds all their roles at once, so a team lead
who also holds `fraud` may approve, and the check can't know who holds which roles. When the case
runs, an approval from anyone who can't see every value the step reads is refused (brief, D30).
An input gets one of these issues at most: the first the runtime would meet when the step runs.

### What the check warns about

Some definitions do what they say, and still surprise their author when a case runs. The check
warns about four, each of them something `run_case` really does with the definition. A warning
lets the definition through: it may be what you meant.

**An outcome nobody reads.** Take `call_customer` out of the quickstart's refund. When the
provider declines, `pay#1 gave declined`, nothing else starts, and the case closes, `closed:
nothing left to do`, with nobody told:

```
steps.pay  OUTCOME_UNREAD (warning)  pay may end declined, and no condition tells that from done,
so the case goes on and nobody is told: add a step that runs when pay.outcome is declined
```

Each outcome a contract declares is checked on its own, and so is a plan step's `failed`. An
outcome is read when some condition can tell it from `done`: it compares the step's outcome with
it, or with `done` (`==`, `!=`, `in`). A task's outcomes get no warning: a `reject` that does
nothing is how a "no" is written, and the person who chose it knows.

**A value read before it is surely set.** Leave `pay`'s `when` out. When the review is rejected,
`pay` still starts, reads `approved_amount`, which only `approve` sets, and fails: the case needs
attention instead of closing:

```
steps.pay.approval.when  MAY_BE_UNSET (warning)  pay reads approved_amount, which only review's
approve sets, and pay may run after review is answered otherwise: then pay fails and needs
attention: run pay only when review.outcome is approve
```

A value is surely set where a step reads it when:

- it is given at the opening;
- the step waits for the step that sets it (`requires`, directly or through the steps it
  requires, or `sequence`), and every way that step can end sets it: a task all of whose outcomes
  set the field; an activity whose contract declares no outcomes, for its outputs; any step, for
  its outcome;
- the step requires a milestone that only setting it reaches: the claim's `pay` requires
  `assessed`, which only `accept` reaches, and `accept` sets `payout`;
- or a guard says so. The step's `when` is read first, so it guards the approval's `when` and the
  inputs: a `when` that is, or holds in an `and` or an `if`'s condition, `review.outcome ==
  "approve"` (an outcome that sets the field), `in` a list of such outcomes, `exists`, or the
  writer's outcome `== "done"` for its outputs. An `or` guards what all its parts guard:
  `approve` or `partial`, if both set the field. Inside a condition only an `if` guards its
  branch: `and` and `or` read all their parts (brief, D20). An input reads every value it names,
  both branches of an `if` and an `exists` included, since where its value comes from is worked
  out from all of them (brief, D36): only the step's `when` guards an input.

If the step that sets the value can only run after the step that reads it, and the step reads
it every time it starts (not in a condition's `if` branch), it fails every time. That is an
error:

```
steps.notify.inputs.refund  SET_AFTER  notify reads pay.refund_id, which only pay gives, and pay
runs only after notify: notify fails every time it starts: read it in a step that comes after
pay, or run notify after pay
```

Proposing the step again changes nothing: the value is set only once the step is done, and it is
done only after a run that read it. A value read in a condition's `if` branch, which some runs
don't take, gets the warning instead: `notify reads pay.refund_id, which only pay gives, and pay
runs only after notify: when notify reads it, it fails and needs attention: read it in a step
that comes after pay`.

**A `max_age` that can only end in attention.** Only a read is fetched again (brief, D33). A
`max_age` on any other fact means a person decides each time it is stale:

```
steps.pay.max_age.approved_amount  NEVER_REFRESHED (warning)  approved_amount comes from a
person, in review, and can't be fetched again: whenever it is older than pay's max_age allows,
pay needs attention: keep it only if a person should decide each time
```

The same for a fact from the opening, from an activity that writes, notifies or computes, from a
workflow step or a plan step, and from a read whose step always needs an approval: a refresh
never asks for one.

**An approval that guards a neighbouring value.** An approval guards the values its step uses
(brief, D9). Write the refund's approval on the amount asked for:

```json
"when": {">": [{"var": "amount"}, 100]}
```

A customer asks for 50 and the reviewer approves 5000: no approval is needed, and 5000 is paid.

```
steps.pay.approval.when  APPROVAL_ELSEWHERE (warning)  pay's approval reads amount, and pay is
given only order_id and approved_amount: it guards a value pay doesn't use: read one of those
in its when
```

| Code | Kind | What is wrong | Example message |
|---|---|---|---|
| `OUTCOME_UNREAD` | warning | an activity or plan step may end with an outcome no condition tells from `done` | as above |
| `MAY_BE_UNSET` | warning | a step reads a value that may not be set yet when it runs | as above |
| `SET_AFTER` | error | a step reads, every time it starts, a value only steps after it set | as above |
| `NEVER_REFRESHED` | warning | a `max_age` names a fact that can never be fetched again | as above |
| `APPROVAL_ELSEWHERE` | warning | an approval's `when` reads none of the fields its step is given | as above |

A step already refused by an error gets none of these, and neither does a value whose step has
one: one cause, one issue. No message quotes a value from a case file, or a literal of the
definition.
