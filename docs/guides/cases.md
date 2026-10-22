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
- it isn't running, and it hasn't run yet (or it is `repeatable`, and a person proposes it or a
  rule starts it).

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
only when a person **proposes** it, or a rule starts it ("Rules", below); `proposed_by` names
which people may. The engine checks the proposal against admission, so a person can't start a
step whose requirements aren't met:

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

If a fact the step needs fresh is stale and can be fetched again, the proposal is accepted and waits
while the fact is fetched again; then the step starts, or doesn't, on the fresh value (the case data
guide, "Fresh facts"). Proposing the step again while it waits is refused, and so is a proposal
whose stale fact can't be fetched again, saying why. A step whose latest run needs attention isn't
started again beside it ("When something breaks").

A **repeatable** step may run again, and only when proposed or started by a rule: it never starts
itself a second time, or it would never stop. A task's `outcome` is then its latest answer, and a
field its form sets holds the latest value (brief, D9). This is how a review is sent back for
rework, with two keys added to `review`:

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
met, its `when` holds, and the approval's own `when` holds now (`approved_amount > 100`), or reads
untrusted data, which can add an approval but never remove one ("Rules", below).

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

## Several approvers

Some steps need more than one person's approval: "two team leads approve a refund above 10,000".
`count` on the approval says how many distinct people must approve (brief, D47); left out, it is
1. The four-eyes refund (`examples/refund/refund-four-eyes.json`) is the refund with:

```json
"approval": {
  "when": {">": [{"var": "approved_amount"}, 10000]},
  "roles": ["support-lead"],
  "count": 2,
  "display": {"reason": "Refunds over 10,000 need two team leads"}
}
```

`count` is a whole number of at least 1: `0`, `"2"`, `2.0` and `true` are refused when the
definition is read. The Python builder (layer 14) will call `count: 2` `four_eyes`.

**One entry collects the answers.** The approval is still one act with one entry,
`pay.approval#1`. It stays open until two different people have approved it; the second approval
gives it, and the payment is scheduled in the same decision:

```
asked pay.approval#1: approval of pay by support-lead, from 2 people
sam answered pay.approval#1 approve as support-lead: 1 of 2 given
lee answered pay.approval#1 approve as support-lead: 2 of 2 given
scheduled pay#1: payments.refund@2 (order_id from system:opener; amount from person:ana), key memory/pay#1
```

Between the two, the case waits for the same entry, saying how far it has got, the same to
everyone:

```python
run = run_case(
    refund_four_eyes,
    file={"order_id": "ord-1", "amount": 12000},
    answers=[("review", "approve", "ana", {"approved_amount": 12000}), ("pay", "approve", "sam")],
    people=PEOPLE,
)
assert run.waiting_for == ["approval of pay by support-lead: 1 of 2 given"]
assert not run.reached("pay")
assert not run.closed
```

The approval sheet says who has approved and how many more are needed (`approved_by`,
`needed`), beside the facts.

**Each approver is someone else.** Every approver passes the checks one approver passes ("Approvals
in a case", above): the reviewer who set the amount, the person who opened the case and the
person who proposed the run approve nothing. Then one more: a person answers an entry once.
Sam answering again, approve or reject, is refused: `sam has already approved pay.approval#1: it
needs 1 more person`. Once an entry is withdrawn and asked again, the count starts from nothing,
and Sam may approve the new entry, since he judges new values.

**One rejection rejects it.** Two people must agree, and one is enough to refuse: a *reject* by
anyone who may answer closes the entry, whatever was approved before (`pay#1 won't run: lee
rejected pay.approval#1, which 1 of 2 had approved`). A retried run goes back to failed, needing
attention, as with one approver. Whoever rejected may answer a later entry like anyone.

**Withdrawn whole.** Anything that withdraws an open approval (a review answered again, a value
`pay` reads changed, by a person, a rule or a refresh) withdraws the entry with every approval on
it, saying how many there were: `withdrew pay.approval#1: review started again, with 1 of 2
approvals given`. A rule's stop and a close cancel it the same way. Freshness is checked once the
count is reached, before the payment starts: a stale fact is fetched again, and a new value
withdraws the approvals given.

Set aside (brief, D47): different roles for different approvers, and `count` in a plan's approval
state.

## What a waiting case reports

A case closes when nothing is left to do (brief, D10). While a task or an approval is open, it
stays open, and `waiting_for` says what it waits for, in the order they opened (brief, D24):

```python
run = run_case(refund, file={"order_id": "ord-1", "amount": 250}, answers=[], people=PEOPLE)
assert run.waiting_for == ["review by support"]
assert not run.closed
```

A step waiting for an event from outside is listed the same way, with who sends it:
`receipt_sent from portal` ("Events from outside", below).

A timer that is set keeps the case open too, but waits on nobody: it is listed in `timers`, not
`waiting_for` ("Rules on time", below).

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

**A retry waits only for what can still let it start** (brief, D26, as amended): its approval,
a fact fetched again, or a step it requires that is still on its way and shown. Anything else
sends it back to needing attention, as the run it is, saying why and what to do:

- its approval is rejected: `pay#1 won't run: sam rejected pay.approval#1, so it needs attention
  again`, and it needs attention as `pay#1: sam rejected pay.approval#1, the approval of its
  retry: retry it to ask again, or close the case`. Its side effect may or may not have happened,
  so the case can't close on it; there is no new run of `pay`;
- its condition is false now: `pay#1 failed again: its retry can't start: review.outcome =
  "approve" is false now`, the condition as the engine writes it, never a value from the case
  file;
- a step it requires ended without completing (a rule stopped it, or its approval was
  rejected): `pay#1 failed again: its retry can't start: pay requires review, which hasn't
  completed`.

A retry is never refused on a condition that reads a fact the step needs fresh and has gone
stale: the fact is fetched again first, if anything can fetch it, then the condition is read. If
nothing can (a person's answer, say), the retry fails at once on the fact's age, as any start
does, saying why: `pay#1 failed: review.outcome was obtained 2 days ago, and pay needs it at most
1 day old: it came from a person, so it can't be fetched again`.

Only a step's latest run is retried. Once a step has run again since a run failed (a refresh
scheduled beside one that failed, say), a retry of the earlier run could never start, so it is
refused, and nothing in the case changes: `check_order#2 can't be retried: check_order#3 has run
since, and only a step's latest run runs again: close the case`.

**Nothing starts beside a failed run.** Say `check_order` is `repeatable`. While `check_order#1`
needs attention, proposing `check_order` again is refused (`check_order#1 needs attention: retry
it, or close the case`), and so is a rule's start. A new run would skip the failed one by another
name, and the operator's retry of it would never be scheduled; for a step with side effects, such
as a payment, the new run's new key could make them happen twice (brief, D17, D26).

## Closing a case

A case closes by itself when nothing is left to do (brief, D10). Two definition keys change that:
`"closes_when": ["paid"]` closes it as soon as the milestones are reached, and `"stays_open":
true` keeps it open when nothing is left to do, until a person closes it or `closes_when` does. A
case whose steps all wait to be proposed needs `stays_open`: otherwise nothing is pending when it
opens, and it closes at once. `closes_when` never cancels a step that needs attention: the case
waits until an operator retries it, or a person closes the case with a reason. Meanwhile nothing
new starts: a step waiting for `paid` doesn't start, a proposal is refused (`paid is reached, so
the case closes once notify#1 is retried, or a person closes it: nothing new starts`), an
approval given meanwhile is let go, saying so (`goodwill not started: paid is reached, …`), and a
proposal waiting for a fact is dropped; the retried run still runs, and closes the case when it
completes.

A person closes a case with a **close reason** the definition declares, with who may use it:

```json
{"close_reasons": {"duplicate": {"display": {"title": "Duplicate request"}, "roles": ["support"]}}}
```

Closing puts the case in **closing**: open tasks and approvals are cancelled, saying why; nothing
new starts; activities already running finish, since a payment can't be safely cut off halfway.
A running plan step is stopped, and a running workflow step finishes too, unless its contract
declares it `cancellable` (see "Workflow steps"). Then the case is **closed**. If something completed while closing, the case is **flagged**, so a
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

**A plan never branches on untrusted data** (brief, D49). A plan transition whose condition reads
a value from an untrusted source stops the plan when it is tried, whatever the value says, and the
step needs attention: `settle#1: check-only@1 stopped: on done, the transition to paid reads note
(untrusted:customer), and untrusted data can't choose a plan's path`. `ventoux check` refuses the
input that carries such a value into a field a transition reads (`UNTRUSTED_TRIGGER`), or warns
when only some writers make it untrusted (`WRITER_DECIDES`). Branch in the case instead: a step's
`when`, or a rule, starts the step that carries each branch, and its inputs are checked (see
"Rules that start steps"); or a person's task decides.

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

A rule can stop a plan step too (see "Rules that stop steps"): the plan stops the same way, and
the history says which rule's entry stopped it, `settle#1 cancelled: stopped by withdraw#1`.

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

A workflow step that fails, runs past its contract's `timeout`, or is cancelled from outside the
case (by someone using Temporal's own tools), fails: the case needs attention,
and an operator retries it, with the same key. A workflow contract the deployment hasn't bound, or
a step naming an activity contract (or an activity step naming a workflow contract), fails the
step too: nothing guesses where to run it. When the case begins closing, a running workflow step
finishes, as an activity does; if it completes after the close, its output still lands, and the
case is flagged. A workflow whose contract declares `cancellable: true` (see the activities guide)
is cancelled instead, and the case waits for it to end: `kyc#1 cancelled: the case is closing`,
then `flagged: kyc#1 cancelled after the close was requested`, since what it did before the
cancellation stands. A rule's stop does the same to it.

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
| `{"started": "assess"}` | each time a run of the step starts: a task opening, an activity or workflow scheduled, a plan started, a stale fact fetched again. A run starts once: a retry of a run that had started is the same run, and doesn't start again; a run that failed before it started starts when the operator's retry runs it |
| `{"answered": "review"}` | each time a run of the task is answered, whatever the outcome. It names a task: an activity, a workflow or a plan finishing is not a moment, so a loop of rules always comes round through a person |

`when` is optional, and reads the case file as it is at that moment, as a step's `when` does: it
is checked against the case's values first, so a misspelt outcome is an error, never false. With
its `when` false, a rule does nothing, and the history says so: `flag_high_risk#1 on reached
checked: its condition is false`. `then` lists the milestones it reaches, the steps it starts
and the steps it stops (below): at least one of them.

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

**Rules that start steps.** A rule's `then` may `start` steps: the engine proposes a run, as a
person does, and admission decides, as it does for a person's proposal. This is how a case sends
work back by itself. Here a team lead checks each approved review of the refund, and a review
sent back is asked again:

```json
"rules": {
  "check_review": {
    "display": {"title": "Have an approved review checked"},
    "on": {"answered": "review"},
    "when": {"==": [{"var": "review.outcome"}, "approve"]},
    "then": {"start": ["lead_check"]}
  },
  "send_back": {
    "display": {"title": "Send the review back"},
    "on": {"answered": "lead_check"},
    "when": {"==": [{"var": "lead_check.outcome"}, "send_back"]},
    "then": {"start": ["review"]}
  }
}
```

```json
"lead_check": {
  "kind": "task",
  "display": {"title": "Check the approved review"},
  "roles": ["support-lead"],
  "automatic": false,
  "repeatable": true,
  "outcomes": {
    "ok": {"display": {"title": "The review is right"}, "reaches": ["lead_checked"]},
    "send_back": {"display": {"title": "Send it back for rework"}}
  }
}
```

`review` and `lead_check` are `repeatable`, `lead_checked` is declared under `milestones`, like
any other, and `pay` also requires `lead_checked`. Read aloud: when the review is approved, a team
lead checks it; when the check sends it back, the review is asked again; the refund is paid once
a check says the review is right.

```
ana answered review#1 approve as support, setting approved_amount
review#1 done
check_review#1 on answered review: starting lead_check
started lead_check#1: waiting for ok or send_back by support-lead
lee answered lead_check#1 send_back as support-lead
lead_check#1 done
send_back#1 on answered lead_check: starting review
started review#2: waiting for approve or reject by support
ana answered review#2 approve as support, setting approved_amount
review#2 done
check_review#2 on answered review: starting lead_check
started lead_check#2: waiting for ok or send_back by support-lead
lee answered lead_check#2 ok as support-lead
lead_check#2 done
reached lead_checked
send_back#2 on answered lead_check: its condition is false
```

`lead_check` names no `proposed_by`: a step a rule starts needs none, and `proposed_by` still
names which people may propose it, so proposing `lead_check` is refused: `lead_check is started
only by a rule: nobody proposes it`. Here `review` has none either, so only the rule sends it
back; keep `"proposed_by": ["support"]` from above to let support send it back by hand too.

**The engine proposes; admission decides.** The proposer is the rule's entry, `send_back#1`, never
a person. Its start is checked as a person's proposal is: the step's requirements, its `when`,
whether it is running, its fresh facts, its approval and its inputs. A start the engine can't
make is never silent:

- **recorded, and nothing runs,** when the step's requirements aren't met, or its `when` is false;
  it is already running, waiting for its approval, or waiting to start (approved, or proposed,
  and waiting for a fact); it has run and isn't repeatable; or its latest run needs attention;
  or every `closes_when` milestone is reached, even on the moment that reached the last.
  Without `repeatable` on `lead_check`: `check_review#2 on answered review: lead_check not
  started: lead_check has run, and is not repeatable`;
- **failed, needing attention,** as when a step starts by itself: its condition can't be read,
  its contract is missing, an input is refused, or a fact it needs fresh is stale. A rule's start
  never waits for a fact to be fetched again, as a person's proposal does: an operator's retry
  fetches it, then the step runs. A fact nothing can fetch again, such as a person's answer, is
  said so, and a retry fails the same way.

**Who can't approve it.** Whoever's answer the rule's `when` read can't approve the run it
starts, as for a step's own `when` (brief, D11): the rule decided that the step runs, on their
answer. The run keeps what its rule read until it starts, since the rule itself remembers
nothing.

**A loop comes round through a person.** A rule starts steps only on a moment, a step finishing
is not a moment, and a rule's start never waits for something to land: what brings a loop of
rules round again is a person, answering a task, proposing a step or retrying one. So a case can't
call a payment provider again on each decline by itself: retrying is the contract's (brief,
D17). And within one decision, a step a rule has started isn't started again by a rule: `…
review not started: a rule already started it in this decision`.

**Untrusted data can't choose what is sent.** A condition that lets a step start decides that
its inputs are sent at all. Say the welcome letter is drafted when a model's notes say so, to an
address the case was opened with:

```json
"when": {"==": [{"var": "kyc.analyst_notes"}, "send welcome"]}
```

Each input on its own is trusted, but the model chose that the letter is sent. So the untrusted
sources a condition reads are checked against each input's policy, apart from what the input
itself reads, and the run fails:

```
welcome#1 failed: letters.draft@2 takes to_customer only from a system or a person, never from untrusted data, and welcome's condition reads kyc.analyst_notes (untrusted:llm)
```

The same goes for the `when` of a rule that starts a step. Only untrusted sources count: an input
that takes a value from one system only, such as `ledger.record@1`'s amount (only from the
opener), is still sent when its step's `when` reads a person's answer. An approval whose `when`
reads untrusted data is asked whatever it says: untrusted data can add an approval, never remove
one. A rule that reaches a milestone still reaches nothing on untrusted data (above), and starts
nothing either: it doesn't act at all.

**The influence goes on with the run.** A run keeps what steered its start, and passes it on: a
rule on its start counts it as read by its condition, so one that reaches or stops doesn't act,
here on the start of a goodbye call a rule began because of what the customer wrote:

```
close_it#1 on started goodbye: reaches nothing: its moment comes from untrusted data: say_goodbye#1's condition, which started goodbye, reads cancelled.note (untrusted:customer), and untrusted data can't decide
```

A value such a rule sets carries it, and a step it starts has it checked against each input's
policy. A steered activity, workflow, plan or wait is done but reaches nothing; its outcome and
outputs carry what steered it, and so does every step that requires it. A person is where it ends:
a task's answer, its outcome's milestones and a rule on that answer decide. An approval doesn't
end it: the approver approves what the step is sent, not what follows, and may never see what
steered the start. So where untrusted data should weigh on what happens next, let a person
decide in a task, and give that task an outcome that says no. `ventoux check` says so first:
`UNTRUSTED_TRIGGER` where every way the step starts is steered, `WRITER_DECIDES` where only some
are, and `INPUT_POLICY` for a step started on such a moment.

**Rules that stop steps.** A rule's `then` may `stop` steps: it does to each one what a close
does to the whole case, and the case goes on. Here a customer who withdraws the request stops the
review and the payment; `withdrawn` is reached by a support task answered when the customer calls:

```json
"withdraw": {
  "display": {"title": "Stop the refund when the customer withdraws"},
  "on": {"reached": "withdrawn"},
  "then": {"stop": ["review", "pay"]}
}
```

```
reached withdrawn
withdraw#1 on reached withdrawn: stopping review and pay
cancelled review#1: stopped by withdraw#1
withdraw#1 on reached withdrawn: pay not stopped: no run of pay is going on
closed: nothing left to do
```

What a stop does depends on what it finds:

| The step's run | What happens |
|---|---|
| an open task | cancelled: `cancelled review#1: stopped by withdraw#1` |
| about to start: waiting for its approval, approved, or waiting for a fact to be fetched again (proposed by a person, or starting by itself) | the approval is withdrawn, or lapses, or the waiting start is dropped, and the run is recorded: `pay#1 cancelled: stopped by withdraw#1`. A fact on its way still lands |
| a running activity, or a workflow step that isn't cancellable | it finishes, since a payment can't be cut off halfway: `pay#1: stop requested by withdraw#1`. Done, its outputs land and the case is flagged: `flagged: pay#1 completed after its stop was requested by withdraw#1`. Failed, it needs attention like any failure: `pay#1 failed after its stop was requested by withdraw#1: …` |
| a running plan step | its plan stops, as when the case closes: `settle#1 cancelled: stopped by withdraw#1`. An activity that was running in it finishes; completed, it flags the case, and failed, the step needs attention |
| a cancellable workflow step | cancelled, the case waiting for it to end, and flagged: `kyc#1 cancelled: stopped by withdraw#1`, then `flagged: kyc#1 cancelled after its stop was requested by withdraw#1` |
| failed, needing attention | never stopped: `… pay not stopped: pay#1 needs attention, and a failed run is never stopped` |
| none | `… pay not stopped: no run of pay is going on` |
| running, its stop already asked | asked nothing again: `… pay not stopped: its stop is already requested` |

A stopped run is `cancelled`: neither done nor failed, so a step that requires `review` waits
for a later run of it to be done. A stop ends only the run going on now: a repeatable step may be
proposed or started again, and a step that starts by itself doesn't start by itself again. An
operator's retry of a run that failed after its stop is a person's decision: the run is no longer
one whose stop was asked.

A stopped look-up that was fetching a fact again counts for nothing, though it runs on and what
it gives lands: a step that was waiting for that fact fails, saying which refresh was stopped and
by which rule, rather than waiting and asking again, and an operator's retry fetches the fact
again.

Inside one `then`, the stop comes first, then `reach`, then `start`, and one rule can't both stop
and start the same step: `review is both stopped and started: a rule can't restart a step; stop
it here, and start it from another rule`. Like a rule that reaches, a rule whose condition reads
untrusted data doesn't stop anything (`… stops nothing: its condition reads kyc.analyst_notes,
from untrusted:llm, and untrusted data can't decide`), and once the case closes, no rule stops
anything: closing stops what is running itself.

**What the check says about rules.** `ventoux check` reads rules too: a milestone a rule may
reach counts as reachable, every `when` taken as possibly true, but proves nothing about what is
set; a step a rule may start can run; a step that a rule on the opening may let start, or start,
keeps the case from closing at once, so no `CLOSES_AT_OPENING` is given for it, nor beside a rule
on the opening with a `when`, which may fail and leave the case waiting for a person; a rule's
`when` is type-checked, and counts for the input policies of the steps it starts (`INPUT_POLICY`, at
`rules.<name>.then.start`); a rule that may stop a step keeps the check from claiming a loop
nothing ends, or a start refused on the step's own start; and these codes are its own:

| Code | Kind | What is wrong | Example message |
|---|---|---|---|
| `NEVER_FIRES` | error | a rule's moment can never come, or comes only once every `closes_when` milestone is reached; or a rule written before it on the same moment always closes the case, so it never acts ("Patterns") | `flag_high_risk can never act: it fires on reached checked, and refund closes once checked is reached, when nothing new is decided: fire it on an earlier moment, or remove checked from closes_when` |
| `UNTRUSTED_TRIGGER` | error | a rule that reaches a milestone or stops a step reads, in its `when`, a value that is untrusted whoever writes it, or fires on the start of a step untrusted data steers however it starts, so it never acts; or a call, plan or wait step every start of which is steered so reaches milestones it never will; or a plan step's input that carries such a value into a field one of its plan's transitions reads, so the plan stops there | `flag_high_risk's condition reads kyc.analyst_notes, which comes from untrusted:llm whoever writes it, and untrusted data can't decide, so it never reaches high_risk: read a value a person or a trusted system gives, such as a task's answer` |
| `NEVER_STARTS` | error | a rule's start of a step is refused every time it fires: on the opening, the step requires what can't be met by then, and the rule's condition can't fail and be retried later; or it fires on the step's own start (unless its condition may fail and the step is repeatable: a retry may come once the step is done; or the step is a task a rule may stop, which a stop cancels at once, letting the start through), or on its own answer when the step isn't repeatable; or it fires on a moment where it, or a rule written before it, always closes the case (no condition, nothing set, every `closes_when` milestone reached, not on a step's start): a start is decided after the moment's rules, and nothing new starts then | `start_pay can never start pay: it fires on opened, and pay requires lead_checked, which nothing can reach by then: start it on a later moment, or remove the requirement` |
| `LOOPS_UNTIL_CLOSED` | warning | rules start steps in a loop that comes round on each answer and that no condition, requirement or rule's stop ends (the rework rules above with their `when`s removed, on the refund with the `duplicate` close reason from "Closing a case"), so the case closes only through a close reason or `closes_when` | `check_review and send_back start lead_check and review again on every answer, and nothing ends it: refund closes only through a close reason or closes_when: give one of the rules a when that ends the loop` |

The rework loop above gets no issue: its rules' `when`s end it.

## Events from outside

Everything so far comes from inside the case: a person's answer, an activity's result, a retry, a
close. An **event** is how the world outside tells a case that something happened: the customer
cancels in the portal, a receipt is uploaded, a support agent logs a call. A case declares each
event it takes under `events`: who may send it, and what it carries.

```json
"events": {
  "cancelled": {
    "display": {"title": "The customer cancels"},
    "sent_by": {"system": "portal"},
    "payload": {
      "note": {
        "type": "string",
        "display": {"title": "What the customer wrote"},
        "source": "untrusted:customer"
      }
    }
  }
}
```

A rule reacts to it with `"on": {"event": "cancelled"}`:

```json
"withdraw_on_cancel": {
  "display": {"title": "Stop the review when the customer cancels"},
  "on": {"event": "cancelled"},
  "then": {"stop": ["review"]}
}
```

Read aloud: when the customer cancels in the portal, the review stops. The refund then has
nothing left to do, and closes:

```
cancelled#1 from portal, giving note from system:portal, untrusted:customer
withdraw_on_cancel#1 on event cancelled: stopping review
cancelled review#1: stopped by withdraw_on_cancel#1
closed: nothing left to do
```

Each arrival is an entry, `cancelled#1`, then `cancelled#2`: an event's name is unlike any step's,
milestone's or rule's.

**Who may send it.** `sent_by` names one sender: a system the platform team registered
(`{"system": "portal"}`), or people holding one of some roles (`{"roles": ["support"]}`), checked
as for a close reason. The Ventoux API, the only caller allowed to send events (brief, D19),
states who sent it. Two systems sending the same news are two events. Anything else is refused,
and nothing changes in the case:

| An event is refused when | Example |
|---|---|
| the case declares no such event | `refunded is not an event of refund: its events are cancelled` |
| another system sends it | `cancelled is sent by portal, and this one comes from system:crm` |
| a person sends a system's event | `cancelled is sent by portal, and this one comes from ana` |
| the person has none of its roles | `customer_called is sent by support, and eve has no role` |
| a payload field is missing | `cancelled's payload has no note` |
| it carries a field it doesn't declare | `cancelled's payload has no field tone: its fields are note` |
| a field is of another type | `cancelled.note is a string, and the event gives a number` |
| the case is closed | `the case is closed: it takes no more events` |

**What it carries.** Each payload field lands in the case file as `<event>.<field>`, from the
latest arrival, as an activity's output does: `cancelled.note`. Every field is given on every
arrival, as a number, a text, a boolean, an outcome or a reference; a list isn't taken yet. It
comes from its sender, `system:portal` or the person who sent it (`person:ana`), and a field's
`source` adds to that whoever sends it. That is why `note` is `untrusted:customer`: the portal
carries it, but a customer typed it, and provenance follows the content, not the system that
carries it (brief, D12). Each value is obtained when its event reaches the case, from the workflow's
time, and nothing can fetch it again.

**Arrival is a fact; content is not.** The API vouches that the portal sent `cancelled`, so a
rule may act on the arrival. What the customer wrote is untrusted: a rule that reaches or stops,
whose `when` reads it, does nothing, as for any untrusted value. With `"when": {"==": [{"var":
"cancelled.note"}, "please cancel"]}` on the rule above, the review stays open:

```
withdraw_on_cancel#1 on event cancelled: stops nothing: its condition reads cancelled.note, from untrusted:customer, and untrusted data can't decide
```

`ventoux check` refuses that rule (`UNTRUSTED_TRIGGER`). A rule that only starts steps may read
it: what it read counts for the started step's input policies, as above.

**Listening is not waiting.** A rule on an event never keeps the case open: a refund nobody
cancels still closes once it is paid. To wait for an event, write a step that waits for it, of
the kind `wait`:

```json
"wait_for_receipt": {
  "kind": "wait",
  "display": {"title": "Wait for the customer's receipt"},
  "event": "receipt_sent",
  "requires": ["review"]
}
```

with the event it waits for under `events`:

```json
"receipt_sent": {
  "display": {"title": "The customer uploads a receipt"},
  "sent_by": {"system": "portal"},
  "payload": {
    "receipt": {"type": "reference", "system": "documents", "display": {"title": "The receipt"}}
  }
}
```

and `pay` requiring `wait_for_receipt`. Read aloud: once reviewed, the refund waits for the
customer's receipt, then pays. A wait starts as any step does, by itself once its requirements are
met, when proposed, or by a rule. Its run is open until the event's next arrival, which makes it
done:

```
started wait_for_receipt#1: waiting for receipt_sent from portal
receipt_sent#1 from portal, giving receipt from system:portal
wait_for_receipt#1 done: receipt_sent#1 arrived
```

While it waits, it is pending work, and the case says so: `waiting_for` lists `receipt_sent from
portal`, beside the tasks and approvals. A stop cancels it, as it cancels an open task, and so
does a close. An answer to it is refused: `wait_for_receipt#1 waits for receipt_sent: it is sent,
never answered`. Only an arrival after it opens counts: one that came before is already in the
case file, but the wait waits for the next. A wait has no inputs, approval or `max_age`; `reaches`
names what it reaches once done.

**When the case closes.** An event that reaches a closing case is refused, and the case is
flagged, since nobody would hear of it otherwise:

```
refused cancelled from portal: the case is closing, so it takes no more events
flagged: cancelled from portal arrived while the case was closing, and was refused
```

A closed case's workflow has ended: sending it an event raises `EventRefused`, and never opens it
again. An event that reaches the case with the very answer that closes it is refused and recorded
after the closed line, `refused cancelled from system:portal: the case is closed`, as is anything a
person sends then. While a failed step holds the close (every `closes_when` milestone reached), an event's
payload still lands and a wait it ends is done, but no rule acts on it.

**Sending one.** On Temporal, `send_event(case, event, payload, by, roles)`, from
`ventoux.temporal.cases`, signals the case's workflow by its ID, as `answer` does: `by` is
`"system:portal"` for a system, or a person's identifier with their `roles`. Every event is the
same signal, whoever sends it. In a test, the script says `send(event,
payload, by)`: `send("cancelled", {"note": "please cancel"}, "system:portal")`, or a person's name,
whose roles come from `people`.

**What the check says about events.** A rule on an event may fire whenever the case is open, so
what it reaches counts as reachable; a payload field is a value of its declared type, so a
misspelt one is `EXPRESSION_INVALID`; a rule that reaches or stops on a payload field declared
untrusted is `UNTRUSTED_TRIGGER`; a person's payload given to an input that takes only a system's
value is `INPUT_POLICY`. A payload field is surely set in a rule on its event, and in a step
requiring a wait for it that is done: read anywhere else, it may not be set yet (`MAY_BE_UNSET`).
A `max_age` on it is `NEVER_REFRESHED`. A system, role or label an event names that nobody
registered is `UNKNOWN_SYSTEM`, `UNKNOWN_ROLE` or `UNKNOWN_SOURCE`, as anywhere else, and a case
naming a system nobody registered is refused when it opens.

## Rules that update the case file

A rule's `then` may `set` fields of the case file, each from an expression over the case file.
Take the claim from "What `ventoux check` proves" below, with the customer's own `estimate` from
"Where each value comes from", and three more fields: the excess the policy deducts, given when
the case opens; what is owed once the claim is assessed; and whether the claim is a large one.

```json
"excess": {"type": "number", "display": {"title": "Policy excess"}},
"owed": {"type": "number", "display": {"title": "What is owed"}},
"large_claim": {"type": "boolean", "display": {"title": "A large claim"}}
```

```json
"work_out_owed": {
  "display": {"title": "Work out what is owed"},
  "on": {"reached": "assessed"},
  "then": {"set": {"owed": {"-": [{"var": "payout"}, {"var": "excess"}]}}}
}
```

Read aloud: once the claim is assessed, what is owed is the payout less the excess. `pay` is then
given `{"var": "owed"}`.

```
ana answered assess#1 accept as adjuster, setting payout
assess#1 done
reached assessed
work_out_owed#1 on reached assessed: setting owed, from person:ana, system:opener
```

The line names the field and where its value comes from, never the value.

**What a rule may set.** A field declared under `fields`, and only one that rules alone write: a
field is given at the opening, set by people's forms, or set by rules, never two of these. The
opening giving a field a rule sets is refused (`owed is set by rules, in work_out_owed, never
given at the opening`), and so is a rule setting a field a form sets (`payout is set by a person
in assess, so a rule never sets it: set another field, and read payout there`). Several rules may set one field, as
several tasks may. A step's outputs and outcome, and what an event carries, belong to whoever
gave them and are never set by a rule. A list field is never set (its value can't be checked
yet); a reference field is set only from a reference field of the same system, read as it is.

The expression's type is the field's, checked by `ventoux check` and again when the rule fires:
a value of another type fails the rule, which needs attention, and nothing in its `then` acts.
Every expression a rule sets is read on the case file as it was when its condition was read, so
their order doesn't matter; and inside one `then` the stop comes first, then `set`, then
`reach`, then `start`, so a step a milestone lets start reads the new value. If any value the
rule sets can't be read, the rule fails as a whole: it stops, sets, reaches and starts nothing.

A rule must read something: `"set": {"owed": 0}` with no `when` is refused, since the value would
come from nobody (`work_out_owed reads no field, so what it sets would come from nobody: read a
field in its when or its values, or reach a milestone instead`). A fact without data is a
milestone.

**Where a set value comes from.** From everything its rule read: each field its expression names,
and each field its `when` names. A rule that writes a constant under a condition still says what
the condition read:

```json
"size_up": {
  "display": {"title": "Mark a large claim"},
  "on": "opened",
  "when": {">": [{"var": "estimate"}, 5000]},
  "then": {"set": {"large_claim": true}}
}
```

```
size_up#1 on opened: setting large_claim, from system:opener, untrusted:customer
```

`large_claim` is `true` because of the customer's own estimate, so it is as untrusted as the
estimate. Setting a field informs; it never decides, so the rule acts, and the value carries
where it came from: a rule that reaches a milestone on `large_claim` reaches nothing (`its
condition reads large_claim, from untrusted:customer, and untrusted data can't decide`), and an
input whose policy refuses untrusted data refuses it. A rule that both sets and
reaches, or stops, on untrusted data doesn't act at all. The same follows a person: a value
computed from Ana's answer comes from Ana, so Ana can't approve a step that is given it.

**What follows the value.** What a computed value reveals and how old it is follow what it was
computed from, the condition included:

- **Sensitive.** A value computed from a sensitive field is set only on a field declared
  `sensitive` too; it is computed inside the worker and kept encrypted like any sensitive value.
  Otherwise the definition is refused: `risk_band is set from national_id, which is sensitive:
  declare risk_band sensitive`.
- **Who sees it.** A set field's `visible_to` is no wider than that of any field it was computed
  from: a field only `fraud` sees can't be copied into one `support` sees. Otherwise refused:
  `escalate is seen by support, and is set from fraud_score, which only fraud sees: let only fraud
  see escalate`.
- **How old it is.** A computed value is as old as the oldest fact it read, never "obtained now".
  A `max_age` on it means every fact it was computed from was obtained within that age. It can't
  be fetched again: a rule doesn't fire again because a fact was refreshed. Stale, the step that
  needs it needs attention: `… it was computed by work_out_owed#1, so it can't be fetched again`.

**Which value stands.** The latest, as with an answer or an output. Two rules setting one field in
one decision set it in order (moments in the order they come, rules in the order written), and
the history shows both. A rule is never fired by a field being set: rules react to moments, and
setting a field is not one. An open approval whose step reads a field a rule changes is withdrawn,
and a given one lapses, as for any change (brief, D25). Like every rule, `set` acts only while the
case is open and not every `closes_when` milestone is reached.

**What the check says about set fields.** Where a value comes from is worked out by going round
the rules until nothing changes, as what a case can reach is: `flagged` set from `large_claim`, in
a rule written before the one that sets `large_claim`, comes from the customer too. An error
claims only what holds whichever rule wrote each value. A field several rules set may come from
untrusted data from some of them and not others; whatever is refused then is said as a warning,
since it depends on which rule wrote last. Say a second rule sets what is owed from the customer's
estimate, and `pay` is given `owed`:

```json
"owe_the_estimate": {
  "display": {"title": "Owe what the customer estimates"},
  "on": {"reached": "checked"},
  "then": {"set": {"owed": {"var": "estimate"}}}
}
```

| Code | Kind | What is wrong | Example message |
|---|---|---|---|
| `WRITER_DECIDES` | warning | a value is refused (by an input's policy, a condition steering what is sent, or a rule that can't decide on it) when some of the rules setting it wrote it, and not when others did | `payments.refund@2 takes amount only from a system or a person, never from untrusted data, and this value comes from owed (person:answering assess, the opener, untrusted:customer): owed comes from untrusted:customer when owe_the_estimate sets it, and not when work_out_owed does: whether pay is refused depends on which rule set owed last: set owed only from values the policy takes` |

A value only rules set is surely set only where a step requires a milestone that only rules
setting it reach, or a guard says so; read anywhere else, it may not be set yet
(`MAY_BE_UNSET`). A `max_age` on it is `NEVER_REFRESHED`.

## Rules on time

A rule may react to time passing: `"on": {"after": "2d", "since": <moment>}` waits two days after
its moment, then fires. Take the refund: if a review is left open for two days, a team lead chases
it.

```json
"chase_review": {
  "display": {"title": "Chase a review left open for two days"},
  "on": {"after": "2d", "since": {"started": "review"}},
  "then": {"start": ["chase"]}
}
```

with the step it starts:

```json
"chase": {
  "kind": "task",
  "display": {"title": "Chase the review"},
  "roles": ["support-lead"],
  "automatic": false,
  "outcomes": {"chased": {"display": {"title": "Review chased"}}}
}
```

Read aloud: two days after the review starts, if it is still open, a team lead chases it. When the
review starts, the rule's **timer** is set; two days later it fires, and the rule acts:

```
started review#1: waiting for approve or reject by support
set chase_review: 2d after started review#1, due 2026-01-03T00:00:00Z
chase_review#1 on 2d after started review#1: starting chase
started chase#1: waiting for chased by support-lead
```

The review stays open: nothing is cancelled or skipped because time passed (brief, D17). `after`
is an age, `30m`, `12h` or `2d`, of at least a minute, and means one firing. `since` is any other
moment a rule may name: `"opened"`, `{"started": …}`, `{"reached": …}`, `{"answered": …}` or
`{"event": …}`, never another timer. The rule's `when`, if it has one, is read when the timer
fires, on the case file as it is then.

**Time is data.** A timer's due time is the time of the event that brought its moment, plus
`after`, and it fires as an event stamped with that time, never "now": replayed on Temporal a
month later, the case decides the same way (brief, D33). Before an event is decided, every timer
due by its time fires first, soonest first; a timer due in the same second as an event fires
before it.

**A timer ends with its purpose.** It needs no `when` saying "if the review is still open": a
timer set on a run's start lives only while that run does. Answered within two days, the review is
done, and its timer goes with it:

```
ana answered review#1 approve as support, setting approved_amount
review#1 done
cancelled chase_review, 2d after started review#1: review#1 is done
```

A stopped run's timers end with it; a failed run's don't, since an operator's retry runs it again
as the same run. A timer set on any other moment, the opening, a milestone, an answer or an
event's arrival, lives until it fires: to act 30 days after the payment, set it on the milestone
the payment reaches, not on its start. And a close cancels every timer, saying so, as it cancels
open tasks; so does a close held by a failed step, after which nothing new is decided.

**A set timer keeps the case open.** It is pending work: a case with a timer set doesn't close
until the timer fires or ends. A rule waiting for its moment holds nothing: listening is not
waiting. Timers aren't in `waiting_for`, which lists what waits on people; `timers` lists each set
timer, soonest first, with its due time:

```python
run = run_case(
    refund_with_chase, file={"order_id": "ord-1", "amount": 40}, answers=[], people=PEOPLE
)
assert run.waiting_for == ["review by support"]
assert run.timers == ["chase_review: 2d after started review#1, due 2026-01-03T00:00:00Z"]
```

That line is where a due date comes from: a task's due date, if the inbox ever shows one, is the
timer set on its run, never a second clock.

**Untrusted data and time.** Time passing is a fact, so a timer set on the opening, a milestone, an
answer or an arrival carries nothing. A timer set on a run's start carries what steered that run:
if a rule started the run on untrusted data, a rule on its timer that reaches or stops does
nothing, as a rule on the start itself would ("Rules that start steps").

**Noticing a stale fact sooner.** A fact a step needs fresh is checked when an event reaches the
case (`max_age`, the case data guide): a team lead approving the payment two days after the
order was looked up waits for it to be looked up again. The engine sets no timer for it; to fetch
a read again before anyone acts, write one, on the case data guide's refund, with `check_order`
repeatable:

```json
"look_again": {
  "display": {"title": "Look the order up again a day after the review"},
  "on": {"after": "1d", "since": {"answered": "review"}},
  "then": {"start": ["check_order"]}
}
```

The approval asked on the old status is withdrawn as the look-up starts again, since `pay`
requires it, and asked again on the fresh status, so the team lead approves on a fact a day old:

```
look_again#1 on 1d after answered review#1: starting check_order
scheduled check_order#2: orders.lookup@2 (order_id from system:opener)
withdrew pay.approval#1: check_order started again
check_order#2 done, giving status from system:orders
asked pay.approval#2: approval of pay by support-lead
```

**What the check says about timers.** A timer fires only if its moment can come: one whose moment
never comes, or comes only once every `closes_when` milestone is reached, is `NEVER_FIRES`. A timer
set as the case opens keeps it open, so the case doesn't close at once. What a timer's rule reads
is checked as for a rule on its moment, since it fires later: what was set then is set still. A
timer can't re-arm itself: one set on a run ends with it, and the moments that come without a
person or an event come once.

## Reading rules

A rule stored as JSON doesn't say the parts people get wrong: what a timer measures from, what
untrusted data can't do, when the condition is read, and that rules stop with the close. Each
rule has a **reading**, the rule in plain words, worked out from the definition alone:

```python
readings = read_rules(parse_case(refund_with_chase))
assert [reading.name for reading in readings] == ["chase_review"]
```

The timer above reads:

```
chase_review: Chase a review left open for two days
  2d after each run of review starts: start chase.
  - The timer is set as each run of review starts, and ends when that run does: done, rejected or cancelled, a stop included. A failed run keeps it: a retry is the same run.
  - While it is set, the timer keeps the case open; a close cancels it.
  - Starting chase is a proposal, decided at once as a person's is: nothing starts, and the history says why, if it is already running, or it has run and isn't repeatable.
  - Only while the case decides: not once the case is closing.
```

and the rule flagging a high-risk customer ("Rules"):

```
flag_high_risk: Flag a high-risk customer
  When checked is reached (once: a milestone is never undone), if kyc.risk_score > 70 (read when it fires): reach high_risk.
  - If its condition reads untrusted data, it acts on nothing, and says why: untrusted data can't decide.
  - Only while the case decides: not once the case is closing.
```

The first line is the rule's name and title; the second its sentence: the moment, the condition
and what it does, in the order the engine does it (stop, set, reach, start). Names are the
definition's, as in the history, so a firing and its reading use the same words, and a condition
reads as the expression renderer writes it. Below come the parts that apply to this rule only:

| Fine print | On |
|---|---|
| the timer is set as each run starts, and ends when that run does; a failed run keeps it | a timer set on a run's start |
| the timer is set when its moment comes, and lives until it fires | a timer set on the opening, a milestone, an answer or an arrival |
| while it is set, the timer keeps the case open; a close cancels it | every timer |
| listening for the event doesn't keep the case open | a rule on an event's arrival |
| if its condition reads untrusted data, or untrusted data steered the run, it acts on nothing | a rule that reaches or stops |
| the values it sets carry the sources of everything it read | a rule that sets |
| what its condition reads counts for the inputs of the steps it starts | a rule that starts a step taking inputs, and neither reaches nor stops |
| stopping it cancels its open task or wait at once | a rule that stops a task or a wait |
| stopping it cancels a run waiting for its approval, or to start, at once; a running call is only asked to stop, may still finish, and is flagged if it does; a failed run isn't stopped | a rule that stops an activity, a workflow or a plan |
| starting it is a proposal, decided at once as a person's is: nothing starts, and the history says why, if it can't run now (its requirements, its condition, already running, run and not repeatable, its latest run needing attention); a stale fact it needs fresh fails the run; it waits for its approval | a rule that starts a step |
| reaching it closes the case, unless a failed run holds the close: open tasks, approvals and timers are cancelled, and running calls finish | a rule that reaches a `closes_when` milestone |
| only while the case decides: not once the `closes_when` milestones are reached, nor once the case is closing | every rule |

Two things hold for every rule, and are said once, above a definition's readings:

```
A rule remembers nothing: its condition is read once, when it fires. A rule whose condition or value can't be read acts on nothing, and needs attention.
```

A reading is never given a case file, so it can't quote a value from one: the constants it shows
(`70`, `"approve"`) are the definition's own. A rule it can't read is refused, never read with a
part left out.

## Simulating a story

A reading says what a rule does; a **story** shows it, on a timeline. A story is a JSON file: the
definition it plays, the values the case opens with, who has which roles, a fake for each contract
the definition calls, and what happens, when:

```json
{
  "title": "Nobody reviews the refund for two days",
  "definition": "../refund-chased.json",
  "file": {
    "order_id": "ord-1",
    "amount": 40
  },
  "people": {
    "ana": [
      "support"
    ],
    "sam": [
      "support",
      "support-lead"
    ]
  },
  "fakes": {
    "payments.refund@2": {
      "gives": {
        "refund_id": "refund-1"
      }
    }
  },
  "timeline": [
    {
      "at": "day 2 09:00",
      "answer": {
        "step": "chase",
        "outcome": "chased",
        "by": "sam"
      }
    },
    {
      "at": "day 2 10:30",
      "answer": {
        "step": "review",
        "outcome": "approve",
        "by": "ana",
        "form": {
          "approved_amount": 40
        }
      }
    }
  ]
}
```

Times are counted from the opening, `day 0 00:00`, which is 1 January 2026, 00:00 UTC: `"day 2"`
or `"day 2 09:00"`. They only move forward, and each becomes its event's time, so a story decides
as a real case would, reading no clock. Each entry does one thing, or nothing, for time passing:

| Entry | Does |
|---|---|
| `"answer": {"step": "review", "outcome": "approve", "by": "ana", "form": {...}}` | a person answers a task or an approval, named by its step or its `entry` (`"pay.approval#1"`) |
| `"propose": {"step": "chase", "by": "sam"}` | a person proposes a run |
| `"retry": {"entry": "pay#1", "by": "omar"}` | an operator retries a failed run or firing |
| `"close": {"reason": "duplicate", "by": "ana"}` | a person closes the case |
| `"send": {"event": "cancelled", "payload": {...}, "by": "system:portal"}` | an event arrives |
| `"finish": {"entry": "pay#1"}` | a held run finishes |
| nothing | time passes to `at` |

`until` moves time on at the end, firing what falls due. Each fake `gives` an output, gives an
`outcome` the contract declares (`{"outcome": "declined"}`), or `fails`; with `"held": true` its
runs keep running until a `finish` entry. Nothing real is called and nothing is sent: a
contract the definition calls with no fake, a fake for nothing it calls, or a plan step refuses
the story before it plays.

```sh
uv run ventoux simulate examples/refund/stories/nobody-reviews.json
```

```
Story: Nobody reviews the refund for two days
Definition: refund (../refund-chased.json)
Opens: 2026-01-01T00:00:00Z, day 0 00:00

Rules
  A rule remembers nothing: its condition is read once, when it fires. A rule whose condition or value can't be read acts on nothing, and needs attention.

  chase_review: Chase a review left open for two days
    2d after each run of review starts: start chase.
    - The timer is set as each run of review starts, and ends when that run does: done, rejected or cancelled, a stop included. A failed run keeps it: a retry is the same run.
    - While it is set, the timer keeps the case open; a close cancels it.
    - Starting chase is a proposal, decided at once as a person's is: nothing starts, and the history says why, if it is already running, or it has run and isn't repeatable.
    - Only while the case decides: not once the case is closing.

Timeline
day 0 00:00
  the case opens
  opened by system:opener, with amount and order_id
  started review#1: waiting for approve or reject by support
  set chase_review: 2d after started review#1, due 2026-01-03T00:00:00Z
day 2 00:00
  chase_review#1 on 2d after started review#1: starting chase
    ↳ chase_review: Chase a review left open for two days
      2d after each run of review starts: start chase.
      - The timer is set as each run of review starts, and ends when that run does: done, rejected or cancelled, a stop included. A failed run keeps it: a retry is the same run.
      - While it is set, the timer keeps the case open; a close cancels it.
      - Starting chase is a proposal, decided at once as a person's is: nothing starts, and the history says why, if it is already running, or it has run and isn't repeatable.
      - Only while the case decides: not once the case is closing.
  started chase#1: waiting for chased by support-lead
day 2 09:00
  sam answers chase: chased
  sam answered chase#1 chased as support-lead
  chase#1 done
day 2 10:30
  ana answers review: approve, with approved_amount
  ana answered review#1 approve as support, setting approved_amount
  review#1 done
  scheduled pay#1: payments.refund@2 (order_id from system:opener; amount from person:ana), key story/pay#1
  pay#1 done, giving refund_id from untrusted:undeclared
  closed: nothing left to do

At the end, day 2 10:30
  status: closed
  nothing pending
```

Each firing is printed beside its rule's whole reading, fine print included. Timers set, fired
and cancelled, and refusals (`refused: review#1 is answered by support, and eve has no role`),
are the engine's own lines, so the output can't drift from what the engine does. At the end
comes every kind of pending work, or `nothing pending`. No line quotes a value from the case file:
the story's own lines name fields, never their values.

**A story is also a test.** Its `expect` holds the timeline, each time with its lines (without the
readings), and the lines at the end, exactly as printed: a firing nobody expected fails it.
`ventoux simulate` exits 0 when it holds (or the story expects nothing), 1 with the first
difference when it doesn't, and 2 when the story or its definition can't be read or can't run.
Every story under `examples/` runs as a test, among them a witness for each part of a reading's
fine print, in `examples/witnesses/stories/`.

## Patterns

A raw rule says everything: its moment, its condition, what it does. Some shapes come up again and
again, so a rule may be written as a **pattern** instead: a name for the shape, which expands into
raw rules when the definition is read (brief, D7, D46). The engine only ever runs raw rules, and
the expansion is shown wherever the rules are: in readings, in simulations, and in what the check
says. A pattern can do nothing raw rules can't.

A pattern is written in `rules`, beside raw rules: an entry with `on` is a raw rule, one with `sla`
or `reminder` a pattern. Its rules stand where it is written, which matters, since rules on one
moment act in the order written.

**An sla** acts when a run of a step isn't finished within an age of its start. The guide's chase
("Rules on time") is one:

```json
"chase_sla": {
  "display": {"title": "Chase a review not done within two days"},
  "sla": {"step": "review", "within": "2d"},
  "then": {"start": ["chase"]}
}
```

It expands into one raw rule, under its own name, so its firings are `chase_sla#1`:

```json
"chase_sla": {
  "display": {"title": "Chase a review not done within two days"},
  "on": {"after": "2d", "since": {"started": "review"}},
  "then": {"start": ["chase"]}
}
```

An sla holds no logic of its own. A timer set on a run's start already measures from the latest
start, ends with its run, fires once per run, and is kept by a failed run (brief, D44): what
D7 asked a pattern to encode. It takes any kind of step, an optional `when`, read when the timer
fires, and any `then`. It reads as its own sentence, then as the rule it expands into:

```
chase_sla: Chase a review not done within two days
  An sla on review: if a run of review isn't finished within 2d of its latest start, start chase.
  It expands to the rule chase_sla.
```

An sla always measures from each run's own start. A deadline that mustn't restart with the step
(30 days from the opening, say) is a raw timer on an instant, `opened` or a milestone, which lives
until it fires.

**A reminder** nudges while a task waits: after each age, from a run's start, it starts a step,
and does nothing else. A team lead reminds the reviewer a day and two days in:

```json
"remind_review": {
  "display": {"title": "Remind the reviewer of an open review"},
  "reminder": {"task": "review", "after": ["1d", "2d"], "start": "remind"}
}
```

```
remind_review: Remind the reviewer of an open review
  A reminder of review: while a run of review is open, start remind 1d and 2d after it starts.
  It expands to the rules remind_review_1d and remind_review_2d.
```

It expands into one timer per age, each named `<name>_<age>`: a name depends only on the
reminder and its age, so adding a rule elsewhere renames nothing in a case's history. The
reminder's task is a task, its step is repeatable (each reminder is its own run), and no two ages
are the same time; anything else is refused when the definition is read. An answered review ends
the reminders still to come. A reminder repeats only as often as its ages say: there is no
"every", which would be a timer that re-arms itself. Its step is the author's, so a reminder that
writes to someone drafts, as everything that talks to people does.

**What the check says of a pattern** is said at the pattern: an issue on an expanded rule points
to the entry it was written as, its moment at `sla` or `reminder.after`, a reminder's start at
`reminder.start`, and a reminder's message names its rule and the reminder:

```
rules.remind_review.reminder.start  NEVER_STARTS  remind_review_1d, from the reminder
remind_review: remind_review_1d can never start review: it fires on 1d after started review, while
review is running: start it on another moment
```

In a simulation, the rules are listed with each pattern's reading above its rules', and a firing
of an expanded rule shows its pattern's sentence, then the rule's whole reading:

```
  remind_review_2d#1 on 2d after started review#1: starting remind
    ↳ from the reminder remind_review: A reminder of review: while a run of review is open, start remind 1d, 2d and 4d after it starts.
    ↳ remind_review_2d: Remind the reviewer of an open review
      2d after each run of review starts: start remind.
```

Two approvers for one step (`four_eyes`) are not a rule pattern: no rule can add an approver. They
come with approvals by several people (11h2).

**Two traps the check still names.** A timer on a step's start is always that run's, but one can
still be timed from a first start by hand, through a milestone a rule reaches as the step starts
("2 days after the review began"). The milestone is reached once, so on a repeatable step the
timer counts from the first start, whatever later runs do. A warning says so:

```
rules.chase_review.on  TIMER_ON_FIRST_START (warning)  chase_review's timer is set when
review_begun is reached, which mark_begun reaches as a run of review starts: review is
repeatable, and a milestone is reached once, so the timer counts from the first such start,
whatever later runs do, and keeps the case open until it fires: to count from each run, set it
on {"started": "review"}, or write an sla
```

And a rule written after one on the same moment that always closes the case (no `when`, setting
nothing, reaching every `closes_when` milestone, on a moment no untrusted data steers) fires, and
is never applied: an error, since it holds in every case:

```
rules.say_goodbye.on  NEVER_FIRES  say_goodbye never acts: it fires on event cancelled after
withdraw, which always reaches withdrawn then, so it isn't applied: refund closes and nothing new
is decided: fire it on another moment
```

A timer set on that moment is never set, or is cancelled by the close, wherever it is written.
Each has its story under `examples/checks/stories/`.

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
keeps `pay`'s runs running until the script says `finish("pay#1")`. `later("2d")` moves time on: the
events after it happen two days later, and every timer due by then fires first, in order, even at
the end of the script. `run.timers` lists the timers still set.

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
| a proposed step's stale fact can't be fetched again | `approved_amount was obtained 3 days ago, and pay needs it at most 1 day old: it came from a person, so it can't be fetched again` |
| nobody proposes a step that starts by itself | `pay starts by itself: nobody proposes it` |
| nobody proposes a step only a rule starts | `lead_check is started only by a rule: nobody proposes it` |
| the step's latest run needs attention | `check_order#1 needs attention: retry it, or close the case` |
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
reports (`status`, `waiting_for`, `needs_attention`, `flags`, `history`, `timers`), and `waiting_at`, the
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
- **A timer is a workflow timer.** The case waits on one, for the soonest timer set; when it
  fires, the timer's firing is decided stamped with its due time, as in memory. A timer set is
  state, not running work: it doesn't hold back continue-as-new, crosses with its due time, and
  fires once in the new run, at once if its time came during the switch.
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

**What it can't see.** The check reads `requires`, `reaches`, who may propose or start a step and
how the case closes. It treats every `when` as possibly true, and every outcome as possible. So it
proves what can *never* happen, and says nothing about what depends on values:

| The check proves | It can't tell, since it depends on values or people |
|---|---|
| steps that wait on each other | a `when` that real data never makes true |
| a step requiring a milestone nothing reaches | a review answered `deny`, so `paid` is never reached: that is a path, not a deadlock |
| a step that waits for every milestone `closes_when` names, which the case closes on before the step could start: nothing new starts once they are reached, even while a failed step holds the close. It may require them, or steps that surely reach them, or come after such a step in `sequence`: `thank can never run: it runs only after draft, which reaches sent, …` | a rejected approval, or whether an operator retries a failed step; a step that only *may* reach a milestone (an activity that can end `declined`, a plan that can fail) |
| a case that closes the moment it opens | whether anyone eligible is there to answer or approve |
| a case nothing in its work or its close reasons can close (`NEVER_CLOSES`, below) | |

### What the check says about structure

| Code | Kind | What is wrong | Example message |
|---|---|---|---|
| `DEADLOCK` | error | steps wait on each other, so none of them can run | as above |
| `NEVER_RUNS` | error | a step's requirements can never all be met, or no person or rule may start it | `approve can never run: it requires reviewed, which no step or rule reaches: reach reviewed from a step or a rule, or remove the requirement` |
| `CLOSES_AT_OPENING` | error | no step starts by itself, or is started by a rule, when the case opens, so it closes at once and every proposal is refused | `nothing starts by itself when claim opens, so it closes at once and every proposal is refused: let a step start by itself with nothing required, start one from a rule on the opening, or add stays_open` |
| `NEVER_CLOSES` | error | nothing in the case's work or its close reasons can close it: it stays open, or, in every case, rules restart its steps in a loop nothing ends; no close reason names a registered role; and `closes_when` is empty or can never be met. If its definition allows forgetting and a role that forgets is registered, only a forget request would close it (the case data guide); otherwise nothing could | `claim stays open, none of its close reasons' roles (supprt) is registered, and closes_when never closes it, so nothing but a forget request could close it: name a registered role in a close reason` |
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
| `UNKNOWN_SYSTEM` | error | a reference names a system nobody registered | `order_id is a reference to ordrs, which is not a registered system: the systems are crm, documents, kyc, orders, policies, portal; use one of them, or ask the platform team to register it` |
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
| a rule's `set` | everything the rule read, its condition included ("Rules that update the case file") |

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

**What decides that a step runs counts too** (brief, D38, D39). A step's `when`, or the `when` of
the rule that starts it, decides whether its inputs are sent at all. If it reads untrusted data,
each input whose policy refuses that data is refused ("Rules", above). The check is separate: the
condition's sources are never added to the input's own, so a value written in the definition still
comes from nobody. Only the untrusted sources count, so a `when` reading a person's answer changes
nothing.

A plan step is followed into its plan: each of the plan's fields comes from what the case gives
it, and each activity in the plan is checked with that. Sending the estimate through
`refund-order@1` is refused in the same words, at the plan step's input, before the plan asks
anyone to approve a payment it could never make.

| Code | Kind | What is wrong | Example message |
|---|---|---|---|
| `REFERENCE` | error | an input that takes a reference to one system is given another system's reference, a text, or a computed value | `letters.draft@3 takes customer as a reference to crm, and is given order_id, a reference to orders: give it a reference to crm, read as it is` |
| `INPUT_POLICY` | error | an input is given a value from a source its policy refuses, or its step's `when` (or the `when` of a rule starting it) reads untrusted data its policy refuses, whoever opens the case | as above |
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
