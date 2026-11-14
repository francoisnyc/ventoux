# The lint bar

Not a layer and not a fix: no rule of the product changes, so nothing is decided in the brief
(the maintainer's walkthrough, 2026-11-13). CI's `ruff check` is asked for more, the code is
brought to it, and what is deliberately left out is named.

## What CI checked before

`pyproject.toml` named one rule, TID252 (relative imports), added to ruff's defaults. With the
ruff this project locks (0.16.10) the defaults are wide: `ruff check --show-settings` on `main`
at `4ea3c5b` lists 414 rules switched on, among them parts of B, SIM, UP and RUF, the import
sorting (I001), `exec` (S102) and the unused `noqa` (RUF100). So `ruff check` on `main` said
`All checks passed!` with a good deal already checked, none of it named in the repository.

## What it checks now

`extend-select` names the families: B, UP, I, SIM, RET, RUF, C4, PIE, PTH, ERA, N, and C901 with
`max-complexity = 10`; 506 rules in all. It also names the five rules the code's own `noqa`
comments silence (S102, BLE001, ASYNC251, DTZ001, TRY004), which this ruff has on by default:
named, each comment stays real whatever a later version's defaults are.

Ignored, each with its reason beside it in `pyproject.toml`:

| Rule | Why |
|---|---|
| RUF001, RUF002, RUF003 | the typographic characters in messages and documents (`‹sensitive›`, `’`) are meant |
| N818 | refusals are named `...Refused` and `...Invalid` on purpose; the maintainer keeps the names |
| RUF043 | `pytest.raises(match=...)` patterns hold unescaped regex characters: left for a pull request of its own |

`docs/layers/spike-dsl` is left out of the lint (`lint.exclude`): the spike is kept as written.
It is still formatted.

## `ruff check`, before and after

Before, on `main` at `4ea3c5b`, with its own configuration: `All checks passed!`

The same code under the new configuration, the spike left out:

```
43  C901    complex-structure
 4  SIM105  suppressible-exception
 4  SIM300  yoda-conditions
 3  RET503  implicit-return
 3  C420    unnecessary-dict-comprehension-for-iterable
 2  RUF006  asyncio-dangling-task
 2  B905    zip-without-explicit-strict
 1  PTH123  builtin-open
 1  RUF005  collection-literal-concatenation
 1  ERA001  commented-out-code
 1  N815    mixed-case-variable-in-class-scope
 1  N806    non-lowercase-variable-in-function
 1  B904    raise-without-from-inside-except
 1  RET504  unnecessary-assign
Found 68 errors.
```

After, on this branch: `All checks passed!`

## The 25 findings, and what each fix does

| Finding | Where | The fix |
|---|---|---|
| RET503 (3) | `case/rules.py` `said`, `case/reach.py` `moment_can_come`, `case/warnings.py` `at_moment` | each ended by calling `unknown_moment`, which always raises; it is now `return unknown_moment(...)`. No behaviour changes. Two of the three refusals had no test of their own: see below |
| B905 | `authoring/provider.py` `difference` | `strict=False`, said on the line: the messages two requests share are compared first, and a different number of them is said just after. `strict=True` would raise instead of saying it |
| B905 | `case/diff.py` `at` | `strict=True`: the lengths are compared on the line before, so it can never raise |
| B904 | `authoring/answers.py` `one_object` | `from None`: the decoder's own error holds the whole text, and is left out of what a traceback prints |
| SIM105 (4) | `temporal/cases.py`, `temporal/contract_check.py`, `tests/test_temporal_case.py` (2) | `contextlib.suppress`, the comment kept |
| RUF006 (2) | `temporal/cases.py` `beside`, `scripts/clock_held.py` | silenced where it is, with the reason: see below |
| SIM300 (4), C420 (3) | tests, `tooling/doctor.py` | ruff's own safe fixes |
| PTH123, RET504, RUF005, N806, ERA001 | tests | `Path.read_text`; a value returned directly; one list; a local name in lower case; a comment reworded (it was prose, read as code) |
| N815 | `tests/test_contract_schema.py` | silenced where it is: `camelCase` is the name under test |

**RUF006, silenced and not "fixed".** The rule asks that a reference be kept to a task, since
asyncio's own loop holds tasks weakly and one can be collected part-way. A workflow doesn't run
on asyncio's loop: Temporal's workflow loop keeps every task it creates in a set until the task
is done (`_register_task` in `temporalio/worker/_workflow_instance.py`, SDK 1.34.0: `self._tasks.add(task)`,
then `task.add_done_callback(self._tasks.remove)`). So the task `beside` creates is not lost.
Keeping our own set would add workflow state that decides nothing. The `noqa` says so where it
is, in `temporal/cases.py` and in the script's workflow.

## Tests added

Where a fix could change behaviour, a test shows the case it guards:

| Test | Guards | Seen failing |
|---|---|---|
| `tests/test_advisor.py::test_a_recording_replays_only_the_requests_it_recorded` (new lines) | a replayed request with one message more is refused for its number of messages | with `strict=True`: `ValueError: zip() argument 2 is longer than argument 1` |
| `tests/test_rules.py::test_an_unknown_moment_fails_closed` (new lines) | `moment_can_come` and `at_moment` each refuse a moment they don't know | with either refusal replaced by `return None` |

The second is more than the lint asked for. Before these lines, each of those two refusals could
be removed with every test passing: the existing test met `said`'s refusal first. Fail closed
asks for a negative test per evaluator.

No test is added for `case/diff.py`'s `at`: `strict=True` there can't be reached with lists of
different lengths.

## The `noqa` comments

The walkthrough counted 41 unused. Under the configuration CI runs, none was: the count comes
from running ruff with only the new families selected (`--select`), where the rules the comments
name are off. With the defaults kept (`extend-select`), S102, BLE001, B015, B006, ASYNC251,
DTZ001, TRY004 and F401 are all on, so every comment silences a real finding. To keep that true
on purpose and not by a version's defaults, the five outside the new families are now named in
`extend-select`. None is left unused, and RUF100 fails a new one.

## C901

43 functions are over 10 branches today: 38 in `src`, 5 in `tests`. Each is marked
`# noqa: C901` where it is defined, by `ruff check --add-noqa`, and nothing else in them is
changed. A new function over 10, or an eleventh branch in one that sits at 10, fails.

## Two mutations, each failing `ruff check`

```
# an unused noqa added to an import in case/keeping.py
RUF100 [*] Unused `noqa` directive (unused: `F401`)
Found 1 error.

# an eleventh branch added to case/reach.py can_happen, which sits at 10
C901 `can_happen` is too complex (11 > 10)
Found 1 error.
```

## Left for later

- RUF043, the 165 `match=` patterns: its own pull request.
- The 43 marked functions: splitting any of them is a change of its own. `case/runtime.py`'s
  split (a pure move) comes next and removes no mark by itself.
