# Layer 11: rules

Status: research done, 2026-10-16 (`docs/layers/11-research.md`, Flowable's CMMN engine at
`f6017e3`); the warm-up skipped at the user's request, 2026-10-17 (learning question 32 stays
open, for the next layer); the split and 11a's eleven choices agreed in the session, 2026-10-17
(all as proposed; design question 17, option a); D38 and the cases guide's "Rules" drafted the same
day; 11a built, slices 0–7; Promises checked against the tests, 2026-10-17; the tutor review's
fix built test-first, and the Promises table names every test, the same day. 11b: the warm-up
(learning question 32) answered "tell me", 2026-10-18; the mentor's review of the first proposal;
the choices agreed in four groups the same day, all as recommended, one of them splitting 11b in
two (see "The split").

## What this layer is for

Until now a case reacts in one way only: after every event, admission asks each step "may you start
now?" (layer 8). That covers "pay once the review approves", not "if nobody has assessed the claim
in five days, escalate", "when the customer cancels, stop", or "once the check is done, mark the
customer high risk if the score is over 70". Layer 11 adds the **rule**: *when* something happens,
*if* a condition holds, *then* act on the case (brief, Simplifications, "one kind of rule"; D7).

User-facing description: `docs/guides/cases.md`, "Rules" (11a's part written 2026-10-17, before
building: the curriculum's "document first"); each later part adds to it. Decision: brief D38.

The `chartering` prototype is checked out in this session (`/home/user/chartering`, `197d519`). It
splits rules into sentries, triggers and deadlines; drawn on below: `src/case/events.ts` (a
trigger's `when` taints what it writes, and a milestone it would reach on untrusted data is
withheld), `src/case/deadlines.ts` (a clock moved only by the caller), `src/case/validate.ts`
(`UNTRUSTED_TRIGGER`, `UNTRUSTED_SENTRY`) and `docs/design.md` §10, "Rules that act on untrusted
data".

## What the research changes

From `11-research.md`, five findings shape the design (each is argued there, with its quotes):

1. **A rule remembers nothing.** Flowable needed a second trigger mode because a remembered "if"
   outlived the moment it described (`TriggerModeSentryTest.testTriggerModeOnEvent`). A Ventoux rule
   reacts to a moment and reads its condition then: Flowable's `onEvent`, as the only mode. What its
   default mode is for ("once A is done and x holds") is admission, which re-reads state after every
   event. **Admission is level-triggered; a rule is edge-triggered.**
2. **Stopping is not cutting.** Flowable's exit deletes a running task or child process. Ventoux's
   stop must do what a close does to one step (brief, D10, D28): cancel open work, let running work
   finish and flag it; and never stop a failed run (brief, D17, D26).
3. **Each run is its entry.** Flowable's repeated runs read the case's variables as they are, plus a
   local counter; Ventoux's runs read the case file as it is, and are named by their entry
   (`assess#2`), which a rule or a timer can name.
4. **Listening is not waiting, said directly.** Flowable reaches it through orphan removal,
   completion-neutral items and auto-complete; Ventoux says it once (brief, D10). Timers do hold a
   case, so they need to be cancelled when they can no longer act (Flowable's orphan idea), and a
   timer that re-arms itself keeps a case open for ever (`RepetitionRuleTest.testRepeatingTimer`).
5. **Rules run before the case settles.** Flowable judges completion "only when children are
   stable"; Ventoux's rules run inside `decide`'s loop, before the case may close.

## The split

Layer 11 lands as seven pull requests, each with its section in this note, its own Promises table
and its own tutor review, as layers 8–10 did. Each part's choices are decided in its own session.

| PR | Builds | Codes (proposed) |
|---|---|---|
| **11a: the raw rule, inside the case** | `rules` in the definition: `on` (the case opened, a milestone reached, a step started), `when`, `then: reach`; when rules run in `decide`; a rule that can't be read needs attention; untrusted data can't decide (design question 17 decided); rules and the close; case validation kept true | `NEVER_FIRES`, `UNTRUSTED_TRIGGER` |
| **11b: rules that start steps** | `then: start` (the engine proposes, through admission: the rework loop), and the moment a task is answered; the half of design question 17 that steers which step starts, built; validation: a step a rule starts can run; a rule that restarts a step for ever | `NEVER_STARTS`, `NEVER_CLOSES` extended, `CLOSED_ONLY_BY_A_PERSON` |
| **11c: rules that stop steps** | `then: stop` (what a close does, to one step; never a failed run); one place in the case that stops every running child; `cancellable` workflows (D29), stopped by Temporal's cancellation; closing through that place | |
| **11d: events from outside** | declared events with a typed payload and a source (D12); `on: {"event": ...}`; `then: set` (update the case file), which brings back the provenance fixpoint (D34, D36); listening is not waiting, and a step explicitly waiting for an event (D10); "arrival is a fact, content is not"; an event as a signal on Temporal | `UNTRUSTED_TRIGGER` for event content; `UNKNOWN_EVENT` |
| **11e: time** | timers, `on: {"after": "5d", "since": <moment>}`: set on their moment, pending work (D10), fired as an event stamped with its own due time (D33), never a clock `decide` reads; cancelled by their rule's purpose ending and by any close; crossing continue-as-new exactly (D27), replaying the same; staleness noticed by a timer (9d's carried note); reports list set timers (D24) | `NEVER_CLOSES` for a timer that re-arms itself |
| **11f: reading rules** | the plain-language renderer for every rule; `ventoux simulate`: a story on a timeline, with simulated time, showing when each rule fires; stories as tests | |
| **11g: patterns and teaching warnings** | `sla` (from the latest start; `since=first_start` explicitly), `reminder`, `four_eyes` (`count=2`, D11, D23), each expanding into raw rules visible in validation and views, each with a story test; D7's teaching warnings (a timer anchored on the first start of a repeatable step, a rule whose condition reads untrusted data, what is left of "rules that can never fire" once 11a's error has taken the proven ones) | warnings |

**Why this order.** 11a is the smallest rule that *acts*, and it brings the two things every later
part stands on: where rules run in `decide`, and case validation kept true once something other
than a step reaches a milestone (brief, D34). Starting steps (11b) needs that loop and reuses
admission; stopping them (11c) reuses closing. Events (11d) bring outside content, so trust and
the update action belong there, with the provenance fixpoint they need. Timers (11e) need moments
to anchor on (11a) and events (11d), since a timer firing is an event with its own time. The
renderer and `simulate` (11f) need every kind of rule to exist; the patterns (11g) are written in
raw rules and tested as stories, so they come last, as D7 says: "raw rules are the engine's
concept, not the first one people meet".

*Renumbered 2026-10-18, in 11b's session:* 11b, as first planned, held both starting and stopping
steps; it was split in two, so events, time, reading rules and patterns moved from 11c–11f to
11d–11g. 11a's section below keeps the letters it was written with, where "11b" meant both.

**Carried into layer 11, and where each lands:**

| Carried | Where |
|---|---|
| Case validation stays true once rules reach milestones and start or stop steps (`can_happen`, `NEVER_RUNS`, `CLOSES_AT_OPENING`, `NEVER_CLOSES`, `SET_AFTER`, the 10d warnings) | 11a for `reach`, 11b for `start`, 11c for `stop`, 11d for `set` |
| Provenance: a rule computing fields from fields brings the fixpoint back (D34, D36) | 11d, with `set` |
| `UNTRUSTED_TRIGGER` and design question 17 | decided in 11a; built in 11a (a condition that decides) and 11b (a condition that steers which step starts); event content in 11d |
| Time as event data stamped from workflow time (D33); timers as pending work (D10), across continue-as-new (D27), on replay; staleness noticed by a timer (9d) | 11e |
| Whether rules act once every `closes_when` milestone is reached (D34) | 11a (choice 7) |
| What a close does to timers (D10: cancelled) | 11e |
| `sla`, `reminder`, `four_eyes`, the renderer, teaching warnings, `ventoux simulate` | 11g, 11f, 11f, 11g, 11f (as in the table) |

---

## 11a. The raw rule, inside the case

### What this part is for

Some facts about a case are decided from its data, not by a step finishing: "the customer is high
risk once the check scores over 70", "the claim is a large one if the payout is over 10 000". Today
a milestone is reached only by a step or one of its outcomes (`reaches`), so these can't be said.
11a adds the rule in its smallest acting form: a moment inside the case, a condition, and milestones
reached.

A sketch, on the cases guide's claim (`check` is the KYC workflow step, giving `risk_score` from
`system:kyc` and `analyst_notes` from `untrusted:llm`):

```json
"rules": {
  "flag_high_risk": {
    "display": {"title": "Flag a high-risk customer"},
    "on": {"reached": "checked"},
    "when": {">": [{"var": "check.risk_score"}, 70]},
    "then": {"reach": ["high_risk"]}
  }
},
"steps": {
  "review_risk": {
    "kind": "task",
    "display": {"title": "Review a high-risk customer"},
    "roles": ["fraud"],
    "requires": ["high_risk"],
    "outcomes": {"cleared": {"display": {"title": "Cleared"}, "reaches": ["risk_cleared"]}}
  }
}
```

Read aloud: once the customer is checked, if the risk score is over 70, the customer is high risk;
a high-risk customer is reviewed by fraud. Its run:

```
check#1 done, giving analyst_notes from untrusted:llm; risk_score from system:kyc; ...
reached checked
flag_high_risk#1 on reached checked: reached high_risk
reached high_risk
started review_risk#1: waiting for cleared by fraud
```

### Decided in the session

All eleven agreed as proposed, 2026-10-17; the alternative set aside is said with each.

1. **Shape: `on`, `when`, `then`.** A rule is `{"display", "on", "when"?, "then"}` under the
   definition's `rules`, by name. `when` means what it means on a step: a condition read once the
   moment has come, so one word keeps one meaning across a definition. `on` names the moment (as
   the prototype's triggers and Flowable's on parts do). People still read *when / if / then*: the
   renderer (11e) says "When the customer is checked, if the risk score is over 70, reach high
   risk". Set aside: `when` for the moment and `if` for the condition, the brief's words, which
   would make a step's `when` and a rule's `when` mean different things. A rule's name is unlike any
   step or milestone, since its firings are entries (`flag_high_risk#1`) beside step runs; a title is
   required (brief, D1).
2. **Three moments in 11a:** `"on": "opened"` (once), `{"reached": "<milestone>"}` (once, since a
   milestone is never undone) and `{"started": "<step>"}` (each run that starts: a task's run
   opening, an activity or workflow scheduled, a plan started, a refresh run too; a retry is the
   same run and starts nothing, brief, D26). Set aside for now: "a step done" and "a step answered":
   an outcome already reaches milestones (`reaches`), so a rule on the milestone says the same. Each
   new moment is a decision recorded in the brief, like an operator.
3. **What a rule reads.** `when` is read in the decision that handles the moment, on the case file
   as it is then, after the event's own changes (an answer's form, an output landing). It is
   type-checked over the case's values first, like every case expression (brief, D35), so a misspelt
   outcome fails the rule instead of reading as false. Nothing is remembered between decisions
   (research, finding 1).
4. **When rules run.** In `decide`, each moment is queued as it happens: the opening, each
   milestone reached, each run started. After the event is handled, and again after each round of
   admission, every queued moment is taken in order, and every rule on it, in the definition's
   order, fires once. A `reach` queues the milestones it reaches, so rules can follow rules; then
   admission runs again. The case settles (and may close) only once nothing is queued. **It ends:**
   in 11a every moment is a milestone reached for the first time (finitely many) or a run started,
   and a decision starts finitely many runs (a step starts by itself at most once; any other start
   needs a person's event). 11b, which lets rules start steps, must keep this true.
5. **A rule that can't be read needs attention** (fail closed, brief, D17). A firing whose `when`
   reads a missing field, a wrong type or an unknown operator reaches nothing and *fails*:
   `flag_high_risk#1 failed: …` joins `needs_attention`, is pending work (the case doesn't close),
   and an operator retries it (its `when` read again, on the case file as it is then) or closes the
   case, as for a step (brief, D26). Set aside: treating it as "not fired", which is the permissive
   default the non-negotiables forbid (a rule that would have reached `closes_when` would let the
   case close as if nothing were wrong).
6. **Untrusted data informs; it never decides** (design question 17, decided here; brief, D12).
   Reaching a milestone decides for the case, like an approval. So:
   - **at runtime**, a rule whose `when` reads any value whose sources include `untrusted:` does not
     act, and says so, naming the value and its source, never the value: `flag_high_risk#1 reached
     nothing: its condition reads check.analyst_notes, from untrusted:llm, and untrusted data can't
     decide`. Not acting is the safe side, so this is recorded, not "needs attention";
   - **in validation**, `UNTRUSTED_TRIGGER` (error) when a value the condition reads is untrusted
     whoever writes it (a field declared `untrusted:<label>`, an output whose contract declares an
     untrusted source or none, brief, D29): the rule could never act, so it is a proof. In 11a every
     value is either always untrusted or never; a field only some writers make untrusted comes with
     `set` (11c), and gets a warning then;
   - **the other half of the question**, whether untrusted data may steer *which step starts*
     (a step's `when`, a rule's `start`), is decided now and built in 11b. Agreed (option a): a
     condition's sources count as read by every input of the step it lets start, for the input
     policy check (the prototype's "strict mode", bounded in a case: the influence ends at the step
     it gates, since a case has no position to carry it further); and an approval's `when` that
     reads untrusted data asks for the approval regardless (untrusted data can add an approval,
     never remove one). This changes behaviour layers 4, 8 and 10c decided (the runtime check before
     an activity and `INPUT_POLICY`), so it needs your agreement. The other options of design
     question 17: refuse such a condition before any step with an input policy; or leave conditions
     to inform, with D7's teaching warning only.
7. **Rules and the close.** Rules act only while the case is open and not every `closes_when`
   milestone is reached: once closing, or once the close is held by a failed run (brief, D34), no
   rule acts, including one on the very moment that completed `closes_when`. Each such firing is
   recorded, so an expected reaction that didn't come is explained: `flag_high_risk#1 not applied:
   paid is reached, so the case closes: nothing new is decided`. This extends D34's "nothing new
   starts" to "nothing new is decided", the same for a person's close. Set aside: letting `reach`
   act while `start` waits (two rules for one close). Timers and the close are 11d's.
8. **Case validation stays true.** Every error must stay a proof (brief, D34):
   - `can_happen` adds every rule whose moment can happen (the opening always; a milestone in the
     set; a step in the set), with what it reaches; its `when` taken as possibly true. Still a least
     fixpoint grown from nothing: it only adds, over finitely many steps, milestones and rules;
   - so `NEVER_RUNS`, `DEADLOCK`, `NEVER_CLOSES` and `CLOSE_UNREACHABLE` count milestones rules
     reach, and their messages say "no step or rule reaches"; `UNREACHABLE_MILESTONE` likewise;
   - **`NEVER_FIRES`** (error), new: a rule whose moment can never happen (a milestone or step left
     out of `can_happen`), or happens only once every `closes_when` milestone is reached (its
     moment is reaching the only one left, or the start of a step that can only start after them),
     so by choice 7 it never acts. D7 calls "rules that can never fire" a teaching warning; what is
     proven for every case is an error since D34, and what depends on values stays a warning (11f);
   - `MAY_BE_UNSET` and `SET_AFTER`: a milestone a rule reaches proves nothing about values, so
     "a milestone only setting it reaches" excludes milestones a rule reaches, and "runs only after"
     counts a rule as a way to reach what the step requires;
   - `OUTCOME_UNREAD` counts a rule's condition as a reader; `EXPRESSION_INVALID`, `MAY_BE_UNSET`
     and `SET_AFTER` read a rule's condition too, its moment standing for `requires` (`reached m`
     as requiring `m`; `started s` as requiring what `s` requires; the opening as nothing);
   - `CLOSES_AT_OPENING` counts what rules on the opening may reach: a rule starts no step, but a
     milestone it reaches admits the steps requiring it in the same decision. *Corrected in the
     tutor review of 11a: it said "unchanged: in 11a a rule starts nothing", which made the error
     no longer a proof (see "From the tutor review").*
   - the runtime depends on nothing validation did (brief, D34): every refusal above happens in
     `decide` too.
9. **On Temporal, nothing new but state.** Rules run in `decide`, so the case workflow runs them as
   it is. A rule's firings and failed firings are part of the case's state, so they cross
   continue-as-new (brief, D27: "the whole state of the case"); a retried rule is the existing
   `retry` signal, naming its entry.
10. **Doors left open** (the checkpoint before layer 12, agreed 2026-10-16). Each choice above
    is checked in the session against what Flowable can express and Ventoux can't yet. Two
    checks so far: "A has completed and, later, x holds" is admission (a step requiring A's
    milestone, with `when: x`), and a rule on a milestone, so remembering nothing loses nothing
    a sentry says; and `on` names one moment, so a stage's moments ("a stage completed") would
    be a new moment, recorded in the brief, without changing the shape.
11. **D38**, drafted with this note once agreed: rules, their moments, what they read, untrusted
    data can't decide (design question 17), and rules stop with the close.

### Where the code goes

- `case/definition.py`: `Rule`, `rules` on the definition; names unlike steps and milestones.
- `case/rules.py` (new): which rules a moment fires, reading the condition, the trust check, acting.
- `case/state.py`: a rule's firings (entry, status, reason); `case/runtime.py`: the moments queued
  in `decide`, and the loop with admission; `case/closing.py`: a failed firing is pending work.
- `case/reach.py`, `case/validate.py`, `case/warnings.py`, `case/types.py`, `case/flow.py`: as in
  choice 8.
- `temporal/carried.py`: the firings cross continue-as-new.
- `docs/guides/cases.md`: "Rules", and the new codes in its tables.

### Not in 11a

- Starting and stopping steps (11b); events from outside and `set` (11c); timers (11d); the
  renderer and `simulate` (11e); patterns and teaching warnings (11f).
- The steering half of design question 17 is decided here and built in 11b.
- No new dependency.

### Seams the tests use

- `parse_case(data)` with `rules`; `CaseInvalid` for a rule naming what doesn't exist.
- `run_case(...)`: `history`, `needs_attention`, `closed`, `waiting_for`; `retry(entry, who)` for a
  failed firing.
- `validate_case(case, catalog)`: the issues above.
- The Temporal test server, once: a case whose rule fired continues as new and replays.
- The guide's examples, run as written.

### Slices, in order

Each starts with its negative test, seen failing for the right reason.

0. **The shape.** Negative: a rule reaching a milestone nobody declared, on a step that doesn't
   exist, named like a step, without a title, with nothing to do: refused when read.
1. **Reaching.** Negative: a rule whose condition is false reaches nothing. Then each moment
   (`opened`, `reached`, `started`), a step requiring a milestone a rule reaches, rules following
   rules, and the order of moments and rules.
2. **Fail closed.** Negative: a rule reading a field nobody set needs attention and the case doesn't
   close; a misspelt outcome fails it too; a retry reads it again.
3. **Untrusted data can't decide.** Negative: a rule reading `check.analyst_notes` reaches nothing,
   saying why, without the value.
4. **The close.** Negative: once every `closes_when` milestone is reached, no rule acts, held or
   closing, and each firing says why.
5. **Validation stays true.** Negative: `NEVER_FIRES` and `UNTRUSTED_TRIGGER`; then a definition
   10a refused that a rule rescues has no issue, and each check in choice 8.
6. **On Temporal.** A case whose rule fired continues as new and replays the same.
7. **The guide and the promises.**

### Decided while building

- **A retried run starts nothing again** (slice 1), as D38 says; and neither does a run that
  failed before it started (an input refused), when an operator retries it: it is the same run,
  and `started` fires only for a new one.
- **Firings cross continue-as-new from slice 1,** not slice 6: the guard on the carried state
  (`test_a_carried_state_reads_back_as_it_was`) failed as soon as the state had a new field.
  Slice 6 kept its Temporal test, seen failing with firings left out.
- **`needs_attention` is one function** for both drivers (slice 2), and who may retry is one
  function for steps and rules (`operating_role`).
- **Not acting is checked before acting, whatever the condition gave** (slice 3): the trust check
  runs on what the condition reads once it could be read, so an untrusted condition's value never
  shows in what happens next.
- **The close, completed** (slice 4), with three things the session left implicit:
  - "nothing new is decided" covers a person's close too, with its own reason (`the case is
    closing, so nothing new is decided`);
  - a rule reaching the last `closes_when` milestone closes the case in the same decision: `decide`
    checks `closes_when` again after admission, which it didn't need while only events reached
    milestones, and stops plan steps after both checks;
  - a failed rule holds a `closes_when` close and a person's close cancels it, as for a failed
    step (brief, D26); retried while it holds the close, it reads its condition, decides nothing,
    and the case closes.
- **What validation claims, and no more** (slice 5):
  - `NEVER_FIRES` "after the close" is claimed only for a rule on reaching the one `closes_when`
    milestone; other forms are left unsaid;
  - a rule's own `SET_AFTER` is claimed only on the opening, where nothing has run; on any other
    moment it is `MAY_BE_UNSET`;
  - the 10a messages for a milestone nothing reaches now say "no step or rule reaches" (choice 8),
    in the guide's table and tests too;
  - all four `NEVER_FIRES` branches were written before their tests, which passed at once; one
    exposed a message ("it can ever happen") copied into the test from the code. Fixed in both.
- **The guide's examples, corrected by running them** (slice 7): the unreadable rule fires
  `"on": "opened"` (on `checked` the score is always set), and the close example closes on
  `checked`, which this refund reaches, where it said `paid`. The two new codes have their own
  table in the guide's "Rules", checked like the others.

### From the tutor review

- **`CLOSES_AT_OPENING` was no longer a proof.** It asked only whether a step starting by itself
  required nothing, but a rule on the opening may reach a milestone that lets such a step start:
  the review's probe (`review` requiring `triaged`, which a rule on the opening reaches) was
  refused as closing at once, and ran waiting for the review. Now the check first collects what
  the opening may reach: the milestones of rules on the opening, then of rules on those, every
  `when` taken as possibly true, as `can_happen` does. A step starting by itself whose
  requirements are all among them may start, so no issue is given; whether it does then depends
  on data.
- **A rule on the opening with an issue of its own gets no `CLOSES_AT_OPENING` beside it.** It may
  fail as the case opens, and the case then needs attention instead of closing; its own issue says
  why (one cause, one issue). Any issue at the rule counts, a warning included, since a rule that
  may fail is enough to make "closes at once" unproven.
- **The Promises table names every test,** one per row or listed by name, so it can be checked
  against the file mechanically, as every earlier table can.

### Promises

Every test is in `tests/test_rules.py` unless said otherwise.

| Promise | Test that would fail |
|---|---|
| A rule reaching a milestone nobody declared is refused when read | `test_a_rule_reaching_an_undeclared_milestone_is_refused` |
| A rule named like a step or a milestone is refused | `test_a_rule_named_like_a_step_or_a_milestone_is_refused` |
| A rule on a step or milestone the case doesn't declare is refused | `test_a_rule_on_what_the_case_doesnt_declare_is_refused` |
| A rule names one of three moments: the opening, a step started, a milestone reached | `test_a_rule_names_one_of_three_moments` |
| An unknown moment is refused in one line | `test_an_unknown_moment_is_refused_in_one_line` |
| A rule without a title is refused | `test_a_rule_without_a_title_is_refused` |
| A rule that reaches nothing is refused | `test_a_rule_that_does_nothing_is_refused` |
| A rule whose `when` is false reaches nothing, and says so | `test_a_false_condition_reaches_nothing`, `test_the_guides_false_condition_says_so` |
| The opening fires its rules once, and a milestone is reached once | `test_a_rule_on_the_opening_reaches_its_milestone_once` |
| A rule fires on each started run of its step | `test_a_rule_fires_on_each_run_of_its_step` |
| Rules follow rules, moments in the order they come, and a milestone a rule reaches admits the steps requiring it in the same decision | `test_a_milestone_a_rule_reaches_starts_what_requires_it`, `test_the_guides_rule_runs_as_shown` |
| Rules on one moment fire in the order written | `test_rules_on_one_moment_fire_in_the_order_written` |
| A rule that can't be read needs attention and keeps the case open, never read as false | `test_a_rule_that_cant_be_read_needs_attention`, `test_the_guides_unreadable_rule_is_shown` |
| A misspelt outcome in a rule's `when` fails it (brief, D35) | `test_a_misspelt_outcome_fails_the_rule_never_reads_false` |
| A retry of a rule that still can't be read is refused | `test_a_rule_still_unreadable_is_not_retried` |
| An operator's retry reads a failed rule's condition again | `test_a_retried_rule_reads_its_condition_again` |
| A rule whose condition reads untrusted data reaches nothing, saying which value and source | `test_untrusted_data_cant_decide`, `test_the_guides_untrusted_rule_is_shown` |
| A trusted value decides | `test_a_trusted_value_decides` |
| Untrusted data beside trusted data still can't decide | `test_untrusted_data_beside_trusted_data_still_cant_decide` |
| Once every `closes_when` milestone is reached, no rule acts, even on that moment, and each firing says why | `test_rules_stop_with_the_close`, `test_the_guides_rule_stopped_by_the_close_is_shown` |
| A rule reaching the last `closes_when` milestone closes the case | `test_a_rule_reaching_closes_when_closes_the_case` |
| A failed rule holds the close | `test_a_failed_rule_holds_the_close` |
| A failed rule retried while it holds the close decides nothing, and the case closes | `test_a_failed_rule_retried_while_it_holds_the_close_lets_the_case_close` |
| A person's close cancels a failed rule | `test_a_person_closing_the_case_cancels_a_failed_rule` |
| While a failed step holds the close, no rule acts | `test_rules_dont_act_while_a_failed_step_holds_the_close` |
| A rule on a milestone nothing reaches never fires (`NEVER_FIRES`) | `test_a_rule_on_a_milestone_nothing_reaches_never_fires` |
| A rule on a step that never runs never fires | `test_a_rule_on_a_step_that_never_runs_never_fires` |
| A rule waiting on a rule that never fires never fires | `test_a_rule_waiting_on_a_rule_that_never_fires_never_fires` |
| A rule on reaching the one `closes_when` milestone never acts | `test_a_rule_on_the_last_closes_when_milestone_never_acts`, `test_the_guides_table_of_rule_codes_is_what_validate_case_says` |
| A rule whose condition reads always-untrusted data is refused (`UNTRUSTED_TRIGGER`) | `test_a_rule_reading_untrusted_data_is_refused`, `test_the_guides_table_of_rule_codes_is_what_validate_case_says` |
| A rule reading trusted data is not refused | `test_a_rule_reading_trusted_data_is_not_refused` |
| A milestone only a rule reaches is reachable: not `NEVER_RUNS`, `CLOSE_UNREACHABLE` nor `UNREACHABLE_MILESTONE` | `test_a_milestone_only_a_rule_reaches_is_reachable` |
| A rule can break a deadlock | `test_a_rule_breaks_a_deadlock` |
| A milestone nothing reaches says "no step or rule reaches" | `test_a_milestone_nothing_reaches_says_no_step_or_rule_reaches_it` |
| A milestone a rule may reach proves nothing about values (`MAY_BE_UNSET`) | `test_a_milestone_a_rule_may_reach_proves_nothing_about_values` (seen failing without the fix) |
| A `SET_AFTER` a rule could undo becomes a warning | `test_a_rule_may_let_a_writer_run_first_so_set_after_becomes_a_warning` (seen failing without the fix) |
| A rule's condition is type-checked (`EXPRESSION_INVALID`) | `test_a_rules_condition_is_type_checked` |
| A rule's condition reads an outcome, for `OUTCOME_UNREAD` | `test_a_rule_reading_an_outcome_tells_it_apart` |
| A rule on the opening reading what only a person sets fails every time (`SET_AFTER`) | `test_a_rule_reading_on_the_opening_what_only_a_person_sets_fails_every_time` |
| A rule reading what may not be set yet is warned (`MAY_BE_UNSET`) | `test_a_rule_reading_what_may_not_be_set_yet_is_warned` |
| A rule reading what its moment ensures is not warned | `test_a_rule_reading_what_its_moment_ensures_is_not_warned` |
| A step that a rule on the opening admits keeps the case open: no `CLOSES_AT_OPENING`, and the run waits for it | `test_a_step_a_rule_on_the_opening_admits_keeps_the_case_open` |
| A rule on the opening whose `when` may be false gives no `CLOSES_AT_OPENING` | `test_a_rule_on_the_opening_whose_when_may_be_false_gives_no_issue` |
| A rule on the opening reaching what no starting step requires leaves `CLOSES_AT_OPENING` as it was | `test_a_rule_on_the_opening_admitting_nothing_leaves_closes_at_opening` |
| A rule on the opening with its own issue gets no `CLOSES_AT_OPENING` beside it | `test_a_rule_on_the_opening_with_its_own_error_gets_no_closes_at_opening_beside_it` |
| The runtime refuses what validation refuses, on nothing validation did | `test_untrusted_data_cant_decide` (`UNTRUSTED_TRIGGER` reaches nothing), `test_rules_stop_with_the_close` (`NEVER_FIRES` is not applied), `test_a_rule_that_cant_be_read_needs_attention` (`SET_AFTER` needs attention): each calls only `run_case` |
| A rule's firings cross continue-as-new, and replay decides the same | `test_rule_firings_cross_continue_as_new_and_replay` (`tests/test_temporal_case.py`, seen failing with firings left out), `test_a_carried_state_reads_back_as_it_was` (`tests/test_temporal_case.py`) |
| No rule line or rule issue quotes a value from a case file | `test_no_rule_line_or_issue_quotes_a_value_from_the_case_file` |
| The guide's rule runs as shown | `test_the_guides_rule_runs_as_shown` |

---

## 11b. Rules that start steps

### What this part is for

A step starts by itself at most once; any other run needs a person to propose it (layer 8). That
says "a person sends the review back", but not "when the check sends the review back, ask for it
again": someone would have to remember to propose it. 11b lets a rule's `then` **start** steps:
the engine proposes a run, as a person does, and admission decides. And it builds the half of
design question 17 that 11a decided: a condition that lets a step start counts for its inputs'
policies (brief, D38).

The sketch, on the refund (the cases guide, "Rules that start steps"): a team lead checks each
approved review, and a review sent back is asked again.

```json
"rules": {
  "check_review": {"display": {"title": "Check an approved review"},
                   "on": {"answered": "review"},
                   "when": {"==": [{"var": "review.outcome"}, "approve"]},
                   "then": {"start": ["check"]}},
  "send_back":    {"display": {"title": "Send the review back"},
                   "on": {"answered": "check"},
                   "when": {"==": [{"var": "check.outcome"}, "send_back"]},
                   "then": {"start": ["review"]}}
}
```

`review` is repeatable; `check` is a task for `support-lead` that only the rule starts, whose
`ok` reaches `checked`; `pay` also requires `checked`.

### How the session went

The warm-up first (learning question 32, "tell me"; recorded in the log). The first proposal, all
eleven choices in one message, went to a mentor review before the user answered (six lenses, a
skeptic each; 77 findings kept, none refuted). It changed the proposal in four places: the moment
(a task answered, not any step completing, which let a case loop with no person in it); option a
as a separate check (merged, it loosened a policy); `stop` doing what a close does (it had left
an approval standing); and a cancelled workflow always flagged. It also found three bugs in merged
code, fixed in slice 0. The choices were then agreed in four groups, 2026-10-18, all as
recommended, one of them splitting 11b in two: this part starts steps; 11c stops them.

### Decided in the session

**Starting a step** (doors rows 6, 10, 11):

1. **A fourth moment, a task answered:** `{"answered": "<task>"}` fires each time a run of the task
   is answered, whatever the outcome, and names only a task. 11a set "a step answered" aside
   because a milestone says the same, but a milestone is reached once and `started` fires before
   the answer exists, so a loop could never send work back twice. What brings a loop of rules
   round again is then a person's answer (brief, design question 18). Set aside: `{"completed":
   <step>}` for any step, which let `on completed pay, when declined, start pay` call the provider
   for ever, with no person in between: a retry policy written by a case (brief, D17).
2. **`start` is a proposal through admission** (row 10). `"then": {"start": ["check"]}`, a list of
   step names like `reach`; the engine proposes, and admission decides as for a person: its
   requirements, running or waiting for its approval, repeatable, its `when`, its fresh facts,
   its approval, its inputs; the close as in 11a. A start the engine can't make is never silent:
   - **recorded, nothing runs:** the step's `when` is false; it is running or waiting for its
     approval; it has run and isn't repeatable; its latest run needs attention;
   - **waits:** a fact it needs fresh is stale and can be fetched again: accepted, the fact is
     fetched, then everything is read again on the fresh value (the pending start);
   - **fails, needs attention,** as admission does: its condition can't be read, its contract is
     missing, an input is refused, a stale fact can't be fetched again.
   A person's proposal gets the same waiting start and the same refusal beside a failed run
   (slice 0). A step a rule starts may leave out `proposed_by`, which keeps meaning which people
   may propose it (row 10). Set aside: every refused start needing attention, which would fill the
   operators' queue with ordinary "already running"s.
3. **Who proposed, and who can't approve.** The proposer is the rule's entry (`send_back#1`), never
   a person. Whoever's answer the rule's `when` read can't approve the run it starts, as for a
   step's own `when` (brief, D11, D25). A rule remembers nothing, so the coming run keeps a record
   until it starts or is dropped: the rule's entry, those people, and the untrusted sources the
   `when` read; it crosses continue-as-new. The person whose answer only brought the moment is not
   excluded: the same chain exists through `requires` (Sam proposes `check`, `pay` requires it,
   Sam approves `pay`). Set aside: excluding them for rules only.
4. **Each decision ends** (row 11). A step a rule has started in a decision isn't started again by
   a rule in it, recorded: once 11c's `stop` can end a task's run inside a decision, two rules on
   `started X`, one stopping it and one starting it, would loop. So a decision starts finitely many
   runs: an event brings at most one `answered` moment, a milestone is reached once, and each step
   gets at most one start from a rule, besides admission's and the event's own. Set aside:
   refusing `stop` and `start` of one step anywhere in a definition, which shuts a later "restart".

**Untrusted data choosing what starts** (design question 17, option a; brief, D38):

5. **A separate check, and only untrusted sources count.** If the step's `when`, or the `when` of
   the rule that started it, read an untrusted (or unrecognised) source, each input whose policy
   refuses that source is refused, and the run fails naming the condition's field and source,
   never the value. The input's own sources are checked as today. Never merged: merged, a literal
   input would be credited with the condition's sources, and the guide's `NO_SOURCES` example
   passed (the mentor's run). A plan step carries its condition's untrusted sources beside its
   fields, never inside them. Set aside: counting every source the condition read, which refuses,
   every time, an input taking a value from one system on a step whose `when` reads a person's
   answer.
6. **The case-data guide's fresh refund moves to `orders.lookup@2`,** which declares `status` from
   `system:orders`: under option a, `@1`'s undeclared status would refuse `pay`'s inputs every
   time. `@1` stays registered, and one test keeps showing that it refuses `pay`. The development
   catalog gets no fake for `@2`: each test that runs it says what it returns, so an override left
   on `@1` fails loudly instead of passing on a default.
7. **A plan's own transitions are left open,** recorded in D39, under design question 17, in the
   plans guide and in the doors note ("Found in 11b").
8. **A field a condition names that isn't set yet counts what any of its writers could give,**
   read from the definition with the real opener, as validation's sources are (fail closed). This
   corrects 11a's runtime (slice 0), where a rule on the opening with `!exists notes`, `notes` from
   `untrusted:customer`, reached its milestone though validation said it never acts.
9. **An approval's `when` that read untrusted data asks anyway,** after being read as today (one
   that can't be read stops the step: 11a's slice 3, "not acting is checked once the condition
   could be read"); the history says why. `NEVER_REFRESHED` counts such an approval as always
   needed. The forms test's order stays: the approval is asked, then the refused input fails.
10. **Where the influence ends:** at the step the condition lets start; a rule on its start, or a
    milestone its run reaches, may carry it further. D39 and the guide say so, and that a person
    (an approval, a task) is the tool there; 11g's teaching warning will point at it.

**Validation stays a proof** (brief, D34):

11. **One answer to "who can start this step"**: it starts by itself, a person with a registered
    role proposes it, or a rule that can fire starts it; used by `can_happen`, `NEVER_RUNS`,
    `CLOSES_AT_OPENING` and the role checks (a misspelt `proposed_by` on a step a rule starts is
    still reported).
12. **`NEVER_STARTS`** (error, at `rules.<name>.then.start`): a start refused every time the rule
    fires, claimed only where proven: the rule fires on the opening and the step requires what the
    opening can't reach, or the step requires what comes only after its own run. A step all of
    whose starts are refused never runs (`NEVER_RUNS`); a step started only by a rule on its own
    moment gets one issue, naming the circle, and no `NEVER_FIRES` beside it.
13. **`INPUT_POLICY` counts conditions:** at the step's input for its own `when`; at
    `rules.<name>.then.start` for the rule's, through the same two openers (`OPENER_DECIDES` when
    only one is refused), worded as a failure ("pay fails on its inputs every time this rule starts
    it"); nothing at the rule when the step's input already has the issue.
14. **`CLOSES_AT_OPENING`** counts a start by a rule on the opening (or one following it) when every
    requirement of the step is among what the opening may reach; its message adds "or start one
    from a rule on the opening".
15. **Unknown moments fail closed:** the five places that read a moment (`rules.said`,
    `reach.moment_can_come`, the rule warnings, `never_fires`, the definition's name check) name
    every moment and refuse one they don't know, with a negative test.
16. **`{"answered": "check"}` counts as waiting for `check`** for `MAY_BE_UNSET` and `SET_AFTER`.
17. **A loop of starts:** `NEVER_CLOSES` (error) only when nothing could end it (no `when` on its
    rules or steps, every step repeatable without an approval, no rule stopping it, entered in
    every case, no reachable `closes_when`, no close reason with a registered role);
    `CLOSED_ONLY_BY_A_PERSON` (warning) when a person or `closes_when` still can (brief, D10: "a
    step that can always be restarted"). A later run counter bounds the loop, and the issue goes.
18. **`NEVER_CLOSES` says what it proves:** a forget request closes any case whose definition
    allows it (brief, D32), so the message says nothing but a forget request could close it.
19. **What isn't claimed** is written down: a writer started only by rules on the reader's own
    moment gives `MAY_BE_UNSET`, never `SET_AFTER`; a cycle through `started` may or may not loop,
    depending on the order of events, and gets nothing.

**And:**

20. **The split:** 11b starts steps; 11c stops them (agreed below); events, time, reading rules and
    patterns become 11d–11g.
21. **D39,** drafted with this note; D38 keeps its text.

### Agreed for 11c, rules that stop steps

Decided in this session, built in 11c (its own section, Promises and tutor review):

- **`stop` ends the run going on now; it doesn't keep the step from starting later** (row 3). A
  list of step names now; an item may become `{"step": …, "<option>": …}` later, a plain name
  keeping its meaning. A name that isn't a step is refused (row 1); so is one name in both `stop`
  and `start` of a rule; inside one `then`: stop, then reach, then start. Stopping a step that
  isn't repeatable means it never runs again; "never pay a high-risk customer" belongs in `pay`'s
  `when`.
- **What a close does, to one step.** An open approval is withdrawn and a given one lapses, and the
  coming run is recorded `cancelled`; an open task is cancelled, saying why; a running activity
  finishes, its run kept `running` with a "stop requested by …" marker, then ends `done`, its
  outputs landing and its milestones reached, the case flagged (`pay#1 completed after stop_pay#1
  asked to stop it`); one that fails after the stop needs attention; a plan gets D28's stop signal,
  with a reason whose default keeps today's text; a failed run is never stopped. A run really
  stopped ends `cancelled`, neither done nor failed (row 5); a stopped refresh counts for nothing,
  and the step that needed it needs attention.
- **One place stops every running child** (rows 2, 7, 8), used by closing and `stop`. A workflow
  step is stopped by Temporal's cancellation if its contract declares `cancellable: true`, written
  as three clauses its history shows (after a request it schedules nothing new; it ends only once
  all it started has ended; it ends cancelled only if nothing it started completed after the
  request), checked by the contract test; every stopped workflow that ends cancelled is flagged;
  the driver waits for it (`WAIT_CANCELLATION_COMPLETED`); the reason names only the entry and the
  rule; an undeclared `cancellable` leaves contract hashes as they are; closing cancels cancellable
  workflow steps too. A workflow that doesn't declare it finishes, like an activity.
- **On Temporal:** a history recorded under 11b's driver replays under 11c's; a child is never
  cancelled twice; a run with a stop requested hasn't ended, and a stopped run's timers end with it
  (row 19, for 11e).

### Where the code goes

- `case/definition.py`: the `answered` moment (a task); `then.start` (steps); a step a rule starts
  needs no `proposed_by`.
- `case/rules.py`: `start`, its record, the per-decision guard; the trust check on what a
  condition reads, unset fields included.
- `case/runtime.py`, `case/admission.py`: one gate for a person's proposal and a rule's start (the
  pending start, refusal beside a failed run); the `answered` moment; the condition check before
  scheduling and starting a plan.
- `case/state.py`: the pending start and its record; the starts made by rules in the decision
  (always empty between events, like `moments`).
- `case/approvals.py`, `case/answers.py`: an approval asked anyway; exclusions from the record.
- `core/before_activity.py`: the condition's untrusted sources, checked apart from the inputs'.
- A function of the definition giving what a field's writers could stamp, shared by the runtime and
  validation (`flow.case_sources` today), so neither depends on the other having run.
- `case/reach.py`, `case/validate.py`, `case/warnings.py`, `case/registered.py`, `case/flow.py`:
  choices 11–19.
- `temporal/carried.py`: the pending start crosses continue-as-new.
- `testing.py`, `contracts.lock.json`: `orders.lookup@2`.
- The guides: cases ("Rules that start steps", the refusals, the codes), case data (the fresh
  refund, a proposal waiting), activities (`@2`), plans (the open half).

### Not in 11b

- Stopping steps, `cancellable` workflows and the one place that stops children (11c); events and
  `set` (11d); timers (11e); the renderer and `simulate` (11f); patterns and warnings (11g).
- Option a inside a plan's own transitions (left open).
- No new dependency.

### Seams the tests use

- `parse_case(data)`: `CaseInvalid` for an `answered` naming what isn't a task, a `start` naming
  what isn't a step.
- `run_case(...)`: `history`, `needs_attention`, `waiting_for`, `closed`, `reached`; `propose`,
  `retry`, answers, `later`.
- `validate_case(case, catalog)`: the issues above.
- The Temporal test server: a pending start and a rule's record cross continue-as-new and replay;
  a history recorded before 11b, committed as a fixture, replays under the new worker.
- The guides' examples, run as written.

### Slices, in order

Each starts with its negative test, seen failing for the right reason.

0. **Three corrections, each in its own commit,** after recording the replay fixture under today's
   code:
   - 0a. A proposal waits for its fresh facts. Negative: a proposed `pay` on a 3-day-old status is
     not scheduled before `check_order#2`.
   - 0b. Nothing starts beside a failed run. Negative: proposing `check_order` while
     `check_order#1` needs attention is refused, and the operator's retry is scheduled.
   - 0c. An unset untrusted field counts. Negative: the `!exists notes` rule reaches nothing.
1. **The shape.** Negative: `answered` naming a step that isn't a task, `start` naming what isn't a
   step, are refused when read; a step a rule starts reads without `proposed_by`.
2. **Starting.** Negative: a rule's start of a step whose `when` is false runs nothing and says so.
   Then each kind of refused start, the rework loop, the waiting start, the failing start, the
   per-decision guard, the proposer and the exclusions.
3. **Option a at runtime.** Negative: the welcome letter on a model's notes fails, naming the
   condition's field. Then the rule's `when`, only untrusted sources counting, a plan step, an
   approval asked anyway, an unset field in a condition, `orders.lookup@2` and the fresh refund.
4. **Validation.** Negative: `NEVER_STARTS`. Then choices 11–19, each shown with a run.
5. **On Temporal.** The pending start and the record cross continue-as-new and replay; the fixture
   replays.
6. **The guide and the promises.**

### Promises

Drafted before building, from the choices above; each row's test is named here first and checked
against the file before the pull request. Every test is in `tests/test_rules.py` unless said
otherwise.

| Promise | Test that would fail |
|---|---|
| A proposal of a step whose fact is stale and can be fetched again waits for the refresh, then reads everything again | `test_a_proposal_waits_for_its_fresh_facts` (`tests/test_fresh_facts.py`) |
| Nothing starts beside a failed run: a person's proposal is refused, and the operator's retry is scheduled | `test_nothing_starts_beside_a_failed_run` (`tests/test_case.py`) |
| A rule's condition naming an unset untrusted field doesn't act | `test_an_unset_untrusted_field_still_cant_decide` |
| `answered` names only a task, and `start` only a step | `test_answered_names_a_task_and_start_a_step` |
| A step a rule starts needs no `proposed_by`, and nobody may propose it | `test_a_step_only_a_rule_starts_is_proposed_by_nobody` |
| `answered` fires on each answer, whatever the outcome | `test_answered_fires_on_each_answer` |
| A rule's start whose `when` is false runs nothing, and says so | `test_a_start_whose_condition_is_false_runs_nothing` |
| A start of a running step, one waiting for its approval, or one that has run and isn't repeatable is recorded, and nothing runs | `test_a_refused_start_is_recorded` |
| A rule's start beside a failed run is refused | `test_a_rule_starts_nothing_beside_a_failed_run` |
| A rule's start on a stale fact waits for the refresh | `test_a_rules_start_waits_for_its_fresh_facts` |
| A rule's start whose condition can't be read, or whose input is refused, needs attention | `test_a_start_that_cant_be_made_needs_attention` |
| The rework loop runs as the guide shows | `test_the_guides_rework_loop_runs_as_shown` |
| A step a rule started in a decision isn't started again by a rule in it | `test_a_rule_starts_a_step_once_per_decision` |
| The proposer is the rule's entry, and whoever's answer its `when` read can't approve the run | `test_whoever_a_rules_condition_read_cant_approve_what_it_started` |
| The person whose answer only brought the moment may approve | `test_the_answer_that_brought_the_moment_doesnt_exclude` |
| What the rule read is kept with the run: a value changed in between still excludes and still taints | `test_a_rules_record_outlives_the_case_file_changing` |
| A step's untrusted `when` refuses an input whose policy refuses it, naming the field and source, never the value | `test_an_untrusted_condition_cant_choose_what_is_sent` |
| A rule's untrusted `when` refuses the started step's input the same way | `test_a_rules_untrusted_condition_cant_choose_what_is_sent` |
| Only untrusted sources count: a `when` reading a person's answer sends a value from one system | `test_a_trusted_condition_changes_nothing` |
| A literal input is never credited with a condition's sources | `test_a_condition_never_vouches_for_a_literal` |
| A plan step carries its condition's untrusted sources beside its fields | `test_a_plan_step_carries_its_conditions_sources` (`tests/test_plan_step.py`) |
| An approval whose `when` read untrusted data is asked whatever it gave, and says why; one that can't be read stops the step | `test_an_untrusted_approval_condition_asks_anyway` |
| `orders.lookup@1`'s undeclared status refuses the fresh refund's `pay`; `@2` runs it | `test_an_undeclared_status_cant_choose_a_payment` (`tests/test_fresh_facts.py`) |
| Who can start a step counts rules: no `NEVER_RUNS` for a step a rule may start, and a misspelt `proposed_by` is still reported | `test_a_step_a_rule_may_start_can_run` (`tests/test_case_validation.py`) |
| A start refused every time is `NEVER_STARTS`, and a step whose every start is refused never runs | `test_a_start_refused_every_time_is_never_starts` |
| A step started only by a rule on its own moment gets one issue | `test_a_step_started_only_on_its_own_moment_gets_one_issue` |
| An untrusted condition gives `INPUT_POLICY` at the step and at the rule, through both openers | `test_input_policy_counts_conditions` (`tests/test_case_validation.py`) |
| A rule on the opening that starts a step keeps the case from closing at once: no `CLOSES_AT_OPENING`, and the run waits | `test_a_step_a_rule_on_the_opening_starts_keeps_the_case_open` |
| A moment a check doesn't know is refused, never read as the opening | `test_an_unknown_moment_fails_closed` |
| `answered` counts as waiting for its task for `MAY_BE_UNSET` and `SET_AFTER` | `test_answered_waits_for_its_task` |
| A loop nothing ends is `NEVER_CLOSES`; one a person can end is `CLOSED_ONLY_BY_A_PERSON` | `test_a_loop_of_starts_never_closes`, `test_a_loop_a_person_can_end_is_warned` |
| `NEVER_CLOSES` says only a forget request could close the case | `test_the_guides_table_is_what_validate_case_says` (`tests/test_case_validation.py`) |
| An approval whose `when` always reads untrusted data is `NEVER_REFRESHED`'s "always needed" | `test_an_untrusted_approval_is_always_needed` (`tests/test_case_validation.py`) |
| A pending start and a rule's record cross continue-as-new, and replay decides the same | `test_a_pending_start_crosses_continue_as_new` (`tests/test_temporal_case.py`) |
| A history recorded before 11b replays under 11b's worker | `test_a_history_from_before_11b_replays` (`tests/test_temporal_case.py`) |
| The runtime refuses what validation refuses, on nothing validation did | `test_an_untrusted_condition_cant_choose_what_is_sent`, `test_a_refused_start_is_recorded`: each calls only `run_case` |
| No line or issue of 11b quotes a value from a case file | `test_no_start_line_or_issue_quotes_a_value` |
| The guides' refusals and codes are what the engine says | `test_the_guides_refusals_are_what_the_engine_says` (`tests/test_case.py`), `test_the_guides_table_of_rule_codes_is_what_validate_case_says` |
