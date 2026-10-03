# Learning log

Check-yourself questions from the design sessions. Answer in your own words first; then we discuss
and record the key points. A question is closed once you can explain the answer without notes.

| # | Topic | Status |
|---|---|---|
| 1 | D1: JSON or code first | open |
| 2 | Design principles | open |
| 3 | Intuitive and shared | open |
| 4 | Simplifications: one rule type | closed |
| 5 | D2: structured to case | open |
| 6 | Why not an existing DSL | closed |
| 7 | D3: expressions | open |
| 8 | Engine language | open |
| 9 | D4: Python engine | open |
| 10 | Versions (pending D5) | closed |
| 11 | Behaviour vs wording | open |
| 12 | Releases | closed |
| 13 | Workflow steps | closed |
| 14 | Quickstart: approvals | open |
| 15 | Case data | closed |
| 16 | D9: task outcomes | closed |
| 17 | D10: closing | closed |
| 18 | D11: approval defaults | closed |
| 19 | D12: sources | closed |
| 20 | D13: kinds of step | closed |
| 21 | D15: forgetting | closed |
| 22 | D16: references and resolvers | closed |
| 23 | D18: fresh facts | closed |
| 24 | D17: failures | closed |
| 25 | D19: identities | closed |
| 26 | Layer 0: core inside a workflow | open |

---

## 1. D1: JSON or code first

> An AI drafts a new case definition. A developer then wants to change one rule in it. What happens
> if code is the only way people edit definitions? And what if JSON is the contract?

- Your answer:
- Discussion:

## 2. Design principles

> A developer asks a coding assistant to "require two approvals above 10,000". List what the
> developer and the reviewer see before it ships: the code diff, then what else?

- Your answer:
- Discussion:

## 3. Intuitive and shared

> An analyst reads the case map and thinks the fraud check should happen before the assessment, not
> after. Walk through what happens, from her comment to the change running. Who sees what at each
> step?

- Your answer:
- Discussion:

## 4. Simplifications: one rule type

> Write "if the assessment isn't done within 5 days, escalate to a senior adjuster" as a single rule.
> What goes in *when*, *if* and *then*?

- Your answer: when assessment starts, if not assessed after 5 days, then escalate.
- Discussion: the three parts are right; the 5 days belong to *when* (the moment the rule fires:
  5 days after `assess` started), not to *if*. *If* is checked when the rule fires: `assessed` not
  reached. *Then*: start `escalate` and reach `escalated`. If the assessment is done on day 3, the
  timer still fires on day 5, the condition is false, and nothing happens. Findings: rules need a
  "step started" event, and the Python builder can't use `if=` (reserved word); `unless=` reads better.
- Follow-up: the assessment starts on Monday, is done on Wednesday, and a new fact reopens it on
  Thursday, so `assess` starts again. When should the clock fire, and what should the rule check?
  Answer: the clock should restart (5 days from Thursday's start), and the rule checks that
  `assessed` was not reached since that start. This led to decision D7: the `sla` pattern measures
  from the latest start by default, and `ventoux simulate` shows it on a timeline.
- Status: closed.

## 5. D2: structured to case

> An invoice approval starts strict: capture → check → approve → pay. Six months later, finance wants
> to allow "request more information from the supplier" at any time before approval, and to skip
> "check" for invoices under 100. Which rules change, and what happens to the invoices currently
> waiting for approval?

- Your answer:
- Discussion:

## 6. Why not an existing DSL

> Why would adopting Serverless Workflow as is fail principle 3 (AI-friendly) for a runtime AI, even
> though it's JSON?

- Your answer: its `run` tasks can execute scripts, so AI output could run code.
- Discussion: right, and that's the core reason. Two more: `call` tasks can reach any HTTP endpoint,
  not only registered capabilities, so side effects escape the registry; and the format has no
  provenance or sink policies, so even without scripts an AI's output could route untrusted data
  anywhere. The lesson: for a runtime AI, unsafe things must be impossible to express in the format
  (safe by construction), not merely forbidden by a policy on top of a larger language (safe by
  restriction), which is easy to get wrong and hard to explain.
- Status: closed.

## 7. D3: expressions

> Finance wants a rule: "require a second approval if the total of all high-risk line items exceeds
> 10,000". Where does the logic for "total of high-risk items" live, and why is that better for the
> reviewer than one long expression?

- Your answer:
- Discussion:

## 8. Engine language

> If Ventoux is a standalone worker running cases, and your activities are written in Java, which
> parts of the system does a Java developer need to read to change a workflow, and which can they
> ignore?

- Your answer:
- Discussion:

## 9. D4: Python engine

> A teammate writes an activity in Java that computes a risk score, and another in Python that sends
> a draft letter. The engine is in Python. What does each activity declare in the registry, and does
> the Java developer ever need to read Python code?

- Your answer (layer 0 warm-up): a contract with schemas, risk and a task queue; no.
- Discussion: schemas and risk are right, and "no" is right. Two corrections. First, the task queue
  is not in the contract: the contract says *what* is promised, and a deployment binding per
  environment says *where* it runs (D5). Moving the scorer to another queue is an operations change
  and needs no new contract version. Second, the contract holds more than schemas and risk:
  `name@version`, the effect, sink policies on inputs, the provenance of each output, the retry
  policy and timeouts, idempotency, and declared failure outcomes (D17). The two activities differ
  on several of these. The risk score is `effect: compute`, so it needs no idempotency key, and the
  platform team declares its output as trusted. The draft letter has a side effect (it creates a
  draft), so it declares an idempotency key. It is low risk because it only drafts and never sends.
  On "no": the Java worker and the Python engine meet only through the contract (published as JSON
  Schema) and a Temporal task queue. The Java developer reads the contract and the JSON definition,
  never the engine. One gap to keep in mind: activation needs every worker to publish a manifest
  (D5), so a Java worker needs a small Ventoux library or an equivalent.
- Follow-up: the platform team moves the risk scorer from the `risk` task queue to `risk-v2` in
  production, without changing its code. What changes in the registry, and does it create a new
  contract version or a release?
  Answer: not sure. Discussion: only the production deployment binding changes (activity name and
  task queue). The contract is untouched, so its hash is unchanged: no new version, nothing for
  packages to adopt, and no release, because a release records which contracts a package needs,
  not where they run. What protects the move is activation and its runtime backstops: workers on
  `risk-v2` must publish a manifest serving `risk.score@1` with the same hash, and an activity
  nobody picks up fails loudly on its schedule-to-start timeout. Keep the question open until you
  can explain "what vs where" without notes.
- Status: open.

## 10. Versions

> A developer fixes a typo in a step's business title (no rule changes) and merges it. Does that
> create a new release? Should open cases migrate to it? What does the semantic diff say?

- Your answer: no new release, it's just a label change.
- Discussion: correct. It led to splitting every definition into behaviour (what the engine can do
  or decide) and presentation (what people read), with presentation in explicit `display` blocks.
  The release digest covers everything outside `display`, so the typo fix creates no release and
  nothing migrates; the new wording shows on running cases at once. The semantic diff lists it under
  "Wording changes (no release)". Subtleties: a literal text passed to an activity is behaviour, not
  wording; and because wording can mislead, it is still reviewed, approval sheets show generated text
  next to labels, and the audit log records which wording an approver saw.
- Status: closed.

## 11. Behaviour vs wording

> A step drafts a customer letter through `letters.draft@1`, with the opening sentence passed as a
> literal input: `"intro": "'Dear customer, we are pleased to confirm…'"`. Marketing wants "pleased"
> changed to "happy". Release or no release, and why? What would you change in the definition so that
> wording like this becomes presentation next time, without weakening any guarantee?

- Your answer:
- Discussion:

## 12. Releases

> Release 12 adds a step that uses a new activity, `fraud.check@1`. It is merged and published, but
> the production workers don't serve `fraud.check@1` yet. What happens when someone runs
> `ventoux activate insurance-claim 12 --env production`, and what happens to claims that are
> already open on release 11?

- Your answer: a) refused, because workers don't serve it; b) they stay on release 11. And: how can
  Ventoux check that concretely?
- Discussion: both right. Temporal knows which workers poll a task queue, not which types they
  serve, so Ventoux workers publish a manifest at startup (contracts served, with hashes) to an
  environment registry (a Temporal workflow per environment). Activation checks the binding, the
  served contract hash and live pollers, and refuses with an explanation. It's a point-in-time
  check, backed at runtime by schedule-to-start timeouts and monitoring. Recorded in D5.
- Status: closed.

## 13. Workflow steps

> The KYC team's Java workflow returns `{ status, riskScore, analystNotes }`, where `analystNotes` is
> a summary written by an LLM from customer documents. Your case has a rule: "if `riskScore > 70`,
> require a second approval before onboarding". What should the contract declare for each output,
> what happens if someone forgets to declare `riskScore`'s provenance, and could `analystNotes` ever
> be used to decide anything?

- Your answer: a) the KYC team; b) untrusted, a human in the loop; c) yes, but only when passed as an
  input to a Charter that can do something with it.
- Discussion: b is right: undeclared output provenance is untrusted (fail safe), so a rule reading
  `riskScore` waits for a person to confirm the value; untrusted data may make things stricter (require
  the approval), never looser. a needs sharpening: `status` and `riskScore` can be trusted
  (`trusted:kyc-provider`, `trusted:kyc-scoring`), but `analystNotes` must be `untrusted:llm`:
  provenance is about where the content comes from, not which team returns it. c: it can never
  decide (start a step, skip an approval, reach a milestone, appear in a condition), but it can be
  used where inputs accept untrusted data: shown to the approver as context, or passed into a draft
  a person reviews. Untrusted data can inform people and drafts; it can never decide or act.
- Follow-up: the KYC team wants to declare `analystNotes` as `trusted:kyc-team` "because our workflow
  produced it". What do you reply?
  Answer: it's LLM content, so it stays untrusted whoever returns it.
- Status: closed.

## 14. Quickstart: approvals

> In the quickstart, the reviewer approves a 250 refund. Which person can approve the payment, and
> who can't? What does the case wait for at that moment, and what would a test assert?

- Your answer:
- Discussion:

## 15. Case data

> A claim's rules need the customer's age (claims for people over 75 get a special review), and the
> denial letter needs the customer's postal address. Which of the two goes in the case file, which
> is fetched by a step, and what happens if the customer later asks to be forgotten?

- Your answer: a) age goes into the case file; b) the postal address, and the age, can be fetched
  using an ID; c) not sure.
- Discussion: a is right: a rule reads it, so it's a fact, and a sensitive one (store the birth date
  so the "over 75" rule stays visible in the definition, rather than a hidden `over_75` flag). b is
  right with a distinction: the address is fetched by the letter activity when it runs and never
  stored; the age is fetched once by a lookup step and stored as a sensitive fact, because rules
  can't fetch anything: they only read the case file. c: the address was never in Ventoux, so the
  CRM erases it and the reference points to nothing; the birth date was encrypted with the case's
  key, and `ventoux forget` destroys the key, making every copy unreadable. The history still shows
  the decisions (the rule fired, who reviewed, outcomes, approvals, when), but not the value: the
  audit trail survives erasure.
- Follow-up: after the customer is forgotten, an auditor asks why claim CLM-7 got a special review.
  What can you show, and what can't you?
  Answer: that the rule fired and who reviewed, but not the birth date. (Also showable: which
  release and rule applied, when, the outcome and the approvals.)
- Status: closed.

## 16. Task outcomes

> The customer asks for 80. The reviewer, Ana, approves but enters 250 as `approved_amount`. a) Where
> does 250 live, and who is it trusted as coming from? b) The payment's approval rule says
> `when=amount > 100`. Is the team lead asked? Should they be? c) Which field should the approval
> rule read?

- Your answer: a) in a case-file field, trusted as a human review; b) no, it's a different field;
  c) from the case file, always.
- Discussion: a is right, and precisely: `approved_amount` is tagged with who answered (Ana, role
  `support`) and when. b is right, and it's the trap: `amount` is 80, so no team lead is asked, yet
  250 is paid. c is true but not enough, since both fields are in the case file. The rule is: **an
  approval guards the value its step actually uses**. `pay` sends `approved_amount`, so the approval
  must read `approved_amount > 100`. The validator now warns when an approval's condition reads
  none of the fields its step uses. Recorded in D9, and the quickstart was corrected.
- Follow-up: should Ana be allowed to approve more than the customer asked for? Where would that
  limit live: in the form, in a rule, or in the activity's contract?
- Status: closed.

## 17. Closing

> Finance adds: "30 days after the refund is paid, draft a satisfaction survey." a) When does a paid
> refund close? b) A rejected refund never sets that timer: when does it close? c) Agents want a
> "close as duplicate" button: what covers it, and what happens to a task still open for Sam?

- Your answer: a) after 30 days, because the timer is part of the case now; b) when it is rejected;
  c) `stays_open=True`. Also: "quiet" is a strange term.
- Discussion: a is right: a set timer is pending work, so the case stays open until the survey is
  drafted (if that's unwanted, `closes_when=paid` closes it at payment and cancels the timer). b is
  right: once the rejection is recorded, nothing is left to do (with the rejection-letter step from
  quickstart section 7, it closes once the draft is done). c: `stays_open` would make every refund
  need a manual close. A person closing a case early is a separate, declared action,
  `close_reason("duplicate", roles=[...])`: Sam's open approval is cancelled and his inbox says
  why. On "quiet": agreed, dropped. The rule is now "closes when nothing is left to do", and the
  things that keep it open are called pending work.
- Follow-up: a case is closed as a duplicate while the `pay` activity is already running. What
  should happen to the payment?
  Answer: the payment finishes, then the case closes. Right: a running side effect can't be safely
  cut off. So a close puts the case in *closing* (no new steps, tasks cancelled, running activities
  finish), then *closed*. The catch: for a duplicate, that payment is itself a duplicate, so the
  closed case is flagged "pay completed after the close was requested" and a person decides on a
  reversal; Ana is warned before confirming. Recorded in D10.
- Status: closed.

## 18. Approval defaults

> Sam (team lead, also `support`) reviews a refund himself and approves 250. a) Can he approve the
> payment, and what does the engine look at? b) Ana edits the refund's reason, which `pay` doesn't
> use: is she excluded? c) Sam approves, then `approved_amount` is corrected to 200: still approved?

- Your answer: a) no, he reviewed it; b) no; c) no, it needs a new approval.
- Discussion: all right. a, precisely: the engine doesn't look at "who reviewed" but at the
  provenance of what `pay` uses: `approved_amount` is tagged with Sam's answer, and `pay` only runs
  because of his *approve* (the `when=` condition). Both exclude him. b: her edit doesn't flow into
  `pay`, so it excludes no one. c: the approval recorded a digest of the inputs; any change voids
  it, even a lower amount, because "smaller is fine" exceptions make the rule hard to explain.
  Recorded in D11.
- Follow-up: Sam is the only `support-lead`, and he reviewed this refund. What happens, and what
  should the inbox show?
- Status: closed.

## 19. Sources

> A developer declares `customer_amount` with `source="trusted:customer-portal"` to skip the review
> for small refunds. a) What does `ventoux check` say? b) The portal is a company system: what's the
> legitimate way to get a trusted value from it, and who agrees? c) Is the amount the customer typed
> in the portal trusted?

- Your answer: a) rejected; b) a platform team contract; c) no, the customer typed it.
- Discussion: all right. a: fields can be declared untrusted, never trusted. b: the platform team
  registers an activity (say `portal.get_request@1`) whose contract declares provenance per output
  field: `order_total` from the orders system is trusted, `requested_amount` is
  `untrusted:customer`. c: the same lesson as question 13: provenance follows the content, not the
  messenger. Recorded in D12.
- Follow-up: finance really does want refunds under 20 paid without review, even from the
  customer's own amount. Untrusted data can't decide... so how could the platform team allow it
  without weakening any guarantee? (Hint: what if the activity itself can't pay more than 20?)
- Status: closed.

## 20. Kinds of step

> Pick the kind of step: a) sanctions check, then an analyst decides on a match, then scoring;
> compliance wants to see and change each part. b) An existing Java Temporal workflow for OCR.
> c) An AI proposes, per claim, a plan to collect missing evidence, approved by an adjuster.

- Your answer: a) task steps; b) workflow; c) charter.
- Discussion: a, more precisely: three case steps of two kinds, an `activity` (sanctions), a `task`
  (the analyst, only when there's a match) and an `activity` (scoring), joined by rules, because the
  business wants to see and change each one. b: right, the logic already exists as Temporal code.
  c: right, it must be data so the validator can prove what the AI's plan can and can't do before
  the adjuster approves it. Caveat: a plan drafted per case at runtime is the ad hoc inline plan,
  deferred until after v1.0; in v1.0 the AI can only choose among registered plans. Recorded in
  D13.
- Status: closed.

## 21. Forgetting

> A customer asks to be forgotten while their claim is open, waiting for an assessor. a) Why can't
> `ventoux forget` destroy the key right now? b) What should happen instead? c) Last quarter's
> export includes this claim: what does the warehouse hold for the birth date?

- Your answer: a) determinism; b) wait for what's in progress to finish; c) it holds the value, not
  sure.
- Discussion: a, precisely: **replay**. Temporal rebuilds an open case by replaying its history, and
  without the key the birth date can't be decoded, so the case breaks on the next worker restart.
  Replay exists because of determinism, but the failure is unreadable history, not changed code.
  b: partly. Waiting for running work is right (D10), but someone must first decide: erasure can
  conflict with legal retention, so `forget` is a change request approved by a data protection role,
  which closes the case ("forgotten"), lets running activities finish, then destroys the key.
  c: that's the trap: if the warehouse held the plain value, destroying the key would forget
  nothing. The export carries ciphertext under the same case key, so it becomes unreadable too.
  Recorded in D15.
- Follow-up: finance's quarterly report shows the average age of claimants. After ten customers
  are forgotten, what happens to the report, and is that acceptable?
- Status: closed.

## 22. References and resolvers

> The `crm` resolver returns a customer's name, address and phone for the inbox. a) Should it be a
> registered activity? b) Does anything it returns enter the case file or history? c) An adjuster
> without the `claims-sensitive` role opens the case: who decides which fields they see?

- Your answer: a) no, because it doesn't affect the case; b) no; c) Ventoux.
- Discussion: a is right: it's read-only and runs in the inbox, outside the workflow, so it needs no
  history or determinism; but it is still *registered* by the platform team, never defined in a
  case. b is right, with a consequence: the audit can't show what the adjuster saw, only that the
  record was shown. If a value matters to the decision, it must become a fact. c: mostly the CRM.
  Whoever holds the data decides: the resolver calls the CRM on behalf of the viewer, so the CRM's
  own permissions apply, and Ventoux may hide more but never show more. A second permission model
  in Ventoux would drift from the CRM's. Ventoux does decide for sensitive fields in its own case
  file. Recorded in D16.
- Status: closed.

## 23. When a fact was obtained

> A claim's `policy_status` is fetched as "active" when the claim opens. Three weeks later the
> payment is ready to run; the policy was cancelled last week. a) What does the case file say, and
> why is that a risk? b) What would you want to write in the definition to prevent it (something
> like `max_age=`)? c) Who should be able to see that the payment relied on a three-week-old status?

- Your answer: a) it says active, which is stale; b) `max_age` on the input; c) the auditor.
- Discussion: a is right: the case file is a snapshot (D8), "active as of three weeks ago", and the
  payment would go out on a cancelled policy. b is right, and placed well: freshness belongs where a
  fact is used, not on the field (a week-old status is fine for a letter). It covers the step's
  condition and approval too, not only inputs. And rather than failing, the engine refreshes: the
  fact's provenance says which step fetched it, so if that step is read-only it runs again, and the
  condition is re-checked with the new value. c: the auditor, after the fact, but first the
  *approver*: the approval sheet shows each fact's age, so the person who can still stop the payment
  sees it. Recorded in D18.
- Status: closed.

## 24. Failures

> The payment times out after the provider took the money; Temporal retries three times and the
> third attempt returns "duplicate request". a) Why wasn't it paid three times? b) Is "duplicate
> request" a failure or a success? c) Who decides the retry policy, and why not the case developer?

- Your answer: a) the idempotency key; b) success, continue; c) the platform team.
- Discussion: all right. a: the key is built from the case, the step and the step's run, so every
  retry carries the same key (Temporal's attempt number would defeat it). b: a success, provided the
  adapter returns the *original* result (the existing payment's ID), so the case records the real
  payment rather than a bare "ok". c: the platform team knows the system's limits (rate limits,
  outages, its own SLA), and one policy then applies to every case; a case developer could hammer
  the provider or give up too soon. A case may tighten it, never loosen it. Recorded in D17.
- Status: closed.

## 25. Identities

> In v1.0 (trusted caller), a developer with Temporal CLI access to production signals "approve
> `pay` on CLM-7, from sam". a) What does the engine do? b) Without signatures, how does the platform
> team prevent it? c) With signatures, what could that developer still do?

- Your answer: a) accepts it; b) mTLS so only the inbox can signal; c) not sure.
- Discussion: a is right, and that's the weakness: the engine believes the caller. b is right: mTLS
  plus Temporal's authorization, so only the Ventoux API's service identity can write, and people
  get read-only access. c: a lot. Terminate cases, *reset* a case to an earlier point (re-running a
  payment as a new step run, with a new idempotency key), read the non-encrypted history, or, with
  deploy rights, ship different worker code. Signatures protect approvals, not the platform: admin
  access must stay small, restricted and audited. They also need binding to the case, step, input
  digest and an expiry, or an old valid signature could be replayed. Recorded in D19.
- Status: closed.

## 26. Layer 0: core inside a workflow

> Why must `core` run inside a Temporal workflow?

- Your answer: because replay must make the same decisions every time.
- Discussion: true, but that is why `core` must be deterministic *once* it runs in a workflow, not
  why it runs there. It runs there because the interpreter (and later the case runtime) makes the
  decisions (which step next, is an approval needed, can the case close) and those span days and
  wait on people. Only workflow code waits durably: Temporal records each decision in history, and
  timers and signals (a person's answer) wake it up; a crash or deploy loses nothing. Temporal
  resumes by replaying the code against that history, hence your point: same decisions every time,
  so no clock, randomness or I/O in `core`, and no Temporal imports. Bonus: pure code also runs in
  memory, in a plain test, so what is tested is what runs.
- Follow-up: why not run the interpreter inside an activity instead, where the clock and I/O are
  allowed and determinism stops mattering? What would we lose?
- Status: open.
