# Fix: case validation says what it proves, and only that

A fix, not a layer: no warm-up, and nothing new to build. Two things found while building layer 11
and left for their own fix: a false `INPUT_POLICY` (on `main` since 11e, recorded in
`docs/layers/fix-untrusted-moment.md`, "Found, not fixed") and an unclaimed `NEVER_STARTS` (from
11h1, recorded in `docs/layers/11-rules.md`, "Decided while building 11h1"). Both were traced in
layer 11's walk-through (learning question 40).

D34 says case validation is a proof: an error claims only what holds in every case, and what
holds in every case is said. These two broke that, one in each direction. The fix only restores
D34, so no decision changes meaning and none gets an amendment.

## 1. A false `INPUT_POLICY`

**The bug.** An input whose policy is `only_from(kyc)` was given a field that a rule sets from
kyc's value, with no mark on the field. The check claimed the input was refused every time, but
the run sent it:

```
INPUT_POLICY (error) at steps.record.inputs.status: ledger.record@1 takes status only from kyc,
  and this value comes from a value written in the plan: use a value kyc gave

keep_status#1 on reached checked: setting kyc_status, from system:kyc
scheduled record#1: ledger.record@1 (amount from person:ana; status from system:kyc)
```

Even the message was wrong: it couldn't find a field that was refused, so it fell back to "a
value written in the plan".

**The cause.**
- `rule_writes` (`case/writers.py`) gives an unmarked field the mark `frozenset()`.
- `always` counted a write as refused when its mark was.
- `only_from` refuses a value with no source ("it comes from no system"). So every rule's write
  to an unmarked field was counted as always refused.
- The runtime stamps the union of what the rule read and the mark (D42), so it sent the value.

**Decided.** No mark means "only the sources of what the rule read". A mark adds a source
(D12), and with none there is nothing to add. In `always`, a write is refused by its mark only
when the mark is not empty. The rest of `always` stays sound because any value it counts as
always refused carries a source the policy refuses, never "no source":
- every value a writer stamps has at least one source;
- marks count only when not empty;
- a rule that reads nothing is refused when the definition is read (D42).

**Every caller checked.**
- `case_sources` and `writer_decides` take the union with the mark, so an empty mark adds
  nothing.
- `how_started` and the refusal of steered values (`flow.py`) look only at untrusted sources,
  and only when there is at least one.
- `trigger_issues`, `moment_issues` and `reach_issues` refuse with `flow.is_untrusted`, which is
  false for no sources.
- `Refusals.always`'s "reads nothing" branch is an input written as a constant, which really
  comes from nobody (D36).

So only the input-policy path was wrong, for a case opened by a system or by a person.

## 2. An unclaimed `NEVER_STARTS`

**The bug.** A rule written before the rule that always closes the case on the same moment,
whose `then` starts a step, never starts it. Its start is a proposal that admission decides after
the moment's rules, when the case is closing. The check said nothing:

```
(validate_case: no issue)

withdraw#1 on event cancelled: reaching withdrawn
say_goodbye#1 on event cancelled: goodbye not started: withdrawn is reached, so the case closes
  and nothing new starts
```

The same holds for the closing rule's own start (`withdraw` reaching `withdrawn` and starting
`goodbye`: in one `then` the reach acts first). And when such a rule is the only way the step
starts, the step never runs, and its `NEVER_RUNS` was silent too. That included 11h1's own form,
a rule written after the closing rule, which got `NEVER_FIRES` while its step got nothing.

**The cause.** `start_refused` (`case/reach.py`) knew two proven forms: the opening, and the
step's own moment. 11h1's test for "this rule always closes the case" lived in `validate.py` and
fed only `NEVER_FIRES`. `can_start` reads `start_refused`, so it counted the rule as able to
start the step.

**Decided.**
- **A third proven form in `start_refused`:** the rule fires on a moment where it, or a rule
  written before it, always closes the case.
- **Scoped as 11h1 scoped `NEVER_FIRES`.** `always_closes` (now in `reach.py`, shared by both
  checks) holds only for a rule that:
  - has no `when`;
  - sets nothing (a value that can't be read fails the whole rule);
  - reaches every `closes_when` milestone;
  - is not on a step's start, which untrusted data may steer (D43), nor a timer.

  Nothing is claimed where that rule may not close.
- **The starting rule's own `when` and `set` don't matter.** If its `when` is false, nothing
  starts. If it is true, the start is refused. If it can't be read, the retry comes once every
  `closes_when` milestone is reached, when nothing new starts (D34).
- **`NEVER_RUNS` follows** through `can_start`, pointing at the rule, as 11b decided ("one
  cause, both issues").
- **One cause, one issue.**
  - A rule that never acts (written after the closing rule) gets `NEVER_FIRES`, never a
    `NEVER_STARTS` beside it.
  - A step whose own requirements already come only once the case closes keeps its own
    `NEVER_RUNS` ("closes once checked is reached, before lookup could start"), and the closing
    form steps aside. Without that, the advice would be "start it on another moment", which
    can't help. (Found by the suite: `test_a_rule_starts_nothing_once_the_case_closes`.)

**The messages** name rules, steps and milestones, never a value:

```
NEVER_STARTS at rules.say_goodbye.then.start: say_goodbye can never start goodbye: it fires on
  event cancelled, where withdraw always reaches withdrawn, so refund closes and nothing new
  starts: start it on another moment
NEVER_STARTS at rules.withdraw.then.start: withdraw can never start goodbye: it fires on event
  cancelled and always reaches withdrawn, so refund closes and nothing new starts: start it on
  another moment
```

The cases guide's `NEVER_STARTS` row names the new form.

## Kept

- **Fail closed.** The first fix removes a false error only where the value's sources are known.
  A value with no source at all is still refused.
- **The runtime depends on nothing validation did.** Neither fix touches the runtime. Each test
  runs the case with `run_case`, which never calls `validate_case`.
- **`core` and `case` read no clock, randomness or I/O.**
- **Decisions are never rewritten.** The "Found, not fixed" entries keep their text, each with a
  dated line saying where it was fixed.

## Promises

Every test is in `tests/test_check_proofs.py` unless said otherwise. Each was seen failing
against `main`'s code, except the controls marked "passes on main". Each condition was checked by
mutation: removing it fails the test named.

| Promise | Test that would fail |
|---|---|
| A rule's write to an unmarked field, from a value the policy takes, isn't claimed refused, and the run sends it | `test_a_rules_write_with_no_mark_isnt_refused_for_coming_from_nothing` |
| It is still claimed where the value really is refused, by what the rule read or by the field's mark, and the run refuses it (passes on main) | `test_a_rules_write_refused_by_what_it_read_or_its_mark_is_still_claimed` |
| A start on a moment where a rule written before it always closes the case is `NEVER_STARTS`, and the run refuses it; the same for the closing rule's own start; whatever the starting rule's own `when` or `set` | `test_a_start_on_the_moment_a_rule_always_closes_never_starts` |
| A step that only such a start starts is `NEVER_RUNS`, pointing at the rule, whether the rule is written before the closing rule (`NEVER_STARTS` beside it) or after it (`NEVER_FIRES` beside it, no `NEVER_STARTS`) | `test_a_step_only_such_a_start_starts_never_runs` |
| Nothing is claimed where the closing rule may not close (a `when`, a `set`, a step's start), and the run starts the step (passes on main) | `test_a_start_where_the_closing_rule_may_not_close_isnt_claimed` |
| A step whose requirements come only once the case closes keeps its own `NEVER_RUNS`, with no `NEVER_STARTS` beside it | `test_a_rule_starts_nothing_once_the_case_closes` (`tests/test_rules.py`) |
| 11h1's `NEVER_FIRES` keeps its scope, now through the shared `always_closes` | `test_a_rule_after_one_that_always_closes_never_acts`, `test_a_rule_after_one_that_may_not_close_isnt_claimed` (`tests/test_patterns.py`) |
