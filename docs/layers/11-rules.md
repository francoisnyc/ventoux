# Layer 11: rules

Status: research done, 2026-10-16 (`docs/layers/11-research.md`, Flowable's CMMN engine at
`f6017e3`); the warm-up skipped at the user's request, 2026-10-17 (learning question 32 stays
open, for the next layer); the split and 11a's eleven choices agreed in the session, 2026-10-17
(all as proposed; design question 17, option a); D38 and the cases guide's "Rules" drafted the same
day; 11a built, slices 0–7; Promises checked against the tests, 2026-10-17; the tutor review's
fix built test-first, and the Promises table names every test, the same day. 11b: the warm-up
(learning question 32) answered "tell me", 2026-10-18; the mentor's review of the first proposal;
the choices agreed in four groups the same day, all as recommended, one of them splitting 11b in
two (see "The split"); D39, the guides' 11b part and a draft Promises table written the same day,
before building, then reviewed (fidelity, truth, proofs, style), which left three questions open
for the user, answered "Go" the same day, taken as the recommendations (see 11b, "Decided after the
review"); 11b built, slices 0–6, and its Promises table checked against the tests, the same day;
then three code reviews, whose fixes were built test-first (see 11b, "From the code review", "From
the second review" and "From the third review"), with two questions left for the user; the tutor
review answered both, and its three items were built test-first the same day (see 11b, "From the
tutor review"). 11c: the warm-up (learning question 39's follow-up) answered "tell me", 2026-10-18;
the four points 11b's session left undiscussed, and 11c's remaining choices, put with a
recommendation each and answered "go with all recommendations" the same day; D40, the guides'
11c part and a draft Promises table written the same day, before building.

## What this layer is for

Until now a case reacts in one way only: after every event, admission asks each step "may you start
now?" (layer 8). That covers "pay once the review approves", not "if nobody has assessed the claim
in five days, escalate", "when the customer cancels, stop", or "once the check is done, mark the
customer high risk if the score is over 70". Layer 11 adds the **rule**: *when* something happens,
*if* a condition holds, *then* act on the case (brief, Simplifications, "one kind of rule"; D7).

User-facing description: `docs/guides/cases.md`, "Rules" (11a's part written 2026-10-17, before
building: the curriculum's "document first"); each later part adds to it. Decisions: brief D38
(11a), D39 (11b), D40 (11c).

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
| **11b: rules that start steps** | `then: start` (the engine proposes, through admission: the rework loop), and the moment a task is answered; the half of design question 17 that steers which step starts, built; validation: a step a rule starts can run; a rule that restarts a step for ever | `NEVER_STARTS`, `NEVER_CLOSES` extended, `LOOPS_UNTIL_CLOSED` |
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
| `sla`, `reminder`, `four_eyes`, the renderer, teaching warnings, `ventoux simulate` | 11g, 11g, 11g, 11f, 11g, 11f (as in the table) |

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
  and `started` fires only for a new one. *(Amended in 11b, 2026-10-18: a run that failed before
  it started fires `started` when its retry runs it, its first start; see 11b, "From the tutor
  review", and D38's amendment.)*
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
says "a person sends the review back", but not "when the team lead sends the review back, ask
for it again": someone would have to remember to propose it. 11b lets a rule's `then` **start**
steps: the engine proposes a run, as a person does, and admission decides. And it builds the half
of design question 17 that 11a decided: a condition that lets a step start counts for its inputs'
policies (brief, D38, as D39 narrows it).

The sketch, on the refund (the cases guide, "Rules that start steps"): a team lead checks each
approved review, and a review sent back is asked again.

```json
"rules": {
  "check_review": {"display": {"title": "Have an approved review checked"},
                   "on": {"answered": "review"},
                   "when": {"==": [{"var": "review.outcome"}, "approve"]},
                   "then": {"start": ["lead_check"]}},
  "send_back":    {"display": {"title": "Send the review back"},
                   "on": {"answered": "lead_check"},
                   "when": {"==": [{"var": "lead_check.outcome"}, "send_back"]},
                   "then": {"start": ["review"]}}
}
```

`review` and `lead_check` are repeatable; `lead_check` is a task for `support-lead` that only a
rule starts, whose `ok` reaches `lead_checked`; `pay` also requires `lead_checked`.

### How the session went

The warm-up first (learning question 32, "tell me"; recorded in the log), then a question: would a
person have to write rules like these? No: they meet patterns through the builder, which expand
into raw rules that `ventoux check` and the case map show (brief, D1, D7; layer 11g). The first
proposal, all its choices in one message, went to a mentor review before the user answered. It
changed four things: the moment (a task answered, not any step completing, which let a case loop
with no person in it); option a as a separate check (merged, it loosened a policy); `stop` doing
what a close does (it had left an approval standing); and a cancelled workflow always flagged. It
also found three bugs in merged code, fixed in slice 0. The choices were then agreed in four
groups, 2026-10-18, all as recommended, one of them splitting 11b in two: this part starts steps;
11c stops them. A review of the drafts (fidelity, truth, proofs, style) then found three
questions that needed the user ("Decided after the review", below).

Below, a choice the user agreed is unmarked; *(assistant's call)* marks what the assistant stated
in the session without putting it as a question; *(added while drafting)* marks what came after
the session, for the user to confirm with this note.

### Decided in the session

**Starting a step** (doors rows 6, 10, 11):

1. **A fourth moment, a task answered:** `{"answered": "<task>"}` fires each time a run of the task
   is answered, whatever the outcome, and names only a task. 11a set "a step answered" aside
   because a milestone says the same, but a milestone is reached once and `started` fires before
   the answer exists, so a loop could never send work back twice. Set aside: `{"completed":
   <step>}` for any step, with a runtime bound on how often rules start a step: `on completed
   pay, when declined, start pay` would still call the provider again on each decline, up to the
   bound, with no person in between: a retry policy written by a case (brief, D17). With a
   rule's start never waiting ("Decided after the review", 1), every loop of rules that crosses
   decisions comes round through a person: an answer, a proposal or a retry.
2. **`start` is a proposal through admission** (row 10). `"then": {"start": ["lead_check"]}`, a
   list of step names like `reach`; the engine proposes, and admission decides as for a person:
   its requirements, running or waiting for its approval, repeatable, its `when`, its fresh facts,
   its approval, its inputs; the close as in 11a. A start the engine can't make is never silent:
   - **recorded, nothing runs:** its `when` is false; it is running or waiting for its approval;
     it has run and isn't repeatable; its latest run needs attention; and *(added while
     drafting)*, following from "through admission": its requirements aren't met, or a start of
     it already waits for a fact fetched again;
   - **waits** (a person's proposal only, once decided after the review): a fact it needs fresh is
     stale and can be fetched again: accepted, the fact is fetched, then everything is read again
     on the fresh value (the waiting start);
   - **fails, needs attention,** as admission does: its condition can't be read, its contract is
     missing, an input is refused, a stale fact can't be fetched again.

   A person's proposal gets the same waiting start and the same refusal beside a failed run
   (slice 0). *Added while drafting:* a person's proposal of a step whose start already waits is
   refused, so its first proposer still can't approve the run (brief, D25). *Decided after the
   review* ("Decided after the review", 1 and 2): a rule's start never waits, so for a rule the
   "waits" kind becomes "fails, needs attention" (an operator's retry fetches the fact again); and
   a person's proposal on a stale fact that can't be fetched again is refused, saying why.

   And the one loosening: a step a rule starts may leave out `proposed_by`, relaxing layer 8's rule
   that a step that doesn't start by itself, or is repeatable, names it (its reason, that nothing
   else could start it, no longer holds); `proposed_by` keeps meaning which people may propose it,
   and with none, nobody may (row 10). Set aside: every refused start needing attention, which
   would fill the operators' queue with ordinary "already running"s.
3. **Who proposed, and who can't approve.** The proposer is the rule's entry (`send_back#1`), never
   a person. Whoever's answer the rule's `when` read can't approve the run it starts, as for a
   step's own `when` (brief, D11, D25). A rule remembers nothing, so the coming run keeps a record
   until it starts or is dropped: the rule's entry, those people, and the untrusted sources the
   `when` read; it crosses continue-as-new. The person whose answer only brought the moment is not
   excluded: the same chain exists through `requires` (Sam proposes `check_order`, `pay` requires
   it, and Sam may still approve `pay`). Set aside: excluding them for rules only.
4. **Each decision ends** (row 11). A step a rule has started in a decision isn't started again by
   a rule in it, recorded: once 11c's `stop` can end a task's run inside a decision, two rules on
   `started X`, one stopping it and one starting it, would loop. *(Added while drafting: the
   bounds, and where the guard sits.)* A decision then starts finitely many runs: the event brings
   at most one `answered` moment and one run of its own; each milestone is reached once; each step
   starts by itself at most once; each stale fact is fetched again at most once until its refresh
   lands (brief, D33); each step has at most one waiting start (a person's), and one start by a
   rule. The guard is read before admission's other refusals, so its line shows even for a step
   already running. Set aside: refusing `stop` and `start` of one step anywhere in a definition,
   which shuts a later "restart".

**Untrusted data choosing what starts** (design question 17, option a):

5. **A separate check, and only untrusted sources count.** If the step's `when`, or the `when` of
   the rule that started it, read an untrusted (or unrecognised) source, each input whose policy
   refuses that source is refused, and the run fails naming the condition's field and source,
   never the value. The input's own sources are checked as today. This narrows D38's "counts as
   read by every input", which, taken as written, merges the sources: merged, an input given only
   a literal would be credited with the condition's sources, so the plan field that `NO_SOURCES`
   refuses today would pass (the mentor's run). A plan step carries its condition's untrusted
   sources beside its fields, never inside them. Set aside: counting every source the condition
   read, which refuses, every time, an input taking a value from one system on a step whose
   `when` reads a person's answer.
6. **The case-data guide's fresh refund moves to `orders.lookup@2`,** which declares `status` from
   `system:orders`: under option a, `@1`'s undeclared status would refuse `pay`'s inputs every
   time. `@1` stays registered, and one test keeps showing that it refuses `pay`. *(Added while
   drafting:)* the development catalog gets no fake for `@2`: each test that runs it says what it
   returns, so an override left on `@1` fails loudly instead of passing on a default.
7. **A plan's own transitions are left open,** recorded in D39, under design question 17, in the
   plans guide and as row 31 of the doors note.
8. **A field a condition names that isn't set yet counts what any of its writers could give,**
   read from the definition with the real opener, as validation's sources are (fail closed). This
   corrects 11a's runtime (slice 0), where a rule on the opening with `!exists notes`, `notes` from
   `untrusted:customer`, reached its milestone though validation said it never acts.
9. **An approval's `when` that read untrusted data asks anyway** *(assistant's call)*, after being
   read as today: one that can't be read stops the step, as 11a's slice 3 has it ("not acting is
   checked before acting, whatever the condition gave": the trust check runs once the condition
   could be read). The history says why. `test_a_forms_values_land_in_the_case_file`
   (`tests/test_case.py`) changes with it: its approval is now asked, and the refused input fails
   once it is given; admission's order (approval, then inputs) stays. *(Added while drafting:)*
   `NEVER_REFRESHED` counts such an approval as always needed.
10. **Where the influence ends** *(assistant's call)*: at the step the condition lets start; a rule
    on its start, or a milestone its run reaches, may carry it further. D39 and the guide say so,
    and that a person (an approval, a task) is the tool there; 11g's teaching warning will point
    at it *(added while drafting)*. *(Added while drafting:)* a rule that reaches a milestone and
    reads untrusted data doesn't act at all, its starts included (D38: "it doesn't act").

**Validation stays a proof** (brief, D34; choices 11–16 are the assistant's call, stated in the
session):

11. **One answer to "who can start this step"**: it starts by itself, a person with a registered
    role proposes it, or a rule that can fire starts it; used by `can_happen`, `NEVER_RUNS`,
    `CLOSES_AT_OPENING` and the role checks (a misspelt `proposed_by` on a step a rule starts is
    still reported).
12. **`NEVER_STARTS`** (error, at `rules.<name>.then.start`): a start refused every time the rule
    fires, claimed only where proven: the rule fires on the opening, its condition can't fail
    there (a failed firing is retried later, on the case file as it is then), and the step
    requires what the opening can't reach; or the step requires what comes only after its own
    run. A step all of whose starts are refused never runs (`NEVER_RUNS`). *(Added while
    drafting:)* a step started only by a rule on its own moment gets one issue, naming the circle,
    and no `NEVER_FIRES` beside it.
13. **`INPUT_POLICY` counts conditions:** at the step's input for its own `when`; at
    `rules.<name>.then.start` for the rule's, worded as a failure ("pay fails on its inputs every
    time this rule starts it"); nothing at the rule when the step's input already has the issue.
    Who opens the case can't change it: the opener's source is trusted either way, so a condition
    never gives `OPENER_DECIDES`.
14. **`CLOSES_AT_OPENING`** counts a start by a rule on the opening (or one following it) when every
    requirement of the step is among what the opening may reach; its message adds "start one from
    a rule on the opening".
15. **Unknown moments fail closed:** the places that read a moment (`rules.said`,
    `reach.moment_can_come`, the rule warnings, `never_fires`, the definition's name check) name
    every moment and refuse one they don't know, with a negative test.
16. **`{"answered": "lead_check"}` counts as waiting for `lead_check`** for `MAY_BE_UNSET` and
    `SET_AFTER`.
17. **A loop of starts:** `NEVER_CLOSES` (error) only when nothing in the case can end it, and
    `LOOPS_UNTIL_CLOSED` (warning) when only a close reason or `closes_when` can (brief, D10: "a
    step that can always be restarted"). *(Added while drafting, from the review's runs:)* "nothing
    can end it" means: a loop that comes round on each answer, entered in every case, with no
    `when` on its rules or steps, every requirement of its steps met whenever a rule of the loop
    starts them (a refused start ends a loop), every step repeatable without an approval, and no
    rule stopping it. A later run counter bounds the loop, and the issue goes (the doors note, row
    11). The warning's name is the assistant's (the session named none).
18. **`NEVER_CLOSES` says what it proves:** a forget request closes any case whose definition
    allows it (brief, D32), so the message says nothing but a forget request could close it.
    *(Added while drafting:)* when its definition says `forgetting: never`, or no role that forgets
    is registered, it says nothing could.
19. **What isn't claimed** is written down *(added while drafting)*: a writer started only by rules
    on the reader's own moment gives `MAY_BE_UNSET`, never `SET_AFTER`; a cycle through `started`
    gets nothing: it can't loop by itself, since a rule's start never waits, so each of its rounds
    begins with a person's event.

**And:**

20. **The split:** 11b starts steps; 11c stops them (below); events, time, reading rules and
    patterns become 11d–11g.
21. **D39,** drafted with this note; D38 keeps its text, and D39 narrows it.

### Decided after the review

The review of the drafts found three questions only the user could answer. Put to the user with a
recommendation each, they were answered "Go", 2026-10-18, taken as the three recommendations:

1. **A rule's start on a stale fact fails and needs attention, even if the fact could be fetched
   again; a person's proposal still waits.** As first agreed, a rule's start waited for the
   refresh. But a refresh lands with no person in it, and the waiting start is then taken up: its
   run's `started` fires rules that may start steps again. With reads slower than a `max_age`, two
   rules on `started` could alternate for ever, each round waiting on a refresh, nobody in
   between: the loop choice 1 set aside. Now an operator's retry fetches the fact again, as a
   retry does today. Set aside: recording it with nothing run, which can quietly lose a start; and
   waiting with a runtime bound.
2. **A person's proposal on a stale fact that can't be fetched again is refused,** saying why (from
   a person, the opening, a write, a workflow, a plan), as a proposal whose condition can't be read
   is refused today: the person is there to read it, and nothing changes. Set aside: accepting it,
   and failing the run.
3. **A fourth bug, fixed in slice 0d:** a person's proposal whose input is refused, whose contract
   is missing, or whose high-risk step has no approval raised out of `decide` instead of failing
   the step: in memory `run_case` raised; on Temporal the case's workflow task failed, the report
   query timed out, and the case stopped deciding. Now the run fails and the case needs attention,
   as when the step starts by itself. Set aside: its own pull request.

### Agreed for 11c, rules that stop steps

Built in 11c, with its own section, Promises and tutor review. What the session settled:

- **Agreed (group 2, A–C):** `stop` ends the run going on now and doesn't keep the step from
  starting later; a repeatable step may be proposed or started again (row 3); a list of step names
  now, an item may become `{"step": …, "<option>": …}` later, a plain name keeping its meaning. A
  payment already running when the stop comes finishes, and the case records it as done (its
  outputs land, its milestones are reached) and flags it for a person. A workflow step is stopped
  by Temporal's cancellation only when its contract declares `cancellable: true`, the team's
  promise, checked by a test; otherwise it runs to its end, like an activity; one that ends
  cancelled after a stop is flagged for a person.
- **Proposed in that group, not objected to:** an open approval is withdrawn and a given one
  lapses, the coming run recorded `cancelled`; an open task is cancelled, saying why; one place
  stops every running child, used by closing and `stop` (rows 2, 7, 8); `cancellable` written as
  three clauses its history shows (after a request it schedules nothing new; it ends only once all
  it started has ended; it ends cancelled only if nothing it started completed after the request);
  `cancellable` left out of a contract's hash when false, declared or not, so existing hashes
  don't change; closing cancels cancellable workflow steps too; a history recorded under 11b's
  driver replays under 11c's; a child is never cancelled twice; a stopped refresh counts for
  nothing; a failed run is never stopped; `stop` refuses a name that isn't a step (row 1); a run
  really stopped ends `cancelled`, neither done nor failed (row 5).
- **Temporal details, left to the assistant in the session:** the driver waits for a cancelled
  child (`WAIT_CANCELLATION_COMPLETED`); a running activity keeps its run `running`, marked "stop
  requested by …", until it ends; a plan's stop signal takes a reason whose default keeps today's
  text, so old histories replay; a cancellation's reason names only the entry and the rule; a run
  with a stop requested hasn't ended, and a stopped run's timers end with it (row 19, for 11e).
- **Not discussed, to put to the user in 11c's session:** one name in both `stop` and `start` of a
  rule refused; inside one `then`, stop, then reach, then start; the step that needed a stopped
  refresh needing attention; one that fails after the stop needing attention.

### Where the code goes

- `case/definition.py`: the `answered` moment (a task); `then.start` (steps); a step a rule starts
  needs no `proposed_by`.
- `case/rules.py`: `start`, its record, the per-decision guard; the trust check on what a
  condition reads, unset fields included.
- `case/runtime.py`, `case/admission.py`: one gate for a person's proposal and a rule's start (the
  waiting start, refusal beside a failed run); the `answered` moment; the condition check before
  scheduling and starting a plan.
- `case/state.py`: the waiting start and its record; the starts made by rules in the decision
  (always empty between events, like `moments`).
- `case/approvals.py`, `case/answers.py`: an approval asked anyway; exclusions from the record.
- `core/before_activity.py`: the condition's untrusted sources, checked apart from the inputs'.
- A function of the definition giving what a field's writers could stamp, shared by the runtime and
  validation (`flow.case_sources` today), so neither depends on the other having run.
- `case/reach.py`, `case/validate.py`, `case/warnings.py`, `case/registered.py`, `case/flow.py`:
  choices 11–19.
- `temporal/carried.py`: the waiting start crosses continue-as-new.
- `testing.py`, `contracts.lock.json`: `orders.lookup@2`.
- The guides: cases ("Rules that start steps", the refusals, the codes), case data (the fresh
  refund, a proposal waiting), activities (`@2`), plans (the open half).

### Not in 11b

- Stopping steps, `cancellable` workflows and the one place that stops children (11c); events and
  `set` (11d); timers (11e); the renderer and `simulate` (11f); patterns and warnings (11g).
- Option a inside a plan's own transitions (left open, doors row 31).
- Three paths carried to layer 12 (from the tutor review), beside 10b's G1 replay note ("Not in
  10b"): on Temporal, a case open under 11a's code on a path 11b decides differently would replay
  differently under the new code, and wait until the code is fixed (brief, D17). The paths: a
  proposal on a stale fact, a proposal beside a failed run, and a condition reading an unset
  untrusted field. Nothing runs in production before v1.0, so no case is open on one; layer 12
  ("releases and changing open cases") is where a behaviour version stored with each case belongs.
  No gating in 11b: `case` stays free of Temporal, and Temporal's `patched` in the driver wouldn't
  reach what `decide` decides.
- No new dependency.

### Seams the tests use

- `parse_case(data)`: `CaseInvalid` for an `answered` naming what isn't a task, a `start` naming
  what isn't a step.
- `run_case(...)`: `history`, `needs_attention`, `waiting_for`, `closed`, `reached`; `propose`,
  `retry`, answers, `later`.
- `validate_case(case, catalog)`: the issues above.
- The Temporal test server: a waiting start and a rule's record cross continue-as-new and replay;
  a history recorded before 11b, committed as a fixture, replays under the new worker.
- The guides' examples, run as written.

### Slices, in order

Each starts with its negative test, seen failing for the right reason.

0. **The corrections, each in its own commit,** after recording the replay fixture under today's
   code, and registering `orders.lookup@2` (`testing.py`, `contracts.lock.json`, no fake), which
   the guide's fresh refund already names; each test that runs it gives its own implementation:
   - 0a. A proposal waits for its fresh facts. Negative: the fresh refund with `pay` made
     `"automatic": false, "proposed_by": ["support"]`, proposed on a 3-day-old status, is not
     scheduled before `check_order#2`.
   - 0b. Nothing starts beside a failed run. Negative: with `check_order` repeatable, proposing it
     while `check_order#1` needs attention is refused (today `check_order#2` is scheduled, and the
     operator's retry of `check_order#1` is recorded but never scheduled), and the retry is
     scheduled.
   - 0c. An unset untrusted field counts. Negative: the `!exists notes` rule reaches nothing.
   - 0d. A proposal that can't be made fails the step. Negative: proposing a step whose input is
     refused fails its run, and the case needs attention, instead of raising out of `decide`.
1. **The shape.** Negative: `answered` naming a step that isn't a task, `start` naming what isn't a
   step, are refused when read; a step a rule starts reads without `proposed_by`. 11a's
   `test_an_unknown_moment_is_refused_in_one_line` and `test_a_rule_that_does_nothing_is_refused`
   change with it: `{"answered": "review"}` is now a moment, the refusal lists four, and a rule
   reaches or starts at least one.
2. **Starting.** Negative: a rule's start of a step whose `when` is false runs nothing and says so.
   Then each kind of refused start, the rework loop, the waiting start, the failing start, the
   per-decision guard, the proposer and the exclusions.
3. **Option a at runtime.** Negative: the welcome letter on a model's notes fails, naming the
   condition's field. Then the rule's `when`, only untrusted sources counting, a plan step, an
   approval asked anyway, an unset field in a condition, and the fresh refund (`@1` refusing
   `pay`, `@2` running it).
4. **Validation.** Negative: `NEVER_STARTS`. Then choices 11–19, each shown with a run.
5. **On Temporal.** The waiting start and the record cross continue-as-new and replay; the fixture
   replays.
6. **The guide and the promises.**

### Decided while building

- **What a condition's message says** (slice 3): the refusal names only the untrusted sources the
  condition read (`welcome's condition reads kyc.analyst_notes (untrusted:llm)`), never the
  trusted ones beside them.
- **`NEVER_STARTS`, in two proven forms** (slice 4a, choice 12):
  - a rule on `opened` with no `when` (a `when` may fail, and a retry reads the case file later)
    starting a step that requires a step (nothing has completed as the case opens) or a milestone
    no rule on the opening reaches. Only `opened` counts as the opening: a rule on a milestone a
    rule on the opening reaches may fire later, if a step reaches it instead;
  - a rule on the step's own moment: on its start, refused while it runs (unless the rule's
    `when` may fail and the step is repeatable: the retry may come once it is done); on its
    answer, refused when it isn't repeatable. This is how the note's "requires what comes only
    after its own run" was read.
- **One cause, one issue, for a start** (slice 4a): no `NEVER_STARTS` when the step never runs
  for its own requirements (its `NEVER_RUNS` says why). When it never runs because nobody can
  start it, both: the rule's `NEVER_STARTS`, and the step's `NEVER_RUNS` pointing at it (`fix
  start_lead_check first`). That `NEVER_RUNS` says how the step starts ("only when proposed", "when
  a rule starts it", or both), then why each can't; 10a's message is unchanged when no rule starts
  the step. Its path is `steps.<name>.proposed_by` when it names roles, else `steps.<name>`.
- **`UNTRUSTED_TRIGGER` only for a rule that reaches** (slice 4b): a rule that only starts steps
  acts, so its condition counts for their inputs instead (11a gave it `UNTRUSTED_TRIGGER`, with a
  message ending "never reaches " and nothing after). One that reaches and starts gets only
  `UNTRUSTED_TRIGGER`, which now says it starts nothing either. `INPUT_POLICY` for a condition
  says what to do as `UNTRUSTED_TRIGGER` does: read a value a person or a trusted system gives.
- **Not claimed: a plan step's condition against its plan's activities** (slice 4b). The runtime
  checks it (slice 3); validation claims less.
- **A 10d test changed its own contracts** (slice 4b): the `NEVER_REFRESHED` test read
  `draft.draft_id` and `note.entry_id`, both undeclared, in `pay`'s condition, so under option a
  `pay` fails every run and the warning gave way to that error. The test's write and compute
  contracts now declare those outputs (`letters.file@1`, `refunds.note@1`); no guide example
  changed.
- **One refusal of an unknown moment** (slice 4c), `rules.unknown_moment`, used by `said`,
  `moment_can_come` and the rule warnings; `NEVER_FIRES` reads the moment through `said`. The
  definition's name check has none: the typed moment refuses an unknown one before it runs. The
  test reaches `said` (through `decide`) and `moment_can_come` (through `validate_case`); the
  warnings' refusal sits behind `moment_can_come`'s, so it is a second guard, never alone under
  test (corrected after the second review, which found `NEVER_FIRES`'s own refusal unreachable).
- **The loop of starts** (slice 4d, choice 17) lives in `case/loops.py`. "Surely starts again"
  means a rule on a task's answer with no `when`, starting a repeatable task with no `when` that
  requires nothing but the task just answered; "entered in every case" means a task of the loop
  starts by itself, with no `when` and nothing required. A loop only a person's proposal enters
  claims nothing: it may never be entered. Its `NEVER_CLOSES` is at the first rule's
  `then.start`, and a case that stays open with nobody to close it is said once, loop or not.
  Only `NEVER_CLOSES` keeps the close reasons' roles from being checked again, never the
  warning.
- **`NEVER_CLOSES`'s words** (choice 18): "nothing but a forget request could close it" when the
  definition lets the case be forgotten while open (`allowed` or `while_open`) and a role that
  forgets is registered; otherwise "nothing could ever close it".

### From the code review

One reviewer, after slice 6, built definitions where an error and a run disagree, by hand and with
a random generator over rules on all four moments (about 8,000 definitions read and run). It found
three, each fixed test-first, and one question for the user:

- **A rule's start once the close is due** (runtime): with every `closes_when` milestone
  reached, `start_from_rules` still started a step, decided on the same moment, and the case was
  flagged; validation's `NEVER_RUNS` for that step was right. Now refused and recorded: `lookup
  not started: checked is reached, so the case closes and nothing new starts`.
- **A rule's record kept with a run that fails before it starts** (runtime): a start failing on a
  stale fact or an unreadable condition dropped what the rule read, so the operator's retry sent
  the letter a model's notes chose, and let the person whose answer decided approve the run.
  Validation's `INPUT_POLICY` at the rule was right.
- **`CLOSES_AT_OPENING` beside a rule on the opening with a `when`** (validation, a gap from 11a):
  such a rule may fail, whatever the check says of what it reads (the opener may leave a field
  out, or the value is read only once a dead step ran), and the case then waits for a person. Not
  claimed any more.
- **Left for the user:** a run that failed before it started, retried, fires no `started`
  moment (11a's "a retried run starts nothing again"). 11b makes that retry the way a rule's
  failed start goes on, so a rule on `started` never hears of that run. *(Answered by the tutor
  review: it fires; see "From the tutor review".)*

### From the second review

A wider review followed: five reviewers (the runtime; determinism and Temporal; validation again;
the documents against the code; the conventions), each finding put to a skeptic who tried to
refute it. 27 findings, 18 kept (three were one bug). Each fix landed test-first:

- **A plan step a rule starts** read the rule's record after it was spent, so the untrusted values
  the rule's condition read never reached the plan, and the refund was paid on a customer's note.
  Now read first. A retried plan, the same run started again (brief, D26), keeps who may approve
  nothing in it and those values on its run (`StepRun.excluded`, `StepRun.steered`), carried
  across continue-as-new: before, its retry let the person whose answer the rule read approve,
  as it let a person who proposed the step (a gap since layer 8, closed with it).
- **An open approval follows the case file before a rule's start is decided**, so a start is
  refused only by an approval that still stands; before, a start was refused by the approval the
  same decision withdrew, and nothing was asked again.
- **A start of a step approved and waiting for a fact** is refused and recorded (`pay is approved,
  and waits to start: pay.approval#1`); before, it failed the step and took its approval. A
  person's proposal of it is refused the same way.
- **A rule's start left when the case stops deciding** (a retried rule reaching the last
  `closes_when` milestone) is recorded, never dropped in silence.
- **A new proposal replaces what a withdrawn one left**, a person's or a rule's: before, a rule's
  record outlived its withdrawn approval and refused the approver of a run a person proposed.
- **A fact nothing can fetch again** fails a rule's start saying why (`it came from a person, so
  it can't be fetched again`), not "retry it to fetch it". D39 gets a dated amendment, and the
  guides say so.
- **Validation:** a warning on an input (`OPENER_DECIDES`) no longer hides the condition's
  `INPUT_POLICY`; `NEVER_REFRESHED` says a person's proposal is refused, where one may propose the
  step; the guide's `NEVER_STARTS` row names the exception for a repeatable step's own start.
- **Tests and promises:** the own-answer `NEVER_STARTS`, a refused input and a fact nothing can
  fetch again, and a rule's start beside a waiting proposal are tested; two rows named tests that
  checked only part of them. `NEVER_FIRES`'s unreachable refusal is gone, and the new
  `writers.writers_of` is `could_come_from`, as the other `writers_of` returns writers.
- **Left for the user: cases already open when 11b is deployed.** 11b decides some paths
  differently from 11a (a proposal on a stale fact, a proposal beside a failed run, a condition
  reading untrusted data). A case open on one of them stops on replay under the new worker:
  Temporal refuses a history the code would decide differently, and the case waits until the code
  is fixed (brief, D17). The fixture replays because its path is decided the same way, so its
  promise says only that. Gating the changed paths (Temporal's `patched`, or a version stamped in
  the state when a case opens) would keep them; changing open cases is layer 12's subject.
  *(Answered by the tutor review: no gating; carried to layer 12, see "Not in 11b".)*

### From the third review

A last pass checked the second review's fixes for regressions (three reviewers, a skeptic for each
finding): none, but the fixes left gaps, closed test-first:

- **Every retried run keeps who may not approve it**, not only a plan's: an activity or workflow
  step keeps, when it is scheduled, the people its first start excluded and the untrusted values
  that chose it, on its run (`may_not_approve`, one function for both), and an approval asked
  only on its retry refuses them. Before, Sam, who proposed the goodwill refund, or whose check a
  rule read, approved its retried run.
- **The close names what holds it:** a failed rule holds a `closes_when` close as a failed run
  does, and what is refused meanwhile now names it (`checked is reached, so the case closes once
  note_it#1 is retried, …`); with only a failed rule, it said "closes once nothing are retried".
- **Pinned by tests:** a retried plan still refused on what the rule read, and refusing the person
  who proposed it; a rule's start replacing a person's withdrawn proposal; each half of
  `NEVER_STARTS`'s exception on a step's own start; `NEVER_REFRESHED` for a step a rule starts.
  Each was a promise that a reverted fix would have broken with every test still passing.

### From the tutor review

The tutor review (at `18edafd`) found nothing that must change but one wording slip, and answered
the two questions; the user agreed with both answers, 2026-10-18. Built test-first:

- **The loop's verb agrees with its rules:** `send_back starts review again on every answer`, and
  `check_review and send_back start …` only when several rules are named; its fix, likewise,
  names the one rule (`give send_back a when that ends the loop`), and says "one of the rules"
  only of several (asked by the user after the tutor review). The guide's example names two
  rules, so its table already read right.
- **Cases open at deployment:** no gating; the three changed paths are carried to layer 12 ("Not
  in 11b").
- **`started` fires the first time a run really starts,** whether admission, a proposal, a rule's
  start or an operator's retry of a run that failed before it started starts it; a retry of a
  run that had already started fires nothing. Recorded as a dated amendment to D38, which adds to
  its "a retry is the same run" and to 11a's "a retried run starts nothing" (above, 11a's
  "Decided while building"): the run is the same, but it starts for the first time. Why: 11e's
  timers `since` a start and 11g's `sla` from a step's latest start (D7) would otherwise miss the
  run an operator had to rescue. A run now records whether it has started (`StepRun.started`,
  carried across continue-as-new; a state from before reads every run as started).

### Promises

Drafted before building, from the choices above; each row's test was named here first, and the
table was checked against the files after slice 6, 2026-10-18: every test it names exists where it
says. Every test is in `tests/test_rules.py` unless said otherwise.

| Promise | Test that would fail |
|---|---|
| A proposal of a step whose fact is stale and can be fetched again waits for the refresh, then reads everything again | `test_a_proposal_waits_for_its_fresh_facts` (`tests/test_fresh_facts.py`) |
| Nothing starts beside a failed run: a person's proposal of a repeatable step is refused, and the operator's retry is scheduled | `test_nothing_starts_beside_a_failed_run` (`tests/test_case.py`) |
| A rule's condition naming an unset untrusted field doesn't act | `test_an_unset_untrusted_field_still_cant_decide` |
| `answered` names only a task, and `start` only a step | `test_answered_names_a_task_and_start_a_step` |
| A step a rule starts needs no `proposed_by`; with none, nobody may propose it | `test_a_step_only_a_rule_starts_is_proposed_by_nobody` |
| A rule that neither reaches nor starts anything is refused, and the unknown-moment refusal lists the four moments | `test_a_rule_that_does_nothing_is_refused`, `test_an_unknown_moment_is_refused_in_one_line` |
| `answered` fires on each answer, whatever the outcome | `test_answered_fires_on_each_answer` |
| A rule's start whose `when` is false, or whose requirements aren't met, runs nothing, and says so | `test_a_start_whose_condition_is_false_runs_nothing`, `test_a_start_whose_requirements_arent_met_runs_nothing` |
| A start of a running step, one waiting for its approval or to start, or one that has run and isn't repeatable is recorded, and nothing runs | `test_a_refused_start_is_recorded` |
| A start of a step approved and waiting for a fact is recorded, and the step starts on that approval once the fact lands | `test_a_start_of_an_approved_step_waiting_for_its_fact_is_refused` (`tests/test_fresh_facts.py`) |
| A rule's start is decided after an open approval follows the case file | `test_a_rules_start_sees_the_approvals_that_stand` |
| A new proposal replaces a withdrawn one's record, either way: the person whose check the rule read may approve a run a person proposed, and a person whose proposal was withdrawn may approve the rule's | `test_a_new_proposal_replaces_a_withdrawn_one` |
| A plan step a rule starts carries the rule's untrusted sources into its plan | `test_a_plan_step_a_rule_starts_carries_what_the_rule_read` (`tests/test_plan_step.py`) |
| A retried plan keeps who may approve nothing in it, the person who proposed it included, and is refused again on what the rule read | `test_a_retried_plan_keeps_who_may_not_approve_in_it` (`tests/test_plan_step.py`), `test_a_plan_step_a_rule_starts_carries_what_the_rule_read` (`tests/test_plan_step.py`) |
| A retried activity keeps who may not approve it: the person whose answer the rule read, and who proposed it | `test_a_retried_run_keeps_who_may_not_approve_it` |
| A run that failed before it started fires `started` once, when an operator's retry schedules it | `test_a_retried_run_that_never_started_fires_started_when_it_starts` |
| A retry of a run that failed after it started fires nothing | `test_a_retry_of_a_run_that_started_fires_nothing` |
| Whether a run has started crosses continue-as-new | `test_a_waiting_start_crosses_continue_as_new` (`tests/test_temporal_case.py`) |
| While a failed rule or run holds the close, what is refused names it | `test_a_failed_rule_holding_the_close_is_named` |
| A person's proposal of a step whose start already waits is refused, and the first proposer still can't approve its run | `test_a_second_proposal_of_a_waiting_step_is_refused` (`tests/test_fresh_facts.py`) |
| A rule's start beside a failed run is refused | `test_a_rule_starts_nothing_beside_a_failed_run` |
| A rule's start whose condition can't be read, whose contract is missing, whose input is refused, or whose stale fact can't be fetched again needs attention, saying why nothing can fetch it | `test_a_start_that_cant_be_made_needs_attention` |
| A rule's start on a stale fact that could be fetched again needs attention, and an operator's retry fetches it, then runs the step | `test_a_rules_start_never_waits_for_a_refresh` |
| A person's proposal on a stale fact that can't be fetched again is refused, saying why | `test_a_proposal_on_a_fact_that_cant_be_fetched_is_refused` (`tests/test_fresh_facts.py`) |
| A person's proposal whose input is refused, whose contract is missing, or whose high-risk step has no approval fails its run, and the case needs attention | `test_a_proposal_that_cant_be_made_needs_attention` (`tests/test_case.py`) |
| The rework loop runs as the guide shows | `test_the_guides_rework_loop_runs_as_shown` |
| A step a rule started in a decision isn't started again by a rule in it, and the line says so (a rule already started it in this decision) even while that run is still open | `test_a_rule_starts_a_step_once_per_decision` |
| The proposer is the rule's entry, and whoever's answer its `when` read can't approve the run | `test_whoever_a_rules_condition_read_cant_approve_what_it_started` |
| The person whose answer only brought the moment may approve | `test_the_answer_that_brought_the_moment_doesnt_exclude` |
| What the rule read is kept with the run: a value changed in between still excludes and still taints | `test_a_rules_record_outlives_the_case_file_changing` |
| A step's untrusted `when` refuses an input whose policy refuses it, naming the field and source, never the value | `test_an_untrusted_condition_cant_choose_what_is_sent` |
| A rule's untrusted `when` refuses the started step's input the same way | `test_a_rules_untrusted_condition_cant_choose_what_is_sent` |
| Only untrusted sources count: an input taking a value from one system is sent when its step's `when` reads a person's answer | `test_a_trusted_condition_changes_nothing` |
| A literal input is never credited with a condition's sources | `test_a_condition_never_vouches_for_a_literal` |
| A condition reading a source the engine doesn't recognise counts as untrusted, and refuses an input whose policy refuses untrusted data | `test_an_unrecognised_condition_source_counts_as_untrusted` |
| A step's `when` naming an unset field that an untrusted writer could give refuses an input whose policy refuses that source | `test_an_unset_field_in_a_steps_condition_counts_its_writers` |
| A plan step carries its condition's untrusted sources beside its fields | `test_a_plan_step_carries_its_conditions_sources` (`tests/test_plan_step.py`) |
| A rule that reaches a milestone and reads untrusted data starts nothing either | `test_a_rule_that_cant_decide_starts_nothing` |
| An approval whose `when` read untrusted data is asked whatever it gave, and says why; one that can't be read stops the step | `test_an_untrusted_approval_condition_asks_anyway` |
| The forms test: the approval is now asked, and the refused input fails once it is given | `test_a_forms_values_land_in_the_case_file` (`tests/test_case.py`) |
| `orders.lookup@1`'s undeclared status refuses the fresh refund's `pay`; `@2` runs it | `test_an_undeclared_status_cant_choose_a_payment` (`tests/test_fresh_facts.py`) |
| Running `orders.lookup@2` with no implementation given raises, naming it: the development catalog has no fake for it | `test_a_contract_with_no_fake_raises` (`tests/test_fresh_facts.py`) |
| Who can start a step counts rules: no `NEVER_RUNS` for a step a rule may start, and a misspelt `proposed_by` is still reported | `test_a_step_a_rule_may_start_can_run` (`tests/test_case_validation.py`) |
| A start refused every time is `NEVER_STARTS`, on the opening, on the step's own start (not when its condition may fail and the step is repeatable), or on its own answer when it isn't repeatable; a rule whose condition may fail at the opening gets none; a step whose every start is refused never runs | `test_a_start_refused_every_time_is_never_starts` |
| A step started only by a rule on its own moment gets one issue | `test_a_step_started_only_on_its_own_moment_gets_one_issue` |
| An untrusted condition gives `INPUT_POLICY` at the step and at the rule, whoever opens the case, and nothing at the rule when the step's input already has an error (a warning there hides nothing); a rule that also reaches gets only `UNTRUSTED_TRIGGER`, saying it starts nothing | `test_input_policy_counts_conditions` (`tests/test_case_validation.py`) |
| A rule on the opening that starts a step keeps the case from closing at once: no `CLOSES_AT_OPENING`, and the run waits | `test_a_step_a_rule_on_the_opening_starts_keeps_the_case_open` |
| A rule on the opening with a `when` gives no `CLOSES_AT_OPENING`: it may fail, and the case waits | `test_a_rule_on_the_opening_that_may_fail_keeps_the_case_open` |
| Once every `closes_when` milestone is reached, a rule's start is refused and recorded, even one decided on that moment | `test_a_rule_starts_nothing_once_the_case_closes` |
| A rule's record is kept with a run that fails before it starts: the retry is still refused on its inputs, and still excludes | `test_a_rules_record_survives_a_start_that_fails` |
| A moment a check doesn't know is refused, never read as the opening | `test_an_unknown_moment_fails_closed` |
| `answered` counts as waiting for its task for `MAY_BE_UNSET` and `SET_AFTER` | `test_answered_waits_for_its_task` |
| A loop of one rule says it `starts` its step, and its fix names that rule; several rules `start` theirs, and the fix says "one of the rules" | `test_a_loop_of_one_rule_says_it_starts`, `test_the_guides_table_of_rule_codes_is_what_validate_case_says` |
| A loop nothing in the case can end is `NEVER_CLOSES`; the same loop a close reason or `closes_when` can close is `LOOPS_UNTIL_CLOSED`, beside a misspelt close role; a loop a refused start ends, or only a person's proposal enters, gets neither | `test_a_loop_of_starts_never_closes`, `test_a_loop_a_close_can_end_is_warned`, `test_a_loop_a_requirement_ends_gets_no_issue` |
| `NEVER_CLOSES` says only a forget request could close the case, or, with no forgetting, that nothing could | `test_the_guides_table_is_what_validate_case_says` (`tests/test_case_validation.py`), `test_never_closes_says_nothing_could_without_forgetting` (`tests/test_case_validation.py`) |
| What isn't claimed: a writer started only on the reader's own moment gives `MAY_BE_UNSET`, a cycle through `started` nothing | `test_what_rules_that_start_steps_dont_claim` |
| An approval whose `when` always reads untrusted data is `NEVER_REFRESHED`'s "always needed" | `test_an_untrusted_approval_is_always_needed` (`tests/test_case_validation.py`) |
| `NEVER_REFRESHED` says a person's proposal is refused where one may propose the step, and that it needs attention where it starts by itself or by a rule | `test_never_refreshed_says_a_proposal_is_refused` (`tests/test_case_validation.py`) |
| A waiting start and a rule's record cross continue-as-new, and replay decides the same | `test_a_waiting_start_crosses_continue_as_new` (`tests/test_temporal_case.py`) |
| A history recorded before 11b, on a path 11b decides the same way, replays under 11b's worker (cases open on a changed path: see "From the second review") | `test_a_history_from_before_11b_replays` (`tests/test_temporal_case.py`) |
| The runtime refuses what validation refuses, on nothing validation did | `test_an_untrusted_condition_cant_choose_what_is_sent` (`INPUT_POLICY` fails the run), `test_a_start_refused_every_time_is_never_starts` (the start `NEVER_STARTS` names is refused): each runs the case through `run_case` alone |
| No line or issue of 11b quotes a value from a case file | `test_no_start_line_or_issue_quotes_a_value` |
| The guides' refusals, start lines and codes are what the engine says | `test_the_guides_refusals_are_what_the_engine_says` (`tests/test_case.py`), `test_the_guides_start_lines_are_what_the_engine_says`, `test_the_guides_table_of_rule_codes_is_what_validate_case_says` |

---

## 11c. Rules that stop steps

### What this part is for

A rule can reach milestones (11a) and start steps (11b), but nothing can stop a step except
closing the whole case. So "when the customer withdraws the claim, stop the assessment" can't be
said without ending the case, and with it every other step. 11c lets a rule's `then` **stop**
steps: what a close does, to one step (brief, D10, D28), never to a failed run (brief, D17, D26).
And it builds the one place that stops a running child, used by `stop` and by closing alike, with
workflow steps whose contract declares `cancellable: true` stopped by Temporal's cancellation
(brief, D6, D29).

The sketch, on the refund (the cases guide, "Rules that stop steps"): a customer who withdraws
the request stops the review and the payment.

```json
"rules": {
  "withdraw": {"display": {"title": "Stop the refund when the customer withdraws"},
               "on": {"reached": "withdrawn"},
               "then": {"stop": ["review", "pay"]}}
}
```

`withdrawn` is reached by a support task, `log_withdrawal`, answered when the customer calls. Its
run, with `review#1` open:

```
reached withdrawn
withdraw#1 on reached withdrawn: stopping review and pay
cancelled review#1: stopped by withdraw#1
withdraw#1 on reached withdrawn: pay not stopped: no run of pay is going on
closed: nothing left to do
```

### How the session went

The warm-up first (learning question 39's follow-up, "not sure, tell me"; recorded in the log).
Most of 11c's choices were settled in 11b's session ("Agreed for 11c", above); the four points that
session didn't discuss, and the choices that remained, were put to the user with a recommendation
each, and answered "go with all recommendations", 2026-10-18. Below, "Agreed in 11b" marks what
11b's session settled; the rest was agreed in this one.

### Decided in the session

**What `stop` means** (doors rows 1, 3, 5):

1. **`stop` ends the run going on now, and doesn't keep the step from starting later** (agreed in
   11b). A repeatable step may be proposed or started again; a step that starts by itself still
   does so at most once, since a stopped run is a run (admission starts it only when it has none).
   `"then": {"stop": ["review"]}` is a list of step names; an item may later become `{"step": …,
   "<option>": …}`, a plain name keeping its meaning (row 3). `stop` refuses a name that isn't a
   step when the definition is read (row 1).
2. **One name in both `stop` and `start` of a rule is refused** when the definition is read. In
   one rule it would mean "restart", and what it did would depend on the step's kind: a task is
   cancelled at once, so the start opens a new run; an activity keeps running, so the start is
   refused as already running. A restart can come later as an option of the object form, recorded
   as a decision. Two rules may still stop and start one step: 11b's per-decision guard keeps the
   pair finite (brief, D39). Set aside: allowing it, with a meaning that depends on the kind.
3. **Inside one `then`: stop, then reach, then start.** The stop acts at once, in the firing; a
   milestone reached is queued as a moment, as in 11a; a start is queued as a proposal, decided by
   admission once the rules on the moment have fired, as in 11b. So the rules that follow, and
   admission's next round, see the stopped run. With choice 2, the order fixes how the history
   reads; it never decides which run a stop hits. Set aside: the order the keys are written in,
   which JSON doesn't keep as meaning.
4. **A run really stopped ends `cancelled`,** neither done nor failed (agreed in 11b; row 5). So
   `requires` doesn't count it as done: a step requiring `review` whose latest run was stopped
   waits for a later run to be done, as it waits while a later run is open. A later `required`
   flag can say what a stopped step counts as.

**What a stop does to each thing it finds** (agreed in 11b, unless marked):

5. **An open task** is cancelled, saying why: `cancelled review#1: stopped by withdraw#1`. The
   reason names only the entry, never a value.
6. **An open approval** is withdrawn and **a given one** lapses, and the coming run is recorded
   `cancelled`: `cancelled pay.approval#1: stopped by withdraw#1`, `pay#1 cancelled: stopped by
   withdraw#1`.
7. **A person's start waiting for a fact** *(this session)* is dropped as an approval is withdrawn:
   the coming run is recorded `cancelled`. The refresh on its way still lands, and changes the case
   file as any read does.
8. **A running activity, or a workflow step whose contract isn't cancellable,** finishes: a side
   effect can't be cut off halfway (brief, D10). Its run stays `running`, marked `stop requested by
   withdraw#1`, until it ends. Done, it is recorded as done (its outputs land, its milestones are
   reached) and flagged: `flagged: pay#1 completed after its stop was requested by withdraw#1`.
9. **A running plan step** is sent the plan's `stop` signal, with a reason: its open waits are
   cancelled, nothing new starts in it, an activity running in it finishes (brief, D28). It ends
   `cancelled`, and an activity in it that completed after the stop flags the case, as closing does.
10. **A cancellable workflow step** is cancelled by Temporal (choices 17–19). Ended cancelled, its
    run is `cancelled` and the case is flagged (`flagged: kyc#1 cancelled after its stop was
    requested by withdraw#1`), since what it did before the request stands; completed after all,
    it is done and flagged, as in choice 8.
11. **A failed run is never stopped** (brief, D17, D26), and the stop is recorded: `withdraw#1 on
    reached withdrawn: pay not stopped: pay#1 needs attention, and a failed run is never stopped`.
12. **Nothing to stop, or a stop already asked** *(this session)*: recorded, and nothing else
    happens: `pay not stopped: no run of pay is going on`, `pay not stopped: its stop is already
    requested`. A child is never cancelled or signalled twice.

**After a stop** (the four points 11b's session didn't discuss):

13. **A run that fails after its stop was requested needs attention,** as any failure does
    (brief, D17): `pay#1 failed after its stop was requested by withdraw#1: provider unreachable`.
    An operator retries it, with the same key, or closes the case. The same for a plan step whose
    activity fails after the stop (the step fails, never `cancelled`), and for a cancellable
    workflow that fails instead of ending cancelled. Set aside: cancelling it and flagging the
    case, as closing does. That is right while closing, where nobody retries a run (8b), and stays
    so; but a case that goes on could later start `pay#2`, with a new key, while nobody knows
    whether `pay#1` paid: what "nothing starts beside a failed run" prevents (brief, D39).
14. **A step that needed a stopped refresh needs attention.** A stopped refresh counts for nothing
    (agreed in 11b): the fact stays stale. Whatever waited for it (a step starting by itself, a
    person's waiting start, a step approved and waiting for its fact) fails, saying why: `pay#1
    failed: check_order.status is stale, and its refresh check_order#2 was stopped by withdraw#1:
    retry pay#1 to fetch it again`. A given approval goes with the failed run, as when any coming
    run fails, and the operator's retry fetches the fact again (brief, D26, D33). Set aside:
    waiting and refreshing again, which loops inside one decision (a rule on `started
    check_order` stopping it: refresh, started, stopped, refresh…) and breaks 11b's bound "each
    stale fact fetched again at most once until its refresh lands" (brief, D39); and dropping the
    waiter, which skips work nobody decided to skip (brief, D17).

**Who may stop:**

15. **Untrusted data can't stop** *(this session)*. Stopping decides for the case: an injected note
    could cancel every review. A rule whose `when` reads an untrusted (or unrecognised) source
    stops nothing, and says so, naming the value and its source, never the value: `withdraw#1 on
    reached checked: stops nothing: its condition reads kyc.analyst_notes, from untrusted:llm, and
    untrusted data can't decide`. Like a rule that reaches, it doesn't act at all, its starts
    included (brief, D38). `UNTRUSTED_TRIGGER` covers a rule that stops, as one that reaches.
16. **Rules stop with the close** (brief, D38): once every `closes_when` milestone is reached, or
    the case is closing, a rule's stop is not applied, recorded as any firing is. Closing stops
    what is running itself, through the same place (choice 20).

**Workflow steps and `cancellable`** (doors row 7; brief, D6, D29):

17. **`cancellable: true` on a workflow contract is the team's promise,** written as three clauses
    its history shows (agreed in 11b): after a cancellation request it schedules nothing new; it
    ends only once everything it started has ended; it ends cancelled only if nothing it started
    completed after the request. Without it (the default), a workflow step runs to its end, like
    an activity.
18. **The hash doesn't change for a contract that isn't cancellable** (agreed in 11b): `cancellable`
    is left out of the hash when false, declared or not, so every existing hash and
    `contracts.lock.json` stay as they are. Declaring it true changes the hash, so it is a new
    version (`kyc.check@1` stays as it is).
19. **The contract test checks the promise** (agreed in 11b): `check_workflow_contract` of a
    cancellable contract also starts the workflow, requests its cancellation, and reads its
    history for the three clauses, on Temporal's time-skipping test server.

**One place that stops every running child** (doors rows 2, 7, 8):

20. **One function in `case/stopping.py`, used by closing and by `stop`** (agreed in 11b). For each
    running run it gives what the run's kind declares: a plan step, the `stop` signal with a
    reason (`StopPlan`); a cancellable workflow step, Temporal's cancellation
    (`CancelWorkflow`); an activity or another workflow step, nothing but the mark "stop
    requested". It refuses a run that is failed, ended or already asked to stop. A later child case,
    or a workflow that waits for people, adds a branch there, not a second way to stop; a later
    `then: close` would call `begin_closing`, which stops running children through it (row 2).
21. **Closing changes with it** (agreed in 11b): a close now cancels a cancellable workflow step,
    where until now it let every workflow step finish (brief, D10, D29). No contract declares
    `cancellable` today, `kyc.check@1` included, so no example changes meaning: each is run
    through `validate_case` and `run_case` before and after, and the results compared. The guides
    say it ("Closing a case", "Workflow steps"; the activities guide).

**Each decision still ends** (row 11; brief, D39):

22. **A stop starts nothing, and nothing a stop does starts a run.** A cancelled task, a withdrawn
    approval or a dropped waiting start leaves the step free, and only admission, a person or a
    rule may start it again; a step starts by itself at most once (choice 1); a step a rule has
    started in a decision isn't started again by a rule in it, so two rules on `started X`, one
    stopping it and one starting it, give one restart per decision; a stopped refresh fails what
    waited for it (choice 14), so a stale fact is still fetched at most once until its refresh
    lands. 11b's bound on the runs a decision starts holds as it is.

**Validation stays a proof** (brief, D34):

23. **What a stop takes away keeps every "may" true.** `can_happen` and every check reading it
    (`NEVER_RUNS`, `DEADLOCK`, `NEVER_FIRES`, `UNREACHABLE_MILESTONE`, `CLOSE_UNREACHABLE`) say
    what *may* happen, every `when` taken as possibly true: a stop only removes paths, so a step
    they say never runs still never runs. A rule that stops counts as any rule: its moment, its
    `when` type-checked (`EXPRESSION_INVALID`), its reads (`OUTCOME_UNREAD`, `MAY_BE_UNSET`,
    `SET_AFTER`), `NEVER_FIRES`.
24. **The claims that something always happens are each checked again, shown with a run.** Two
    already stop being proofs once a rule can stop a step, and claim less from 11c:
    - **the loop of starts** (`NEVER_CLOSES`, `LOOPS_UNTIL_CLOSED`; `case/loops.py`): D39 says "no
      rule stopping it", and the code doesn't check it, since nothing could stop a step. A rule
      that may stop a task of the loop can end it, so the loop is claimed only when no rule that
      can fire stops a step of it;
    - **`NEVER_STARTS` on the step's own start** ("refused while it runs"): a rule that may stop
      the task first lets the start through. Claimed only when no rule that can fire stops the
      step.
    The others are checked with a run each, and kept as they are or narrowed the same way:
    `NEVER_RUNS` after the close, `SET_AFTER` and `MAY_BE_UNSET` (a step required is done: a
    stopped run isn't, choice 4), `CLOSES_AT_OPENING`, `NEVER_CLOSES`. No new code.
25. **The runtime depends on nothing validation did** (brief, D34): every refusal above happens in
    `decide` too, tested through `run_case` alone.

**On Temporal** (agreed in 11b, the details left to the assistant):

26. **The driver waits for a cancelled child** (`ChildWorkflowCancellationType.
    WAIT_CANCELLATION_COMPLETED`), so its run ends only once the child has, and what it gave comes
    back as for any child.
27. **The plan's `stop` signal takes a reason, whose default keeps today's text** (`the case is
    closing`), so a history whose signal carried none replays the same.
28. **A child is never cancelled twice:** the run's mark "stop requested" is set once, and the
    driver keeps which children it asked; a close after a stop asks nothing again.
29. **What crosses continue-as-new:** a run's "stop requested", carried; a state from before 11c
    reads it as none (brief, D27). A case continues as new only when nothing runs, as today.
30. **A history recorded under 11b's driver replays under 11c's,** with a fixture committed before
    the driver changes, as 11b did: a plan step stopped by a close, and a workflow step finishing
    through a close.

**Timers (11e), only what it needs** (row 19):

31. **A run has ended once it has its final status** (`done`, `rejected`, `failed`, `cancelled`).
    A run whose stop is requested and still running hasn't ended; a stopped run's timers end with
    it, when it does.

**And:**

32. **D40,** drafted with this note: `stop`, what it does to each thing it finds, the one place,
    `cancellable` workflows and closing through it. D10, D28, D29, D38 and D39 keep their text;
    D40 adds to them.

### The doors left open (the checkpoint's 11c section)

| Row | How 11c keeps it open |
|---|---|
| 1 Stages | `stop` refuses a name that isn't a step (choice 1), so a stage named there later is a new meaning, never a changed one; "exit a stage" can be "stop each step in it" through the one place |
| 2 Exit criteria on the case | a later `then: close` calls `begin_closing`, which stops running children through the one place (choice 20), and rules stop with the close (choice 16): it lands on "closing", never on a cut |
| 3 Exit types | `stop` ends only the run going on now (choice 1); "and keep it from starting" would be an option of the documented object form, never a second action or a new reading of a plain name |
| 5 Required items | a stopped run ends `cancelled`, neither done nor failed (choice 4), so a later `required` can say whether it counts |
| 7 Human waits inside a workflow step | one place stops every child, each by the mechanism its kind declares (choice 20); a workflow that waits for people adds its mechanism there. D27's quiet point and D10's "closing lets a workflow finish" still need an addition before row 7 is built, as the table says |
| 8 Child cases | a child case adds a kind to the one place, not a second way to stop; D27's quiet point still needs its addition |
| 19 Orphan removal (timers) | a run has ended once it has its final status, and a stopped run's timers end with it (choice 31), so 11e's "purpose ending" covers a stopped step with no new rule |

### Where the code goes

- `case/definition.py`: `then.stop` (steps; not also in `start`); a rule reaches, starts or stops.
- `case/stopping.py` (new): the one place, for closing and `stop`.
- `case/rules.py`: a firing's stop, after the trust check and before reach and start.
- `case/state.py`: a run's `stop_requested`; `CancelWorkflow`, a reason on `StopPlan`; the event
  for a workflow step ended cancelled.
- `case/runtime.py`, `case/closing.py`: closing through the one place; a run that ends or fails
  after its stop; a stopped refresh failing what waited for it.
- `case/memory.py`: a held workflow step cancelled; `testing.py` passes it through.
- `core/workflow_contract.py`, `core/contract_hash.py`: `cancellable`, out of the hash when false.
- `case/loops.py`, `case/validate.py`, `case/reach.py`, `case/warnings.py`: choices 23–24.
- `temporal/cases.py`: a workflow step started with a handle and cancelled; the plan's stop with
  a reason; never twice. `temporal/workflow.py`: the `stop` signal's reason. `temporal/carried.py`:
  `stop_requested`. `temporal/contract_check.py`: the cancellation check.
- The guides: cases ("Rules that stop steps", "Closing a case", "Plan steps", "Workflow steps",
  the codes), activities (`cancellable`, the contract test).

### Not in 11c

- Events and `set` (11d); timers (11e), beyond choice 31; the renderer and `simulate` (11f);
  patterns and warnings (11g), including a warning for two rules stopping and starting one step.
- A restart (stop and start in one rule), and "stop and keep from starting" (the object form).
- `then: close` (row 2: where it would land is said above).
- No new dependency.

### Seams the tests use

- `parse_case(data)`: `CaseInvalid` for a `stop` naming what isn't a step, a name in both `stop`
  and `start`, a rule that does nothing.
- `run_case(...)`: `history`, `needs_attention`, `flags`, `closed`, `waiting_for`; `held` and
  `finish` for a running activity or workflow; `propose`, `retry`, `close`, answers, `later`.
- `validate_case(case, catalog)`: the issues above.
- `contract_hash(contract)` and the lock file; `catalog.register` for `cancellable`.
- `check_workflow_contract(...)` on the time-skipping test server, for a cancellable contract
  that keeps or breaks its promise.
- The Temporal test server: a stopped plan step, a cancelled workflow step, a close cancelling
  one, never twice; `stop_requested` crossing continue-as-new; the 11b fixture replaying.
- The guides' examples, run as written.

### Slices, in order

Each starts with its negative test, seen failing for the right reason.

0. **Before anything changes:** the replay fixture recorded under 11b's driver, and every
   example's `validate_case` issues and `run_case` result recorded, to compare at the end.
1. **The shape.** Negative: `stop` naming a milestone, one name in both `stop` and `start`, are
   refused when read; a rule stopping a step reads. `cancellable`: false leaves every hash as it
   was; true changes it.
2. **Stopping, in memory.** Negative: a rule's stop of a failed run stops nothing, and says so.
   Then an open task, an approval open or given, a waiting start, nothing to stop, a stop already
   asked; a running activity finishing, flagged; the order stop, reach, start; untrusted data
   can't stop; a stop once the close is due; `requires` after a stopped run; a step that starts
   by itself, stopped, doesn't start by itself again.
3. **After a stop.** Negative: an activity failing after its stop needs attention, never
   `cancelled`. Then the stopped refresh, and its waiters.
4. **The one place.** Negative: closing a case with a cancellable workflow step running cancels it
   (today it finishes). Then a plan step stopped by a rule, with its reason; a workflow step
   stopped, cancelled or not; never twice.
5. **Validation.** Negative: the loop a rule can stop is no longer `NEVER_CLOSES` (seen wrong with
   a run first). Then `NEVER_STARTS`, each check of choice 24 with a run, `UNTRUSTED_TRIGGER` for
   a stop.
6. **On Temporal.** Negative: a cancellable workflow step, stopped, is cancelled on the
   time-skipping test server and the driver waits for it. Then the plan's stop with a reason,
   never twice, the contract test's cancellation check, continue-as-new, the fixture. The contract
   test's three new messages join the activities guide's table then, since a test reads that
   table against the check.
7. **The guides, the examples compared, and the promises.**

### Promises

Drafted before building, from the choices above; each row's test named here first, to be checked
against the files once built. Every test is in `tests/test_rules.py` unless said otherwise.

| Promise | Test that would fail |
|---|---|
| `stop` names only steps, and refuses a milestone or an unknown name | `test_stop_names_a_step` |
| One name in both `stop` and `start` of a rule is refused | `test_a_rule_cant_stop_and_start_one_step` |
| A rule that neither reaches, starts nor stops is refused | `test_a_rule_that_does_nothing_is_refused` |
| `cancellable` left false, or not declared, leaves a contract's hash and the lock file as they were; true changes the hash | `test_cancellable_false_leaves_the_hash` (`tests/test_catalog.py`), `test_every_development_contract_matches_its_recorded_hash` (`tests/test_catalog.py`) |
| A stopped open task is cancelled, saying which rule's entry stopped it, and the case may close | `test_a_stop_cancels_an_open_task` |
| A stopped approval, open or given, is withdrawn or lapses, and the coming run is recorded `cancelled` | `test_a_stop_withdraws_an_approval` |
| A stopped waiting start is dropped, its coming run recorded `cancelled`, and its refresh still lands | `test_a_stop_drops_a_waiting_start` (`tests/test_fresh_facts.py`) |
| A stop with nothing to stop, or already asked, is recorded and does nothing else | `test_a_stop_with_nothing_to_stop_is_recorded` |
| A failed run is never stopped, and the stop says so | `test_a_failed_run_is_never_stopped` |
| A running activity finishes when stopped: marked, then done, its outputs and milestones landing, and flagged | `test_a_stopped_activity_finishes_and_is_flagged` |
| An activity failing after its stop needs attention, never `cancelled` | `test_a_run_failing_after_its_stop_needs_attention` |
| A step waiting for a stopped refresh fails, saying so, and an operator's retry fetches the fact again | `test_a_step_needing_a_stopped_refresh_needs_attention` (`tests/test_fresh_facts.py`) |
| Inside one `then`, the stop acts first, then reach, then start, and later rules on the moment see the stopped run | `test_stop_then_reach_then_start` |
| A rule whose condition reads untrusted data stops nothing, naming the value and source, never the value | `test_untrusted_data_cant_stop` |
| Once every `closes_when` milestone is reached, a rule's stop is not applied, and says why | `test_a_stop_once_the_close_is_due_is_not_applied` |
| A stopped step's latest run isn't done: a step requiring it waits for a later run | `test_a_stopped_run_is_not_done` |
| A step that starts by itself, stopped, doesn't start by itself again; a repeatable step may be proposed again | `test_a_stopped_step_may_start_again_only_if_asked` |
| Two rules on a step's start, one stopping it and one starting it, restart it once per decision | `test_stop_and_start_on_one_moment_end` |
| A plan step stopped by a rule ends `cancelled` with the rule's reason; an activity completing in it after the stop flags the case; one failing needs attention | `test_a_rule_stops_a_plan_step` (`tests/test_plan_step.py`) |
| A cancellable workflow step is cancelled when stopped, and flagged; one that isn't cancellable runs to its end, and is flagged | `test_a_stopped_workflow_step_is_cancelled_only_if_cancellable` (`tests/test_workflow_step.py`) |
| A close cancels a cancellable workflow step, through the same place, and lets any other finish | `test_a_close_cancels_a_cancellable_workflow_step` (`tests/test_workflow_step.py`) |
| A child is never stopped twice: a close after a stop asks nothing again | `test_a_child_is_never_stopped_twice` (`tests/test_workflow_step.py`) |
| A loop of starts a rule may stop is neither `NEVER_CLOSES` nor `LOOPS_UNTIL_CLOSED` | `test_a_loop_a_rule_can_stop_gets_no_issue` |
| `NEVER_STARTS` on a step's own start isn't claimed when a rule may stop the step | `test_never_starts_isnt_claimed_when_a_rule_may_stop_the_step` |
| Each check that claims something always happens is still a proof with rules that stop, each shown with a run | `test_what_validation_claims_stays_true_with_stops` (`tests/test_case_validation.py`) |
| A rule that stops reads like any rule: its moment, its condition type-checked, `NEVER_FIRES` | `test_a_rule_that_stops_is_checked_like_any_rule` |
| A rule that stops on always-untrusted data is `UNTRUSTED_TRIGGER` | `test_a_rule_stopping_on_untrusted_data_is_refused` |
| The runtime refuses what validation refuses, on nothing validation did | `test_untrusted_data_cant_stop`, `test_a_failed_run_is_never_stopped`: each runs the case through `run_case` alone |
| A cancellable workflow step stopped on Temporal is cancelled, and the case waits for it to end | `test_a_stopped_cancellable_workflow_is_cancelled_on_temporal` (`tests/test_temporal_workflow_step.py`) |
| A plan step stopped on Temporal ends with the rule's reason; the signal's default keeps today's text | `test_a_rule_stops_a_child_plan` (`tests/test_temporal_case.py`) |
| A child is never cancelled twice on Temporal | `test_a_child_is_cancelled_once_on_temporal` (`tests/test_temporal_workflow_step.py`) |
| The contract test checks a cancellable workflow's three clauses, and reports each one broken | `test_the_contract_test_checks_cancellation` (`tests/test_temporal_workflow_step.py`) |
| "Stop requested" crosses continue-as-new; a state from before 11c reads it as none | `test_a_stop_request_crosses_continue_as_new` (`tests/test_temporal_case.py`), `test_a_carried_state_reads_back_as_it_was` (`tests/test_temporal_case.py`) |
| A history recorded under 11b's driver replays under 11c's | `test_a_history_from_before_11c_replays` (`tests/test_temporal_case.py`) |
| No line or issue of 11c quotes a value from a case file | `test_no_stop_line_or_issue_quotes_a_value` |
| The guides' stop lines, closing and workflow text are what the engine says | `test_the_guides_stop_lines_are_what_the_engine_says`, `test_the_guides_table_of_rule_codes_is_what_validate_case_says` |
