# The split of `case/runtime.py`: the list, to agree before anything moves

Not a layer and not a fix: no rule of the product changes (the maintainer's walkthrough,
2026-11-13). **This pull request holds only this list.** Nothing has moved. The list was agreed
in the review of #108 on 2026-11-14, with one change, the folder below. The move starts once the
lint bar (#107) is merged, since #107 touches `case/runtime.py`.

## Why

`src/ventoux/case/runtime.py` is 2,390 lines with 95 top-level names (93 functions and classes,
2 constants), where the convention is one idea per file. `answers.py`, `closing.py`,
`admission.py` and `timers.py` already hold their own part of the runtime; this does the same
for the rest.

## The rule of the move

A pure move. `case/runtime.py` becomes a folder, `case/runtime/` (the maintainer's choice, in
the review of #108), and each function goes to a file inside it, grouped by the kind of event
it handles. No function's body changes: only the file it is in, each file's imports, and a
docstring at the top of each new file.

## The folder

- **`case/runtime/__init__.py` holds imports only,** as `core/expressions` and
  `tooling/builder` do. It re-exports every name that is imported from
  `ventoux.case.runtime` from outside today: `decide`, `proposal_refused`, `preview_migration`,
  `CaseRefused`, `EventRefused`, `ShownRefused`. So `from ventoux.case.runtime import decide,
  CaseRefused` reads as it does now.
- **`case/runtime/deciding.py`** holds the five names that were to stay in `runtime.py`:
  `decide`, `decide_again`, `MigrationPreview`, `preview_migration` and `proposal_refused`
  (about 150 lines and their imports).
- **The twelve files below go inside the folder,** under these names. There the pairs can't be
  confused: `case/runtime/answering.py` is the runtime taking an answer, `case/answers.py` the
  rule for who may give one.
- **`case` stays at 58 entries.**

## What moves, and where

Thirteen files in `case/runtime/`: `deciding.py` above, and these twelve. "Lines" counts the
definitions alone, before imports and the file's docstring.

| New file | Its one idea | Names | Lines | What moves in |
|---|---|---|---|---|
| `receiving.py` | an event from outside reaches the case, or a record is shown | 7 | 129 | `EventRefused`, `ShownRefused`, `receive`, `arrive`, `sender_role`, `refuse_payload`, `record_shown` |
| `opening.py` | the case opens with its first values | 4 | 96 | `CaseRefused`, `open_case`, `refuse_to_open`, `refuse_unless_wrapped` |
| `answering.py` | a person answers a task or an approval, a claim names its entry, and an option's or attachment's check comes back | 19 | 356 | `answer`, `sent_never_answered`, `entry_to_hold`, `open_entry`, `has_been_open`, `answer_task`, `take_answer`, `as_worded`, `answer_approval`, `checked_set`, `asked_with`, `checked_by`, `check_of`, `vouched_for`, `not_taken`, `checked_answer`, `check_answered`, `check_back`, `check_failed` |
| `proposing.py` | a person proposes a step | 1 | 77 | `propose` |
| `completing.py` | what a run gives back: completed, failed, cancelled, a child's end | 7 | 169 | `complete`, `failed`, `plan_cancelled`, `workflow_cancelled`, `child_rang`, `child_not_ended`, `child_ended` |
| `retrying.py` | an operator retries a failed run | 3 | 113 | `retry`, `operating_role`, `reads_a_stale_fact` |
| `admitting.py` | after any event: every step that may start now is started, and what can't is said | 13 | 227 | `admit`, `nothing_on_its_way`, `let_go_while_held`, `retry_fails`, `free_to_start`, `start_from_rules`, `proposed_by_a_rule`, `taken_up`, `drop_waiting`, `left_unstarted`, `nothing_new`, `holding`, `held_close_refusal` |
| `refreshing.py` | a step needs a fact fresh, and it is fetched again | 5 | 145 | `StoppedRefresh`, `refresh_stale`, `refreshable`, `is_from_a_person`, `never_waits` |
| `starting.py` | one run starts: a task opens, an activity is scheduled, a plan or a child begins | 7 | 244 | `start`, `schedule`, `steering`, `required_steering`, `refuse_sensitive_inputs`, `start_plan`, `open_child` |
| `items.py` | a repeated step's runs, one per item of its list | 6 | 150 | `start_items`, `ran`, `item_of`, `numbered_items`, `with_item`, `start_item` |
| `outcomes.py` | whether what a run gave can be taken, and where it lands | 3 | 66 | `outcome_problem`, `plan_outcome_problem`, `write_outputs` |
| `runs.py` | what every file above shares: a step's coming run and entry, failing and flagging, small wording | 15 | 109 | `DONE`, `FAILED`, `coming_run`, `coming_entry`, `next_entry`, `listed`, `marked`, `flag`, `fail`, `stopped_because`, `proposal_spent`, `may_not_approve`, `origins`, `reach_unless_steered`, `flag_if_stopping` |

90 names go to these twelve files and 5 to `deciding.py`: 95 in all, each counted once
(checked by script against the file).

## The order the files import each other

Worked out from the call graph between the 95 names. Each file imports only files below it in
this list, so there is no import cycle and no import inside a function:

```
deciding     -> receiving, opening, answering, proposing, completing, retrying, admitting
completing   -> answering, starting, outcomes, runs
retrying     -> items, runs
proposing    -> admitting, refreshing, starting, runs
receiving    -> runs
answering    -> opening, outcomes, runs
opening      -> runs
admitting    -> refreshing, starting, items, runs
refreshing   -> starting, runs
starting     -> runs
items        -> runs
outcomes     -> runs
runs         -> (none of these)
```

## Three choices in the list, as agreed

1. **Names beside existing files: a folder instead.** As first proposed, `answering.py` would
   have sat beside `answers.py`, `admitting.py` beside `admission.py`, `refreshing.py` beside
   `freshness.py`: three pairs differing by an ending, in a folder going from 58 files to 70.
   The maintainer chose the folder, which keeps the names and removes the confusion.
2. **The checks of an option or attachment stay with the answers** (agreed). `answer_task`
   calls the checks, and a check coming back calls `take_answer`: in two files they would
   import each other. That is why `answering.py` is the largest (356 lines of definitions).
3. **`runs.py` is the shared floor** (agreed). Fifteen small names every other file uses. It
   is a grouping by "who needs it", not by event; the alternative, each helper beside its main
   caller, brings the cycles back.

## Who imports from `runtime` today, and what changes for them

Measured on `main` at `4ea3c5b`: 7 files in `src` and 24 in `tests` import from
`ventoux.case.runtime`. They import seven names:

| Name | Imported by | After the move |
|---|---|---|
| `decide` | 24 files | unchanged |
| `CaseRefused` | 6 | unchanged (re-exported) |
| `EventRefused` | 4 | unchanged (re-exported) |
| `proposal_refused` | 3 | unchanged |
| `ShownRefused` | 2 | unchanged (re-exported) |
| `preview_migration` | 2 | unchanged |
| `listed` | 2: `case/validate.py`, `case/warnings.py` | imported from `ventoux.case.runtime.runs` |

So two import lines change outside the moved code. Importing `ventoux.case.runtime.runs` loads
the package first, as importing `runtime` does today: nothing those two files load changes. No
name of `runtime.py` is in `src/ventoux/public.json`.

## Documents that name `case/runtime.py`

- Ten notes in `docs/layers` and two entries of `docs/LEARNING.md` say that a function is "in
  `case/runtime.py`". They stay as written (agreed): the notes are records of when they were
  written, and the learning log is the maintainer's. This note is the pointer to where each
  group went.

## The proof the move will carry

In this note, once the move is made:

- the suite's count unchanged, before and after;
- the recorded histories replay;
- a script showing each moved function's body is the same before and after (compared as
  parsed code, so a comment or a blank line that moved is seen too);
- `tests/test_layers.py` passes;
- the 8 `# noqa: C901` marks `runtime.py` holds after #107 travel with their functions:
  `ruff check` passing shows none was lost or left behind;
- `src/ventoux/public.json` unchanged;
- which files in `case` are still over 1,000 lines afterwards, and why. Today that would be
  `definition.py` alone (1,244 lines), which this doesn't touch.

## Not part of this

`temporal/cases.py`: `CaseWorkflow` waits until after the first release.
