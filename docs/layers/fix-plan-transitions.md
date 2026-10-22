# Fix: a plan's path is never chosen by untrusted data

A fix, not a layer: no warm-up. Found at the checkpoint before layer 12
(`docs/layers/checkpoint-doors.md`, row 31, choice 4); on `main` since plan steps (layer 8c).
Recorded as D49 (brief), with dated amendment lines on D39 and design question 17, whose text is
kept.

## The bug

D38 says untrusted data informs and never decides. D39 and D43 check it through a case's steps,
and left a plan's own transitions open (design question 17). A plan branches on its fields:

```json
"check_order": {"activity": "orders.lookup@1", "inputs": {"order_id": {"var": "order_id"}},
                "on": {"done": [{"target": "paid", "when": {"==": [{"var": "note"}, "go"]}},
                                {"target": "failed"}],
                       "not_found": "failed"}}
```

Given the case's `note`, declared `untrusted:customer`, the plan step reached its milestone, the
case's `closes_when`, on `"go"`, and gave `failed` on anything else. The customer's text closed the
case; `validate_case` said nothing.

## Decided

Agreed with the user, 2026-10-22: option (b) of the two put at the checkpoint, refusing now;
option (a), D43's way inside a plan, recorded as the planned loosening.

1. **The runtime refuses.** When a run tries a transition whose `when` reads a field holding a
   source the engine doesn't trust (`untrusted:`, or one it doesn't recognise), it stops before
   reading the condition, whatever it would give, naming the field and its sources, never the
   value: `on done, the transition to paid reads note (untrusted:customer), and untrusted data
   can't choose a plan's path`. A plan step then fails and needs attention (D17, D28). A transition
   never tried (an earlier one held) reads nothing, and refuses nothing.
2. **Plan validation refuses** a transition reading a field the plan declares untrusted:
   `UNTRUSTED_TRANSITION` at `states.<state>.on.<event>[<n>].when`.
3. **Case validation refuses** a plan step's input feeding a field a transition reads, when the
   input is untrusted whoever writes it: `UNTRUSTED_TRIGGER` at `steps.<step>.inputs.<field>`;
   where only some writers make it so, `WRITER_DECIDES` (a warning, D42). A field the plan itself
   declares untrusted is plan validation's to say (one cause, one issue).
4. **What it blocks:** a plan can't branch on untrusted data at all, a model's classification
   included, until (a) is built. Branching on it is done in the case (D39, D43).
5. **Cases already open** on such a plan replay differently: carried to layer 12.

## Seams the tests use

- `run_plan(plan, fields, answers)`: `status`, `reason`, history.
- `run_case(...)`: `history`, `needs_attention`, `closed`.
- `validate(parse_plan(p), CATALOG)` and `validate_case(parse_case(d), CATALOG, plans)`: issues.

## Promises

Every test is in `tests/test_plan_transitions.py`.

| Promise | Test that would fail |
|---|---|
| A transition reading an untrusted value stops the plan, before reading it, naming the field and source and never the value | `test_a_transition_reading_untrusted_data_stops_the_plan` |
| A source the engine doesn't recognise counts as untrusted | `test_an_unrecognised_source_stops_the_plan_too` |
| A transition never tried refuses nothing; trusted transitions still choose | `test_a_transition_never_tried_refuses_nothing` |
| In a case, the plan step needs attention and reaches nothing, whatever the note says | `test_a_plan_step_branching_on_untrusted_data_needs_attention` |
| Plan validation refuses a transition reading a field the plan declares untrusted | `test_plan_validation_refuses_a_transition_on_an_untrusted_field` |
| Case validation refuses a plan step's untrusted input feeding a transition, and warns where only some writers make it so | `test_case_validation_refuses_an_untrusted_input_a_transition_reads`, `test_case_validation_warns_when_only_some_writers_make_it_untrusted` |
| Case validation says nothing of a trusted input a transition reads | `test_case_validation_says_nothing_of_a_trusted_input_a_transition_reads` |
