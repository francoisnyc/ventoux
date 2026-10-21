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
| 7 | D3: expressions | closed |
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
| 26 | Layer 0: core inside a workflow | closed |
| 27 | Tracer: running the quickstart | closed |
| 28 | Card: catalog, contract, binding | open |
| 29 | Layer 1: why `@1` and not `@1.0` | closed |
| 30 | Spike: guarantees outside the standard | closed |
| 31 | Pydantic: when checks run | closed |
| 32 | Layer 2: why `now` can't be written | open |
| 33 | Layer 3: why plans can be checked and code can't | open |
| 34 | Layer 5: why check input policies twice | open |
| 35 | Layer 6: what lives in workflow history | closed |
| 36 | Layer 8: the model picks the step, never the values | open |
| 37 | Layer 9c: what the audit keeps after forgetting | open |
| 38 | Layer 9d: stale facts, and why replay decides the same way | open |
| 39 | Layer 10: why a fixpoint is needed | open |

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

- Your answer (spike warm-up): it goes in the contract?
- Discussion: close, one level off. The contract is the *promise* (inputs: the line items; output:
  `high_risk_total`; `effect: compute`; the output's provenance), but the *logic* lives in the
  activity's code behind it: a registered activity with `effect: compute` (D3), ordinary Python or
  Java, unit-tested and reviewed like any code. The case runs it as a step that writes
  `high_risk_total` to the case file, and the approval reads one short condition,
  `high_risk_total > 10000`. Better for the reviewer because: the condition says what it guards in
  one line (and renders as one plain sentence); "what counts as high risk" is a business definition
  with its own tests and its own owner, changed without touching every rule that uses it; the total
  is a named fact with provenance and a time obtained, so the approval sheet can show it (D11, D18)
  and an approval guards that value; and the expression language stays small enough to check,
  which is the spike's whole question (design question 11).
- Follow-up: `$sum(items[risk = 'high'].amount) > 10000` fits D3's subset (a simple filter and
  `$sum`). When would you still move it into a compute activity?
  Answer: when the rules need to change without editing every rule. Right: once "high-risk
  total" is used by more than one rule (an approval, an escalation, a report), it is a business
  definition, and it belongs in one place with one owner. Other signs: it needs its own tests
  (missing `risk`, currencies, rounding); "high risk" stops being a field comparison (a category
  table, a threshold per product); or the value should appear as a fact on the approval sheet, with
  provenance and the time obtained. And the reverse: used once, short, and reading as a sentence,
  the inline expression is fine and more visible, since the rules sheet shows it directly.
- Status: closed.

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
  Answer from memory (an earlier layer 1 warm-up, in another session): only the deployment
  binding changes; no new version or release. Right on every point: the contract (what) is untouched, so its hash and version stay;
  a release records which contracts a package needs, not where they run; the binding (where) is an
  operations change, protected by activation's check of manifests and live pollers.
- Retrieval (layer 1 warm-up, this session), the same follow-up plus a twist: (c) the same week,
  they also raise the scorer's start-to-close timeout from 10 s to 30 s. Answer: a) the registry gets the new
  queue; b) no new contract version, no release; c) no change. Discussion: b is right, and it's the
  "what vs where" half, now recalled without notes. a needs one word changed: the queue isn't in
  the registry (which holds contracts: *what* is promised) but in production's **deployment
  binding** (*where* it runs), so the registry and the contract hash don't move. c is the trap:
  the retry policy and timeouts are part of the contract (D17), because cases depend on them (how
  long a step may run before it needs attention) and may only tighten them, which needs a fixed
  baseline. Any contract change needs a new number (D5), so it is `risk.score@2`, published side
  by side with `@1`; CI's contract hash would fail a change made under `@1`. Packages adopt `@2`
  by referencing it, which creates a release; cases on `@1` keep the 10 s timeout. Rule of thumb:
  it's in the contract if a case could notice it or tighten it; where it runs is not.
- Status: reopened; "what vs where" is solid now, the contents of a contract (D17) still need a
  retrieval. Layer 1 builds exactly that.

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

- Your answer (tracer warm-up): people with the approval role other than the reviewer.
- Discussion: right for the first part, made precise by D11: anyone with `support-lead` (Sam)
  except Ana, whose answer set `approved_amount`, the value `pay` sends, and whose *approve* is
  what lets `pay` run; the person who opened the case is excluded too. The other two parts were
  missing. The case waits for one piece of pending work, the approval of `pay` by a
  `support-lead`: `pay` has not run, and the case stays open (D10). The test asserts exactly that:
  `run.waiting_for == ["approval of pay by support-lead"]`, and also that `pay` was not reached and
  the case is not closed. The tracer bullet runs this test.
- Retrieval (layer 7 warm-up): not recalled; asked to be reminded, and given the answer above in
  brief (Sam may approve, Ana may not since her answer set `approved_amount`; the case waits for
  the approval of `pay` by a `support-lead`; the test asserts `waiting_for`, not reached, not
  closed). Layer 7 builds this exclusion, so it comes back in code.
- Retrieval (layer 8b warm-up): "Sam can approve, Ana can't; it waits for a support-lead
  approval." Most of it, from memory. Two parts didn't come back. *Why Ana can't:* not because
  she isn't a team lead: her answer set `approved_amount`, which `pay` sends, so provenance
  excludes her (D11); with the `support-lead` role she would still be refused (`ana set
  approved_amount, which pay uses, so cannot approve it`). *The test:* `waiting_for == ["approval
  of pay by support-lead"]`, `not run.reached("pay")` and `not run.closed`; since layer 8a it runs
  on the real runtime.
- Retrieval (layer 9c warm-up): "Sam can approve, Ana can't since she set approved_amount." The
  exclusion came back with its reason, from memory, for the second time in a row: provenance,
  not rank (brief, D11). Three parts didn't come back, the same as in 8b:
  - **The person who opened the case is excluded too** (brief, D11, D25). In the quickstart a
    system opens it, so nobody is, but a refund opened by a support agent couldn't be approved by
    them. And since 8a, whoever *proposed* a step's run can't approve it either: the rule 9c
    reuses for forgetting (a forget request approved by its proposer is refused).
  - **What the case waits for:** one piece of pending work, the approval of `pay` by a
    `support-lead`. `pay` hasn't run, and the case stays open (brief, D10, D24).
  - **The test:** `run.waiting_for == ["approval of pay by support-lead"]`, `not
    run.reached("pay")` and `not run.closed`.
- Retrieval (layer 11h warm-up, 2026-10-21): "someone with the right role and other than the
  reviewer can approve. The case would wait for an approval, and the test would assert that the
  approver is different from the reviewer." The core came back for the third time in a row; all
  three parts were attempted, which is new. Sharpened:
  - **Why "other than the reviewer":** not because she reviewed, but because her answer set
    `approved_amount`, the value `pay` sends, and her `approve` lets `pay` run: provenance, not
    position (brief, D11). Someone who only edited a field `pay` doesn't use isn't excluded; and
    the opener of the case, and whoever proposed the run, are excluded too (D11, D25). The
    opener didn't come back, for the fourth time.
  - **What it waits for, in the inbox's words:** one approval, `approval of pay by
    support-lead` (brief, D24): `pay` hasn't run, and the case stays open (D10).
  - **The test asserts the moment, not an approver:** at that moment nobody has approved yet, so
    there is no approver to compare. It asserts `run.waiting_for == ["approval of pay by
    support-lead"]`, `not run.reached("pay")` and `not run.closed`. That Ana is refused is a
    second test: her answer is refused, saying `ana set approved_amount, which pay uses, so
    cannot approve it`.
  - **Why it matters now (11h, choice 9):** a second approver (`four_eyes`) is excluded by the
    same rule, plus whoever already gave the first approval.
- Status: open, until the opener and the test's three assertions come back with the exclusion.

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
  Answer: the interpreter needs durability. Right. An activity is one attempt: it runs to the end
  or fails and is retried from the start. It can't wait days for a person's answer (signals and
  durable timers belong to workflows), and its progress isn't recorded, so a crash midway would
  restart the whole case and re-run steps that already had side effects, with no history of which
  decisions were made. Activities are for the side effects; the decisions live in the workflow,
  which is why they must be deterministic.
- Retrieval (tutor review, after the tracer bullet): answered "core needs to be deterministic"
  again; the durability half was missing a second time. In one line: it runs in a workflow to
  survive days of waiting; it must be deterministic because that is how a workflow survives.
  The review added a second part: importing `temporalio` breaks *portability* (core would only run
  inside a workflow: no `run_case`, no simulate, no fast tests), while calling an LLM breaks
  *determinism* (a different answer on replay means a different path, and a side effect outside
  the registry).
- Follow-up: where does the step advisor's LLM call happen, and what does replay do with its
  answer? Answer: in an activity, and replay uses the recorded answer. Right: Temporal stores the
  activity's result in history and replay reads it instead of asking the model again. That answer
  is still `untrusted:llm`: it may only name a step, and the engine re-checks admission.
- Retrieval (layer 2 warm-up): "core must be inside a workflow for durability." Right, and the
  durability half came first and without prompting this time, which is what kept the question
  open. Unpacked: the decisions (which step next, is an approval needed, can the case close) span
  days and wait on people; only workflow code waits durably, with each decision recorded in
  history and timers and signals waking it up, so a crash or a deploy loses nothing. The other
  half follows from it: Temporal resumes a workflow by replaying its code against that history,
  so `core` must make the same decisions every time (no clock, randomness or I/O). Layer 2 is
  where that rule first shapes a language: an expression that read the clock would decide
  differently on replay.
- Status: closed.

## 27. Tracer: running the quickstart

> What did running the quickstart teach you that reading it didn't?

- Your answer: that the approval exclusion depends on who set the values.
- Discussion: right, and it's the key lesson. Read, the rule sounds like one about a person ("the
  team lead can't be the reviewer"); run, it is one about values: whoever set a value the step uses,
  or the answer that lets it run, can't approve it. The quickstart's own story (Ana reviews, Sam
  approves) never exercises it, since Ana isn't a team lead; only Sam reviewing then approving
  shows it. It needs a record of who set each value (`set_by` in the tracer, provenance in layer 4),
  so approvals (layer 7) depend on provenance, not only on roles. Smaller lessons: an example can
  pass while under-testing (the large-refund test), and a case waiting on a task had no defined
  report (design question 14).
- Status: closed.

## 28. Card: catalog, contract, binding

> Three words, three questions. Without looking: what question does each answer, give an example,
> and say what happens when it changes.

| Word | Question it answers | Example | Changes when… |
|---|---|---|---|
| **Catalog** | What can a definition call? | `payments.refund@1`, `risk.score@1` | a contract is added or retired |
| **Contract** | What does one entry promise? | schemas, risk, effect, retries, timeouts, idempotency, outcomes | never: a change is a new `@N` |
| **Binding** | Where does it run, here? | production: queue `risk-v2` | operations move it; no version, no release |

- In one line: the catalog lists contracts; each environment binds them.
- The test: if changing it would change the contract hash, it's the contract. Another way to put
  it: it's in the contract if a case could notice it or tighten it.
- The analogy: an OpenAPI document (the catalog) keeps its operations (contracts) apart from its
  `servers` per environment (bindings).
- Why "catalog" and not "registry": design question 15.
- Retrieval (layer 3 warm-up): "catalog = list of activities; contract = I/O for activities;
  binding = Temporal config binding a case to queues." The questions half came back. Catalog: right,
  and more exactly it lists *contracts*, never implementations (`core` runs no I/O). Contract:
  I/O is the start; it also holds risk, effect, retries and timeouts, idempotency and outcomes
  (D17), and the test for membership is "could a case notice it or tighten it?". Binding: right
  that it's per-environment Temporal config, but it binds an *activity* (`risk.score@1`) to a task
  queue, not a case. The examples and the "changes when…" column didn't come back: a catalog
  changes when a contract is added or retired; a contract never changes (a change is a new `@N`);
  a binding changes when operations move it, with no new version and no release.
  Check: `payments.refund@1` (a) moves to queue `payments-v2`, (b) its start-to-close timeout goes
  from 30 s to 60 s. Answer: both only update the binding. (a) right. (b) is the same trap as
  question 9's twist: timeouts and retries are in the contract (D17), because a case can notice
  them (how long a step may run before it needs attention) and may only tighten them, which needs
  a fixed baseline. So (b) is `payments.refund@2`, CI's hash check would refuse it under `@1`, and
  packages adopt `@2` through a release. Rule: what the activity promises is the contract; where
  it runs is the binding.
- Retrieval (layer 8c warm-up), with a twist: `payments.refund@2` allows 5 attempts; (b1) the
  platform team wants 8, (b2) the refund case wants at most 3. Answer: "catalog of activities,
  places and contracts; contracts are on activities' inputs; a binding defines how workers
  connect to the engine. Attempts are defined in the contract. Yes, it's a new contract version."
  Discussion: the retry half came back from memory this time, after being the trap twice
  (questions 9 and 28): attempts are in the contract (D17), so 8 attempts is
  `payments.refund@3`, and packages adopt it through a release. Three parts didn't come back.
  - **Catalog:** it lists *contracts* (and the roles and labels the platform team registers), not
    places: where an activity runs is the binding's.
  - **Contract:** inputs are only the start: the outputs, input policies, risk, effect, retry
    policy and timeouts, idempotency and outcomes are all in it, and it never changes (a change is
    a new `@N`).
  - **Binding:** close: per environment, which task queue serves a reference. It changes when
    operations move it, with no version and no release.
  - **(b2), the case's 3 attempts:** not a new contract version. A case may make a contract's
    retry policy *stricter*, never looser (D17, non-negotiables), so it is written in the case
    definition, and changes the case's behaviour, so the case package gets a new release. The
    contract stays `@2`. The examples and the "changes when…" column didn't come back either.
- Asked: "stricter, never looser: what if a constraint needs loosening?" The rule is about who
  is *downstream*, not a ban on loosening. Only the owner of a constraint loosens it, at its
  source, as a new version everyone can see: the platform team's 8 attempts (b1) is a loosening,
  allowed because they own the contract, published as `@3`, shown in the semantic diff
  (layer 13: a loosening is reported as such, never hidden) and adopted through a release. A case
  can loosen only its own tightening, back to the contract's level, never past it. So a case
  that needs more than the contract allows asks the platform team for a new version. Why: a
  reader can then trust a contract's limits by reading the contract alone, whatever case uses it.
- Retrieval (layer 10d warm-up): "the catalog contains the list of steps; contracts the
  definition of input, output and policies; a binding defines how to connect with Temporal and
  workflow configs." The contract came back best; the other two need sharpening, and the
  examples and the "changes when…" column didn't come back, for the third time.
  - **Catalog:** it lists *contracts*, not steps. Steps live in a case definition, and each
    *references* a contract by name and version (`pay` calls `payments.refund@2`). The catalog
    also holds what the platform team registers: roles, source labels, systems. It changes when a
    contract is added or retired.
  - **Contract:** inputs, outputs and their policies, yes; also risk, effect (`read`, `write`,
    `notify`, `compute`), retries and timeouts, the idempotency key and the declared outcomes
    (brief, D17). It never changes: a change is a new `@N`. 10d reads two of these: the outcomes
    (`declined`, an outcome no step may read) and the effect (only a `read` is fetched again
    when a `max_age` finds it stale).
  - **Binding:** narrower than "how to connect with Temporal": per environment, which task queue
    serves a reference (production: `risk.score@1` on queue `risk-v2`). A workflow's settings
    that a case could notice (its timeout, its outputs' sources) are in its *workflow contract*,
    not the binding. A binding changes when operations move it, with no version and no release.
  In one line: the catalog lists contracts; a contract is what one entry promises; a binding is
  where it runs here.
- Status: open (a card: kept in the warm-up rotation until all three come without the table).

## 29. Layer 1: why `@1` and not `@1.0`

> Why `@1` and not `@1.0`?

- Your answer: because any change is a new contract, so there are no minor versions.
- Discussion: right, that's the core. Two sharpenings. First, *any change to the contract*, not
  to the code: a bug fix inside the refund adapter, with the same schemas, risk, retries and
  outcomes, needs no new number (D5, implementation changes). Second, why a minor version would
  hurt, not just be unneeded: semantic versioning lets "compatible" changes ship under the same
  name and lets consumers float (`^1.0` picks up `1.1`), so one reference would mean different
  promises over time. Ventoux needs a reference to mean one thing for good: an approval, a
  release record and an audit ("which contract did this case use?") must have one answer, and the
  hash can tell that a contract *changed* but never that the change is *compatible*, which is a
  judgment. So a whole number, exact, with no ranges and nothing to resolve. Whether a change is
  breaking still matters, but only for how much work packages need to adopt `@2`.
- Follow-up: the payments team fixes a rounding bug inside the refund adapter's code; the contract
  is unchanged. New version? New release? What tells the running cases?
  Answer (tutor review): no new version, no release, just deploy the worker. Right on all three.
  Nothing needs to tell the running cases: they only know `payments.refund@1`, and the next call
  is picked up by whichever worker serves it (an attempt already running finishes on the old code;
  a retry may land on the new). It's safe because Temporal never replays activities, only their
  recorded results; changing *workflow* code is what needs worker versioning (D5). The judgment to
  watch: "unchanged" must be true in meaning, not only in the hash. If the fix changes what callers
  rely on (rounding down becomes rounding to the nearest cent), the promise changed and a person
  decides it's `@2`. The hash tells you that something changed, never that a change is harmless.
- Status: closed.

## 30. Spike: guarantees outside the standard

> Which of our guarantees could not be expressed as a restriction of the standard, and why?

- Your answer: no eval?
- Discussion: the opposite case, and a useful one: "no eval" is the guarantee you *can* get by
  restriction. Forbid `run` (script, shell, container), `call` to URLs, custom functions,
  catalogs, extensions and `loose` mode, and nothing from a definition is executed. Fragile
  (every door must be found: a custom function is itself a task, an extension adds `before` and
  `after` tasks), which is why question 6 prefers safe by construction, but possible. A
  restriction can only *remove*. The guarantees it can't give are those that need something the
  standard doesn't have:
  - **provenance and input policies:** values carry no record of where they came from, so no
    amount of forbidding adds one; it is new information (D12);
  - **an approval on every path, by someone else:** there is no approval, role or answer, only
    an event anyone may send, so "someone other than whoever set the amount" can't be said (D11);
  - **references to contracts only:** a `call` name binds to nothing the standard can check;
  - **case semantics:** no position, closing when nothing is left to do (D10): a flow can't be
    restricted into a case;
  - **fail closed:** jq reads a missing field as `null` and `null > 1000` as `false`. That is
    the language's meaning, not a feature to forbid; changing it changes the semantics.
  In one line: restriction removes capabilities; our guarantees mostly *add* information
  (sources, who answered) or *change* meaning (errors instead of false).
- Follow-up: why can't you make jq fail closed by forbidding parts of it?
  Answer: because missing fields return null by design. Right: it lives in the meaning of the
  most basic operation, `.payout`, not in a feature you could remove. Forbidding works on syntax;
  every field access can yield `null`, and `null > 1000` is `false` (jq orders `null` below every
  number), so you would have to forbid field access, which is the whole language. jq can't even
  tell a missing field from one set to `null` (`{}` and `{"payout": null}` both give `null`). The
  only fixes add or change something: check before evaluating that every field read has a value
  (which needs a parser to know the fields), or an evaluator with different rules. Either way it
  is no longer the standard's jq, which is the point of the question.
- Status: closed.

## 31. Pydantic: when checks run

> Predict, then run: (1) `payments_refund.risk = "low"`; (2)
> `payments_refund.model_copy(update={"risk": "low"}).risk`; (3) building a contract with
> `effect="write"` and `idempotency_key=None`: which rule fires, and in which mode?

- Your answer: (1) an error; (2) `"low"`; (3) asked for the explanation.
- Discussion: (1) right: `frozen=True` refuses the assignment ("Instance is frozen"), so D5 is
  enforced by the object itself. (2) right, and the trap: `model_copy` makes a *new* object and
  runs no checks at all. Trying it with `risk="hihg"` and no idempotency key produced a copy that
  `Catalog.register` accepted: every rule skipped, failing open through a side door. Fix added to
  layer 3: `register` re-checks what it receives. (3) In order: the `mode="before"` validator
  (`no_unknown_fields`) sees the raw dict; then each field is checked alone against its type
  (`None` is a valid `str | None`); then the `mode="after"` validators see the whole object, and
  `side_effects_are_idempotent` finds `effect == "write"` with no key and raises `ValueError`,
  which Pydantic wraps in a `ValidationError`. In one line: field checks see one value, "after"
  rules see the whole object, and both run only when an object is built, never when it's copied.
- Follow-up: the platform team wants a helper, `next_version(contract, **changes)`, that copies a
  contract as `@N+1` with some changes. How should it build the new contract so every rule runs?
- Status: closed.

## 32. Layer 2: why `now` can't be written

> Why can't `now` be written at all, and what would break on Temporal replay if it could?

- Your answer: because time breaks determinism.
- Discussion: right at the core, and the short version of two answers. *Can't be written*, not
  *refused*: `now` has no model and isn't in `OPERATORS`, so the published JSON Schema has no
  shape for it and neither a person nor a model can express it. The prototype's JSONata had
  `$now()` in the language and refused it from an allowlist, where any gap lets it through; ours
  is safe by construction (question 6). *What breaks*: on Monday `now > deadline` is false and the
  workflow waits, which history records; on Thursday a worker restarts and Temporal replays the
  code against that history, the condition is now true, the code asks to schedule `escalate`,
  history says otherwise, and the case stops on a non-determinism error until someone fixes the
  code (or, if the commands happened to line up, the run quietly diverges from what happened).
  One sharpening: reading the *wall clock* breaks determinism, not time itself. Temporal has
  replay-safe time (`workflow.now()` comes from history), but `core` may not import Temporal, so
  time reaches an expression only as data history recorded: a timer firing, an event, a field.
- Follow-up: a claim must escalate if nobody has assessed it within 5 days. Without `now`, how is
  that written, and where does the time come from?
  Answer: asked for it. As a rule whose *when* is time passing, not an expression reading the
  clock (D7, the `sla` pattern of layer 11): *when* 5 days after the case opened (a timer, declared
  as data, `5d`), *if* `assessed` is not reached (a question about the case file), *then* start
  `escalate`. The engine starts a durable Temporal timer when the case opens; the Temporal server
  keeps the time, and history records `TimerFired`. On replay, Temporal reads that event at the
  same point instead of waiting or reading a clock, so the condition sees the same case file and
  decides the same way. Time enters as a recorded event, never as something an expression reads.
- Retrieval (layer 4 warm-up): "it's implemented as a signal, not sure how it is written." Half
  right: time does come in from outside the code, as a recorded event, which is the core. But it
  is a **timer**, not a signal. A signal is sent by someone (a person's answer, an outside
  system); a timer is set by the workflow itself and fired by the Temporal server, so no person or
  system has to remember to send "5 days have passed". History records `TimerStarted` when the
  case opens and `TimerFired` five days later. It is written as a rule (brief, D7): *when* 5 days
  after the case opened, *if* `assessed` is not reached, *then* start `escalate`; the `sla`
  pattern writes it for you (layer 11). On replay, Temporal reads `TimerFired` from history at the
  same point, so the condition sees the same case file and decides the same way. The difference
  matters for provenance too (layer 4): a signal carries content from a sender, whose trust must
  be tagged; a timer carries none, so it can't be injected.
- Retrieval (layer 6 warm-up): "if 5 days passed since the signal was received for the claim,
  then escalate." The shape came back this time: a rule reacting to time passing, from an anchor,
  not an expression reading the clock. Anchoring on an event is right too (D7 anchors on the case
  opening or a step's latest start; the claim arriving is that kind of event). Two parts didn't
  come back. *The **if**:* as written, every claim escalates on day 5, even one assessed on day 2;
  the rule needs *if `assessed` is not reached* (or the `sla` pattern, which cancels its timer
  when the step completes). *Where the time comes from:* for the second warm-up in a row, the
  answer names a signal and not the **timer**. The signal is only the anchor; the time comes from
  a durable timer the workflow sets and the Temporal server fires, recorded as `TimerStarted` and
  `TimerFired`. On replay, the code reads `TimerFired` from history at the same point instead of
  waiting or reading a clock, so it decides the same way. Layer 6 builds exactly this, for a
  wait's timeout (`at most 48h`).
- Retrieval (layer 9 warm-up), the follow-up, with a third part added (on Temporal, after a
  restart and replay, why does the case decide the same way?): "when we reach claim a timer starts
  and if nothing happens within 5 days ventoux closes the task and opens an escalation." The
  **timer** came back, from memory, for the first time, anchored on an event (the claim arriving).
  That was the missing part in the last two warm-ups. Three parts didn't come back:
  - **The *if* is a question about the case file, not "nothing happens".** The rule reads
    *if `assessed` is not reached*. "Nothing happens" would let any event (a document arriving, a
    note) stop the escalation, though the claim is still not assessed. Or, read the other way,
    the escalation would wait on events that don't matter.
  - **Nothing closes the task.** The assessment stays open, and `escalate` starts beside it,
    typically to a team lead. Closing a person's task because time passed would cancel work
    nobody decided to cancel. Work is never cancelled or skipped automatically (brief, D17). The
    `sla` pattern cancels its own *timer* once the step completes, never the step.
  - **Replay (the added part).** History records `TimerStarted` when the claim arrives and
    `TimerFired` five days later. On replay the code reads `TimerFired` from history at the same
    point, and nothing waits or reads a clock, so the condition sees the same case file and the
    case decides the same way. Layer 9 needs the same idea for `max_age`: the time a decision is
    made reaches `decide` as data that history recorded, never from a clock that `case` reads.
- Retrieval (layer 11b warm-up, 2026-10-18; skipped at 11a): "tell me". Nothing came back this
  time, so the answer, in plain words, in three parts:
  - **How it is written:** a rule (brief, D7, D38). *When* 5 days have passed since the claim
    opened: a timer, written as data (`5d`, anchored on a moment, layer 11e). *If* the claim is
    still not assessed: a question about the case file, read when the timer fires. *Then* start
    `escalate`, to a team lead. The assessment stays open: nothing is cancelled or skipped
    because time passed (brief, D17). The `sla` pattern writes this for you, and cancels its
    timer once the assessment is done (brief, D7).
  - **Where the time comes from:** a durable timer the case workflow sets and the Temporal
    server fires; nobody sends "5 days have passed". History records `TimerStarted` when the
    claim opens and `TimerFired` five days later, and the firing reaches the case as an event
    stamped with its own due time (brief, D33).
  - **Why replay decides the same:** on replay the code reads `TimerFired` from history at the
    same point, instead of waiting or reading a clock. So the condition reads the same case file
    and decides the same way. A clock read on replay would see another time, ask for what
    history never recorded, and stop on a non-determinism error.
  One sharpening, new since 11a: a milestone is not a value a condition can read (brief, D35),
  so "not assessed" is written over what the assessment gives (its outcome), and how a timer's
  condition says it exactly is 11e's to decide.
- Status: open. The timer is solid now; the question stays in the rotation until the *if* and
  replay come back too.


## 33. Layer 3: why plans can be checked and code can't

> Why is this impossible to check on ordinary workflow code? ("This": what the validator proves
> before anything runs, such as "every path to `pay` passes an approval".)

- Your answer: it's a DAG? Or a decision tree to resolve, compared to a full AST?
- Discussion: the core is right: a plan is a small graph of explicit moves, and a program is a
  full syntax tree whose behaviour you would have to work out. Two sharpenings. First, a plan is
  neither a DAG nor a tree: it is a directed graph that may have cycles (slice 8's retry loop
  goes back to `pay`) and branches that merge again (`reject` and `timeout` both go to
  `failed`). The search still ends because it keeps a `seen` set and a plan has finitely many
  states. Second, the shape is only half of it. Two things make the plan checkable:
  - **the moves are closed and explicit:** every way out of a state is an entry in its `on`, so
    "every path" means "every arrow", a finite list. A condition is an opaque fork, and the
    validator assumes either branch can run. That over-approximation is safe: it can refuse a
    plan that would in fact be fine, never accept one that isn't (fail closed);
  - **the meaning is declared, not inferred:** "high risk" is read from the contract, and "an
    approval" is a wait offering `approve` and `reject`. In the Python workflow,
    `await workflow.wait_condition(lambda: self.approved)` is just a lambda: which signal sets
    `self.approved`, who may send it, and whether `refund` is risky are nowhere in the code.
  In code, even with the full AST, paths go through loops, function calls, exceptions and
  values computed at run time, and "can line B run without line A first?" is undecidable in
  general (Rice's theorem): a tool can only guess or give up. Ventoux's rule, by contrast, is
  three lines of graph search.
- Follow-up: slice 8's plan loops back to `pay` after a declined refund. Why does `reach` still
  finish on a graph with a cycle, and why does that loop make the plan unsafe, not just slow?
- Retrieval (layer 5 warm-up): "every path to pay is encoded in the model?"; the follow-up: "don't
  know". The first half is the core: in a plan every move is an entry in some state's `on`, so the
  paths are data the validator can list, where in code they are implicit in loops, calls,
  exceptions and values computed at run time. The other half didn't come back: the *meaning* is
  declared too ("high risk" is read from the contract; an approval is a wait offering exactly
  `approve` and `reject`), while in code `wait_condition(lambda: self.approved)` says neither.
  The follow-up, in two parts. *Why `reach` finishes:* it keeps a `seen` set and adds a state to
  the work list only the first time it is seen, so each state is visited at most once; a plan has
  finitely many states, so the search ends after at most that many steps, cycle or not. *Why the
  loop is unsafe:* `pay` → `declined` → back to `pay` runs the high-risk refund a second time on
  the approval already spent. An approval is for one run of one step (brief, D11), so the loop is
  a second refund nobody approved. `validate` refuses it as `APPROVAL_REUSED`: after a high-risk
  activity, follow every arrow except an approval's `approve`; reaching a high-risk activity
  again, itself included, means a run without its own approval. The fix routes the loop through
  an approval, so each pass is approved.
- Retrieval (layer 10a warm-up), the follow-up: (a) "don't know"; (b) "not sure". Neither came
  back, so in full again, with a trace:
  - **(a) Why `reach` finishes.** `reach` keeps two things: `seen`, every state found so far, and
    `waiting`, the states still to look out of. A state goes into `waiting` only when it is first
    added to `seen`, so each state is looked out of at most once. Slice 8's plan: from `initial`,
    `check_order`, then `approve_refund`, then `pay`, then `declined`; out of `declined`, the
    arrow back to `pay` finds `pay` already in `seen`, so nothing is added, and the search moves
    on. A plan has finitely many states, so `waiting` empties after at most that many turns. A
    cycle can't make it spin: the second time round, every state on the cycle is already seen.
  - **(b) Why the loop is unsafe.** `pay` → `declined` → `pay` runs the high-risk refund a second
    time on the approval already spent before the first run. One approval unlocks one run of one
    step (brief, D11), and the second run has its own idempotency key (`pay#2`), so the payment
    system treats it as a new refund: money may move twice, with nobody approving the second.
    `validate` refuses it as `APPROVAL_REUSED`: from each high-risk activity, follow every arrow
    except an approval's `approve`; reaching a high-risk activity again, itself included, means a
    run without its own approval. The fix sends the loop back through the approval.
  - **Why it came up now.** Layer 10's fixpoint ends for the same reason as `reach`: the set of
    what a case can reach only grows, and there are finitely many steps and milestones to put in
    it.
- Retrieval (layer 11f warm-up, 2026-10-19), the follow-up: "help me", then, after a hint per
  part, "walk me through it". Walked through with the trace:
  - **(a)** `reach` puts a state in `waiting` only when it first enters `seen`. Slice 8's plan:
    `initial`, `check_order`, `approve_refund`, `pay`, `declined` are each added once; out of
    `declined`, the arrow back to `pay` finds it already seen and adds nothing, so `waiting`
    empties. Finitely many states, so finitely many turns, cycle or not.
  - **(b)** One approval unlocks one run of one step (brief, D11). `pay#2` runs on the approval
    `pay#1` spent, under a new key, so the payment system makes a second refund nobody approved.
    `APPROVAL_REUSED` refuses it; the fix sends the loop back through the approval.
  - **Why it came up in 11f:** a timer that re-arms itself would be a loop with no person in
    between, which 11f's choice 3 rules out.
- Status: open, until the follow-up comes from memory.


## 34. Layer 5: why check input policies twice

> Why check sink policies twice? (`validate` before the plan runs, and again before each activity
> is scheduled; "input policies" since brief, D21.)

- Your answer: "validation happens before the run, that makes sense, and at run it checks the
  real inputs?"
- Discussion: right, and "the real inputs" is the key phrase. The two checks see different
  things, and each catches what the other can't:
  - **`validate` sees declarations, on every path.** It knows only what the plan says about its
    fields: `untrusted:llm`, or nothing. An unmarked field is the case's to vouch for, so it
    passes `trusted_only` (layer 4). What it gives: every path checked at once, before any case
    runs, with a message telling the author what to change.
  - **The runtime sees real sources, on the one path this run takes.** Each value arrives with
    where it actually came from (`sourced(…, "untrusted:llm")`). The curriculum's test is the
    gap between the two: `suggested_recipient` unmarked passes `validate`, and the model's value
    is refused before `letters.draft@2` is called.
  - **The runtime check depends on nothing the static one did.** A plan may reach the engine
    without having been checked: an AI draft, an older release, a bug in `validate`, a copy made
    with `model_copy`. The runtime check reads no flag saying "validated", so skipping
    validation can never weaken it. Defence in depth, failing closed.
  In one line: `validate` proves a plan *can't* misuse declared data on any path; the runtime
  proves *this* value, on *this* path, really may go in.
- Asked: "is it because an activity can change at runtime?" No: a contract never changes (a
  change is a new `@N`, layer 1), and its input policies are in its hash (layer 4); only its
  binding can move, and a binding carries no policy. What differs between the two checks is the
  *data*. The same `draft-reply` plan, `suggested_recipient` unmarked, passes `validate` once; in
  case A the CRM set the field (`system:crm`) and the draft is made, in case B a model did
  (`untrusted:llm`) and the step stops. Nothing in the plan tells A from B, only the values do,
  and they don't exist when `validate` runs.
- Follow-up: if the runtime check catches everything with the real sources, why keep the static
  one at all?
- Retrieval (layer 8d warm-up), the follow-up: "the static one catches issues before they fail at
  runtime." Right: *before* is the core. Three parts didn't come back, and they are why "before"
  matters:
  - **Every path, not this one.** The runtime check sees only the path a run takes. A bad flow on
    a rare branch (a refund over 1000, a rework after a rejection) may never run in a test and
    surfaces months later, in a live case. `validate` checks every path at once.
  - **Who hears of it.** The static refusal reaches the *author*, at `ventoux check` or in the pull
    request, with what to change. The runtime one reaches an *operator*: a case needs attention, a
    customer waits, and the person looking at it can't change the definition.
  - **What fixing it costs.** Caught before release, it is an edit. Caught at runtime, it is a new
    release, and open cases still on the old one (layer 12). For a drafted plan (layer 15), the
    static issues are what the authoring loop feeds back to the model to repair it.
  In one line: the static check prevents, for authors, on every path; the runtime check enforces,
  for this value, on this path. Neither replaces the other. In 8d, output provenance gets only the
  runtime check; case validation (layer 10) will read the declared sources statically.
- Retrieval (layer 9d warm-up), the follow-up: "the static one catches problems on every path,
  before release." **Every path** came back from memory, for the first time: the runtime check
  sees only the path a run takes, so a bad flow on a rare branch may surface months later in a
  live case. **Before release** carries the cost: an edit then, a new release and open cases on
  the old one after. One part didn't come back: **who hears of it.** The static refusal reaches
  the *author*, at `ventoux check` or in the pull request, who can change the definition; the
  runtime one reaches an *operator*, with a case stuck and a customer waiting, who can't. 9d has
  the same split: a `max_age` naming a field its step doesn't read is refused when the
  definition is read (for the author), while a stale fact from a person is found at runtime and
  the case needs attention (for an operator).
- Retrieval (layer 11d warm-up, 2026-10-19), the follow-up: "because it catches if all paths are
  valid. It's better than failing at runtime." **Every path** came back a second time. "Better
  than failing at runtime" is the right instinct; what makes it better is two things:
  - **Who hears of it.** The static issue reaches the *author*, at `ventoux check` or in the pull
    request, and the author is the one person who can change the definition. The runtime refusal
    reaches an *operator*: a case needs attention, a customer waits, and the person looking at it
    can't change the definition. In 11d's terms: a person's event payload given to an input that
    takes `only_from("payments")` is an error the author fixes with one edit; at runtime it is a
    refund stuck in someone's queue.
  - **What fixing it costs.** Before release, an edit; after, a new release, and the open cases
    still on the old one (layer 12).
  In one line: the static check prevents, for the author, on every path; the runtime check
  enforces, for this value, on this path. Neither replaces the other.
- Status: open, until "who hears of it" comes back from memory.


## 35. Layer 6: what lives in workflow history

> What lives in workflow history, and why must the interpreter be deterministic? Concretely: Sam
> approved the guide's refund, and the worker crashed just before `pay` finished. What does the
> new worker read from history, what runs again, and is the refund paid twice?

- Your answer: "history holds the activity results, signals and timers; replay reads them back."
- Discussion: the core is right: what came from outside is recorded, and replay reads it back
  instead of doing it again. Three parts didn't come back.
  - **History also holds what the workflow asked for:** the run's input and every command
    (`ActivityTaskScheduled`, `TimerStarted`), next to the results (`ActivityTaskCompleted`,
    `WorkflowExecutionSignaled`, `TimerFired`). That is the *why* of determinism: replay runs the
    code again from the start, and each command it issues must match the next recorded one, in
    kind and order, or Temporal raises a non-determinism error and holds the run (slice 6's test).
    A clock or a random number could change what the code asks for. Replay checks the commands,
    not their inputs (checked in layer 6), so keeping the inputs deterministic is the boundary
    test's job.
  - **The scenario.** The new worker reads back the lookup's result, Sam's signal and the
    `ActivityTaskScheduled` for `pay`; the workflow code runs again, each step matched against
    history, nothing repeated. The `pay` *activity* is a different story: it never reported back,
    so after its `start_to_close` (30s) Temporal **retries** it, and the first attempt may already
    have moved money.
  - **Paid twice? Not by replay, and not by the retry,** because of the idempotency key: both
    attempts carry `refund-1/<run ID>/pay#1`, so the payment system returns the first refund
    instead of paying again (brief, D17; slice 4's test).
  In one line: replay re-decides from recorded facts; retries re-do side effects, and the key
  makes them safe.
- Follow-up: a person *resets* that run to before `pay` (brief, D19). Is the refund paid twice
  now, and why does the key not save it?
- Retrieval (layer 8 warm-up), the follow-up: "yes, paid twice; a reset gives a new run ID, so a
  new key." Both right, and from memory. A reset starts a new run of the same workflow from an
  earlier point; the key carries the run ID, so `pay#1` in the new run sends a key the payment
  system has never seen, and it pays again. That is why the brief keeps resets small and audited
  (D19). Part (c), asked as a lead into layer 8, didn't come up: *anything* that starts a new run
  of the same case changes the run ID, and continue-as-new (design question 18) does exactly that
  for every long case. So a case's keys can't simply carry the run ID: a key must name the same
  step run in every run of the case (the case's workflow ID, the step, and a step-run count that
  crosses over). Layer 8 decides it.
- Status: closed (the follow-up came from memory; part (c) is decided in layer 8).


## 36. Layer 8: the model picks the step, never the values

> What does "the model picks the step, never the values" mean in code? Using 8a: if a step
> advisor (layer 15) suggested the next step, which seam would its suggestion go through, what
> would the engine still check, and where could a value it made up never get in?

- Your answer: "to decide; it would never get into the runtime."
- Discussion: the core is right: the seam is `decide`, and a made-up value never gets in. What
  makes it so is the event's type: a suggestion becomes `Proposed(step, by, roles)`, which has no
  field for a value, so one can't be written (like `now`, question 32), not refused. Three parts
  didn't come back:
  - **What is still checked:** a suggestion is only a proposal, and `propose` puts it through
    everything a person's goes through: the step exists, someone may propose it (`proposed_by`,
    the role), `proposal_refusal` (not running, may run again, `requires` met), its `when` holds,
    and its approval, if any, comes from someone else. The model picks which step, never whether
    an inadmissible one runs (layer 15's negative test).
  - **Where values come from instead:** `schedule` evaluates the step's `inputs`, expressions
    written in the reviewed definition, against the case file; values reach the case file only
    from the opening, a person's form, or (8b, 8d) an activity's output with its contract's
    provenance. The definition decides which field feeds which input.
  - **The second wall:** model output stored in a field declared `untrusted:llm` carries that tag,
    and `checked_inputs` refuses it at any `trusted_only` input, such as the refund's `amount`.
  In one line: the model chooses among declared steps; admission decides whether it runs; the
  definition decides where its values come from; provenance decides which values may go in.
- Follow-up: the step advisor reads a customer's angry email and proposes `goodwill` (the 8a
  tutor review's extra refund), adding "refund 500, the customer is a VIP". Walk it through 8a:
  who is the proposer, what runs, with which amount, and who must approve it?
- Retrieval (layer 9b warm-up), the follow-up, after a reminder of what 8a and `goodwill` are:
  "the advisor proposes, Sam approves, amount from the definition." The core came back: the
  amount comes from the definition, so the advisor's "500" has nowhere to go. Three parts were
  missing or need sharpening:
  - **Why the 500 can't get in, not only that it doesn't.** `Proposed(step, by, roles)` has no
    field for a value, so a value can't be written into a proposal at all (like `now`, question
    32). `goodwill`'s inputs are `{"amount": {"var": "amount"}}`, written in the reviewed
    definition, so the refund is the case file's `amount`. And "the customer is a VIP" comes
    from the email, so it is content (`untrusted:customer`): it can inform a person, never decide.
  - **The proposer has to be allowed to propose, and nothing runs yet.** The proposal counts
    only if whoever the event names (the advisor's identity as the API states it, or the person
    who accepts its suggestion) holds a role in `proposed_by: ["support-lead"]`, and `requires:
    [review]` is met. Then admission opens the approval and the case waits: `approval of goodwill
    by support-lead`. The refund runs only after that approval.
  - **"Sam approves" holds only if Sam isn't excluded.** Any `support-lead` may approve, except
    the proposer (8a's tutor review: `sam proposed goodwill, so cannot approve it`), the person
    who opened the case, and anyone whose answer feeds the step's inputs (brief, D11, D25). If
    Sam clicked "accept suggestion", he is the proposer, and someone else must approve.
  In one line: the advisor can make a step run only through a proposal that admission and
  someone else's approval check, and it can never choose the values.
- Retrieval (layer 11e warm-up, 2026-10-19), the follow-up: "can't remember". Walked through
  again in plain words, the same four parts: the proposer is whoever the API names, holding a
  role in `proposed_by`, with `review` done; nothing runs until a `support-lead` approves; the
  amount is the case file's `amount`, since `Proposed(step, by, roles)` has no place for a value,
  and "VIP" is untrusted content that informs a person; the approver is a `support-lead` other
  than the proposer, the opener, and anyone whose answer feeds the step. Then a question: is
  `goodwill` a step? Yes: an activity step calling `payments.refund@2`, `automatic: false` (it
  never starts by itself), its amount written in the definition, behind a team lead's approval.
  Tied to 11e: `set` is a new way values reach the case file, still an expression in the
  definition, and a value computed from Ana's answer still keeps Ana from approving (brief, D42).
- Status: open, until the proposer's checks and the exclusions come back from memory.


## 37. Layer 9c: what the audit keeps after forgetting

> After a customer is forgotten, what can the audit still show, and what can't it? (Claim-7:
> opened with a national ID, Ana typed a tax ID into her form, a lookup failed quoting the ID,
> Pia proposed forgetting it and Olu approved.) a) What stays readable, and where? b) What is
> gone, and why can't it come back, in history and in an earlier export? c) What is lost that
> wasn't a sensitive field?

- Your answer: "decisions and who made them stay; sensitive values are gone."
- Discussion: the core is right, and it is D15's last line. Three parts didn't come back.
  - **Where, and with no key at all:** the case's closing report (`report`), every line with
    `‹sensitive›` in place of a value; Temporal's history read as stored: the definition (the
    rules and release), each answer's entry, outcome, person and role, the approved request;
    values that weren't sensitive where they were used (`estimated_damage` in the next run's
    start); the forget request's own history, which replays with no key. Staff identifiers stay:
    forgetting is about the case's subject, through its sensitive fields.
  - **Why it can't come back:** sensitive values were never stored in plain text (9b), only as
    `encrypted/n` parts under the case's key; the key is destroyed and never made again, so no
    one can open them, in Temporal's history or in an export, which carries the same ciphertext
    (question 21's trap). A replay fails with `the key of claim-7 was destroyed when it was
    forgotten`.
  - **The surprise:** every form value in an answer event (the client seals them all, since it
    can't tell which are sensitive, D31), and every failure's message and stack trace (always
    sealed: Ventoux can't know what an activity's error says). After forgetting, an operator
    sees that a step failed and with which type, never what it said.
  In one line: the audit keeps that each decision happened, who made it, under which rule and
  as what; it loses every value it can't prove was safe to keep.
- Follow-up: a regulator asks why claim-7 was denied. After forgetting, which of their
  questions can you still answer, and which not?
- Retrieval (layer 10b warm-up), the follow-up: "I can answer who did what, but the values would
  be gone." The core came back from memory: decisions and who made them stay; values go. Three
  sharpenings:
  - **More than who did what:** *under which rule* (the definition and release are in history, so
    the condition that led to the denial can be shown), *as what* (each outcome, role and time),
    *in what order* (which steps ran, which failed), and *on which facts, by name and source*
    (`policy_status from system:policies`), even where the value is gone.
  - **Not every value is gone:** a value that wasn't sensitive stays where it was used, such as
    `estimated_damage` in a later step's start. What goes: the sensitive fields (national ID, tax
    ID), every value in a form answer (the client seals them all, D31), and every failure's
    message. So "the amount assessed" may still be answerable; "what Ana typed" is not.
  - **The real answer is decided before forgetting.** If a regulator may ask for the values, the
    case says so in its definition: `forgetting: "while_open"` or `"never"` (brief, D32, books and
    records), and a request to forget it is refused. Forgetting is a retention choice made by the
    definition's author, not a surprise for the auditor.
  In one line: after forgetting, the audit explains the decision (rule, people, order, facts by
  name) but can't show the personal values it rested on; if those must be shown, the definition
  must never let the case be forgotten.
- Status: open, until "the facts by name and source" and the retention choice (D32) come back
  from memory.

## 38. Layer 9d: stale facts, and why replay decides the same way

> Sam approves a refund on day 3. Ana's review set `approved_amount` on day 0, and
> `check_order.status` came from an order lookup on day 0. `pay` needs both at most a day old.
> a) What happens to each fact, and why are they treated differently? b) On Temporal the worker
> restarts and replays the case. Why does it decide the same way, given that "3 days old"
> depends on time?

- Your answer: a) "the person's answer needs attention, the lookup gets refreshed"; b) "because
  it recalculates everything, it does not rely on time."
- Discussion: a is right on both facts. The why: a read changes nothing in the world, so running
  it again only fetches today's value; a person can't be asked again by the engine, so a person
  decides (send the review back, then retry `pay`, or close the case) (brief, D18). Two details:
  `pay#1` fails before it starts and Sam's approval goes with the failed run, for a retry
  (brief, D26), which was slice 8's loop fix; and the refresh passes the same gate as any start,
  its condition true and no approval needed, or it isn't run (the tutor review, brief, D33). The
  facts are checked in `max_age`'s order: if `approved_amount` comes first, `pay` stops before
  any lookup runs. b is half right: replay does run `decide` again on every event, in the order
  history recorded them. But it does rely on time, only on the right one. Each event carries
  `at`, stamped once from Temporal's workflow time, which history records; on replay
  `workflow.now()` gives the recorded time, so Sam's approval is day 3 again and the fact is 3
  days old again, even replayed on day 10. Had `decide` read the clock, a replay on day 10 would
  see "10 days old", ask for what history never did, and stop on a non-determinism error. The
  same lesson as question 32: time enters as data history recorded, never as a clock the case
  reads.
- Retrieval (layer 10c warm-up): "facts are timestamped and they are used by Temporal during
  replay." b's core came back: time is data the case was given, not a clock it reads. Sharpened:
  - **Which timestamp, and who reads it.** Every event carries `at`, stamped once as it reaches
    the case, from Temporal's workflow time (`workflow.now()`), which history records; each value
    then records when it was obtained (brief, D33). Temporal doesn't use it: the case's own
    `decide` reads it. On replay `workflow.now()` gives the recorded time again, so Sam's approval
    is day 3 even replayed on day 10, and the fact is 3 days old again. A clock read on day 10
    would ask for a refresh history never recorded: a non-determinism error.
  - **a didn't come back:** the two facts are treated differently. `check_order.status` is a
    read, so it is fetched again, as a new run of the step (with no approval needed, or it
    needs attention); `approved_amount` is a person's answer, which the engine can't ask again, so
    `pay` needs attention and a person decides (send the review back, then retry, or close).
  In one line: a stale read is refreshed, a stale answer goes to a person; and replay decides the
  same because the time is recorded on each event, never read from a clock.
- Retrieval (layer 11g warm-up, 2026-10-20): a) "to see the timestamp"; b) "because each event
  has the time it was logged on". b came back: each event carries its time, recorded once. a
  didn't, for the second time: the timestamp is how staleness is *noticed*, not what is *done*
  about it. Sharpened:
  - **a, the two answers:** both facts are 3 days old, and `pay` needs them at most 1 day old.
    `check_order.status` is a **read**, so the engine fetches it again, as a new run of
    `check_order`, and `pay` goes on with the fresh value. `approved_amount` is **a person's
    answer**. The engine can't ask Ana again, so `pay` needs attention, and a person decides:
    send the review back, then retry `pay`, or close the case (brief, D18, D33). A hook to
    remember it: *a stale read goes back to its system; a stale answer goes to a person.*
  - **b, one word to add, "recorded":** the time is stamped once as the event reaches the case,
    from Temporal's workflow time, and history records it. On replay `decide` reads that recorded
    time, never a clock, so the fact is 3 days old again even on day 10.
  - **Why it matters now (11g):** `ventoux simulate` works only because of b. A story's times are
    the events' times, so a timeline in simulated time decides exactly as a real case would.
  In one line: a stale read is refreshed, a stale answer goes to a person; replay decides the
  same because each event's time is recorded, never read from a clock.
- Status: open, until a (a read refreshed, a person's answer to a person) comes back from memory.


## 39. Layer 10: why a fixpoint is needed

> Why is a fixpoint needed? a) What a case can reach: why can't one pass in the written order
> decide which steps can ever run, and why start from nothing rather than from everything?
> b) Where each value comes from: why does that need no fixpoint, and what would bring one back?

- Your answer (layer 10d, closing the layer): "not sure"; asked for a short explanation, without
  jargon.
- Discussion, in plain words:
  - **a) Going round more than once.** The claim written `pay`, `assess`, `check`: one pass down
    the list finds `pay` waiting for "assessed" and `assess` waiting for "checked", neither
    there yet, then adds `check`, and would conclude two steps never run. They only come later
    than they are written: a case has no position. So the check goes down the list again until a
    round adds nothing (round 2 adds `assess`, round 3 `pay`, round 4 nothing). It always ends:
    each round only adds, and the steps are a finite list.
  - **Why start from nothing.** Starting from "everything can run", the deadlocked pair vouch
    for each other ("pay can run because assess can, and assess because pay can") and the
    deadlock passes. Grown from nothing, a step goes in only once what it waits for is in, so
    neither ever does: only what some order of events really reaches.
  - **b) One look is enough for where values come from.** Whoever writes a value stamps it with
    its own mark, whatever it read: a person's answer with the person, an output with its
    contract's source (brief, D29, D34). A field's origin never depends on another field's, so
    one look at each field's writers gives the whole answer.
  - **What brings the repeating back:** a field computed from other fields, as layer 11's rules
    may do ("total = amount + fee"). Its origin then depends on theirs, which may depend on
    others: round again until nothing changes (brief, D34).
  In one line: what a case can reach needs rounds until nothing changes, grown from nothing;
  where a value comes from needs one look, until fields are computed from fields.
- Follow-up: with steps written `c`, `b`, `a`, where `c` requires `b` and `b` requires `a`, how
  many rounds does the check take, and what does each add? And why would starting from
  "everything" wrongly accept two steps that each require the other?
- Retrieval (layer 11c warm-up, 2026-10-18), the follow-up: "not sure, tell me". In plain words:
  - **Four rounds, three that add.** `can_happen` (`case/reach.py`) goes down the steps in the
    written order each round, and a step added earlier in a round counts for the steps after it.
    Round 1: `c` waits for `b`, not in yet; `b` waits for `a`, not in yet; `a` requires nothing,
    so it goes in. Round 2: `c` still waits; `b` goes in. Round 3: `c` goes in. Round 4 adds
    nothing, and that empty round is how the check knows it is done. Written `a`, `b`, `c`, one
    round would add all three and a second would confirm it: the order changes how many rounds,
    never the answer. Each round only adds, out of a finite list of steps (and, since 11a,
    milestones and rules), so it always ends.
  - **Why not start from "everything".** Say `pay` requires `assess` and `assess` requires
    `pay`. Started from "everything can run", each step's requirement is already in the set, so
    nothing is ever taken out: each vouches for the other, and the deadlock passes as fine.
    Grown from nothing, a step goes in only once what it waits for is in, so neither ever does,
    and validation says `DEADLOCK`. Starting from nothing finds only what some real order of
    events reaches.
  - **Why it came up in 11c.** A rule's `stop` only takes paths away, so this set, a "may
    happen", stays sound; what has to be checked again are the claims that something always or
    never happens (11c's audit of the proofs).
- Status: open.

