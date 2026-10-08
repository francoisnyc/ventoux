# Layer 6: the Temporal adapter

Status: draft, for agreement in the session, 2026-10-08.

## What this layer is for

Layer 5 runs a plan in memory, asking for each activity and each answer through two functions it
is given (`call` and `wait`). Layer 6 hands it Temporal's: the same `interpret` runs inside a
Temporal **workflow**, activities run on a worker with the retry policy and timeouts their
contracts declare, answers arrive as **signals**, and a wait's timeout is a Temporal **timer**.

Temporal keeps a run alive across crashes by **replay**: a new worker runs the workflow code again
against the run's history, handing back each recorded result instead of acting again. That only
works if the code asks for the same things in the same order every time, which is why `core` reads
no clock, randomness or I/O. So this layer first makes that ban hold.

User-facing description, written first: `docs/guides/plans.md`, "Running a plan on Temporal".

Drawn on: the prototype's `src/temporal/workflow.ts` (the interpreter inside a workflow; signals
for answers), `activities.ts` (activities from the catalog), `worker.ts` and `client.ts`. Ours
differs: retry policy and timeouts come from each contract, not one default; a declared outcome is
never retried; the idempotency key names the run.

## Decided in the session

1. **First, close the side doors in the ban** (curriculum, layer 6 "First"). `tests/test_layers.py`
   reads only `import X` and calls to forbidden builtins by name, so today `import asyncio` (its
   event loop has a clock), `importlib.import_module("time")` and `__import__("random")` all pass.
   Added:
   - imports of `asyncio`, `importlib` and `builtins` are forbidden in `core` and `case`;
   - calls to the builtins `__import__`, `eval`, `exec` and `compile` are forbidden, by name, as
     `open` is: `re.compile(...)` is a method and stays allowed;
   - the name `__builtins__` may not appear at all (`__builtins__["open"]` reaches any builtin).

   Each with a negative test. This is a fence against mistakes in our own reviewed code, not an
   attacker: definitions are data and never run (non-negotiables). Temporal's workflow sandbox
   checks again at runtime, the same "check twice" idea as learning question 34.
2. **The idempotency key names the run:** `<workflow ID>/<run ID>/<state>#<n>`, so two runs never
   share one (brief, D17). The workflow ID alone isn't enough: it can be reused once a run closes,
   and a reset keeps it. The run ID comes from `workflow.info()`, recorded, so replay gives the
   same key; a reset gets a new one, so it re-runs a payment with a new key, which is why resets
   must be restricted (brief, D19). `interpret` takes the run's name as a parameter (`core` reads
   nothing from Temporal), with no default: a forgotten name would be the shared key D17 forbids.
   `run_plan` names its run `memory`.
3. **The bound of 1,000 states without a wait stays a count** inside `interpret`, unchanged. On
   replay the same code counts the same states from the same history, so it stops at the same
   place; it never reads `workflow.now()` or the history's length. Measured on the test server:
   1,000 activities make 6,003 history events, under Temporal's warning (about 10,000) and far
   under its limit (51,200).
4. **No continue-as-new in this layer.** The curriculum's Build line doesn't name it, and the bound
   keeps a run far below the limits. A loop through a wait is unbounded, but every pass needs a
   person's answer. Deciding what a new run carries (fields, entry counts, history, answers sent
   during the switch) belongs with the case's state, in layer 8: design question 18 in the brief.
5. **The dependency:** the Temporal Python SDK, `temporalio` (agreed). Its test server runs here
   (checked: it starts in under a second and skips a 48-hour timer at once). Tests keep using
   `asyncio.run`, as layer 5's do; no `pytest-asyncio`.

## How it works

### The workflow

`PlanWorkflow` holds the code; a deployment subclasses it to name its catalog. Temporal's Python
SDK refuses a workflow class made inside a function, and wants `@workflow.run` on the class it
registers, so the subclass is three lines (shown in the guide). The development one, for tests,
sits next to the development catalog.

Its input, `PlanStart`, is the plan as stored data and the fields, each value with its sources.
Inside, it parses the plan (`parse_plan`, as `run_plan` does) and calls `interpret` with:

- **`call`**: `workflow.execute_activity(reference, inputs, …)` with the contract's timeouts
  (`start_to_close`, `schedule_to_start`) and retry policy (`maximum_attempts`,
  `initial_interval`, `backoff_coefficient`). A declared outcome comes back as a non-retryable
  error of type `Outcome` and is raised again as `Outcome(name)`, so the interpreter reads it as
  in memory. Any other failure, after the retries, reaches the interpreter as an exception: the
  step stops (brief, D17).
- **`wait`**: answers arrive by the signal `answer(state, outcome, by)` and are kept in the order
  they came. A wait takes the first answer sent to its state, as the in-memory script does; it
  waits with `workflow.wait_condition`, and with the wait's timeout (`48h`) as a timer when it has
  one, giving `Answer("timeout", None)` when it fires. The interpreter's checks on answers are
  unchanged: who may answer is layer 7's.
- **the run's name**: `<workflow ID>/<run ID>`, from `workflow.info()`.

It returns a `RunReport`: the status, the reason and the history, one line per event (`str` of
each). The query `report` gives the same while it runs, with the status `waiting` while it waits;
in memory the script running out says that, on Temporal nothing does, since a wait just waits.

`ventoux.core` and Pydantic are passed through the workflow sandbox (imported once, not per run):
they are deterministic, and the boundary test is what holds `core` to that.

### Activities

`plan_activities(catalog, implementations)` turns each implementation into a Temporal activity
named by its contract's reference (`payments.refund@2`), the name deployment bindings use (brief,
D5). It refuses an implementation for a reference the catalog doesn't hold, so a typo can't
register an activity no plan can call. Implementations keep layer 5's shape (inputs in, output
out, `Outcome(name)` raised for a declared outcome). The key the engine filled reaches the
implementation unchanged on every attempt; it is never the attempt number (brief, D17).

### Exact numbers across Temporal

Temporal's default converter can't write a `Decimal` at all, and Pydantic's writes it as the text
`"0.1"`, which would come back a string and stop the guide's `amount > 100` as a text compared with
a number. So `ventoux.temporal` has its own data converter: JSON whose numbers are written exactly
and read back as `Decimal` (brief, D20), the same rule as `load_definition`. A binary `float` is
refused when written: it may already have lost its exact value, so it never enters a run.

### Worker and client

- `plan_worker(client, task_queue, workflow, implementations)`: a worker for the workflow and its
  activities, with the converter.
- `start_plan(client, workflow, plan, fields, id, task_queue)`, `answer(run, state, outcome, by)`,
  `report(run)`: start a run, answer a wait, read how it is going.

## Not in this layer

- Continue-as-new (design question 18, layer 8).
- Who may answer or approve, and answers sent by people with roles (layer 7, brief D19).
- Cases as workflows, child workflows and `workflow` steps (layer 8).
- The payload codec and key provider for sensitive fields (layer 9).
- Replay tests over recorded production histories in CI (brief, D17): this layer proves replay
  works and fails on changed code; collecting histories comes with releases (layer 12).

## Files

- `tests/test_layers.py`: the side doors.
- `src/ventoux/core/interpreter.py`: `interpret` takes the run's name; the key names it.
- `src/ventoux/testing.py`: `run_plan` names its run `memory`; the development workflow.
- `src/ventoux/temporal/workflow.py`: `PlanWorkflow`, `PlanStart`, `RunReport`.
- `src/ventoux/temporal/activities.py`: `plan_activities`.
- `src/ventoux/temporal/converter.py`: the exact-number data converter.
- `src/ventoux/temporal/worker.py`, `client.py`.
- Tests: `tests/test_layers.py`, `tests/test_interpreter.py` (the key), `tests/test_temporal.py`.

## Seams the tests use

- `forbidden_imports(layer, source)`, `forbidden_calls(source)` and a new
  `forbidden_names(source)` (the boundary test's own seams, as before).
- `run_plan` (the key in memory).
- `plan_worker`, `start_plan`, `answer`, `report` and the run's `result()`, against Temporal's
  time-skipping test server; `RunReport.status`, `.reason`, `.history`.
- Temporal's `Replayer`, on a history fetched from a finished run, for replay.
- The guide's examples: its run on Temporal gives the same history as in memory.

## Slices, in order

0. **The side doors.** Negative, each: `import asyncio`, `import importlib`,
   `from importlib import import_module`, `import builtins`, `__import__("random")`,
   `eval("1")`, `exec("x = 1")`, `compile("1", "", "eval")`, `__builtins__["open"]` are reported.
   Then `re.compile(...)` is not, and the real source tree reports nothing.
1. **The key names the run.** Negative: two runs of the same plan never share a key (in memory,
   two names). Then `memory/pay#1`, `memory/pay#2`; layer 5's key tests updated.
2. **Exact numbers across Temporal.** Negative: a float is refused by the converter; then a
   `Decimal("0.1")` written and read back is `Decimal("0.1")`, never text or a float.
3. **A plan runs as a workflow.** Negative: a run with a field missing is refused to start, as in
   memory; the injection plan stops before `letters.draft@2` is called. Then a final-state plan
   ends `succeeded`, and the guide's plan with an answer gives the guide's history, line for line.
4. **Activities from the catalog.** Negative: an implementation for a reference the catalog
   doesn't hold is refused; a declared outcome (`declined`) is not retried and moves the plan on;
   an activity failing past `maximum_attempts` stops the step. Then **a retried activity reuses
   the same idempotency key** (the curriculum's negative test): it fails once, succeeds on the
   second attempt, and both attempts saw `refund-1/<run ID>/pay#1`.
5. **Waits.** Negative: an answer the wait doesn't offer is refused and the wait goes on; a run
   with no answer reports `waiting`. Then the 48-hour timeout fires on the time-skipping server
   and moves on by `timeout`.
6. **Replay** (the curriculum's other negative test). Negative: a finished run's history,
   replayed against workflow code changed to ask for something else first, fails with a
   non-determinism error. Then the same history replayed with the real code passes.
7. **The bound on Temporal.** Negative: the looping plan stops after 1,000 states, as in memory,
   and its history replays. (About 8 seconds; the slowest test.)

## Promises

To be filled in against the tests before the pull request. Each claim above, and the test that
fails if it isn't true:

| Promise | Test |
|---|---|
| `core` and `case` may not import `asyncio`, `importlib` or `builtins`, call `__import__`, `eval`, `exec` or `compile`, or name `__builtins__` | |
| `re.compile` and other methods named like a builtin stay allowed | |
| Two runs never share an idempotency key; the key names the run, the state and its entry | |
| A retried activity reuses the same key; the key is never the attempt number | |
| Numbers cross Temporal as exact decimals; a float is refused | |
| On Temporal a run makes the same decisions and history as in memory, the runtime input check included | |
| A run refuses to start on Temporal as in memory | |
| An activity is retried with its contract's policy; a declared outcome is never retried | |
| An implementation for a reference the catalog doesn't hold is refused | |
| An answer a wait doesn't offer is refused, and the wait goes on; a waiting run reports `waiting` | |
| A wait's timeout is a timer, and moves on by `timeout` | |
| A history replays with the same code, and fails replay with code changed to ask for something else | |
| The bound of 1,000 states holds on Temporal, as a count | |
