# Ventoux — design brief

Status: draft, 2026-10-03; all design questions decided (D1–D19). Read this first; it is the short
version of what we are building and why. The longer reference is `docs/design.md` in the
`chartering` prototype.

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
| **Platform team** (a few people) | Registers activities, workflows and resolvers, sets policies, runs releases and operations | contract (with retry policy and idempotency), deployment binding, risk, sink policy, source labels, resolver, key provider, release, activation, needs attention |
| **Analyst / business owner** | Reads, proposes and approves changes | case map, rules sheet, plain-language diff |

**Progressive disclosure.** Advanced concepts have defaults, so people meet them only when needed:
- locally and in staging, releasing and activating are automatic; in production they are
  deliberate;
- one folder is one package;
- the registry ships with example activities and sensible policies;
- identity is the trusted-caller model, with the engine reachable only through the Ventoux API (D19);
- provenance and sink policies are set by the platform team on each activity; developers meet
  them only through validator errors, and every error says what was wrong, why, and what to do
  instead.

The quickstart (`QUICKSTART.md`) is the running test of this principle.

## Six ideas the whole design rests on

1. **Definitions are data.** Plans and case definitions are JSON. Nothing in them is ever executed
   as code: no `eval`, no imports. Because they are data, they can be validated, rendered for people,
   compared between versions, migrated, and written by an AI.
2. **Capabilities live in a registry.** Definitions *reference* activities (`claims.pay@1`); they
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

### D3. Expressions are a small JSONata subset

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
  the Temporal Python SDK (its workflow sandbox helps catch non-determinism), and `jsonata-python`, a
  native port of the JSONata reference implementation.
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
- It is described by a **workflow contract** in the registry: name and version, input and output
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
  The registry refuses a side-effecting contract without one. An adapter that receives "duplicate
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
| Registry | What a deployment allows: activity and workflow contracts, resolvers, roles and source labels |
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
| Sink policy | A rule on an activity input: which sources may influence it |
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
core         schema · expressions · registry · provenance · validation · interpreter (pure)
```

`core` and `case` stay free of Temporal and LLM dependencies, so they run in memory, in tests and
inside a Temporal workflow alike.

## Non-negotiables

- Definitions are data. Never `eval`, `exec`, `compile`, import or unpickle anything from them.
- Expressions are pure and deterministic, limited to the subset in D3.
- Every side effect goes through a registered activity.
- The interpreter is deterministic, so it runs as a Temporal workflow and survives replay.
- Every value carries provenance; sink policies are checked before an activity is scheduled.
- Anything that talks to people drafts by default; it never sends on its own.
- Policies can be made stricter, never looser, by anyone downstream: a case can tighten a contract's
  retry policy or freshness, untrusted data can add an approval, a view can hide more than the
  source system; none of them can loosen.
- Nothing is skipped automatically: a failed step waits for a person (D17).
- Every feature ships with tests, including at least one negative test (a definition that must be
  rejected).

## Out of scope for v1.0

A visual editor, a polished production UI (v1.0 ships the API and a reference inbox, which draws
task forms from field types; there is no form designer), broker connectors, BPMN or CMMN import,
multi-tenancy, code inside definitions (scripts, listeners), and the deferred features listed above.

## Design questions (all decided)

1. JSON or code first: D1.
2. Expressions: D3, with CEL compared in the spike.
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
    including the error code (`SINK_POLICY` or `INPUT_POLICY`).
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
    marked `# TRACER: layer 2`, which commits to neither.
12. **Who has which role in `run_case`?** (found in the tracer bullet) The quickstart's tests name
    people (`"ana"`) but never say where their roles come from. The tracer uses a fixed directory
    (`ana`: support; `sam`: support, support-lead). To decide in layer 7: roles passed to
    `run_case`, a test directory, or roles carried with each answer.
13. **How is an approval answered?** (found in the tracer bullet) The quickstart never answers an
    approval in a test, so its shape is undefined. The tracer answers it by naming the step:
    `("pay", "approve", "sam")`. To decide in layer 7, with D11 (an approval is a task with
    *approve* and *reject*).
14. **What running the quickstart taught us.** (found in the tracer bullet)
    - *Fixed:* the large-refund test asserted only `waiting_for`, not that nothing was paid and
      the case stayed open, which is what matters most. The quickstart now asserts all three.
    - *Open:* a case waiting for a *task* has no defined report. The quickstart only shows waiting
      for an approval, and the tracer crashes when no one has answered the review. Proposal:
      `waiting_for` lists open tasks too (`"review by support"`). To decide in layer 8, with
      pending work (D10).
    - *Open:* the quickstart's story (Ana reviews, Sam approves) never shows the D11 exclusion,
      because Ana isn't a team lead anyway. Only a reviewer who is also a team lead shows it
      (learning question 18). Proposal: the quickstart's "When Ventoux says no" adds Sam
      reviewing and then trying to approve, refused with the reason.
    - *Open:* reading a field nobody set fails at runtime (a rejected review leaves
      `approved_amount` unset, and the tracer only avoids reading it because `pay` doesn't run).
      D9 already asks the validator to warn about conditions on answers that may not exist; to
      check in layer 3 that this covers inputs too.

## Prior art

Agentic Chartering (plans as checked data, which it calls Charters, and the trust model), CaMeL
(provenance), CMMN and Flowable (case concepts), Temporal (durable execution), AWS CDK and Pulumi
(code that produces checked artifacts), `jsonata-python` (expressions). The `chartering` prototype
is a TypeScript reference. See "Related work" in the README draft.
