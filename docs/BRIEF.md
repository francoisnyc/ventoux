# Ventoux — design brief

Status: draft, 2026-10-09; decisions D1–D26 (D3 superseded by D20). Read this
first; it is the short version of what we are building and why. The longer reference is
`docs/design.md` in the `chartering` prototype.

## In one sentence

Ventoux adds case management and human-in-the-loop workflows to your existing Temporal server, with
definitions that are data: reviewed in pull requests, checked before they run, changeable for open
cases, and safe for an AI to draft.

## Why it exists

- **Teams on Temporal build human work by hand.** Temporal gives durable execution and signals, but
  no cases, no worklists, no approval rules, no way to change the rules of open work. Teams write
  this themselves, or run a second engine (Camunda, Flowable) next to Temporal.
- **BPM platforms lose developers.** A separate studio, its own app model and process files nobody
  can review (an earlier tool failed at the author's company for these reasons).
- **AI is entering this work.** Models draft workflows and propose next steps. For critical tasks
  (costly, irreversible or regulated actions), a model's mistake or an injected instruction must not
  turn into an action.

## Who it is for, and not for

- **For:** developers on teams that already run Temporal and have long-running work with people in
  the loop: claims, onboarding and KYC, access requests, incident and change management. And the
  analysts and business owners who work with those developers.
- **Not for:** teams that want analysts to draw and edit processes in a visual tool, or a ready-made
  UI product. Camunda, Flowable or Pega fit those better.

## Where it runs

On the Temporal server the team already operates (self-hosted or Temporal Cloud), not as a second
platform beside it, unlike Camunda or Flowable, which bring their own engine, database and studio:

- **Cases are Temporal workflows** in your namespace: their history is Temporal history, with no
  new engine and no new database.
- **The Ventoux engine is a Python library** inside a worker you deploy like any other.
- **Your activities and workflows stay where they are** (Python or Java workers); cases call them.
- **Operations are Temporal's:** the same UI, metrics, alerting and access control.
- **What Ventoux adds:** one small API service with a reference inbox (the only way into the engine),
  resolvers to show records from your systems, and a key provider (such as Vault or a cloud KMS)
  for sensitive fields.

## Design principles

Every decision is checked against these five.

1. **Change.** Workflows evolve easily and safely, including work already running.
2. **Engineering practice.** Definitions live in git, are typed, tested, reviewed and deployed
   through CI, as Temporal workflows are.
3. **AI-friendly.** An AI understands definitions well enough to go quickly from idea to product,
   and to monitor and change them over time.
4. **Intuitive and shared.** Developers, analysts and users understand and discuss the same workflow,
   each in their own terms.
5. **Easy to adopt.** A developer runs a first case in 15 minutes, meeting at most five concepts.
   Documentation comes first: if something is hard to explain in the docs, the design changes, not
   the docs.

## Personas and the concepts they meet

| Persona | What they do | Concepts they meet |
|---|---|---|
| **Workflow developer** (most users) | Writes cases and tests them | case, case file, step, approval, rule; validator errors when something is unsafe |
| **Platform team** (a few people) | Registers activities, workflows and resolvers, sets policies, runs releases and operations | contract (with retry policy and idempotency), deployment binding, risk, input policy, source labels, resolver, key provider, release, activation, needs attention |
| **Analyst / business owner** | Reads, proposes and approves changes | case map, rules sheet, plain-language diff |

**Progressive disclosure.** Advanced concepts have defaults, so people meet them only when needed:
- locally and in staging, releasing and activating are automatic; in production they are
  deliberate;
- one folder is one package;
- the catalog ships with example activities and sensible policies;
- identity is the trusted-caller model, with the engine reachable only through the Ventoux API (D19);
- provenance and sink policies are set by the platform team on each activity; developers meet
  them only through validator errors, and every error says what was wrong, why, and what to do
  instead.

The quickstart (`QUICKSTART.md`) is the running test of this principle.

## Six ideas the whole design rests on

1. **Definitions are data.** Plans and case definitions are JSON. Nothing in them is ever executed
   as code: no `eval`, no imports. Because they are data, they can be validated, rendered for people,
   compared between versions, migrated, and written by an AI.
2. **Capabilities live in a catalog.** Definitions *reference* activities (`claims.pay@1`); they
   never define them. Activities are ordinary code, registered with a contract: input and output
   schemas, a risk class, and policies on their inputs.
3. **Every value carries its provenance.** Values are tagged with where they came from (a system, a
   person's answer, or an untrusted source such as `untrusted:llm`; D12). Sink policies on activity
   inputs say which sources may reach them. This is checked on the definition before it runs, and
   again before each activity is scheduled.
4. **Cases have no position.** A case is a case file, milestones and rules for what may happen next.
   Nothing stores "where the case is", so open cases can move to new rules without mapping positions.
5. **People decide what matters.** Approvals by a second person, work routed to roles, change
   requests reviewed before they apply, deadlines that escalate. The engine enforces these.
6. **AI proposes, the engine decides.** A model may draft a definition or propose the next step. It
   never picks the values a critical action runs with, and its output at runtime is untrusted data.

## Decisions

### D1. JSON is the foundation; a Python builder is the front door

- **JSON is the contract.** The validator, semantic diff, runtime, business views and runtime AI all
  work on JSON.
- **Developers write Python** with a typed builder that produces the JSON (a Java builder may follow).
  The builder is one-to-one with the JSON, its output is deterministic, and CI fails if the committed
  JSON differs from what the code generates. The builder comes after the core (curriculum layer 14).
- **Two kinds of AI.** AI at design time (a coding assistant) writes builder code, reviewed in pull
  requests like any code. AI at runtime (step advisor, author) only produces JSON, which is untrusted,
  validated and never executed. A runtime draft that should be kept becomes a reviewed pull request.
- **Business views are first-class outputs,** generated from the JSON: a case map, a rules sheet and
  a plain-language semantic diff. Definitions carry business titles and descriptions for steps,
  milestones and fields; the validator requires them.
- **Collaboration model:** visual for reading, language for proposing, code for authoring, people
  for approving. Analysts propose changes in plain words; an AI drafts them as a pull request; the
  analyst approves the meaning (the plain-language diff), a developer approves the code. There is no
  visual editor; a read-only case map with comments is the compromise.

### D2. One model from structured workflows to case management

- A structured workflow is a case with tight rules: each step requires the previous one and starts
  automatically. Loosening it means relaxing rules (manual steps, optional steps, new rules), with
  the same format, engine, diff and tests. Open cases can migrate from the strict to the loose
  version because cases have no position.
- A `sequence` shorthand expands into those rules; the expansion is visible in the diff and views.
- Rework loops ("send back for correction") use repeatable steps whose `outcome` is the latest answer
  (D9), since milestones are never undone. This pattern gets a documented example.
- Simple parallelism (independent steps running at the same time) is in v1; advanced join rules are
  not.
- Strict cases are drawn as a flowchart derived from their rules; loose cases as a board of
  available steps.
- Short sequences without people stay inside a plan. Anything that waits on people or runs for
  days is a case step, where it can change.

### D3. Expressions are a small JSONata subset (superseded by D20)

> **Superseded on 2026-10-04 by D20** (structured JSON), after the spike
> (`docs/layers/spike-dsl.md`): JSONata reads a missing field as nothing, so an approval condition
> on a missing amount meant "no approval needed". Kept as written, so references to D3 and the
> history stay true.


- Allowed: field paths, literals, comparisons, `and`/`or`/`not`, arithmetic, conditionals, simple
  array filters, and a short list of functions (`$exists`, `$count`, `$sum`, `$contains`,
  `$string`, `$number`, …). The JSONata engine evaluates them; the validator rejects anything else.
- Not allowed: user-defined functions, `$map`/`$reduce` and other higher-order functions, regular
  expressions, variable bindings, and anything non-deterministic.
- Logic that doesn't fit becomes a registered activity with `effect: compute`: real code, tested
  and reviewed.
- Typed builder expressions (`file.payout > 1000` written with typed field objects) compile to this
  subset.
- CEL (Common Expression Language) is compared on the same examples in the curriculum's spike.

### D4. The engine is written in Python

- Why: the team that will use and maintain Ventoux works mostly in Python (and Java). The people who
  live with the engine must be able to read, debug and extend it.
- Stack: Python 3.12+, Pydantic for schemas, pytest, strict type checking (pyright or mypy strict),
  and the Temporal Python SDK (its workflow sandbox helps catch non-determinism). Expressions need
  no library: their evaluator is a small part of `core` (D20).
- No lock-in to the engine language: the definition format is published as **JSON Schema**
  (generated from Pydantic), and a **conformance suite** (definitions, expected validation results
  and run histories) checks any implementation, including the TypeScript prototype.
- Activities stay polyglot: Python or Java workers, connected through Temporal task queues.
- Browser front ends (an inbox, business views) stay separate, in TypeScript, and use the JSON Schema
  and an API.

### D5. Versions and releases

- **Contracts** (activities, and workflows per D6) keep explicit versions (`name@N`). Contracts are
  immutable: any change to one, breaking or not, needs a new number. CI hashes each contract
  (schemas, risk, policies, output provenance) and fails if it changed without a new number.
  Whether a change is breaking only decides how much work packages need to adopt it.
- **Implementation changes** (code inside an activity or workflow) need no new contract version and
  no release; workflow code relies on Temporal's worker versioning for running executions.
- **Contract versions live side by side.** A package adopts a new contract version by referencing
  it, which creates a release. An old contract version stays served while any active release or
  open case uses it; tooling reports what still depends on it, and it can then be retired.
- **What vs where.** A contract says what is promised; a deployment binding per environment says
  where it runs (workflow type or activity name, task queue, namespace). Moving where something runs
  is an operations change, not a contract change. Activation checks the bindings.
- **Definitions are released as packages.** A case definition and the plans it uses form one
  package, released together. References inside a package carry no versions; a shared plan
  library is its own package, referenced by release.
- **Releases are assigned by tooling.** On merge, CI gives the package its next release number and a
  content digest, and writes an immutable release record (package, number, digest, commit, required
  activity contracts, release notes). Nobody bumps definition versions by hand.
- **Behaviour vs presentation.** Everything that changes what the engine can do or decide is
  behaviour; titles, descriptions, help text and approval reasons are presentation, kept in explicit
  `display` blocks. The release digest covers everything outside `display`. A presentation change
  is reviewed in a pull request but creates no release, and applies to running cases at once; the
  audit log records which wording a person saw. Literal values passed to activities are behaviour.
- **Publish, activate, migrate are separate moves.** Publishing creates an immutable release and
  changes nothing in production. Activating a release in an environment makes new cases start on
  it; it is refused unless that environment's workers serve every activity contract the release
  needs, and rolling back means activating the previous release. Migrating open cases is a change
  request, previewed and approved by a second person; cases not migrated finish on their release.
- **How the activation check works.** Temporal knows which workers poll a task queue, but not which
  activity or workflow types they serve, so Ventoux fills the gap: (1) at startup, each worker
  built with Ventoux's library publishes a **worker manifest** (environment, task queue, build, and
  every contract it serves with its contract hash); (2) manifests are kept in an **environment
  registry**, itself a long-running Temporal workflow per environment; (3) `ventoux activate` checks,
  for each contract in the release record, the binding (which task queue), that a manifest there
  serves it **with the same hash**, and that workers are polling that queue now. Failures are
  refused with an explanation. This is a check at activation time, so a second layer runs
  continuously: schedule-to-start timeouts make an activity nobody picks up fail loudly, and
  monitoring alerts when a contract an active release needs has no live worker.
- **Retirement.** A release with no open cases can be retired: it can no longer start cases, and it
  is kept forever for audit and replay.
- **Drafts.** Unreleased definitions run in tests and the development inbox, never in production.
- **Release notes** are the semantic diff between releases, with wording changes listed separately.

### D6. Existing Temporal workflows as steps

- A fourth kind of step, `workflow`, runs an existing Temporal workflow (in any SDK language) as a
  child workflow of the case.
- It is described by a **workflow contract** in the catalog: name and version, input and output
  schemas, risk class and effect, sink policies on inputs, the provenance of each output, and
  whether it can be cancelled. Its deployment binding gives the workflow type and task queue.
- The engine checks admission, approvals, risk and sink policies before starting it, and tags its
  result with the declared provenance. **Undeclared output provenance is untrusted** (fail safe).
- **Automated only in v1:** a workflow step must not wait for people. Human work is a `task` step
  before or after it, so it shows in worklists and is routed and audited. Declared human waits may
  come later.
- The contract is a promise, not a proof: it is reviewed like code, shown in the semantic diff, and
  checked by contract tests that run the workflow on Temporal's test server against its schemas.
  Changes of meaning inside the code are the owning team's responsibility to publish as a new
  contract version.
- Choosing between a `workflow` step and the other kinds: see D13.
- Later: workflows owned by other teams or namespaces through Temporal Nexus, building on the same
  contracts.

### D7. Rules are written through patterns, explained back in plain language

- Raw *when / if / then* rules are the engine's concept, not the first one people meet. The builder
  offers named **patterns** for the common shapes (`sequence`, `sla`, `reminder`, `four_eyes`, and
  others found in real cases), each expanding into rules that stay visible in `ventoux check`, the
  case map and the diff. Raw rules remain available for unusual cases.
- Patterns encode the tricky parts once. `sla` measures from the step's **latest start**: the clock
  restarts when the step restarts, is cancelled when the step completes, and fires once per attempt
  (`since=first_start` is available, explicitly).
- **Plain-language rendering** of every rule and pattern ("Escalate to a senior adjuster if the
  assessment isn't finished within 5 days of its latest start").
- **Teaching warnings** for known traps: timers anchored on the first start of a repeatable step,
  rules that can never fire, rules whose condition reads untrusted data.
- **`ventoux simulate`** replays a story on a timeline ("Mon: assess starts; Wed: assessed; Thu:
  assess restarts") and shows when each rule fires. Stories are also tests, with simulated time.
- Steps emit a **started** event, so rules and timers can anchor on it. In the Python builder,
  conditions use `unless=` / `only_if=`, since `if` is reserved.

### D8. Ventoux is not a system of record

1. **Business records stay in your systems.** Customers, policies, orders and documents live in
   their systems of record; the case file holds **references** to them (`policy_id`,
   `document_ids`).
2. **The case file holds decision facts:** the typed values rules, approvals and steps use
   (`estimated_damage`, `decision`, `payout`), each with its provenance and when it was obtained.
3. **Fetch close to use.** Data needed by a single step (an address for a letter) is fetched by
   that step's activity from the system of record, not copied into the case file.
4. **Sensitive fields are declared.** They are kept out of plain workflow history: encrypted with a
   per-case key that is destroyed when a person asks to be forgotten (D15).
   The validator warns about free-text and very large fields.
5. **Reporting uses an export** (the audit and read-model export), never queries against running
   cases.

Why: Temporal history is append-only and kept for its retention period (personal data in it can't
be erased on request), has size limits, and a second copy of business records goes stale.

### D9. Tasks answer with named outcomes and typed fields

- A **task** asks a person a question; its **outcomes** are the closed list of answers
  (`approve`, `reject`). Conditions read them: `review.outcome == "approve"`. For a repeatable task,
  `outcome` is the latest answer; history keeps every answer, who gave it and when.
- An outcome may **set declared case-file fields** through a small form (`Outcome("Approve",
  sets=[approved_amount])`). The values land in the case file, never in task-local data, so rules
  still only read the case file (D8). The inbox draws the form from the fields' types.
- A person's answer is **trusted**, tagged with who answered and their role. This is how an
  untrusted value becomes usable: a named person confirms it, and the audit shows who.
- Only the task's `roles` may answer; the engine re-checks the role and validates the form.
- The validator rejects unknown outcome names, and warns about conditions on a task that may not
  have answered yet and about outcomes no rule reads.
- **An approval guards the values its step actually uses.** Its condition should read the step's
  inputs (or the fields passed to them), not a neighbouring field: an approval on the requested
  amount while the reviewer's approved amount is what gets paid guards the wrong value. The
  validator warns when an approval's condition reads none of the fields its step uses.
- Replaces untyped signal payloads (the prototype's `wait: {signals}` plus `update` expressions):
  in a task, outcomes are the signals and their forms are the payload schemas.

### D10. A case closes when nothing is left to do

- **Pending work** is what keeps a case open: a running step, an open task or approval, a timer that
  is set, or a step explicitly waiting for an event. A case with no pending work closes by itself,
  recording why (the milestones and outcomes it ended on). This is CMMN's *auto-complete*, as the
  default. No new term: the case map says "closes when nothing is left to do: after the payment, or
  after a rejected review".
- **Listening is not waiting.** A rule that reacts to an outside event ("customer cancels") does not
  keep the case open; only a step or rule explicitly waiting for the event does. Otherwise a case
  that listens for anything would never close.
- **Timers count.** A rule that fires 30 days after payment keeps the case open 30 days, and the case
  map says so. Patterns cancel their own timers (an `sla` stops when its step completes).
- **Overrides:** `closes_when=<milestones>` closes the case as soon as they are reached, cancelling
  any pending work (recorded in history); `stays_open=True` means only a person or a rule closes it.
- **Closing by a person** is declared, like a task outcome: `refund.close_reason("duplicate",
  "Duplicate request", roles=["support"])`. Open tasks and approvals are cancelled, and the people
  they were assigned to see why ("closed as duplicate by Ana"). Undeclared reasons and roles are
  refused.
- **Running activities finish; nothing new starts.** A side effect can't be safely cut off halfway
  (a payment call may already have moved money), so a close, by a person or by `closes_when`, puts
  the case in **closing**: tasks, approvals and timers are cancelled, no step starts, running
  activities complete and their results are recorded, then the case is **closed**. Before
  confirming, the person sees what is still running ("a refund of 250 is in progress; closing won't
  stop it"). If something completed while closing, the closed case is flagged ("pay completed after
  the close was requested") so a person can decide on a reversal; automatic compensation (sagas)
  comes later.
- The validator warns about cases that can never close (a step that can always be restarted, a
  timer that re-arms itself) and about `closes_when` milestones that can't be reached.

### D11. Approval defaults

- **Roles are on the approval** (`Approval(when=…, roles=["support-lead"])`), and an approval is a
  task with two outcomes, *approve* and *reject*, shown in the inbox like any task; rules can read
  it (`pay.approval == "reject"`).
- **"Someone else" is computed from provenance.** Excluded from approving a step: every person whose
  answer flows into the step's inputs or into its run condition (`when=`), and the person who opened
  the case. Nobody lists them by hand; the inbox explains an exclusion ("you set approved_amount").
  Editing a field the step doesn't use excludes no one.
- **An approval is tied to the values it saw.** It records a digest of the step's inputs; if any of
  them changes before the step runs (by a change request, or a task answered again), the approval
  lapses and a new one is needed, whether the value went up or down. One approval unlocks one run
  of one step.
- **Several approvers** use `count=2` (distinct people, each excluded by the rule above), which the
  `four_eyes` pattern (D7) expands to.
- The validator rejects an approval without roles on a high-risk step. Whether anyone eligible
  exists is a staffing fact, not something the validator can know: at runtime, an approval nobody
  eligible can take is shown as blocked, with the reason.

### D12. A small vocabulary of sources

- Three origins, each with one owner: **system** (the system that opened the case, or an activity's
  output, declared per output field in its contract by the platform team), **person** (a task or
  approval answer, tagged by the engine with who answered), and **untrusted:*label*** (declared by
  the developer on a field).
- Labels (`customer`, `llm`, `document`, `email`, `web`, …) are registered by the platform team, like
  roles, so a typo is caught by `ventoux check`. They explain where a value came from; trust is the
  part policies check.
- **A developer can declare a field untrusted, never trusted.** `source="trusted:…"` on a field is
  rejected. A value becomes trusted only through a contract the platform team owns, or a person's
  answer.
- **Provenance follows the content, not the system that carries it.** A company portal is a system,
  but an amount a customer typed into it is `untrusted:customer`, declared so in the portal
  activity's contract (see D6 and learning question 13).
- Sink policies mostly ask one question, trusted or not (`no_untrusted`); requiring specific origins
  (`only_from=["payments"]`) is the advanced form.

### D13. Plans are an advanced concept

- **Build order is not learning order.** Plans come first in the curriculum (the interpreter,
  provenance and validation rest on them) but late in the docs: the quickstart and first guides use
  tasks and activities only, and `ventoux init` generates no plan.
- **Which kind of step:** `activity` for one call to a system; `task` for one question to a person;
  `workflow` when a team already has the logic as Temporal code; `plan` when several calls and
  waits belong together as one step *and* must be data, because an AI drafts it or because the diff
  and approval sheet must say what it will never do. When the business wants to see and change each
  part, use separate case steps instead.
- Plans get their own guide ("Multi-step steps and AI-drafted plans"); the rule of thumb above
  appears in the case-map docs.
- In v1.0, plans are registered and released like any definition (D5); a model may choose among
  them. A model drafting a new one for a single case at runtime is the deferred "ad hoc inline
  plan".

### D14. "Charter" is renamed "plan"

- The step kind is `plan` (`claim.plan("collect_evidence", "evidence.collect@2")`), and approvers see
  "Approve this plan". The word is plain for analysts, honest (a plan of steps, as data, checked
  before it runs), and reads naturally in the core sentence: "the AI proposes a plan, the adjuster
  approves it". "Charter" was borrowed from Agentic Chartering, which stays credited in prior art.
- "Agent" describes where a plan came from, not what it is: most plans are written by developers, and
  an agent only proposes; the engine runs the plan and a person approves it. A plan's provenance
  records who drafted it ("drafted by the claims agent"). The pitch: **Agents propose plans.
  Ventoux checks them. People approve.**
- To avoid a clash, the AI that suggests a case's next step is the **step advisor**, not a planner.
- The `chartering` prototype keeps its names (Charter, fragment, planner).

### D15. Forgetting a person: per-case keys

- Sensitive fields are encrypted with a **key per case**, kept outside Temporal, through Temporal's
  payload codec (outside workflow code, so the engine stays deterministic). Sensitive values travel
  in their own payloads, so the rest of the history stays readable.
- Keys come from a small **key provider** interface (create, use, destroy) with a development
  provider (a local file) and one production adapter (HashiCorp Vault or AWS KMS) in v1.0. Rejected:
  "sensitive by reference only" (rules couldn't read the value) and one key per environment
  (destroying it forgets everyone).
- **Forgetting is a change request** (proposed, then approved by someone else, typically a data
  protection role), because erasure can conflict with legal retention and is a business decision.
- **An open case is closed first.** Replaying an open case's history needs its key, so destroying
  it mid-case would break the case. Once approved, `forget` closes the case with the reason
  "forgotten" (D10: tasks cancelled, running activities finish), then destroys the key and records
  that it did.
- **Every copy stays encrypted.** The audit export carries sensitive values as ciphertext under the
  same case key (or omits them), so destroying the key makes the warehouse copy unreadable too.
  Reports that need such a value decrypt it through the key provider while the key exists.
- The audit trail keeps every decision, who made it, the rule and the release; only the values go.

### D16. References are typed; resolvers show what they point to

- A **reference** is its own field type with a system name (`claim.reference("customer_id",
  system="crm")`). Contracts can require a reference to a given system, so `ventoux check` refuses a
  policy ID where a customer ID is expected; the diff reports which systems a case points to.
- A **resolver**, registered by the platform team per system, turns a reference into what a person
  may see in the inbox. It is not an activity: it is read-only, runs in the inbox (outside the
  workflow), and nothing it returns enters the case file or the history. Like activities, it is
  registered, never defined in a case.
- **Whoever holds the data decides who sees it.** The resolver calls its system on behalf of the
  viewer (their identity and roles), so the system of record's own permissions apply; Ventoux may
  hide more, never show more. Sensitive fields in the case file are Ventoux's to guard (D15, roles).
- **Case-file fields are Ventoux's to show, by role.** A field may say `visible_to=[roles]`; ordinary
  fields are visible to anyone with a role on the case, sensitive ones only to the listed roles. The
  case view, task forms, approval sheets and the API filter on the server, and say when something is
  hidden ("Date of birth: hidden (needs claims-sensitive)"). Hiding is not protection against the
  Temporal UI, which shows history to anyone with namespace access: only encryption (D15) is, which
  is why sensitive fields are encrypted, not just hidden.
- **Approvers must see what they approve.** The validator warns when an approval's roles can't see a
  field its step uses or its condition reads (D11).
- The history records that a record was shown (system, reference, viewer, time), not its content.
  If a value matters to a decision, it must become a fact: fetched by a step, or confirmed in a task
  answer (D9).

### D17. Failures: retry, answer, or ask for attention

- **Systems down: Temporal retries.** The retry policy and timeouts are part of the activity's
  contract, set by the platform team, who know the system's limits; a case may make them stricter,
  never looser. The case waits and the inbox shows why ("retrying, attempt 4"). Rules keep running,
  so an `sla` still escalates during a long outage.
- **Side effects are idempotent.** Every activity whose effect is not read-only declares how: it
  sends a key built from the case, the step and the step's run (never Temporal's attempt number).
  The catalog refuses a side-effecting contract without one. An adapter that receives "duplicate
  request" returns the original result (the existing payment's ID), so the case records the real
  payment.
- **Business failures are outcomes.** Declined, account closed: the contract declares them as
  outcomes of the activity, read like task outcomes (`pay.outcome == "declined"`, D9). The validator
  warns about declared outcomes no rule handles.
- **Unexpected failures need attention.** After its retries, a failed step puts the case in **needs
  attention**, in a queue for an operations role, with the error. The failed step is pending work
  (D10), so the case doesn't close. An operator retries the step (after a fix is deployed), closes
  the case, or files a change request (to skip the step, approved by someone else). **Nothing is
  ever skipped automatically.**
- **Engine and definition bugs block, they don't lose.** A failing workflow task keeps its state and
  resumes once fixed code is deployed; runtime expression errors become "needs attention"; replay
  tests in CI catch changes that would break running cases.

### D18. Facts know when they were obtained; steps can require fresh ones

- Every fact records **when it was obtained**, from workflow time (deterministic on replay), and,
  when the contract declares it, the source's own **as-of** time (a score as of last month).
- A step may require facts to be fresh where it uses them: `max_age={"policy_status": days(1)}`,
  covering its inputs, its condition and its approval. Freshness belongs at the use, not the field:
  a week-old status is fine for a letter, not for a payment.
- **A stale fact is refreshed, not trusted.** Provenance records which step obtained it; if that step
  is read-only, the engine runs it again before the step that needs the fact, then re-checks the
  condition (a cancelled policy now stops the payment). If the fact came from a person or from a
  step with side effects, the case needs attention (D17) instead.
- **People see the age where it matters:** the case view shows when each fact was obtained, and an
  approval sheet shows the age of every fact the approval depends on ("policy status: active,
  obtained 3 weeks ago"), so the approver can act before, and the audit can explain after.

### D19. Who may talk to the engine; signed approvals later

- **v1.0 is the trusted caller, locked down.** The engine believes the identity the caller states, so
  only the Ventoux API may start cases or send signals: production deployments use mTLS and
  Temporal's authorization so that only the API's service identity can write; people get read-only
  access to Temporal. The deployment guide says so, and `ventoux doctor` checks what it can.
- **Admin access stays powerful, so it stays small and audited.** Whoever can terminate, reset or
  deploy workers can stop cases, re-run history from an earlier point, or ship different code;
  signatures can't prevent that. Resets in particular must be restricted, since re-running a
  payment step creates a new step run (and a new idempotency key, D17).
- **After v1.0, signed approvals are the production default for high-risk steps** (optional
  elsewhere). The signature binds the approver, the case, the step, the digest of the inputs (D11)
  and an expiry, so it can't be forged by someone with signal access, or replayed on another case,
  step or amount. Verifying it is a pure calculation, safe inside the workflow.

### D20. Expressions are structured JSON with a fixed list of operators (supersedes D3)

- **Stored as structured JSON:** a literal, a field (`{"var": "approved_amount"}`), or one operator
  with its arguments (`{">": [{"var": "approved_amount"}, 100]}`). No parser: Pydantic validates the
  shape, the fields an expression reads are explicit (provenance, D12), it diffs exactly and hashes
  canonically (D5), and the published JSON Schema constrains what a model can write (layer 15).
- **Written** through the Python builder (`approved_amount > 100` with typed field objects) or, at
  runtime, by a model under the JSON Schema. **Read** as a one-line rendering (`approved_amount >
  100`) in diffs and reviews, and in plain language by analysts. No text syntax is parsed in v1.
- **The operators:** `var` (a declared field) and literals; `==`, `!=`, `>`, `>=`, `<`, `<=`; `and`,
  `or`, `!`; `+`, `-`, `*`, `/`; `if` (condition, then, else); `in` (membership in a list); `cat`
  and `string`; `exists`; `count`; `sum` over a list field with a simple `where`, reading each
  element with `item`.
- **Names follow JsonLogic where ours are only stricter.** An operator takes JsonLogic's name when,
  whenever ours returns a value, JsonLogic returns the same one: ours may only refuse more. Refused:
  a default in `var`, `var` of the whole data, `if` chains, truthiness (conditions are `true` or
  `false`), coercion in `==` and `cat`. Where the shape or meaning differs, the name is ours (`sum`,
  `count`, `exists`, `string`, `item`), so nobody assumes JsonLogic's behaviour.
- **Typed, and fail closed.** Checked before running against the declared field types, with one
  `number` type and outcomes as closed lists, so a misspelled outcome (`"aprove"`) is rejected. At
  runtime a missing field, a wrong type or an unknown operator is an error, never `false`; `and` and
  `or` evaluate every operand, so an error is never hidden. Why: JSONata, the earlier choice, reads
  a missing field as nothing, and the prototype's `holds()` turned that into `false`, so an approval
  condition on a missing amount meant "no approval needed".
- **Numbers are exact decimals, never binary floats.** JSON numbers are read as decimals, and both
  evaluators use exact decimal arithmetic, so `0.1 + 0.2 == 0.3` holds and money agrees with the
  contracts (`payments.refund@1` takes a `Decimal`). A division that doesn't terminate (`1 / 3`)
  keeps 34 significant digits, rounding half to even (IEEE 754 decimal128), set explicitly in both
  evaluators, never taken from a global default. Division by zero is an error. Rounding is not an
  operator: a `compute` activity does it, with an explicit scale and mode.
- **Deterministic by construction.** No operator reads the clock, randomness or I/O, and there are
  no user-defined or higher-order functions, variable bindings or regular expressions. They can't be
  written, so there is nothing to refuse.
- **The list is fixed here.** Adding an operator is a design decision recorded in this brief, with
  its reason, not a code change. Logic that doesn't fit becomes a registered activity with
  `effect: compute`: real code, tested and reviewed. The TypeScript evaluator (for the inbox) passes
  the same conformance suite as the Python one (D4), so the two can't drift.
- Compared in the spike (`docs/layers/spike-dsl.md`) with the JSONata subset, CEL and JsonLogic.
- *Added 2026-10-04 (tutor session):* the one-line rendering uses **FEEL-style** syntax, the
  expression language of DMN and Camunda 8, because business readers and Camunda users know it:
  `review.outcome = "approve" and approved_amount > 100`, with `=` and `!=`, `and`, `or`,
  `not(...)`. Display only: the text is never parsed back, so none of FEEL's runtime behaviour
  (a failure returns `null`, `now()`) comes with it.

### D21. Input policies: their name, their kinds, and where they are written

*Decided 2026-10-07, in layer 4 (design question 10).*

- **"Input policy" is the name** in every message, guide and error code (`INPUT_POLICY`). "Sink
  policy", the taint-analysis term, is mentioned once in the activities guide for readers who know
  the security literature. Earlier text (D5, D6, D12, the non-negotiables) keeps the word it was
  written with; both mean the same rule.
- **Written on the input field it guards,** in the activity's input model:
  `amount: Annotated[Decimal, trusted_only()]`. A policy sits next to the field, so no field name
  is spelled twice, and it is part of the input's JSON Schema, which the contract hash already
  covers (D5): adding a policy is a new contract version.
- **Two kinds, a closed list fixed by the engine:** `trusted_only()` (no `untrusted:` source; D12
  called it `no_untrusted`) and `only_from("payments", …)` (every source is one of the systems
  named). Every policy on an input applies. Adding a kind is a design decision recorded here, with
  its reason, like an expression operator (D20): the static check, the runtime check, the
  plain-language sentence, the semantic diff ("stricter or looser?") and the TypeScript evaluator
  must all understand it. A kind the engine doesn't know is refused, never ignored.
- **Read as one sentence,** the same in validator errors, approval sheets and diffs: "takes
  `to_customer` only from a system or a person, never from untrusted data"; "takes `account` only
  from payments". Developers never write a policy; they meet that sentence.

### D22. Roles come with each answer, from the trusted caller

*Decided 2026-10-08, in layer 7 (design question 12).*

- **Who answered, and their roles, travel with the answer.** The Ventoux API, the only caller
  allowed to send answers (D19), states the person signed in and the roles its identity provider
  gives them. The engine never looks a person up: a lookup would be I/O inside the workflow, and a
  replay after someone's roles changed would decide differently. History records the answer with
  its roles, so replay and the audit both see what was true when the person answered.
- **Roles are registered in the catalog,** by the platform team, like source labels (D12), each
  with the highest risk it may approve (`register_role("support-lead", approves="high")`; none by
  default). A definition naming an unregistered role is refused by `ventoux check`, and a role the
  engine doesn't know counts for nothing at runtime (fail closed).
- **Every wait and approval names its roles;** there is no "anyone may answer" default.
- **A person's identifier is written one way:** lowercase letters, digits, `.`, `_`, `@` and `-`,
  starting with a letter or digit (`ana`, `ana.lee@example.com`); no capitals, spaces or `:`. The
  API normalises what its identity provider gives it; the engine refuses any other spelling at
  the answer, before any other check, since "someone else" (D11) compares identifiers exactly and
  `Sam` would otherwise be someone other than `sam`. Widening it is a decision recorded here.
- **In tests, the test plays the API:** `run_case(..., people={...})` and `run_plan(...,
  people={...})` give each scripted answer the roles listed for its person.

### D23. An approval is its own act, answered and checked like a task

*Decided 2026-10-08, in layer 7 (design question 13).*

- **An approval is declared, never inferred from an outcome's name.** In a plan it is its own kind
  of state, `{"approval": {"of": "pay", "roles": [...]}}`, with the outcomes `approve` and
  `reject`; `approve` must lead to the state it names. A wait offering an outcome called `approve`
  approves nothing.
- **Answered like a task answer** (D9), naming the entry it answers (`approve_refund#1`), and
  checked the same way, in the same order: the entry is open, the outcome is one offered, the
  person has one of its roles. An approval adds: the role may approve the activity's risk, and the
  person is not excluded (D11). A misspelled outcome is refused, never read as "not approved".
- **A rejection is an outcome:** the plan goes where `reject` says, and the approved step doesn't
  run (in a case, the case can then close, or a rule react).
- **Asking again withdraws the last answer:** entering an approval withdraws any open approval of
  the same step, so an earlier approval never outvotes a later rejection.
- **A lapsed approval stops the step.** If the step's inputs no longer match the digest the
  approval recorded (D11), the step stops and needs a new decision; it is never run, and never
  sent back to an approval by the engine on its own.
- **Several approvers (`count=2`) come with the `four_eyes` pattern** (layer 11).

### D24. A waiting case says what it waits for

*Decided 2026-10-09, in layer 8 (design question 14).*

- **`waiting_for` lists each open task and approval,** in the order they opened, in the words the
  inbox uses: `review by support`, `approval of pay by support-lead`. A case waiting for its
  review says so; it neither crashes nor closes.
- **It is the part of pending work (D10) that waits on people.** Running steps, set timers and
  failed steps are pending work too, and keep the case open; they are reported as they arrive
  (failures and closing in layer 8, timers in layer 11), never folded into `waiting_for`.

### D25. An open approval follows the case file

*Decided 2026-10-09, in layer 8.*

- **An approval is asked when its step is about to start:** its requirements are met, its `when`
  holds, and the approval's own `when` holds now. Each time it is asked is its own entry
  (`pay.approval#1`), answered by entry like any task (D23).
- **While it is open, it follows what the step reads.** If the step stops being admitted, or any
  value the step reads (its inputs, its `when`, the approval's `when`) changes, the open approval
  is withdrawn and recorded with the reason; if the step is admitted again, a new entry is asked.
  An answer to the withdrawn entry is refused as closed. So nobody approves values they didn't
  see: Sam, reading a sheet that says 250, can't approve the 900 a reworked review set since.
- **A given approval is spent in the decision that starts its step,** so in a case nothing comes
  between them; a lapse (D11, D23) can only come from a change request (layer 12), and it stops
  the step.
- **The person who opened the case approves none of its steps** (D11). Who opened it is stated by
  the trusted caller, like an answer's roles (D22); a case a system opened has no such person.
- **Nor does the person who proposed a step's run approve that run.** A proposal decides that the
  step runs, so its proposer is excluded like anyone whose answer decides it (D11), as change
  requests are "applied only after someone else approves". *Added in the tutor review of layer 8a,
  before D25 was merged.*

### D26. Who operates a case, and what a retry is

*Decided 2026-10-09, in layer 8b.*

- **Operating is a role the platform team registers,** like approving (D22):
  `register_role("operations", operates=True)`. A role the catalog doesn't mark as operating may
  not act on a failed step, whoever states it. "Needs attention" is the platform team's concept
  (personas), so no case names its operators, and the quickstart meets nothing new.
- **An operator acts on a failed step in two ways:** retry it, or close the case through a close
  reason that lists their role (D10). There is no skip: skipping is a change request (D17).
- **A retry is the same step run, with the same idempotency key.** A step fails after its retries
  ran out, so its side effect may or may not have happened; sending the same key (`pay#1`) lets
  the system return the first result instead of acting twice (D17). This is unlike a reset,
  which starts a new run of the workflow and so new keys (D19). The retry checks the step again
  first (its requirements, its condition, its inputs), and an approval spent on the run still
  holds only if the inputs it saw are unchanged (D11).
- **A failed step is never cancelled by a milestone.** While a run needs attention, reaching the
  milestones of `closes_when` doesn't close the case (D10's "cancelling any pending work" was
  written before failed runs were pending work): it closes once the run is retried to completion,
  or a person closes it with a declared reason. Nothing is skipped automatically (D17). *Added in
  the tutor review of layer 8b, before D26 was merged.*

### D27. A case continues as new, keeping its keys (design question 18)

*Decided 2026-10-09, in layer 8c.*

- **A case is its workflow ID, and its keys survive every run of it.** An idempotency key is
  `<workflow ID>/<first run ID>/<entry>`: the case's ID, the run ID Temporal gives the first run
  of its chain (the same in every run after a continue-as-new), and the step run, `pay#1`. The
  entry counts come from the case's step runs, which cross over, so a key never repeats and never
  changes between runs. The first run ID keeps two cases apart even if an ID is reused once
  Temporal has forgotten a closed case; while it remembers it, a second case with the same ID is
  refused. A plan step's keys add its own: `<case key>/collect#1/pay#1`.
- **A reset keeps the case's keys.** Temporal keeps the first run ID through a
  reset (its documentation; not tested here), so a reset case sends the same keys again and the
  payment system returns the first refund. This narrows D19's warning to plans, whose keys carry
  their own run ID; resets stay restricted and audited (D19) for every other reason.
- **When:** after a fixed count of events in one run, or when Temporal suggests it (its history is
  getting large), whichever comes first; and only at a quiet point: no activity or plan step
  running, no event waiting to be decided, no signal still being handled. An open task or approval
  is only state, so it doesn't hold the switch back. A count, never a clock, so replay switches at
  the same place.
- **What crosses:** the whole state of the case: the case file and each value's sources, the
  milestones, every step run (and so the entry counts), open, given and withdrawn approvals, who
  proposed what, what waits on people, who opened the case, its phase, its flags and its history
  lines, with the definition it runs. Nothing else: the new run decides from that state alone.
- **Answers sent during the switch are never carried as a queue.** The switch happens only with
  no event waiting, and Temporal refuses to complete it if a signal arrived meanwhile: the run
  goes on, decides that signal, and switches later. So every answer is judged by the run whose
  history records it, against the entry open when it arrived (layer 6). An entry open before the
  switch is still open after it, under the same name.
- **People address the case, not a run:** answers, proposals, retries, closes and reports go to
  the workflow ID alone, which always reaches its latest run.

### D28. A plan step runs as a child workflow of its case

*Decided 2026-10-09, in layer 8c.*

- **A case references a plan, never defines one:** `{"kind": "plan", "plan": "refund-order@1",
  "inputs": {...}}`. The deployment supplies its plans, as it supplies its catalog; releases
  package them later (D5, D13). A plan the deployment lacks fails the step (fail closed).
- **Its inputs are expressions over the case file;** each becomes one of the plan's fields with
  the sources of what it read (D12), so provenance crosses into the plan, and the plan's checks
  see where each value really came from.
- **On Temporal it is a child workflow,** `<case ID>/collect#1`, whose run is named by the case:
  its keys are the case's key for that step run, then the plan's own (`…/collect#1/pay#1`). A
  retry (D26) starts the child again under the same ID, with the same keys.
- **How it ends:** a plan that succeeds makes the step `done`; one that ends in a failed final
  state gives the outcome `failed`, which a step can react to, like a declared outcome; one that
  stops makes the step fail, and the case needs attention (D17).
- **The case's exclusions cross into the plan:** the person who opened the case, and the person
  who proposed the step's run, approve nothing inside it (D25). Otherwise a plan step would be a
  way around them.
- **The plan's own waits are answered on the child,** by its ID; the case's history shows the step
  started, and the case waits for it. Listing them in the case's `waiting_for` (D24) needs the
  child to tell its parent, and comes later: until then the inbox reads them from the child.
- **Closing the case stops its plan steps.** A wait open inside a running plan is the case's
  pending decision one level down, so when the case begins closing (D10), the plan stops taking
  answers: its open waits are cancelled, nothing new starts in it, and an activity already
  running inside it finishes, since it may already have acted. The plan then ends, its step run
  is recorded as cancelled because the case is closing, and the case closes once it has ended.
  On Temporal the case signals its child to stop; it doesn't cancel it, since cancellation
  would cut short the wait on an activity that must finish. *Added in the tutor review of layer
  8c, before D28 was merged.*
- **What ran on after the close is flagged, never hidden.** A stopped plan reports each activity
  that finished or failed after the stop, and the case flags each one as it flags a step (D10):
  `settle#1: payments.refund@2 completed after the close was requested`, or `… failed after the
  close was requested: <what it said>`. A duplicate refund paid after the close never
  disappears into "cancelled". *Added in the second tutor review of layer 8c, before D28 was
  merged.*
- **No approval of the whole plan yet.** A plan carries its own approvals, checked when it is
  read (layer 3); "Approve this plan" (D14), for plans an AI drafts, comes with authoring
  (layer 15).

### D29. Outputs carry their contract's sources; workflow steps are bound children

*Decided 2026-10-10, in layer 8d.*

- **An output's source is declared on its field, in the contract:** `system:<name>` or
  `untrusted:<registered label>`, never `person:` or `trusted:` (D12). A field with nothing
  declared is `untrusted:undeclared` (D6); `undeclared` is the engine's label, never registered.
- **Declaring a source changes the contract's hash; declaring none changes nothing.** The source
  is part of the output's JSON Schema, which the hash covers (D5), and a field with none adds
  nothing to it. So contracts written before output sources existed keep their hashes, and read
  every output as untrusted: the strictest reading, so no promise was loosened. Making an output
  trusted is a new version.
- **Outputs land in the case file as `<step>.<field>`,** like the step's outcome, with the source
  the contract declares, never one the activity or workflow sends back; only the fields the
  contract declares, only with `done`, the latest run's read.
- **An output is a value the case file holds exactly:** a decimal, a text or true or false (D20).
  A contract whose output field is a `float`, an `int` or a nested model is refused when
  registered; and checked again when the value arrives, on nothing registration did, a value of
  any other type fails the step, and nothing it gave lands. *Added in the tutor review of layer
  8d, before D29 was merged.*
- **A workflow contract** shares the catalog, its references and its hash with activity contracts.
  It promises a `timeout` instead of a retry policy, and declares no outcomes. `cancellable` (D6)
  comes with the first thing that stops a running step; until then closing lets a workflow step
  finish (D10).
- **A binding says where a workflow contract runs** (workflow type, task queue), supplied by the
  deployment (D5's "what vs where"). No binding, or a step naming a contract of the other kind,
  fails the step (fail closed). On Temporal a workflow step is a child workflow `<case ID>/<entry>`,
  retried under the same ID and key (D26, D27).
- **A binding's task queue may move under open cases; its workflow type may not.** A case's
  history records the type of each child it started, so a case replayed with its workflow bound to
  another type fails replay and waits; moved to another queue, it replays. Changing a workflow
  type while cases are open is planned with releases and activation (layer 12). *Found in slice 6
  of layer 8d.*
- **The contract test checks shape, not truth:** it runs the bound workflow on Temporal's test
  server and reports a missing, extra or mistyped output, a timeout and a failure. Whether a
  declared source is true is for review (D6).

### D30. References go where their system is expected; the case file is filtered by role

*Decided 2026-10-10, in layer 9a.*

- **Systems are registered,** by the platform team, like source labels (D12):
  `register_system("crm")`. A reference naming a system nobody registered is refused: in a
  contract when it is registered, in a case when it opens, in a plan when its run starts.
- **A contract input may require a reference to one system:** `Annotated[str, reference("crm")]`,
  part of the input's JSON Schema, so the hash covers it (D5). At runtime it takes only a
  reference field of that system, read as it is; another system's reference, a text or a computed
  value fails the step (fail closed), in cases and in plans. `ventoux check` refuses it first
  (case validation, layer 10).
- **Who sees a field:** anyone holding a role the case names, unless the field's `visible_to`
  narrows it (D16); outcomes and outputs follow the same default. The view is filtered where the
  case runs, before it is sent: a hidden field is absent, and said hidden with the roles that
  would see it.
- **An approver must see what they approve:** an answer to an approval, approve or reject, from a
  person who can't see a value the step reads (its inputs, its `when`, the approval's `when`) is
  refused, saying what they can't see. D16's validator warning is layer 10's; this refusal
  depends on nothing it does.
- **Resolvers** are functions registered per system in `tooling`, called with the viewer. They read
  the reference from the viewer's filtered view, so nothing hidden can be resolved, and what they
  return is never stored. That a record was shown is recorded on an open case by a `shown` event,
  as a line naming the field, the system and the reference.
- **A refusal or a failure names the field and the kind of value, never the value:**
  `approved_amount is a number, and the answer gives a string`. The history, and every report
  read from it, reaches people who may not see a field; a message quoting its value would show it
  to them. Only a `shown` line names a reference, as D16 asks. *Added in the tutor review of 9a,
  before D30 was merged.*

### D31. Sensitive values are wrapped, encrypted one by one, and never written out

*Drafted 2026-10-13, in layer 9b.*

- **A sensitive field names who may see it.** `"sensitive": true` needs `visible_to`; any field
  type may be sensitive. Only those roles get its value in the view (D16); everyone reads
  `‹sensitive›` wherever a value would be written: history lines, refusals, failures, the view's
  lines, a `shown` line's reference.
- **The value is wrapped wherever it goes.** In the state it is `Sensitive`, whose text is
  `‹sensitive›`. An input computed from it is wrapped too, so it reaches an activity or a plan
  encrypted, and the activity receives the plain value. Conditions and checks read the plain
  value inside the worker. A sensitive value arriving unwrapped is refused: it has already been
  seen. A workflow step can't be given one: its worker doesn't hold the key.
- **Each value crosses Temporal in its own part of a payload,** which the payload codec has the
  key provider seal with the case's key, found from the workflow ID Temporal gives it; a child
  `<case ID>/<entry>` uses its case's. The provider seals and opens; it never hands out a key, so
  a key never leaves it, as with Vault's transit engine or a cloud KMS. The development provider
  seals with AES-256-GCM, from `cryptography`. So a case ID has no `/`. A payload with
  no sensitive part passes untouched, needing no key: histories written before 9b replay as
  they are. Anything the codec can't encrypt or decrypt (no key, no workflow ID, a damaged
  part) is an error, never plain text.
- **A key is made when a case (or a standalone plan run) starts, and never made again,** by the
  client, through the key provider (D15), before the workflow starts. If the start then fails,
  the ID is spent.
- **Failures are encrypted whoever raised them.** Temporal keeps a failure's message and stack
  trace outside payloads; Ventoux's failure converter moves both into one, as sensitive parts.
  An activity's own message is treated as sensitive in every case, since Ventoux can't know
  what it says: the case records `failed: ‹sensitive›`, and the text stays only in Temporal's
  failure, under the case's key.
- **The worker's log keeps only an exception's type.** Temporal's SDK logs a failed activity, and
  a failed workflow task, with its exception and traceback before the failure is sealed; worker
  logs go where many people read them. So the workers install a filter on Temporal's loggers
  that keeps the exception's type and drops its message and traceback. The case's line names the
  type too (`failed with ConnectionError: ‹sensitive›`): a type is code, never data, and tells
  an operator something. **An activity's own logging belongs to its author:** Ventoux can't
  filter it, and the deployment guide (D19) must say so. *Added in the tutor review of 9b,
  before D31 was merged.*
- **The client can't tell which form fields are sensitive,** so every form value crosses
  encrypted, and the case keeps encrypted only the sensitive ones.
- Rejected: encrypting whole payloads (the history would be unreadable wherever a sensitive value
  appears, D15); sensitive outputs from contracts (a contract change of its own, nothing needs
  it yet); keeping an activity's message readable to operators (operators aren't in
  `visible_to`).

### D32. Forgetting a case: a request, a close, then the key

*Drafted 2026-10-14, in layer 9c.*

- **Forgetting is its own small workflow, `<case ID>/forget`,** proposed by one person and
  approved by another, both holding a role the platform team registered to forget
  (`register_role("privacy", forgets=True)`, as operating roles are, D26). The proposer can't
  approve it (D11, D25). A refused answer is recorded and the request waits on; a rejection ends
  it. It is the first change request (D15); layer 12 makes the mechanism general.
- **Destroying the key comes last.** The approved request asks the case to close as `forgotten`
  (D10: tasks and approvals cancelled, running work finishes, anything completing after the
  close is flagged). Only once the case's workflow has ended, with no activity, plan step or
  workflow step of it still running, is the key destroyed, by an activity the worker registers,
  never a contract a definition could call. Work still in flight can't decrypt its own values
  without the key, and an open case's replay needs it (D15).
- **A closed case can be forgotten,** keeping its own close reason, **unless its definition keeps
  its records:** `"forgetting": "allowed"` (the default), `"while_open"` (refused once the case is
  closed, for books and records) or `"never"`. It is a business decision about a kind of record,
  so it lives in the definition and changes with a release (D5). No deployment-wide default yet.
- **Twice, or a case that never existed, is refused before anyone approves,** from the key
  provider, which remembers a destroyed key and never makes it again, so the check holds after
  Temporal has dropped old workflows, and the ID can never open a case again.
- **A forgotten case reads cleanly.** `report` reads the report the case returned when it closed,
  which holds no sensitive part; `view` is refused; any other query or replay fails saying the
  key was destroyed, and the worker carries on. Never plain text, never a crashed worker.
- **What stays:** every decision, who made it and with which role, the definition, flags, every
  value that wasn't sensitive where it was used, and the request's own history. **What goes:**
  every sensitive value, every form value in the answers people sent (D31 encrypts them all),
  and every failure's message and stack trace. Staff identifiers stay: forgetting is about the
  case's subject, through its sensitive fields.

### D33. Fresh facts: time on events, refreshing a read, and a given approval's lapse

*Drafted 2026-10-15, in layer 9d. Adds to D18 and D25.*

- **Time is data on each event,** in whole seconds since the epoch: the case reads no clock, so
  the same history decides the same way (D18's "workflow time"). On Temporal each event is
  stamped as it reaches the case, from the workflow's time, which history records. Tests give
  the time themselves.
- **Every value written records when, and by which step run, it was obtained:** the opening, a
  person's answer, or a run such as `check_order#1`.
- **`max_age` is written where a fact is used** (D18): on an activity, workflow or plan step,
  only for fields the step reads, as `30m`, `12h` or `1d`. It is checked once the step's
  `requires` are met, before its `when`, its approval's `when`, asking for its approval and
  starting it. A fact with no known time stops the step (fail closed).
- **Only a read is fetched again:** an output or outcome of an activity step whose contract's
  effect is `read`. Everything else (the opening, a person, a `write`, `notify` or `compute`
  activity, a workflow or a plan step) needs attention (D17). A `compute` step run again on the
  same inputs gains nothing; a workflow belongs to another team and is not re-run unasked.
- **A refresh is a new run of the step,** with its own entry and key (D17), checked as every run
  is; its output replaces the old one, with fresh sources and time. It doesn't undo its step for
  `requires` while it runs: only what it changes counts. If it gives no fresh value, the step
  that needed it needs attention: never a second refresh for the same need.
- **A refresh passes the same gate as any start, and fails closed.** It runs only if its step
  could start now: its requirements met, its condition true, and no approval needed. A refresh
  never asks for an approval: a read behind one (a high-risk credit check) needs attention, and
  a person decides, since one approval unlocks one run of one step (D11). Asking for a new
  approval while the step that needs the fact waits was the other way; it needs more machinery
  (an approved run marked as a refresh, a rejection's meaning for the waiting step) than any case
  has asked for yet. *Added in the tutor review of 9d, before D33 was merged.*
- **A given approval lapses on a refresh that changes what it saw** (D11): the step's inputs, its
  `when` or the approval's `when`, which it now records as an open approval does (D25). The step
  is then checked again, and a new approval asked if one is still needed, since a refresh is the
  engine's routine, not a person's change. A lapse from a change request still stops the step
  (D25). A refresh that changes nothing leaves an approval standing, open or given.
- **People read ages at their own time:** the approval sheet shows each fact's age as of when it
  is read, a time the reader gives, since a sheet is read, never decided on (D18).
- **Staleness is noticed only when an event reaches the case.** Timers that would notice sooner
  come with rules (layer 11). The source's own as-of time (D18) waits until something needs it:
  it is a contract change.

### D34. Case validation: errors and warnings, structure proven, the runtime on its own

*Drafted 2026-10-15, in layer 10a.*

- **A case definition is checked against the catalog before any case opens,** by
  `validate_case(case, catalog)`, which lists every problem as an issue (`path`, `code`,
  `message`: what is wrong, then what to do), as plan validation does. It lands in four parts
  (layer 10a–10d).
- **An error or a warning, said on each issue.** An error is proven wrong for every case of the
  definition, or can't be read, and refuses it. A warning may be meant, or depends on what the
  check can't know (who holds which roles, the data), and is shown. A warning lets a definition
  through, never a run. An issue that says neither is an error (fail closed).
- **Structure is proven; values are not.** What a case can ever reach is the least set closed
  under "a step whose requirements can all be met can run, and reaches its milestones", grown from
  nothing until a round adds nothing; it ends because it only grows, over the definition's finite
  steps and milestones. Every `when` is taken as possibly true and every outcome as possible, so a
  step left out can never run on any path, and is an error. A step only data keeps from running
  isn't seen, and runs nothing unsafe.
- **Case-file provenance is computed in one pass:** each writer tags what it writes with sources
  that don't depend on what it read (D9, D29), so a field's sources are the union of what its
  writers stamp. A fixpoint over sources is needed once a field is computed from other fields
  (rules updating the case file, layer 11; design question 17).
- **Once every `closes_when` milestone is reached, nothing new starts,** even while a failed run
  holds the close. Adds to D10 ("no step starts" once a case closes) and D26 (a failed run is
  never cancelled by a milestone), between which admission went on: a step waiting for the
  milestone started though the case was about to close. Now a proposal is refused, saying why; an
  approval given meanwhile starts nothing; the failed run, retried, still runs, and its completion
  closes the case. So a step requiring every `closes_when` milestone can never run, and case
  validation's error for it is a proof. *Added in the tutor review of 10a, before D34 was
  merged.*
- **A case that can never close is an error, not a warning,** when it is proven: it stays open,
  no close reason names a registered role, and `closes_when` is empty or can never be met. This
  refines D10's "the validator warns about cases that can never close": what is proven for every
  case refuses the definition; what may be meant warns (a `closes_when` milestone that can't be
  reached, while the case still closes another way). *Added in the tutor review of 10a, before
  D34 was merged.*
- **The runtime depends on nothing validation did.** No flag says a definition was checked; the
  drivers don't call `validate_case`; every runtime refusal stays. A case that skips validation is
  as safe as before.
- **`ventoux check` comes with the builder** (layer 14), which reads the Python file and maps
  errors to source lines; `validate_case` is its engine.

### D35. Case validation reads each step against what it calls; the runtime refuses the same

*Decided 2026-10-15, in layer 10b.*

- **What a step calls is read against the catalog and the deployment's plans:** its contract
  exists and is of the step's kind; its inputs are the ones its contract or plan takes, all of the
  needed ones, never the idempotency key the engine fills (D17); a high-risk step has an approval,
  and every role on it may approve that risk (D11, D22); every role, source label and system it
  names is registered (D12, D22, D30).
- **The plans are given as the runtime is given them:** `validate_case(case, catalog, plans=…)`
  takes the stored plans by reference, as `run_case` and the case workflow do (D28), and reads
  each with the runtime's own reader. A plan step whose plan isn't given is an error (fail
  closed). The plan's own checks stay its own (layer 3).
- **A case's expressions are type-checked as a plan's are** (D20), over the values a case holds:
  its fields; a task's outcome, as the closed list of its outcomes (D9); an activity step's as
  `done` and its contract's outcomes (D17); a workflow step's as `done` (D29); a plan step's as
  `done` or `failed` (D28); each output with its contract's type (D29). Nothing else is a value.
- **Every error is one the runtime would meet too.** Where a check found something the runtime let
  through, the runtime now refuses it, on nothing validation did (D34): a case expression that
  doesn't type-check fails its step, so a misspelt outcome is no longer silently false; an input
  named after the idempotency key is refused, never overwritten; a case declaring a field
  untrusted with a label nobody registered doesn't open; and a role nobody registered gives sight
  of nothing, as it answers nothing (D22, D30).
- **A message may quote a literal of the definition when that literal is what is wrong**
  (`assess.outcome has no outcome "acept"`): it is text the author wrote, already in the
  definition. Titles, an approval's reason and every value from a case file are never quoted.
- **One cause, one issue:** a step whose contract or plan is missing gets one issue, and nothing
  that reads what it would give is reported again; a role already named by a structural issue
  (D34) isn't repeated.

### D36. Case validation follows each value to where it goes; inputs take only their exact type

*Drafted 2026-10-16, in layer 10c.*

- **Where a value comes from is computed in one pass** (D34): the opening is stamped with the
  opener, a person's answer with the person, an outcome with its contract or plan, an output with
  its contract's source (D29), and a field declared `untrusted:<label>` keeps its label whoever
  writes it (D12). An input comes from every field it reads, a condition inside it included, as
  the runtime records. So a value an input policy refuses (D21) is refused every time the step
  runs, and case validation's `INPUT_POLICY` is an error. Who opens a case is the one thing the
  check can't know: a refusal that holds only when a person opens it is a warning.
- **A plan step carries its case's sources into its plan** (D28): each of the plan's fields comes
  from what the case gives it, and each activity in the plan is checked with that, at the case's
  input, before the plan runs. The plan's own marks stay the plan's to answer for (layer 3).
- **Every input is given exactly the type it takes.** A case holds decimals, texts and booleans
  (D20), and an activity's or a workflow's inputs are validated strictly: a value is never
  converted, so the text `"40"` is refused where a decimal is taken, in cases and in plans. A plan
  checks each field the case gives it against the field's type when it starts, and a reference
  field takes only a reference to its system, read as it is, as a contract's reference input does
  (D30). Case validation refuses both first.
- **An input takes only what a case's value can be,** checked when its contract is registered,
  as an output's type is (adds to D29): a `Decimal`, a `str`, a `bool` or a `Literal` of texts,
  each possibly optional, a reference being a `str`. Strict validation would accept other types
  (a `float` from a decimal, an `Any`), and the activity's own model would then convert the value;
  so the catalog refuses them, saying what to use instead. *Added in the tutor review of 10c,
  before D36 was merged.*
- **A workflow step is never given a sensitive value** (D31), and case validation refuses one
  first. A plan field given only values written in the definition comes from nobody, so the plan
  refuses to start, and case validation says so first.
- **An approver who can't see what they approve is a warning, never an error** (D16): an
  approval is judged with every role the person holds, so someone holding a role that sees the
  value as well may approve, and the check can't know who holds which roles. The refusal at
  answer time stays (D30).
- **One data-flow issue per input:** the first the runtime would meet when the step runs.

### D37. Case validation warns about what surprises an author; only what holds for every case refuses

*Drafted 2026-10-16, in layer 10d.*

- **A warning describes what the runtime really does** with the definition, and each is shown
  with its run. Four are given:
  - **an outcome a system may give that no condition reads** (D9, D17): each outcome an
    activity's contract declares, and a plan step's `failed`, that no condition tells from `done`.
    The case goes on, and with nothing left to do closes, with nobody told. A task's outcomes get
    none: the person who answered chose it.
  - **a value read before it is surely set** (D9, design question 14): reading a value nobody set
    fails the step. A value is surely set when it is given at the opening, when the step waits
    for its writer and every way the writer ends sets it, when the step requires a milestone only
    setting it reaches, or when a guard says so: the step's `when`, read first, guards its
    approval's `when` and its inputs, and inside one expression only `if` guards a branch, since
    `and` and `or` read every part (D20).
  - **a `max_age` on a fact that can never be fetched again** (D33): from the opening, a person, a
    step that writes, notifies or computes, a workflow or a plan step, or a read whose step always
    needs an approval. Each time it is stale, the step needs attention.
  - **an approval whose `when` reads none of the fields its step is given** (D9): it guards a
    neighbouring value, not the one that is sent.
- **What holds for every case is an error** (D34): a step reading, every time it starts, a value
  that only steps waiting for it set fails every time. The value is set only once the step is
  done, and it is done only after a run that read it, so no retry or proposal helps. A
  condition reads only the branch of an `if` it takes; an input reads every value it names, as
  where its value comes from is worked out from all of them (D36). *Corrected while building
  layer 10d, before D37 was merged: the draft exempted a step that can be proposed, which the
  runtime refuses too.*
- **The quickstart warns about nothing:** its refund calls the customer when the provider
  declines, so a declined refund no longer closes the case with nobody told.
- **One cause, one issue,** as for errors (D35): a step or a value an error already names gets no
  warning.

### D38. Rules: a moment, a condition read then, and untrusted data never decides (design question 17)

*Drafted 2026-10-17, in layer 11a. Adds to D7, D10 and D34.*

- **A rule is `on`, `when`, `then`.** `on` names one moment; `when` is a condition, as on a step,
  read once the moment has come; `then` acts. People read it as *when / if / then* (D7). In 11a a
  rule only reaches milestones; starting and stopping steps, events from outside, updates to the
  case file and timers come in the later parts of layer 11.
- **Three moments, a closed list:** the case opened (once), a milestone reached (once, since it is
  never undone), a step's run started (each run, a refresh included; a retry is the same run,
  D26). Adding a moment is a decision recorded here, like an operator (D20).
- **A rule remembers nothing.** Its condition is read in the decision that handles its moment, on
  the case file as it is then, and type-checked first (D35). A step's admission is read again
  after every event: admission is level-triggered, a rule edge-triggered. Why: Flowable's CMMN
  engine remembers a met sentry part until its item starts, and needed a second mode because the
  memory outlived the data it was read from (`docs/layers/11-research.md`).
- **Rules run inside the decision, in order.** Moments are taken as they happen, the rules on one
  moment in the definition's order; a milestone a rule reaches is a moment too; admission runs
  again after; the case settles only once nothing is left. Each firing is an entry
  (`flag_high_risk#1`), so a rule's name is unlike any step's or milestone's.
- **A rule that can't be read needs attention** (D17): it acts on nothing, keeps the case open, and
  an operator retries it, reading its condition again, or closes the case. Never read as false.
- **Untrusted data informs; it never decides** (design question 17). A rule that reaches a
  milestone decides for the case, so if its condition reads a value from an `untrusted:` source it
  doesn't act, and says which value and source, never the value. Case validation refuses a rule
  whose condition reads a value that is untrusted whoever writes it (`UNTRUSTED_TRIGGER`). And,
  built in layer 11b: a condition that lets a step start (its `when`, or a rule that starts it)
  counts as read by every input of that step, for its input policies (D21), so an untrusted
  condition can't choose which trusted value is sent; an approval whose `when` reads untrusted
  data is asked whatever it says, since untrusted data may add an approval, never remove one
  (D11). This changes the runtime check before a step (layers 4, 8) and case validation's
  `INPUT_POLICY` (D36) when it is built.
- **Rules stop with the close.** Once every `closes_when` milestone is reached, closing or held by
  a failed run (D34), no rule acts, including one on the moment that completed it; each such
  firing is recorded with why. D34's "nothing new starts" becomes "nothing new is decided"; a
  person's close does the same.
- **Case validation counts rules** (D34): what a case can reach includes what rules reach, every
  `when` taken as possibly true; a milestone a rule may reach proves nothing about values; and a
  rule whose moment can never come, or comes only once every `closes_when` milestone is reached,
  is an error (`NEVER_FIRES`). D7's "rules that can never fire" stays a warning only where it
  depends on values.

### D39. Rules that start steps: the engine proposes, and an untrusted condition can't choose what is sent

*Drafted 2026-10-18, in layer 11b. Adds to D11, D17, D25, D26, D33, D34 and D36; narrows D38, whose
text is kept.*

- **`start` is a proposal by the engine.** `"then": {"start": ["review"]}` proposes a run of each
  step named, and admission decides as for a person's proposal: its requirements, whether it is
  running or waiting for its approval, whether it may run again, its `when`, its fresh facts, its
  approval and its inputs; and rules stop with the close (D38). The proposer is the rule's entry
  (`send_back#1`), never a person. A step a rule starts may leave out `proposed_by`: D39's one
  loosening, of layer 8's rule that a step that doesn't start by itself, or is repeatable, names
  it, whose reason (nothing else could start it) no longer holds once a rule may. `proposed_by`
  keeps meaning which people may propose it; with none, nobody may.
- **A fourth moment: a task answered.** `{"answered": "<task>"}` fires each time a run of the task
  is answered, whatever the outcome, and names only a task (D38: a moment is added by a decision).
  A milestone is reached once and `started` fires before the answer exists, so a loop needs it.
  What brings a loop of rules round again is then a person's answer, as a plan's loop passes
  through a wait (design question 18). Set aside: a moment for any step finishing, with which a
  case could call a payment provider again on each decline by itself, a retry policy that is the
  platform team's (D17).
- **A start the engine can't make is never silent.** It is recorded, and nothing runs, when the
  step's requirements aren't met or its `when` is false; it is running, waiting for its approval,
  or already waiting to start; it has run and isn't repeatable; or its latest run needs
  attention. It waits when a fact it needs fresh is stale and can be fetched again. And it fails,
  needing attention, as admission does, when its condition can't be read, its contract is
  missing, an input is refused, or a stale fact can't be fetched again (D17, D35).
- **A proposal waits for its fresh facts** (adds to D33). A step a person proposes, or a rule
  starts, whose stale fact can be fetched again is accepted and waits: the fact is fetched, then
  admission reads everything again on the fresh value, and starts the step or says why not. The
  waiting start crosses continue-as-new (D27). Until now a person's proposal skipped the check and
  ran on the stale fact, against D33.
- **Nothing starts beside a failed run** (adds to D26). A step whose latest run needs attention is
  not started again, by a rule or a person's proposal: the failure would be skipped by another
  name (D17), and for a step with side effects the new run's new key could make them happen
  twice. An operator retries it or closes the case. Until now a person could propose a new run of
  a repeatable step, and the operator's retry of the failed one was then never scheduled.
- **Who can't approve what a rule started** (adds to D11, D25): whoever's answer the rule's `when`
  read, as for a step's own `when`. A rule remembers nothing (D38), so the run keeps, until it
  starts or is dropped, the rule's entry, those people and the untrusted sources the `when` read.
  The person whose answer only brought the moment is not excluded, as a person whose run a step
  `requires` isn't; changing that would be one decision covering both.
- **Each decision still ends.** A step a rule has started in a decision isn't started again by a
  rule in it (recorded): a rule that stops a step (layer 11c) could otherwise loop with one that
  starts it. A decision then starts finitely many runs: an event brings at most one `answered`
  moment and one run of its own; each milestone is reached once; each step starts by itself at
  most once; each stale fact is fetched again at most once until its refresh lands (D33); each
  step has at most one waiting start, and one start by a rule.
- **An untrusted condition can't choose what is sent** (narrows D38's "counts as read by every
  input of that step", which, taken as written, merges the condition's sources into each
  input's; adds to D36). A separate check, never merged into an input's own sources: if the step's
  `when`, or the `when` of the rule that started it, read an untrusted (or unrecognised) source,
  each input whose policy refuses that source is refused, and the run fails naming the condition's
  field and source, never the value. Only those sources count: a `when` reading a person's answer
  changes nothing for an input that takes a value from one system. Merging them would loosen a
  policy: a literal input would be credited with the condition's sources. A plan step carries its
  condition's untrusted sources beside its fields, never inside them. A field the condition names
  that isn't set yet counts what any of its writers could give, read from the definition (fail
  closed; this corrects 11a's runtime, which skipped it, so a rule validation refused acted).
- **An approval's `when` that read untrusted data asks anyway.** It is read as before, so one that
  can't be read stops the step; if it read untrusted data, the approval is asked whatever it gave,
  saying why: untrusted data may add an approval, never remove one (D11).
- **Where the influence ends:** at the step the condition lets start. A rule on that step's start,
  or a milestone its run reaches, may carry it further; there the safe tool is a person, in an
  approval or a task. A rule that reaches a milestone and reads untrusted data doesn't act at
  all, its starts included (D38). A plan's own transitions are left as they are, and open (design
  question 17).
- **Case validation counts what rules start** (D34). One answer to "who can start this step" (it
  starts by itself, a person with a registered role proposes it, or a rule that can fire starts
  it) wherever a check asks; a start refused every time it fires is an error at the rule
  (`NEVER_STARTS`), claimed only where proven, and a step all of whose starts are refused never
  runs; an input refused every time a rule starts its step is `INPUT_POLICY` at the rule; a
  moment a check doesn't know is an error, never read as the opening.
- **A loop of starts.** A loop that comes round on each answer and that nothing in the case can
  end (entered in every case; no `when` on its rules or steps; every requirement of its steps met
  whenever a rule of the loop starts them; every step repeatable without an approval; no rule
  stopping it), with no reachable `closes_when` and no close reason with a registered role, is
  `NEVER_CLOSES`. The same loop when a close reason or `closes_when` can still close the case is a
  warning, `LOOPS_UNTIL_CLOSED`, as D10 asks for "a step that can always be restarted". A cycle
  through `started` gets nothing: whether it loops depends on the order of events.
- **`NEVER_CLOSES` says what it proves** (adds to D34): an approved forget request closes any case
  whose definition allows it (D32), so the error says nothing in the case's work or its close
  reasons can close it, and, when its definition allows forgetting and a role that forgets is
  registered, that only a forget request would; otherwise, that nothing could.

### Simplifications adopted

- **Kinds of step:** `activity` (call one activity), `task` (one human task), `plan` (a multi-step
  state machine, only when needed) and, per D6, `workflow` (an existing Temporal workflow). Same
  checks around all of them.
- **One kind of rule:** *when* (milestones reached, a step starts or answers, an event arrives, time
  passes) *if* (a condition)
  *then* (reach a milestone, start or stop a step, update the case file). It replaces sentries,
  triggers, deadlines and automatic activation as separate concepts. Trust checks apply to it.
- **One change request mechanism:** someone proposes, someone else approves, the engine applies. Used
  for case-file edits, migrations and any other change to a running case.
- **Deferred until after v1.0:** signed approvals (D19), ad hoc steps with inline plans drafted at
  runtime (D13), restarting running steps on a new version, advanced parallel joins, automatic
  compensation (sagas).

## Concepts

| Term | Meaning |
|---|---|
| Activity | A registered capability with a versioned contract (`name@version`), implemented as code |
| Catalog | What a deployment allows, never where it runs: activity and workflow contracts, resolvers, roles and source labels |
| Plan | A step made of several calls and waits, written as data: a state machine whose states call activities, wait for answers, or end ("Charter" in Agentic Chartering and the prototype) |
| Case definition | Long-running work: a typed case file, milestones, steps and rules |
| Step | A unit of work in a case (an activity, a human task, a plan or a workflow) and when it may run |
| Contract | What an activity or workflow promises: schemas, risk, input policies, output provenance, outcomes, retry policy, idempotency |
| Deployment binding | Where a contract runs in an environment: workflow type or activity name, task queue |
| Rule | *When* something happens, *if* a condition holds, *then* act on the case |
| Case file | The case's decision facts and references to records elsewhere, each with its provenance |
| Reference | The ID of a record kept in another system, typed by that system's name |
| Resolver | Shows a person what a reference points to, by asking its system on their behalf; never stored |
| Task | A step asking people with given roles a question, answered with an outcome |
| Outcome | A named answer from a task, an approval or an activity (`approve`, `declined`); a task's may set case-file fields |
| Approval | A task guarding a step: approve or reject, by an eligible person, tied to the values it saw |
| Closing | A case that will start nothing new and closes once its running activities finish |
| Pending work | What keeps a case open: running steps, open tasks or approvals, timers, explicit waits, failed steps |
| Needs attention | A case with a step that failed after its retries, waiting for an operator; nothing is skipped automatically |
| Sensitive field | A personal fact, encrypted with the case's key and shown only to listed roles |
| Milestone | A fact the case has reached (`assessed`, `paid`); recorded, never undone |
| Admission | The engine's decision to allow a proposed step, re-checked when it runs |
| Provenance tag | The sources a value was derived from |
| Input policy | A rule on an activity input: which sources may influence it (a "sink policy" in the security literature; D21) |
| Change request | A proposed change to a running case, applied only after someone else approves it |
| Package | A case definition and the plans it uses, released together |
| Release | An immutable, numbered version of a package, identified by its behaviour digest |
| Activation | Making new cases in an environment start on a given release |
| Migration | Moving an open case to a newer release, checked and approved |

(In the `chartering` prototype, steps are called fragments, and rules are split into sentries,
triggers and deadlines.)

## Layers of the system

```
tooling      CLI · semantic diff · business views · Python builder · API and inbox · resolvers
authoring    AI drafting of plans · AI step advisor for cases             (uses an LLM)
temporal     plan and case workflows · activities · worker · client ·
             payload codec and key provider                              (uses Temporal)
case         case runtime · rules · validation · migration · worklists (pure)
core         schema · expressions · catalog · provenance · validation · interpreter (pure)
```

`core` and `case` stay free of Temporal and LLM dependencies, so they run in memory, in tests and
inside a Temporal workflow alike.

## Non-negotiables

- Definitions are data. Never `eval`, `exec`, `compile`, import or unpickle anything from them.
- Expressions are pure and deterministic, limited to the operators listed in D20.
- Every side effect goes through a registered activity.
- The interpreter is deterministic, so it runs as a Temporal workflow and survives replay.
- Every value carries provenance; sink policies are checked before an activity is scheduled.
- Anything that talks to people drafts by default; it never sends on its own.
- Policies can be made stricter, never looser, by anyone downstream: a case can tighten a contract's
  retry policy or freshness, untrusted data can add an approval, a view can hide more than the
  source system; none of them can loosen.
- Nothing is skipped automatically: a failed step waits for a person (D17).
- **Fail closed.** Anything the engine can't evaluate or doesn't recognise (an unknown operator, a
  missing field, an undeclared answer) is an error that stops the step, never a permissive default
  such as "false" or "no approval needed". The validator rejects it first; the runtime refuses it
  again (found in the tracer review: an unknown operator in an approval's condition let a refund be
  paid without approval).
- Every feature ships with tests, including at least one negative test (a definition that must be
  rejected).

## Out of scope for v1.0

A visual editor, a polished production UI (v1.0 ships the API and a reference inbox, which draws
task forms from field types; there is no form designer), broker connectors, BPMN, CMMN or
Serverless Workflow import, multi-tenancy, code inside definitions (scripts, listeners), and the
deferred features listed above.

## Design questions (all decided)

1. JSON or code first: D1.
2. Expressions: D3 (a JSONata subset), superseded by D20 (structured JSON) after the spike.
3. Is a plan the right unit inside a case: no, kinds of step (Simplifications, D13).
4. Existing Temporal workflows as steps: D6.
5. Signed identities as the production default: D19, for high-risk approvals after v1.0.
6. Naming ("Charter"): D14, renamed "plan".
7. Versions: D5.
8. Gaps found by the quickstart draft: task outcomes (D9), closing (D10), approval defaults (D11),
   sources (D12), plans as an advanced concept (D13).
9. Gaps found by the case-data guide draft: references and resolvers (D16), erasure and an audit that
   survives it (D15), facts and when they were obtained (D18).

New questions found while building go here, numbered from 10.

10. **"Sink policy" or "input policy"?** (found in layer 0) "Sink" is taint-analysis jargon that
    few developers or analysts know, and the brief already uses both names (six ideas and concepts
    table: "input policies"; D5, D6, D12: "sink policy"). Proposal: say **input policy** in all
    user-facing text and validator errors, mentioning "sink" at most once for readers who know the
    security literature; analysts see only plain language ("never sends email to an address chosen
    by the AI"). The policy kinds stay a short list fixed by the engine (`no_untrusted`,
    `only_from`), written by the platform team on each contract input. To decide in layer 4,
    including the error code (`SINK_POLICY` or `INPUT_POLICY`). **Decided in layer 4:** "input
    policy" and `INPUT_POLICY`, written on the input field, kinds `trusted_only` and `only_from`
    (D21).
11. **Expressions: JSONata strings, CEL, or structured JSON?** (found before the tracer bullet)
    D3 stores conditions as JSONata strings. Few people read the stored form: developers read the
    builder (`approved > 100`), analysts and approvers read plain language. Programs read it all the
    time: the validator, provenance analysis (which fields does this condition read?), the diff, and
    a model drafting definitions. Strings read well raw but every tool must parse them, and "reject
    anything outside the subset" needs a parser for a large language. Structured JSON
    (`{">": [{"field": "approved_amount"}, 100]}`) is clumsy raw but needs no parser, is validated
    by Pydantic, makes the fields read explicit, diffs exactly, and lets a model's output be
    constrained by a JSON Schema. A middle path: people write readable syntax, the stored JSON is
    structured. To decide in the spike before layer 2, on the claim-case examples, judged on
    readability for people, parsing, typing, provenance analysis, schema-constrained model output,
    exact diffs, determinism and Python support. The tracer bullet uses a minimal structured form,
    marked `# TRACER: layer 2`, which commits to neither. **Decided in the spike:** structured JSON
    with a fixed list of operators (D20, superseding D3; `docs/layers/spike-dsl.md`).
12. **Who has which role in `run_case`?** (found in the tracer bullet) The quickstart's tests name
    people (`"ana"`) but never say where their roles come from. The tracer uses a fixed directory
    (`ana`: support; `sam`: support, support-lead). To decide in layer 7: roles passed to
    `run_case`, a test directory, or roles carried with each answer. **Decided in layer 7:**
    roles carried with each answer, stated by the trusted caller, and registered in the catalog
    with the risk each may approve (D22).
13. **How is an approval answered?** (found in the tracer bullet) The quickstart never answers an
    approval in a test, so its shape is undefined. The tracer answers it by naming the step:
    `("pay", "approve", "sam")`. To decide in layer 7, with D11 (an approval is a task with
    *approve* and *reject*). The tracer review found that approval answers aren't checked like task
    answers: a misspelled outcome (`"aprove"`) is quietly treated as "not approved" instead of
    refused, and a *rejected* approval leaves the case waiting for approval forever instead of
    letting the step not run (and the case close, or a rule react). Layer 7 must check approval
    answers exactly like task answers and define what a rejection does. **Decided in layer 7:**
    an approval is its own state, answered by entry and checked like a task answer; a rejection
    is an outcome; a lapsed approval stops the step (D23).
14. **What running the quickstart taught us.** (found in the tracer bullet)
    - *Fixed:* the large-refund test asserted only `waiting_for`, not that nothing was paid and
      the case stayed open, which is what matters most. The quickstart now asserts all three.
    - *Open:* a case waiting for a *task* has no defined report. The quickstart only shows waiting
      for an approval, and the tracer crashes when no one has answered the review. Proposal:
      `waiting_for` lists open tasks too (`"review by support"`). To decide in layer 8, with
      pending work (D10). **Decided in layer 8:** `waiting_for` lists open tasks and
      approvals, the part of pending work that waits on people (D24).
    - *Open:* the quickstart's story (Ana reviews, Sam approves) never shows the D11 exclusion,
      because Ana isn't a team lead anyway. Only a reviewer who is also a team lead shows it
      (learning question 18). Proposal: the quickstart's "When Ventoux says no" adds Sam
      reviewing and then trying to approve, refused with the reason.
    - *Open:* reading a field nobody set fails at runtime (a rejected review leaves
      `approved_amount` unset, and the tracer only avoids reading it because `pay` doesn't run).
      D9 already asks the validator to warn about conditions on answers that may not exist; to
      check in layer 3 that this covers inputs too.
15. **"Registry" or "catalog"?** (found in the layer 1 warm-up) Decided: **catalog**. To most
    developers a registry says *where* things run (a service registry, Temporal registering
    activities on a worker), and in the warm-up the queue was put "in the registry". A catalog
    lists what can be ordered and what each item promises, never which warehouse ships it. Each
    word answers one question: the **catalog** says what a definition can call; a **contract**
    says what one entry promises (and never changes: a change is a new `@N`); a **deployment
    binding** says where it runs in one environment. In short: the catalog lists contracts; each
    environment binds them. The test: if changing it would change the contract hash, it's the
    contract. "Binding" is kept (an environment *binds* a contract to a queue). The D5
    **environment registry** keeps its name: it does record where things run (worker manifests).
    Past entries in the learning log keep the old word.

16. **Should a hash failure say what changed?** (found in layer 1's walk-through) Today CI says
    "`payments.refund@1` changed without a new version", and the cause can be invisible: renaming
    the input class or editing its docstring changes the JSON Schema, so the hash. A message such
    as "`retry.maximum_attempts`: 5 → 9" would teach the rule each time it fires. But
    `contracts.lock.json` stores only hashes. Options: store each contract's canonical promise in
    the lockfile (bigger, but pull requests show a readable diff), or leave it to the semantic diff
    (layer 13). To decide by layer 12 (releases), which also reads the recorded contracts. Found in
    the layer 1 review: changing *how* the hash is computed (sorting outcomes, a Pydantic upgrade
    changing the generated JSON Schema) changes existing hashes with no change of promise, so the
    hash method itself needs a version recorded with each hash.
17. **May an untrusted value steer a condition?** (found in layer 4) An input policy checks the
    values an activity receives, not *whether* it runs. In a plan, a transition's `when` that reads
    an untrusted field (`{"==": [{"var": "llm_says_refund"}, true]}`) decides which activity runs
    next, though every input it gets is trusted. The prototype's "strict mode" adds the
    condition's sources to the inputs of the state it enters, and no further (a state machine has
    no point where the influence ends). For a high-risk activity, the approval already puts a
    person between the condition and the step (D11); for a low-risk one, such as choosing which of
    two trusted recipients gets a letter, nothing does. Options: add a condition's sources to the
    entered state's inputs, as the prototype; refuse a condition reading untrusted data before
    an activity with an input policy; or leave conditions to inform and let rules decide (D7's
    teaching warning on "rules whose condition reads untrusted data"). To decide with
    `UNTRUSTED_TRIGGER` (layer 11), or earlier if case validation (layer 10) needs it. **Decided in
    layer 11a:** untrusted data informs, never decides; a condition that lets a step start counts
    as read by its inputs, and an untrusted approval condition asks anyway (D38). *Added in layer
    11b, 2026-10-18:* built for a case's steps, narrowed by D39 (only the condition's untrusted
    sources count, checked apart from the input's); a plan's own transitions are
    left open, recorded in `docs/layers/checkpoint-doors.md` for the checkpoint before layer 12.
18. **When does a run continue as new, and what does it carry?** (found in layer 6) Temporal
    warns at about 10,000 history events and ends a run at 51,200; continue-as-new ends a run and
    starts a fresh one with its state carried over. A plan doesn't need it yet: the bound of 1,000
    states without a wait keeps a loop on activities to about 6,000 events, and a loop through a
    wait needs a person's answer on every pass. A case does: it lives for weeks, with rules,
    timers and many tasks. What crosses over must be decided with the case's state in view: the
    case file and its sources, the count of entries per state (a count that restarts would repeat
    an idempotency key, which is why the key carries the run ID), the history so far, and answers
    sent during the switch. To decide in layer 8. **Decided in layer 8c:** D27.

## Prior art

Agentic Chartering (plans as checked data, which it calls Charters, and the trust model), CaMeL
(provenance), CMMN and Flowable (case concepts), Temporal (durable execution), AWS CDK and Pulumi
(code that produces checked artifacts), JsonLogic (operator names for expressions) and CEL (strict
types, errors instead of defaults). Serverless Workflow 1.0 was compared in the spike and not
adopted: our guarantees fall outside it (`docs/layers/spike-dsl.md`). The `chartering` prototype is
a TypeScript reference. See "Related work" in the README draft.
