# Ventoux

**Case management and human-in-the-loop workflows for Temporal.**

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](../LICENSE)
![Status: v0.1 alpha](https://img.shields.io/badge/status-v0.1%20alpha-orange)

Ventoux adds cases, approvals and human tasks to your existing [Temporal](https://temporal.io) server.
Definitions are data: reviewed in pull requests, checked before they run, changeable for open cases,
and safe for an AI to draft. Cases run as Temporal workflows on your server: there is no studio, no new
engine and no new database to operate.

Camunda and Flowable bring their own platform. Plain Temporal makes you build cases and human tasks
yourself. Ventoux adds them to your existing Temporal server.

- **Cases without flowcharts.** A case is a case file, milestones and rules for what may happen next.
  People, systems or an AI propose the next step; the engine admits or refuses it.
- **People in the loop.** Approvals by a second person, work routed to roles, deadlines that
  escalate, and held requests for sensitive changes.
- **Change running work safely.** Move open cases to a new definition with a checked, approved
  migration. Work in progress finishes under the rules it started with.
- **Checked before it runs.** Deadlocks, missing approvals and unsafe data flows are validation
  errors, caught in CI rather than in production.
- **Safe for AI to draft and assist.** A model can write a workflow or propose the next step, but
  untrusted content (an email, a model's output) can't reach a critical action, however it's worded.

> **Alpha.** The API and the definition format may change. Integrations are deterministic mocks today
> (see [Status](#status-of-the-prototype)).

---

## A case in one file

The Case below is a trimmed version of the prototype's
[`examples/cases/insurance-claim`](https://github.com/francoisnyc/chartering/tree/main/examples/cases/insurance-claim), and it validates as
written. Each *fragment* is a unit of work (a *plan*, described under
[How it works](#how-it-works)) together with the rules for when it may run. No flowchart fixes the
order.

```json
{
  "schemaVersion": 1,
  "id": "claim",
  "version": 1,
  "file": {
    "claimId": "string", "threadId": "string", "policyId": "string",
    "estimatedDamage": "number", "decision": "string", "payout": "number"
  },
  "milestones": ["facts_extracted", "assessed", "paid"],
  "fragments": {
    "intake": {
      "charter": "claim-intake@1",
      "activation": "automatic",
      "params": { "threadId": "file.threadId" },
      "produces": "facts_extracted",
      "update": { "estimatedDamage": "result.facts.estimatedDamage" }
    },
    "assess": {
      "charter": "claim-assess@1",
      "requires": ["facts_extracted"],
      "params": { "claimId": "file.claimId", "estimatedDamage": "file.estimatedDamage" },
      "produces": "assessed",
      "update": {
        "decision": "result.signal.name = 'ASSESSED' ? 'approved' : 'denied'",
        "payout": "result.signal.name = 'ASSESSED' ? result.signal.payload.amount : 0"
      }
    },
    "pay": {
      "charter": "claim-pay@1",
      "requires": ["assessed"],
      "allowedWhen": "file.decision = 'approved' and file.payout > 0",
      "approval": { "requiredWhen": "file.payout > 1000", "reason": "payouts over 1000 need a human sign-off" },
      "params": { "claimId": "file.claimId", "policyId": "file.policyId", "amount": "file.payout" },
      "produces": "paid"
    }
  },
  "work": { "fragments": { "assess": { "roles": ["adjuster"] } }, "approvers": ["adjuster"] },
  "closable": { "anyOf": [["paid"]] }
}
```

Validation runs in CI, like any other check. It also reports where every case-file value can come
from:

```console
$ npm run charter -- case validate claim.json --charters examples/cases/insurance-claim/charters
✓ claim.json is valid (3 fragments, no structural deadlock)
  file.estimatedDamage: UNTRUSTED [trusted:case-open, untrusted:llm]
  file.payout: trusted [trusted:case-open, trusted:signal]
  ...
```

`estimatedDamage` was extracted by an LLM, so it is untrusted. `payout` comes from the adjuster's
response, so the payment can depend on it.

Change `assess` to also require `paid`, and the Case is rejected before it is deployed:

```console
✗ claim.json has 2 error(s):
  ✗ fragments [DEADLOCK] after milestones [facts_extracted] no fragment can run and the case cannot be closed
  ✗ closable [NEVER_CLOSABLE] no reachable set of milestones lets the case close
```

## People in the loop

- **Approvals are enforced, not conventional.** A fragment's `approval.requiredWhen` needs a human
  other than the proposer. A high-risk activity can't be reached without an `APPROVED` step on every
  path, and one approval can't unlock two high-risk actions.
- **Human tasks** are wait states in a plan (`ASSESSED` or `DENIED`, `CLEARED` or `FLAGGED`), with
  optional timeouts. The response's payload is written to the case file, tagged as a person's input.
- **Work is routed** to roles or a named assignee. Worklists are derived from case state across
  cases: tasks to answer, proposals to approve, values to confirm, requests to review.
- **Sensitive changes are held for a second person:** case-file edits marked for approval,
  migrations, unplanned work and restarts. The requester can't approve their own request.
- **Deadlines escalate.** A case-level SLA ("assess within 5 days") can reach a milestone and start an
  escalation when it is breached.
- **A development inbox** (`npm run demo:inbox`) shows each person their work and signs their
  actions. Production UIs are yours to build on the same APIs.

## Changing work that is already running

In workflow code or a BPMN diagram, a running instance has a position in a graph. Changing the
process means versioning the code, migrating each instance to a new position, or letting old
instances finish on old logic.

A Case has no position. Its state is its case file, its milestones and its history. Fragments carry
admission rules rather than "next" arrows. So when you publish a new version of a Case definition:

- **New rules apply to current state.** Open cases are evaluated under the new rules from the moment
  they move, and milestones already reached stay reached.
- **Running work finishes where it started.** Each running fragment completes under the definition
  it began with. A move is refused only if a running fragment's result would have nowhere to go.
- **Moves are checked first.** The new version must validate, and it must have no deadlock
  reachable from the case's *current* milestones. You can preview a move across every open case of
  a type before anything changes.
- **Moves are held for a second person.** One person requests the migration, another approves it,
  and the case records every attempt.

`npm run demo:migration` shows this with three open claims. Version 2 adds a fraud check before
payouts:

```console
== Migrate the cohort: adjuster-1 requests, adjuster-2 approves ==
  CLM-1: now on insurance-claim@2 (assess keeps running under the rules it started with)
  CLM-2: now on insurance-claim@2
  CLM-3: now on insurance-claim@2

== After the move ==
  CLM-1: the assessment started under version 1 finishes: payout 1800, milestones [facts_extracted, assessed]
  CLM-1: pay is refused: requires milestone(s) fraud_checked
  CLM-3: pay is refused: requires milestone(s) fraud_checked
  CLM-3: the fraud team clears it: milestones [facts_extracted, assessed, fraud_checked]
  CLM-3: pay admitted (payout over 1000, approved by human:adjuster-2): payment payment-1, ...
```

The request names the new definition and a reason, and nothing else. Only renames need a mapping:
had version 2 also renamed `payout`, the preview would have refused the claims whose running work or
case file still use the old name, until the rename was mapped. A migration maps names, not positions.

Plans are the exception: a running plan is a small graph with a position, and it stays on its
version. That's also what gives an approval its meaning, since the approver signed that exact
content. The validator warns when a plan grows past a few states or waits on people more than
twice, so long-running steps stay in the Case, where they can change.

## Safe for AI to draft and assist

AI enters case work in two ways: drafting workflows, and proposing what to do next. Ventoux lets it
do both for **critical tasks**, actions that are costly, irreversible or regulated, such as paying a
claim, changing access rights or sending a regulated letter.
In short: **agents propose plans, Ventoux checks them, people approve.**

Ventoux doesn't make the model right. It makes the model's mistakes safe: a hallucinated tool, an
unsafe data flow or a missing approval is a validation error, not an action.

- **Data flow is checked on the plan, before it runs.** A plan that would let an LLM's output or
  an email choose a payment destination or a recipient is rejected at validation. The same check
  runs again before each activity is scheduled.
- **The guarantee carries through a whole case:** across fragments, human edits and days of waiting.
- **The model picks the step, never the values.** An AI step advisor answers with a fragment name and
  nothing else. The fragment's inputs come from declared expressions over the case file, with their
  provenance. The step advisor does read case data, including untrusted values (marked as such), so an
  injection can still influence *which* fragment it proposes. It can't make an inadmissible fragment
  run, skip a required approval, or choose the values a fragment runs with.

Most platforms defend against prompt injection by judging content. Ventoux defends by tracking where
data came from: untrusted content can't reach a critical action, however it's worded.

### See it reject a prompt injection

`examples/injection-attempt.json` is a plan that drafts a reply to an email thread and lets an LLM
pick the recipient. The thread contains an instruction to send the reply to `attacker@evil.example`.

```console
$ npm run charter -- validate examples/injection-attempt.json
✗ examples/injection-attempt.json has 1 error(s):
  ✗ states.draft.input.to [SINK_POLICY] gmail.createDraft@1 input "to" must not be influenced by
    untrusted data, but value is influenced by untrusted source(s) untrusted:llm
```

Nothing in the engine special-cases this attack. Two general rules catch it:

- `llm.extract@1` output is always tagged `untrusted:llm`.
- The `to` input of `gmail.createDraft@1` has a `noUntrusted` sink policy.

If you skip the static check (`--skip-static`), the runtime check still blocks the draft before it is
scheduled. The safe variant, `examples/reply-to-sender.json`, takes the recipient from the trusted
sender header, and it validates and runs.

## How it works

There are two levels, and both are plain JSON. Nothing in a plan or a Case is ever `eval`ed or
imported.

**1. Plans: one task as a state machine.** Each state either calls a *registered activity*,
waits for a signal, or ends. Expressions are structured JSON with a short, fixed list of operators
(`{">": [{"var": "amount"}, 1000]}`). None of them reads the clock or randomness, so a run replays
exactly on Temporal, and a missing value is an error, never a quiet `false`. The example below is
still in the prototype's shape, with string paths (`"params.policyId"`); it will be rewritten in
the structured form when plans are built (layer 2).

```json
{
  "schemaVersion": 1,
  "id": "claim-pay",
  "version": 1,
  "params": { "claimId": "string", "policyId": "string", "amount": "number" },
  "initial": "get_policy",
  "states": {
    "get_policy": {
      "activity": "policies.get@1",
      "input": { "policyId": "params.policyId" },
      "resultAs": "policy",
      "on": { "DONE": "await_approval", "ERROR": "failed" }
    },
    "await_approval": {
      "wait": { "signals": ["APPROVED", "REJECTED"], "timeout": "48h" },
      "on": { "APPROVED": "pay", "REJECTED": "failed", "TIMEOUT": "failed" }
    },
    "pay": {
      "activity": "claims.pay@1",
      "input": { "claimId": "params.claimId", "amount": "params.amount", "destination": "policy.payoutAccount" },
      "on": { "DONE": "done", "ERROR": "failed" }
    },
    "done":   { "type": "final" },
    "failed": { "type": "final", "outcome": "failed" }
  }
}
```

A plan *references* capabilities (`claims.pay@1`) and never defines them. Activities are ordinary
code that you register and run as Temporal activities. Each one is classified by risk and declares
policies on its inputs: `claims.pay@1` only accepts a `destination` that comes from the policy
database, and it is high risk, so every path to it must pass an `APPROVED` signal first.

The interpreter (what Agentic Chartering calls the *Dispatcher*) re-validates a plan before
running it, and checks access and sink policies again before each activity is scheduled. Like code
mode (where a model writes a program that calls its tools), a plan keeps intermediate data out of
a model's context: results flow between steps inside the engine. Unlike code mode, nothing a model
wrote is executed, so there is no sandbox to trust.

**2. Cases: long-running work made of plans.** A Case declares a typed case file, milestones,
fragments with admission rules, events, sentries, deadlines and when it may close. On Temporal, a
case is a parent workflow and each fragment runs as a child workflow.

**Why data and not code?** Because data can be checked, rendered and changed in ways code can't:

- the validator proves properties before anything runs (approvals on every path, no deadlock, where
  each value comes from);
- `charter render` turns a plan into a plain-language sheet for its approver, including what it
  will never do;
- open cases can move to a new definition without mapping positions;
- an AI can draft it without anything it wrote being executed.

Arbitrary logic still lives in code, in the activities you register. Two items on the
[Roadmap](#roadmap-to-v10) bring the rest of the developer experience: a typed Python builder that
produces the definitions, and existing Temporal workflows as steps of a case.

## What the engine enforces

- **Static validation.** It checks the schema, that every referenced activity exists at the declared
  version, that every expression type-checks against the declared fields, that every state is
  reachable, and that the Case has no structural deadlock. Deadlocks that depend on guard values
  can't be decided statically, so they are detected at runtime.
- **Provenance tracking.** Every value carries the sources it was derived from. Sink policies are
  checked before an activity is scheduled, not after it runs.
- **Events are provenance sources too.** Each event a Case accepts declares its source and whether it
  is trusted. An untrusted event (an email, a chat message) can start work or be recorded in the case
  file, but it can't make a decision: a trigger may reach a milestone because a customer wrote, not
  because of what they wrote. The validator rejects rules that only untrusted content could satisfy.
  At runtime, a rule whose condition reads an untrusted case-file value waits until a person confirms
  the value.
- **Role-based access by risk level.** Roles cap the risk class of the activities they may use, and
  a deny rule always wins.
- **Separation of duties.** When a fragment's `approval.requiredWhen` holds, someone other than the
  proposer must approve it. Only a principal of kind `human` can approve.
- **Verified identities (optional).** Signals, approvals, edits and case starts can be bound to
  Ed25519-signed claims from an issuer you trust. Each claim is scoped to one workflow and one action,
  expires, and can be used once. Verification uses public keys only and replays deterministically.
  See [Trust model](#trust-model).
- **Draft, never send.** This is the default for anything that talks to people. The built-in email
  capability creates a draft for a person to review, and the catalog has no send activity.
- **Durable execution.** The same interpreter runs as a Temporal workflow, with `continueAsNew` for
  long cases and a read-only history query for following a run.
- **An audit trail of decisions, not just actions.** Every proposal records who made it (a person or
  an AI) and why it was admitted or refused. Every value records where it came from, and every
  approval binds to the exact content approved. Retention and export depend on your Temporal setup
  today (see [Roadmap](#roadmap-to-v10)).

## Trust model

Every approval and signal has to come from someone, and Ventoux supports two ways to establish who.

- **Trusted caller (the default).** The engine accepts the identity that the caller of Temporal
  asserts. Make your own backend the only path to Temporal: users sign in to it through SSO, and it
  connects to Temporal over mTLS. The backend then vouches for every identity. The workflow history
  records who the backend *said* acted.
- **Signed claims (production mode).** Configure the worker with trusted issuer keys, and each
  approval, signal and edit must carry an Ed25519-signed claim. Every claim is scoped to one workflow
  and one action, expires, and can be used once. The workflow verifies each claim itself, so the
  history *proves* who acted, and a caller that reaches Temporal without a valid claim can't approve
  anything. Today `charter identity keygen|sign` issues claims for development.

Ventoux doesn't provide SSO or mTLS itself; configure them in your deployment and in Temporal.

## Getting started

> Ventoux is being rebuilt in Python, the language of its first users (see the design brief). The
> commands and outputs in this README come from the TypeScript prototype it is based on, and will be
> replaced as each layer of the Python version lands. The prototype calls plans *Charters*, steps
> *fragments*, and the step advisor a *planner*.

The prototype requires Node 22 or later.

```sh
git clone https://github.com/<org>/ventoux && cd ventoux
npm install
npm test

npm run charter -- case validate examples/cases/insurance-claim/case.json --charters examples/cases/insurance-claim/charters
npm run demo:migration      # move three open claims to a new version
npm run demo:inbox          # dev Temporal server, a worker and a work inbox at http://127.0.0.1:8090/
npm run charter -- validate examples/injection-attempt.json   # rejected: SINK_POLICY
```

Runs use deterministic mocks over the fixture world in `examples/fixtures/world.json`. The Temporal
tests and the inbox demo download a Temporal dev server on first use.

See the prototype's [`docs/design.md`](https://github.com/francoisnyc/chartering/blob/main/docs/design.md) for the full architecture and
the security review.

## Status of the prototype

**Works today:** Plans and Cases in memory and on Temporal; static and runtime validation;
provenance and sink policies; role-based access; verified identities; milestones, sentries, triggers,
deadlines, unplanned (ad hoc) fragments and parallel fragments; approvals, routed worklists and
requests held for a second person; checked migration of open cases; an authoring loop in which a
model drafts plans that are validated and repaired; Mermaid and SVG diagrams; a development work
inbox.

**Not yet:** terminating a case early, required fragments, one fragment instance per item of a
collection, child cases and stages; claiming and reassigning tasks, and typed task responses; real
integrations (Gmail, Slack and payments are deterministic mocks); audit export; multi-tenancy; a
production UI.

## Roadmap to v1.0

- [ ] The engine in Python (Temporal Python SDK, Pydantic), with the definition format published as
      JSON Schema and a conformance suite any implementation must pass
- [ ] A typed Python builder that produces plans and Cases, so definitions are written as code and
      checked as data
- [ ] Existing Temporal workflows as case steps, each with a declared contract (inputs, outputs
      and their provenance, risk)
- [ ] Human tasks: named outcomes whose forms set case-file fields, approval defaults computed from
      provenance
- [ ] Task assignment: a person claims a task from a role's queue, or assigns or reassigns it to
      someone else; and assignment by rule, written in the definition
- [ ] Case lifecycle: closing when nothing is left to do, closing by a person with a declared
      reason, required steps, one step per collection item, child cases
- [ ] Case data: typed references shown through resolvers, sensitive fields encrypted per case,
      `ventoux forget`, facts with the time they were obtained and `max_age`
- [ ] More field types: a date, stored and compared; an option from a system's list, checked
      against that system when the answer is given; and a file attachment, a reference to a
      document store, uploaded from the inbox
- [ ] Failures: retry policies and idempotency in contracts, business failures as outcomes, a
      "needs attention" queue
- [ ] Audit export: an append-only copy of case and run events, with its own retention and
      sensitive values kept encrypted
- [ ] Security and utility results on the [AgentDojo](https://github.com/ethz-spylab/agentdojo)
      prompt-injection benchmark
- [ ] A published Python package and a `ventoux` CLI

Beyond v1.0, tracked as issues: stages, advanced joins (such as an inclusive join, waiting for
every branch that started), timers anchored to a date on the case, absolute and recurring timers,
suspend and reactivate, declared compensation (sagas), inbound event adapters, signed approvals (the
production default for high-risk steps), plans drafted by a model for a single case at runtime,
tamper-evident history, capture of model inputs and outputs, revising drafts in conversation, and
tool search during authoring.

Today a step's `requires` is an "all of these" join, and several steps reaching one milestone make
a "first of these" join. An inclusive join would wait for every branch that started and ignore the
ones that didn't; its design question is how case validation proves such a join is ever met, since
a branch that starts and never ends would hold the case open.

Timers anchored to a date on the case would build on the date field type (in v1.0) with a timer
before or after that date: "3 days before the renewal date", "on the appointment date". Today a
timer counts forward from a moment in the case (its opening, a milestone, a run's start, an answer,
an event's arrival). The design questions: where the date may come from, since a date from
untrusted data would decide when something happens; what a timer does when its date changes after
it is set; which time zone a day is read in; and a date already past when the timer would be set.

## Contributing

Contributions are welcome, especially:

- **Activities.** New registered capabilities, each with its risk class, input sink policies and
  output provenance. This is where real integrations belong.
- **Case features** from the roadmap, each with the validation rules that keep it checkable.
- **Validation.** New static checks, each with a plan or Case it must reject.
- **Docs and examples.**

Every change includes tests, including at least one negative test (a plan or Case that must be
rejected). Run the tests, the type checker and the linter before opening a PR.

## Related work

Ventoux combines ideas that others introduced. Here is where they come from and how Ventoux differs.

- **Agentic Chartering.** Adam Terlson,
  ["The Agentic Unlock"](https://www.bluefolders.ai/insights/the-agentic-unlock). The model writes a
  declarative state machine (a Charter), and a runtime decides whether it is admissible and runs it
  through registered activities. Ventoux takes its plan concept (their Charter) and its trust model
  from this work, and adds provenance checking and the Case layer.
- **CaMeL.** Debenedetti et al.,
  ["Defeating Prompt Injections by Design"](https://arxiv.org/abs/2503.18813). A privileged LLM
  writes a plan, a quarantined LLM handles untrusted data, and a custom interpreter tracks the
  provenance of every value. Ventoux's provenance model comes from CaMeL. The difference is that
  Ventoux also checks provenance statically, on a JSON plan, before execution.
- **Case and process platforms.** [Camunda](https://docs.camunda.io/docs/components/agentic-orchestration/ai-agents/),
  [Flowable](https://documentation.flowable.com/latest/ai/ai-orchestration) and Pega offer BPMN and
  CMMN with task management, forms and UIs, and let AI agents act inside processes and cases. Ventoux
  borrows CMMN's ideas (milestones, sentries, discretionary work) but runs on your Temporal instead of
  its own platform. Their AI guardrails judge content; Ventoux tracks where data came from. In
  Camunda's AI agent the model also chooses the tool's parameters; in Ventoux the case file supplies
  them.
- **Developer-first orchestration.** [Orkes Conductor](https://orkes.io/compare/orkes-conductor-vs-camunda-bpmn)
  offers human tasks on its own engine. [Zigflow](https://github.com/mrsimonemms/zigflow) compiles a
  declarative DSL to Temporal workflows, without cases or human task management.
- **Human tasks on Temporal.** [KuFlow](https://docs.kuflow.com/developers/client-integration-temporal)
  is a hosted platform that adds human tasks, forms, a task UI and access control to Temporal
  workflows written as code, on a Temporal cluster it runs. Ventoux is a library on your own Temporal,
  and adds case semantics and definitions that are checked as data.
- **Agentic case management notations.** [ACMN](https://acmnstandard.org/), an April 2026 working
  draft, extends CMMN with AI agents as case participants, governed by guardrails, tool policies and
  confidence thresholds. Ventoux keeps AI as a proposer, governed by data provenance rather than by
  judging its output.
- **Workflows as JSON state machines.** AWS Step Functions and the
  [Serverless Workflow](https://serverlessworkflow.io/) specification run declarative state machines
  through registered tasks. A plan has the same shape, and a model can write it.
- **Plan-then-execute agents.** ReWOO and LLMCompiler generate the whole plan up front and then
  execute it. They do this to save model calls, not to check the plan.
- **Plans as contracts.** The [Agentic Contract Model](https://github.com/ddse-foundation/acm) (ACM)
  versions LLM-generated plans as contracts and records replay bundles of every run. Its policies run
  at runtime, and its provenance describes the planning context, not where each value came from.
- **Runtime policy enforcement.** Microsoft's
  [FIDES](https://devblogs.microsoft.com/agent-framework/fides/),
  [AgentFlow](https://arxiv.org/abs/2608.22868), [Progent](https://arxiv.org/abs/2504.11703) and
  Amazon Bedrock AgentCore Policy check labels or rules as each tool call happens. Ventoux runs the
  same kind of check at runtime, as a second line of defense behind the static one.
- **Static checks on agent workflows.** [Agentproof](https://arxiv.org/abs/2603.20356) checks the
  structure of LangGraph, CrewAI, AutoGen and ADK graphs (dead ends, missing human gates) before
  deployment. Ventoux checks structure too, and adds data flow.
- **Durable execution.** [Temporal](https://temporal.io) provides the replay, timers and history that
  Ventoux runs on.

## License

MIT. See [LICENSE](../LICENSE).
