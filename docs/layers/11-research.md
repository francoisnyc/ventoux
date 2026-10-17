# Layer 11, research: how Flowable's CMMN engine re-checks sentries

Status: prior art, read 2026-10-16, before layer 11's design. Not a decision: what each answer means
for Ventoux is proposed in `docs/layers/11-rules.md` and decided there, with the user.

## What was read, and how

- **Reached:** this environment's network reaches GitHub. Flowable's engine was cloned read-only
  (`git clone --depth 1 --sparse https://github.com/flowable/flowable-engine`, only
  `modules/flowable-cmmn-engine`), at commit `f6017e3` (2026-10-16), into the session's scratch
  directory, never into this repository. No Flowable code is copied into Ventoux; quotes below are
  for reading.
- **Where the quotes come from.** Two prefixes, used below:
  - `engine/` is `modules/flowable-cmmn-engine/src/main/java/org/flowable/cmmn/engine/impl/`;
  - `tests/` is `modules/flowable-cmmn-engine/src/test/java/org/flowable/cmmn/test/`, and each
    test's model is the `.cmmn` file of the same name under
    `modules/flowable-cmmn-engine/src/test/resources/org/flowable/cmmn/test/`.
- **The code that re-checks sentries** is `engine/agenda/operation/AbstractEvaluationCriteriaOperation.java`
  (entry and exit criteria, the "if" part, what is remembered between evaluations),
  `engine/util/PlanItemInstanceUtil.java` (repetition) and
  `engine/util/PlanItemInstanceContainerUtil.java` (when a stage or a case may complete).
  The tests were read first: they say what the code is for.
- **Flowable's words stay Flowable's** inside quotes (plan item, sentry, on part, if part, stage,
  event listener, plan model). Ventoux's words are used only in "What it means for Ventoux".

A short glossary, so the quotes can be read: a **plan item** is one thing in a case's plan (a
task, a stage, a milestone, an event listener); each time it is created at runtime it is a **plan
item instance**, with a state (`available`: waiting for its entry sentry; `enabled`: waiting for a
person to start it; `active`; then `completed`, `terminated` or `failed`). A **sentry** guards
entry or exit: zero or more **on parts** (a lifecycle transition of another plan item, such as
`complete` or `occur`) and at most one **if part** (a condition). A **stage** is a plan item that
holds others; the **plan model** is the case's outermost stage.

The `chartering` prototype was also read where it touches the same questions
(`src/case/events.ts`, `src/case/deadlines.ts`, `src/case/validate.ts`, `docs/design.md` §7 and
§10); it is cited in `11-rules.md`, not here.

---

## 1. When is a met "on" part forgotten?

**Answer.** It depends on the sentry's trigger mode, and on the plan item instance it belongs to.

- In the **default** mode, a satisfied on part (or if part) is *stored* and remembered across
  later evaluations, until the plan item instance starts, is enabled, or reaches a terminal state:
  then its remembered parts are deleted.
- In the **`onEvent`** mode, a satisfied part is kept only for the current evaluation cycle (one
  transaction), never stored: the if part is evaluated only when the on parts are all satisfied by
  the event being handled.
- A **repetition** creates a *new* plan item instance (a copy), which starts with nothing
  remembered: the memory belongs to the instance, not to the plan item.

The code that stores, or doesn't store, a satisfied part,
`engine/agenda/operation/AbstractEvaluationCriteriaOperation.java`, lines 711–717:

```java
        // In the default triggerMode satisfied parts are remembered for subsequent evaluation cycles.
        // In the onEvent triggerMode, they are stored for the duration of the transaction (which is the same as one evaluation cycle) but not inserted.
        if (sentry.isDefaultTriggerMode()) {
            sentryPartInstanceEntityManager.insert(sentryPartInstanceEntity);
        }

        entityWithSentryPartInstances.getSatisfiedSentryPartInstances().add(sentryPartInstanceEntity);
```

and where the if part is evaluated, same file, lines 552–559:

```java
                // Evaluate the if part of the sentry:
                // In the onEvent triggerMode all onParts need to be satisfied before the if is evaluated
                if (sentry.getSentryIfPart() != null && !sentryIfPartSatisfied
                    && (isDefaultTriggerMode || (sentry.isOnEventTriggerMode() && allOnPartsSatisfied) )) {
```

Forgetting on start, `engine/agenda/operation/StartPlanItemInstanceOperation.java`, lines 67–68
(the same in `EnablePlanItemInstanceOperation.java`, lines 46–47, and on every terminal state in
`AbstractMovePlanItemInstanceToTerminalStateOperation.java`, line 145):

```java
        // Sentries are not needed to be kept around, as the plan item is being started
        removeSentryRelatedData();
```

A repetition is a copy, `engine/util/PlanItemInstanceUtil.java`, lines 180–181:

```java
    public static PlanItemInstanceEntity createPlanItemInstanceDuplicateForRepetition(PlanItemInstanceEntity planItemInstanceEntity, CommandContext commandContext) {
        PlanItemInstanceEntity childPlanItemInstanceEntity = PlanItemInstanceUtil.copyAndInsertPlanItemInstance(commandContext, planItemInstanceEntity, false, false);
```

**The test that shows why remembering can be wrong:**
`tests/sentry/TriggerModeSentryTest.java`, `testTriggerModeOnEvent`. The case opens with
`goToC = true`; stage "2.1" repeats; two sentries on its `complete` read `goToC` and `!goToC`. After
the first completion, `goToC` is changed to false, and the second completion must start D, not C:

```java
        // Now we're completing B again, changing the variable. If we were using the default triggerMode,
        // the ifPart would already have been stored and the wrong thing would be activated now.
        // However, the onEvent semantics make sure the correct thing happens here.
        cmmnTaskService.complete(tasks.get(1).getId(), Collections.singletonMap("goToC", false));
```

and, in the same file, `testTriggerModeOnEventConditionCalledOnce`: "the ifPart of an onEvent
triggered sentry doesn't get called unless the event happens" (the condition's counter stays 0 until
the task completes, then is 1).

**What it means for Ventoux.**
- Flowable needed a second mode because a remembered part outlives the moment it described: a
  condition true at one completion was still "true" at the next, after the data changed. Ventoux can
  avoid the memory altogether. A rule's *when* is a moment (a milestone reached, a step started, an
  event arriving, a timer firing), and its *if* is read in the decision handling that moment, on the
  case file as it is then: Flowable's `onEvent`, as the only mode. Nothing half-met is stored, so
  nothing needs forgetting, and continue-as-new (brief, D27) has nothing extra to carry.
- What Flowable's default mode is used for ("start B once A has completed and, later, x holds") is
  already Ventoux's admission: a step's `requires` and `when` are re-read after every event, from the
  milestones and the case file, which hold the facts. So the two needs get two shapes: **a step's
  admission is level-triggered** (it starts as soon as its requirements hold, read again each time);
  **a rule is edge-triggered** (it reacts once to each moment, never to a state that merely persists).
- The memory being per instance, and a repetition being a new instance, is the same as Ventoux's
  step runs (`review#2` is a new run). A rule triggered by a step's start fires once per run, which
  is what D7's `sla` from the latest start needs.

## 2. What do exit conditions stop, and what of work already running?

**Answer.** An exit sentry terminates its plan item instance in whatever state it is: an `available`
one will never start, an `enabled` one is withdrawn, an `active` one is cut off. Two exit types
narrow it to active (or active and enabled) instances. Exiting a stage exits everything inside it.
What "cut off" does depends on the behaviour: a human task's task is deleted, a child process
instance is deleted. A repeatable item that is exited is, by default, not repeated.

What a non-default exit type leaves alone,
`engine/agenda/operation/ExitPlanItemInstanceOperation.java`, lines 87–94:

```java
    public boolean shouldPlanItemStayInCurrentState() {
        return !isStage() && (
            (EXIT_TYPE_ACTIVE_INSTANCES.equals(exitType) &&
                (ENABLED.equals(planItemInstanceEntity.getState()) || EVALUATE_STATES.contains(planItemInstanceEntity.getState())))
                ||
            (EXIT_TYPE_ACTIVE_AND_ENABLED_INSTANCES.equals(exitType) &&
                EVALUATE_STATES.contains(planItemInstanceEntity.getState()))
        );
    }
```

a stage's children, same file, lines 126–128:

```java
            // regardless of the exit event type, we need to exit the child plan items as well (we don't propagate the exit event type though, children are
            // always exited, not completed)
            exitChildPlanItemInstances(PlanItemTransition.EXIT, exitCriterionId, exitEventType);
```

and repetition after an exit, lines 158–160:

```java
        // by default, we don't create new instances for repeatable plan items being terminated, however, if the exit type is set to only terminate active or
        // enabled instances, we might want to immediately create a new instance for repetition, but only, if the current one was terminated, of course
        return (EXIT_TYPE_ACTIVE_INSTANCES.equals(exitType) || EXIT_TYPE_ACTIVE_AND_ENABLED_INSTANCES.equals(exitType)) && TERMINATED.equals(getNewState());
```

What happens to running work: a human task's tasks are deleted,
`engine/behavior/impl/HumanTaskActivityBehavior.java`, lines 491–497:

```java
        if (PlanItemTransition.TERMINATE.equals(transition) || PlanItemTransition.EXIT.equals(transition)) {
            ...
            List<TaskEntity> taskEntities = taskService.findTasksBySubScopeIdScopeType(planItemInstance.getId(), ScopeTypes.CMMN);
            for (TaskEntity taskEntity : taskEntities) {
                TaskHelper.deleteTask(taskEntity, "cmmn-state-transition-" + transition, false, true, cmmnEngineConfiguration);
            }
```

and a child process is deleted, `engine/behavior/impl/ProcessTaskActivityBehavior.java`, lines
192–193:

```java
            if (PlanItemTransition.TERMINATE.equals(transition) || PlanItemTransition.EXIT.equals(transition)) {
                deleteProcessInstance(commandContext, planItemInstance);
```

**The tests.** `tests/runtime/PlanItemExitSentryTest.java`, `testExitSentryTerminatingAvailableTaskB`
(exit type "active instances", the task not started yet):

```java
        // trigger exit sentry with Task B still in available state -> nothing must be changed
        cmmnRuntimeService.completeUserEventListenerInstance(getPlanItemInstanceIdByName(planItemInstances, "Kill active tasks B"));
```

and `testExitSentryTerminatingActiveTaskB` (the task started, and repeatable):

```java
        // trigger exit sentry with Task B still in active state -> must terminate the active task B, but leave it in waiting for repetition state
```

`tests/itemcontrol/RepetitionRuleTest.java`, `testRepetitionRuleWithExitCriteria`:

```java
        //Completion of taskB will transition taskA to "exit", skipping the evaluation of the repetition rule (Table 8.8 of CMM 1.1 Spec)
```

`tests/runtime/ExitCriteriaTest.java`, `testExitPlanModelWithNestedCaseTasks`: exiting the plan
model ends the case *and its three child cases* (four case instances running before, none after,
four finished in history).

**What it means for Ventoux.**
- Flowable's exit is a cut: work in progress is deleted, a child process included. Ventoux can't
  take that over: "a side effect can't be safely cut off halfway" (brief, D10), and closing already
  lets running activities finish, flags what completed after the close was asked, and signals a
  plan step to stop rather than cancelling it (brief, D28). A rule that **stops a step** should do
  what a close does to that one step: cancel its open task or approval (saying why), let a running
  activity or workflow finish and record its result, stop a plan step's plan, and flag what
  completed after the stop. D29 left `cancellable` workflows "with the first thing that stops a
  running step": this is it.
- Flowable's three exit types answer a real question Ventoux must answer too: does stopping a step
  also mean it will **not start later**? Flowable's default says yes (an `available` item is
  terminated); "active instances" says no. Ventoux's step has no "available instance" to terminate,
  so this becomes part of the definition of the stop action.
- A failed step has no counterpart in Flowable's exit (a failed item is terminal there). In Ventoux
  a failed run waits for a person and is never cancelled by a milestone (brief, D17, D26), so a rule
  must not stop it either: that would be an automatic skip.
- "Repeatable items are not repeated after an exit" matches Ventoux already: a repeatable step runs
  again only when proposed.

## 3. What does each repeated run see?

**Answer.** Each repetition is a new plan item instance with its own *local* variables (the
repetition counter, and with a collection, the item and its index), and it reads the case's
variables as they are when it starts and while it runs: nothing of the case's variables is copied
or frozen per run. Results can be gathered per run only by declared aggregations.

`tests/itemcontrol/RepetitionRuleTest.java`, `testPlanItemLocalVariables` (model: a task repeated
while `repetitionCounter < 3`): the first run sees

```java
        assertThat(cmmnTaskService.getVariables(task.getId()))
                .containsOnly(
                        entry("repetitionCounter", 1),
                        entry("initiator", null)
                );
```

the second `repetitionCounter = 2`, the third `3`, then the case ends. In
`testPlanItemLocalVariablesWithCollection`, each instance also gets its item and index as local
variables. The counter is written on the copy, `engine/util/PlanItemInstanceUtil.java`, in
`copyAndInsertPlanItemInstance` (line 49: `localVariables.put(getCounterVariable(planItemInstanceEntityToCopy),
counter);`).

The repetition condition is read on the case as it is at the moment the item would be activated,
same file, `evaluateRepetitionRule`, lines 147–150: "check the plan item to be repeating by evaluating its repetition
rule ... create a new duplicated plan item instance in waiting for repetition as this one is
becoming active".

**What it means for Ventoux.**
- Ventoux has no run-local data, by choice: "rules still only read the case file" (brief, D8, D9),
  and a repeatable task's outcome and form fields hold the latest answer. So every run, and every
  rule, sees the case file as it is when it is read: the same as Flowable's case variables.
- What Flowable puts in a local counter, Ventoux already has in the entry (`review#2`), which a
  history line, a key (brief, D17, D27) and a timer can name. A rule that reacts to a step's start
  should know *which* run started, so a timer set on `assess#2`'s start is the second attempt's, and
  can be cancelled when that run ends (D7: "fires once per attempt").
- Collections ("one step per item of a collection") are after layer 15 in the curriculum; nothing
  here pulls them in.

## 4. How does an event listener differ from waiting for an event?

**Answer.** In Flowable an event listener never becomes active: it *occurs*. Its only effect is to
satisfy on parts. While it is `available` it is a pending plan item, and it keeps a stage or case
that is **not** auto-complete open, unless (a) nothing could react to it any more, in which case it
is removed as an *orphan*, or (b) it is marked completion-neutral. In an **auto-complete** container
an available listener does not keep it open, unless it is *required*. A timer event listener whose
timer repeats keeps a non-auto-complete case open for as long as it repeats.

`engine/agenda/operation/AbstractEvaluationCriteriaOperation.java`, lines 108–110:

```java
            if (planItem.getPlanItemDefinition() instanceof EventListener) {
                activatePlanItemInstance = false; // event listeners occur, they don't become active
            }
```

Orphans, `engine/persistence/entity/PlanItemInstanceEntityManagerImpl.java`, lines 203–221:

```java
        /*
         * 'Orphan' event listeners are event listeners that are no longer referenced by any plan item instance that is not in a terminal state.
         * Said simpler: when they occur, nothing is listening to them anymore. As such, they have no value to keep around.
         * For example, imagine a user event listener is used to exit a stage. When the stage goes into a terminal state (via another way),
         * there is no purpose for the user event listener anymore. At that point, it is removed.
         ...
         *    - If the event listener is used for an entry criterion: if they are all in a state different from available, it is an orphan.
         *    - If the event listener is used for an exit criterion: if they are all in a terminal state, the user event listener is an orphan and can be deleted.
```

and an exception for repetition, same file, lines 241–244:

```java
        // if the plan item has repetition, we don't remove any event listeners for entry dependencies, as they might trigger in the future and re-create
        // the plan item as it has repetition and therefore, we also don't remove any exit sentry dependant event listeners, as if in the future, the plan
        // item becomes active again, those event listeners might trigger again to terminate it, so we need them to stay in place
```

**The tests.** `tests/eventlistener/UserEventListenerTest.java`, `testCaseWithoutFiringTheEvent`
(a case, not auto-complete, whose only other work is one task; the listener would exit that task's
stage):

```java
        //Complete the Task
        cmmnRuntimeService.triggerPlanItemInstance(task.getId());

        //Listener should be terminated as it's orphaned
        ...
        assertCaseInstanceEnded(caseInstance);
```

`tests/itemcontrol/CompletionNeutralTest.java`, `testEventListenerBypassed`, whose model documents
it: "Task B inside the Stage has a Exit Criteria on a Completion Neutral Event Listener, the stage
should complete when TaskB complete even it the event is not triggered".

`UserEventListenerTest.testUserEventListenerInAutoCompletableStage`: "B is the only required now. So
completing it, should delete the event listener" (the case ends), and
`testRequiredUserEventListenerInAutoCompletableStage`: a *required* listener must occur before the
case ends.

`tests/itemcontrol/RepetitionRuleTest.java`, `testRepeatingTimer` (a timer `R/PT1H` whose
occurrence starts a repeating task; the plan model is not auto-complete):

```java
        // Completing all the tasks should still keep the case instance running
        ...
        // Terminating the case instance should remove the timer
        cmmnRuntimeService.terminateCaseInstance(caseInstance.getId());
        ...
        assertThat(cmmnManagementService.createTimerJobQuery().caseInstanceId(caseInstance.getId()).count()).isZero();
```

**What it means for Ventoux.**
- Flowable gets "listening doesn't keep the case open" only indirectly, through three mechanisms
  (orphan removal, completion-neutral, auto-complete), and a modeller has to know which applies.
  D10 says it directly: **listening is not waiting**. A rule that reacts to an outside event is not
  pending work, whatever state the case is in; only a step (or rule) explicitly waiting for the
  event is. Ventoux's default close is Flowable's auto-complete (brief, D10), where an available
  listener is already ignored, so the rule matches what Flowable does in the mode Ventoux chose.
- Orphan removal is the idea to keep for **timers**, which *are* pending work (brief, D10): a timer
  that can no longer do anything should not hold the case open. D7's `sla` cancels its timer when
  its step completes; the raw rule needs its own answer (a timer is cancelled when the moment it was
  set for has passed its use: the case closing, at least).
- `testRepeatingTimer` is D10's warning in a running engine: a timer that re-arms itself keeps the
  case open for ever. Ventoux's validator is to warn about it (brief, D10), and since layer 10 an
  error when it is proven (brief, D34).
- Ending the case removes its timers in Flowable; in Ventoux, closing cancels timers (brief, D10).

## 5. When does a stage or a case count as complete?

**Answer.** A container may complete when none of its children is active and no *required* child
is left to do. Whether it *does* complete by itself depends on auto-complete: with auto-complete,
`available` and `enabled` children (work that hasn't started, including manually activated items)
don't hold it; without, they do, and a person completes the case once it is *completable*. Some
items can be told to be ignored ("parent completion rules": ignore, ignore after first completion,
ignore if available or enabled). Completion is only judged once the children are stable.

`engine/util/PlanItemInstanceContainerUtil.java`, lines 60–66 (the method's description):

```java
    /**
     * Method to check a plan item container (most likely a stage or case plan model) if it should be completed according its child plan item states and their
     * combined behavior rules (e.g. repetition, if-part, manual activation, required, etc). The method returns two results: whether the plan item itself
     * is completable, which is the case when there is no more active or required work to be done, but it might still have optional work to do and a second
     * one which represents whether the plan item should in fact be completed (the difference being the state of the autocomplete mode, where if turned off,
     * only returns true, if there is no more work to be done and no more further options to activate some optional work).
```

and the line that makes not-yet-started work count only without auto-complete, lines 143–146:

```java
                    // if the plan item is in available or enabled state, we ignore it, if we look at it with autocompletion in mind
                    if (AVAILABLE.equals(planItemInstance.getState()) || ENABLED.equals(planItemInstance.getState())) {
                        shouldBeCompleted = shouldBeCompleted && containerIsAutocomplete;
                    }
```

Stable children first, `engine/agenda/operation/AbstractEvaluationCriteriaOperation.java`, line 379:

```java
        if (!autoComplete || evaluateStagesAndCaseInstanceCompletion) { // auto completion should only be evaluated when children are stable
```

**The tests.** `tests/itemcontrol/RequiredRuleTest.java`, `testOneRequiredHumanTask` (auto-complete
plan model; a required task and an optional one):

```java
        // Completing the task should autocomplete the plan model, as the plan model is autoComplete enabled
        ...
        // Completing the required task should not autocomplete the plan model
```

(the first case started only the required task, so it ends; the second started both, so the
optional one, now active, holds it). `testCompleteCaseInstanceManually` (not auto-complete):

```java
        // Case should not be completeable
        assertThatThrownBy(() -> cmmnRuntimeService.completeCaseInstance(caseInstance1.getId()))
                .isInstanceOf(FlowableIllegalArgumentException.class)
                .hasMessage("Can only complete a case instance which is marked as completeable. Check if there are active plan item instances.");

        // Completing both tasks should not auto complete the case, as the plan model is not auto complete
```

`tests/itemcontrol/ManualActivationRuleTest.java`, `testSingleHumanTask`: a manually activated task
is `ENABLED`, the case does not end until a person starts it and completes it.
`tests/runtime/CaseCompletionExitSentryTest.java`, `testCompleteCaseThroughExitSentryWithException`:
an exit sentry with the `complete` event type is refused while a task is active ("Cannot exit case
with 'complete' event type"), and succeeds once it has completed; a `forceComplete` variant ends the
case whatever is running.

**What it means for Ventoux.**
- Ventoux's default close, "nothing left to do" (brief, D10), is Flowable's auto-complete without
  required items: steps waiting to be proposed don't hold the case, running and open work does.
  `stays_open` is close to Flowable's non-auto-complete case completed by a person.
- Flowable's "required" has no counterpart yet; "required steps" are listed after layer 15 in the
  curriculum. Nothing in layer 11 needs it.
- Flowable's `complete` exit, refused while work is active, and `forceComplete`, which ends it
  regardless, are the two answers Ventoux rejected in favour of a third: `closes_when` begins
  *closing*, where running work finishes and nothing new starts (brief, D10), and a failed run holds
  the close (brief, D26, D34). Rules must fit that: whether a rule may still act once every
  `closes_when` milestone is reached is the open question for layer 11.
- "Only once the children are stable" is what Ventoux's `decide` already does: it admits steps
  until nothing more starts, then settles. Rules have to run inside that loop, before the case
  settles, or a case could close between a rule's trigger and its action.

---

## In one table

| Question | Flowable | For Ventoux (proposed in `11-rules.md`) |
|---|---|---|
| When is a met part forgotten? | default: remembered until the item starts or ends; `onEvent`: at the end of the evaluation | nothing is remembered: a rule reacts to a moment, read then; admission keeps re-reading state |
| What does an exit stop? | the item in any state (or only active ones); running work is deleted | stopping a step does to it what a close does: open work cancelled, running work finishes and is flagged; a failed run is never stopped |
| What does a repeated run see? | the case's variables as they are, plus a local counter and item | the case file as it is; the run is named by its entry |
| Listening vs waiting | an available listener holds a non-auto-complete case unless orphaned or completion-neutral | listening never holds the case; a timer does, until cancelled |
| When complete? | no active and no required work; with auto-complete, not-started work doesn't count | unchanged (brief, D10); rules run before the case settles, and the close rules them too |
