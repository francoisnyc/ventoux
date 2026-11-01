# Expressions: conditions and values in a definition

> **For workflow developers.** This guide describes layer 2, and dates from layer 16a, as if they
> already worked; the code that makes it true is built test-first in those layers. You will usually write expressions through the
> Python builder (`approved_amount > 100`, layer 14). This guide shows what is stored, how it reads
> back, and what is refused.

**The rule of thumb:** an expression is a small question about the case file: is the amount over
100, did the reviewer approve. It can compare, combine and count the values the case file
declares, and nothing else. It can't read the clock, call a system or run code. When the logic
you need doesn't fit, write it as an activity with `effect: compute` (see the activities guide).
That gives you real code, with tests and a review.

## What is stored, and how it reads

An expression is stored as JSON. It is either a literal (a number, a text, `true`/`false`, or a
date, `{"date": "2026-10-31"}`), a field (`{"var": "approved_amount"}`), or one operator with its arguments. Reviewers and diffs
show it on one line, in the style of FEEL, the expression language of DMN and Camunda 8: `==` reads
as `=`, and `!` as `not(...)`.

| Stored | Reads as |
|---|---|
| `{">": [{"var": "approved_amount"}, 100]}` | `approved_amount > 100` |
| `{"==": [{"var": "review.outcome"}, "approve"]}` | `review.outcome = "approve"` |
| `{"and": [{"==": [{"var": "review.outcome"}, "approve"]}, {">": [{"var": "approved_amount"}, 100]}]}` | `review.outcome = "approve" and approved_amount > 100` |
| `{"and": [{"or": [{"var": "urgent"}, {"var": "vip"}]}, {">": [{"var": "amount"}, 0]}]}` | `(urgent or vip) and amount > 0` |
| `{"!": [{"exists": "approved_amount"}]}` | `not(exists(approved_amount))` |
| `{"in": [{"var": "review.outcome"}, ["approve", "escalate"]]}` | `review.outcome in ["approve", "escalate"]` |
| `{"if": [{"==": [{"var": "review.outcome"}, "approve"]}, {"var": "approved_amount"}, 0]}` | `if review.outcome = "approve" then approved_amount else 0` |
| `{"cat": ["Refund of ", {"string": [{"var": "approved_amount"}]}]}` | `cat("Refund of ", string(approved_amount))` |
| `{"count": {"over": {"var": "items"}, "where": {"==": [{"item": "risk"}, "high"]}}}` | `count(items where item.risk = "high")` |
| `{"sum": {"over": {"var": "items"}, "where": {"==": [{"item": "risk"}, "high"]}, "value": {"item": "amount"}}}` | `sum(item.amount over items where item.risk = "high")` |
| `{">=": [{"var": "incident_date"}, {"var": "policy_start"}]}` | `incident_date >= policy_start` |
| `{"<": [{"var": "incident_date"}, {"date": "2026-01-01"}]}` | `incident_date < date("2026-01-01")` |

The one-line form is for reading only. Nothing parses it back: what is stored is the JSON.

## The operators

The list is fixed (decision D20 in the brief). Adding an operator is a design decision, not a code
change.

| Operator | Takes | Gives |
|---|---|---|
| `var` | a declared field's name | its value |
| `==`, `!=` | two values of the same type | boolean |
| `>`, `>=`, `<`, `<=` | two numbers, or two dates | boolean |
| `and`, `or` | two or more booleans | boolean |
| `!` | one boolean | boolean |
| `+`, `*` | two or more numbers | number |
| `-`, `/` | two numbers | number |
| `if` | a boolean, then two values of the same type | that type |
| `in` | a value, and a list of literal values of its type | boolean |
| `cat` | one or more texts (an outcome counts as one) | text |
| `string` | one number, boolean, reference or date | text (a date as `2026-10-31`) |
| `exists` | a declared field's name | boolean: whether it has a value |
| `count` | `over` a list field, optional `where` | number |
| `sum` | `over` a list field, optional `where`, a numeric `value` | number |
| `item` | a field of the current element, inside `count` and `sum` | its value |
| `date` | a calendar date, written `YYYY-MM-DD` | that date, as a literal |

If you know JsonLogic, most names are the same, and ours are stricter. Ours either gives the same
answer as JsonLogic or refuses. A field can't have a default, `if` takes exactly three arguments,
and nothing is "truthy": a condition must be `true` or `false`. `1 == "1"` is refused instead of
being `true`, and `cat` only joins texts (use `string` for a number). Where ours behaves
differently, the name is ours (`exists`, `count`, `sum`, `string`, `item`), so nobody expects
JsonLogic's behaviour from it.

## Types

Every field in the case file is declared with a type, and every expression is checked against
those types before the definition is accepted:

| Type | Example | Notes |
|---|---|---|
| `number` | `250`, `0.1` | one number type, exact decimal |
| `string` | `"Refund of "` | text |
| `boolean` | `true` | |
| outcome | `review.outcome` | a closed list of names (`approve`, `reject`) |
| `reference` | `order_id` (system `orders`) | only `==` and `!=` with a reference to the same system, and `string` |
| `date` | `incident_date`, `{"date": "2026-10-31"}` | a calendar date, no time and no time zone; compared with another date, and `string` |
| list | `items` | read only by `count` and `sum`; its elements have declared fields, read with `item` |

**Numbers are exact decimals.** `0.1 + 0.2 == 0.3` is `true`, so money adds up the way people
expect. A division that doesn't come out exactly (`1 / 3`) keeps 34 significant digits, rounding
half to even (IEEE 754 decimal128). Expressions don't round otherwise: rounding is a compute
activity, with the scale and rounding mode written out. A number must be finite: infinity and NaN
are refused, since an infinite amount would pass any threshold. It must also fit decimal128 (34
digits, exponents within ±6144), so every evaluator holds the same number.

**A date is a day on the calendar, not a moment.** `2026-10-31` is the same day wherever it is
read: it has no time and no time zone, so comparing two dates gives the same answer everywhere, and
on every replay. It is written in JSON as text, `"2026-10-31"`, because JSON has no date, and the
field's type is what makes it a date: in a case file it must be a real day (`2026-02-30` is
refused), and in an expression it is never a text (`incident_date == "2026-10-31"` is refused:
write `{"date": "2026-10-31"}`). The case-data guide says where a date may come from.

**No expression asks what day it is.** There is no `today`, as there is no `now`: a condition that
read the calendar would decide differently on replay (see "Why `now` can't be written" below). To
ask "was it reported within 30 days?", compare two dates the case file holds, such as
`incident_date` and `reported_on`, both recorded when they were given. To act when 30 days have
passed, use a timer (cases guide, "Rules on time"): the time reaches the case as an event its
history records.

## What is refused, and what it says

When the definition is checked, before anything runs:

| You wrote | Refused with |
|---|---|
| `{"now": []}` | `` `now` is not an operator. The operators are: var, ==, !=, >, >=, <, <=, and, or, !, +, -, *, /, if, in, cat, string, exists, count, sum, item, date. Logic that doesn't fit is a compute activity. `` |
| `{"today": []}` | `` `today` is not an operator. The operators are: var, ==, !=, >, >=, <, <=, and, or, !, +, -, *, /, if, in, cat, string, exists, count, sum, item, date. Logic that doesn't fit is a compute activity. `` |
| `{"==": [{"var": "review.outcome"}, "aprove"]}` | `` ==[1]: review.outcome has no outcome "aprove"; its outcomes are approve, reject `` |
| `{">": [{"var": "approved_amount"}, "100"]}` | `` >[1]: `>` compares two numbers or two dates, and this is a string `` |
| `{">": [{"var": "incident_date"}, 30]}` | `` >[1]: `>` compares two numbers or two dates, and this is a number, not a date `` |
| `{"==": [{"var": "incident_date"}, "2026-10-31"]}` | `` ==[1]: `==` compares values of the same type, and this is a string, not a date `` |
| `{"date": "2026-02-30"}` | `` date: "2026-02-30" is not a day on the calendar; write a date as YYYY-MM-DD, such as "2026-10-31" `` |
| `{">": [{"var": "aproved_amount"}, 100]}` | `` >[0]: aproved_amount is not a declared field `` |

**Why `now` can't be written.** A case runs as a Temporal workflow, which can be replayed later
from its history. Replay must make the same decisions it made the first time. An expression that
read the clock could be true when the workflow ran and false when it replays a week later, and the
replay would take a different branch. So the language has no clock, no randomness and no calls.
There is nothing to forbid, because none of it can be written. Time reaches a case as an event the
history records, such as a timer.

When the case runs, a value the check couldn't see is an error that stops the step:

| Situation | Error |
|---|---|
| `approved_amount` has no value yet | `approved_amount has no value` |
| `{"/": [{"var": "amount"}, {"var": "items"}]}`, with 250 and 0 | `division by zero in amount / items` |
| a result beyond what decimal128 can hold | `` `*` gives a number too large for an expression (decimal128) `` |
| an element of `items` lacks `risk`, in `count(items where item.risk == "high")` | `item.risk has no value (element 2 of items)` |
| `approved_amount > 100`, with a text in `approved_amount` | `` `>` compares two numbers or two dates, and it was given a string `` |
| `incident_date < date("2027-01-01")`, with a text in `incident_date` | `` `<` compares two numbers or two dates, and it was given a string `` |

**Why an error and not `false`.** Suppose an approval's condition is `approved_amount > 100` and
the amount is missing. Reading the condition as `false` would mean "no approval needed", and the
refund would be paid without one. In Ventoux an expression the engine can't evaluate always stops
the step, and a person looks at it. `and` and `or` also evaluate every part, so an error is never
hidden behind a part that already decided the answer. To handle a missing value on purpose, say
so: `if exists(approved_amount) then approved_amount else 0`. That works because `if` evaluates
only the branch its condition chooses: the condition is what says which branch means something.
A field holding JSON's `null` has no value, for `exists` and for `var` alike.

## In a plan

Plans are an advanced kind of step (see the brief, D13). Their inputs and conditions use the same
expressions:

```json
"pay": {
  "activity": "payments.refund@2",
  "inputs": {"order_id": {"var": "order_id"}, "amount": {"var": "amount"}},
  "on": {"done": "paid"}
}
```
