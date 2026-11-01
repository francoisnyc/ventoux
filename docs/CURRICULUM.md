# Ventoux — building it layer by layer

Status: draft, 2026-10-04. Order: layer 0, the tracer bullet, layer 1, the spike, layers 2–15.
Layers 16–21, the rest of v1.0, were added on 2026-10-31, after layer 15. They are drafts: each
layer's design note may change what they say.
Each layer is one pull request. Don't start a layer until the previous one is merged and you can
explain it in your own words.

References point to the `chartering` prototype, which is written in TypeScript; Ventoux is built in
Python (decision D4). Read them to understand an idea; don't copy whole
files. Every layer should end up smaller and clearer than its prototype.

## How each layer runs

0. **Warm-up:** one earlier check-yourself question from `docs/LEARNING.md`, answered from memory
   (an open question first; otherwise one closed at least two layers ago). Recalling it later is
   what makes it stick; record the answer in the log.
1. **Explain:** the assistant explains the concept and the design choice, with a small example.
2. **Document first:** update the user-facing docs (the quickstart, or the guide for this layer's
   persona) to describe the layer as if it already worked. If it is hard to explain, revisit the
   design before building.
3. **Decide:** you agree on a short design note (a few paragraphs in `docs/layers/NN-name.md`).
4. **Agree the seams:** name the public interfaces the tests will use (for example "the catalog's
   lookup" or "`validate()` returns issues"), never internals, so the tests survive refactoring.
5. **Build test-first, one slice at a time:** one failing test (start with the negative one) →
   the least code that passes it → the next test. Watch each fail for the right reason. Don't write
   all the tests up front: each test should respond to what the last one taught. Tidy up once the
   slice is green. Where the docs show an example, a test runs it, so the docs can't drift from the
   code.
6. **Check the promises:** the design note ends with a "Promises" table: each claim about behaviour
   and the test that proves it. A claim without a test gets one, or leaves the note. The reviewer
   checks the table against the code (twice a note promised what the code didn't do).
7. **Walk through:** the assistant walks you through the code; you ask questions until it's clear.
8. **Check yourself:** answer the layer's questions below. If you can't, don't move on.

This loop is a small version of QRSPI (question, research, design, structure, plan, implement): the
brief and this curriculum already answer the questions and the design, so each layer starts at the
design note. Full QRSPI is kept for later work that cuts across several layers.

---

## 0. Repository and conventions

- **Learn:** the project's rules, and why the core stays free of Temporal and LLM code.
- **Build:** Python 3.12+, a project managed with `uv`, Pydantic, pytest, ruff, and strict type
  checking (pyright or mypy); CI running tests, type checks and linting; `CLAUDE.md`, the brief,
  this curriculum and the quickstart draft in the repo.
- **Done when:** CI is green on an empty test suite and the layout matches the brief's layers.
- **Check yourself:** why must `core` run inside a Temporal workflow?

## Tracer bullet (after layer 0): the quickstart's refund case, end to end

- **Learn:** a tracer bullet is a thin path through the whole system, built first and deepened
  later. Seeing a case run from opening to closing shows what every later layer is for, and tests
  the quickstart's design against real code in the first week rather than at layer 8.
- **Build:** the refund case from `docs/QUICKSTART.md`, running in memory, crudely: its definition
  as a JSON file (`examples/refund/refund.json`, the shape `ventoux check` would produce, written by
  hand since the builder comes at layer 14); a fake `payments.refund@1`; scripted answers; a small
  loop that opens the case, runs `review`, checks `pay`'s condition and approval, runs it, and
  closes when nothing is left to do; and `ventoux.testing.run_case` with the shape the quickstart
  shows. Every crude part carries a `# TRACER:` comment naming the layer that replaces it
  (catalog: 1, expressions: 2, validation: 3, provenance: 4, interpreter: 5, Temporal: 6,
  approvals and roles: 7, case runtime: 8).
- **Tests:** the quickstart's three tests (small refund, large refund waiting for a team lead,
  rejected review), run against the JSON definition. They stay for good as acceptance tests: every
  later layer must keep them green, and at layer 14 they switch to the Python definition exactly as
  the quickstart shows.
- **Negative test:** an answer with an outcome the task doesn't declare is refused; a refund over 100
  is not paid until someone other than the reviewer approves.
- **Done when:** the three tests pass, every `# TRACER:` comment names its layer, and anything the
  quickstart got wrong or left unsaid is recorded as a new design question in `docs/BRIEF.md`
  (numbered from 10).
- **Reference:** `docs/QUICKSTART.md`; the prototype's `scripts/migration-demo.ts` shows a case run
  end to end.
- **Check yourself:** what did running the quickstart teach you that reading it didn't?

## 1. Activities and the catalog

- **Learn:** capabilities as versioned contracts; risk classes; why definitions only reference them.
- **Build:** an activity contract (name, version, input and output schemas, risk, effect, retry
  policy and timeouts, idempotency, declared failure outcomes; decision D17) and a catalog with
  lookup by `name@version`. Two or three mock activities. First, close a loophole in layer 0's
  boundary test found in review: relative imports (`from ..temporal import worker`) aren't checked,
  so ban them with ruff's `TID252` rule, and every import names its layer.
- **Negative test:** a relative import in `src/` fails `ruff check`; an unknown name or version is
  not found; a reused `name@version` with different
  content is refused; a contract whose hash changed without a new version fails the CI check; a
  side-effecting contract without idempotency is refused.
- **Reference:** `src/core/registry.ts`, `src/activities/catalog.ts`; `docs/design.md` §8.
- **Check yourself:** why `@1` and not `@1.0`?

## Spike (one or two days, before layer 2): existing standards for plans and expressions

- **Learn:** what Serverless Workflow 1.0 (the CNCF standard, run on Temporal by Zigflow) offers, and
  what it would cost to adopt it for plans instead of our own format. And how CEL (Common
  Expression Language) and structured JSON expressions (an expression tree stored as JSON, written
  by people through the builder) compare with our JSONata subset (design question 11).
- **Do:** express the `claim-pay` plan and the small claim case from the prototype in Serverless
  Workflow 1.0. For each, list what fits, what is missing (provenance, sink policies, approvals on
  every path, case semantics), and what we would have to forbid (scripts, shell, containers,
  non-deterministic expressions). Write the conditions, inputs and updates of the claim case in the
  JSONata subset, CEL and structured JSON; compare readability for people, ease of parsing,
  typing, provenance analysis, model output constrained by a JSON Schema, exact diffs, and Python
  support (`jsonata-python`; `cel-python` or Google's `cel-expr-python`).
- **Output:** a short note in `docs/layers/spike-dsl.md` with a recommendation: adopt it for
  plans (keeping our case layer), offer import/export later, or keep our own format. No product
  code. For expressions: keep the JSONata subset, or switch to CEL or structured JSON.
- **Reference:** the Serverless Workflow specification and its Python SDK; Zigflow; the CEL
  specification and its implementations.
- **Check yourself:** which of our guarantees could not be expressed as a restriction of the
  standard, and why?
- **Done:** `docs/layers/spike-dsl.md`. Plans keep our own format; expressions are structured JSON
  with a fixed list of operators (D20).

## 2. Plan schema and expressions

- **Learn:** a plan as a state machine of data; expressions as data (structured JSON, decision D20);
  why some things can't even be written; why a missing value is an error, not `false`.
- **Build:** the plan schema (activity, wait and final states; transitions); expressions with D20's
  operators: the Pydantic models, a type check against declared fields (outcomes as closed lists),
  a fail-closed evaluator and the one-line rendering. The tracer's minimal form (`=`, `field`)
  becomes `==` and `var`.
- **Negative test:** an unknown operator (`now`, `map`) is rejected with one clear message; a
  misspelled outcome and a text compared with a number are rejected; a malformed plan is rejected;
  evaluating with a missing field, or an operator the evaluator doesn't know, raises an error,
  never returns false (fail closed); `{"/": [x, 0]}` raises an error; and, as a positive check on
  exact decimals, `{"==": [{"+": [0.1, 0.2]}, 0.3]}` is `true`.
- **Reference:** `src/core/schema.ts`; `docs/design.md` §2; `docs/layers/spike-dsl.md` and its
  `structured.py` sketch. The prototype's `src/core/expr.ts` shows the JSONata version, and why it
  failed open.
- **Check yourself:** why can't `now` be written at all, and what would break on Temporal replay if
  it could?

## 3. Static validation

- **First:** the readability refactor of layer 2's `core/expressions.py` (1,043 lines, five jobs):
  split it into a package, one module per job (the models and parsing, the type check, evaluation,
  rendering), as a pure move: no behaviour change, tests unchanged and green. Then the same for
  layer 1's `core/catalog.py` (agreed in the tutor session):
  split it into `contract.py` (a contract and what it refuses), `catalog.py` (lookup) and
  `contract_hash.py` (the hash and the CI check); a one-line comment per field; a comment on each
  Pydantic idiom the first time it appears; the reference check readable (commented or a small
  function); every error message in the same shape (what's wrong, then what to do). No behaviour
  change: all tests stay green, and one new test checks that every rule in the design note is
  registered on the contract, so a rule can never silently stop running. One fix found in the
  tutor session: `model_copy(update=...)` skips every check, so a copied contract with risk
  `"hihg"` and a `write` with no idempotency key was accepted into the catalog. `Catalog.register`
  must re-check every contract it receives (Pydantic's `revalidate_instances="always"`), with a
  negative test: a copy that breaks a rule is refused at registration. Also a reference check: every
  decision cited in `src/` ("brief, D5") exists in the brief and is not superseded.
- **Learn:** what can be proven by reading a definition: references exist, states are reachable,
  high-risk activities are behind an approval on every path.
- **Build:** a validator returning structured issues (`path`, `code`, `message`).
- **Negative test:** an unreachable state; a high-risk activity reachable without `APPROVED`
  (`APPROVAL_REQUIRED`); one approval unlocking two high-risk actions.
- **Reference:** `src/core/validate.ts`; `docs/design.md` §3.
- **Check yourself:** why is this impossible to check on ordinary workflow code?

## 4. Provenance and sink policies

- **Learn:** tagging values with their sources; sink policies; the prompt-injection example.
- **Build:** provenance tags, propagation through expressions, `noUntrusted` and `onlySources`
  policies, the static check in the validator.
  The three origins and registered labels (decision D12).
- **Negative test:** the injection plan, where an LLM chooses an email recipient, is rejected with
  `SINK_POLICY` (named `INPUT_POLICY` since brief D21); a field declared `trusted:…` is rejected;
  an unregistered label is rejected.
- **Reference:** `src/core/provenance.ts`, `examples/injection-attempt.json`,
  `examples/reply-to-sender.json`; `docs/design.md` §5.
- **Check yourself:** how is this different from a guardrail that judges content?

## 5. The deterministic interpreter, in memory

- **Learn:** running a plan with injected activities and signals; why nothing touches the clock or
  I/O directly; the run history.
- **Build:** the interpreter loop, mock activities, scripted signals, history events, and the runtime
  sink check before each activity.
- **Negative test:** with the static check skipped, the runtime check still blocks the injection,
  and an approval condition the interpreter can't evaluate stops the step instead of skipping the
  approval (fail closed).
- **Reference:** `src/core/interpreter.ts`, `src/mocks/index.ts`; `docs/design.md` §4.
- **Check yourself:** why check sink policies twice?

## 6. Temporal adapter

- **First:** close the side doors in layer 5's ban on the clock, randomness and I/O (found in the
  tutor review of layer 5): `import asyncio` (its event loop has a clock),
  `importlib.import_module("time")` and `__import__("random")` all pass the boundary test today.
  Forbid `asyncio` and `importlib` in `core` and `case`, and the calls `__import__`, `eval`,
  `exec` and `compile` (already non-negotiables in `CLAUDE.md`), each with a negative test. Replay
  is what this layer depends on, so the ban must hold before the workflow runs the interpreter.
- **Learn:** workflows vs activities; signals and queries; replay; `continueAsNew`.
- **Build:** a plan workflow running the same interpreter, activities wired to the catalog with
  the retry policy and timeouts from their contracts and an idempotency key per step run (decision
  D17), a worker and a client, tests against Temporal's test server.
- **Negative test:** a run whose history is replayed with changed code fails replay; a retried
  activity reuses the same idempotency key.
- **Reference:** `src/temporal/workflow.ts`, `activities.ts`, `worker.ts`, `client.ts`.
- **Check yourself:** what lives in workflow history, and why must the interpreter be deterministic?

## 7. People in the loop

- **First:** two small fixes from the tutor review of layer 6. The history's waiting line names the
  entry it waits in (`waiting at approve_refund#1 for approve or reject`), so a refusal naming an
  entry reads clearly beside it, even when one wait leads straight into another. And
  `test_a_run_without_its_answer_reports_waiting` also checks `waiting_at`, the half of its promise
  it doesn't test today.
- **Learn:** waits, signals from people, role checks, approvals by someone other than the proposer;
  task outcomes and their forms (decision D9).
- **Build:** role-based access by risk, approval rules, signal senders with roles; outcomes as the
  signals a wait accepts, each with a form schema whose fields are written to the context (the case
  file, from layer 8), tagged with who answered; the approval defaults (decision D11).
- **Negative test:** a self-approval is refused; an approval from a role without the right risk class
  is refused; an answer with an unknown outcome, a form that fails its schema, or from a role the
  task doesn't allow is refused; a condition reading a misspelled outcome is rejected; a person whose
  answer flows into a step's inputs or condition cannot approve it; an approval lapses when an input
  changes (decision D11).
- **Reference:** `src/core/access.ts`, `src/core/identity.ts` (signed claims: later, optional);
  `docs/design.md` §3a–3b.
- **Check yourself:** in the trusted-caller model, who vouches for identity, and what must the
  deployment lock down (decision D19)? And why must an approval read the value its step actually
  uses?

## 8. Case layer: case file, milestones, steps, admission, closing

- **Learn:** cases without positions; the kinds of step (`activity`, `task`, `plan`, `workflow`;
  decision D13); admission; closing when nothing is left to do, and its overrides (decision D10);
  structured workflows as cases with tight rules (`sequence`); workflow contracts and deployment
  bindings (decision D6); failures that need attention (decision D17).
- **Build:** the case definition schema, the case runtime (open, propose, admit, run, complete, close
  when no work is pending, close by a declared reason), simple parallelism, the `sequence`
  shorthand, in memory first, then as a parent workflow with child workflows on Temporal; `workflow`
  steps that start an existing workflow from its contract and binding, with a contract test on
  Temporal's test server; activity outcomes; the "needs attention" state and its operator actions.
- **Negative test:** a step whose `requires` are not met is refused; a case with an open approval does
  not close; a person closing a case with an undeclared reason or role is refused; a step without a
  business title is rejected; a `workflow` step's output with undeclared provenance cannot reach a
  sink that requires trusted data; a failed step is never skipped without an approved change
  request.
- **Reference:** `src/case/schema.ts`, `src/case/runtime.ts`, `src/temporal/case-workflow.ts`;
  `docs/design.md` §7.
- **Check yourself:** what does "the model picks the step, never the values" mean in code?

## 9. Case data: references, sensitive fields, fresh facts

- **Learn:** what goes in the case file (decision D8): references, decision facts and sensitive
  fields; who sees what; forgetting a person; facts that go stale.
- **Build:** reference fields with a system name and the resolver interface, called on behalf of the
  viewer (decision D16); field visibility by role, filtered on the server; sensitive fields
  encrypted with per-case keys through a key provider and Temporal's payload codec, and `forget` as a
  change request that closes the case first (decision D15); facts with the time obtained, and
  `max_age` refreshing stale facts (decision D18).
- **Negative test:** a `policies` reference passed where a contract expects a `crm` reference is
  rejected; a field hidden from a role is absent from that role's API response; a forget request
  approved by its proposer is refused; history and export contain no sensitive value in plain text;
  a step whose `max_age` fact is stale does not run before the fact is refreshed.
- **Reference:** none in the prototype; `guides/case-data.md`.
- **Check yourself:** after a customer is forgotten, what can the audit still show, and what can't it?

## 10. Case validation: provenance and deadlocks

- **Learn:** provenance flowing through a case file (a fixpoint); structural deadlocks.
- **Build:** case-file provenance computed over all steps; deadlock and never-closable checks.
- **Negative test:** the deadlocked claim (`assess` requiring `paid`) is rejected.
- **Reference:** `src/case/validate.ts`.
- **Check yourself:** why is a fixpoint needed?

## 11. Rules: milestones, events and time

- **Learn:** one rule shape (*when*, *if*, *then*) reacting to milestones, external events, time and
  step starts; untrusted events can't decide; the rework-loop pattern; rule patterns (decision D7).
- **Build:** rules over milestones, declared events with trust levels, step starts and timers; actions
  that reach milestones, start or stop steps and update the case file. Then, on top: the `sla`,
  `reminder` and `four_eyes` patterns, the plain-language renderer, teaching warnings, and
  `ventoux simulate` with story tests (one story test per pattern).
- **Negative test:** a trigger whose condition only untrusted content could satisfy is rejected
  (`UNTRUSTED_TRIGGER`).
- **Reference:** `src/case/events.ts`, `src/case/deadlines.ts`; `docs/design.md` §7 and §10.
- **Research first** (agreed at the end of layer 10, 2026-10-16): a targeted read of Flowable's
  CMMN engine, its code that re-checks sentries and above all its tests, to answer: when is a met
  "on" part forgotten (a step repeated)? What do exit conditions stop, and what of work already
  running? What does each repeated run see? How does an event listener differ from waiting for an
  event (brief, D10's "listening is not waiting")? When does a stage or a case count as complete
  (required items, manual steps only available)? Report what each answer means for Ventoux, say
  which file it came from, and never translate it. Prior art, as the brief lists it; first check
  that this environment's network can reach it.
- **Check yourself:** "arrival is a fact, content is not": give an example.

## Checkpoint (after layer 11, before layer 12): doors left open

Agreed at the start of layer 11, 2026-10-16. Layer 12 publishes the definition format and lets
open cases depend on it, so a concept missing then costs a migration, not an edit. This is one
short note, not a layer.

- **Do:** a table in `docs/layers/checkpoint-doors.md` of what Flowable's CMMN engine offers and
  Ventoux doesn't (stages, or steps that close together; required items; one step per item of a
  list; human waits inside a workflow step; child cases; claiming and reassigning tasks; and any
  other the layer 11 research found). For each: Ventoux's answer (built, planned at layer N, after
  v1.0, or out of scope), and whether any decision so far blocks adding it without breaking
  existing definitions.
- **Done when:** every row that would be blocked is either unblocked before layer 12, or
  recorded in the brief as a deliberate limit.
- **Reference:** `docs/layers/11-research.md`; the brief's "Out of scope" and "Deferred".
- **Drafted after 11a** (2026-10-17), so 11b–11e (as renumbered in 11b's session) can check their
  choices against the table; the checkpoint still closes it before layer 12.

## 12. Releases and changing open cases

- **Learn:** packages and releases (decision D5); behaviour vs presentation; publish, activate,
  migrate; migration that maps names, not positions; change requests; graduating a strict workflow
  to a looser case.
- **Build:** the release tool (behaviour digest, next release number, immutable release record,
  wording-only changes detected); worker manifests and the environment registry; activation per
  environment checking bindings, served contract hashes and live pollers; one change request
  mechanism (propose, approve, apply) used for case-file edits and migrations; preview across a
  cohort; running steps finishing under their old release.
- **Negative test:** a self-approved migration; an unmapped rename that running work depends on;
  activating a release whose activities no worker serves; activation refused when the served
  contract's hash differs; a change outside `display` reported as wording-only.
- **Reference:** `src/case/migrate.ts`, `src/case/requests.ts`, `scripts/migration-demo.ts`;
  `docs/design.md` §8.
- **Check yourself:** why do plans not migrate?

## 13. Semantic diff

- **Learn:** comparing two versions by effect: rules, approvals, provenance, what each will never do.
- **Build:** a diff of plans and case definitions, in developer and plain-language forms, plus
  the generated case map and rules sheet; a CI step that posts them on pull requests and says whether
  the change creates a release; release notes generated from it.
- **Negative test:** a change that loosens a sink policy is reported as such, never hidden.
- **Reference:** `src/authoring/render.ts` (the "will never do" sheet);
  `thoughts/qrspi/2026-10-01-01/`.
- **Check yourself:** what would a reviewer have missed with only the JSON diff?

## 14. Python builder

- **Learn:** code that produces checked data (like AWS CDK); build time vs runtime values; typed
  expressions in Python.
- **Build:** a typed Python builder producing the same JSON, typed runtime expressions, deterministic
  output checked in CI, errors mapped to source lines, and the JSON Schema published from Pydantic.
- **Negative test:** a plain Python value where a runtime expression is required fails the type check;
  regenerated output that differs from the committed JSON fails CI.
- **Reference:** none yet; see the deferred questions in `thoughts/qrspi/2026-10-01-01/task.md`.
- **Check yourself:** why must the builder never run on model output?

## 15. AI authoring and the step advisor

- **Learn:** a model drafting plans, validated and repaired; a step advisor that only names steps.
- **Build:** the authoring loop (draft, validate, feed errors back), `render` for approvers, and the
  step advisor.
- **Negative test:** a step advisor answer naming an inadmissible step is refused; a drafted plan
  with an unsafe data flow is rejected and repaired or abandoned.
- **Reference:** `src/authoring/loop.ts`, `prompt.ts`, `render.ts`, `case-planner.ts`;
  `docs/design.md` §6.
- **Check yourself:** what can an injected instruction still influence, and what can't it?

---

## 16. More field types: dates, options, attachments

- **Learn:** a field type is a check as much as a shape; a date is a value, not a clock (comparing
  two dates is pure, asking what day it is isn't); an answer checked against a system at the moment
  it is given; a document kept as a reference, never its bytes in the history.
- **Build:** the date first: a `date` field, stored as a calendar date, compared and shown, with no
  expression reading today (D20 stays free of the clock). Then an option from a registered system's
  list, checked through an activity when the answer is given; and a file attachment, a reference
  to a registered document store. Each in the definition format, the JSON Schema, the builder, the
  diff and the plain forms.
- **Negative test:** an expression comparing a date with a number is refused before anything runs;
  an option the system's list doesn't hold is refused, and the refusal recorded; an attachment that
  names no registered store is refused.
- **Reference:** none in the prototype. Timers anchored to a date build on this later (the README
  draft's "Beyond v1.0").
- **Check yourself:** why may an expression compare two dates but never ask what day it is?

## 17. Task assignment

- **Learn:** who may answer a task (its role) and who is asked to (its assignee); a role's queue;
  claiming, assigning and reassigning as events in the case's history; assignment by rule, written
  in the definition and checked like any other rule.
- **Build:** claiming a task from its role's queue, and giving it back; assigning and reassigning
  it, by a person whose role allows it; the case report showing who holds each task; assignment
  rules in the definition, shown in the diff and the plain forms.
- **Negative test:** a claim by someone without the task's role is refused; a reassignment by
  someone not allowed to assign is refused; an assignment rule that can only pick people who can't
  answer the task is refused at validation.
- **Reference:** `src/case/worklist.ts` (an assignee keeps a task off other people's worklists).
- **Check yourself:** is an assignment a permission? What changes for the person assigned, and
  what doesn't?

## 18. Case lifecycle: required steps, repeated steps, child cases

- **Learn:** required work, and what "nothing left to do" means then; a step run once per item of
  a list; a child case, with its own file, release and lifecycle, and how its parent hears that it
  ended.
- **Build:** required steps, without which the case can't close, and validation that each can
  still be done; one step per item of a list field, each run given its item; child cases started
  from a step, reporting their end to the parent by a signal (the checkpoint's note carried for
  D27 and D48).
- **Negative test:** a required step that no rule or person can ever start is refused at
  validation; a step repeated over a field that isn't a list is refused; a child case of a
  definition not active in the environment is refused before it starts.
- **Reference:** `src/temporal/case-workflow.ts` (fragments run as child workflows, signalled only
  once started).
- **Check yourself:** what can a child case never do to its parent, and why?

## 19. Audit export and a production key provider

- **Learn:** an audit trail kept apart from Temporal's history, with its own retention; why
  sensitive values leave encrypted and stay so (D15); keys held by the platform's key service,
  never by Ventoux.
- **Build:** the audit export, an append-only copy of case and run events, sensitive values as
  ciphertext; a key provider for Vault or a cloud KMS, behind the existing `KeyProvider`.
- **Negative test:** an exported event holding a sensitive value in clear text fails the export; a
  key the provider can't give is an error that says so, never an empty value.
- **Reference:** none in the prototype.
- **Check yourself:** once a case is forgotten, what does its audit export still say, and what can
  no one read?

## 20. Deployment and the published package

- **Learn:** what a deployment must lock down (D19, the trusted caller); checking a deployment
  rather than only describing it; a conformance suite as the contract any other implementation
  meets.
- **Build:** the deployment guide; `ventoux doctor`, checking what it can of a deployment; the
  conformance suite (definitions with their expected validation results), published with the JSON
  Schema; the published package.
- **Negative test:** `ventoux doctor` fails on a deployment that breaks a rule it checks, naming the
  rule; a change to validation that alters a conformance result fails CI.
- **Reference:** none in the prototype.
- **Check yourself:** which of a deployment's promises can `ventoux doctor` check, and which can
  only the guide state?

## 21. The AgentDojo benchmark

- **Learn:** measuring security and utility together; what a prompt-injection benchmark measures,
  and what it can't.
- **Build:** AgentDojo's suites run through Ventoux (plans drafted, checked and run), with security
  and utility results published and reproducible.
- **Negative test:** an injected task that would send data to an attacker's sink is refused before
  any activity is scheduled.
- **Reference:** none in the prototype; [AgentDojo](https://github.com/ethz-spylab/agentdojo).
- **Check yourself:** what would a perfect security score with a low utility score tell you?

---

After layer 21, v1.0 is built. What comes after it is listed under "Beyond v1.0" in
`docs/README-draft.md`.
