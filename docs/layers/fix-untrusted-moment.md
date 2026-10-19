# Fix: untrusted data decides through a moment

A fix, not a layer: no warm-up. Found in the tutor review of 11e (pull request #30); on `main`
since 11b. Recorded as D43 (brief), with dated amendments to D39 and D42, whose text is kept.

## The bug

D38 says untrusted data informs and never decides, and the engine checked that on what a rule's
condition reads. But a start is also a moment. A rule may start a step on what a customer typed:
D39 allows it, since a start can only do harm through what is sent, and the input policies check
that. A second rule on that step's start then reads nothing untrusted, so it passes the check:

```json
"say_goodbye": {"on": {"event": "cancelled"},
                "when": {"==": [{"var": "cancelled.note"}, "please cancel"]},
                "then": {"start": ["goodbye"]}},
"close_it":    {"on": {"started": "goodbye"}, "then": {"reach": ["withdrawn"]}}
```

With `withdrawn` in `closes_when`, the customer's note closed the case, with no person and no
input policy in between, and `ventoux check` said nothing. The cases guide even described the
hole ("a rule on that step's start can carry it further").

## Every path found

Each was run on `main` with `cancelled.note` set to `"please cancel"`, then to anything else.
Every probe closed the case, stopped a step, or sent what a policy refuses only on the first
note; `ventoux check` was silent on each.

| | Path | On `main` | Now |
|---|---|---|---|
| 0a | A rule on the start of a run a rule started on untrusted data reaches a milestone | the case closes | it reaches nothing, saying what steered the start |
| 0b | The same, the step started by itself on its own untrusted `when` | the case closes | the same |
| 1 | A steered activity's (workflow's, plan's) own `reaches` | the case closes | the run is done and reaches nothing, saying why |
| 2 | A steered run's outcome, read later by a rule that reads nothing else untrusted | the case closes | the outcome and outputs carry what steered the run |
| 3 | A step requiring a steered run starts by itself; a rule on its start reaches | the case closes | the step is steered by what steered its requirement |
| 4 | A steered wait, ended by the next arrival whatever it says, reaches its milestone | the case closes | as 1 |
| 5 | A person answers a steered task; a rule on `answered` reaches | the case closes | unchanged: a person decided (below) |
| 6 | A rule on a steered start stops a step | the review is cancelled | it stops nothing |
| 7 | A rule on a steered start sets a field from trusted data | the field reads as trusted | it carries what steered the start |
| 8 | A rule on a steered start starts a step whose input refuses untrusted data | the letter is drafted | the start fails on its input |
| 9 | A refresh scheduled for a step whose requirement was steered | its start is a clean moment | it keeps what steered the requirement |
| 10 | A rule on a steered start fails, and an operator retries it | (would act once 0a is fixed) | the firing keeps what its moment carried |
| 11 | An approval given on a steered run | — | doesn't end the steering (decision 4) |

**Why 5 is fine.** The person's answer is a trusted source (D12), and nothing happens until they
act: they may also not answer, and a person may close the case. D39 names a person, in a task,
as the safe tool. The guide asks an author to give such a task an outcome that says no.

## Decided

Agreed with the user, 2026-10-19: option (a+) of the three put (a moment carries what caused it;
(a+) a run carries what steered it, and its start carries the run's; (b) refuse such a rule when
the definition is read), recorded as D43.

1. **A run keeps what steered its start** (`StepRun.steered`, which activities and plans kept
   since 11b, now every kind): its own `when`; the `when` of the rule that started it and what
   that rule's moment carried (`RuleStart.steered`); and what steered the latest done run of
   each step it requires, unless that step is a task. A refresh also keeps what steered the step
   it fetches for (path 9).
2. **A run's start carries it on.** A `started` moment names its run; a rule firing on it keeps
   what the run was steered by (`RuleFiring.steered`), for its retry too (path 10), and counts it
   as read by its condition: a rule that reaches or stops doesn't act (paths 0, 6); a value it
   sets carries it (path 7); a step it starts carries it to its inputs' policies, and on (path 8).
3. **A steered call or plan run** gives an outcome and outputs that carry what steered it (paths
   2, 3), and, like a steered wait, reaches nothing (paths 1, 4). A milestone is then reached only
   by a trusted decision or a person, so no milestone carries steering.
4. **A person in a task is where it ends; an approval is not.** The approver approves that run's
   inputs (D11), not what other rules do once it starts; may never see the untrusted data that
   steered the start; and whether an approval is asked can hang on its own `when`'s threshold, so
   trust would too. Fail closed. (The user, 2026-10-19.)
5. **The messages** name what steered, never a value (D35):
   `close_it#1 on started goodbye: reaches nothing: its moment comes from untrusted data:
   say_goodbye#1's condition, which started goodbye, reads cancelled.note (untrusted:customer),
   and untrusted data can't decide`.
6. **Case validation stays a proof.** How each step's runs may be steered is a value of 11e's
   fixpoint, `started <step>`, grown with the case file's sources since each feeds the other. Its
   ways are the step's starts: by itself or a person's proposal (its own `when` and requirements),
   and each rule that may start it (plus that rule's condition and moment). It is "always"
   untrusted when every way is, whoever writes what each reads. Then:
   - `UNTRUSTED_TRIGGER` (error) or `WRITER_DECIDES` (warning) at a rule on such a start that
     reaches or stops, and at a steered call, plan or wait step's `reaches`;
   - every value read from a steered outcome or output carries it, so the existing checks on what
     a rule's condition or a step's input reads claim it where proven;
   - `INPUT_POLICY` (or `WRITER_DECIDES`) at a start made on such a moment, and at a step's input
     for what steered its requirements.
7. **Cases already open.** A case open on a path the fix decides differently (0a–4, 6) replays
   differently under the new worker, and Temporal refuses its history: it waits until the code is
   fixed (D17). Carried to layer 12, as 11b's paths were; a fixture recorded before the fix shows
   it. On a path decided the same (7: only sources change, no command), the history replays; a
   second fixture shows it.

## Not in this fix

- 11f's timers `since` a start: a moment a run brings, so it must carry what steered the run
  (D43 says so).
- A plan's own transitions stay open (design question 17).

## Seams the tests use

- `run_case(...)`: `history`, `state` (milestones, sources, phase), `needs_attention`; `retry`.
- `validate_case(parse_case(d), CATALOG)`: the issues above.
- The Temporal test server: steering crosses continue-as-new; the two fixtures replay or don't.

## Slices, in order

Each starts with its negative test, seen failing for the right reason.

0. The two fixtures, recorded under `main` before any change; this note and D43.
1. A rule on a steered start doesn't decide (0a, 0b, 6), and a trusted start still does.
2. What a steered start passes on: `set` (7), `start` (8), a retried rule (10).
3. A steered run: reaches nothing (1, 4), its outcome and outputs (2), a step requiring it (3), a
   refresh (9); a person's answer ends it (5); an approval doesn't (11).
4. Case validation: the fixpoint and each issue.
5. On Temporal: crossing continue-as-new; the fixtures.
6. The guide, and the promises.

## Promises

Filled once built: each promise the note makes, and the test that would fail if it weren't true.
