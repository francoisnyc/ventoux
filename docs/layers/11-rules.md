# Layer 11: rules

Status: research done, 2026-10-16 (`docs/layers/11-research.md`, Flowable's CMMN engine at
`f6017e3`); the warm-up skipped at the user's request, 2026-10-17 (learning question 32 stays open, for the next layer); the split and 11a's choices **proposed, not yet agreed**. Nothing is built.

## What this layer is for

Until now a case reacts in one way only: after every event, admission asks each step "may you start
now?" (layer 8). That covers "pay once the review approves", not "if nobody has assessed the claim
in five days, escalate", "when the customer cancels, stop", or "once the check is done, mark the
customer high risk if the score is over 70". Layer 11 adds the **rule**: *when* something happens,
*if* a condition holds, *then* act on the case (brief, Simplifications, "one kind of rule"; D7).

User-facing description: `docs/guides/cases.md` gains a "Rules" section, written once each part's
design is agreed and before it is built (the curriculum's "document first").

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

Layer 11 lands as six pull requests, each with its section in this note, its own Promises table
and its own tutor review, as layers 8–10 did. Each part's choices are decided in its own session.

| PR | Builds | Codes (proposed) |
|---|---|---|
| **11a: the raw rule, inside the case** | `rules` in the definition: `on` (the case opened, a milestone reached, a step started), `when`, `then: reach`; when rules run in `decide`; a rule that can't be read needs attention; untrusted data can't decide (design question 17 decided); rules and the close; case validation kept true | `NEVER_FIRES`, `UNTRUSTED_TRIGGER` |
| **11b: rules that start and stop steps** | `then: start` (the engine proposes, through admission: the rework loop) and `then: stop` (what a close does, to one step; `cancellable` workflows, D29; never a failed run); the half of design question 17 that steers which step starts, built; validation: a step a rule starts can run; a rule that restarts a step for ever | `NEVER_CLOSES` extended |
| **11c: events from outside** | declared events with a typed payload and a source (D12); `on: {"event": ...}`; `then: set` (update the case file), which brings back the provenance fixpoint (D34, D36); listening is not waiting, and a step explicitly waiting for an event (D10); "arrival is a fact, content is not"; an event as a signal on Temporal | `UNTRUSTED_TRIGGER` for event content; `UNKNOWN_EVENT` |
| **11d: time** | timers, `on: {"after": "5d", "since": <moment>}`: set on their moment, pending work (D10), fired as an event stamped with its own due time (D33), never a clock `decide` reads; cancelled by their rule's purpose ending and by any close; crossing continue-as-new exactly (D27), replaying the same; staleness noticed by a timer (9d's carried note); reports list set timers (D24) | `NEVER_CLOSES` for a timer that re-arms itself |
| **11e: reading rules** | the plain-language renderer for every rule; `ventoux simulate`: a story on a timeline, with simulated time, showing when each rule fires; stories as tests | |
| **11f: patterns and teaching warnings** | `sla` (from the latest start; `since=first_start` explicitly), `reminder`, `four_eyes` (`count=2`, D11, D23), each expanding into raw rules visible in validation and views, each with a story test; D7's teaching warnings (a timer anchored on the first start of a repeatable step, a rule whose condition reads untrusted data, what is left of "rules that can never fire" once 11a's error has taken the proven ones) | warnings |

**Why this order.** 11a is the smallest rule that *acts*, and it brings the two things every later
part stands on: where rules run in `decide`, and case validation kept true once something other
than a step reaches a milestone (brief, D34). Starting and stopping steps (11b) need that loop and
reuse admission and closing. Events (11c) bring outside content, so trust and the update action
belong there, with the provenance fixpoint they need. Timers (11d) need moments to anchor on (11a)
and events (11c), since a timer firing is an event with its own time. The renderer and `simulate`
(11e) need every kind of rule to exist; the patterns (11f) are written in raw rules and tested as
stories, so they come last, as D7 says: "raw rules are the engine's concept, not the first one
people meet".

**Carried into layer 11, and where each lands:**

| Carried | Where |
|---|---|
| Case validation stays true once rules reach milestones and start or stop steps (`can_happen`, `NEVER_RUNS`, `CLOSES_AT_OPENING`, `NEVER_CLOSES`, `SET_AFTER`, the 10d warnings) | 11a for `reach`, 11b for `start` and `stop`, 11c for `set` |
| Provenance: a rule computing fields from fields brings the fixpoint back (D34, D36) | 11c, with `set` |
| `UNTRUSTED_TRIGGER` and design question 17 | decided in 11a; built in 11a (a condition that decides) and 11b (a condition that steers which step starts); event content in 11c |
| Time as event data stamped from workflow time (D33); timers as pending work (D10), across continue-as-new (D27), on replay; staleness noticed by a timer (9d) | 11d |
| Whether rules act once every `closes_when` milestone is reached (D34) | 11a (choice 7) |
| What a close does to timers (D10: cancelled) | 11d |
| `sla`, `reminder`, `four_eyes`, the renderer, teaching warnings, `ventoux simulate` | 11f, 11e, 11e, 11f, 11e (as in the table) |

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

### Proposed choices

Each is a proposal for the session; the alternative I'd set aside is said with it.

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
     (a step's `when`, a rule's `start`), is decided now and built in 11b. My proposal: a
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
   - `CLOSES_AT_OPENING` is unchanged: in 11a a rule starts nothing;
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

### Where the code goes (proposed)

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

### Seams the tests use (proposed)

- `parse_case(data)` with `rules`; `CaseInvalid` for a rule naming what doesn't exist.
- `run_case(...)`: `history`, `needs_attention`, `closed`, `waiting_for`; `retry(entry, who)` for a
  failed firing.
- `validate_case(case, catalog)`: the issues above.
- The Temporal test server, once: a case whose rule fired continues as new and replays.
- The guide's examples, run as written.

### Slices, in order (proposed)

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

### Promises (proposed: each test is written in its slice)

| Promise | Test that would fail |
|---|---|
| A rule's moment fires it once: the opening once, a milestone once, each started run once | `test_each_moment_fires_its_rules_once` (slice 1) |
| A rule whose `when` is false reaches nothing | `test_a_false_condition_reaches_nothing` (slice 1) |
| Rules on one moment fire in the definition's order; moments are taken in the order they happen | `test_rules_fire_in_order` (slice 1) |
| A milestone a rule reaches admits the steps that require it, in the same decision | `test_a_rule_reached_milestone_admits_steps` (slice 1) |
| A rule that can't be read needs attention and keeps the case open, never read as false | `test_an_unreadable_rule_needs_attention` (slice 2) |
| A misspelt outcome in a rule's `when` fails it (brief, D35) | `test_a_misspelt_outcome_fails_the_rule` (slice 2) |
| An operator's retry reads a failed rule's condition again | `test_a_retried_rule_reads_again` (slice 2) |
| A rule whose condition reads untrusted data reaches nothing, saying which value and source, never the value | `test_untrusted_data_cant_decide` (slice 3) |
| Once every `closes_when` milestone is reached, no rule acts, and each firing says why | `test_rules_stop_with_the_close` (slice 4) |
| A definition with a rule that can never fire is refused (`NEVER_FIRES`) | `test_never_fires` (slice 5) |
| A rule whose condition reads always-untrusted data is refused (`UNTRUSTED_TRIGGER`) | `test_untrusted_trigger` (slice 5) |
| A step requiring a milestone only a rule reaches is not `NEVER_RUNS`; a deadlock a rule breaks is not `DEADLOCK` | `test_rules_count_in_what_can_happen` (slice 5) |
| A milestone a rule may reach proves nothing about values (`MAY_BE_UNSET`, `SET_AFTER`) | `test_a_rule_reached_milestone_sets_nothing` (slice 5) |
| A rule's condition reads an outcome (`OUTCOME_UNREAD` silent) and is type-checked (`EXPRESSION_INVALID`) | `test_rule_conditions_are_checked` (slice 5) |
| A case run without validation refuses the same at runtime | the runtime tests of slices 1–4 use no validation |
| A rule's firings cross continue-as-new, and replay decides the same | `test_rule_firings_cross_continue_as_new` (slice 6) |
| No message quotes a value from a case file | each slice's messages, checked in slice 7 |
