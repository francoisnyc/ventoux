# The split of `case/runtime.py`: the list, to agree before anything moves

Not a layer and not a fix: no rule of the product changes (the maintainer's walkthrough,
2026-11-13). The list below was agreed in the review of #108 on 2026-11-14, with one change, the
folder. The move was made once the lint bar (#107) was merged, on `main` at `9aad27a`; its proof
is at the end.

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

Read from the files as moved. Each file imports only files below it in this list, so there is
no import cycle and no import inside a function:

```
deciding     -> receiving, opening, answering, proposing, completing, retrying, admitting
completing   -> answering, outcomes, runs
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

## The proof

All on this branch after the move, against `main` at `9aad27a` (which has #106 and #107).

**Every definition's text is the same.** The script below reads each top-level function, class
and constant of the old file and of the new ones, with the comment lines just above it, its
decorators, signature and body, and compares the text exactly:

```
$ git show 9aad27a:src/ventoux/case/runtime.py > before.py
$ python same_bodies.py before.py src/ventoux/case/runtime
before: 95 definitions; after: 95
missing: []; added: []; changed: []
```

Seen failing twice: with one space added inside `listed`'s docstring (`changed: ['listed']`),
and with the comment above `DONE` dropped (`changed: ['DONE']`). The script:

```python
"""Each top-level definition of the old `case/runtime.py` is in `case/runtime/`, once, with the
same text: the comment lines just above it, its decorators, signature and body. Usage:
    git show 9aad27a:src/ventoux/case/runtime.py > before.py
    python same_bodies.py before.py src/ventoux/case/runtime
"""

import ast
import sys
from pathlib import Path


def definitions(path: Path) -> dict[str, str]:
    """Each top-level function, class or constant's text, with its comment lines, by name."""
    text = path.read_text()
    lines = text.splitlines(keepends=True)
    found: dict[str, str] = {}
    for node in ast.parse(text).body:
        if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name):
            name = node.targets[0].id
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            name = node.name
        else:
            continue
        start = min([node.lineno, *(d.lineno for d in getattr(node, "decorator_list", []))]) - 1
        while start > 0 and lines[start - 1].startswith("#"):
            start -= 1  # the comment lines directly above it are its own
        found[name] = "".join(lines[start : node.end_lineno])
    return found


before = definitions(Path(sys.argv[1]))
after: dict[str, str] = {}
for file in sorted(Path(sys.argv[2]).glob("*.py")):
    if file.name == "__init__.py":
        continue  # imports and `__all__` only
    for name, text in definitions(file).items():
        assert name not in after, f"{name} is defined twice"
        after[name] = text
missing = sorted(set(before) - set(after))
added = sorted(set(after) - set(before))
changed = sorted(name for name in before if name in after and before[name] != after[name])
print(f"before: {len(before)} definitions; after: {len(after)}")
print(f"missing: {missing}; added: {added}; changed: {changed}")
sys.exit(1 if missing or added or changed else 0)
```

**What else changed, outside the moved text:**

- each new file's docstring, and its imports: the old file's whole import block was copied into
  each, with the sibling names it uses, and `ruff check --fix --select F401,I001` removed what
  each file doesn't use and sorted the rest;
- `__init__.py`: imports and `__all__` only;
- `case/validate.py` and `case/warnings.py`: `listed` from `ventoux.case.runtime.runs`.

One correction to the list: `completing.py` doesn't import `starting.py`. The call graph had
counted `steering`, the name of a variable in `complete`'s comprehension, as the function of that
name; the table above is now read from the files. The tutor's review found the same kind of
false edge (`failed`, in `held_close_refusal`).

**The checks:**

| Check | Result |
|---|---|
| the suite, on `main` at `9aad27a` | 4720 passed, 3 skipped |
| the suite, on this branch | 4720 passed, 3 skipped: the same |
| the recorded histories replay (`pytest -k "replay or histories or history"`) | 54 passed |
| `tests/test_layers.py` (`case` stays pure, walking the folder too) | 76 passed |
| `ruff check`, with the 8 `# noqa: C901` marks moved with their functions (none lost: a function over 10 without its mark fails; none left behind: an unused mark fails) | clean |
| `ruff format --check`, mypy strict | clean |
| `src/ventoux/public.json` | unchanged |

**Files in `case` still over 1,000 lines:** `definition.py` alone (1,244), which this doesn't
touch: it holds the definition's schema, one Pydantic model per part of a case, and its checks.
The largest file in `case/runtime/` is `answering.py`, 462 lines with its imports.

## Not part of this

`temporal/cases.py`: `CaseWorkflow` waits until after the first release.
