# Checkpoint: doors left open

Status: drafted 2026-10-17, after 11a was merged and before 11b, so that 11b–11d (11b–11e, as
renumbered below) can check each of their choices against it, as 11a's choice 10 did. A draft, not
the checkpoint: the checkpoint itself (each blocked row unblocked, or recorded in the brief as a
deliberate limit) stays where the curriculum puts it, before layer 12. No decision is changed here.
*Renumbered 2026-10-18, in 11b's session:* 11b was split into 11b (rules that start steps) and 11c
(rules that stop steps), so events, time, reading rules and patterns became 11d to 11g; the table
and the sections below use the new letters. Two things found in 11b are added as rows 31 and 32.
*Renumbered again 2026-10-19, in 11d's session:* 11d was split into 11d (events from outside) and
11e (rules that update the case file), so time, reading rules and patterns became 11f to 11h;
the table and the sections below use the new letters (brief, D41).
*Brought up to date 2026-10-22, after layer 11 was merged in full* (11a–11h2, the fixes of the
retry rejected, the untrusted moment and the check's proofs, and the wrap-up: pull requests #24
and #26–38). The table now says what layer 11 built and where each door held; rows 34 to 37 are
added from the notes' known limits; "Choices before layer 12" lists what the user decides.
*Closed 2026-10-22:* the user answered every choice as recommended, adding a line to choice 4.
The deliberate limits are D48 in the brief, with dated amendment lines; choice 10's rows are in
the brief's deferred list; "Done when" is checked row by row below. Choices 4, 5, 6 and 8 need
code, each built test-first in a pull request after this one.

## What this note is for

Layer 12 publishes the definition format and lets open cases depend on it. After that, a concept
missing from the format costs a migration, not an edit. This note lists what Flowable's CMMN engine
offers and Ventoux doesn't (or does differently), and for each one asks: can it still be added
later without changing what an existing definition means?

"Blocked" means: adding it would change the meaning of a definition already written, or would
need a merged decision rewritten. Adding a new optional key, a new step kind, a new moment or a new
value is not blocking: a definition has no unknown keys (every shape refuses them), so an old
definition simply doesn't use the new one. Such an addition is still a decision recorded in the
brief (D38: "adding a moment is a decision recorded here, like an operator").

One consequence, used in the choices below: **refusing now keeps a door open; allowing now may
close one.** A shape refused today can be accepted later, and no published definition changes
meaning, since none uses it. A shape accepted today and refused (or read differently) later breaks
every definition that uses it.

## Where the Flowable references come from

Flowable's engine was cloned read-only again for this note, at the same commit as the research
(`f6017e3`, 2026-10-16), into the session's scratch directory, never into this repository. The
prefixes are the research's (`docs/layers/11-research.md`), plus one:

- `engine/` is `modules/flowable-cmmn-engine/src/main/java/org/flowable/cmmn/engine/impl/`;
- `tests/` is `modules/flowable-cmmn-engine/src/test/java/org/flowable/cmmn/test/` (each test's
  model is the `.cmmn` file of the same name under the matching `src/test/resources/` folder);
- `model/` is `modules/flowable-cmmn-model/src/main/java/org/flowable/cmmn/model/`.

Flowable's words (stage, plan item, sentry, event listener) stay in the first two columns.

## The table

The first six rows are the curriculum's list; rows 7–30 are what the layer 11 research found, or
what reading Flowable's tests again turned up; rows 31–37 are Ventoux's own.

The answer column uses the curriculum's four answers: **built**, **planned** (at layer *N*, or
after layer 15 in v1.0), **after v1.0**, **out of scope** (by design, or by a non-negotiable).
Rows that had "not planned" were placed by choice 10. The last column says where layer 11
was asked to keep the door open, and whether it held.

| # | Flowable offers | What it is for (and where it comes from) | Ventoux's answer now | Blocked by anything merged? | Where layer 11 kept it open, and whether it held |
|---|---|---|---|---|---|
| 1 | **Stages** (steps that close together) | A group of plan items entered, completed and exited as one, possibly nested. `model/Stage.java`; `tests/runtime/StageTest.java`, `testOneNestedStage`, `testThreeNestedStagesWithCriteria` | **After v1.0** (choice 10; brief, Simplifications, amended 2026-10-22) | **No.** A new optional key (a step's `stage`, or a `stages` map) in the one namespace of steps, milestones, events and rules (11a, D46). "A stage completed" would be a new moment (D38), and at once a timer anchor (D44). Inside a stage that runs again, `requires: [step]` would mean "done in this run of the stage": new meaning only for new definitions | **Held.** `stop` refuses a name that isn't a step (D40), so a stage's name there later is new meaning; "exit a stage" can be "stop each step in it" through the one place (D40); a timer's purpose ending is general (D44), so an exited stage cancels its timers with no new rule |
| 2 | **Exit criteria on a stage or on the whole case** | Ending a stage, or the whole case, with everything inside it. `tests/runtime/ExitCriteriaTest.java`, `testExitPlanModelWithNestedCaseTasks`; `TimerEventListenerTest.testExitPlanModelOnTimerOccurrence` | **Whole case: built** as a close (layer 8, D10, D28, D34). **A step: built** (`stop`, 11c, D40). **A stage:** with row 1 | **No.** A rule closing the case would be a new action (`then: close`) landing on what `closes_when` does | **Held.** A close stops children through the one place (D40), and rules stop with the close (D38), so a later `then: close` lands on "closing", never on a cut |
| 3 | **Exit types:** exit only what is running, or also what hasn't started | Whether "stop B" also means "B won't start later". `engine/agenda/operation/ExitPlanItemInstanceOperation.java`; `tests/runtime/PlanItemExitSentryTest.java` | **Built** (11c): `stop` ends the run going on now and doesn't keep the step from starting later (D40) | **No:** the other meaning is an option of `stop`'s documented object form (`{"step": …, "<option>": …}`, D40), a plain name keeping its meaning | **Held** (D40's first bullet) |
| 4 | **Exit as "complete" or "force complete"** | Ending a case or stage as completed, refused while work is active, or regardless. `tests/runtime/CaseCompletionExitSentryTest.java` | **Out of scope, by design:** closing, where running work finishes and nothing new starts (D10; research, finding 5) | **Rejected on purpose,** not blocked | — |
| 5 | **Required items** | A plan item that must complete before its stage or case completes by itself. `model/RequiredRule.java`; `tests/itemcontrol/RequiredRuleTest.java` | **Planned:** "required steps", after layer 15, in v1.0 (curriculum) | **No.** A `required` flag, false by default; one more kind of pending work and of `NEVER_CLOSES` | **Held.** A stopped run ends `cancelled`, neither done nor failed (D40), so `required` can say whether it counts; the explicit wait is a step (`wait`, D41), so one flag serves it and every other step |
| 6 | **One plan item per element of a collection** | One instance per element of a list, each seeing its element, results gathered back. `model/RepetitionRule.java`; `tests/itemcontrol/PlanItemRepetitionWithCollectionVariableTest.java`; `RepetitionVariableAggregationTest.java` | **Planned:** after layer 15, in v1.0 (curriculum) | **No, for existing definitions:** a new option or kind, with runs named by entry (`review#3`, D27) and its own gathering of results | **Held.** A list payload is refused (11d), a list field is never set (D42): never packed into a text. A rule's `start` proposes one run (D39); nothing depends on a step never having two runs open beyond "already running" |
| 7 | **Human waits inside a called process** | A child that waits for people while the case waits for it. `engine/behavior/impl/ProcessTaskActivityBehavior.java`; `tests/runtime/CaseTaskTest.java`, `testBasicSubHumanTask` | **After v1.0** for a `workflow` step (D6: "Declared human waits may come later"). **Built** for a `plan` step: its waits are answered on the child (D28) | **No, for definitions:** a contract declaring waits is a new contract version (D5). **Two merged rules need an addition before it is built:** D27's quiet point (a case continues as new only when nothing runs, `temporal/cases.py`, `time_to_switch`, `running == 0`), which a long wait postpones; and closing letting a non-cancellable workflow finish (D10, D29, D40), which would wait for a person. **Already true today for plan steps:** `running` counts child plans, so a plan waiting for an approval holds the switch until it is answered or times out | **Held** for the close: D40 built one place that stops every child by its kind's mechanism, and a cancellable workflow is cancelled by a close. **Not held for D27:** nothing in layer 11 touched it. **Recorded:** D27's limit and direction, and a waiting workflow cancellable (choices 2, 3; brief, D48; D6, D27, D40 amended) |
| 8 | **Child cases** | A case task starts another case and waits for it (or not); ending the parent ends the children. `model/CaseTask.java`; `tests/runtime/CaseTaskTest.java`; `ExitCriteriaTest.testExitPlanModelWithNestedCaseTasks` | **Planned:** after layer 15, in v1.0 (curriculum) | **No, for definitions:** a new step kind (Simplifications, D13), modelled on D28. **But D27's quiet point needs an addition:** a child case runs for weeks | **Held** for stopping (a child case adds a kind to D40's one place) and for events (addressed to the case's workflow ID, `sent_by` takes a later kind of sender, D41). **D27 not held:** recorded, with the direction rows 7 and 8 take (choice 2; brief, D48, D27 amended) |
| 9 | **Claiming and reassigning tasks** | A person takes a task from a queue, or gives it to someone else. `tests/runtime/HumanTaskTest.java`; `tests/runtime/CaseInstanceDueDateAndClaimTest.java` | **Planned:** after layer 15, in v1.0 (curriculum; `docs/layers/07-people.md`) | **No.** Case state and the inbox's, not the definition's; roles still checked when the answer comes (D22), exclusions still hold (D11, D25, D47) | Nothing in layer 11 touched it. **Held** |
| 10 | **Manual activation** | A plan item enabled and waiting for a person to start it. `model/ManualActivationRule.java`; `tests/itemcontrol/ManualActivationRuleTest.java` | **Built** (layer 8): `automatic: false` and `proposed_by` | **No** | **Held.** A rule's `start` is a proposal through admission (D39). D39's one loosening (a step a rule starts may leave out `proposed_by`) keeps its meaning, "which people may propose it" |
| 11 | **Repetition, and its counter** | Running an item again on each entry, with a counter each run reads; a maximum. `model/RepetitionRule.java`; `tests/itemcontrol/RepetitionRuleTest.java`; `PlanItemRepetitionMaxCountTest.java` | **Built:** `repeatable` (layer 8), each run named by its entry (D27); the rework loop through `answered` (D39). **After v1.0:** a run count read in a condition, a maximum (choice 10) | **No.** A run count as a value would be new in D35's list; a maximum a new optional key | **Held.** `NEVER_CLOSES` is claimed only for a loop nothing in the case can end, no rule stopping it (D39, D40), so a later counter bounds a loop without turning an error into a non-error |
| 12 | **User event listeners** | A button a person presses whose only effect is to fire sentries. `model/UserEventListener.java`; `tests/eventlistener/UserEventListenerTest.java` | **Built** (11d): an event `sent_by` people with roles, checked as for a close reason (D41) | **No** | **Held** (D41) |
| 13 | **Signal, generic and intent event listeners** | Reacting to something sent from outside. `tests/eventlistener/SignalEventListenerTest.java` and others | **Built** (11d): `on: {"event": …}`, one Temporal signal, `event` (D41) | **No** | **Held:** a kind of sender is data on the declaration, never a signal of its own (D41) |
| 14 | **Variable event listeners** | Reacting when a case variable is created or changed. `tests/eventlistener/VariableEventListenerTest.java` | **After v1.0** (choice 10; brief, Simplifications, amended 2026-10-22) | **No:** a "field set" moment is a decision recorded in the brief (D38) | **Held.** `set` brings no such moment; a later one would fire at most once per field in a decision, so each decision stays finite (D42) |
| 15 | **Timer event listeners**, started by another item | A timer set when something happens, firing once. `model/TimerEventListener.java`; `tests/eventlistener/TimerEventListenerTest.java` | **Built** (11f): `on: {"after": "5d", "since": <moment>}` (D44); `sla` (D46) | **No** | **Held.** `since` takes the five other moments, so a later moment is an anchor at once; a date from the case file is a later shape of its own (D44) |
| 16 | **Repeating timers** (every hour, three times, cron) | A timer that fires again and again. `tests/itemcontrol/RepetitionRuleTest.java`, `testRepeatingTimer` and others | **Built:** `after` means one firing; a `reminder` takes a finite list of ages (D46). **After v1.0:** an `every` with a count (choice 10). Cron: **after v1.0** (a calendar and time zones) | **No** | **Held.** A repeat is its own key with a count, never a new reading of `after` (D44); no timer re-arms itself, so `NEVER_CLOSES` has nothing new to claim |
| 17 | **Available conditions** on event listeners | A listener that listens only while a condition holds. `tests/listener/AvailableConditionTest.java` and others | **Built:** a rule's `when` is read at its moment (D38), a timer's at its firing (D44) | **No:** a condition on *setting* a timer would be a later, explicit key (D44) | **Held** |
| 18 | **Completion-neutral items** | An item that never keeps its stage open. `model/CompletionNeutralRule.java`; `tests/itemcontrol/CompletionNeutralTest.java` | **Built:** listening is not waiting (D10, D41) | **No** | **Held:** a rule on an event is never pending work; only a `wait` step is (D41) |
| 19 | **Orphan event listener removal** | Removing a listener nothing can react to any more. `engine/persistence/entity/PlanItemInstanceEntityManagerImpl.java` | **Built:** nothing to remove for events (row 18); a timer's purpose ends in general (D44) | **No** | **Held,** with one change: a failed run keeps its timers (D40 as amended by D44), so an `sla` still escalates during an outage (D17) |
| 20 | **Auto-complete,** or a person completes | Whether a stage or case completes by itself. `engine/util/PlanItemInstanceContainerUtil.java`; `RequiredRuleTest.testCompleteCaseInstanceManually` | **Built** (D10): auto-complete by default, `stays_open` waits for a person or a rule | **No** | **Held:** rules run before the case settles (D38) |
| 21 | **Parent completion rules** | Telling a container which children not to wait for. `model/ParentCompletionRule.java`; `tests/runtime/PlanItemCompletionTest.java` | **Out of scope, by design:** a step not started never holds the case, a running one always does (D10); the rest waits for stages (row 1) | **Partly, on purpose:** "ignore a running step" contradicts D10's "running activities finish" | — |
| 22 | **Repeating milestones** | A milestone reached again, each time with its own variables. `tests/runtime/MilestoneTest.java`, `testRepeatingMilestoneWithLocalVariables` | **Out of scope, by design** (D2: "milestones are never undone"); the rework loop uses a repeatable step's latest answer (D2, D9) | **Yes, by D2 and D38,** and layer 11 built more on it: `{"reached": m}` fires once (D38); a timer on a milestone lives until it fires (D44); `TIMER_ON_FIRST_START` and `since=first_start` rest on it (D46); 11h1's `NEVER_FIRES` and the fix's `NEVER_STARTS` read "always closes" from milestones reached for good. Reaching one again would change what every existing definition means | Nothing: kept closed. **Recorded as a deliberate limit** (choice 1; brief, D48, and D2 and D38 amended) |
| 23 | **Fault transitions** | A business error firing sentries. `tests/runtime/FaultTransitionTest.java` | **Built:** declared outcomes (D17), a plan's `failed` (D28), read in `when` | **No** | — |
| 24 | **Non-blocking tasks and case tasks** | Starting an item and moving on at once. `model/Task.java` (`blocking`); `tests/runtime/CaseTaskTest.java`, `testBasicNonBlocking` | **After v1.0** (choice 10; brief, Simplifications, amended 2026-10-22) | **No, for definitions** (an explicit option, false by default), but it needs its own answer to D10's and D28's flags: a step the case doesn't wait for has nobody to flag its result | — |
| 25 | **Case reactivation** | Reopening a completed case on an event. `model/ReactivateEventListener.java`; `tests/reactivation/SimpleCaseReactivationTest.java` | **After v1.0** (choice 10; brief, Simplifications, amended 2026-10-22) | **No, for definitions:** a reopened case would be a new chain of runs with new keys (D27) | **Held:** an event to a closed case raises `EventRefused` at the client, never starts a workflow; one that comes with the close is refused and recorded (D41, amended) |
| 26 | **Plan item injection, discretionary items** | Adding an item to a running case. `tests/runtime/PlanItemInjectionTest.java` | **After v1.0:** ad hoc steps with inline plans (Simplifications, "Deferred"; D13); a changed definition for open cases is a migration (layer 12) | **No** | — |
| 27 | **Changing a case's state by hand** | Activating or terminating items directly. `tests/dynamic/ChangeStateTest.java` | **Out of scope, by design:** no position to move (idea 4); edits and skips are change requests (layer 12, D17) | **No:** nothing to add | — |
| 28 | **Lifecycle listeners, task listeners, script tasks** | Code in the model. `tests/listener/TaskListenerTest.java`; `tests/task/CmmnScriptTaskTest.java` | **Out of scope:** "code inside definitions" (brief, "Out of scope"; non-negotiables) | **Yes, on purpose:** a non-negotiable, already recorded | — |
| 29 | **Decision tasks** (DMN) | Deciding a value from a table of rules. `model/DecisionTask.java` | **Built in effect:** an expression (D20), a `set` (D42), or a `compute` activity (D20) | **No** | — |
| 30 | **Due dates on tasks and cases** | A date a task or case should be done by. `tests/task/CmmnTaskDueDateTest.java`; `CaseInstanceDueDateAndClaimTest.java` | **Built:** timers with their due time in reports, and `sla` (D44, D46). **Planned:** a due date shown in the inbox, with claiming, after layer 15, in v1.0 (choice 10) | **No** | **Held:** a due date is a view of the timer set on a run (D44), never a second clock |
| 31 | **Ventoux's own, found in 11b:** untrusted data steering a plan's own transitions | Design question 17 began with a plan's transition reading an untrusted field (`llm_says_refund`). D39 and D43 answer it for a case's steps; a plan's transitions are left open (D39, DQ 17) | **Open, and wider than the draft said.** Run on `main` at `24b5d03`: a plan step whose plan reads the case's `note` (`untrusted:customer`) in a transition to its success state reaches `settled`, the case's `closes_when`, on `"go"`, and gives `failed` on anything else. The customer's text closed the case, against D38; `validate_case` says nothing | **Not yet; from layer 12, yes:** refusing or reading it differently after plans are published would change plans accepted today | Nothing in layer 11 was asked to. **Unblocked by refusing** (choice 4): its own pull request, D49 |
| 32 | **Ventoux's own, found in 11b:** an output's `system:<name>` not checked against the registered systems | D30 refuses a reference naming an unregistered system, but `Catalog.register` checks only `untrusted:` labels on outputs (`check_output_labels`): `kyc.check@1` declares `system:kyc` and `kyc` isn't registered in the development catalog | **Not checked** | **Not for definitions** (a contract is the catalog's); but layer 12's activation would then refuse at startup a worker serving such a contract, so later is costlier | **Unblocked** (choice 5): its own small pull request, with choices 6 and 8 |
| 33 | **Ventoux's own, decided in the tutor review of #31, found again in 11h:** untrusted data deciding what doesn't happen | A step's own `when` reading untrusted data, false, keeps the step from starting, and the case may close without it; a rule whose condition reads untrusted data, false (or written with `!`), keeps a step from starting (11h's probe B6). D46 leaves it to the checkpoint | **Open:** allowed, and `validate_case` says nothing | **Not yet; from layer 12, yes:** a runtime answer as the default (asking a person) would change what published definitions do; a warning refuses nothing and can come any time | **Recorded as a deliberate limit** (choice 6; brief, D48, D38 and D46 amended); the history line it needs in a small pull request |
| 34 | **Ventoux's own, from 11e:** what a case did is seen by every role | D42's known limit: a milestone a rule reaches on a field narrowed by `visible_to` is seen by everyone. The same holds wider, by D30's design: `visible_to` filters values in the view (`case/visibility.py`, `case_view`), never the history, milestones or step runs, and outcomes and outputs are seen by every role the case names | **Built as it is;** recorded only as D42's known limit | **No:** a `visible_to` on a milestone (or an output) would be a new optional key, absent meaning "every role", as today | **Recorded as a deliberate limit** (choice 7; brief, D48, D30 and D42 amended) |
| 35 | **Ventoux's own, carried by the tutor session:** a misleading flag, on `main` since the held close (D26, D34) | When a failed run holds the close (D34) and an operator's retry completes it, the closed case is flagged `notify#1 completed after the close was requested`, though the retry is what the close waited for. Run on `main` at `24b5d03`: `omar retried notify#1`, `notify#1 done`, `flagged: notify#1 completed after the close was requested`, `closed: paid reached`. `flag_if_stopping` (`case/runtime.py`) reads only the phase | **Built, wrongly worded** | **No:** a flag is a history line, not a command, so replay decides the same; not part of the format | **Fixed** in a small pull request (choice 8), with an amendment line on D34 |
| 36 | **Ventoux's own, from 11g2:** `ventoux simulate` reads the development catalog only | 11g2, choice 10: the command passes `ventoux.testing.CATALOG`; `simulate(story, case, catalog)` already takes a catalog | **Planned at layer 14,** with `ventoux check` and the builder (11g2, "Decided while building") | **No:** a story names its definition and fakes by contract reference, never a catalog; choosing one is the command's | **Left at layer 14** (choice 9) |
| 37 | **Ventoux's own, from 11d, 11h1 and 11h2:** shapes refused for now | No sensitive, list or `visible_to` payload field (11d); no `since=first_start` (D46); no `count` on a plan's approval, no different roles per approver (D47); no list field set by a rule (D42); one sender per event (D41) | **Refused, each** | **No:** each is refused today, so accepting it later changes no published definition | Nothing to decide (choice 11); listed in D48, so layer 12 publishes them as refused |

## Did the doors hold?

Each part of layer 11 was asked to keep some rows open ("What 11b to 11f must not close off",
below), and each recorded its answer in `docs/layers/11-rules.md`, "The doors left open":

- **11b:** rows 6, 10, 11 held (D39).
- **11c:** rows 1, 2, 3, 5, 19 held; rows 7 and 8 held for stopping (one place, D40), and left
  D27 as it was, as the table said they would.
- **11d:** rows 5, 6, 8, 12, 13, 18, 25 held (D41).
- **11e:** rows 6 and 14 held (D42); found the visibility limit (row 34).
- **11f:** rows 15, 16, 17, 19, 30 held (D44), with D40 amended for a failed run's timers.
- **11g, 11h:** touched no row; 11h1 sent row 33 back here (D46), and 11h2 adds row 37's
  set-aside shapes (D47).
- **The three fixes:** none touched a row. The untrusted moment (D43) closed the paths a case's
  steps had; a plan's transitions are row 31's, still open.

One door did not hold as the draft described it: row 31 is not only "which trusted value a plan
sends" but a milestone reached on untrusted data, the bug D43 fixed for steps, still open through a
plan (the run above).

## Choices before layer 12

*Answered 2026-10-22: 1 to 11, all as recommended, with the user's addition to 4.*

Each is numbered so you can answer by number. "Record" means a new decision in the brief, or a
dated amendment line on an existing one, never a rewrite. I'd gather every deliberate limit into
**one new decision, D48** ("Deliberate limits, recorded at the checkpoint before layer 12"), each
limit a bullet saying what is refused or not offered, why, and which door stays open, with a
dated amendment line on each decision it adds to (D2, D27, D38, D42, D46).

1. **Row 22, repeating milestones.** *Recommended: record as a deliberate limit* (D48, and an
   amendment line on D2 and D38). A milestone is reached once and never undone; repeated facts,
   if ever needed, are a new concept beside milestones (a step's latest answer, or an event's
   latest arrival, already serve), never a milestone reached twice. Why: D38's "once", D44's
   timers on a milestone, D46's first-start warning, and the "always closes" proofs all read a
   milestone as reached for good; changing it would change every definition.

2. **Rows 7 and 8, D27's quiet point.** A case continues as new only when nothing is running,
   and a child that waits for people (a child case, a workflow waiting for people, and already
   today a plan waiting for an approval) holds the switch for as long as it waits.
   *Recommended: record now, build with rows 7 and 8* (a dated amendment line on D27, and a D48
   bullet): today's limit, stated (a plan step waiting for a person postpones continue-as-new
   until it is answered or times out; Temporal's history limit is the bound), and the direction
   each row must take when built: a long-running child reports its end to the case by a signal to
   the case's workflow ID (D27: "people address the case, not a run"), so the switch no longer
   waits for it. No definition changes meaning; nothing is built now, since neither row is in
   v1.0 before layer 15. Set aside: building the signal-back now for plans; it is engine work no
   published definition depends on.

3. **Row 7, a close waiting for a person.** D10 and D29 let a non-cancellable workflow step
   finish when the case closes, and D40 cancels a cancellable one. *Recommended: record now* (a
   D48 bullet, adding to D6 and D40): a workflow contract that declares human waits must declare
   `cancellable: true`, refused at registration otherwise, so a close never waits for a person.
   It uses D40's one place and contract test as built, and refusing is the fail-closed default.

4. **Row 31, a plan's transition reading untrusted data.** The run above shows untrusted data
   deciding through a plan. *Recommended: unblock now, by refusing* (option b), in its own pull
   request, test-first, after the docs one:
   - at runtime, a transition whose `when` reads an untrusted (or unrecognised) source stops the
     plan, naming the field and source, never the value; the plan step fails and needs attention
     (D17, D28): nothing is skipped;
   - plan validation refuses a transition reading a field the plan declares untrusted, and case
     validation refuses (`UNTRUSTED_TRIGGER`) a plan step whose input feeding such a field is
     untrusted whoever writes it, as D34 claims only what is proven;
   - recorded as a new decision (D49, "a plan's path is never chosen by untrusted data"), with an
     amendment line on D39 and on design question 17's "left open".
   Option (a), D43's way inside a plan (the plan reports what steered the transitions it took, so
   its run reaches nothing and its outcome and outputs carry it, and each entered state's inputs
   are checked, D39) is the later loosening, if a team needs it: refusing now keeps it open;
   allowing now and refusing later would not. Set aside: recording it as a limit, since it breaks
   D38 and a non-negotiable ("untrusted data never decides" is fail-closed, not a preference).
   *The user's addition, 2026-10-22:* D49 says plainly that this blocks a plan from branching on
   untrusted data at all, an LLM's classification included, until option (a) is built, and
   records (a) as the planned loosening, so it isn't forgotten.

5. **Row 32, `system:<name>` on an output.** *Recommended: unblock now*, in its own small pull
   request, test-first: `Catalog.register` refuses an output whose `system:` names an unregistered
   system, as `check_output_labels` does for labels (one more branch there), the development
   catalog registers `kyc`, and the test catalogs register the systems their own contracts name
   (`accounts`, `ledger`, `letters`, `payments` appear in tests; the suite will say which
   catalogs lack them). More than a line or two, since several test files change. No decision
   changes meaning: D30 says systems are registered; this enforces it at one more place, with an
   amendment line on D29.

6. **Row 33, untrusted data deciding what doesn't happen.** A `when` is one condition: true lets
   a step start, false keeps it from starting. D39 allows a start on untrusted data (inputs
   checked), so refusing the false side would refuse the true side too, and rewrite D39.
   *Recommended: record as a deliberate limit* (D48, amendment line on D38 and D46): untrusted data
   may keep a step from starting or a rule from acting; a step that must happen is guarded by
   something it can't skip (a `closes_when` milestone only it reaches, or a task, where a person
   decides). The doors kept: a runtime answer ("ask a person when an untrusted condition is
   false") would be an opt-in key, never a changed default; a teaching warning refuses nothing, so
   it can come with `ventoux check` (layer 14).

   **But today the run says nothing either.** Run on `main` at `24b5d03`: a task `check` whose
   `when` is `note != "skip"`, `note` declared `untrusted:customer`, opened with `"skip"`: the
   history is `opened by system:opener, with note` then `closed: nothing left to do`. Nobody can
   tell the step was kept from starting, nor by what. A limit nobody can see is a silent skip
   (D17: "nothing is skipped automatically"). So, with the limit: *a small pull request,
   test-first,* adding one line when the case closes with a step that never ran because a
   condition reading untrusted data was false, naming the step, the field and the source, never
   the value (`check never started: its condition reads note (untrusted:customer)`). A history
   line and no command, so replay decides the same. Set aside: recording the limit with no line.

7. **Row 34, what a case did is seen by every role.** *Recommended: record as a deliberate limit*
   (D48, amendment line on D30 and D42): `visible_to` narrows who sees a value, never what the
   case did; milestones, step runs, the history, and outcomes and outputs are seen by every role
   the case names, and no history line quotes a value (D30). A case needing more gives its steps
   narrower roles, or keeps the fact out of a milestone. The door kept: a later `visible_to` on a
   milestone or an output is an optional key, absent meaning "every role", as today.

8. **Row 35, the misleading flag.** *Recommended: fix it, in a small pull request after the docs
   one*, test-first, with a dated amendment line on D34. The run the held close waited for still
   gets a flag (D28: "flagged, never hidden"; a payment retried after the case's `withdrawn` was
   reached may still need a reversal), but a true one, naming the retry: `notify#1 completed on
   omar's retry, after paid was reached`. A line or two in `flag_if_stopping` plus its test; a
   history line and no command, so replay decides the same. Set aside: dropping the flag (it would
   hide what ran after the case's end was reached).

9. **Row 36, `ventoux simulate`'s catalog.** *Recommended: leave it at layer 14*, as 11g2
   decided. Nothing in the story format names a catalog, so nothing freezes; no brief change.

10. **Placing the unplaced rows.** The curriculum asks for one of four answers per row; rows 1,
    11 (a run count, a maximum), 14, 16 (`every`), 24, 25 and 30 (an inbox due date) had "not
    planned". *Recommended:* 30's inbox due date with claiming (after layer 15, in v1.0, both the
    inbox's); the others **after v1.0**, added to the brief's "Deferred until after v1.0" by a
    dated amendment line (Simplifications), each "a decision recorded in the brief when it comes".
    None is blocked.

11. **Row 37, shapes refused for now.** *Recommended: nothing to decide.* Each is refused, so
    accepting it later is a new decision that changes no published definition. Listed so layer 12
    publishes them as refused, not as missing.

## Layer 12's own, not decided here

Gathered so layer 12 starts from them. None is decided in this note.

**Open cases replaying differently after an engine change** (layer 12's "behaviour version stored
with each case", 11b's note):

- 10b: a case failed by G1 can't be retried (the same check refuses the retry) and waits for a
  change request; and a running case that skipped such a step under the old code would replay
  differently (`docs/layers/10-case-validation.md`, "Not in 10b").
- 11b: three paths decided differently, on a case open under 11a's code: a proposal on a stale
  fact, a proposal beside a failed run, a condition reading an unset untrusted field
  (`docs/layers/11-rules.md`, "Not in 11b").
- The untrusted moment (D43): paths 0a–4 and 6 replay differently; a fixture shows it
  (`docs/layers/fix-untrusted-moment.md`, decision 7).
- The retry rejected: decision 4's paths (A, D, C, F, C′, E′, L) where the case later went on, and
  decision 6's (N) (`docs/layers/fix-retry-rejected.md`); closing the gap "would need a patch
  marker passed to `decide` as event data; not built".
- If choice 4 is taken: a plan run whose transition read untrusted data stops, where `main` went
  on, so such a history replays differently.
- D46: a pattern's expansion is part of the format; changing one changes how open cases replay.
- Design question 16: the hash method needs a version recorded with each hash ("to decide by
  layer 12").

**Change requests** (layer 12's one mechanism):

- skipping a failed step, never automatic (D17; `docs/layers/08-case.md`);
- case-file edits, and the lapse they cause: D25's "a lapse from a change request stops the step",
  for every approval on an entry at once (D47);
- forget as the first change request, made general (D32; `docs/layers/09-case-data.md`, 9c);
- migrations of open cases, mapping names, not positions (D2, D5).

**Bindings changing while cases are open:**

- a workflow contract's workflow type may not move under open cases; its task queue may (D29);
- activation checking bindings, served contract hashes and live pollers (8c, 8d; curriculum,
  layer 12).

## "Done when", row by row

The curriculum: every row that would be blocked is either unblocked before layer 12, or recorded
in the brief as a deliberate limit. Each row that is blocked, or would be once layer 12 publishes
the format:

| Row | Blocked by | Done | Where |
|---|---|---|---|
| 7 | D27's quiet point; a close waiting for a person (D10, D29) | recorded: the limit, and the direction the row takes when built | D48; D6, D27, D40 amended |
| 8 | D27's quiet point | recorded, as for row 7 | D48; D27 amended |
| 21 | D10, on purpose ("running activities finish") | already decided | D10 |
| 22 | D2 and D38 | recorded as a deliberate limit | D48; D2, D38 amended |
| 28 | a non-negotiable | already recorded | brief, "Out of scope for v1.0"; non-negotiables |
| 31 | would be, from layer 12 | unblocked by refusing, before layer 12 | D49, its own pull request |
| 33 | would be, from layer 12 | recorded as a deliberate limit; its history line in a small pull request | D48; D38, D46 amended |
| 34 | not blocked; a known limit to record | recorded as a deliberate limit | D48; D30, D42 amended |
| 37 | not blocked; each refused | listed, so layer 12 publishes them as refused | D48 |

Every other row is not blocked: the table says why. Rows 32 and 35 are not blocked either, and
are fixed in a small pull request (choices 5 and 8); row 36 stays at layer 14.

## What 11b to 11f must not close off

Kept as written in the draft, each with the answer its part recorded.

### 11b: rules that start steps

Rows touched: 6, 10, 11.

- **Termination and its proofs** (row 11). Keep 11a's "a decision starts finitely many runs" true
  with `start`, and claim `NEVER_CLOSES` for a restarting rule only where nothing could stop it,
  so a later run counter or maximum can bound a restart.
- **A rule's start is a proposal through admission** (row 10), so `automatic` and `proposed_by`
  keep their meanings.
- **`start` starts one run of a step** (row 6): nothing depends on a step never having two runs
  open, beyond today's "already running" refusal.

### 11c: rules that stop steps

Rows touched: 1, 2, 3, 5, 7, 8, 19.

- **`stop`'s meaning, and its shape** (row 3). Say once whether stopping a step also keeps it from
  starting later; give `stop` a shape that can take the other meaning as an option, rather than
  needing a second action or a migration.
- **One place that stops every running child** (rows 7, 8): a plan, a workflow step, later a child
  case or a workflow waiting for people, each by the mechanism its kind declares. Closing and
  `stop` then reach every child the same way. Which mechanism a workflow step uses (Temporal's
  cancellation, as D6's "whether it can be cancelled" suggests, or a declared signal) is 11c's to
  decide: it is another team's workflow, unlike the plan workflow Ventoux writes (D28).
- **A stopped run ends as itself** (row 5): neither `done` nor failed, so `requires` doesn't count
  it as done, a later `required` can decide what it means, and a failed run is still never stopped
  (D17, D26).
- **`stop` refuses a name that is not a step** (row 1), so a stage named there later is new meaning,
  never changed meaning.
- **One place a later `then: close` lands** (row 2): the same place that stops every child.
- **A run has ended once it has its final status** (row 19): a run whose stop is asked and still
  running hasn't ended, and a stopped run's timers end with it.

*Answered in 11c's session, 2026-10-18:* how each of these rows stays open is said in
`docs/layers/11-rules.md`, 11c, "The doors left open", and in D40.

### 11d: events from outside

Rows touched: 5, 6, 8, 12, 13, 14, 18, 25.

- **Who may send an event** (row 12). Leave room for a person as the sender (roles checked as for a
  close reason, source `person:`), not only a system: that is Flowable's user event listener.
- **One event shape and one signal** (row 13), addressed to the case's workflow ID (D27), so a
  parent and a child case can later send each other events (row 8).
- **Payload types are the case's** (row 6): decimals, texts, booleans and declared list fields; a
  list is never packed into a text.
- **Listening never holds the case; an explicit wait does** (rows 5, 18), and the explicit wait is
  the one place a later `required` can build on.
- **A "field set" moment, if `set` brings one** (row 14), keeps the termination argument: 11e's
  since the split.
- **An event reaching a closed case is refused** (row 25), never a way to reopen it.

*Answered in 11d's session, 2026-10-19:* how each of these rows stays open is said in
`docs/layers/11-rules.md`, 11d, "The doors left open", and in D41. Row 14 ("a field set" moment)
is 11e's to decide, with `set`.

*Answered in 11e's session, 2026-10-19:* `set` brings no "field set" moment; a later one would fire
at most once per field in a decision, so each decision stays finite (`docs/layers/11-rules.md`, 11e,
"The doors left open"; brief, D42). Found there, for the checkpoint: a milestone a rule reaches on
a field narrowed by `visible_to` is seen by everyone (brief, D42, known limit). Now row 34.

### 11f: time

Rows touched: 15, 16, 17, 19, 30.

- **`since` takes D38's moment shape** (row 15), so every later moment is an anchor at once, and a
  date from the case file is one more shape later.
- **`after` means one firing** (row 16); a repeat, if ever, is its own key, with a count.
- **When a timer's `when` is read** (row 17): at its firing, on the case file then, as D38 says;
  a condition on setting it would be a separate key.
- **A timer's purpose ending, defined in general** (row 19): the run or moment it was set for having
  ended, or the case closing, so a stopped step, an exited stage or an ended child case cancels its
  timers with no new rule.
- **A due date is a view of a timer** (row 30): a task's due date, if the inbox ever shows one,
  reads the timer set on its run, never a second clock.

*Answered in 11f's session, 2026-10-20:* each of these stays open as the row says it should
(`docs/layers/11-rules.md`, 11f, choices 1, 3 and 14; brief, D44). Row 19's purpose ending covers
a stopped step, an exited stage or an ended child case through one rule: a timer set on a run's
start ends with the run.

## Found in 11b, for the checkpoint

Two rows (31 and 32) are not Flowable's: they are open in Ventoux itself, found in 11b's session.
Row 31 is the one to watch: it is not blocked today, but it would be once plans are published.
*2026-10-22:* row 31 is wider than this said; see the table and choice 4.

## Found in 11h, for the checkpoint

Row 33 was decided in the tutor review of #31 and added in 11h1 (docs only), with 11h's probe B6:
D7's teaching warning "rules whose condition reads untrusted data" has nothing left to warn about
where something happens (an error or designed behaviour, `docs/layers/11-rules.md`, 11h, choice
15), and what is left is untrusted data deciding what doesn't happen, the same for a step's own
`when` and a rule's. Like row 31, it is not blocked today, and would be once definitions are
published.
