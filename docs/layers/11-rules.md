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
11c part and a draft Promises table written the same day, before building; then built, slices
0–7, with a read of the code by six readers beside slice 2 (see 11c, "From the code map"), and
the Promises table checked against the tests, the same day. 11d: the warm-up (learning question
34's follow-up) answered, 2026-10-19; 23 choices and a split put with a recommendation each, and
"build" taken as all of them, the split included, so `set` became 11e (see 11d, "The split"); the
guide's part and D41 written before building; built, slices 0–8, once the fix of a rejected retry
was merged; the Promises table checked against the tests, the same day. 11e: the warm-up
(learning question 36's follow-up) answered "can't remember", 2026-10-19; 14 choices put with a
recommendation each, answered "all as recommended, one pull request" the same day; the guide's
part, D42 and a draft Promises table written before building; built, slices 0–9, and the Promises
table checked against the tests, the same day (see 11e, "Decided while building"). 11f: the
warm-up (learning question 33's follow-up) walked through, 2026-10-19; sixteen choices put with a
recommendation each, recorded as a draft awaiting answers, then answered "all as recommended,
one pull request", 2026-10-20; D44, the guide's part and the slices' plan written before
building; built, slices 0–9, and the Promises table checked against the tests, the same day (see
11f, "Decided while building"). 11g: the warm-up (learning question 38) put, 2026-10-20; eighteen
choices put with a recommendation each, one of them splitting 11g in two, recorded as a draft
awaiting answers; the warm-up answered, and the choices answered "all as recommended", the same
day; D45 and the guide's "Reading rules" written before building 11g1.

## What this layer is for

Until now a case reacts in one way only: after every event, admission asks each step "may you start
now?" (layer 8). That covers "pay once the review approves", not "if nobody has assessed the claim
in five days, escalate", "when the customer cancels, stop", or "once the check is done, mark the
customer high risk if the score is over 70". Layer 11 adds the **rule**: *when* something happens,
*if* a condition holds, *then* act on the case (brief, Simplifications, "one kind of rule"; D7).

User-facing description: `docs/guides/cases.md`, "Rules" (11a's part written 2026-10-17, before
building: the curriculum's "document first"); each later part adds to it. Decisions: brief D38
(11a), D39 (11b), D40 (11c), D41 (11d), D42 (11e).

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

Layer 11 lands as eight pull requests, each with its section in this note, its own Promises table
and its own tutor review, as layers 8–10 did. Each part's choices are decided in its own session.

| PR | Builds | Codes (proposed) |
|---|---|---|
| **11a: the raw rule, inside the case** | `rules` in the definition: `on` (the case opened, a milestone reached, a step started), `when`, `then: reach`; when rules run in `decide`; a rule that can't be read needs attention; untrusted data can't decide (design question 17 decided); rules and the close; case validation kept true | `NEVER_FIRES`, `UNTRUSTED_TRIGGER` |
| **11b: rules that start steps** | `then: start` (the engine proposes, through admission: the rework loop), and the moment a task is answered; the half of design question 17 that steers which step starts, built; validation: a step a rule starts can run; a rule that restarts a step for ever | `NEVER_STARTS`, `NEVER_CLOSES` extended, `LOOPS_UNTIL_CLOSED` |
| **11c: rules that stop steps** | `then: stop` (what a close does, to one step; never a failed run); one place in the case that stops every running child; `cancellable` workflows (D29), stopped by Temporal's cancellation; closing through that place | |
| **11d: events from outside** | declared events with a typed payload and one sender (D12); `on: {"event": ...}`; listening is not waiting, and a step explicitly waiting for an event (D10); "arrival is a fact, content is not"; an event as a signal on Temporal | `UNTRUSTED_TRIGGER` for event content (no new code: see 11d, choice 15) |
| **11e: rules that update the case file** | `then: set`, which brings back the provenance fixpoint (D34, D36); who may write a field; what "surely set" and `SET_AFTER` claim then | `WRITER_DECIDES` (proposed) |
| **11f: time** | timers, `on: {"after": "5d", "since": <moment>}`: set on their moment, pending work (D10), fired as an event stamped with its own due time (D33), never a clock `decide` reads; cancelled by their rule's purpose ending and by any close; crossing continue-as-new exactly (D27), replaying the same; staleness noticed by a timer (9d's carried note); reports list set timers (D24) | `NEVER_CLOSES` for a timer that re-arms itself |
| **11g: reading rules** | the plain-language renderer for every rule; `ventoux simulate`: a story on a timeline, with simulated time, showing when each rule fires; stories as tests | |
| **11h: patterns and teaching warnings** | `sla` (from the latest start; `since=first_start` explicitly), `reminder`, `four_eyes` (`count=2`, D11, D23), each expanding into raw rules visible in validation and views, each with a story test; D7's teaching warnings (a timer anchored on the first start of a repeatable step, a rule whose condition reads untrusted data, what is left of "rules that can never fire" once 11a's error has taken the proven ones) | warnings |

**Why this order.** 11a is the smallest rule that *acts*, and it brings the two things every later
part stands on: where rules run in `decide`, and case validation kept true once something other
than a step reaches a milestone (brief, D34). Starting steps (11b) needs that loop and reuses
admission; stopping them (11c) reuses closing. Events (11d) bring outside content, so trust
belongs there; the update action (11e) brings the provenance fixpoint it needs. Timers (11f) need
moments to anchor on (11a) and events (11d), since a timer firing is an event with its own time.
The renderer and `simulate` (11g) need every kind of rule to exist; the patterns (11h) are written in
raw rules and tested as stories, so they come last, as D7 says: "raw rules are the engine's
concept, not the first one people meet".

*Renumbered 2026-10-18, in 11b's session:* 11b, as first planned, held both starting and stopping
steps; it was split in two, so events, time, reading rules and patterns moved from 11c–11f to
11d–11g. 11a's section below keeps the letters it was written with, where "11b" meant both.

*Renumbered again 2026-10-19, in 11d's session:* 11d, as planned, held both events and `then:
set`; it was split in two (see 11d, "The split"), so `set` is 11e, and time, reading rules and
patterns moved to 11f–11h. The table, "Why this order" and the table below use the new letters;
11a's, 11b's and 11c's sections keep the letters they were written with, as does the brief
(brief, D41).

**Carried into layer 11, and where each lands:**

| Carried | Where |
|---|---|
| Case validation stays true once rules reach milestones and start or stop steps (`can_happen`, `NEVER_RUNS`, `CLOSES_AT_OPENING`, `NEVER_CLOSES`, `SET_AFTER`, the 10d warnings) | 11a for `reach`, 11b for `start`, 11c for `stop`, 11d for events, 11e for `set` |
| Provenance: a rule computing fields from fields brings the fixpoint back (D34, D36) | 11e, with `set` |
| `UNTRUSTED_TRIGGER` and design question 17 | decided in 11a; built in 11a (a condition that decides) and 11b (a condition that steers which step starts); event content in 11d |
| Time as event data stamped from workflow time (D33); timers as pending work (D10), across continue-as-new (D27), on replay; staleness noticed by a timer (9d) | 11f |
| Whether rules act once every `closes_when` milestone is reached (D34) | 11a (choice 7) |
| What a close does to timers (D10: cancelled) | 11f |
| `sla`, `reminder`, `four_eyes`, the renderer, teaching warnings, `ventoux simulate` | 11h, 11h, 11h, 11g, 11h, 11g (as in the table) |

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
   file as any read does. *(Widened while building: so is a step about to start by itself once its
   fact lands; see "From the code map".)*
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
    (brief, D17): `pay#1 failed after its stop was requested by withdraw#1: payments.refund@2
    failed with RuntimeError: ‹sensitive›` *(quoted as built: what an activity said is never
    written, brief, D31)*.
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
    waiter, which skips work nobody decided to skip (brief, D17). *(As built, the line reads
    `pay#1 failed: check_order.status was obtained 3 days ago, and pay needs it at most 1 day old:
    its refresh check_order#2 was stopped by stop_lookup#2, so it counts for nothing; retry it to
    fetch it again`; and what the stopped look-up gives still lands. See "Decided while
    building".)*

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
    `then: close` would begin closing, and `decide` then stops running children through it
    (`stop_children`), as for any close (row 2).
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
    *Amended 2026-10-20, in 11f's session (choice 4):* for its timers, a failed run hasn't ended:
    it waits for a person, and an operator's retry runs it again as the same run (brief, D26).

**And:**

32. **D40,** drafted with this note: `stop`, what it does to each thing it finds, the one place,
    `cancellable` workflows and closing through it. D10, D28, D29, D38 and D39 keep their text;
    D40 adds to them.

### Decided while building

- **The order of the slices:** the Temporal slice (6) came before validation (5). The driver had
  to carry `CancelWorkflow` before slice 4 could pass the type check, so the Temporal work was
  built and tested next, then validation.
- **The fixtures keep their key** (slice 0): Ana's review is an answer with a form, sealed with
  the case's key (brief, D31), so a fixture replays only with it. Each fixture's development key
  is committed beside it (`<name>.keys.json`, a key made by a test server for a fake case), and
  `ventoux.testing.fixture_converter` reads it. 11b's fixture needed none: its case had no form.
- **The before and after of every example** (slices 0 and 7): every `run_case` and `validate_case`
  call the suite makes was recorded with its full result (status, history, flags, what needs
  attention, what waits; every issue), before any code changed and again at the end: 783
  records, all identical, and 48 new ones from 11c's tests. No example changed meaning, closing's
  change included: no contract declares `cancellable`.
- **Who stopped a run, on the run** (slice 2): `StepRun.stop_requested` holds the rule's entry
  (`withdraw#1`). A close marks nothing: it happens once, and stops only runs no rule asked, so a
  child is asked once either way. A `cancelled` line says `stopped by withdraw#1` or `the case is
  closing`, from the run, never from what the child reports.
- **The lines, as built:** `pay#1: stop requested by withdraw#1` for any running run;
  `pay#1 cancelled: stopped by withdraw#1` for a coming run or a child that ended cancelled;
  `flagged: … completed after its stop was requested by withdraw#1`, and `… cancelled after its
  stop was requested by …` for a cancellable workflow (after a close: `… after the close was
  requested`); `pay#1 failed after its stop was requested by withdraw#1: …`, its reason in
  `needs_attention` unchanged. An activity in a stopped plan reports `… completed after the stop
  was requested`, as it reports `… after the close was requested`.
- **An operator's retry clears the stop request** (slice 3): a person decided to try again, so a
  retried run that completes is not flagged as completing after a stop.
- **A stopped refresh, as built** (slice 3): a look-up is an activity, so a stop leaves it running
  and it finishes; what it gives lands, as any read does (choice 8). It counts for nothing for
  what waited on it: the waiter fails at once. An operator's retry fetches the fact again even
  while the stopped look-up still runs, so the failure's "retry pay#1 to fetch it again" holds.
- **A plan stopped by a rule, on Temporal** (slice 6): an activity in it that fails after the stop
  makes the plan end `stopped`, never `cancelled`, so the step fails and needs attention
  (choice 13); while closing, it is flagged as before. The plan's `stop` signal carries its
  reason; its handler reads a signal given none as a close, so a history from before 11c replays
  (Temporal doesn't compare a signal's input on replay). *(Corrected after the review: this said
  a close's signal carried no argument, which wasn't so when the close came while the child
  started, and which nothing needed.)*
- **A workflow step on Temporal** (slice 6) is started with `start_child_workflow` and
  `WAIT_CANCELLATION_COMPLETED`, its handle kept; cancelling the handle sends the request, with
  the reason, and the case waits. Neither changes the history of a step that isn't cancelled:
  the fixture replays. A cancellation arriving after the run ended (in memory, a start and its
  cancellation in one batch) is ignored, the run's result already recorded.
- **The contract test's cancellation check** (slice 6), for a cancellable contract: a second run,
  asked to cancel once its first workflow task has run, its history read for the three clauses.
  An activity, a timer or a child workflow counts as something it starts (clauses 1 and 2); only
  an activity or a child workflow completing counts for clause 3 (a timer firing is not work
  done). A run that ended before the request is a problem: the promise wasn't checked, so the
  team gives an input that keeps it running (fail closed).
- **`NEVER_STARTS` on a step's own start** (slice 5) is claimed only when no rule in the
  definition stops the step, which claims a little less than "no rule that can fire" (choice 24):
  `start_refused` doesn't know what can fire, and claiming less never makes an error false.
- **The guide's lines are the engine's** (slice 7): every stop line "Rules that stop steps" quotes
  comes from a run (`test_the_guides_stop_lines_are_what_the_engine_says`); the plan's and the
  workflow step's lines from their own tests.
- **The driver's own "never twice"** (`stopping` in `temporal/cases.py`) is a second guard: the
  case never asks twice, so it is never alone under test.

### From the code map

Six readers mapped the code 11c touches (the runtime, rules, validation, the in-memory driver,
Temporal, contracts) while slice 2 was built, each running its claims against the code. What
changed because of it:

- **Five validation claims stop being proofs once a rule can stop a step,** each confirmed with a
  run, then fixed test-first in slice 5 (choice 24 named two of them):
  - the loop of starts (`NEVER_CLOSES`, `LOOPS_UNTIL_CLOSED`): D39's "no rule stopping it" was in
    the brief and never in the code. Tasks a rule that can fire may stop are left out of the
    restart graph before any loop is looked for, so a stoppable loop found first can't hide one
    no rule stops;
  - `NEVER_STARTS` on the step's own start;
  - `UNTRUSTED_TRIGGER`, never said for a rule that only stops (the runtime refused it already);
  - `INPUT_POLICY` at `rules.<name>.then.start` for a rule that stops and starts: on untrusted
    data it doesn't act at all, so `UNTRUSTED_TRIGGER` alone says it (one cause, one issue).
  The other checks stay proofs, each shown with a run
  (`test_what_validation_claims_stays_true_with_stops`).
- **A step about to start by itself once its fact lands** was invisible to a stop: no state
  names it, so the stop said "no run going on" and the step started afterwards. Now its coming
  run is recorded `cancelled` (choice 7, widened).
- **A cancellation after its run ended** is ignored (above).
- **A retried run waiting for its approval or its fact** (`retrying`, not yet running) counts as
  the failed run it rescues: a stop leaves it alone, saying it needs attention.
- **Found, not fixed, for the user:** a run that failed, retried, and whose approval is then
  rejected stays `retrying` for ever and holds the close, while the rejection is recorded on a
  new entry (`pay#2 won't run`). It is older than 11c and unrelated to stopping; it needs its own
  test and fix.

### From the review

After slice 7, five reviewers read the branch, each with one lens (the runtime; validation, with
a random generator over about 45,000 definitions with rules that stop, start and reach on all
four moments, which found no error a run contradicts; Temporal and replay; the documents against
the code; the conventions), and a skeptic per lens tried to refute each finding with a run. Of
32 findings, 30 were kept, for 13 causes; each fix landed test-first:

- **A stop cancelled a step that wasn't about to start** (runtime): `waits_for_its_fact` read only
  "automatic, never run, a refresh of a fact it reads running", so a stop of `pay`, whose review
  wasn't done, while another step had the status fetched again, recorded `pay#1 cancelled`, and
  the refund was never paid. It now asks what admission asks: requirements met, the close not
  held, a fact too old for this step with a refresh of it running; the event's time reaches the
  firing for it.
- **On Temporal, a retry after a stop was stopped again** (Temporal): the driver never forgot a
  stop, so an operator's retry of a plan or workflow step that failed after a rule's stop was
  stopped as it started, recorded as the case closing, and the case closed with nothing done; a
  workflow step's case hung. A start now forgets the stop asked of an earlier attempt.
- **A workflow step cancelled from outside the case was read as a close** (Temporal, fail
  closed): any cancellation became `kyc#1 cancelled: the case is closing`, the case closed, and
  the check was skipped; before 11c it failed and needed attention, and a history recorded so no
  longer replayed. Now only a cancellation the case asked for is one; any other is a failure
  (`decide` also fails closed on one nobody asked for), and that history, recorded under main and
  committed as `before_11c_workflow_cancelled_outside.json`, replays.
- **A stop signal reaching a child that had just ended failed the case workflow** (Temporal,
  older than 11c, which a close could hit; every rule's stop of a plan now can): the signal's
  failure is dropped when it says the child has ended, and any other still raises.
- **The contract test missed local activities, and could wait for ever:** a local activity run
  after the request (recorded as a marker once it has run) breaks the promise's first part; a
  completion counts for the third only for what was started before the request, so one cause
  gives one problem; a cancellation run that never starts is reported, never waited for.
- **`NEVER_STARTS` on a step's own start** is now dropped only for a task: a stopped activity,
  plan or workflow runs on through the decision, so the start is still refused every time, and
  claimed.
- **The stopped-refresh advice** names the run to retry (`retry pay#1 to fetch it again`), and a
  person whose proposal it refuses reads `propose recheck again once check_order#2 has landed`.
- **A stop of a run being retried** says so (`pay#1 is retried by an operator`), where it said
  the run needed attention.
- **Promises with no test,** each now tested: a given approval lapsing on a stop (removing it
  paid on the old approval with every test passing); a retried run left alone; a stop while the
  case closes; the driver keeping a stop decided while the child starts, for a plan and a
  workflow; the loop fix counting only rules that can fire, and never letting a stoppable loop
  hide another.
- **The documents:** `kyc.check@2` named two contracts, so the cancellable example is
  `kyc.check@3`; the case data guide's forget now says what any close does; a few quotes and
  lines here corrected where marked.
- **Set aside, with why:** none. Two findings were refuted (a step kind `ask_to_stop` doesn't
  name is one that is asked nothing by design, since every kind it lacks finishes; and test
  comments may cite several decisions at once, the rule being for `src/`).

### The doors left open (the checkpoint's 11c section)

| Row | How 11c keeps it open |
|---|---|
| 1 Stages | `stop` refuses a name that isn't a step (choice 1), so a stage named there later is a new meaning, never a changed one; "exit a stage" can be "stop each step in it" through the one place |
| 2 Exit criteria on the case | a later `then: close` begins closing, and `decide` then stops running children through the one place (choice 20), as for any close; rules stop with the close (choice 16): it lands on "closing", never on a cut |
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
- `case/runtime.py`: closing through the one place (`decide` calls `stop_children`); a run that
  ends or fails after its stop; a stopped refresh failing what waited for it.
- `case/memory.py`: a held workflow step cancelled; `testing.py` passes it through.
- `core/workflow_contract.py`, `core/contract_hash.py`: `cancellable`, out of the hash when false.
- `case/loops.py`, `case/validate.py`, `case/reach.py`, `case/flow.py`: choices 23–24.
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
   test's new messages join the activities guide's table then, since a test reads that
   table against the check.
7. **The guides, the examples compared, and the promises.**

### Promises

Drafted before building, from the choices above, then checked against the files once built,
2026-10-18: every test named here exists where it says. Every test is in `tests/test_rules.py`
unless said otherwise.

| Promise | Test that would fail |
|---|---|
| `stop` names only steps, and refuses a milestone or an unknown name | `test_stop_names_a_step` |
| One name in both `stop` and `start` of a rule is refused | `test_a_rule_cant_stop_and_start_one_step` |
| A rule that neither reaches, starts nor stops is refused | `test_a_rule_that_does_nothing_is_refused` |
| `cancellable` left false, or not declared, leaves a contract's hash and the lock file as they were; true changes the hash; an activity contract has none | `test_cancellable_false_leaves_the_hash` (`tests/test_catalog.py`), `test_every_development_contract_matches_its_recorded_hash` (`tests/test_catalog.py`, seen failing with the exclusion removed), `test_an_activity_contract_has_no_cancellable` (`tests/test_catalog.py`) |
| A stopped open task is cancelled, saying which rule's entry stopped it, an answer to it is refused, and the case may close | `test_a_stop_cancels_an_open_task` |
| A stopped approval is withdrawn, an answer to it refused saying why, and the coming run recorded `cancelled`, so the step doesn't start by itself again; a given one lapses, and nothing is paid on it | `test_a_stop_withdraws_an_approval`, `test_a_stop_lapses_a_given_approval` (`tests/test_fresh_facts.py`, seen failing with the lapse removed) |
| A stopped waiting start, a person's or the step's own, is dropped and its coming run recorded `cancelled`; the fact on its way still lands. A step not about to start (its requirements unmet), while another step's refresh runs, loses nothing | `test_a_stop_drops_a_waiting_start` (`tests/test_fresh_facts.py`), `test_a_stop_drops_a_step_waiting_for_its_own_fact` (`tests/test_fresh_facts.py`), `test_a_stop_of_a_step_not_about_to_start_cancels_nothing` (`tests/test_fresh_facts.py`) |
| A stop with nothing to stop, or already asked, is recorded and does nothing else | `test_a_stop_with_nothing_to_stop_is_recorded` (seen failing with the guard removed) |
| A failed run is never stopped, and the stop says so; nor is one an operator is retrying | `test_a_failed_run_is_never_stopped`, `test_a_stop_leaves_a_retried_run_alone` (`tests/test_fresh_facts.py`) |
| A running activity finishes when stopped: marked, then done, its outputs and milestones landing, and flagged | `test_a_stopped_activity_finishes_and_is_flagged` |
| An activity failing after its stop needs attention, never `cancelled`; an operator's retry runs it with the same key, and its completion isn't flagged | `test_a_run_failing_after_its_stop_needs_attention` |
| A step waiting for a stopped refresh fails, saying which run to retry; once the look-up lands, a retry runs it; a retry while the look-up still runs fetches the fact again; a person's proposal meanwhile is refused, saying to propose again once the look-up has landed | `test_a_step_needing_a_stopped_refresh_needs_attention` (`tests/test_fresh_facts.py`), `test_a_retry_fetches_again_past_a_stopped_refresh` (`tests/test_fresh_facts.py`), `test_a_proposal_on_a_stopped_refresh_is_refused_saying_what_to_do` (`tests/test_fresh_facts.py`) |
| Inside one `then`, the stop acts first, then reach, then start, and later rules on the moment see the stopped run | `test_stop_then_reach_then_start` |
| A rule whose condition reads untrusted data stops nothing, naming the value and source, never the value | `test_untrusted_data_cant_stop` |
| Once every `closes_when` milestone is reached, or the case is closing, a rule's stop is not applied, and says why | `test_a_stop_once_the_close_is_due_is_not_applied`, `test_a_stop_while_closing_is_not_applied` |
| A stopped step's latest run isn't done: a step requiring it waits for a later run | `test_a_stopped_run_is_not_done` |
| A step that starts by itself, stopped, doesn't start by itself again; a repeatable step may be proposed again | `test_a_stopped_step_may_start_again_only_if_asked` |
| Two rules on a step's start, one stopping it and one starting it, restart it once per decision | `test_stop_and_start_on_one_moment_end` |
| A plan step stopped by a rule ends `cancelled` with the rule's entry as reason | `test_a_rule_stops_a_plan_step` (`tests/test_plan_step.py`), `test_a_rule_stops_a_child_plan` (`tests/test_temporal_case.py`) |
| An activity in a plan a rule stopped that completes flags the case; one that fails makes the step need attention | `test_a_payment_in_a_plan_a_rule_stopped_completes_flagged_or_fails_for_a_person` (`tests/test_temporal_case.py`, its failing half seen failing with the plan's check removed) |
| A cancellable workflow step is cancelled when stopped, and flagged; one that isn't runs to its end, and is flagged | `test_a_stopped_workflow_step_is_cancelled_only_if_cancellable` (`tests/test_workflow_step.py`) |
| A close cancels a cancellable workflow step, through the same place, and lets any other finish | `test_a_close_cancels_a_cancellable_workflow_step` (`tests/test_workflow_step.py`), `test_a_workflow_finishing_after_the_close_flags_the_case` (`tests/test_workflow_step.py`) |
| A child is never stopped twice: a close after a stop asks nothing again | `test_a_child_is_never_stopped_twice` (`tests/test_workflow_step.py`, seen failing with the skip removed), `test_a_child_is_cancelled_once_on_temporal` (`tests/test_temporal_workflow_step.py`) |
| On Temporal a start forgets the stop asked of an earlier attempt: an operator's retry after a rule's stop runs; a stop decided as the child starts is kept, and reaches it once started | `test_a_retry_after_a_stop_runs_on_temporal` (`tests/test_temporal_case.py`), `test_a_plan_stopped_as_it_starts_is_stopped_on_temporal` (`tests/test_temporal_case.py`), `test_a_workflow_stopped_as_it_starts_is_cancelled_on_temporal` (`tests/test_temporal_workflow_step.py`) |
| A workflow step cancelled from outside the case, or ending cancelled when the case asked nothing of it, fails and needs attention, never read as a close; a history recorded under main with that path replays | `test_a_workflow_step_cancelled_from_outside_needs_attention` (`tests/test_temporal_workflow_step.py`), `test_a_cancellation_nobody_asked_for_needs_attention` (`tests/test_workflow_step.py`), `test_a_history_with_an_outside_cancel_from_before_11c_replays` (`tests/test_temporal_workflow_step.py`, seen failing with both guards removed) |
| A stop signal that finds the child just ended is dropped; any other failure of it still raises | `test_a_stop_to_a_child_that_has_just_ended_is_dropped` (`tests/test_temporal_case.py`, seen failing with the catch removed) |
| A cancellable workflow step stopped on Temporal is cancelled with the rule's entry as reason, and the case waits for it to end | `test_a_stopped_cancellable_workflow_is_cancelled_on_temporal` (`tests/test_temporal_workflow_step.py`) |
| The contract test checks a cancellable workflow's three clauses, a local activity run after the request included, reports each one broken once, a run it couldn't cancel, and a cancellation run that never starts; a contract that isn't cancellable gets no second run | `test_the_contract_test_checks_cancellation` (`tests/test_temporal_workflow_step.py`), `test_the_contract_test_finds_each_broken_promise` (`tests/test_temporal_workflow_step.py`) |
| A run's stop request crosses continue-as-new, every field of a run crosses, and a state from before 11c reads it as none | `test_a_stop_request_crosses_continue_as_new` (`tests/test_temporal_case.py`), `test_a_carried_state_reads_back_as_it_was` (`tests/test_temporal_case.py`) |
| Histories recorded under 11b's driver, a plan step stopped by a close and a workflow step running through one, replay under 11c's | `test_a_history_from_before_11c_replays` (`tests/test_temporal_case.py`), `test_a_workflow_history_from_before_11c_replays` (`tests/test_temporal_workflow_step.py`) |
| A loop of starts a rule may stop is neither `NEVER_CLOSES` nor `LOOPS_UNTIL_CLOSED`; one a rule stopping something else, or a rule that can never fire, can't end still is, and a stoppable loop never hides one no rule stops | `test_a_loop_a_rule_can_stop_gets_no_issue` (seen wrong with a run first), `test_a_loop_is_claimed_unless_a_rule_that_can_fire_stops_it` |
| `NEVER_STARTS` on a step's own start isn't claimed when a rule may stop the step and it is a task, and still is when none does, or when what a stop leaves running is an activity | `test_never_starts_isnt_claimed_when_a_rule_may_stop_the_step` (seen wrong with a run first), `test_never_starts_on_its_own_start_stays_claimed_for_what_a_stop_leaves_running` |
| A rule that stops on always-untrusted data is `UNTRUSTED_TRIGGER`, saying it never stops; one that also starts gets that issue alone, no `INPUT_POLICY` at its start | `test_a_rule_stopping_on_untrusted_data_is_refused`, `test_a_rule_that_stops_and_starts_on_untrusted_data_gets_one_issue` (each seen wrong with a run first) |
| The checks that claim something never or always happens stay proofs with rules that stop, each shown with a run: `NEVER_RUNS` after the close, `NEVER_CLOSES` from the settings, `CLOSES_AT_OPENING`, no `MAY_BE_UNSET` | `test_what_validation_claims_stays_true_with_stops` |
| A rule that stops is checked like any rule: `NEVER_FIRES`, `EXPRESSION_INVALID`, `SET_AFTER`, and the run fails as it says | `test_a_rule_that_stops_is_checked_like_any_rule` |
| The runtime refuses what validation refuses, on nothing validation did | `test_untrusted_data_cant_stop`, `test_a_failed_run_is_never_stopped`, `test_a_rule_stopping_on_untrusted_data_is_refused`: each runs the case through `run_case` alone |
| No line or issue of 11c quotes a value from a case file | `test_no_stop_line_or_issue_quotes_a_value` |
| The guides' stop lines, plan and workflow lines, refusals and codes are what the engine says | `test_the_guides_stop_lines_are_what_the_engine_says`, `test_a_rule_stops_a_plan_step` (`tests/test_plan_step.py`), `test_a_close_cancels_a_cancellable_workflow_step` (`tests/test_workflow_step.py`), `test_a_stopped_workflow_step_is_cancelled_only_if_cancellable` (`tests/test_workflow_step.py`), `test_the_guides_table_of_rule_codes_is_what_validate_case_says` |

## 11d. Events from outside

### What this part is for

Until 11d everything a case reacts to comes from inside it: a person's answer, an activity's
result, a retry, a close. 11d lets the world outside tell a case that something happened (the
customer cancels in the portal, a receipt is uploaded, support logs a call), lets rules react to
it, and lets a step wait for it. The lesson is the curriculum's check-yourself: **arrival is a
fact, content is not.** The Ventoux API vouches for who sent an event, so a rule may act on its
arrival; what the event says is only as trusted as its sources.

A sketch, the cases guide's (`docs/guides/cases.md`, "Events from outside"):

```json
"events": {
  "cancelled": {
    "display": {"title": "The customer cancels"},
    "sent_by": {"system": "portal"},
    "payload": {"note": {"type": "string", "display": {"title": "What the customer wrote"},
                         "source": "untrusted:customer"}}
  }
},
"rules": {
  "withdraw_on_cancel": {
    "display": {"title": "Stop the review when the customer cancels"},
    "on": {"event": "cancelled"},
    "then": {"stop": ["review"]}
  }
}
```

```
cancelled#1 from portal, giving note from system:portal, untrusted:customer
withdraw_on_cancel#1 on event cancelled: stopping review
cancelled review#1: stopped by withdraw_on_cancel#1
closed: nothing left to do
```

User-facing description: `docs/guides/cases.md`, "Events from outside", written before building.
Decision: brief, D41.

### How the session went

The warm-up first (learning question 34's follow-up, recorded in the log), 2026-10-19. The design
was put to the user in 23 choices with a recommendation each, and a split; the user answered the
warm-up and said "build", taken as all recommendations agreed, the split included (as 11b's "Go"
was). 11d's code waited for the fix of a retried run stuck after its approval was rejected
(`docs/layers/fix-retry-rejected.md`, pull request #28), so it builds on that fix, and its
invariant (every pending item shown) covers 11d's new pending work: an open wait.

### The split

11d, as planned, held two lessons: events from outside, and `then: set` with the provenance
fixpoint it brings back. Events on their own keep provenance one pass: with one sender per event
(choice 2), each value an event carries has one writer, as every value has today (brief, D34). So
11d builds events, and **11e** builds `set`, the fixpoint, who may write a field, the warning 11a
promised for a field only some writers make untrusted (`WRITER_DECIDES`, proposed), and what
"surely set" and `SET_AFTER` claim then (choices 16–23 of the session, carried to 11e unbuilt).
Time, reading rules and patterns move to 11f–11h ("The split", above; brief, D41).

### Decided in the session

All as recommended, 2026-10-19.

**Declaring an event:**

1. **Shape.** `events.<name>` is `{display, sent_by, payload}`. An event is not named like a step,
   a milestone or a rule: its arrivals are entries (`cancelled#1`) beside step runs and firings,
   and its values are read as `<event>.<field>` beside a step's outputs.
2. **One sender:** `{"system": "<a registered system>"}`, or `{"roles": [...]}`, people holding
   one of them, checked as for a close reason (brief, D10, D22). Never both, never neither. Room
   is left for a later kind of sender (a child case, doors row 8) as one more key of the object.
3. **Where a payload value comes from:** its sender (`system:portal`, `person:ana`), and the
   field's `untrusted:<label>`, added whoever sends it, as for the opening's values (brief, D12).
   Set aside: an undeclared field read as `untrusted:undeclared`, as an output is (brief, D29):
   an output is another team's code, while an event's sender is stated by the trusted caller,
   as the opener is, and a developer could then never make a system's event trusted.
4. **Its types:** the case's scalar types; every field given on every arrival, checked strictly
   (`fits`, as the opening's values are). A list is refused when the definition is read, since
   `fits` can't check a list value yet: never packed into a text meanwhile (doors row 6). No
   payload field is sensitive or narrows who sees it yet: a payload field says only its type,
   title and source.
5. **Where it lands:** as `<event>.<field>`, the latest arrival's, as an output does.

**What a rule may read of an event:**

6. **A fifth moment, `{"event": "<name>"}`,** each arrival (brief, D41, adding to D38's closed
   list). A rule may act on the arrival itself. Its `when` reads the case file as always: a
   payload value decides only as any value does, through its sources. Untrusted, it can't reach
   or stop (brief, D38, D40), and it steers a start only through the started step's input
   policies (brief, D39).

**Listening and waiting** (doors rows 5, 18):

7. **A rule on an event is never pending work** (brief, D10).
8. **The explicit wait is a step of the kind `wait`,** naming its `event`. It starts as any step
   does; its run is open until the event's next arrival, which makes it done and reaches its
   `reaches`. It is pending work, listed in `waiting_for` as `receipt_sent from portal` or
   `customer_called by support` (adds to D24). A stop or a close cancels it as an open task; an
   answer to it is refused. It takes no inputs, approval or `max_age`. Only an arrival after it
   opens ends it. It is the one place a later `required` can build on (doors row 5).

**Closing** (doors row 25):

9. **While closing,** an event is refused, recorded and flagged: a signal has no reply.
10. **Once closed,** the workflow has ended: the client's send raises `EventRefused`, and never
    starts a workflow to deliver it.
11. **While a failed run holds the close** (brief, D34), payload lands and a wait it ends is done,
    but no rule acts (brief, D38).

**Time** (brief, D33):

12. **An arrival is stamped from workflow time** as it reaches the case; its values are obtained
    then, by its entry. Nothing can fetch them again, and the line says so.

**On Temporal** (doors rows 8, 13):

13. **One `event` signal,** `CaseEvent(event, payload, by, roles)`, `by` being `system:<name>` or a
    person's identifier (which never holds a `:`, brief, D22), addressed to the workflow ID
    (brief, D27). An open wait is only state, like an open task: it doesn't hold back
    continue-as-new.

**Validation stays a proof** (brief, D34):

14. **Each check that reads moments or writers, checked again with a run:** `can_happen` counts a
    rule on an event as able to fire whenever the case is open; a payload value is surely set in a
    rule on its event and once a wait for it is done; never `SET_AFTER`; a loop through an event
    is never claimed; a person's payload given to an `only_from` input is `INPUT_POLICY`.
15. **No new code.** `UNKNOWN_EVENT` already means something else: plan validation gives it for
    a transition on an outcome a state never gives (`core/validate.py`). An undeclared event
    name is refused when the definition is read, as a step's or a milestone's is, and an event
    the runtime doesn't know is refused (`EventRefused`). `UNTRUSTED_TRIGGER` covers payload that
    is untrusted whoever sends it.

### Decided while building

- **A wait gives no value.** Its run ends only `done`, so `<wait>.outcome` says nothing a
  `requires` doesn't; it is left out of the case's values, and reading it is `EXPRESSION_INVALID`.
  The event's payload is the event's, read as `<event>.<field>`.
- **The guide said a `when` could let a wait be skipped** once its event had arrived. Writing the
  test showed it wrong: a step that requires the wait would then never start. The sentence is
  gone; the guide says the wait waits for the next arrival.
- **The development catalog registers `portal`,** the guide's sender. Three messages that list
  the registered systems now end with it (the activities guide, the cases guide, a test).
- **The guide's refusal table has its own header** (`An event is refused when`): the cases guide's
  test reads the first table headed `Refused when`. And `send_event` is said in prose: that test
  runs every Python block outside "Running a case on Temporal", and a top-level `await` can't run.
- **What was found failing, or failing closed,** each fixed test-first:
  - `said`, `can_happen` and the 10d warnings raised on the new moment: fail closed, never read
    as the opening (brief, D38), until each knew it;
  - `UNTRUSTED_TRIGGER` and `INPUT_POLICY` missed a payload value until `case_sources` stamped it
    with its sender and mark: no error was claimed falsely, but one was missed;
  - **the check that silently stopped saying something:** `surely_set` read any value that is
    neither a step's nor set by a form as "given at the opening (assumed)", so a payload value
    read where nothing waits for it got no `MAY_BE_UNSET`. A warning is no proof, but this one
    would never have been said;
  - `refreshable` and `never_fetched` said a stale payload value "came from the opening": a line
    that lied. They now say it came from the event, sent from outside.
- **Every place that read "not a task" as "a call or a plan step"** (freshness, inputs, the
  invariant's facts, which steps call something) now asks for a call or a plan step: mypy found
  each one once `wait` was a kind.
- **A refused event on Temporal names who sent it** (`refused cancelled from system:crm: …`),
  never what it carries; the client tells a case that has ended from an ID no case has, since
  Temporal says `NOT_FOUND` of both.

### From the tutor review

Reviewed at `18f047a`, 2026-10-19: one change needed, and one optional nit, both built test-first.

- **A signal that came with the close was lost unrecorded.** This note listed it as a known limit,
  and it contradicted D41 as written, which promises two outcomes for an event that comes too late
  (refused, recorded and flagged while closing; `EventRefused` at the client once closed): a
  third existed, the client's send succeeding and the case recording nothing. The review showed
  it with a run (the closing answer and an event, both sent before any worker runs, land in the
  case's first workflow task: the loop decides the answer, the case closes, and the loop ends with
  the event still in its inbox), and in a plain race (8 cases of 12 recorded neither the event nor
  its refusal). Decided: **once the loop ends, each item still in the inbox is refused and
  recorded, `refused cancelled from system:portal: the case is closed`, and the inbox cleared,
  before the workflow returns.** It adds a line of history and no command, so replay decides the
  same; and Temporal fails a completion that a newer signal overtakes, retrying it with that
  signal, so every signal accepted before the close is recorded. Answers, proposals, retries,
  close and forget requests were lost the same way on `main`; the same lines cover them. The two
  runs were seen failing first, the history ending at `closed: nothing left to do`. Added to D41,
  dated.
- **Optional: an event's people naming no role** were refused with plan validation's message, "a
  wait or an approval names at least one role that may answer it", which now reads as if it were
  about the new step. It has its own: `an event sent by people names at least one role that may
  send it`.

### Known limits

- **No sensitive payload, no list payload, no `visible_to` on a payload field:** each is refused,
  never read another way, so adding it later changes no definition's meaning.

### The doors left open (the checkpoint's 11d section)

| Row | How 11d keeps it open |
|---|---|
| 5 Required items | the explicit wait is a step (choice 8), so one `required` flag later can serve it and every other step |
| 6 One step per item of a list | a list payload is refused (choice 4), never packed into a text, so a later list type reads nothing differently |
| 8 Child cases | events are addressed to the case's workflow ID (choice 13), and `sent_by` takes a later kind of sender as one more key (choice 2) |
| 12 User event listeners | a person may send an event, roles checked as for a close reason, source `person:` (choice 2) |
| 13 Signal and generic listeners | one event shape and one signal, the sender data on the declaration (choice 13) |
| 14 Variable listeners | 11d brings no "field set" moment; `set` (11e) decides whether it comes with one, keeping each decision finite |
| 18 Completion-neutral items | listening is never pending work (choice 7); only a wait is (choice 8) |
| 25 Case reactivation | an event reaching a closed case is refused at the client, never delivered by starting a workflow (choice 10) |

### Where the code goes

- `case/definition.py`: `SentBy`, `PayloadField`, `DeclaredEvent`, `events`; the moment
  `EventArrived`; `WaitStep`; names unlike steps, milestones and rules.
- `case/state.py`: the event `Sent`; `arrived`, the arrivals' counts; `Obtained.run` may name an
  arrival.
- `case/runtime.py`: `receive` (sender, payload, the close), `arrive` (the values, the moment, the
  waits it ends); a wait's start; an answer to a wait refused; `refreshable` on an arrival; the
  case refused when it names an unregistered sender or label.
- `case/rules.py`: the moment said. `case/types.py`: payload types. `case/writers.py`: payload
  sources. `case/reach.py`: an event may come. `case/known.py`, `case/warnings.py`: surely set,
  `MAY_BE_UNSET`, `NEVER_REFRESHED`. `case/registered.py`: senders, roles, labels.
  `case/visibility.py`: a sender's roles are named. `case/stopping.py`, `case/validate.py`: a wait
  is not a call step.
- `temporal/cases.py`: `CaseEvent`, the `event` signal, `send_event`, refusals recorded.
  `temporal/carried.py`: `arrived`. `testing.py`: `send`, `portal` registered.

### Seams the tests use

- `parse_case(data)`: `CaseInvalid` for each shape refused.
- `run_case(...)` with `send(event, payload, by)` in the script: `history`, `waiting_for`,
  `needs_attention`, `flags`, `status`, `state`, `view`; `EventRefused`, `AnswerRefused`,
  `ProposalRefused`, `CaseRefused`.
- `validate_case(case, catalog)`: the issues above.
- The Temporal test server: `start_case`, `send_event`, `answer`, `report`, `view`, a case that
  continues as new.
- The guide's section, read as the engine runs it.

### Slices, in order

Each started with its negative test, seen failing for the right reason.

0. **The docs first:** the guide's section and D41.
1. **The shape.** Negative: a rule on an undeclared event (seen refused as an unknown moment).
2. **An arrival, in memory.** Negative: an undeclared event (seen failing closed on the moment,
   then taken in silence). Then the sender, the payload, the values landing, arrival and content.
3. **A wait.** Negative: an answer to a wait (seen crashing on a wait treated as a call step).
   Then it holds the case, ends on its event, is stopped and closed.
4. **The close.** Negative: an event to a closed case (seen taken). Then closing, and a held close.
5. **Time.** Negative: a stale payload value (seen said to come from the opening).
6. **Validation.** Negative: `validate_case` on the guide's case (seen failing closed). Then each
   check of choice 14, each seen missing or wrong first where it was.
7. **On Temporal.** Negative: an event to a closed case (seen raising Temporal's `NOT_FOUND`).
   Then a refusal recorded (seen hanging), a wait, exact values, continue-as-new (seen failing
   with the count left out of the carried state).
8. **The guide, as the engine does it, and the promises.**
9. **From the tutor review.** Negative: an event, then a person's proposal, each sent with the
   closing answer before any worker runs (each seen lost). Then the sender's own message.

### Promises

Every test is in `tests/test_events.py` unless said otherwise. Checked against the files once
built, 2026-10-19: every test named here exists where it says.

| Promise | Test that would fail |
|---|---|
| A rule on an undeclared event, a wait naming one, and an event named like a step are refused when the definition is read | `test_a_rule_on_an_event_the_case_doesnt_declare_is_refused`, `test_a_wait_names_a_declared_event`, `test_an_event_is_not_named_like_a_step` |
| An event has one sender, a system or people, never both or neither; its people name a role, said in its own words | `test_an_event_is_sent_by_one_sender`, `test_an_events_people_name_a_role` |
| A payload carries no list, and says only its type, title and source | `test_an_event_carries_no_list`, `test_a_payload_field_says_only_its_type_title_and_source` |
| A wait takes no inputs, approval or `max_age`; events and a wait read | `test_a_wait_takes_no_inputs_approval_or_max_age`, `test_events_and_a_wait_read` |
| An event the case doesn't declare is refused, naming its events | `test_an_event_the_case_doesnt_declare_is_refused` |
| Only its sender sends an event: another system, a person for a system's event, a system for people's, a person without a role, a misspelt person, are refused | `test_only_its_sender_sends_an_event` |
| An event carries exactly its payload: a field missing, one undeclared, one of another type, refused, naming the type, never the value | `test_an_event_carries_exactly_its_payload`, `test_no_event_line_or_issue_quotes_a_value` |
| An arrival lands each value as `<event>.<field>`, from its sender and its mark, obtained then by its entry, and its rule acts on the arrival | `test_an_arrival_lands_its_payload_and_its_rule_acts` |
| A person's event comes from them, and listening holds nothing | `test_a_persons_event_comes_from_them` |
| Each arrival is its own entry, and the latest payload stands | `test_each_arrival_is_its_own_entry_and_the_latest_payload_stands` |
| Untrusted content can't decide: a rule reading it stops nothing, saying which value and source, never the value | `test_untrusted_content_cant_decide` |
| A start on the arrival alone is made; one on untrusted content is refused by the started step's input policy | `test_untrusted_content_cant_choose_what_is_sent` |
| A wait is never answered | `test_a_wait_is_never_answered`, `test_the_guides_answer_to_a_wait_is_refused_as_it_says` |
| A wait is pending work, listed in `waiting_for` with its sender, until its event arrives, which makes it done | `test_a_wait_holds_the_case_until_its_event_arrives`, `test_a_wait_sent_by_people_says_who_sends_it` |
| Only an arrival after a wait opens ends it | `test_only_an_arrival_after_a_wait_opens_ends_it` |
| A stop or a close cancels a wait | `test_a_stop_or_a_close_cancels_a_wait` |
| A closed case refuses an event; a closing one refuses it, records it and is flagged, nothing landing | `test_a_closed_case_refuses_an_event`, `test_a_closing_case_refuses_an_event_and_is_flagged` |
| While a failed run holds the close, an event lands and ends a wait, and no rule acts | `test_while_a_failed_run_holds_the_close_an_event_lands_and_no_rule_acts` |
| A stale value an event carried is never fetched again, and the refusal says it came from the event | `test_a_stale_value_an_event_carried_is_never_fetched_again` |
| The guide's events get no issue; a rule on an event may fire whenever the case is open, and what it reaches can close the case | `test_the_guides_events_get_no_issue`, `test_what_a_rule_on_an_event_reaches_can_close_the_case` |
| A rule deciding on untrusted content is `UNTRUSTED_TRIGGER`, and the runtime refuses the same on its own | `test_a_rule_deciding_on_untrusted_content_is_refused`, `test_untrusted_content_cant_decide` |
| A person's payload given where only a system may give it is `INPUT_POLICY`, and the runtime refuses it on its own | `test_a_persons_payload_is_refused_where_only_a_system_may_give_it` |
| A payload read where nothing waits for it warns `MAY_BE_UNSET`; after its wait, or in a rule on its event, it is surely set; it is never `SET_AFTER` | `test_a_payload_read_where_nothing_waits_for_it_may_be_unset`, `test_a_payload_is_surely_set_after_its_wait_and_in_a_rule_on_its_event`, `test_a_payload_read_as_the_case_opens_is_never_set_after` |
| A `max_age` on a payload value is `NEVER_REFRESHED`, saying it came from the event | `test_a_max_age_on_a_payload_is_never_refreshed` |
| A sender, role or label nobody registered is `UNKNOWN_SYSTEM`, `UNKNOWN_ROLE` or `UNKNOWN_SOURCE`; a case naming such a sender or label doesn't open | `test_what_an_event_names_is_registered`, `test_a_case_naming_an_unregistered_sender_or_label_doesnt_open` |
| A misspelt payload field is `EXPRESSION_INVALID`, and fails its rule at runtime | `test_a_misspelt_payload_field_is_refused_and_fails_its_rule` |
| A wait open at the opening keeps the case from closing at once: no `CLOSES_AT_OPENING` | `test_a_wait_open_as_the_case_opens_keeps_it_from_closing_at_once` |
| A loop that comes round through an event is never claimed | `test_a_loop_that_comes_round_through_an_event_is_not_claimed` |
| A sender's roles are roles the case names, and give sight of its ordinary values | `test_a_sender_is_a_role_the_case_names` |
| On Temporal, a closed case refuses an event at the client, and so does an ID no case has, each saying which; nothing starts a workflow | `test_a_closed_case_refuses_an_event_at_the_client`, `test_an_event_to_an_id_no_case_has_is_refused_at_the_client` (both `tests/test_temporal_events.py`) |
| On Temporal, an event is decided as in memory, and a refusal is recorded, naming its sender, while the case waits on | `test_an_event_on_temporal_is_decided_as_in_memory` (`tests/test_temporal_events.py`) |
| On Temporal, a wait holds the case until its event arrives | `test_a_wait_on_temporal_holds_the_case_until_its_event_arrives` (`tests/test_temporal_events.py`) |
| A person's event crosses Temporal with exact values | `test_a_persons_event_crosses_with_exact_values` (`tests/test_temporal_events.py`) |
| Arrival counts cross continue-as-new; every field of the state crosses | `test_arrivals_cross_continue_as_new` (`tests/test_temporal_events.py`, seen failing with the count left out), `test_a_carried_state_reads_back_as_it_was` (`tests/test_temporal_case.py`) |
| On Temporal, a signal that comes with the close, an event or a person's request, is refused and recorded after the closed line, never lost; nothing it carries lands | `test_an_event_that_comes_with_the_close_is_refused_and_recorded`, `test_a_persons_request_that_comes_with_the_close_is_refused_and_recorded` (both `tests/test_temporal_events.py`, seen failing first) |
| A history recorded before 11d replays: the new signal changes nothing that was recorded | `test_a_history_from_before_11c_replays` (`tests/test_temporal_case.py`), `test_a_workflow_history_from_before_11c_replays` (`tests/test_temporal_workflow_step.py`) |
| Every decision of every in-memory test shows each pending item, an open wait included | the invariant, `tests/conftest.py` and `tests/invariants.py`, run after every decision of the tests above |
| The guide's definitions, histories and refusals are what the engine does | `test_the_guides_definitions_are_these_tests`, `test_the_guides_histories_are_what_the_engine_records`, `test_the_guides_refusals_are_what_the_engine_says`, `test_every_refusal_in_the_guide_is_tested` |
| No line, refusal or issue of 11d quotes a value an event carried | `test_no_event_line_or_issue_quotes_a_value` |

---

## 11e. Rules that update the case file

### What this part is for

Until 11e every value in the case file is stamped by whoever writes it, whatever it read: the
opening by the opener, a form by the person, an output by its contract, a payload by its sender
(brief, D34, D36). 11e lets a rule compute a field from other fields, `"then": {"set": {"owed":
<expression>}}`, so a field's origin now depends on other fields' origins. The lesson is that
**provenance follows the value, through the condition too**: a computed value comes from, reveals,
and is as old as everything its rule read. Without that, `set` would launder untrusted data: a
rule could turn the customer's estimate into a trusted-looking `large_claim = true`, and a second
rule could reach a milestone on it.

The sketch, the cases guide's ("Rules that update the case file"), on the claim:

```json
"work_out_owed": {
  "display": {"title": "Work out what is owed"},
  "on": {"reached": "assessed"},
  "then": {"set": {"owed": {"-": [{"var": "payout"}, {"var": "excess"}]}}}
}
```

```
work_out_owed#1 on reached assessed: setting owed, from person:ana, system:opener
```

User-facing description: `docs/guides/cases.md`, "Rules that update the case file", written
before building. Decision: brief, D42.

### How the session went

The design was read afresh from the docs, 2026-10-19: 11d's session had drafted choices for
`set` (its choices 16–23) that were never recorded on `main`. The warm-up first (learning question
36's follow-up, "can't remember"; recorded in the log), then a question: is `goodwill` a step? (Yes:
an activity step that never starts by itself, behind a team lead's approval.) Fourteen choices and
a split were put with a recommendation each, and answered "all as recommended, one pull request",
2026-10-19.

### Decided in the session

All as recommended, 2026-10-19.

**What `set` writes:**

1. **Shape.** `"then": {"set": {"<field>": <expression>}}`. It names declared case-file fields
   only, never `<step>.<field>`, an outcome or `<event>.<field>`: those belong to a contract or a
   sender, and setting them would misreport where they came from (a `Name` holds no `.`, so the
   shape refuses them). No list field (`fits` can't check a list value yet, as in 11d); a reference
   field only from a reference field of its system, read as it is (brief, D30). Every expression
   reads the case file as it was when the condition was read, so the order of keys in `set` doesn't
   matter. Inside one `then`: stop, **set**, reach, start, so a step a milestone admits reads the
   new value. **A rule acts whole or not at all:** every value is computed before anything acts;
   if one can't be read, the firing fails, needs attention, and nothing in its `then` acts; a
   retry reads it all again.
2. **Types.** Statically, `EXPRESSION_INVALID` at `rules.<r>.then.set.<f>` when the expression's
   type isn't the field's. At runtime, the rule's type check (brief, D35) fails the firing first,
   and the value is checked against the field again with `fits`, on nothing validation did. Messages
   name the field and the kinds, never the value.
3. **One kind of writer per field** (brief, D9 extended). A field is given at the opening, set by
   people's forms, or set by rules: never two of these, refused when the definition is read; the
   opening giving a rule's field is refused, as it is for a form's. Several rules may set one
   field. Set aside: rules overwriting an opening's or a form's value, which would silently undo a
   named person's answer; two fields (`asked_priority`, `priority`) say the same openly.
4. **No value from nobody.** A `set` whose expression and rule's `when` read no field is refused
   when the definition is read: a field with no sources can't exist today (10c: `validate_case`
   raises on `NoSources`). A milestone says a fact without data. Set aside: a new `definition:`
   source, a change to D12's vocabulary.

**Provenance follows the value:**

5. **Sources.** A written value carries the sources of every field its expression and its rule's
   `when` name (both branches of an `if`, as for an input, brief, D36), plus the field's mark. The
   moment doesn't count, as in 11b. A field named but not set yet counts what its writers could
   give (brief, D39). So Ana's `payout` feeding `owed` keeps Ana from approving `pay` given `owed`
   (brief, D11): `someone_else` already reads the recorded sources.
6. **Setting informs; it never decides** (brief, D38). A rule that only sets acts on untrusted
   data, its value carrying it, and gets no `UNTRUSTED_TRIGGER`; one that also reaches or stops
   doesn't act at all, as 11b's starts.
7. **Sensitive (brief, D31).** A value computed from a sensitive field, in the expression or the
   condition, is set only on a field declared sensitive; refused when read otherwise. Computed on
   plain values in the worker, written wrapped. This keeps `SENSITIVE_TO_WORKFLOW` a proof.
8. **Visibility (brief, D30).** A set field's `visible_to` is no wider than that of any field it
   was computed from, the condition included; refused when read otherwise. Known limit, for the
   checkpoint: a milestone a rule reaches on a narrowed field is seen by everyone already.
9. **Freshness (brief, D33).** Obtained when the oldest fact it read was, by the firing
   (`work_out_owed#1`), never "now". A `max_age` on it bounds every fact it was computed from. It
   can never be fetched again: stale, the step needs attention, saying it was computed by the
   firing (`refreshable` today would say "it came from the opening", a line that lies);
   `NEVER_REFRESHED` warns.

**The fixpoint, and who writes:**

10. **`case_sources` becomes a fixpoint grown from nothing,** used by validation and by the runtime
    for unset fields, with two sets per field: **may** (the union of what any write could carry)
    and **surely** (what every writer always carries: a rule's is what it reads surely, a field's
    the intersection over its writers). Errors read *surely* (a proof), warnings *may*. With one
    union, `INPUT_POLICY` and `UNTRUSTED_TRIGGER` would claim "refused every time" of a field one
    rule writes from untrusted data and another from a person's answer: they would silently stop
    being proofs. It ends: both only grow, over finitely many fields and sources. A test shows a
    case one pass gets wrong.
11. **`WRITER_DECIDES` (warning):** a refusal that holds for some writers of a value and not
    others, at a rule's `when`, an input's policy, or a `when` steering which step starts. The
    message names the writers, never values. One issue per place: an error first, then
    `OPENER_DECIDES`, then `WRITER_DECIDES`.
12. **What the 10d checks claim.** A value only rules set is surely set behind a milestone only
    rules setting it reach (true by choice 1's order and "whole or not at all"), or behind a guard;
    elsewhere `MAY_BE_UNSET`. This closes a hole like 11d's: `surely_set` reads any value that is
    neither a step's nor a form's as "given at the opening (assumed)", so it would never warn.
    `SET_AFTER` only where every rule setting it fires after the reader is done; otherwise
    `MAY_BE_UNSET`. Any `max_age` on it is `NEVER_REFRESHED`.
13. **Which write stands:** the latest; every write is a line naming the field and its sources,
    never the value. Two rules setting one field in one decision: in order (moments as they come,
    rules as written), the latest stands, both recorded. Set aside: refusing the second. A change
    to what an open approval saw withdraws it, and a given one lapses (brief, D25): `follow`,
    proved by a test.
14. **No "field set" moment now** (doors row 14). `set` queues no moment and starts nothing, so
    11b's bound on a decision holds as it is. The door stays open: a later `{"set": <field>}`
    moment would fire at most once per field in a decision, so moments stay bounded by the fields.

**Stated, with no choice needed:**

- **When `set` acts:** where rules act today; not once every `closes_when` milestone is reached,
  nor while a failed run holds the close, nor while closing, never once closed (`nothing_decided`),
  each such firing recorded "not applied".
- **Every check that reads writers or sources gets a run first**, kept as a test: `can_happen`,
  `CLOSES_AT_OPENING`, `NEVER_FIRES`, known and surely set, `OUTCOME_UNREAD` (a set expression
  reads), `MAY_BE_UNSET`, `SET_AFTER`, `NEVER_REFRESHED`, `APPROVAL_ELSEWHERE`, `INPUT_POLICY`,
  `OPENER_DECIDES`, `NO_SOURCES`, `UNTRUSTED_TRIGGER`, `APPROVER_CANT_SEE`, `SENSITIVE_TO_WORKFLOW`,
  `REFERENCE`, `INPUT_TYPE`, D11's exclusion, and 11b's steering.
- **On Temporal:** no new signal; set values cross continue-as-new in `values`, `sources` and
  `obtained`, a sensitive one encrypted; replay decides the same; a history from before 11e
  replays.
- **D42,** drafted with this note. No new dependency.
- **One pull request.** Building the runtime before the checks would leave `main` with checks
  that are no longer proofs, which is what the reviews of 11a–11d each found.

### The doors left open (the checkpoint's 11e section)

| Row | How 11e keeps it open |
|---|---|
| 14 Variable listeners | no "field set" moment; a later one fires at most once per field in a decision, so each decision stays finite (choice 14) |
| 6 One step per item of a list | a list field is never set (choice 1), never packed into a text, so a later list type reads nothing differently |

### Where the code goes

- `case/definition.py`: `Then.set`; one kind of writer per field; a set reading nothing; sensitive
  and visible checks; `Then.does_something` counts `set`.
- `case/rules.py`: computing every value before acting; writing them, with sources, time and the
  firing; the order stop, set, reach, start; the history line.
- `case/writers.py`: `case_sources` as a fixpoint, *may* and *surely*; a rule as a writer.
- `case/runtime.py`: the opening refuses a rule's field; `refreshable` says a value was computed.
- `case/types.py`: a set expression's type against its field. `case/known.py`, `case/warnings.py`:
  surely set, `MAY_BE_UNSET`, `SET_AFTER`, `NEVER_REFRESHED`, `OUTCOME_UNREAD` with set
  expressions. `case/flow.py`: errors on *surely*, `WRITER_DECIDES` on *may*.
- `temporal/`: nothing new; `tests/test_temporal_set.py` proves set values cross and replay.
- `core/approval.py`: D11's refusal says truthfully when a rule computed the value.
- `docs/guides/cases.md`: "Rules that update the case file", and `WRITER_DECIDES` in its table.

### Seams the tests use

- `parse_case(data)`: `CaseInvalid` for each shape refused.
- `run_case(...)`: `history`, `needs_attention`, `state` (values, sources, obtained), `waiting_for`;
  `retry(entry, who)`; `CaseRefused`, `AnswerRefused`.
- `validate_case(case, catalog)`: the issues above.
- The Temporal test server: a case whose rule set a value continues as new and replays.
- The guide's section, read as the engine runs it.

### Slices, in order

Each starts with its negative test, seen failing for the right reason.

0. **The docs first:** the guide's section, D42, this note.
1. **The shape.** Negative: `set` naming what isn't a field. Then a list field, a field a form or
   the opening also writes, a set reading nothing.
2. **Writing, in memory.** Negative: a set value that can't be read fails the firing, and nothing
   in its `then` acts. Then the value lands, typed, with its sources and the history line; the
   order inside `then`; the latest stands; the opening refuses a rule's field.
3. **Provenance at work.** Negative: a constant set under an untrusted condition is untrusted, and
   a rule reaching on it doesn't act. Then an input policy, D11's exclusion, an approval that
   follows the value.
4. **Time.** Negative: a stale computed value is never fetched again, saying it was computed.
5. **Sensitive and visible.** Negative: a value set from a sensitive field on a plain one is
   refused. Then visibility, and a sensitive value kept wrapped.
6. **The close.** Negative: a `set` once `closes_when` is complete is not applied.
7. **Validation stays a proof.** Negative: a definition one pass gets wrong. Then *may* and
   *surely*, `WRITER_DECIDES`, and each check in "Stated", each with its run.
8. **On Temporal.** A set value crosses continue-as-new and replays the same.
9. **The guide, as the engine does it, and the promises.**

### Decided while building

- **"Surely" is a question, not a set** (slice 7; corrects choice 10 and D42's draft). The note
  had *surely* sources as the intersection over a field's writers. That would have weakened an
  existing proof: a field two tasks' forms set is stamped `person:answering t1` by one and
  `person:answering t2` by the other, so the intersection is empty, and an `only_from` input
  reading it would have dropped from an error to a warning. What a check needs is "refused
  whichever writer wrote it". Every policy refuses a set of sources when one of them is refused,
  and a set value comes from the union of what its rule read, so a rule's write is always
  refused when its field's mark is, or a value it reads always is. That answer is grown from
  nothing too (`writers.always`), once per policy and opener. A value with no sources at all (a
  literal) is asked directly, since `only_from` refuses it. D42 is worded so, before merging.
- **Each place that claimed an error on sources now asks the same two questions:**
  `UNTRUSTED_TRIGGER`, `INPUT_POLICY` at an input, at a condition steering what is sent (11b),
  and at a plan step's input; `NEVER_REFRESHED`'s "always needs an approval". Each was seen
  claiming a false error first. `OPENER_DECIDES` comes before `WRITER_DECIDES`, one issue per
  place.
- **Two lines that lied, as the note foresaw:** `refreshable` said a stale computed value "came
  from a person"; `NEVER_REFRESHED` said it came "from the opening". Both now say it was computed,
  by which firing or which rule. And D11's refusal said `sam set owed` of a value a rule computed
  from Sam's answer; it now says `sam's answer is in owed, which a rule computes and pay uses, so
  cannot approve it` (plans keep their wording: nothing computes their fields).
- **What a rule doesn't do on untrusted data** names its sets too: `reaches and sets nothing`,
  and `UNTRUSTED_TRIGGER`'s "it never reaches large or sets large_claim".
- **A value set on an outcome field from a text** is checked as it is written: whether the text
  is one of the outcomes depends on the value. The message names the outcomes, never the text.
- **`fits_type` moved from `flow.py` to `types.py`,** so the runtime's rule check and validation
  share it; `set_by` in the runtime gave way to `definition.form_fields`, beside `rule_fields`.
- **The Temporal test has its own file,** `tests/test_temporal_set.py`, where the draft named
  `tests/test_temporal_case.py`; it also replays the new run's history.
- **Seen passing at once, as the note predicted:** an approval following a set value (`follow`
  compares values whoever changed them), `set` stopping with the close (`nothing_decided`), and
  `NEVER_FIRES`, `CLOSES_AT_OPENING`, `SENSITIVE_TO_WORKFLOW`, `REFERENCE`, `INPUT_TYPE` and
  `APPROVER_CANT_SEE` with set fields, each kept as a test. A probe found a rule that never
  fires still getting `MAY_BE_UNSET` for its condition beside `NEVER_FIRES`, as before 11e; left
  as it is (not this layer's).

### Promises

Every test is in `tests/test_set.py` unless said otherwise. Checked against the files once built,
2026-10-19: every test named here exists where it says.

| Promise | Test that would fail |
|---|---|
| `set` names declared fields only; a list field, a field a form writes, and a set reading nothing are refused when read; a constant under a condition is taken | `test_set_names_a_field_of_the_case_file`, `test_a_list_field_is_never_set`, `test_a_field_has_one_kind_of_writer`, `test_a_set_reading_nothing_is_refused`, `test_a_constant_set_under_a_condition_comes_from_what_the_condition_read` |
| A reference field is set only from a reference field of its system, read as it is | `test_a_reference_is_set_only_from_its_systems_reference`, `test_a_reference_is_set_from_its_systems_reference_read_as_it_is` |
| The opening giving a field a rule sets is refused | `test_the_opening_never_gives_a_rules_field` |
| A set value lands with the sources of everything its rule read, obtained by the firing, and the line names the field and the sources, never the value | `test_a_set_value_comes_from_everything_its_rule_read`, `test_no_set_line_or_issue_quotes_a_value` |
| A value that can't be read, or isn't of its field's type, fails the rule, and nothing in its `then` acts; a retry reads it again | `test_a_set_that_cant_be_read_fails_the_whole_rule`, `test_a_set_of_another_type_fails_the_rule`, `test_a_text_set_on_an_outcome_field_is_checked_when_written`, `test_a_retried_set_reads_again` |
| Values are read on the case file as the condition saw it; set comes before reach | `test_set_values_are_read_together`, `test_a_milestone_a_rule_reaches_sees_what_it_set` |
| The latest write stands; two rules in one decision set in order, both recorded | `test_the_latest_write_stands` |
| A constant set under an untrusted condition is untrusted; a rule that only sets acts; one that also reaches doesn't act at all; a rule reaching on the set value doesn't act | `test_a_constant_under_an_untrusted_condition_is_untrusted`, `test_a_rule_that_sets_and_reaches_on_untrusted_data_doesnt_act`, `test_untrusted_data_cant_decide_through_a_set_field` |
| An input policy refuses a value computed from untrusted data | `test_an_input_policy_refuses_a_value_computed_from_untrusted_data` |
| A person whose answer a set value carries can't approve a step given it, and the refusal says so truthfully | `test_whose_answer_a_set_value_carries_cant_approve` |
| A set changing what an approval saw withdraws it | `test_a_set_changing_what_an_approval_saw_withdraws_it` |
| A set value is as old as the oldest fact it read; stale, it is never fetched again, saying it was computed | `test_a_set_value_is_as_old_as_its_oldest_fact`, `test_a_stale_set_value_is_never_fetched_again` |
| A value computed from a sensitive field, by its value or its condition, is set only on a sensitive field, and kept wrapped | `test_a_value_from_a_sensitive_field_is_set_only_on_a_sensitive_one`, `test_a_condition_on_a_sensitive_field_counts_too`, `test_a_set_sensitive_value_stays_wrapped` |
| A set field is seen by no role that can't see what it was computed from; it may hide more | `test_a_set_field_is_seen_by_no_one_its_sources_hide_from`, `test_a_set_field_may_hide_more_than_its_sources` |
| No `set` acts once `closes_when` is complete, or while the case closes | `test_set_stops_with_the_close`, `test_set_doesnt_act_while_the_case_closes` |
| Sources go round until nothing changes: a case one pass in written order gets wrong is right | `test_sources_go_round_until_nothing_changes` (seen failing with one pass) |
| A value some writers make untrusted gives `WRITER_DECIDES`, never a false error; one every writer makes untrusted stays an error: at a rule's condition, an input, a steering condition, a plan step | `test_a_field_only_some_writers_make_untrusted_warns`, `test_a_field_every_writer_makes_untrusted_is_refused`, `test_an_input_given_a_value_only_some_writers_make_untrusted_warns`, `test_an_input_given_a_value_every_writer_makes_untrusted_is_refused`, `test_a_condition_steering_on_a_set_field_is_claimed_only_where_proven`, `test_a_plan_step_given_a_set_field_is_claimed_only_where_proven` (each seen claiming the false error first) |
| A value only rules set is never assumed given at the opening: `MAY_BE_UNSET` where nothing ensures it, and the run fails so | `test_a_value_rules_set_may_be_unset`, `test_a_rule_reading_a_value_rules_set_may_find_it_unset` (both seen silent first) |
| It is surely set behind a milestone only rules setting it reach | `test_a_value_rules_set_is_surely_set_behind_their_milestone` (seen failing with the milestone proving nothing) |
| `SET_AFTER` only where every setting rule fires after the reader is done; a set on the opening reading what a person sets fails every time | `test_set_after_a_rule_is_claimed_only_where_proven`, `test_a_set_reading_on_the_opening_what_a_person_sets_fails_every_time`, `test_a_set_guarded_by_its_condition_is_not_warned` |
| A `max_age` on a set value is `NEVER_REFRESHED`, saying it was computed | `test_a_max_age_on_a_set_value_is_never_refreshed` (seen saying "the opening" first) |
| A set expression is type-checked, and counts as a reader of outcomes | `test_a_set_expression_is_type_checked`, `test_a_set_expression_reads_an_outcome` |
| The other checks hold with set fields: `NEVER_FIRES`, `CLOSES_AT_OPENING`, `SENSITIVE_TO_WORKFLOW`, `REFERENCE`, `INPUT_TYPE`, `APPROVER_CANT_SEE`; `UNTRUSTED_TRIGGER` names the sets | `test_a_set_only_rule_whose_moment_never_comes_never_fires`, `test_a_rule_setting_on_the_opening_doesnt_keep_the_case_open`, `test_a_workflow_step_given_a_value_computed_from_a_sensitive_one_is_refused`, `test_a_reference_a_rule_copies_goes_where_its_system_is_expected`, `test_an_input_given_a_set_field_of_another_type_is_refused`, `test_an_approver_who_cant_see_a_set_field_is_warned`, `test_a_rule_that_reaches_and_sets_on_untrusted_data_never_sets_either` |
| A rule that does nothing is refused, `set` counting as doing something | `test_a_rule_that_does_nothing_is_refused` (`tests/test_rules.py`) |
| A set value crosses continue-as-new, a sensitive one encrypted; a rule sets again in the new run; the new run replays the same | `test_a_set_value_crosses_continue_as_new` (`tests/test_temporal_set.py`), `test_a_carried_state_reads_back_as_it_was` (`tests/test_temporal_case.py`) |
| Every decision shows each pending item | the invariant, `tests/conftest.py` and `tests/invariants.py`, run after every decision of the tests above |
| The guide's section, its `WRITER_DECIDES` row and its quoted refusals are what the engine does | `test_the_guides_set_runs_as_shown`, `test_the_guides_writer_decides_is_what_validate_case_says`, `test_the_guides_set_refusals_are_what_the_engine_says` |

---

## 11f. Time

**Decided, 2026-10-20:** all sixteen choices as recommended, one pull request (the user, "all as
recommended, one pull request"). Choice 4 changes 11c's choice 31, which keeps its text and gets
a dated amendment; D44 (brief) records the layer, with a dated amendment to D40.

### What this part is for

A timer is a rule whose moment is time passing after another moment:

```json
"escalate": {
  "display": {"title": "Escalate a slow assessment"},
  "on": {"after": "5d", "since": {"started": "assess"}},
  "when": {"!=": [{"var": "assess.outcome"}, "done"]},
  "then": {"start": ["lead_review"]}
}
```

```
day 0  started assess#1                    → timer set: escalate since assess#1, due day 5
day 5  (no event; the timer is due)        → TimerDue stamped day 5, never "now"
       escalate#1 on 5d after assess#1 started: started lead_review
```

- **Time stays data** (brief, D33). The due time is the event time of the decision where the
  `since` moment came, plus `after`. The firing is an event like any other, stamped with that due
  time. `decide` still reads no clock.
- **A set timer holds the case (brief, D10); a rule that listens doesn't (brief, D41).** Once the
  `since` moment has come, the timer is a firing that will happen at a known time. Until then, the
  rule is only listening.
- **Purpose ending.** Without it, a timer would hold the case after its reason was gone: if
  `assess#1` is done on day 2, its timer should end then, not keep the case open until day 5. This
  is Flowable's orphan removal (`docs/layers/checkpoint-doors.md`, row 19), defined once for all
  timers.

### How the session went

The warm-up first: learning question 33's follow-up, answered "help me", then "walk me through
it" (recorded in the log). Then 11f was explained and sixteen choices were put, each with a
recommendation, 2026-10-19. This draft records them before the answers, at the user's request. Answered "all as recommended, one pull request", 2026-10-20.

### Decided in the session

All sixteen as recommended, 2026-10-20. Each is written as it was put.

1. **Shape.** Recommended: `on: {"after": "<age>", "since": <moment>}`.
   - `after` uses D33's format (`30m`, `12h`, `1d`) and must be at least one minute. It means one
     firing (doors row 16).
   - `since` takes one of D38's five moment shapes. A nested timer is refused, and so is a date
     from the case file; that one is a later shape (row 15).
   - `when` is read at the firing, on the case file as it is then (row 17).
2. **Setting and naming.** Recommended:
   - a timer is set in the decision where its `since` moment comes, but only while the case
     decides. Once the case is closing or its close is held, a timer that would be set is not,
     and a line says so (11a's "nothing new is decided");
   - it is named by its rule and its anchor: `escalate since assess#1`, `remind since
     cancelled#2`. When it fires, the firing gets the rule's next entry (`escalate#1`);
   - it lives in `state.timers`, which crosses continue-as-new.
3. **Purpose ending, in general (row 19).** Recommended:
   - a timer set on a run's start lives only while that run hasn't ended. A stop ends its timers
     through this rule (brief, D40);
   - a timer set on an instant (opened, reached, answered, an event's arrival) lives until it
     fires;
   - any close ends every timer. Each cancellation is a line in the history.

   What follows: "30 days after payment" anchors on the milestone `pay` reaches, not on `pay`'s
   start. The `sla` behaviour D10 describes ("cancelled when the step completes") then comes from
   this rule, with nothing added for patterns.
4. **A failed run hasn't ended for its timers.** Recommended: amend 11c's choice 31, with a date
   (see "What choice 4 changes", below). An operator's retry is the same run (brief, D26), and
   D17 says "an sla still escalates during a long outage".
5. **Firing.** Recommended:
   - a new event, `TimerDue(rule, since, at=due)`, decided like any other: the timer is removed,
     its moment is queued, and its rule fires;
   - a firing for a timer that isn't set is refused (fail closed: only the drivers make these
     events, from the state).
6. **Order, so replay decides the same.** Recommended:
   - before an event stamped `t` is decided, every timer due at or before `t` fires, in due order;
     timers due at the same second fire in the order they were set. At a tie with an event, the
     timer goes first: an event stamped `t` happened during that second, and the timer was due at
     its start;
   - one pure function in `case` gives "the firings due by `t`", and both drivers use it;
   - in memory, `later("5d")` advances time and fires what falls due, even at the end of a
     script.
7. **What holds the case, and where it shows.** Recommended:
   - a set timer is pending work. It stays out of `waiting_for` (brief, D24);
   - `run.timers` and `CaseReport.timers` list each set timer, soonest first: `escalate since
     assess#1: due 2026-10-24T09:00:00Z`. A due time is not a case-file value, so showing it
     quotes nothing from the case file;
   - the invariant in `tests/invariants.py` adds two checks: every set timer is listed, and no set
     timer has outlived its purpose.
8. **The close.** Recommended:
   - closing cancels every set timer, with a line for each (brief, D10);
   - a timer due at or before the close's own time fires first (choice 6). A timer due later is
     cancelled. Either way it is recorded and never lost, the same promise 11d's review made for
     signals;
   - a held close (a failed run holding it, brief, D34) also cancels timers. A held close never
     goes back to deciding, so they could never act. This is one line, said once, instead of a
     "not applied" line at each firing.
9. **Temporal.** Recommended:
   - the workflow keeps one workflow timer, for the earliest due time (`wait_condition` with a
     timeout). When it wakes, the loop decides the due firings, each stamped with its due time;
   - no new command: the timers follow `state.timers`;
   - continue-as-new (brief, D27):
     - a timer is state, not running work, so it doesn't hold back the switch;
     - the new run sets its workflow timer again from the carried state. A timer that fell due
       during the switch fires at once, still stamped with its due time;
     - it fires once: a timer is in the state until the decision that fires it removes it, so
       exactly one run fires it;
     - two tests on the time-skipping server: a timer due across the switch, and one due at the
       instant the switch happens;
   - replay: a state carried from before 11f reads as having no timers, and a fixture recorded
     before 11f replays.
10. **Staleness noticed by a timer** (brief, D33's "timers that would notice sooner come with
    rules"). Recommended: the engine sets no timer on its own; an author writes one (for example,
    a rule that starts the read again a day after the review is answered; the open approval then
    follows the case file, brief, D25).
    - Why: a timer the engine set would keep cases open and call systems nobody asked it to.
    - The approval sheet already shows each fact's age (brief, D33).
    - The guide gets that example, and a test runs it.
    - The alternative: when an approval waits on a fact, the engine sets a timer at the fact's
      `max_age` expiry. When it fires, a read is refreshed and a fact from a person needs
      attention.
11. **Trust (brief, D43).** Recommended: a timer set on a run's start carries what steered that
    run, so a rule on its firing that reaches or stops doesn't act. Timers set on the opening, a
    milestone, an answer or an arrival carry nothing: time passing is a fact.
12. **Validation stays a proof, and every check below is shown with a run.** Recommended:
    - `can_happen`: a timer fires only if its `since` moment can come;
    - `NEVER_FIRES`: a timer whose moment never comes, or comes only once every `closes_when`
      milestone is reached;
    - `CLOSES_AT_OPENING`: a timer set at the opening keeps the case open, so today's error would
      stop being a proof;
    - surely-set, `MAY_BE_UNSET`, `SET_AFTER` and `OUTCOME_UNREAD` treat a firing as happening at
      its `since` moment. That claims less, and claiming less never makes an error false;
    - `UNTRUSTED_TRIGGER`, `WRITER_DECIDES` and `INPUT_POLICY` reuse the fixpoint's `started
      <step>` value;
    - the loop checks (`NEVER_CLOSES`, `LOOPS_UNTIL_CLOSED`) are checked again with timer rules
      inside a loop.
13. **`NEVER_CLOSES` for a timer that re-arms itself.** Under choice 3, every way a timer could
    re-arm goes through a person, an event, or a run ending: a timer on a run dies with that run,
    and the anchors that fire with no person or event (the opening, a milestone) happen only once.
    So there is nothing to prove. Recommended: record this in D44, and add a test that runs the
    would-be loop (`since started ping`, `then start ping`) and shows it ends. A repeating key, if
    one ever comes (row 16), brings its own `NEVER_CLOSES`. If choice 3 is rejected, this error
    has to be built.
14. **A due date is a view of a timer (row 30).** Recommended: the report line in choice 7 is that
    view. If the inbox ever shows a task's due date, it will read the timer set on that task's
    run.
15. **Records.** Recommended: D44, written before building. The cases guide gets a "Rules on time"
    section, and its examples run as tests. No new dependency.
16. **Size.** Recommended: one pull request, about nine slices:
    1. the shape;
    2. setting and firing in memory, with the order;
    3. purpose ending and the close;
    4. the reports and the invariant;
    5. trust;
    6. validation;
    7. Temporal and continue-as-new;
    8. staleness;
    9. the guide and the Promises table.

    That is about the size of 11e. The alternative, two pull requests: split after slice 6, 11f1
    in memory with validation, 11f2 with Temporal, continue-as-new and staleness.

### What choice 4 changes

11c's choice 31 (above, under "Timers (11e), only what it needs") says: "A run has ended once it
has its final status (`done`, `rejected`, `failed`, `cancelled`). A run whose stop is requested
and still running hasn't ended; a stopped run's timers end with it, when it does." D40's last line
says the same.

Choice 4 would take `failed` out of that list, for timers. A failed run waits for a person, and an
operator's retry runs it again as the same run (brief, D26). So it hasn't ended for its timers:
they stay set, and a rule on one still acts unless the close is held (choice 8). Kept as written,
an `sla` would stop escalating the moment its step needs attention, against D17's "an sla still
escalates during a long outage". A failed run that is then cancelled by a close ends its timers
with the close.

Agreed, 2026-10-20: choice 31 and D40 keep their text, and each has an amendment saying when it
was added (CLAUDE.md: decisions are never rewritten). Nothing built depended on choice 31: no
timer existed before 11f.

### Where the code goes

- `case/definition.py`: the timer's shape, `{"after", "since"}`, a moment of its own whose
  `since` is one of the five others; `anchor`, the moment a timer is set on (the moment itself for
  any other rule), which every check reads.
- `case/timers.py` (new): setting a timer on its moment, firing one, ending those whose purpose
  ended, the firings due by a time, and how a timer reads (its line, its due date in UTC, worked
  out from whole seconds: `case` reads no `datetime`, layer 0's boundary).
- `case/state.py`: `Timer`, `state.timers`, the `TimerDue` event; a moment names the entry it
  came from (`assess#1`, `cancelled#2`), and a timer's moment the rule it is for.
- `case/rules.py`: timers are set as their moments are taken; a timer's firing fires its rule
  alone. `case/runtime.py`: `TimerDue` decided; `case/closing.py`: a set timer is pending work,
  and closing cancels it.
- `case/memory.py`, `testing.py`: the driver fires what falls due before each event, and
  `later(...)` moves time on; `run.timers`.
- `case/reach.py`, `case/validate.py`, `case/warnings.py`, `case/writers.py`, `case/flow.py`:
  each check reads a timer by its anchor where that claims less, never more (choice 12).
- `temporal/cases.py`: one workflow timer for the earliest due time; `CaseReport.timers`.
  `temporal/carried.py`: timers cross continue-as-new.
- `tests/invariants.py`: no set timer outlives its purpose.
- `docs/guides/cases.md`: "Rules on time", written before building.

### Not in 11f

- A repeating timer (an `every`, with a count): not planned (row 16). Cron: after v1.0.
- A timer at a date read from the case file: a later shape of `since` (row 15).
- A condition on setting a timer: a later key (row 17).
- A timer the engine sets for a `max_age` expiry (choice 10).
- The renderer and `simulate` (11g); `sla`, `reminder` and the teaching warnings (11h).
- No new dependency.

### Seams the tests use

- `parse_case(data)` with a timer's `on`; `CaseInvalid` for a bad one.
- `run_case(...)` with `later(age)` in the script: `history`, `timers`, `closed`,
  `needs_attention`, `waiting_for`; `decide` with a `TimerDue`, for the refusals.
- `validate_case(parse_case(d), CATALOG)`: the issues of choice 12.
- The Temporal test server, skipping time: a timer fires stamped with its due time, across
  continue-as-new, and a history from before 11f replays.

### Slices, in order

Each starts with its negative test, seen failing for the right reason.

0. This note, D44, the guide's part, and a fixture recorded before any change.
1. The shape. Negative: a bad `after`, a timer `since` a timer, `since` what the case doesn't
   declare.
2. Setting and firing in memory, and the order. Negative: a firing for a timer that isn't set,
   or stamped with another time, is refused.
3. Purpose ending and the close. Negative: a timer on a run that ended doesn't fire; a close
   cancels it.
4. The reports and the invariant.
5. Trust. Negative: a timer on a steered start reaches nothing.
6. Validation, each check shown with a run.
7. Temporal and continue-as-new.
8. Staleness noticed by a timer an author writes.
9. The guide, run as written, and the Promises table checked against the tests.

### Decided while building

- **A timer's firing is its own rule's moment alone** (slice 2): two rules may wait the same age
  after the same moment, so the firing names its rule (`Moment.rule`) rather than being matched
  by what the history says. A moment now also names the entry it came from (`review#1`,
  `cancelled#2`), so a timer reads `2d after started review#1`; for a start, the entry is the run
  whose steering it carries (D43), which the trust check needed no other change to find
  (slice 5, seen failing with the firing's run left out).
- **The driver asks for one firing at a time** (`next_due`, slice 2): a firing may set a timer due
  before time stops moving, or end another, so the next is worked out afresh. It ends: each
  firing removes a timer, and a new one is due at least a minute after the firing's own time.
- **A set timer is pending work from slice 2,** not slice 3: without it, a case whose only work is
  a timer closed as it opened, with the timer still set.
- **Timers cross continue-as-new from slice 2,** as firings did in 11a: the guard on the carried
  state failed as soon as the state had a new field.
- **Due dates in UTC are worked out by hand** (`utc`, slice 2): `case` may import no `datetime`
  (layer 0's boundary), so a small named function, Howard Hinnant's `civil_from_days`, does it,
  and a test checks it against Python's own over leap years and centuries.
- **The guide's `run.timers` example runs on its own case** (slice 4): the guide test runs every
  Python block in one namespace, so the block opens the guide's refund itself.
- **What a timer that starts a read again does to an open approval** (slice 8), found by running
  it: the approval is withdrawn as its step's requirement starts again, and asked again once the
  fresh value lands, whether or not it changed (layer 8's "an open approval follows the case
  file"). The guide said "asked again if what it saw changed"; it now says what happens, and D44
  too, before merging.
- **On Temporal, one workflow timer at a time** (slice 7): `wait_condition` with a timeout, for the
  soonest timer, which Temporal cancels when an event comes first. With no timer set it is called
  as before, with no timeout, so a history recorded before 11f replays (two fixtures, recorded
  under `main` in slice 0). A timer already due when the loop comes round (one carried across a
  switch) fires without waiting.
- **Checked by mutation, not only by running:** the order test with the driver firing only at
  `later`; the trust tests with the firing's run left out; `CLOSES_AT_OPENING` and `NEVER_STARTS`
  with the anchor removed; the Temporal tests with no workflow timer. Each failed, then passed
  with the code put back.

### Promises

Every test is in `tests/test_timers.py` unless said otherwise. Each negative test was seen failing
for the right reason before its code was written.

| Promise | Test that would fail |
|---|---|
| A timer waits an age in D33's format, at least a minute | `test_a_timer_waits_an_age_of_at_least_a_minute` |
| A timer is never set on another timer | `test_a_timer_is_never_set_on_another_timer` |
| A timer set on what the case doesn't declare is refused, each name checked as on the moment itself | `test_a_timer_since_what_the_case_doesnt_declare_is_refused` |
| A timer names its age and its moment, and nothing else | `test_a_timer_names_its_age_and_its_moment` |
| A timer may be set on any of the five moments | `test_a_timer_is_set_on_any_of_the_five_moments` |
| A rule's `on` lists the timer among the moments it takes | `test_an_unknown_moment_is_refused_in_one_line` (`tests/test_rules.py`) |
| A firing for no timer set is refused, and changes nothing | `test_a_firing_for_a_timer_that_isnt_set_is_refused` |
| A firing stamped with another time than its due time is refused | `test_a_firing_stamped_with_another_time_is_refused` |
| A timer is set when its moment comes, due its moment's time plus its age, and keeps the case open | `test_a_timer_is_set_when_its_moment_comes` |
| It fires once its time has passed, its rule acts, and nothing is cancelled because time passed | `test_a_timer_fires_once_its_time_has_passed_and_its_rule_acts` |
| It never fires before its time | `test_a_timer_doesnt_fire_before_its_time` |
| A firing is stamped with its due time, never "now" | `test_the_firing_is_stamped_with_its_due_time`, `test_a_firing_stamped_with_another_time_is_refused`, `test_a_timer_that_fell_due_during_the_switch_fires_at_once_stamped_with_its_due_time` (`tests/test_temporal_timers.py`) |
| A timer due the second an event comes fires before it; on Temporal, a timer already due and a person's answer decided in the same workflow task, the timer first | `test_a_timer_due_with_an_event_fires_before_it`, `test_a_timer_already_due_and_an_answer_in_one_workflow_task_fire_timer_first` (`tests/test_temporal_timers.py`) |
| Timers fire soonest first, two due at one second in the order set | `test_timers_fire_soonest_first_and_in_the_order_set_at_one_second` |
| `later` fires what falls due, even at the end of a script, and timers set on the way fire in turn | `test_a_timer_falling_due_at_the_end_of_the_script_fires`, `test_a_timer_set_while_time_moves_on_fires_in_turn` |
| A timer's `when` is read at its firing, on the case file then | `test_a_timers_condition_is_read_when_it_fires` |
| Due times read as dates in UTC, with no `datetime` in `case` | `test_due_times_read_as_dates_in_utc` |
| A timer set on a run's start ends with it, needing no `when` | `test_a_timer_set_on_a_run_ends_with_it` |
| A stopped run's timers end with it; one asked to stop that runs on keeps them until it ends | `test_a_stopped_runs_timers_end_with_it`, `test_a_run_asked_to_stop_keeps_its_timers_until_it_ends` |
| A failed run's timer stays set, and its rule acts (D40, as amended by D44) | `test_a_failed_runs_timer_stays_set` |
| A timer set on an instant lives until it fires, keeping the case open | `test_a_timer_set_on_an_instant_keeps_the_case_open_until_it_fires` |
| A close cancels every timer, saying so | `test_a_close_cancels_every_timer`, `test_a_close_cancels_a_timer_on_temporal_and_the_case_ends` (`tests/test_temporal_timers.py`) |
| A timer due as the case closes fires first, never lost | `test_a_timer_due_as_the_case_closes_fires_first` |
| A close held by a failed run cancels every timer, once | `test_a_held_close_cancels_every_timer` |
| A timer isn't set once nothing new is decided, and a line says so | `test_a_timer_isnt_set_once_nothing_new_is_decided` |
| Reports list set timers soonest first, with their due time, never in `waiting_for` | `test_a_report_lists_set_timers_soonest_first_never_in_waiting_for`, `test_a_timer_fires_on_temporal_as_in_memory` (`tests/test_temporal_timers.py`) |
| No set timer outlives its purpose, after every decision | `test_the_invariant_finds_a_timer_that_outlived_its_purpose`, and the invariant (`tests/conftest.py`, `tests/invariants.py`) run after every decision of the tests above |
| A timer on a start untrusted data steered reaches nothing, saying what steered, never the value | `test_a_timer_on_a_start_untrusted_data_steered_reaches_nothing` |
| A value set on such a timer carries what steered the start | `test_a_timer_on_a_steered_start_sets_a_value_that_carries_it` |
| Time passing after an arrival is a fact: its rule decides | `test_time_passing_after_an_arrival_is_a_fact` |
| `ventoux check` reads the guide's timer with no issue | `test_check_reads_the_guides_timer` |
| A timer whose moment never comes, or comes only once every `closes_when` milestone is reached, is `NEVER_FIRES` | `test_a_timer_whose_moment_never_comes_never_fires`, `test_a_timer_on_the_last_closes_when_milestone_never_acts` |
| A timer set as the case opens keeps it open: no `CLOSES_AT_OPENING` | `test_a_timer_set_as_the_case_opens_keeps_it_open` |
| A timer's condition is read as firing at its moment: `MAY_BE_UNSET`, never `SET_AFTER`, where the value may be set by then | `test_a_timer_reads_what_may_be_set_by_then` |
| A step reading what only a timer after its own answer sets fails every time (`SET_AFTER`) | `test_a_step_reading_what_only_a_timer_after_it_sets_fails_every_time` |
| What steered a start reaches a timer on it: `UNTRUSTED_TRIGGER`, `WRITER_DECIDES` | `test_check_follows_what_steered_a_timers_start` |
| An input a timer on a steered start would send is `INPUT_POLICY` | `test_check_refuses_an_input_a_timer_on_a_steered_start_would_send` |
| A timer on its step's own start can never start it (`NEVER_STARTS`) | `test_a_timer_on_its_steps_start_can_never_start_it` |
| No timer re-arms itself: nothing to claim, and the run ends | `test_a_timer_cant_re_arm_itself` |
| A timer that may stop a loop lets it end: no `NEVER_CLOSES` | `test_a_timer_that_may_stop_a_loop_lets_it_end` |
| The engine sets no timer for a fact's age; an author's timer fetches a read again before anyone acts | `test_a_timer_an_author_writes_fetches_a_read_again_before_anyone_acts` |
| An open approval follows what the timer's read gives | `test_an_open_approval_follows_what_the_timers_read_gives` |
| On Temporal, a timer fires as in memory | `test_a_timer_fires_on_temporal_as_in_memory` (`tests/test_temporal_timers.py`) |
| A timer crosses continue-as-new and fires once; one that fell due during the switch fires at once | `test_a_timer_crosses_continue_as_new_and_fires_once`, `test_a_timer_that_fell_due_during_the_switch_fires_at_once_stamped_with_its_due_time` (`tests/test_temporal_timers.py`) |
| Timers cross in the carried state; a state from before 11f has none | `test_a_timer_crosses_in_the_carried_state` (`tests/test_temporal_timers.py`), `test_a_carried_state_reads_back_as_it_was` (`tests/test_temporal_case.py`) |
| A case whose timer fired replays; histories from before 11f replay | `test_a_case_whose_timer_fired_replays`, `test_a_history_from_before_11f_replays` (`tests/test_temporal_timers.py`) |
| The guide's definitions, histories and `run.timers` are what the engine does | `test_the_guides_definitions_are_these_tests`, `test_the_guides_histories_are_what_the_engine_records`, `test_the_guides_examples_run_as_written` (`tests/test_case.py`) |
| No timer line or issue quotes a value from a case file | `test_no_timer_line_or_issue_quotes_a_value_from_the_case_file` |
| The runtime refuses what the check refuses, on nothing validation did | each runtime test above runs through `run_case` alone |

---

## 11g. Reading rules

**Decided, 2026-10-20:** all eighteen choices as recommended (the user, "all as recommended"),
so 11g lands as two pull requests: 11g1, the reading (choices 1–6), then 11g2, the story and the
command line (choices 7–15). D45 (brief) records the layer.

### What this part is for

A rule is stored as JSON, and its behaviour has parts people get wrong: a timer's anchor, what
untrusted data can't do, when the condition is read, and that rules stop with the close. 11g
gives two ways to read a rule before it runs on a real case (brief, D7):

- **a reading**, the rule in plain words, worked out from the definition alone;
- **a story**, a timeline in simulated time that `ventoux simulate` plays on the in-memory engine,
  showing each firing beside its reading. A story says what it expects, so it is also a test.

The guide's timer, read:

```
chase_review: Chase a review left open for two days
  2d after each run of review starts: start chase.
  - The timer is set as each run of review starts, and ends with that run: done, rejected,
    stopped or cancelled. A failed run keeps it, since a retry is the same run.
  - While it is set, the timer keeps the case open.
  - Only while the case decides: not once the case is closing.
```

And D7's story ("Mon: assess starts; Wed: assessed; Thu: assess restarts"), on a claim whose
`escalate` rule waits 5 days after `assess` starts:

```
day 0 00:00  the case opens
             started assess#1: waiting for done by adjuster
             set escalate: 5d after started assess#1, due 2026-01-06T00:00:00Z
day 2 09:00  ana answers assess#1: done
             ana answered assess#1 done as adjuster
             assess#1 done
             cancelled escalate, 5d after started assess#1: assess#1 is done
day 3 09:00  ana proposes assess
             started assess#2: waiting for done by adjuster
             set escalate: 5d after started assess#2, due 2026-01-09T09:00:00Z
day 8 09:00  escalate#1 on 5d after started assess#2: starting lead_review
               ↳ escalate: 5d after each run of assess starts: start lead_review.
             started lead_review#1: waiting for reviewed by support-lead

At the end, day 9 00:00: open
  waiting for: assess by adjuster, lead_review by support-lead
  timers: none
```

The reader sees what the engine does: the timer measures from the latest start, ends with the
first run, and fires once for the second. (The engine lines are the history the engine writes
today; the exact wording of the story's own lines is choice 12.)

### How the session went

The warm-up first: learning question 38, answered 2026-10-20 (b came back, a didn't; recorded in
the log). Then 11g was explained
and eighteen choices were put, each with a recommendation, recorded as a draft awaiting answers,
then answered "all as recommended", 2026-10-20.

### Decided in the session

All eighteen as recommended, 2026-10-20. Each is written as it was put.

**The reading (the renderer)**

1. **A pure function of the definition.** Recommended: `read_rules(case) -> list[Reading]` in
   `case/reading.py`, taking a `CaseDefinition` and nothing else. A `Reading` is the rule's name,
   its title, its sentence and its fine print (choice 4). It is never given a case file, so it
   can't quote a value from one; a rule's own constants (`> 70`, `"done"`) are the definition's,
   and show through the expression renderer (`core/expressions/render.py`). The type checker
   holds this, and the layer test keeps I/O out of `case`.
2. **Names, not titles.** Recommended: a reading names steps, milestones, tasks and events by
   their names, as the history does, so a firing and its reading, printed side by side, use the
   same words; the rule's title heads the reading. Set aside: titles ("when Checked is reached"),
   which read more smoothly but differ from the history beside them, and two may be the same.
   This changes the wording 11a's choice 1 sketched ("if the risk score is over 70, reach high
   risk"): a condition reads as the expression renderer writes it, `kyc.risk_score > 70`. Prose
   for an expression would need a second renderer, and a second place to be wrong.
3. **The sentence.** Recommended: `<moment>[, if <condition>]: <actions>.`
   - The moment, one wording per shape:

     | `on` | reads |
     |---|---|
     | `"opened"` | `when the case opens` |
     | `{"reached": "checked"}` | `when checked is reached (once: a milestone is never undone)` |
     | `{"started": "assess"}` | `each time a run of assess starts` |
     | `{"answered": "review"}` | `each time review is answered, whatever the outcome` |
     | `{"event": "cancelled"}` | `each time cancelled arrives` |
     | `{"after": "5d", "since": …}` | `5d after` and the moment it is set on: `5d after each run of assess starts` |

   - The condition, through `render()`, followed by when it is read: `(read when it fires)`; for
     a timer, `(read when the timer fires, not when it is set)` (brief, D44).
   - The actions in the order the engine takes them (brief, D40, D42): `stop review, set owed to
     amount - fee, reach high_risk, start chase`.
4. **The fine print: each faithful part, only where it applies.** Recommended: a short line per
   part, each from a closed list of **clauses**, shown only on the rules it is true of:
   - *a timer on a run*: set as each run starts, ended with that run (done, rejected, stopped or
     cancelled); a failed run keeps it, since a retry is the same run (brief, D40 as amended by
     D44);
   - *a timer on an instant* (the opening, a milestone, an answer, an arrival): set when the
     moment comes, and lives until it fires;
   - *a timer holds the case*: while set, it keeps the case open (brief, D10);
   - *listening*: a rule on an event holds nothing until it fires (brief, D41);
   - *untrusted data can't decide*, on a rule that reaches or stops: if its condition reads
     untrusted data, it acts on nothing, saying why (brief, D38, D40, D42). On a rule set on a
     run's start, or a timer set on one, it adds "or if untrusted data steered that run"
     (brief, D43, D44). Nothing is added on the other moments: an answer is a person's, an
     arrival and the opening are facts, and a milestone never carries what steered anything;
   - *a set value carries what it read*, on a rule that sets and neither reaches nor stops: the
     value carries the sources of everything its rule read (brief, D42), and what steered the
     run, on a start;
   - *starts are checked against inputs*, on a rule that starts a step that takes inputs: what
     the condition reads, and what steered the run on a start, counts for that step's input
     policies (brief, D39, D43);
   - *only while the case decides*, on every rule, naming the definition's own `closes_when`:
     `not once paid is reached, nor while the case is closing` (brief, D34, D38); without
     `closes_when`, `not once the case is closing`.

   Two facts true of every rule are said once, above the readings, rather than on each:
   a rule remembers nothing between firings, and a rule whose condition or value can't be read
   acts on nothing and needs attention (brief, D17, D38).
5. **Every shape, and fail closed.** Recommended:
   - a moment, an action or an expression the renderer doesn't know raises `ReadingRefused`,
     naming it: never a sentence with a part left out;
   - **coverage is proven from the definition's own closed lists**, as for operators: a test
     reads the moment shapes from `RuleMoment`'s union (its tags) and the actions from `Then`'s
     fields, and asserts each has a row in the test's table of exact readings. A new moment or
     action added to the definition fails that test until the renderer and a row cover it.
     Expressions are covered by `render()`'s own tests (layer 2);
   - the negative test first: a shape the definition can't hold, forced past it, is refused.
6. **Faithful: each clause has a witness.** Recommended: every clause in the closed list of
   choice 4 has a **witness**, a test that reads a rule with that clause and runs a case where
   the engine does what the clause says, in one test:
   - *a timer on a run*: the run done, the timer cancelled; a run failed, the timer fires;
   - *untrusted data can't decide*: `reaches nothing: … untrusted data can't decide`, and on a
     steered start too;
   - *read when the timer fires*: a value changed between setting and firing, and the firing
     reads the new one;
   - *only while the case decides*: `not applied: paid is reached …`;
   - *the order of actions*: one rule with all four, and the history in that order;
   - and one each for the rest.

   A test asserts that the witnesses' clauses are exactly the closed list. So a clause can't be
   added without a run showing it, and an engine change that breaks a clause fails its witness.
   In 11g2 (choice 18) each witness becomes a story, so it reads as the reader will see it.

**The story**

7. **A story is data:** a JSON file, read with the standard library, as definitions are.
   Recommended keys, each refused if misspelt (`extra="forbid"`):
   - `title`;
   - `definition`, a path relative to the story file, so a story runs the real definition;
   - `file`, the values the case opens with; `opened_by`, if a person opened it;
   - `people`, each person's roles, as the API states them (brief, D22);
   - `fakes`, by contract reference (choice 10);
   - `timeline`, the entries in time (choices 8 and 9);
   - `until`, when the story ends (default: the last entry's time). Time moves on to it at the
     end, so a timer due by then fires;
   - `expect`, optional (choice 13).
8. **How a story names a moment in time.** Recommended: `"at": "day 3"` or `"day 3 14:30"`,
   counted from the opening, which is day 0 00:00. The opening is fixed at
   2026-01-01T00:00:00Z (the tests' `START`), printed in the header, so the timers' due times read
   as real dates. Time only moves forward: an entry earlier than the one before is refused.
   Set aside: weekday names, as D7 sketches them ("Mon", "Wed"), which are ambiguous after a
   week; and an `opens` date, which needs a date parser in `case` for little gain.
9. **What happens on the timeline.** Recommended: each entry has `at` and at most one of
   `answer` (`step` or `entry`, `outcome`, `by`, `form`), `propose` (`step`, `by`), `retry`
   (`entry`, `by`), `close` (`reason`, `by`), `send` (`event`, `payload`, `by`) or `finish`
   (`entry`: a held run ends, giving its fake's result). An entry with none of them is time
   passing. These are `run_case`'s script items, so stories and tests drive the engine the same
   way. Left out: `shown` and `forget`, which no rule reads.
10. **Activities are fakes the story declares.** Recommended:
    - by contract reference: `{"gives": {...}}`, `{"outcome": "declined"}` (a declared outcome)
      or `{"fails": "provider down"}`, with `"held": true` to keep its runs going until a
      `finish` entry. Workflow contracts the same way;
    - every contract the definition calls needs a fake, or the story is refused before it runs,
      listing each one missing (fail closed: nothing real is reached for);
    - nothing is sent: a fake is a value, and simulate imports no Temporal client and no network
      code. A `notify` contract's fake gives its draft's id; nothing leaves the process
      (draft, never send);
    - a definition with a plan step is refused, saying so: plans in a story are not in 11g;
    - the contracts are the development catalog's (`ventoux.testing.CATALOG`), as in `run_case`.
      A project's own catalog comes with `ventoux check` and the builder (layer 14), which needs
      the same thing.
11. **Simulated on the in-memory driver.** Recommended: `simulate(story, definition, catalog) ->
    Simulation`, pure, in `case/simulate.py`, with the format in `case/story.py`. It plays each
    entry through the in-memory driver's `until` and `carry`, so each history line gets the time
    of the decision that wrote it, a timer's firing its due time; the state and the history's
    lines are unchanged. Time stays data (brief, D33): the entries' times are the events' times,
    and nothing reads a clock. An entry the engine refuses (an answer from someone without the
    role, a close reason not declared) is shown as `refused: <why>` at its time, changes nothing,
    and the story goes on; any other error is a bug and stops it. The same story gives the same
    output, byte for byte.
12. **The output.** Recommended:
    - a header (the title, the definition, the opening time), then each rule's reading;
    - the timeline, grouped by time: the story's own entry first, by names only (`ana answers
      assess#1: done`, never the form's values), then the engine's lines as it wrote them.
      Each firing line is followed by its rule's sentence, `↳ escalate: …`. Timers set, fired
      and cancelled, refusals and lines such as `reaches nothing: … untrusted data can't
      decide` are the engine's own lines, so the output can't drift from the engine;
    - at the end, the status and every kind of pending work (brief, D10), each on its line:
      waiting for people, running steps, set timers with their due times, what needs attention,
      a step waiting for an event. None is left out; with nothing pending, it says
      `nothing pending`;
    - no value from the case file: the engine's lines quote none (earlier layers), the story's
      lines are names only, and the readings show only the definition's constants.
13. **What a story expects.** Recommended: `expect` holds the timeline's lines, each with its
    time, exactly as printed (without the readings), and the end's lines. Compared exactly, so
    nothing the engine did goes unchecked: a rule firing that nobody expected fails the story.
    A mismatch prints the first line that differs, expected and got, and a failing story fails
    its test. Set aside: expected lines as a subsequence, shorter to write, through which an
    unexpected firing passes. A story without `expect` only prints.
14. **Stories as tests.** Recommended: stories live beside their definition,
    `examples/<case>/stories/*.json`; one parametrized test runs every story under `examples/`.
    The guide's stories are among them, so the guide can't drift. 11h adds one story per
    pattern (curriculum, layer 11).

**The command line**

15. **One entry point, one command.** Recommended: `[project.scripts] ventoux =
    "ventoux.tooling.cli:main"`, with `argparse` (no dependency). One command: `ventoux simulate
    STORY.json`, which prints the simulation and exits 0 when its expectations hold (or it has
    none), 1 when one fails, 2 when the story or its definition can't be read, each problem on a
    line saying where, what is wrong, then what to do. Reading files and printing happen only in
    `tooling/cli.py`. `ventoux check` stays with the builder (brief, D34: layer 14); until then,
    a story with an empty timeline reads a definition's rules. Set aside: a second command,
    `ventoux rules DEFINITION.json`, printing the readings alone.

**Patterns, for 11h**

16. **Room for patterns, nothing built.** Recommended: 11h gives a pattern its own reading (D7's
    "Escalate to a senior adjuster if the assessment isn't finished within 5 days of its latest
    start"), and its expansion is raw rules, which `read_rules` reads as any other. In a
    simulation, a firing of an expanded rule then shows its pattern's sentence and its own. 11g
    adds no pattern field and no hook for one.

**Records and size**

17. **Records.** Recommended: D45, written before building, adding to D7: what a reading is (a
    pure function of the definition, every shape, fails closed, each clause witnessed), what a
    story is (its format, its time, its fakes, what it expects), and the one command. The cases
    guide gets "Reading rules" and "Simulating a story", written before building, their examples
    run as tests. No new dependency.
18. **Size: two pull requests.** Recommended:
    - **11g1, the reading** (choices 1–6): the renderer, its coverage and its witnesses as
      `run_case` tests. Pure code in `case`, about five slices;
    - **11g2, the story** (choices 7–15): the format, `simulate`, the output, expectations,
      stories as tests, the command line, and the witnesses moved into stories. About seven
      slices.

    Why: they are two kinds of code (a pure function; a data format with I/O around it), and the
    story is a new format people will write, worth its own review. The alternative: one pull
    request, about twelve slices.

### Where the code goes

- `case/reading.py` (new): `read_rules`, `Reading`, the clauses, `ReadingRefused`.
- `case/story.py` (new, 11g2): the story's format, its times (`day 3 14:30` to seconds).
- `case/simulate.py` (new, 11g2): playing a story on the in-memory driver, the timeline, the end,
  the expectations.
- `case/memory.py`: nothing new expected; `Driver` is used as it is.
- `tooling/cli.py` (new, 11g2): `main`, `simulate`; reading the files, printing, the exit code.
- `pyproject.toml` (11g2): the `ventoux` script.
- `examples/refund/stories/`, `examples/claim/` (11g2): stories, and the definitions they run.
- `docs/guides/cases.md`: "Reading rules" (11g1), "Simulating a story" (11g2).

### Not in 11g

- Patterns, their readings, their stories, and teaching warnings (11h).
- `ventoux check`, a project's catalog, and readings in the case map (layer 14).
- Plan steps in a story; `shown` and `forget` entries.
- Prose for expressions: conditions read as the expression renderer writes them.
- No new dependency.

### Seams the tests use

- `read_rules(parse_case(d))`: each reading's text; `ReadingRefused` for a shape it doesn't know.
- `run_case(...)` (11g1's witnesses): `history`, `timers`, `needs_attention`.
- `simulate(story, definition, CATALOG)` (11g2): the printed timeline, the end, and whether its
  expectations hold.
- `main(["simulate", path])` (11g2): what it prints and its exit code.
- The guide's examples, run as written.

### Slices, in order

Each starts with its negative test, seen failing for the right reason.

11g1:

0. This note, D45's first part, the guide's "Reading rules".
1. The moments. Negative: a moment the renderer doesn't know is refused; then each shape, and the
   coverage test over `RuleMoment`.
2. Conditions and actions. Negative: an action it doesn't know; then the order, and the coverage
   test over `Then`.
3. The fine print, each clause where it applies.
4. The witnesses, one per clause, and the test that they cover the closed list.
5. The guide, run as written, and the Promises table checked against the tests.

11g2:

0. D45's second part, the guide's "Simulating a story".
1. The format. Negative: a misspelt key, an entry with two actions, time going back, a missing
   fake, a plan step.
2. Playing it: entries, time passing, timers firing at their due time, refusals as lines.
3. The output: grouped by time, each firing beside its reading, the end's pending work, no value
   from the case file.
4. Expectations. Negative: a story whose expectation fails, saying the first line that differs.
5. Stories as tests; the witnesses as stories.
6. The command line: `ventoux simulate`, its exit codes.
7. The guide, run as written, and the Promises table checked against the tests.

### Promises

A draft, to be checked against the tests once built. Tests in `tests/test_reading.py` (11g1)
and `tests/test_simulate.py` (11g2) unless said otherwise.

| Promise | Test that would fail |
|---|---|
| A reading is worked out from the definition alone, and quotes only its constants | `test_a_reading_needs_only_the_definition` |
| A moment, action or expression the renderer doesn't know is refused, never left out | `test_a_shape_the_renderer_doesnt_know_is_refused` |
| Every moment shape the definition takes has a reading | `test_every_moment_the_definition_takes_is_read` |
| Every action the definition takes has a reading | `test_every_action_the_definition_takes_is_read` |
| A condition reads as the expression renderer writes it, read when the rule fires | `test_a_condition_reads_as_rendered_and_when_it_is_read` |
| A timer's condition is read when it fires, not when it is set | `test_a_timers_condition_is_read_when_it_fires` (witness) |
| Actions read in the order the engine takes them: stop, set, reach, start | `test_actions_read_in_the_order_the_engine_takes_them` (witness) |
| A timer on a run reads as ending with that run, kept by a failed run | `test_a_timer_on_a_run_reads_as_ending_with_it` (witness) |
| A timer on an instant reads as living until it fires | `test_a_timer_on_an_instant_reads_as_living_until_it_fires` (witness) |
| A set timer reads as keeping the case open | `test_a_set_timer_reads_as_keeping_the_case_open` (witness) |
| A rule on an event reads as listening, holding nothing | `test_a_rule_on_an_event_reads_as_listening` (witness) |
| A rule that reaches or stops reads as acting on nothing on untrusted data, and on a steered start | `test_untrusted_data_reads_as_deciding_nothing` (witness) |
| A rule that only sets reads as carrying what it read | `test_a_set_value_reads_as_carrying_what_it_read` (witness) |
| A rule that starts a step with inputs reads as checked against their policies | `test_a_start_reads_as_checked_against_inputs` (witness) |
| Every rule reads as acting only while the case decides, naming `closes_when` | `test_a_rule_reads_as_acting_only_while_the_case_decides` (witness) |
| Each clause has a witness, and the witnesses cover the closed list | `test_every_clause_has_a_witness` |
| The guide's readings are the renderer's | `test_the_guides_readings_are_the_renderers` (`tests/test_case.py`) |
| A story with a misspelt key, an entry with two actions, or time going back is refused, saying where | `test_a_story_that_cant_be_read_is_refused` |
| A story missing a fake for a contract its definition calls is refused before it runs, listing each | `test_a_story_without_a_fake_is_refused` |
| A story whose definition has a plan step is refused, saying so | `test_a_story_with_a_plan_step_is_refused` |
| Times are named from the opening, `day 3 14:30`, and events are stamped with them | `test_a_story_names_times_from_the_opening` |
| Time passing fires each timer due, stamped with its due time | `test_time_passing_fires_timers_at_their_due_time` |
| An entry the engine refuses is a line, changes nothing, and the story goes on | `test_a_refused_entry_is_a_line_and_the_story_goes_on` |
| Each firing is shown beside its rule's reading | `test_each_firing_is_shown_beside_its_reading` |
| Every kind of pending work is listed at the end; with none, `nothing pending` | `test_the_end_lists_every_pending_item` |
| No output line quotes a value from the case file | `test_no_output_line_quotes_a_value_from_the_case_file` |
| The same story gives the same output, byte for byte | `test_a_story_simulates_the_same_every_time` |
| Nothing real is called: only the story's fakes run | `test_only_the_storys_fakes_run` |
| A story whose expectation fails says the first line that differs | `test_a_failing_expectation_says_where` |
| Every story under `examples/` holds | `test_every_story_holds` |
| `ventoux simulate` exits 0, 1 or 2 as its story holds, fails or can't be read | `test_simulate_exits_as_its_story_does` (`tests/test_cli.py`) |
| The `ventoux` command is installed | `test_the_ventoux_command_is_installed` (`tests/test_cli.py`) |
| The guide's stories and their output are what `simulate` prints | `test_the_guides_stories_are_what_simulate_prints` (`tests/test_case.py`) |
| `case` stays free of the clock and I/O: reading the files is the command line's | `tests/test_layers.py`, as it is |
