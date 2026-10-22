# Layer 12, research: how running work survives a change

Status: prior art, read 2026-10-22, before layer 12's design. Not a decision: what each finding
means for Ventoux is proposed in `docs/layers/12-releases.md` and decided there, with the user.

## What was read, and how

- **Reached:** this environment's network reaches GitHub. Each source was cloned read-only into
  the session's scratch directory, never into this repository; no code from them is copied into
  Ventoux, and the quotes below are for reading.
  - Temporal's Python SDK, `temporalio/sdk-python` at commit `c4de91d` (2026-10-22), version
    1.34.0, the version Ventoux depends on. Its `temporalio/bridge/sdk-core` is a submodule that
    wasn't fetched, so what Temporal's core (Rust) writes to history is read from the SDK's tests,
    its protocol docstrings and the docs, never from core's code.
  - Temporal's documentation, `temporalio/documentation` at commit `82ac5bd` (2026-10-21).
  - Flowable's engine, `flowable/flowable-engine` at commit `f6017e3` (2026-10-16, the commit the
    layer 11 research and the checkpoint read), sparse: the CMMN case instance migration code, its
    tests and their models, and the `runtime`, `cmd` and `job` folders the migration calls.
  - The `chartering` prototype, `francoisnyc/chartering` at commit `197d519`. It isn't public;
    this session was given read access to it, and cloned it beside this repository
    (`/home/user/chartering`), outside it.
- **Prefixes used below.** For the SDK, paths are from its root (`temporalio/…`, `tests/…`); for
  the docs, from theirs (`docs/…`). For Flowable:
  - `engine/` is `modules/flowable-cmmn-engine/src/main/java/org/flowable/cmmn/engine/impl/`;
  - `api/` is `modules/flowable-cmmn-api/src/main/java/org/flowable/cmmn/api/migration/`;
  - `tests/` is `modules/flowable-cmmn-engine/src/test/java/org/flowable/cmmn/test/migration/`,
    each test's model under the matching `src/test/resources/` folder.
- **The tests were read first,** as in layer 11: they say what the code is for. Each quote was
  checked against the clone it names.
- **Three of the curriculum's names don't match the prototype.** `scripts/migration-demo.ts` does
  not exist: the migration story is step 9 of `examples/cases/insurance-claim/script.json`, run by
  `scripts/temporal-case-demo.ts`. `docs/design.md` §8 is "Versioning", and says nothing of
  releases, digests, activation or worker manifests: those are the brief's own (D5), not the
  prototype's. Change requests are design §7's "requests held for a second person".
- **Each source's words stay its own** inside quotes (patch, marker, build ID, plan item, sentry,
  fragment, Charter, held request). Ventoux's words are used only in "What it means for Ventoux".

---

## 1. Temporal: patching

**In one line:** a patch is a named branch whose answer is recorded in the run's history the first
time it is asked; a run that has already answered "old" keeps answering "old" until it ends.

**1.1. What `patched` answers.** `temporalio/workflow/_context.py`, the docstring of `patched`:

> When called, this will only return true if code should take the newer path which means this is
> either not replaying or is replaying and has seen this patch before.

**1.2. The answer is decided once per run, and memoised.** `temporalio/worker/_workflow_instance.py`,
`workflow_patch`:

```python
        use_patch = self._patches_memoized.get(id)
        if use_patch is not None:
            return use_patch
        ...
        if deprecated or self._is_replaying or id in self._patches_notified:
            use_patch = not self._is_replaying or id in self._patches_notified
        ...
        self._patches_memoized[id] = use_patch
```

A marker command is added only when the answer is true. On replay the answer is true only if the
history holds the marker (`_patches_notified`, filled by core before any signal is applied).

**1.3. The test that shows a run keeps its first answer.** `tests/worker/test_workflow.py`,
`test_workflow_patch_memoized`. The workflow asks `patched("some-patch")` before and after a
signal; a run started under the unpatched code, then picked up by the patched worker, answers
false the second time too, though that second call runs new code after replay has ended:

```python
        assert ["some-value"] == await pre_patch_handle.result()

        assert [
            "pre-patch",
            "some-value",
            "post-patch",
        ] == await post_patch_handle.result()
```

The docs say the same, `docs/encyclopedia/workflow/patching.mdx`:

> During a Replay, if there is no marker for a given patch ID, the execution will return `false`
> and will not add a marker to the event history. In addition, all future calls to `patched()`
> with that ID will return `false` -- even after it is done replaying and is running new code.

**1.4. What history holds.** `tests/worker/test_event_groups.py` counts a `core_patch` marker per
patch, and a `TemporalChangeVersion` search attribute upserted beside each:

```python
    patches = _markers_named(events, "core_patch")
    assert len(patches) == 2
    # EG-COMMANDS-21 plus the two TemporalChangeVersion upserts beside the patches
```

**1.5. Where a patch may be asked.** The docs (`patching.mdx`): "If that patch ID exists later,
you get a non-determinism error. If the patch doesn't exist later, you don't get a
non-determinism error, and the call returns `false`", and they advise asking the newest first:
`if patched('v3') … elif patched('v2') … else`. A query can't ask one:
`_workflow_instance.py` calls `self._assert_not_read_only("patch")`, and
`test_workflow_queries_doing_bad_things` asserts `"While in read-only function, action
attempted" in str(err)`.

**1.6. The lifecycle: patch, deprecate, remove.** `docs/develop/python/workflows/versioning.mdx`:

> 1. Patch in any new, updated code using the `patched()` function. … 2. Remove old code and use
> `deprecate_patch()` to mark a particular patch as deprecated. 3. Once there are no longer any
> open Workflow Executions of the previous version of the code, remove `deprecate_patch()`.

and, on replay, a worker "will fail the Workflow task when the Workflow code doesn't produce the
same patch marker", while deprecated markers "won't cause a replay failure". `test_workflow_patch`
runs the four versions (pre-patch, patch, deprecate, post-patch) against each other's histories;
the one case it leaves untested is in a comment: removing the call while a non-deprecated marker
is in history "causes a non-determinism failure … but we don't have an easy way to test it".

**1.7. The SDK versions its own behaviour the same way.** `tests/worker/test_replayer.py`,
`test_replayer_command_reordering_backward_compatibility`, docstring: "The test passes because
core in fact (because the history lacks the flag) uses its old logic". The SDK records which of
its own logic changes a history was made under (`sdk_metadata.lang_used_flags`), and replays an
old history with the old logic.

**1.8. A new, experimental hook.** `temporalio/worker/_worker.py`, `patch_activation_callback`:
"Callback to decide whether the first non-replay call to `workflow.patched` for a patch ID should
activate that patch … WARNING: This is an experimental feature". A declined patch lets an old
worker finish the run (`test_workflow_declined_patch_rolls_out_to_old_worker`).

**What it means for Ventoux.**

- A patch answers "which code made this part of the history", and keeps the old answer for the
  rest of a run (1.2, 1.3). For a case, a run lasts until it continues as new (D27), a point
  chosen by an event count, not by anyone: a case open before a fix would take the fix at its
  next switch, silently, mid-case. That is a behaviour change nobody approved and no history line
  says, against "nothing a person did is undone silently".
- Asked inside `decide`, it would bring Temporal into `case`. Asked in the driver and passed in,
  it stays outside: that is the "patch marker passed to `decide` as event data" the fix of the
  retry rejected named.
- What 1.7 shows is the shape Ventoux needs: the history says which logic made it, and replay
  reads the old logic from that, as data. A case can carry its engine version the same way, in
  its own state, asked once when it opens (1.5's newest-first chain is how), and crossing
  continue-as-new with the rest of the state (D27), so it never changes by itself.
- The lifecycle (1.6) is the one old engine versions need: kept while any open case uses them,
  then removed, with a replay test proving none is left.

## 2. Temporal: worker versioning

**In one line:** a pinned workflow runs to its end on the build it started on; an auto-upgrade
workflow moves to the newest build and needs patches.

**2.1. The two behaviours.** `temporalio/common.py`, `VersioningBehavior`:

```python
    PINNED = ...
    """The workflow will be pinned to the current Build ID unless manually moved."""
    AUTO_UPGRADE = ...
    """The workflow will automatically move to the latest version (default Build ID of the task
    queue) when the next task is dispatched."""
```

A version is a deployment name and a build ID (`WorkerDeploymentVersion`, `deployment_name`,
`build_id`); `WorkerDeploymentConfig` and `deployment_config` are marked "experimental".

**2.2. The test that shows both.** `tests/worker/test_worker.py`,
`test_worker_with_worker_deployment_config`: three workers on one task queue (1.0 auto-upgrade,
2.0 pinned, 3.0 auto-upgrade), the current version moved forward each time:

```python
    assert res1 == "version-v3"
    assert res2 == "version-v2"
    assert res3 == "version-v3"
```

The workflow started on 1.0 finished on 3.0; the pinned one stayed on 2.0. Each workflow task's
completion records the behaviour and the build in history
(`workflow_task_completed_event_attributes.versioning_behavior`, `.worker_version.build_id`).

**2.3. Fail closed at the worker.** With worker versioning on, a workflow that names no behaviour
and has no default is refused when the worker is built: `test_worker.py` asserts `"must specify a
versioning behavior" in str(exc_info.value)`.

**2.4. When to pin.** `docs/production-deployment/worker-deployments/worker-versioning/index.mdx`:

> Pinned Workflows don't need to be patched, as they run on the same worker and build until they
> complete.

> If you expect your Workflow to run longer than you want your Worker Deployment Versions to
> exist, you should mark your Workflow Type as Auto-Upgrade.

Its table gives "`PINNED` + upgrade on CaN" for workflows that run "Months-Years" and continue as
new. Older pinned versions drain: "**Drained**: The version was draining and now all the pinned
Workflows that were running on it are closed" (`docs/encyclopedia/workers/worker-versioning.mdx`).

**2.5. Continue-as-new.** The same page: "Auto-upgrade Workflows never inherit versions", and a
pinned version "is inherited across the Continue-As-New chain". Moving a pinned chain to a new
build at a switch is `continue_as_new(..., initial_versioning_behavior=AUTO_UPGRADE)`, tested in
`test_continue_as_new_with_version_upgrade` (`if info.is_target_worker_deployment_version_changed():`);
the docs mark it "Public Preview as an experimental SDK-level option".

**What it means for Ventoux.**

- Pinning answers a question about *code* (which build replays this history), not about a case's
  *rules*: a pinned case still runs the release it started on only because its definition is in
  its history; and pinning keeps every old build running for as long as a case is open (months),
  or moves it at a switch nobody chose (2.5), the same objection as 1.3.
- D5 already gives worker versioning its place: "workflow code relies on Temporal's worker
  versioning" for implementation changes. For case workflows, which carry what decides in data,
  auto-upgrade plus Ventoux's own engine version fits the docs' rule (2.4): a case outlives any
  build.
- 2.3 is the shape for activation's checks: refuse at startup what can't be served, never let it
  fail later.
- A build ID is not what activation checks: D5's worker manifest lists the *contracts* a worker
  serves, with their hashes, which nothing in Temporal knows.

## 3. Temporal: replay testing

**3.1. The API.** `temporalio/worker/_replayer.py`: `Replayer(workflows=…)`,
`replay_workflow(history, *, raise_on_replay_failure=True)`, `replay_workflows(histories, *,
raise_on_replay_failure=True)`. There is no `fail_fast` parameter in the SDK; the docs' mention
of one (`docs/develop/python/best-practices/testing-suite.mdx`) is stale.

**3.2. The error.** A history the code doesn't reproduce raises
`temporalio.workflow.NondeterminismError`; `tests/worker/test_replayer.py` quotes one:
`[TMPRL1100] Nondeterminism error: Update machine does not handle this event: HistoryEvent(id: 6,
WorkflowExecutionCompleted)`.

**3.3. A stored history, replayed.** `tests/worker/test_replayer.py`:

```python
    await Replayer(workflows=[SayHelloWorkflow]).replay_workflow(
        WorkflowHistory.from_json("fake", history_json)
    )
```

and `test_replayer_nondeterministic_history.json` under `pytest.raises(workflow.NondeterminismError)`.
`test_replayer_multiple_histories_fail_slow` collects every failure with
`raise_on_replay_failure=False`, keyed by run ID.

**3.4. The docs' recipe for CI:** "Download the Event Histories of a representative set of recent
open and closed Workflows … Run the Event Histories through replay. Fail CI if any error is
encountered during replay."

**What it means for Ventoux.** Ventoux already does this (`tests/histories/`, a fixture per layer
that changed what a case decides). Layer 12 adds two kinds: histories recorded before layer 12
that must replay as they are, and, once a case carries its engine version, a history made under
one engine version replayed by code that knows a newer one. The collecting form (3.3) is what a
cohort's check before an engine's old version is removed needs (1.6).

## 4. Flowable: migrating a running case

**In one line:** a migration document maps plan items by their definition IDs; what has no
counterpart is terminated, quietly; the history is rewritten to the new definition.

**4.1. The migration document.** `engine/migration/CaseInstanceMigrationDocumentConstants.java`
names its keys: the target (`toCaseDefinitionId`, or `toCaseDefinitionKey` and
`toCaseDefinitionVersion`), `enableAutomaticPlanItemInstanceCreation`, the mapping sections
(`activatePlanItemDefinitions`, `terminatePlanItemDefinitions`,
`moveToAvailablePlanItemDefinitions`, `waitingForRepetitionPlanItemDefinitions`,
`removeWaitingForRepetitionPlanItemDefinitions`, `changePlanItemIds`,
`changePlanItemIdsWithDefinitionId`, `changePlanItemDefinitionWithNewTargetIds`),
`caseInstanceVariables`, and two expressions, `preUpgradeExpression` and `postUpgradeExpression`.
Every mapping is keyed by a definition ID, with an optional condition
(`api/PlanItemDefinitionMapping.java`, `PlanItemDefinitionMapping(String planItemDefinitionId,
String condition)`): by name, never by position.

**4.2. What has no counterpart is terminated, without asking.**
`engine/runtime/AbstractCmmnDynamicStateManager.java`,
`executeTerminateNonExistingPlanItemInstancesInTargetCmmnModel`:

```java
if (!excludePlanItemDefinitionIds.contains(currentPlanItemDefinitionId) && targetCmmnModel.findPlanItemDefinition(currentPlanItemDefinitionId) == null) {
    ...
        if (!PlanItemInstanceState.TERMINAL_STATES.contains(currentPlanItemInstance.getState())) {
            terminatePlanItemInstance(currentPlanItemInstance, commandContext);
```

The test, `tests/CaseInstanceMigrationTest.java`, `withNoNewPlanItemForPlanItemInstance` (a
two-task case migrated to one task, no mappings):

```java
assertThat(planItemInstances).filteredOn("name", "Task 2")
        .extracting(PlanItemInstance::getState).containsOnly(PlanItemInstanceState.TERMINATED);
```

**4.3. A rename passes validation and replaces the work.**
`tests/CaseInstanceDirectPlanItemMigrationTest.java`, `directMigrateRenameTaskIdCase`: the model
renames `humanTask1` to `humanTask2`;

```java
assertThat(validationResult.isMigrationValid()).isTrue();
...
assertThat(task.getName()).isEqualTo("Task 1 updated");
```

By 4.2 and automatic creation, the old task is terminated and a new one made: validation said
nothing. Keeping the work under a new name takes an explicit mapping,
`changePlanItemDefinitionWithNewTargetIds`, which relabels the instance and its task in place
(`currentPlanItemInstance.setPlanItemDefinitionId(...)`, `task.setTaskDefinitionKey(...)`); its
test asserts `historicTasks).hasSize(1)`.

**4.4. Running work.** A kept human task is the same row, pointed at the new definition, its name
and form key copied from the new model where the model changed them
(`navigatePlanItemInstances`: `task.setScopeDefinitionId(caseDefinition.getId());`). Terminating
cascades: `terminatePlanItemInstance` deletes the task, the child process
(`deleteProcessInstance`), the child case (`deleteCaseInstance`), timer jobs and event
subscriptions. A kept event listener keeps its subscription
(`tests/CaseInstanceEventSubscriptionMigrationTest.java`, `withBasicEventRegistryEvent`:
`assertThat(eventSubscriptions).hasSize(1)` before and after); no migration test has a timer.

**4.5. Remembered sentry parts survive only if nothing about them changed.**
`verifySatisfiedSentryPartsForCriterion` keeps a satisfied part only when the criterion, the
sentry's ID and the condition's text match the new model; otherwise its memory is deleted.

**4.6. The order of operations is fixed.** `doMovePlanItemState`: verify sentry parts; terminate;
terminate what has no counterpart; re-point; change IDs; navigate; set variables; activate stages,
then other items; finally `agenda.planEvaluateCriteriaOperation`, which reads every sentry again
under the new model.

**4.7. What is checked before.** `api/CaseInstanceMigrationValidationResult.java` is a list of
strings (`isMigrationValid()` is `validationMessages.isEmpty()`). `doValidatePlanItemMappings`
checks only that the target exists and that each ID a mapping names exists in it:

```java
validationResult.addValidationMessage("Invalid mapping for activate plan item definition '" + planItemDefinitionId + "' cannot be found in the case definition");
```

(`tests/CaseInstanceMigrationValidationTest.java` asserts these messages.) It never lists what
would be terminated. And `migrate()` doesn't validate first
(`CaseInstanceMigrationBuilderImpl.migrate` calls `migrateCaseInstance` directly): a bad mapping
fails at run time.

**4.8. A cohort, one transaction per case.** Batch migration stores the document as JSON
(`.batchDocumentJson(document.asJsonString())`), runs one job per case with no retry, and records
each result (`"success"` or `"fail"`, with the message). `tests/CaseInstanceMigrationBatchTest.java`,
`testCaseInstanceBatchMigrationWithWrongMapping`: each part fails with `"Cannot find plan item
with definition id 'nonExisting'"`, and each case is left on version 1. A synchronous migration of
every case of a definition runs in one command: one failure rolls back all of them.

**4.9. Code in the document.** `preUpgradeExpression` and `postUpgradeExpression` are evaluated
expressions (`createExpression(document.getPreUpgradeExpression()).getValue(caseInstance)`); the
test `withPreUpgradeExpression` uses one that sets a variable. And a mapping's condition that
gives anything but `true` is false (`return conditionResult instanceof Boolean condition &&
condition;`): a condition it can't read skips the mapping silently.

**4.10. History is rewritten, not added to.**
`historyManager.updateCaseDefinitionIdInHistory(caseDefinitionToMigrateTo, caseInstance);` points
every historic plan item and task, ended ones included, at the new definition; the tests assert
`historicPlanItemInstance.getCaseDefinitionId()).isEqualTo(destinationDefinition.getId())`. No
entry says "migrated from 1 to 2", and a migration checks no permission (no match for
`permission|authoriz|identityLink` in the migration code). A completed case is migrated by a
separate call that only re-points it, and refuses a running one: `"Historic case instance has not
ended and can only be migrated with the regular case instance migrate method"`.

**What it means for Ventoux.**

- **Names, as D2 and D5 say,** and an explicit rename that keeps the run (4.1, 4.3): Ventoux maps
  steps, milestones, fields, rules, timers and events by name, never by position.
- **Every one of Flowable's permissive defaults is one Ventoux refuses:** a run with no
  counterpart terminated (4.2: it is the curriculum's "unmapped rename that running work depends
  on", refused; D10, "running work finishes"); a rename read as a new step (4.3); validation that
  doesn't list what would end (4.7: Ventoux's preview says everything the migration does); a
  migration that may apply unchecked (4.7: Ventoux's apply checks again, depending on nothing the
  preview did, D34's rule); a condition read as false (4.9: fail closed); code in the document
  (4.9: a non-negotiable); history rewritten (4.10: Ventoux's history is Temporal's, append-only,
  and says what changed); no permission (4.10: a change request, approved by someone else).
- **Worth taking:** the fixed order, ending with every condition read again under the new
  definition (4.6), which in Ventoux is admission after the migration's decision; one case at a
  time, each with its own result (4.8), which a case workflow per case gives at once; a closed
  case treated apart (4.10), which in Ventoux is simply refused: a closed case has nothing to
  migrate.
- 4.5 is the memory D38 chose not to have: a rule remembers nothing, so a migration has no
  half-met condition to keep or lose.

## 5. The prototype: `src/case/migrate.ts`, `src/case/requests.ts`, the demo

**5.1. The mapping.** `src/case/migrate.ts`: only milestones and fields map; a name missing from
the mapping keeps its name, `null` drops it:

```ts
      const target = m in mm ? mm[m] : m;
```

Fragments meet the new version by name; deadlines missing from it are cancelled, those kept keep
their old due time; held sentries the new version lacks vanish (`runtime.ts`, `// gone after a
migration`).

**5.2. What it refuses.** Among them: a migration not by a person, or approved by its requester
(`'the requester cannot approve their own migration'`); a reached milestone the new version lacks
(`MILESTONE_REMOVED`, `reached milestone "${m}" does not exist in version ${to.version} … ; map it
or drop it`); a field removed or of another type; a running fragment that will write what the new
version lacks:

```ts
          err(`running.${name}`, 'RUNNING_FRAGMENT_FIELD', `${name} is running and will update file.${k}, which version ${to.version} does not have; map it, or migrate after ${name} finishes`);
```

and a deadlock in the new version from the milestones the case has reached.

**5.3. Running work finishes under what it started with,** its writes renamed through the
mapping; values keep their tags (`file[target] = t; // provenance is kept`); the case records
`state.definition = \`${to.id}@${to.version}\``. An approver signs a digest of the definition,
the library and the mapping (`migrationDigest`), so a claim binds content, not a name.

**5.4. A preview, and a cohort.** `previewMigration` runs the migration on a copy of the state;
`planCaseMigration` (`src/temporal/case-client.ts`) previews every open case of a type, skipping
closed ones, ones already on the version, and ones whose definition it doesn't have.

**5.5. Requests.** `requests.ts`: kinds `'edit' | 'migrate' | 'adhoc' | 'restart'` (no skip); a
request is approved by someone else (`'you cannot approve your own request'`), re-checked in full
when approved, and named for good (`requestIdTaken`). An edit (`src/case/edits.ts`) tags the new
value with the field's edit label (`makeTags(policy!.label)`, "a person verifying an LLM-extracted
value makes it trusted"); nothing lapses on an edit.

**5.6. The demo** (`examples/cases/insurance-claim/script.json`, step 9): a claim migrated from v1
to v2 by `adjuster-1`, approved by `adjuster-2`, "New policy: fraud check before every payout"; v2
adds `fraud_checked` and makes `pay` require it; afterwards `propose pay` is refused, "requires
milestone(s) fraud_checked" (`test/migrate.test.ts`), and the customer's message keeps
`untrusted:llm`.

**5.7. Design §7 and §8.** "Everything is pinned to an exact version"; a running fragment "stays on
the Charter it started with, until it finishes or is restarted"; and, the curriculum's question:

> Charters are the only topology, so they stay small. A running Charter is a graph with a
> position, and it stays on its version: that is also what makes an approval signed against its
> exact content mean something.

Engine changes: "Temporal worker versioning / `patched()` … definition checks are recorded, so new
rules don't fail running cases".

**What it means for Ventoux.**

- **Taken:** names, with renames written explicitly; a reached milestone the new release lacks
  refused (D48's "reached once, never undone"); running work finishing on what it started with,
  its results landing under the mapped names; provenance kept through a migration, never
  re-stamped; the approver signing the content (a digest of release and mapping); a preview per
  case and across a cohort; the demo's story, which is the first migration test to write.
- **Refused, because the prototype is looser than Ventoux's rules:**
  - an unmapped name silently carried, and `null` dropping a field with its provenance and no
    record: every name that running work or the case file depends on is mapped or refused, and
    what is dropped is said in the history;
  - a migration that doesn't check its source is the case's release (it takes `from` from its
    caller), nor the roles of who asks and approves, nor that the target was ever released; a
    request with no roles meaning "any person": fail closed;
  - a running fragment whose spec isn't found, skipped (`if (!spec) continue;`), and a cohort
    preview that skips cases it can't read: each is an error, said;
  - an edit's title and history quoting the value (`` `Change file.${req.field} to
    ${JSON.stringify(req.value)}` ``): no message quotes a value from the case file (D30);
  - an edit making untrusted data trusted by re-tagging it: an edit is a person's value, sourced
    to that person (D43: "a person is where it ends"), never a laundered copy of the old one;
  - nothing lapsing on an edit: D11 and D25 make an approval lapse when what it saw changes;
  - deadlines keeping their old due time when the rule's age changed, and sentries vanishing:
    what happens to each timer is decided and said.
- **Plans don't migrate** (5.7): a plan run has a position, and its approvals were given against
  its exact content. In Ventoux a plan step runs as its own child workflow with its plan in its
  start (D28), so a running plan finishes on the plan it started with, whatever happens to its
  case.

## 6. What the four sources agree on

- **A running thing finishes on what it started with:** a pinned workflow on its build (2.1), a
  prototype fragment on its spec (5.3), a Flowable task on its row (4.4), a Ventoux plan on its
  plan (D28) and an activity with its result (D10).
- **Old behaviour is read from the history, as data:** a patch marker (1.4), the SDK's own logic
  flags (1.7), the prototype's `state.definition` (5.3). Ventoux's case already carries its
  definition in its start (`CaseStart.definition`, D27); layer 12 adds which release and which
  engine version.
- **None of them does what Ventoux's rules ask of a migration:** approved by someone else and
  checked again when applied; nothing a person did undone silently; the history saying what
  changed, never quoting a value; untrusted data never made trusted on the way.
