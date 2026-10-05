# Plans: several calls and waits as one step

> **For workflow developers.** Plans are an advanced concept (brief, D13): most cases need only
> tasks and activities. This guide describes layer 3 as if it already worked; the code that makes it
> true is built test-first in that layer. It covers what `ventoux check` proves about a plan before
> it runs. Running a plan comes at layer 5.

**The rule of thumb:** use a plan when several calls and waits belong together as one step *and*
must be data, because an AI drafts it or because the approval sheet must say what it will never
do. When the business wants to see and change each part, use separate case steps instead.

## A plan, read aloud

A plan is a state machine written as data. Each state calls one activity, waits for an answer, or
ends. Its `on` says where to go next, by what happened: "on *this*, go *there*".

```json
{
  "plan": "refund-order",
  "version": 1,
  "display": {"title": "Refund an order"},
  "fields": {"order_id": {"type": "reference", "system": "orders"}, "amount": {"type": "number"}},
  "initial": "check_order",
  "states": {
    "check_order": {
      "activity": "orders.lookup@1",
      "inputs": {"order_id": {"var": "order_id"}},
      "on": {"done": "approve_refund", "not_found": "failed"}
    },
    "approve_refund": {
      "wait": {"outcomes": ["approve", "reject"], "timeout": "48h"},
      "on": {"approve": "pay", "reject": "failed", "timeout": "failed"}
    },
    "pay": {
      "activity": "payments.refund@1",
      "inputs": {"order_id": {"var": "order_id"}, "amount": {"var": "amount"}},
      "on": {"done": "paid", "declined": "failed"}
    },
    "paid": {"final": "succeeded"},
    "failed": {"final": "failed"}
  }
}
```

Read aloud: look the order up; if it isn't found, fail. Otherwise wait up to 48 hours for an
approval; on *approve*, refund the customer; on *reject* or after 48 hours, fail. A refund ends
paid, or failed if the provider declines it.

An event in `on` maps to a state name, or to a list of transitions tried in order, each with an
optional condition: `"done": [{"when": …, "target": "approve_refund"}, {"target": "pay"}]` reads
"on done, if the condition holds go to `approve_refund`, otherwise go to `pay`".

## Approvals

An **approval** is a wait whose outcomes are `approve` and `reject` (brief, D11). The outcome name
`approve` is reserved for approvals: a wait that offers it must offer exactly those two, so for
any other question use another word (`accept`, `confirm`). Only the `approve` transition counts as
approving.

Two rules hold for every high-risk activity in a plan:

- **Every path to it passes an approval.** A condition is a fork the check can't see through: it
  assumes either branch can run. To approve only large refunds, a plan can't skip the approval for
  small ones; that is a case's choice (its step's `approval.when`), not a plan's.
- **One approval unlocks one run.** After a high-risk activity, reaching another one, or the same
  one again in a loop, needs a new approval.

Roles on an approval come with people in the loop (layer 7).

## What `ventoux check` proves

`ventoux check` reads the plan as a graph and lists every problem at once, each with its path in
the plan, a code and a message saying what is wrong, then what to do. Nothing runs.

Here is the plan above with the approval skipped for small refunds:

```json
"check_order": {
  "activity": "orders.lookup@1",
  "inputs": {"order_id": {"var": "order_id"}},
  "on": {
    "done": [
      {"when": {">": [{"var": "amount"}, 100]}, "target": "approve_refund"},
      {"target": "pay"}
    ],
    "not_found": "failed"
  }
}
```

The condition reads `amount > 100`. The check says:

```
states.pay  APPROVAL_REQUIRED  payments.refund@1 is high risk, and check_order → pay reaches it
without an approval: route every path to pay through an approval
```

Every problem it finds:

| Code | What is wrong | Example message |
|---|---|---|
| `UNKNOWN_TARGET` | `initial` or a transition names no state | `"pai" is not a state: the states are approve_refund, check_order, failed, paid, pay` |
| `UNKNOWN_ACTIVITY` | the activity isn't in the catalog | `payments.refund@3 is not in the catalog. Registered: payments.refund@1. Use a registered version, or register this one first.` |
| `UNKNOWN_INPUT` | an input the contract doesn't take | `payments.refund@1 has no input amout: its inputs are amount, order_id` |
| `MISSING_INPUT` | an input the contract needs is missing | `payments.refund@1 needs the input amount: add it to inputs` |
| `ENGINE_INPUT` | the plan sets the idempotency key | `idempotency_key is filled by the engine, never by a plan: remove it` |
| `UNKNOWN_EVENT` | `on` handles an event the state never gives | `payments.refund@1 never gives cancelled: its events are done, declined` |
| `MISSING_EVENT` | an event the state can give isn't handled | `declined is not handled: say where the plan goes on declined` |
| `RESERVED_OUTCOME` | a wait offers `timeout` as an outcome | `timeout is the event of a wait's timeout, not an outcome: name the outcome differently` |
| `APPROVAL_OUTCOMES` | a wait offers `approve` and other outcomes | `a wait offering approve is an approval, and offers exactly approve and reject; this one offers approve, edit: use another word than approve` |
| `EXPRESSION_INVALID` | an input or a condition fails the expression check | `amout is not a declared field` |
| `UNREACHABLE_STATE` | no path from `initial` reaches the state | `no path from check_order reaches refund_fee: remove it, or add a transition to it` |
| `NO_PATH_TO_FINAL` | the plan can never end from the state | `the plan can never end from retry_payment: add a path to a final state` |
| `APPROVAL_REQUIRED` | a high-risk activity can run without an approval | as above |
| `APPROVAL_REUSED` | one approval would unlock two high-risk runs | `one approval would unlock two high-risk runs: after pay, refund_fee can run without a new approval: add an approval before refund_fee` |

A wait handles a `timeout` event exactly when it declares a `timeout`; without one, `timeout` is an
unknown event.

What the check doesn't prove yet: that an input's type matches the contract's (checked when the
step runs, layer 5), where values come from and where they may go (layer 4), and who may approve
(layer 7).
