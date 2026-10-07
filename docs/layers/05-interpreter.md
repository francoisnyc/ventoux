# Layer 5: the deterministic interpreter, in memory

Status: design agreed in the session, 2026-10-07; not built yet.

## What this layer is for

Layers 2 to 4 made a plan data and proved things about it by reading it. Layer 5 runs it. The
**interpreter** enters a state and does what it says (call an activity, wait for an answer, or
end), then follows `on` to the next state. It writes down what happened as a **history** of
events.

It never acts on the world itself: it asks for each activity and each answer through two
functions it is given, and reads no clock and no randomness. Run again with the same answers, it
makes the same decisions, which is what Temporal's replay needs (layer 6).

And it checks every activity's inputs **again, with the real sources of each value**, before the
activity is scheduled. Layer 4's static check trusts a plan field with no declared source (the
case vouches for it); this check is the one that doesn't take the case's word for it (brief, idea
3 and D12).

User-facing description, written first: `docs/guides/plans.md`, "Running a plan".

Drawn on: the prototype's `src/core/interpreter.ts` (the loop over states; activities and waits
through injected functions; history events; the input check before scheduling; a "skip static
validation" option) and `docs/design.md` §4. Ours differs where the prototype failed open:

- its runtime check read each parameter's *declared* tags, and a parameter with none got empty
  tags, which read as trusted: the hole layer 4's review found;
- a condition was read as truthy (`Boolean(…)`), so a number or a text could take a transition;
- skipping the static check was an option on `run`, which "callers must never set".

## Decided in the session

1. **The loop asks for side effects through two functions it is given:** `async def
   interpret(plan, fields, catalog, call, wait)`. That is the shape a Temporal workflow already
   has, so layer 6 passes Temporal's functions in. Tests use a small in-memory driver,
   `run_plan`, with fake activities and scripted answers (`asyncio.run`, no new dependency).
2. **The interpreter never runs `validate`, and has no option to skip it.** Validating is
   `ventoux check`'s job, before a release. The runtime check depends on nothing the static check
   did, so "with the static check skipped" in a test means only that the test doesn't call
   `validate`. `run_plan` parses the plan (`parse_plan`: its shape), which is not validating it.
3. **Every field is given with its real sources** (`sourced(value, *sources)`), and the run
   refuses to start, failing closed, when:
   - a declared field is missing, or a field isn't declared;
   - a field comes with no sources (no sources reads as "written in the plan", which policies
     trust);
   - a source is `case`: the static check's stand-in for "the case vouches for it", never a real
     origin (today `is_trusted("case")` is true, so at runtime it would pass `trusted_only`).

   A field the plan declares `untrusted:<label>` keeps that source added to the given ones: a mark
   can add distrust, never remove it (non-negotiables: stricter downstream, never looser).
4. **The idempotency key is filled now,** from the step's run: `<state>#<n>`, `n` being how many
   times the run has entered that state (`pay#1`, `pay#2`). The input check needs it (the
   contract's input schema requires it), and the history already counts entries. Layer 6 adds
   the workflow's ID, so two runs never share a key (brief, D17).

## How a run goes

A run starts from `initial`, with the given fields. A plan binds no new values, so the fields and
their sources are the same in every state.

- **Activity state.** Look up the contract (not in the catalog: stop). Evaluate each input, and
  the engine's idempotency key. Then **the check before an activity**, in this order:
  1. every input policy on every input, against the sources of the fields its expression reads
     (`provenance`, layer 4), with the real sources;
  2. the inputs against the contract's input schema.

  Any refusal stops the step before anything is scheduled. Otherwise `call(reference, inputs)`:
  an output that fits the contract's output schema gives the event `done`; raising `Outcome(name)`
  for one of the contract's outcomes gives that event. Any other exception, an undeclared
  outcome, or an output that doesn't fit stops the step. Retries are Temporal's (layer 6): in
  memory an activity is called once.
- **Wait state.** `wait(state, outcomes, timeout)` returns an answer, or `None` when nothing more
  will come (the run is `waiting`). An answer is an outcome and the person who gave it; `timeout`
  comes with no person, and only from a wait that declares one. Any other answer is refused,
  recorded, and the wait goes on. Who may answer is layer 7's.
- **Final state.** The run ends `succeeded` or `failed`, as the state says.
- **Choosing the next state.** `on[event]`'s transitions are tried in order; the first with no
  `when`, or whose `when` is `true`, is taken. Fail closed: a `when` that raises, or gives
  anything but a boolean, stops the step, and the next transition is never tried; so do an event
  `on` doesn't handle, no transition holding, and a target that isn't a state.

### How a run ends

| Status | What happened |
|---|---|
| `succeeded` | a final state `succeeded` |
| `failed` | a final state `failed`: the plan said how it fails |
| `waiting` | an answer hasn't come |
| `stopped` | the step needs attention; nothing after it runs; `run.reason` says why (brief, D17) |

`stopped` is never `failed`: a plan that fails took a path its author wrote; a stopped one was
refused by the engine, and a person decides what happens next (nothing is skipped
automatically).

### The history

Plain frozen dataclasses, appended as the run goes; each reads as one line (`str(event)`), which
the guide shows and the tests compare:

| Event | Line |
|---|---|
| `Started` | `started refund-order@1` |
| `Entered` | `entered pay` |
| `Scheduled` | `scheduled payments.refund@2 (order_id from system:orders; amount from system:opener)` |
| `Gave` | `payments.refund@2 gave done` |
| `Waiting` | `waiting for approve or reject, at most 48h` |
| `Answered` | `sam answered approve` |
| `Refused` | `refused ana's answer edit: approve_refund offers approve or reject` |
| `Moved` | `moved on done to approve_refund` |
| `Stopped` | `stopped at draft: …: the step needs attention, and nothing after it runs` |
| `Ended` | `ended succeeded` |

`Scheduled` keeps the inputs (the key included) and each input's sources; `Gave` keeps the
output. No event has a time: there is no clock to read. Temporal's own history adds them.

### The refusal sentence

The runtime refusal reads like `INPUT_POLICY`'s: `<ref> takes <input> <describe()>, and this value
comes from <field> (<sources>)`, then what to do: `the step needs attention, and nothing after it
runs`. One function writes the shared part for both.

## The tracer runner

`case/runner.py`'s `# TRACER: inputs aren't checked against the contract's schema (the
interpreter, layer 5)` goes: the runner calls the same check before an activity, with the sources
it already keeps (layer 4), so the quickstart's `pay` step gets the runtime input-policy check and
the schema check too. A refusal raises (the runner has no history; it is replaced at layer 8).
Its idempotency key is `<step>#1` (each step runs once in the tracer); its `# TRACER` for the key
keeps naming layer 6. The quickstart's tests stay green.

## Not in this layer

- Who may answer or approve, and approvals lapsing when an input changes (layer 7).
- Retries, real timers, a bound on loops, continue-as-new (layer 6).
- Field values checked against their declared types at start (the case file is typed, layer 8; a
  wrong type is still caught, by the evaluator or by the input check).
- An activity's output reaching the case file (layer 8).
- An untrusted value steering a condition (design question 17).

## Files

- `src/ventoux/core/interpreter.py`: `interpret`, `PlanRun`, `Outcome`.
- `src/ventoux/core/history.py`: the events.
- `src/ventoux/core/before_activity.py`: the check before an activity, used by the interpreter and
  the tracer runner.
- `src/ventoux/core/provenance.py`: `Sourced` and `sourced`.
- `src/ventoux/testing.py`: `run_plan`, the in-memory driver.
- `src/ventoux/case/runner.py`: the check before an activity, replacing its layer 5 `TRACER`.
- Tests: `tests/test_interpreter.py`, and new tests in `tests/test_quickstart.py`.

## Seams the tests use

- `run_plan(data, fields, answers, activities=…)` → `PlanRun` with `status`, `reason` and
  `history` (each event read with `str`).
- `sourced(value, *sources)`; `Outcome(name)`, raised by a fake activity.
- `run_case` (the quickstart's tests).
- The plans guide's examples: its plan, its run, its history and its two `stopped` messages.

`interpret` itself is the seam layer 6 uses; tests reach it through `run_plan`.

## Slices, in order

1. **Starting a run.** Negative: a field with no sources, a source `case`, a missing field and an
   undeclared one are each refused. Then a plan whose `initial` is a final state ends `succeeded`.
2. **Activities.** Negative: an activity not in the catalog, a target that isn't a state, an
   activity raising, an undeclared outcome and an output that doesn't fit each stop the run.
   Then `done` and a declared outcome each move on.
3. **The check before an activity (the curriculum's first negative test).** Negative: the
   injection plan with `suggested_recipient` unmarked, `validate` never called, and the value
   given as `untrusted:llm`: stopped, and the fake `letters.draft@2` is never called. Negative: a
   field the plan marks `untrusted:llm` and the case gives as `system:opener` is still refused.
   Negative: an input that doesn't fit the schema stops the run. Then trusted values pass, and the
   key is `draft#1`.
4. **Conditions (the curriculum's second negative test).** Negative: the guide's fork with
   `amount` given as `"250"` stops at `check_order`, and `pay` is never called. Negative: a `when`
   giving a number, an unhandled event, no transition holding. Then transitions are tried in
   order.
5. **Waits.** Negative: an undeclared outcome, and `timeout` from a wait without one, are refused
   and the wait goes on; a script that runs out leaves the run `waiting`. Then the guide's run,
   its history line by line, and `pay#2` on a second pass through `pay`.
6. **The tracer runner.** Negative: a review whose `approved_amount` is a text is refused before
   the refund is called. The quickstart's tests stay green.
7. **The guide runs:** its run, its history and its two `stopped` messages.

## Promises

Each claim this note makes about behaviour, and the test that fails if it isn't true. `I` is
`tests/test_interpreter.py`, `Q` `tests/test_quickstart.py`. Test names are planned; the table is
checked against the code before the pull request.

| Promise | Test |
|---|---|
| A run refuses to start with a field missing, undeclared, with no sources, or from `case` | I `test_a_run_needs_every_field_with_its_sources`, `test_case_is_not_a_source_at_runtime` |
| The runtime check uses the real sources: an injection the static check passes is stopped before the activity is called | I `test_with_the_static_check_skipped_the_runtime_check_still_blocks_the_injection` |
| A field marked untrusted stays untrusted, whatever the case gives | I `test_a_mark_adds_distrust_never_removes_it` |
| Inputs that don't fit the contract stop the step before it is called | I `test_an_input_that_does_not_fit_the_contract_stops_the_step` |
| A condition that can't be evaluated, or isn't a boolean, stops the step; the next transition is never tried | I `test_a_condition_that_cannot_be_evaluated_stops_instead_of_skipping_the_approval`, `test_a_condition_must_give_a_boolean` |
| An unhandled event, no transition holding, an unknown target or activity stop the step | I `test_what_the_plan_does_not_say_stops_the_step` |
| An activity failing, an undeclared outcome, or an output that doesn't fit stops the step; a declared outcome moves on | I `test_an_activity_failure_stops_the_step`, `test_a_declared_outcome_moves_on` |
| An answer the wait doesn't offer, or a `timeout` it doesn't declare, is refused and the wait goes on | I `test_an_answer_the_wait_does_not_offer_is_refused` |
| A run with no answer left is `waiting`, not ended | I `test_a_run_without_its_answer_waits` |
| The key is the state and its entry count | I `test_the_key_is_the_state_and_its_run` |
| The same plan, fields and answers give the same history | I `test_a_run_is_the_same_every_time` |
| The guide's run, history and messages are what the code does | I `test_the_guides_run`, `test_the_guides_history`, `test_the_guides_stopped_messages` |
| The tracer runner checks inputs before an activity; the quickstart stays green | Q `test_an_input_that_does_not_fit_is_refused_before_the_refund`, the quickstart's tests |
