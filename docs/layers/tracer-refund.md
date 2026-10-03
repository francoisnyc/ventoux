# Tracer bullet: the quickstart's refund case, end to end

Status: draft, for agreement.

## What this is for

A thin path through the whole system, built first and deepened later. The refund case from
`docs/QUICKSTART.md` runs from opening to closing, in memory and deliberately crude, so we see what
every later layer is for and test the quickstart's design against real code now rather than at
layer 8. Every crude part carries a `# TRACER:` comment naming the layer that replaces it, and
nothing is built on it.

## The definition

`examples/refund/refund.json`, written by hand in the shape `ventoux check` would produce (the
builder comes at layer 14):

```json
{
  "case": "refund",
  "title": "Customer refund",
  "fields": {
    "order_id": {"type": "reference", "system": "orders", "title": "Order"},
    "amount": {"type": "number", "title": "Amount requested"},
    "approved_amount": {"type": "number", "title": "Amount approved"}
  },
  "steps": {
    "review": {
      "kind": "task",
      "title": "Review the refund request",
      "roles": ["support"],
      "outcomes": {
        "approve": {"title": "Approve the refund", "sets": ["approved_amount"]},
        "reject": {"title": "Reject the refund"}
      }
    },
    "pay": {
      "kind": "activity",
      "title": "Refund the customer",
      "activity": "payments.refund@1",
      "inputs": {"order_id": {"field": "order_id"}, "amount": {"field": "approved_amount"}},
      "when": {"=": [{"field": "review.outcome"}, "approve"]},
      "approval": {
        "when": {">": [{"field": "approved_amount"}, 100]},
        "roles": ["support-lead"],
        "reason": "Refunds over 100 need a team lead"
      }
    }
  },
  "sequence": ["review", "pay"]
}
```

Conditions use a minimal structured form (`=`, `>`, `and`, `field`, literals), which commits to
neither JSONata nor structured JSON (design question 11). It is evaluated by a few lines of plain
code, never `eval`.

## How it runs

`run_case` walks the `sequence` in order:

- **A task** takes the next scripted answer for it. The answer is refused if its outcome isn't
  declared or the person lacks one of the task's roles. Its form may set only the fields the
  outcome declares, and each field remembers who set it. With no answer left, the case waits
  ("review by support").
- **An activity** runs only if its `when` holds; otherwise it is not needed. If its approval's
  `when` holds, it needs an approval answer from someone with the approval's roles who is not
  excluded: the people who set the fields it uses, and who answered the steps its `when` reads.
  With no approval answer, the case waits ("approval of pay by support-lead"). Then it calls the
  activity through a fake registry.
- **The case closes** when nothing is left to do: no step waiting.

People and roles are a fixed directory: `ana` (support), `sam` (support, support-lead) (design
question 12). An approval is answered by naming its step: `("pay", "approve", "sam")` (design
question 13).

## Files

- `src/ventoux/case/runner.py`: the loop, conditions, refusals. Pure (no I/O), so it passes layer
  0's boundary test.
- `src/ventoux/testing.py`: `load_definition`, `run_case`, the fake `payments.refund@1` and the
  people directory. Reading the JSON file is I/O, so it lives here, not in `case`.
- `examples/refund/refund.json` and `tests/test_quickstart.py`.

## Seams the tests use

- `load_definition(path)` returns the definition.
- `run_case(definition, file=…, answers=[(step, outcome, person, form?), …])` returns a run with
  `closed`, `reached(step)` and `waiting_for`.
- A refused answer raises `AnswerRefused`, with the reason in its message.

## Slices, in order

1. Negative: an answer with an outcome the task doesn't declare (`"aprove"`) is refused.
2. The quickstart's three tests, kept for good as acceptance tests: small refund paid, large refund
   waiting for a team lead, rejected review closes without paying.
3. Negative: Ana can't approve the payment of a refund she reviewed; Sam can, and it is paid.
4. Every `# TRACER:` comment names its layer (registry 1, expressions 2, validation 3,
   provenance 4, interpreter 5, Temporal 6, approvals and roles 7, case runtime 8).

## Done when

The tests pass, every `# TRACER:` comment names its layer, and anything the quickstart got wrong
or left unsaid is a design question in `docs/BRIEF.md` (11–13 so far).
