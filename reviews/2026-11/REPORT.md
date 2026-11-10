# Whole-project review of Ventoux, November 2026

**Status: all six passes are done,** and a further round is closing what they left unchecked:
the in-memory findings were run on a Temporal worker (all eleven reproduce there; section 7a),
and the decisions pass 6 did not check claim by claim are being checked (section 7b, to come).
The summary is at the end of this page.

- **A correction to the task's own numbers:** `tests/histories` holds 68 files, of which 34 are
  recorded histories and one a carried state; the other 33 are the key files beside them.

- **What was reviewed:** `main` at `3edb471` (layers 0 to 20 merged). The review branch
  `review-2026-11` adds files only under `reviews/2026-11/`; `git diff 3edb471 HEAD -- src tests
  docs examples scripts pyproject.toml uv.lock .github` is empty, so every run below is a run of
  `3edb471`'s code, whatever commit of the review branch it names.
- **Baseline:** `uv sync --locked`, then `uv run pytest -q -p no:cacheprovider`: `4694 passed, 3
  skipped in 326.29s`, before any probe was written.
- **Every probe behind a finding or a "what held" claim has now been run twice,** once by the
  reviewer who wrote it and once by the lead reviewer, the three heavy replay probes included. The exception is pass 4: of its 263 mutations, the
  lead reviewer ran again the three behind findings 4.1, 4.2 and 4.4, against the whole suite.
- **How to read a proof:** every finding names a probe under `reviews/2026-11/probes/`, run from
  the repository root with `uv run python reviews/2026-11/probes/<name>.py`. Each probe's first
  line says what it shows, and its last line is `RESULT: BROKEN - …` or `RESULT: HELD - …`. Each
  probe behind a finding was written by one reviewer and run again, on its own, by the lead
  reviewer before the finding was written here.
- **Severity:** *breaks a promise* (a guarantee can be broken, shown by a run); *weakens one* (it
  holds today, but nothing would notice if it stopped); *misleads* (a document or a message says
  something untrue); *minor*.
- **In memory and on Temporal:** findings 1a.1 to 1a.4, 1b.1, 1b.2, 1b.3, 1b.5, 1b.6, 1b.8 and 3.3
  were first shown on the in-memory runtime; each was then run on a Temporal worker and gives the
  same wrong outcome there (section 7a).
- **Finding numbers** name the pass and the finding in it: `1a.2` is the second finding of pass 1,
  part a.

## Every finding, most serious first

### Breaks a promise

| # | Finding |
|---|---|
| 1c.1, 1b.4 | A sensitive option or attachment is written in plain text in the case's Temporal history, as its check activity's input, and stays readable after the case is forgotten (D31, D32, D67, D68). |
| 1c.5 | A closed case whose definition says `forgetting: while_open` is forgotten: the case refuses the approval, and the forget request destroys the key anyway (D32). |
| 1c.2 | A second request to forget the same case shares the first one's audit stream: the request that really forgets destroys the key, then never ends, can't be read, and leaves no record of the proposal, the approval or the key destroyed (D32, D77). |
| 1c.7 | A form value given under a name that is no field is unwrapped and kept in clear: in the history, in the audit store, for every role, and after forgetting (D31, D32). |
| 1a.1 | A repeated step (`for_each`) keeps nothing of what steered its runs: on untrusted data it sends a trusted-only input, and rules and steps after it reach `closes_when` milestones; `ventoux check` says these can never happen (D39, D43, D73). |
| 1a.2 | A case step keeps nothing of what steered it: a child case opened on untrusted data reaches milestones in its parent and sends its own trusted-only input, and `ventoux check` is silent on the case step's `reaches` (D43, D74). |
| 1a.3 | A child case's field declared `untrusted:` loses its mark when the parent gives the value, so the child decides on it and reports it back clean (D12, D41, D74). |
| 1a.4 | A `max_age` refresh hands back a clean run for a step that only untrusted data started: a day's wait turns what a customer's text made exist into trusted data (D33, D43). |
| 1b.1 | A person who answers a wait inside a plan step decides the plan's outcome, then approves the case step whose `when` reads it (D11, D28). |
| 1b.2 | In a child case, the parent's opener and the case step's proposer approve change requests, an edit and a skip (D52, D74). |
| 1b.5, 1c.4 | A value hidden by `visible_to` is shown to roles it is hidden from once it passes into a child case's field, back through a child's report, or into the audit store under a plan step's input names, where `read_audit` shows it to every role, `roles=[]` included ("a view hiding more than its source", D30, D42, D77). |
| 1c.3 | The audit export can be refused for good by a record's names (an event payload key, an activity output name, a plan input named like a sensitive field, a refused unsealed answer): the case never ends, `retry_export` meets the same refusal, and the case can't be forgotten (D17, D32, D77). |
| 1c.6 | The worker's log quotes an activity failure's message in plain text when the failure can't be sealed, for instance while the key service is unavailable (D31). |
| 1b.6 | A parent closing by `closes_when`, or a parent's rule stopping the case step, cancels a failed run inside the child with no person and no flag; the brief's texts pull against each other here (D17, D26, D40 against D74). |
| 1b.3 | A child's reported field named `outcome` replaces `<step>.outcome` in the parent with a person's free text, which validation accepts and the step advisor is then sent (D61, D74). |
| 1c.8 | A raw signal carrying `NaN` or `Infinity` makes the case's workflow task fail for good; needs a caller that signals with Temporal's client directly, which D79 forbids and Temporal doesn't prevent (D17). |
| 3.1 | A `VAULT_TOKEN` ending with a line break is quoted in an error that is neither `KeyRefused` nor `KeyUnavailable`: it reaches the caller of `start_case`, Temporal's history and the worker's output (D31, D78). |
| 3.3 | A contract validator's own message is copied in clear into the history, the needs-attention line and the audit record, a sensitive field's value with it (D30, D31). On Temporal it is also in the raw workflow history, as the audit export activity's input, where the same value quoted by the activity's own failure reads `‹sensitive›` (7a). |
| 3.2 | A `404` from any server is read as Vault's answer "never made", for good, and `ventoux doctor` says `keys.reachable` passed of a server that isn't Vault (D78, D81). |
| 3.4 | A path that isn't there reads as nothing to compare, exit 0: `ventoux summary --packages`, `conformance --since`, `check` and `check --unchanged` (D55 as amended in 13e: "anything it can't read ... fails the step"; D59, D80). |
| 2.1 | A migration the case refused, and recorded as refused, for an engine version its code didn't know is taken when a later worker replays the history: the refusal is decided from the code's own list on every replay, behind no engine version or patch (D51, D53, D76). |

### Weakens a promise

| # | Finding |
|---|---|
| 1b.9 | "Anything that talks to people drafts by default; it never sends on its own" is enforced and checked nowhere: a low-risk `notify` contract sends as the case opens, with no issue from the catalog, validation or the runtime (non-negotiable; D56). |
| 1a.5 | Untrusted data decides by making a person's work not exist: a rule on the absence of a task's answer, or a step requiring a task repeated over an empty customer-typed list, closes the case with nobody in it; one step past two recorded limits (D38, D48, D73). |
| 1b.8 | The person a step's `when` read is refused as approver of a call step, and approves the same payment once the step is a plan step or a case step (D11, D28, D74). |
| 1c.11 | A raw start with `carried` set skips the registry, the opening and the release check, so a draft runs in production on a state its caller wrote (D51, D54; a raw start). |
| 1c.10 | A request to forget waits in silence, its look-up retried without end, when the case's start doesn't read as a case (D32). |
| 1c.9 | Ten of 56 malformed raw signals are dropped with no line and no record (D41 as amended, D76). |
| 1c.12 | An activity failure's `details` and its `ApplicationError` type cross Temporal unsealed, and the type lands in the case's own line (D31). |
| 3.6 | A package file with a JSON key written twice is checked, released and run with the last one, nothing said; the authoring loop refuses the same from a model (D1, D59). |
| 3.5 | `read_audit` hands a value in a stored shape it doesn't know to a reader without its roles, in clear (D77). |
| 3.7 | A worker's manifest file and a release record ignore unknown keys and convert loosely: a misspelt `binds` binds nothing, `"development": "no"` reads as false (D54, D81). |
| 2.4 | The 34 kept histories leave whole areas with none: no plan run, no timer, no child case or doorbell, no registry that continued as new, no case migrated to engine 3, nine signal types; and the tests that replay them check only that no error is raised, never what the replay rebuilds (D51). |
| 2.2 | A request to forget stamps its audit records with the code's `ENGINE` constant, not with anything recorded: with the constant moved, a recorded request replays with no error and rebuilds records that say another engine version (D51, D76, D77). |
| 5.3, 6b.1 | Thirteen names the documents tell a team to use are not in `public.json`, so they are "internal: importable, unsupported, free to change": among them `ventoux.testing.run_case` and `CATALOG`, `Catalog`, `registry_worker`, and `propose`, `retry`, `close`, `view` and `propose_change` in `ventoux.temporal.cases`. A case of one's own can't be run, in a test or to its close, without them; the guides call `run_case` 20 times without ever showing its import, so the test that compares the guides' imports with the list can't notice (D82). |
| 4.2 | `closes_when` can be changed to close a case on any one of its milestones, where the rule is all of them, and all 4,694 tests still pass (D10). |
| 4.1 | The rule that an approver's role must be one the approval lists can be removed, for a plan's approval and a case step's, and all 4,694 tests still pass (D11, D23). |
| 4.4 | The runtime's own refusal of a repeated high-risk step can be removed and all 4,694 tests still pass; only the refusal at validation is tested (D34 "the runtime depends on nothing validation did", D73). |
| 4.5 | Nine refusals the brief states have no negative test, each removed with no test noticing among the 4,385 that need no Temporal server: among them a migration's label that isn't its target's, a release record of another package, and notes with no record before (D45, D50, D53, D55, D57, D83). |
| 4.6 | Four readers have no negative test for an input they don't know: the expression type checker's last refusal, the plain reading, the diff's value renderer and the digest's canonical form (CLAUDE.md: "Every evaluator has a negative test for an input it doesn't know"). |

### Misleads

| # | Finding |
|---|---|
| 1b.10 | An edit withdraws the approval a person's proposal waited for; nothing asks again, as D52 says each is, and no line says the proposal is over (D25, D52). |
| 1c.13 | `report` says `open`, with no history, of a case refused at its opening whose workflow failed. |
| 6.4.1 | `README.md` says "There is no code yet ... Nothing here is ready to use"; the repository holds 147 source files, 20 commands and a 0.1.0 changelog entry. |
| 6.4.2 | `docs/QUICKSTART.md` says "none of it is built yet" and tells the reader to run `ventoux init`, `dev` and `start`, none of which is a command (principle 5; D13). |
| 6.1.2 | D13 relies on `ventoux init`, which doesn't exist, and no dated line or out-of-scope entry says so. |
| 6.1.1 | `ventoux version` prints a prefix (`https://ventoux.dev/schema/engine-3/`), not a schema's `$id` as D82 says, and `docs/guides/deployment.md` shows a one-line output the command never prints. |
| 6.4.3 | `docs/guides/cases.md` gives the schema's `$id` as `engine-2`; the committed schemas, `ENGINE` and the conformance suite say 3 (D60). |
| 6.2.1 | D74 adds a sixth kind of step (`case`) without saying it adds to the Simplifications' kinds or to D13, as D41 did for `wait`; the glossary's "Step" row still lists four. |
| 5.1 | The quickstart, followed to the letter, fails in six places: three commands that don't exist, `uv run pytest` as printed, a step `ventoux check` refuses, `ventoux diff` with no arguments; and it meets twelve concepts beyond the five principle 5 promises (see also 6.4.2). |
| 5.4 | `run_case` plays a project's own case under the development catalog unless given `catalog=`, which the cases guide never names, and the refusal ("has no role") names the wrong cause. |
| 5.5 | `start_case` given the builder's `Case` raises a bare `AttributeError`, after the case ID is spent; `run_case` accepts the same object. |
| 5.6 | The releases guide's `environment_worker(...)` snippet is a `TypeError`: `audit` is required and the snippet leaves it out. |
| 5.7 | `report` just after `start_case` on a release, in an environment, says `draft` with an empty history, where the cases guide asserts the release at once. |
| 5.2 | No document says how to install the package or start a local Temporal server (with 6.4.1). |
| 6b.2 | D76's own example says an answer that approves `pay` and so starts it is one record, `approved`, `admitted`, `started`; a run gives `approved`, `started`, and the same decision's dated line says `admitted` is an approval asked. |

### Minor

| # | Finding |
|---|---|
| 1b.7 | Whoever's answer reaches the milestone a step requires approves that step; D39 records this on purpose, and nothing tells an author which of two equivalent definitions they wrote. |
| 1b.11 | A retry stopped by a lapsed approval says "a new approval is needed", and no retry can ask for one when the change came from a task answered again (D23, D25). |
| 1c.14 | A case with no parent closes on a raw `close_by_parent` signal, with any reason and nobody named. |
| 3.8 | `ventoux doctor` says "each certificate in date" of a certificate that isn't valid yet (D81). |
| 3.9 | A role registered twice takes the second `approves`, looser included, with no error (D22). |
| 3.10 | An expression result too small for decimal128 is zero with no error, so `a * a > 0` is false for a tiny positive `a`; a result too large is an error (D20). |
| 2.3 | A case workflow's class settings (`events_per_run`, `audit_bound`) decide where a recorded run switches or holds, and nothing records them: lowered, recorded runs no longer replay, failing closed with nothing naming the cause (D27, D77). |
| 6.6.1 | 457 of `main`'s 574 commit messages name an AI model version, and 501 carry a session link (the review's rule on names; see also 6.6.2 and 6.6.3: three mentions of an AI coding product in tracked files, and 54 commits under an address that isn't a no-reply one). |
| 6.4.4 | Guides and 11 docstrings still name "the Ventoux API" and "the inbox" as what the reader has; D79 re-reads decisions only. |
| 6.4.5 | Two rows of "Promises" tables (layers 18 and 20) name tests that no longer exist. |
| 6.2.2 | The glossary's "Catalog" row lists resolvers, which D30 puts in `tooling`, and omits systems, option checks and document stores. |
| 6.2.3 | The brief's status line says "decisions D1–D26"; it holds D1 to D83. |
| 5.8 | With the registry's worker not running, `environment create` reports success, `activate` gives Temporal's raw words after 30 seconds, and `environment check` doesn't return. |
| 5.9 | `report` on a handle from Temporal's client is a `CaseReport` while the case is open and a plain `dict` once closed. |
| 5.10 | Guides run commands on the repository's `examples/` folder, which an installed wheel doesn't have, without saying so. |
| 6b.3 | An age has no upper bound: an `sla` of a 30-digit number of days is read, validated and run in memory, and raises `ValueError` as the duration a workflow timer's wait is written into (D44 states no bound). |
| 6b.4 | Three quoted wordings are printed slightly otherwise: D55's "Looser:", D74's `closed by its parent: …`, and D50's `same behaviour as refund 2`, which is said only for a revert to an older release. |
| 4.7 | Small bounds nobody tests: a form number may be an infinite decimal, an option or attachment may be the empty text, and four more. |
| 4.8 | Three rules on Temporal survive their own test files: the forget request's identifier check, the hold at exactly 256 KB, and a boolean read as a carried time. |

### Where the brief reads against itself (found in pass 1; proposals only)

- D32 says "every form value in the answers people sent" goes with forgetting, while D76 keeps a
  non-sensitive form value in clear in the state and the audit store (pass 1, part c).
- D74 adds the step kind `case`, and the glossary and "Simplifications adopted" still list four
  kinds (finding 6.2.1).
- D74 says a parent's close "closes the child through D40's one place", while D17, D26 and D40 say
  a failed run is never cancelled by a milestone or stopped by a rule (finding 1b.6).


---

## Pass 1, part a: trust and provenance, on the in-memory runtime

Every run below was made at `ab909df` (the review branch; `git diff 3edb471 ab909df -- src tests
docs examples scripts pyproject.toml` is empty, so the source is `3edb471`). Each probe is run from
the repository root with `uv run python reviews/2026-11/probes/<name>.py`.

Cases are built as plain JSON definitions and run through `ventoux.testing.run_case` with the
development catalog. Where a probe reaches past the supported names it says so in its docstring:
`ventoux.case.definition.parse_case` and `ventoux.case.validate.validate_case` (to ask the check
what it says of the same definition), and, in one probe only, `ventoux.temporal.carried` and
`ventoux.case.memory.run_case_in_memory` (there is no supported door to the carried state).

The guarantees I tested, in my own words, from the brief:

1. Untrusted data never reaches an input whose policy refuses it, as a value (D12, D21, D29) or
   by choosing whether the value is sent (D39).
2. Untrusted data never decides: it reaches no milestone, stops no step, closes no case and
   chooses no plan's path, directly, through a moment, through a run it steered, or through what
   such a run gives (D38, D40, D42, D43, D44, D49).
3. Untrusted data may add an approval, never remove one (D11, D39).
4. Every value keeps where it came from across every route: a rule's `set` (D42), an edit (D52), a
   migration (D53), continue-as-new (D27), a child case in both directions (D74), a list's items
   (D73). A developer's `untrusted:` mark is added whoever gives the value (D12, D41).
5. Anything unknown is an error: a source spelling, an operator, a missing field (D20, fail closed).

### Findings

#### 1a.1 A repeated step keeps nothing of what steered its runs (breaks a promise)

A step with `for_each` (D73) starts its runs without recording what steered them, and without the
"untrusted condition can't choose what is sent" check. So, for a repeated activity step, on the
customer's word alone: its trusted-only input is sent; a rule on its start reaches a milestone and
closes the case; a step that requires it reaches a milestone and closes the case; and when it
requires a steered run itself, it still sends its trusted-only input. The same definitions with a
plain step (the control, in the same probe) are refused at each of the four places. The check
(`validate_case`) reports the same errors for the repeated step as for the plain one
(`INPUT_POLICY`, `UNTRUSTED_TRIGGER`), so validation claims "never" and the runtime does it; D34
says the runtime refuses whether or not validation ran.

Promises touched:
- D39: "if the step's `when`, or the `when` of the rule that started it, read an untrusted (or
  unrecognised) source, each input whose policy refuses that source is refused".
- D43: "A run keeps what steered its start: the untrusted (or unrecognised) sources of every
  condition that let it start: its own `when`; ... and what steered the latest done run of each
  step it requires, unless that step is a task. ... Every kind of step keeps it".
- D43: "A rule on its `started` moment counts it as read by its condition: a rule that reaches or
  stops doesn't act".
- D73: "Its `when` is read for each run, with its item" (D73 records only the false side, an item
  kept from starting, as a deliberate limit; nothing records the true side as one).

Proof (`uv run python reviews/2026-11/probes/p1a_repeated_step_steering_lost.py`, trimmed):

```
=== 1. the step's own untrusted `when` and a trusted-only input (D39)
--- plain step (control)
    check: [('error', 'INPUT_POLICY', 'steps.draft.inputs.to_customer'), ...]
      draft#1 failed: letters.draft@2 takes to_customer only from a system or a person, never from untrusted data, and draft's condition reads note (untrusted:customer)
--- repeated over lines
    check: [('error', 'INPUT_POLICY', 'steps.draft.inputs.to_customer'), ...]
      scheduled draft.1#1: letters.draft@2 (to_customer from system:opener; template from the case), key memory/draft.1#1
      scheduled draft.2#1: letters.draft@2 (...)
=== 2. a rule on the steered start reaches a closes_when milestone (D43)
--- repeated over lines
    check: [..., ('error', 'UNTRUSTED_TRIGGER', 'rules.close_it.on')]
    status: closed | milestones: ['settled']
      close_it#1 on started draft: reaching settled
=== 3. a step requiring the steered run reaches a milestone (D43)
--- plain step (control)
      settle#1 failed: ... and settle requires draft, and draft's condition reads note (untrusted:customer)
--- repeated over lines
    check: [('error', 'INPUT_POLICY', 'steps.settle.inputs.to_customer'), ('error', 'UNTRUSTED_TRIGGER', 'steps.settle.reaches'), ...]
    status: closed | milestones: ['settled']
      scheduled settle#1: letters.draft@2 (to_customer from system:opener; ...)
      reached settled
=== 4. a repeated step requiring a steered run sends a trusted-only input (D43)
--- plain step (control)
      draft#1 failed: ... and draft requires listen, and listen's condition reads note (untrusted:customer)
--- repeated over lines
      scheduled draft.1#1: letters.draft@2 (to_customer from system:opener; ...)
RESULT: BROKEN - an untrusted `when` chooses what a repeated step sends to a trusted-only input; a rule on a repeated step's steered start reaches a milestone; a step requiring a repeated step's steered runs reaches a milestone; a repeated step requiring a steered run sends what a plain step is refused
```

Where: `src/ventoux/case/runtime.py`, `start_item` passes `()` as what steered the run to
`checked_inputs` and never sets the run's `steered`; `ran` adds the `started` moment with nothing
carried. `required_steering` then finds nothing on a repeated step's done runs.

Proposed fix, in words: a repeated run is started as a plain run is: its steering is worked out
(its own `when` read with its item, and what steered the runs it requires), checked against each
input's policy, and kept on the run; a step requiring a repeated step is steered by every item's
latest done run, not one. A negative test per place the control refuses. Whether the items of an
untrusted list themselves steer their runs (the run exists only because the customer listed the
item) is a decision to record: see finding 5.

#### 1a.2 A case step keeps nothing of what steered it, and the check is silent on its `reaches` (breaks a promise)

A case step (D74) whose `when` reads the customer's note, or which a rule starts on the customer's
word, opens its child with nothing carried. Its own `reaches` apply, a rule on its start reaches,
a timer set on its start reaches, a value set on its start is clean, its outcome is
`case:<child>` alone, a step requiring it reaches, and the child sends its trusted-only input
though an untrusted condition chose that it be sent. The same definition with a plan step (the
control) is refused at every one of these. Unlike finding 1, the check is also silent in one
place: it reports no `UNTRUSTED_TRIGGER` at the case step's `reaches`, where it reports one for
the plan step.

Promises touched:
- D74: "A case step opens a child case ... It takes what a plan step takes".
- D43: "A steered run reaches nothing. An activity, a workflow, a plan or a wait run that
  untrusted data steered is done, and its `reaches` aren't applied" and "Every kind of step keeps
  it"; "What only untrusted data made exist is untrusted. A steered activity's, workflow's or
  plan's outcome and outputs carry what steered the run".
- D39: "A plan step carries its condition's untrusted sources beside its fields, never inside
  them."
- D44: "A timer set on a run's start carries what steered the run".
- D74: "a child that closed by itself gives `done` with `case:repair` alone" (true only of a child
  nothing steered).

Proof (`uv run python reviews/2026-11/probes/p1a_case_step_steering_lost.py`, trimmed):

```
=== write is a plan step (control)
check:
   error UNTRUSTED_TRIGGER rules.begin.on
   error UNTRUSTED_TRIGGER steps.write.reaches
   error UNTRUSTED_TRIGGER steps.follow_up.reaches
history:
    begin#1 on started write: reaches nothing: its moment comes from untrusted data: write's condition reads note (untrusted:customer), and untrusted data can't decide
    mark#1 on started write: setting seen, from system:opener, untrusted:customer
    write#1 failed: write@1 stopped: letters.draft@2 takes to_customer only from a system or a person, never from untrusted data, and write's condition reads note (untrusted:customer)
milestones: [] | sources: {'write.outcome': [], 'seen': ['system:opener', 'untrusted:customer']}

=== write is a case step
check:
   error UNTRUSTED_TRIGGER rules.begin.on
   error UNTRUSTED_TRIGGER steps.follow_up.reaches
   warning KEPT_FROM_STARTING steps.write.when
history:
    started write#1: case write@1 (email from system:opener), run memory/write#1
    begin#1 on started write: reaching began
    mark#1 on started write: setting seen, from system:opener
    write#1 done: write closed, nothing left to do; reporting nothing
    reached written
    scheduled follow_up#1: orders.lookup@1 (order_id from system:opener)
    reached followed
child's history:
       scheduled letter#1: letters.draft@2 (to_customer from system:opener; template from the case), key memory/write#1/letter#1
milestones: ['began', 'followed', 'written'] | sources: {'write.outcome': ['case:write'], 'seen': ['system:opener']}

=== a rule starts the case step on the note; a timer is set on its start
    start_write#1 on opened: starting write
    set chase: 1d after started write#1, due 2026-01-02T00:00:00Z
    chase#1 on 1d after started write#1: reaching began
RESULT: BROKEN - on the customer's note the case step's run and rule reached ['began', 'followed', 'written']; the child sent its trusted-only input under the untrusted condition; write.outcome doesn't carry untrusted:customer; a value set on its start doesn't carry untrusted:customer; a timer set on a rule-started, steered case step's start reached a milestone; the check is silent where it refuses the plan step: [('UNTRUSTED_TRIGGER', 'steps.write.reaches')]
```

Where: `src/ventoux/case/runtime.py`, `open_child` never sets the run's `steered` (the wait, task
and plan branches of `start` each do), and `OpenCase` carries no steering as `StartPlan` does.
The check's "steered run's reaches" claim in `src/ventoux/case/flow.py` covers call, plan and wait
steps.

Proposed fix, in words: a case step's run keeps what steered it, as a plan step's does; its
`reaches` aren't applied when steered; its outcome and reported fields carry what steered it
beside `case:<child>`; and the child's opening carries the untrusted sources that steered it, so
the child checks them against each of its inputs' policies, as a plan does (a decision to record
under D74: how far into the child the steering goes, since a child has tasks, where D43 says it
ends). The check claims the same at `steps.<case step>.reaches`. This is the pure runtime; D75's
Temporal side uses the same `decide`.

#### 1a.3 A child case's field declared untrusted loses its mark when its parent gives the value (breaks a promise)

When a parent opens a child, each field takes the sources the parent gave and nothing else: the
`untrusted:<label>` the child's own definition declares on the field is not added. The same child
opened on its own adds it. So a child whose developer wrote "whatever lands in `summary` was
written by a model" reaches a milestone on it, sends it to a trusted-only input, and reports it
back clean; the parent then sends it on to a trusted-only input, at a place where the check of
the parent says that input is refused in every case.

Promises touched:
- D12: "untrusted:*label* (declared by the developer on a field)" and "Provenance follows the
  content, not the system that carries it."
- D41: "a field's declared `untrusted:<label>` is added whoever sends it, as for the opening's
  values (D12)".
- D53: "Values keep their sources, never re-stamped; a mark the target declares is added (D12,
  D43)" (a migration adds a declared mark, and the probe `p1a_migration_keeps_distrust.py` shows
  it does; a child's opening doesn't).
- D74: "The child is given an opening, its fields read from the parent's case file, each with its
  sources".

Proof (`uv run python reviews/2026-11/probes/p1a_child_field_mark_dropped.py`, trimmed):

```
=== the child opened on its own (control)
    flag#1 on opened: reaches nothing: its condition reads summary, from untrusted:llm, and untrusted data can't decide
    letter#1 failed: letters.draft@2 takes to_customer only from a system or a person, never from untrusted data, and this value comes from summary (system:opener, untrusted:llm)
    summary's sources: ['system:opener', 'untrusted:llm']
=== the same child opened by a parent, from a trusted field
check of the parent:
    error INPUT_POLICY steps.reply.inputs.to_customer: ... this value comes from intake.summary (case:intake, the opener, untrusted:llm): use a value a system or a person gave
--- intake, as the parent's child
    flag#1 on opened: reaching urgent
    scheduled letter#1: letters.draft@2 (to_customer from system:opener; template from the case), key memory/intake#1/letter#1
    summary's sources: ['system:opener']
--- parent
    scheduled reply#1: letters.draft@2 (to_customer from case:intake, system:opener; template from the case), key memory/reply#1
RESULT: BROKEN - a child's field declared untrusted:llm loses its mark when its parent gives the value: ...
```

Where: `src/ventoux/case/runtime.py`, `open_case`: `state.sources[name] = marked(case, name,
origin) if given is None else given`.

Proposed fix, in words: at a child's opening each value takes the sources its parent gave plus
the mark the child's field declares, as the check already assumes. One negative test: the child
above, opened by a parent from a trusted field, refuses its letter.

#### 1a.4 A `max_age` refresh hands back a clean run for a step that only untrusted data started (breaks a promise)

A read step that nothing starts but a rule, on the customer's text, is steered: its run reaches
nothing, a rule on its start reaches nothing, and its output carries `untrusted:customer`. If
another step needs that output at most a day old and reads it a day later, the engine fetches it
again, and the new run carries nothing: its `reaches` apply, the rule on its start reaches, the
output is `system:orders` alone, and the trusted-only input that was refused the day before is
sent. Without the customer's text none of it happens (the output never exists, and the reading
step fails). So waiting a day turns what untrusted data made exist into trusted data. The check
reports all three as errors that can never happen.

Promises touched:
- D43: "What only untrusted data made exist is untrusted" and "A refresh also keeps what steered
  the step it fetches for."
- D38: "Untrusted data informs; it never decides".
- D33 (a refresh is the engine's own start, with no person in it; D39: "a refresh lands with no
  person in it").

Proof (`uv run python reviews/2026-11/probes/p1a_refresh_launders_steered_run.py`, trimmed):

```
check:
   INPUT_POLICY steps.confirm.inputs.to_customer: ... this value comes from check.status (system:orders, untrusted:customer)
   UNTRUSTED_TRIGGER rules.begin.on: ... so it never reaches began
   UNTRUSTED_TRIGGER steps.check.reaches: ... so it never reaches checked
=== the text, then the review at once
    check#1 done, giving status from system:orders, untrusted:customer
    check#1 reaches nothing: on_text#1's condition, which started check, reads said.text (untrusted:customer), and untrusted data can't decide
    confirm#1 failed: letters.draft@2 takes to_customer only from a system or a person, never from untrusted data, and this value comes from check.status (system:orders, untrusted:customer)
    milestones: ['reviewed']
=== the text, then the review three days later
    refreshing check.status for confirm: obtained 3 days ago, at most 1 day
    scheduled check#2: orders.lookup@2 (order_id from system:opener)
    begin#2 on started check: reaching began
    check#2 done, giving status from system:orders
    reached checked
    scheduled confirm#1: letters.draft@2 (to_customer from system:orders; template from the case), key memory/confirm#1
    reached confirmed
    milestones: ['began', 'checked', 'confirmed', 'reviewed']
=== no text; the review three days later
    confirm#1 failed: to_customer can't be evaluated: check.status has no known sources
    milestones: ['reviewed']
RESULT: BROKEN - a day's wait launders what the customer's text started: ...
```

Where: `src/ventoux/case/runtime.py`: the refresh is scheduled with `required_steering` of the
step it fetches for, and `steering` of the refreshed step as it reads now; what a rule's start
carried (`proposed_by_rules`) was spent when the first run started, so nothing of it is left. A
refreshed step steered by its own `when` is steered again (its `when` is read again); only what
came by a rule's start, or that rule's moment, is lost. I tried the other direction too (a
refresh fetched for a step steered by its own `when`): the refresh runs before the `when` is
read, whatever the note says, so the note decides nothing there.

Proposed fix, in words: a refresh's run also keeps what steered the run it fetches again (the
step's latest counted run), since without that run there would be nothing to refresh. One
negative test: the probe's second timeline reaches only `reviewed` and refuses the letter.

#### 1a.5 Untrusted data decides by making a person's work not exist, and the absence reads as trusted (weakens a promise; to be judged against D48 and D73)

Two shapes, both with the check silent (one `KEPT_FROM_STARTING` warning in the first, nothing in
the second). I report them as one finding of lower severity because each rests on a recorded
limit, taken one step further than the limit says.

(a) A task starts only when the customer's note says go (D48 allows untrusted data to keep a step
from starting). A rule on another task's answer reaches the closing milestone when
`review.outcome` doesn't exist. With the note saying stay, the rule reaches and the case closes:
the customer's note alone removed the review and so decided. The engine reads the unset
`review.outcome` as a person's (its only writer is a person), though nobody answered. For an
activity kept from starting the same rule is refused, because the unset output is read as
carrying what would steer its run (`p1a_expression_forms_never_decide.py`); a task's is not.

(b) A task repeated over a list the customer typed, and a step that requires it and reaches the
closing milestone. With any line, a person inspects each before the step runs. With an empty
list the requirement is met at once (D73) and the case closes with no person in it.

Promises touched:
- D38: "Untrusted data informs; it never decides"; D43: "a milestone is reached only by a trusted
  decision or a person"; "A person is where it ends".
- The recorded limits: D48/D38 "untrusted data may keep something from happening: a step's
  `when`, or a rule's condition, that reads untrusted data and is false keeps the step from
  starting"; D73 "`requires` is met once every item's latest run is done, at once for an empty
  list, the history saying so". Neither says that the absence may then reach a milestone.
- D39: "A field the condition names that isn't set yet counts what any of its writers could give,
  read from the definition (fail closed)".

Proof (`uv run python reviews/2026-11/probes/p1a_absence_of_people_decides.py`, trimmed):

```
=== 1. a rule on the absence of a task's answer, the task kept from starting by the note
check: [('warning', 'KEPT_FROM_STARTING', 'steps.review.when')]
--- the note says go
    ana answered review#1 ok as support
    unreviewed#1 on answered hold: its condition is false
    closed: nothing left to do; settled not reached
--- the note says stay
    unreviewed#1 on answered hold: reaching settled
    review not started: its condition reads note, from untrusted:customer, and is false
    closed: settled reached
=== 2. a step requiring a task repeated over a list the customer typed
check: []
--- two lines: open; waiting for ['inspect.1 by support', 'inspect.2 by support']
--- no lines: closed; waiting for []
    inspect: lines has no items, so it has no runs
    scheduled settle#1: letters.draft@2 (to_customer from system:opener; template from the case), key memory/settle#1
    reached settled
    closed: settled reached
RESULT: BROKEN - ...
```

Proposed fix, in words: decide and record it. Either (i) say in D48 and D73 that these are
accepted (an author who reads an absence, or requires a repeated task, on untrusted data gets a
warning from the check, as `KEPT_FROM_STARTING` warns today); or (ii) make the absence carry it:
an unset outcome or form field of a task whose start untrusted data steers reads as steered (as
an activity's already does), and a step requiring a step repeated over an untrusted list is
steered by the list. (ii) is the fail-closed reading.

### What held

- Every expression form in a deciding rule (`exists`, `if`, `in`, `cat`, a short-circuited `or`,
  `count`, `count ... where`, `sum`), and the absence of an output only a steered activity would
  write (by its own `when`, by a rule's start, behind a requirement): the rule reaches nothing
  whatever the note says, and the check refuses each with `UNTRUSTED_TRIGGER`.
  `p1a_expression_forms_never_decide.py`.
- Timers, events, `set`, an approval's `when` and a plan's transition in one case: a timer on a
  steered task's start and a rule reading the payload reach nothing; a timer on an arrival alone,
  a person's answer and a timer on that answer reach; a value set under an untrusted condition
  carries it; the approval is asked whatever the set flag says, and also when the flag isn't set
  and the condition is `exists flag`; the plan stops at the transition that reads the flag.
  `p1a_timers_events_set_approval_plan.py`.
- A migration to a release that removes `untrusted` marks, removes a steered step's condition and
  renames the field: every value keeps its sources under its new name, the run steered before
  the migration still reaches nothing, the new rules reach nothing, the letters are refused, and
  a mark the target adds is added to the value already held. `p1a_migration_keeps_distrust.py`.
- Continue-as-new (pure functions only): the state reads back equal through the exact payload
  converter; afterwards a held steered run, a rule's start waiting for its approval, an
  operator's retry of that start once refused (approved a second time), a timer on a steered
  start and a set value all still carry `untrusted:customer`, and nothing is reached.
  `p1a_steering_crosses_continue_as_new.py`.
- A child case, round trip, for values (not steering): the customer's note given to a child stays
  `untrusted:customer` in the child, through a value the child's rule sets, and back in the
  parent with `case:sub`; it reaches nothing and no trusted-only input on either side; a child a
  person closed gives `sub.outcome` from `person:ana, case:sub`.
  `p1a_child_report_round_trip.py`.
- Steering crosses a `sequence` (an implied requirement); an edit to the value already held is
  refused however the number is written (250, 250.00), and a real edit keeps the field's declared
  mark beside its two people. `p1a_sequence_and_edit.py`.
- Odd source spellings (`trusted:x`, `Untrusted:x`, ` untrusted:x`, `untrusted:`, `untrusted`,
  empty, `System:orders`, `systemx:orders`, `person:`/`case:` on a field or an output, an
  unregistered label or system): refused when a case field or a contract output declares them;
  given to a plan with the public `sourced(...)`, refused by a trusted-only input and at a
  transition as "a source Ventoux doesn't recognise"; `only_from` refuses `case:repair`,
  `person:ana` and a value with no source. `p1a_odd_source_spellings.py`.
- Unreadable expressions (a missing field, a number compared with a text, a division by zero, a
  text added to a number, `false and <missing>`, `true or <missing>`) in a step's `when`, a rule's
  `when`, an approval's `when`, a rule's `set` value, a child case's input and a repeated step's
  `when`, with the runtime alone: 36 of 36 stop what they guard and need attention, none reads as
  false or as "no approval"; an unknown operator, a binary float, `each` outside a repeated step
  and `now` are refused when read. `p1a_unreadable_expression_never_false.py`.
- Inside the BROKEN probes, the controls held: a plain step and a plan step are refused at every
  place where the repeated step and the case step are not.

### Unproven

- Findings 1, 2 and 4 are in `decide`, which the Temporal case workflow also runs, so I expect
  the same on Temporal; I ran nothing there (out of this pass's scope).
- A child's list field with a declared mark, given by its parent, should lose its mark by the
  same line as finding 3, and its repeated step's `each.<field>` with it; not run.
- After a migration that renames a field, a run steered before it still says the old name
  ("look's condition reads note") in its later lines; seen in the migration probe's output,
  harmless as far as I can tell, and I did not look for a promise it breaks.
- An edit (D52) of a value that is untrusted only through its rule's reads or through a child's
  opening (no mark declared on the field) becomes its two people's alone. D52 says so ("An edited
  value is the decision of its two people"; only a declared mark is kept), so I did not count it;
  I did not run it.

### Unchecked

- Temporal workers, people and approvals beyond what steering needs, assignment rules (D71),
  forgetting and audit: another reviewer's passes.
- Workflow steps (D6, D29) combined with the features above, options and attachments (D67, D68)
  fitting a `reference()` input together with `only_from`, dates (D66), and a required step
  (D72) behind a steered one: not reached in the time. I read the code paths for the first two
  and saw the plain-step machinery in use, but ran nothing, so I claim nothing.
- The TypeScript evaluator and the conformance suite (D20): not in this pass.


---

## Pass 1, part b: people, approvals, lifecycle and AI, on the in-memory runtime

Every probe was run at commit `ab909df` (the review branch; `git diff 3edb471 ab909df -- src tests docs
examples` is empty, so the source is 3edb471). Each is run from the repository root with
`uv run python reviews/2026-11/probes/<name>.py` and ends with a `RESULT:` line. All run on the pure
runtime through `ventoux.testing.run_case` and the development catalog; where a probe reaches past the
supported names its first line says so (`decide`, `ventoux.authoring`, `validate_case`, `package`).

Seventeen probes: ten report BROKEN (eight broken promises, one unenforced non-negotiable, one
misleading behaviour), seven report HELD (they cover about 80 separate attempts).

### Findings

#### 1b.1 A person who answers a wait inside a plan step decides the plan's outcome, then approves the step that outcome starts (breaks a promise)

A plan step's outcome (`done` or `failed`) lands in the case file with the source
`system:<plan>` only. When a person's answer to a wait inside the plan chose which final state
the plan reached, that person is in nobody's sources, so "someone else" doesn't see them: they
approve the high-risk step whose `when` reads `<step>.outcome`. The same decision written as a task
of the case excludes them.

- Promise: D11, "**"Someone else" is computed from provenance.** Excluded from approving a step:
  every person whose answer flows into the step's inputs or into its run condition (`when=`)".
  D74 states the cause as a fact: "as a plan's outcome carries `system:refund-order@1`", and for
  a child case draws the opposite conclusion: "which reason was chosen is a person's act, as a
  task's outcome is ... and the closer approves nothing that outcome decides (D11)".
- Proof: `uv run python reviews/2026-11/probes/p1b_plan_wait_answerer_approves.py`

  ```
  task `review` answered by sam, pay approved by sam
      -> REFUSED (AnswerRefused): sam set review.outcome, which decides whether pay runs, so cannot approve it
  plan wait `decide` answered by sam, pay approved by sam
      -> ACCEPTED
         | sam answered pay.approval#1 approve as support-lead
         | scheduled pay#1: payments.refund@2 (...)
    sources of triage.outcome: ['system:triage@1']
  RESULT: BROKEN - ...
  ```
- Proposed fix: the plan's end report carries who answered the waits that its path passed
  (the audit already receives a plan's decisions with `by`, D77), and the step's outcome gains
  `person:<each>` beside `system:<plan>`, as a child's outcome gains `person:<closer>`.

#### 1b.2 In a child case, the parent's opener and the case step's proposer approve change requests (an edit, a skip) (breaks a promise)

The parent's exclusions cross into the child for step approvals (held, see "What held"), but a
change request in the child checks only `state.opened_by`, which is empty in a child, never the
exclusions that crossed. So the person who opened the parent, and the person who proposed the case
step, approve an edit of a child's field and the skip of a child's failed run. In one case the
opener is refused both.

- Promise: D74, "the parent's exclusions cross: the parent's opener and the step's proposer
  approve nothing in the child (D25)". D52, "**Never approved by its proposer, nor by the person
  who opened the case** (D25: a change decides as much as a step's run) ... a skip never by anyone
  who may not approve the run it skips".
- Proof: `uv run python reviews/2026-11/probes/p1b_child_change_request_by_parents_opener.py`

  ```
  lee opened the refund; kim proposes an edit, lee approves it
      -> REFUSED (AnswerRefused): lee opened the case, so cannot approve a change to it
  lee opened the PARENT; in the child kim proposes an edit of cost, lee approves it
      -> ACCEPTED
  olga opened the PARENT; in the child tell#1 failed, omar proposes its skip, olga approves it
      -> ACCEPTED
  kim PROPOSED the case step; in the child lee proposes an edit of cost, kim approves it
      -> ACCEPTED
  olga PROPOSED the case step; in the child tell#1 failed, omar proposes its skip, olga approves it
      -> ACCEPTED
         | applied case.change#1: tell#1 skipped by omar, approved by olga
  RESULT: BROKEN - approved and applied inside the child: edit by parent's opener; skip by parent's opener; edit by step's proposer; skip by step's proposer
  ```
- Where: `case/requests.py`, `excluded()` and `skip_excluded()` read `state.opened_by` and
  `run.excluded`; `case/runtime.py` `may_not_approve()` builds `run.excluded` from `state.opened_by`
  and the proposers, never from `state.excluded`. `answers.why_excluded()` does read
  `state.excluded`, which is why step approvals hold.
- Proposed fix: one function says who a case excludes from every approval (its opener, and
  whoever crossed from its parent), and the change request's check, the skip's check and
  `may_not_approve` all ask it. Not tried: a migration proposed inside a child (the same
  `excluded()` decides it).

#### 1b.3 A child's reported field named `outcome` replaces `<step>.outcome` in the parent with a person's free text, which then reaches the step advisor (breaks a promise)

A contract may not declare an output named `outcome` ("an output can't be named outcome:
<step>.outcome is the step's outcome"). A child case may: `"reports": ["outcome"]` over a text
field is accepted when read and by validation. When the child closes, its report is written after
its outcome under the same name, so `repair.outcome` holds whatever a person typed in the child's
form. The parent's `when` on `repair.outcome` then reads that text (in the probe the payment that
runs "when the repair closed by itself" never starts, and nothing fails or says why), and the step
advisor is sent it as the run's outcome.

- Promises: D74, "`repair.outcome`, which is `done` or the close reason a person used,
  type-checked against the child's reasons"; "the engine reads each child's outcomes and reported
  fields from them, so `repair.cost` is type-checked at runtime as at validation". D61, "**What it
  is shown: no case-file value at all** ... Never a value, trusted or not".
- Proof: `uv run python reviews/2026-11/probes/p1b_child_report_named_outcome.py`

  ```
  validation of the parent with this child says: ['OUTCOME_UNREAD: ...', 'MAY_BE_UNSET: ...']
    the child's own ending: closed: nothing left to do
    repair.outcome in the parent is the canary: True
    its sources: ['case:repair', 'person:sam']
    pay (when repair.outcome == 'done') waits or ran: ['note by support'] False
    the request the step advisor's model would read holds the canary: True
  RESULT: BROKEN - validation accepts a child that reports a field named outcome; repair.outcome holds the field's text, not `done`, so pay never starts; the step advisor is sent the person's text as the run's outcome
  ```
- Proposed fix: refuse a field named `outcome` in `reports` when the child is read (the rule a
  contract's outputs already follow), and have `child_ended` refuse a report that names it
  (fail closed at runtime too, since the runtime depends on nothing validation did). The advisor's
  `outcome_of` could also check the value against the outcomes its step declares.

#### 1b.4 A sensitive attachment's ID, and a sensitive option, leave the engine unwrapped in the command that asks their check (breaks a promise)

An attachment or an option "may be sensitive, as any field". When a person's answer gives one,
the engine builds the check's command from `str(plain(form[name]))`: plain text. Every other
sensitive input stays `Sensitive` in its command (the control in the probe). The value is kept
wrapped in the case file afterwards, so only the check's call carries it in clear.

- Promise: D31, "**The value is wrapped wherever it goes.** In the state it is `Sensitive` ... An
  input computed from it is wrapped too, so it reaches an activity or a plan encrypted"; D68
  (layer note), "a `sensitive` attachment's ID is sealed and forgotten with the case".
- Proof: `uv run python reviews/2026-11/probes/p1b_sensitive_attachment_check_unwrapped.py`

  ```
  review#1.receipt asks documents.issued@1 with attachment = str(doc-7f3a)
  review#1.branch asks branches.holds@1 with option = str(BR-0142)
  in the case file the two are kept as: Sensitive Sensitive
  control: tell#1 asks letters.draft@2 with to_customer = Sensitive(‹sensitive›)
  RESULT: BROKEN - ...
  ```
- Where: `case/runtime.py`, `checked_set()` and `answer_task()` (`Schedule(..., {shape.asked:
  value})`). On Temporal `CaseWorkflow.run_activity` passes `command.inputs` to
  `workflow.execute_activity` as they are, so the ID would be written to the history in clear and
  outlive the key; I did not run that (see Unchecked; a probe named
  `p1c_sensitive_check_in_history.py` from another pass appears to cover it).
- Proposed fix: keep the form's wrapper for a sensitive field when building the check's
  command (`kept_sensitive`, as an activity's inputs do), and add the negative test.

#### 1b.5 A value hidden by `visible_to` in a parent is shown to the roles it is hidden from once it is a child case's opening field; a child's hidden field comes back the same way (breaks a promise)

Inside one case, a rule copying a hidden field into an open one is refused when the definition
is read. Across a case step nothing checks it: the parent's `fraud_score` (seen only by `fraud`)
given to the child's field `score`, which declares no `visible_to`, is read by `support` in the
child's view. Validation says nothing. The reverse also happens: the child's `margin` (only
`fraud`) is reported and `support` reads `repair.margin` in the parent.

- Promises: CLAUDE.md non-negotiable, "Policies can be made stricter downstream, never looser (a
  case tightening a contract, untrusted data adding an approval, a view hiding more than its
  source)". D42, "A set field is seen by no role that can't see every field it was computed from
  (D30): a view may hide more than its source, never less." D74 applies it to sensitive values
  only: "A sensitive value enters a child only into a sensitive field, and a report carries no
  sensitive field, for now ...: a view hides more than its source, never less." The check built
  for it (`sensitive_to_child_issues`) reads `sensitive` and never `visible_to`.
- Recorded limit that touches the second half: D48, "`visible_to` narrows values, never what the
  case did. Milestones, step runs, the history, and outcomes and outputs are seen by every role
  the case names". A report lands as a step's outputs, so the parent showing `repair.margin` can
  be read as inside that limit; the first half (a parent's field value copied into a child's
  field) is no output of anything, and I found no recorded limit for it (searched D30, D42, D48,
  D74 and `docs/layers/18-lifecycle.md`).
- Proof: `uv run python reviews/2026-11/probes/p1b_hidden_value_into_child.py`

  ```
  Control: a rule sets an open field from fraud_score (seen only by fraud)
      -> REFUSED (CaseInvalid): rules.copy.then.set.flag: flag is seen by every role of the case, and is set from fraud_score, which only fraud sees: let only fraud see flag
  Attack: the same value given to the child's open field `score`. Validation says of it: nothing
    parent, as support sees it: ['Fraud score: hidden (needs fraud)']
    child, as support sees it:  ['Score given by the parent: 77, from system:opener']
    child, as support sees it:  ['Our margin: hidden (needs fraud)']
    parent's values for support include repair.margin: 41
  RESULT: BROKEN - ...
  ```
- Proposed fix: the check that refuses a sensitive input into a non-sensitive child field also
  refuses an input reading a field with `visible_to` into a child field seen by a role outside
  it; decide and record whether a child may report a field that declares `visible_to` (refuse it
  as a sensitive one is refused, or write it into D48's limit by name). Not tried: the same
  value given to a plan step's field.

#### 1b.6 A parent closing by itself, or a parent's rule stopping the case step, cancels a failed run inside the child with no person (breaks a promise; the brief's texts pull against each other)

In one case, `closes_when` waits for a failed run, and a rule never stops one. Put the failed
payment in a child case and both happen automatically: the parent reaching its `closes_when`
milestone, or a rule's `stop` of the case step on a portal event, closes the child, and the
child's failed `parts#1` (a payment that may or may not have happened) is recorded `cancelled`.
No operator retried it, nobody skipped it with a second person, nobody closed anything, and
neither case is flagged.

- Promises: CLAUDE.md, "Nothing is skipped automatically: a failed step waits for a person."
  Cases guide (D34), "`closes_when` never cancels a step that needs attention: the case waits
  until an operator retries it, or a person closes the case with a reason." D40 table, "failed,
  needing attention | never stopped". D74, "**A child needing attention is the child's,** retried
  by its operators; the parent waits."
- The text it follows: D74, "A close, or a rule stopping the step, closes the child through D40's
  one place ... and the parent closes once the child has ended; a close never waits for a person
  (D48)." D48's sentence is about a workflow *waiting for people* (open tasks); it does not say a
  failed run is let go. So D74 as built contradicts D17/D34/D40 for a child's failed runs.
- Proof: `uv run python reviews/2026-11/probes/p1b_parent_auto_close_cancels_childs_failed_run.py`

  ```
  Control, one case: pay#1 failed, then `reviewed` (closes_when) is reached:
      status: open | needs attention: ['pay#1: payments.refund@2 failed with ConnectionError: ‹sensitive›']
  Attack 1: the failed payment is in the child; the parent reaches `reviewed` (closes_when):
         | parts#1 failed: payments.refund@2 failed with ConnectionError: ‹sensitive›
         | cancelled parts#1: closed by its parent: reviewed reached
         | closed: by its parent: reviewed reached
  Attack 2: a parent's rule stops the case step when the portal's event arrives:
         | cancelled parts#1: closed by its parent: stopped by withdraw#1
  RESULT: BROKEN - the parent's closes_when cancelled the child's failed parts#1 with no person (flags: none); ...
  ```
- Proposed decision (not mine to make): either a child holding a failed run holds its parent's
  automatic close and refuses a rule's stop, as a failed run does in one case (a person's close
  of the parent still closes both); or D74 says in words that a parent's close or stop lets a
  child's failed runs go, and both cases are flagged so a person looks at what may have been paid.

#### 1b.7 Whoever's answer reaches the milestone a step requires approves that step (minor: a recorded position, with nothing warning of it)

*Lead reviewer's note:* D39 records this side on purpose: "The person whose answer only brought the moment is not excluded, as a person whose run a step `requires` isn't; changing that would be one decision covering both." So this breaks no stated promise. It is kept as a minor finding because two definitions that decide the same thing exclude different people, and neither `ventoux check` nor the case map says which one an author has written.

`pay` is given only the opener's values and requires the milestone `approved`. The milestone is
reached by the review's `approve` outcome (`reaches`), or by a rule on the answer whose `when`
reads `review.outcome`. Either way sam's answer alone decides that the payment runs (a `reject`
pays nothing), and sam approves it. Write the same decision as `pay`'s own `when`, or as a rule
that *starts* `pay`, and sam is refused.

- Promise: D11, "Excluded from approving a step: every person whose answer flows into the step's
  inputs or into its run condition (`when=`)"; D39/cases guide, "Whoever's answer the rule's
  `when` read can't approve the run it starts ... the rule decided that the step runs, on their
  answer"; cases guide, "asking for a payment and approving it are two people's acts".
  `requires` on a milestone is not `when`, so the letter is kept; the stated reason is not, and
  two definitions that decide the same thing exclude different people.
- Proof: `uv run python reviews/2026-11/probes/p1b_milestone_route_around_someone_else.py`

  ```
  ... (when); sam approves pay
      -> REFUSED (AnswerRefused): sam set review.outcome, which decides whether pay runs, so cannot approve it
  ... (rule starts); sam approves pay
      -> REFUSED (AnswerRefused): sam set review.outcome, which decided that go#1 started pay, so cannot approve it
  ... (outcome reaches); sam approves pay
      -> ACCEPTED
  ... (rule reaches); sam approves pay
      -> ACCEPTED
    (outcome reaches) had sam answered `reject`: pay reached = False, waiting = []
  RESULT: BROKEN - ...
  ```
- Proposed fix: a milestone keeps who reached it (the person whose outcome's `reaches` named it,
  and whoever the reaching rule's `when` read), and a step is not approved by whoever reached a
  milestone it requires. If that is judged too wide (every later step would exclude the
  reviewer), record it in the brief as a deliberate limit and have `ventoux check` warn where an
  approval's step requires a milestone only one task's outcome reaches.

#### 1b.8 The person a step's `when` read is no longer excluded once the step is a plan step or a case step (weakens a promise)

D28 and D74 carry two exclusions into a plan or a child: the opener and the step's proposer (and
the code adds whoever a starting rule's `when` read). Whoever's answer the step's own `when` read
does not cross, so the reviewer whose `approve` let the payment's step start approves the payment
inside the plan, and inside the child.

- Promise: D11 (as in finding 7), and D28's own reason: "**The case's exclusions cross into the
  plan:** the person who opened the case, and the person who proposed the step's run, approve
  nothing inside it (D25). Otherwise a plan step would be a way around them." The list is two
  people; the purpose covers the third.
- Proof: `uv run python reviews/2026-11/probes/p1b_when_decider_crosses_into_plan_and_child.py`

  ```
  Control, a call step: sam's answer is read by pay's `when`; sam approves pay
      -> REFUSED (AnswerRefused): sam set review.outcome, which decides whether pay runs, so cannot approve it
  A plan step with the same `when`: sam approves the payment inside the plan
      -> ACCEPTED
  A case step with the same `when`: sam approves the payment inside the child
      -> ACCEPTED
  RESULT: BROKEN - ...
  ```
- Proposed fix: `may_not_approve` also adds each person in the sources of the fields the step's
  `when` reads, with the reason a call step gives ("decides whether settle runs").

#### 1b.9 "Anything that talks to people drafts by default; it never sends on its own" is enforced nowhere (weakens a promise; the non-negotiable misleads)

I looked for what enforces or checks this non-negotiable and found nothing: no check in the
catalog, the validator, the runtime, the will-never sheet or the diff reads a contract's `notify`
effect to require a draft, a person or an approval. The only place `notify` decides anything is
that a `write` or `notify` contract must name an idempotency key (`core/contract.py`). The rule is
carried by what a contract's author writes in its description ("Never sends.").

- Promise: CLAUDE.md and the brief's non-negotiables, "Anything that talks to people drafts by
  default; it never sends on its own." D56 is honest that the sheet never says it: "**Never
  said:** ... and "drafts, never sends", until the engine checks it."
- Proof: `uv run python reviews/2026-11/probes/p1b_notify_sends_on_its_own.py` (its own catalog,
  one contract `mail.send@1`, effect `notify`, risk `low`, and a case whose only step calls it)

  ```
  the catalog registers mail.send@1: notify, low risk, no draft
      -> ACCEPTED
  validation of a case whose only step sends, with no task and no approval: no issue
         | scheduled send#1: mail.send@1 (to from system:opener; body from the case), key memory/send#1
         | send#1 done, giving message_id from untrusted:undeclared
         | closed: nothing left to do
    sent, with no person involved: ['customer@example.com']
  RESULT: BROKEN - ...
  ```
- Proposed: either build the check D56 waits for (for instance: a `notify` contract is at least
  medium risk or its step must carry an approval with no `when`, refused at validation and at the
  start, with a negative test), or reword the non-negotiable to say it is a convention for
  contract authors that the engine does not check yet.

#### 1b.10 An edit withdraws the approval a person's proposal waited for, and nothing asks again or says the proposal is over (misleads)

For a step that starts by itself, an edit withdraws the open approval and a new one is asked in
the same decision. For a step a person proposed, the approval is withdrawn and that is the last
line: `waiting_for` is empty, nothing needs attention, the case shows nothing pending, and the
state still keeps the proposer.

- Promise: D52, "**An edit lapses what saw the old value:** an open approval reading it is
  withdrawn, every approval on the entry at once (D47); a given one lapses; each is asked again."
  D25, "if the step is admitted again, a new entry is asked."
- Proof: `uv run python reviews/2026-11/probes/p1b_proposed_step_not_asked_again.py`

  ```
  The same, where kim proposed pay:
         | applied case.change#1: approved_amount edited by lee, approved by sam
         | withdrew pay.approval#1: approved_amount changed
    waiting_for: [] | needs_attention: [] | status: open
    the case still keeps kim as pay's proposer: {'pay': 'kim'}
  RESULT: BROKEN - (misleads) ...
  ```
  A migration that changes the step and renames it does the same
  (`withdrew pay.approval#1: refund 2 changed pay`, `renamed step pay to pay2`, nothing asked);
  a migration that keeps the step's name asks again. I saw this while exploring and did not keep
  a probe for the migration variant.
- Proposed fix: either ask again for the proposed run (it is still the proposer's), or add a
  line saying the proposal is over and must be made again, and clear the kept proposer.

#### 1b.11 A retry stopped by a lapsed approval says "a new approval is needed", and nothing can ask for one (minor)

The promise holds: the retry never pays the amount the approver did not see. But when the change
came from a task answered again (not an edit), every retry stops the same way for ever, where the
same change made by an edit lapses the spent approval and the retry asks again (D25 as amended by
D52). The only ways out are an edit to yet another value, or closing the case; the message names
neither.

- Proof: `uv run python reviews/2026-11/probes/p1b_lapsed_retry_can_never_be_approved.py`
  (three retries, three times `pay#1 failed: the inputs of pay changed since kim approved them: a
  new approval is needed`; the provider was called once, with 900). RESULT: HELD, with the note.
- Proposed fix: lapse a spent approval whenever the inputs it saw change, whoever changed them,
  so the retry asks again; or say in the reason what to do.

### What held

Each line is an attempt that did not break, with the probe that shows it.

- **Identifiers are written one way at every entry point** (D22):
  `p1b_identifier_spelling_every_entry_point.py`. Twelve misspellings (`Sam`, trailing and leading
  space, a Cyrillic look-alike, a trailing newline, `send_back#1`, `case:x`, `person:sam`,
  `system:opener`, empty, `-sam`, `sam,lee`) against nineteen acts (open, answer a task, answer an
  approval, propose, claim, give back, assign by and to, unassign, close, send an event, propose
  and approve an edit, propose a skip, retry, propose a migration, shown, forget's proposer and
  approver). None taken; each refused by the spelling check before any other. A control with a
  well-written identifier reaches every act.
- **"Someone else" across fourteen joins** (D11, D42, D52, D70, D71, D74):
  `p1b_someone_else_across_joins.py`. A person's event payload feeding the input; an amount
  carried through two rules' `set`; a child's reported value excluding the child's answerer in
  the parent; a child's close reason excluding its closer; an edit's proposer and approver; the
  value's giver approving its edit; a holder who then edited the value (sent back to the queue);
  an excluded person unassigning, reassigning, the opener assigning, assigning to an excluded
  person, answering a held entry, the proposer assigning; an assignment rule picking the reviewer
  (left in its queue).
- **The parent's opener and the step's proposer approve no step in the child** (D74): seen while
  exploring (`lee opened the case, so cannot approve its steps`; `kim proposed repair, so cannot
  approve it`); only change requests break (finding 2).
- **An approval is tied to what it saw** (D11, D25, D47, D52, D53):
  `p1b_approval_lapses_across_joins.py`. `count: 2` half given then an edit (withdrawn whole); half
  given then a migration to a release asking one person (withdrawn, never counted as given); a
  spent approval on a failed run then an edit, and then a migration changing the inputs (lapsed,
  the retry asks again, the provider not called twice); a sensitive value edited under an open
  approval (withdrawn, no line quotes either value); one approval, one run of a repeatable step.
- **Nothing is skipped by another name, inside one case** (D17, D26, D34, D40, D52, D53, D72):
  `p1b_nothing_skipped_by_another_name.py`, twelve attempts: a rule's stop on a failed run and on a
  run whose retry waits for its approval; a new proposal beside a failed run; `closes_when`
  reached; a migration to a release without the failed step; a skip of a required step; a skip
  approved by the run's approver, and by whoever's value it was given; a skip approved after the
  retry succeeded; two edits pending on one field; a request after the close; a request pending
  at the close.
- **A migration never loosens** (D53): `p1b_migration_never_loosens.py`. Dropping, widening or
  replacing `visible_to`, on a plain and on a sensitive field; losing `sensitive`; changing type;
  each also through a rename: all refused. A pending edit follows its field's rename and its
  giver still can't approve it; a step's proposer follows its rename; `{"to": "answered"}` finds
  the answerer under the task's new name.
- **The step advisor and the authoring loop** (D61, D62, D63):
  `p1b_advisor_and_authoring_decide_nothing.py`. Eight canaries (every case-file value, an event's
  payload, the opener's and the answerer's identifiers) and every history line are absent from
  the request; a hidden field is said `hidden`; an answer with an amount, with prose, or naming a
  step admission refuses suggests nothing; asking changes nothing in the case; the person who
  proposes the suggestion can't approve the run; a `suggested_by` of a caller's own words refuses
  the proposal. The loop abandons a draft that is a case, another plan, a plan with a case in a
  second key, or the plan with the approval bypassed. (The advisor's one gap is finding 3.)
- **An approver must see what they approve** (D30) and a sheet shows no hidden or sensitive
  value: seen while exploring (`lee can't see nid, which tell reads: it needs claims-sensitive`;
  the sheet's line `NID: hidden (needs claims-sensitive)`, and `‹sensitive›` for a role that may
  see it). Expression errors name kinds, never values (read in `core/expressions/evaluate.py`,
  not probed one by one).
- **Rules that would copy a hidden or a sensitive field into a wider one** are refused when the
  definition is read (the control of `p1b_hidden_value_into_child.py`, and exploration for the
  sensitive case).

### Unproven

- **A migration proposed inside a child case, approved by the parent's opener.** The same
  `excluded()` that lets the edit and the skip through decides it, so I expect it is taken; I did
  not build the release records to run it.
- **A hidden (`visible_to`) value given to a plan step's field.** A plan has no view of its own
  in the pure runtime that I could read by role, so I could not show who sees it.
- **A spent approval on a failed run when only a value the step's `when`, or the approval's
  `when`, reads is edited** (not an input). `lapse_spent` compares the digest of the inputs
  only; D52's words are "whose inputs the edit changed", so the letter is kept, while an open
  approval is withdrawn on any value the step reads (D25). I did not run it.
- **A child's failed run when a person closes the parent.** I assume it is cancelled as in
  finding 6; that would be a person's close, which the brief allows. Not run.

### Unchecked

- **Temporal.** Nothing here ran on a worker, by the pass's scope. In particular finding 4's
  consequence (the attachment's ID in clear in the workflow history) is read from
  `temporal/cases.py` `run_activity`, not run; and findings 1, 2, 6 and 8 were not replayed on
  child workflows (D75).
- **Forgetting** with failed runs, and the **audit export read by role** (`read_audit`, D77): left
  to the passes that own them. I only read that the export attaches `visible_to` by the field's
  name in its own case (`temporal/audit.py`, `restricted_fields`), so the value of finding 5
  would be written in clear under the child's field name; not run.
- **The live model provider**: never called (no key, by the rules). Recorded providers only.
- **`ventoux draft-sheet` refusing an edited draft** (D64): not probed; its tests record the
  known limit that an edit which also rewrites the record is not told.
- **`ruff` on the probes** reports three import-order remarks; the probes run as they are and I
  left them, since they are generated with a shared header.


---

## Pass 1, part c: on Temporal

Every run below was made at `f79b0e5` (branch `review-2026-11`; `git diff 3edb471 HEAD -- src tests
docs` is empty, so the source is 3edb471), against Temporal's time-skipping test server as the
repository's tests start it. Each probe is run from the repository root with
`uv run python reviews/2026-11/probes/<name>.py`. All sixteen were run at least twice, the last
time one after the other on their own; each gave the same result both times.

The probes share `reviews/2026-11/probes/p1c_harness.py` (a case worker, the development forget
workflow, raw histories) and `p1c_workflows.py` (three `CaseWorkflow` subclasses that only set the
class variables the code documents as "a test's workflow lowers", or name an environment).
**Reached past the supported names** in every probe: the tests' own server harness
(`tests/skipping_server.py`, `tests/worker_threads.py`), and `ventoux.testing`'s development
catalog, workflows and `release_of` (shipped, but not in `public.json`). Each probe's docstring
says what else it reached for (`send_event`, `propose_change`, `view`, `propose`, `retry`,
`case_handle` in `ventoux.temporal.cases`, which D79 names as the caller's functions but
`public.json` doesn't list; raw signals; `validate_case`).

Two things about the test server that a reader of the probes should know: it sometimes returns an
ended run's history without its last events (so the harness walks a case's runs from the latest
back, by `continued_execution_run_id`), and `handle.result()` on a handle that wasn't returned by
`start_workflow` can raise "No completion event found" while the workflow is still running (so
probes poll `describe`).

### Findings

#### 1c.1 A sensitive option and a sensitive attachment cross Temporal in plain text, and stay readable after forgetting — *breaks a promise*

When a task's form gives an option or an attachment whose field is `sensitive`, the case
schedules the check activity (`branches.holds@1`, `documents.issued@1`) with the value unwrapped.
It is written in the case's history as the activity's input, in clear, and is still there, in
clear, once the case is forgotten and its key destroyed. Everything else about the value is
sealed (the answer's signal, the state, the audit record), so nothing in the case's own lines
shows it.

Promises:
- D31: "**A sensitive field names who may see it.** `"sensitive": true` needs `visible_to`; any
  field type may be sensitive." and "**The value is wrapped wherever it goes.** … An input
  computed from it is wrapped too, so it reaches an activity or a plan encrypted, and the activity
  receives the plain value."
- D68: "**Forgetting reaches the ID, not the file:** a `sensitive` attachment's ID is sealed and
  forgotten with the case's key (D31)".
- D32: "**What goes:** every sensitive value, …".
- `docs/guides/case-data.md`: "Mark an attachment `sensitive` if its ID…" and, in its design
  notes, "only `sensitive` keeps a value out of Temporal's plain history."

Proof (`p1c_sensitive_check_in_history.py`):
```
validation errors: []
    ana answered assess#1 accept as adjuster, setting branch and id_scan, checked by branches.holds@1 and documents.issued@1
    closed: nothing left to do
forget request: forgotten | key: destroyed
in plain text in the history after forgetting:
    branch: event 20 ACTIVITY_TASK_SCHEDULED branches.holds@1 input b'{"option": "BR-0142"}'
    id_scan: event 21 ACTIVITY_TASK_SCHEDULED documents.issued@1 input b'{"attachment": "doc-7f3a"}'
RESULT: BROKEN - a sensitive option and a sensitive attachment cross Temporal in plain text as their check's input, and stay readable once the case's key is destroyed
```
`p1c_plaintext_everywhere.py` finds the same two values in the parent's second run, before and
after forgetting, among everything else it reads. (Pass 1b's
`p1b_sensitive_attachment_check_unwrapped.py` looks at the same join from the engine's side; this
one shows what it leaves in Temporal, and that forgetting doesn't reach it.) The layer note's
promise rows 15 and 16 for 16c say "pinned; nothing of 16c's own": the in-memory test checks the
state and the lines, and no test reads the Temporal history of a case with a sensitive checked
field.

Proposed fix: have the engine hand the check its value still wrapped when the field is sensitive
(the converter then gives it its own part, the codec seals it, and the activity receives the
plain value, as any activity input computed from a sensitive field does), and add a Temporal test
that searches the raw history for a sensitive option and a sensitive attachment, before and after
forgetting.

#### 1c.2 A second request to forget the same case loses its records, never ends, and can no longer be read — *breaks a promise*

Every request to forget a case writes its audit records to the one stream `<case>/forget`,
numbered from 1. A second request for the same case therefore sends a record 1 with other
content, which the store refuses (`AuditRefused`). Two cases:

- **After a rejected (or refused) request, the request that really forgets the case.** Its writer
  fails at its first record; the request goes on all the same, has the case close, destroys the
  key, and only then meets the writer's failure, which it can no longer seal (the key is gone).
  Its workflow task then fails again and again, for good: the request never ends, its report
  query no longer answers (replaying it needs the destroyed key, because the sealed `AuditRefused`
  failure is in its history), no later request for the case can start while it runs, and the
  audit store holds no record of who proposed the forgetting, who approved it, or that the key was
  destroyed. The store still shows only the first request, rejected.
- **A request made once the case is forgotten** is refused before anyone approves, as D32 says,
  but its workflow never ends either: its first record is refused, the refusal can't be sealed
  under the destroyed key, so Temporal no longer sees a non-retryable `AuditRefused` and the
  write is retried without end (4 attempts in 4 real seconds here; 8,854 in 40 s once the test
  server skipped time, seen while building `p1c_forgotten_id.py`).

Promises:
- D77: "**Forgetting:** close, export, then destroy (D32, as amended). The forget request's own
  stream, holding no sensitive value, is written behind the patch marker `ventoux-forget-export`,
  beside the request, never in its way: one record per act (the proposal, each answer, the key
  destroyed), the last written once the key is gone."
- D15: "The audit trail keeps every decision, who made it, the rule and the release; only the
  values go." D17, as amended by D77: "Nothing is dropped, nothing decided unrecorded."
- D32: "**What stays:** every decision, who made it and with which role, …, and the request's own
  history." and "**Twice, or a case that never existed, is refused before anyone approves**".
- `propose_forget`'s own words: "one that ended (refused, rejected, forgotten) leaves room for a
  new one".
- `forget.py`'s header: "None of this workflow's payloads holds a sensitive part, so it never
  asks for the key, and its history stays readable once the key is gone."

Proof (`p1c_second_forget_request.py`):
```
first request: rejected
   the request's stream: ["1: forget proposed by pat: ['admitted']", "2: answered by noor: ['rejected']"]
second request's workflow, 3 s after the key went: RUNNING
   its report can't be read: TimeoutError
   its history: 1 write refused (AuditRefused), 1 workflow task failures so far
   key of claim-1: destroyed
   the request's stream now: ["1: forget proposed by pat: ['admitted']", "2: answered by noor: ['rejected']"]
third request, 4 s later: refused ["refused pat's proposal: claim-1 was already forgotten: its key was destroyed"] | its workflow: RUNNING
   pending ventoux.audit.append, attempt 4
RESULT: BROKEN - the request that forgot the case can no longer be read; the request that forgot the case never ends …; the audit store holds no record of quinn's proposal, rosa's approval or the key destroyed; a request made after the case was forgotten never ends …
```

Proposed fix: give each request its own stream, or carry the stream's next number into a new
request (the workflow's run ID, or a count read from the store through the look-up activity, in
the stream's name or as the starting number); stop the request, saying why, before it asks the
case to close if its own records are refused; and never route a failure of the forget workflow
through the case's key (its failures quote no value). A test with two requests for one case,
reading the store after each, would have caught it.

#### 1c.3 The audit export can be refused for good by a record's names, so the case never ends and can't be forgotten — *breaks a promise*

The export refuses a record that holds "a sensitive field, in clear", and decides that by the
value's *name* alone, compared with the case's sensitive fields. But a record's names are not all
case fields, and a refused act's values are recorded as they came. Four ordinary ways to make a
record the export refuses on every retry:

1. **An event** (even one the case doesn't declare) whose payload has a key spelt like a
   sensitive field. The event is refused and recorded; the record's `values` are the payload.
2. **An activity's output** with a field spelt like a sensitive case field (the development
   catalog's `orders.lookup@1` gives `status`; a case with a sensitive `status` field is enough).
   No outside input at all; the package passes case validation.
3. **A plan step** whose plan passes a plain value to an activity input spelt like a sensitive
   case field (the plan's decisions ride in the record of the step's end, under the plan's input
   names). The package passes case validation.
4. **A raw `answer` signal with an unsealed sensitive value.** D31's refusal happens, rightly;
   then the refused answer's record holds the plain value, and can never be written.

In each, the case needs attention with `audit export failed: audit record …/2 holds <field>, a
sensitive field, in clear: nothing was written: look at the store, then retry the export`;
`retry_export` gets the same refusal, every time; the case is "closed" in its report while its
workflow runs for ever; and an approved request to forget waits at "closing the case" with the
key kept. Nothing an operator can do through Ventoux ends it (a skip is for a failed run, an edit
for a field). The message also sends the operator to the store, which is not at fault.

Promises:
- D77: "the case needs attention, and an operator retries the export with `retry_export` (D26)"
  and "The case never closes with records unwritten" (so a record that can never be written means
  a case that can never close); D32 as amended: "with the store down the case stays closing and
  the request waits, saying why" (here the request says nothing of why).
- D15/D32: forgetting is promised for a case; here a person's case can't be forgotten at all.
- D17: "Nothing is dropped, nothing decided unrecorded." and CLAUDE.md, "Nothing is skipped
  automatically: a failed step waits for a person" (the person has no act that helps).

Proof (`p1c_export_refused_for_good.py`, trimmed; the plan-step case is part B of
`p1c_plan_step_audit_names.py`):
```
definition 1/3: validation errors: []
definition 2: validation errors: []
1 event: history:
     refused ping from system:portal: ping is not an event of claim: its events are none
     audit export failed: audit record claim-1/2 holds national_id, a sensitive field, in clear: nothing was written
     omar retried the audit export as operations
     audit export failed: audit record claim-1/2 holds national_id, a sensitive field, in clear: nothing was written
1 forget request, approved: closing the case | claim-1 asked to close as forgotten
1 case: closed | unwritten 5 | workflow RUNNING | key kept
2 activity output: history:
     look#1 done, giving status from untrusted:undeclared
     audit export failed: audit record claim-2/2 holds status, a sensitive field, in clear: nothing was written
3 unsealed answer: history:
     refused ana's answer accept to assess#1: national_id is sensitive and was given in plain text: send it through ventoux.temporal.cases, which encrypts it
     audit export failed: audit record claim-3/2 holds national_id, a sensitive field, in clear: nothing was written
RESULT: BROKEN - the audit export is refused for good, the case never ends and can't be forgotten, after: an event's payload key, an activity's output name, a refused unsealed answer
```
```
B: needs attention: ['audit export failed: audit record lookup-1/2 holds order_id, a sensitive field, in clear: …']
B: its workflow is RUNNING (closed in name, never ended)
```

Proposed fix: make a record say what kind of name each value has (a case field, a payload field,
an output, a plan's input, an assignment's `to`), and check "sensitive in clear" only against
case fields; record a refused act's value for a sensitive field as refused-and-withheld (or seal
it in the activity, since it has the key) instead of carrying the plain value to a check that can
only fail; and give the operator an act for a record that can't be written (D17's change request
is the model). Negative tests: an event, an output and a plan input each spelt like a sensitive
field, exported.

#### 1c.4 A plan step's inputs are written to the audit store under the plan's names, so a `visible_to` value is read by every role — *breaks a promise*

A case field that narrows who sees it (`visible_to`, not sensitive) is written by the export "in
clear, saying who may see it", and `read_audit` hides it from other roles. When the same value is
given to a plan step, the plan's decisions ride in the record of the step's end, each fact named
after the *plan's activity input*. That name is no restricted field of the case, so the value is
written with no `visible_to`, and `read_audit` shows it to any role, and to no role at all
(`roles=[]`). In the very same stream the case's own `started` decision hides the same value.

Promises:
- CLAUDE.md, non-negotiables: "Policies can be made stricter downstream, never looser (a case
  tightening a contract, untrusted data adding an approval, a view hiding more than its source)."
- D77: "A field that narrows who sees it without being sensitive is written in clear, saying who
  may see it." and "**Reading it,** `read_audit(store, case, roles, keys)`, filters each value as
  the case view does (D30): a value whose field narrows who sees it is said hidden unless the
  reader holds one of those roles".

Proof (`p1c_plan_step_audit_names.py`, part A):
```
A: validation errors: []
A: read_audit(roles=['adjuster']) shows the value in clear: True
   record 1 started   read {'field': 'watchlist_ref', 'sources': ['system:opener'], 'value': 'hidden (needs fraud)'}
   record 2 started   read {'field': 'order_id', 'sources': ['system:opener'], 'value': 'WATCHLIST-HIT-9931'}
A: read_audit(roles=[]) shows the value in clear: True
```
(A sensitive value given to a plan fails the safe way: it is sealed with `visible_to: []`, hidden
from everyone, even from those who may see its field.)

Proposed fix: have the case, which knows which of its fields each plan field was computed from,
carry who may see each plan input with the plan step's start (the strictest of the fields read),
and have the export write the plan's facts with it; a test that reads the store as another role
after a plan step was given a `visible_to` field.

#### 1c.5 A closed case that keeps closed cases (`forgetting: while_open`) is forgotten; more widely, the request destroys the key even when the case refused it — *breaks a promise*

The request looks the case up before anyone answers: is its workflow *running*? A case that has
closed but not yet ended (its records are not all written: the store is down, or the export is
under way) is running. The request therefore admits the proposal; on approval it signals the
case; the case, being closed, refuses and records the refusal (`the case is closed`); the request
never learns of it, waits for the workflow to end, and destroys the key. The window is as long as
the store is down. The same blind spot applies to any refusal the case itself makes of an
approved request (`forget()` in `case/forgetting.py` checks again "depending on nothing the
request did", but its answer goes nowhere): the key is destroyed whenever that case's workflow
later ends.

Promise, D32: "**A closed case can be forgotten,** keeping its own close reason, **unless its
definition keeps its records:** `"forgetting": "allowed"` (the default), `"while_open"` (refused
once the case is closed, for books and records) or `"never"`."

Proof (`p1c_forget_while_open_after_close.py`):
```
the case: closed | its workflow: RUNNING | unwritten: 2
the request, after its look-up: waiting ['pat proposed forgetting claim-1, as privacy']
the case's own history, once ended:
     closed: nothing left to do
     audit export failed: the store failed with OSError: ‹sensitive›
     refused forgetting the case, approved by noor: the case is closed
     omar retried the audit export as operations
the request: forgotten
     claim-1 asked to close as forgotten
     claim-1 ended: omar retried the audit export as operations
     the key of claim-1 was destroyed
key of claim-1: destroyed
RESULT: BROKEN - a closed case whose definition says forgetting: while_open refused the approval, and its key was destroyed anyway
```
(The request's line "claim-1 ended: omar retried the audit export as operations" also shows that
"its closing line" is simply the report's last line, which a closed case can still add to.)

Proposed fix: decide `while_open` on the case's own word, never on Temporal's status: the look-up
asks the case's report for its phase, and, before destroying, the request reads how the case
closed (its returned report says `closed: forgotten` or its own reason, and whether it refused
the request) and stops, saying why, when the case refused. A test: a `while_open` case closed
with its store down, then proposed.

#### 1c.6 The worker's log quotes an activity failure's message in plain text when the failure can't be sealed — *breaks a promise*

Ventoux's log filter drops an exception's message and traceback from records that carry
`exc_info`. When sealing an activity's failure itself fails (the key service doesn't answer at
that moment, `KeyUnavailable`; or the case's key is gone), Temporal's SDK logs
`Exception handling failed, original error: <the activity's own message>` on
`temporalio.activity`, with the message formatted into the record's text. The filter keeps it. An
activity that quotes what it was given, the very case D31's filter was added for, then writes a
national ID to the log each time it is tried. The failure Temporal records is no longer the
activity's own either ("Failed building exception result"), so a failure the activity raised as
non-retryable is retried (three attempts here).

Promise, D31: "**The worker's log keeps only an exception's type.** Temporal's SDK logs a failed
activity, and a failed workflow task, with its exception and traceback before the failure is
sealed; worker logs go where many people read them. So the workers install a filter on Temporal's
loggers that keeps the exception's type and drops its message and traceback."

Proof (`p1c_log_quotes_failure_without_key.py`):
```
the case says: ['look#1: orders.lookup@1 failed with ApplicationError: ‹sensitive›']
LOGGED: Exception handling failed, original error: no record for 1 85 05 78 006 084 36 ({'activity_id': '1', 'activity_type': 'orders.lookup@1', 'attempt': 1, … 'workflow_id': 'claim-1', …}) (KeyUnavailable)
LOGGED: … 'attempt': 2 …
LOGGED: … 'attempt': 3 …
RESULT: BROKEN - the worker's log holds the national ID in plain text, 3 time(s): the SDK logs the activity's own message when sealing its failure fails
```
The line is the SDK's (`temporalio/worker/_activity.py`, `logger.exception(f"Exception handling
failed, original error: {err}")`, SDK 1.34.0). The same line appeared, harmlessly, in
`p1c_forget_family_in_flight.py` ("original error: the audit store is down") once the key was
destroyed.

Proposed fix: have the filter replace the text of any record on Temporal's loggers that carries
an exception with a fixed sentence and the exception's type (never pass the SDK's formatted
message through), or allow only the messages the filter knows; and a test with a key provider
that raises `KeyUnavailable` from `seal`.

#### 1c.7 A form value given under a name that is no field is kept in clear: in the history, in the audit store, for every role, after forgetting — *breaks a promise*

The client seals every form value, "since it can't tell which fields are sensitive". An answer
with a value under a name the case doesn't have is refused and recorded; for its record the value
is *unwrapped* (`kept()` returns `plain(value)` for a name that is no field) and so written in
clear in the audit store, with no `visible_to`; it also crosses in clear in the export
activity's input and in the state the case continues as new with. `read_audit` shows it to every
role and to none, and it is still readable after the case is forgotten. A name that is no field
is exactly what the engine doesn't recognise; the permissive reading ("not sensitive") is chosen.
A person who typed a national ID into the wrong box of a form built on an older wording is the
case this protects.

Promises:
- D32: "**What goes:** every sensitive value, every form value in the answers people sent (D31
  encrypts them all), and every failure's message and stack trace." (the guide: "Where a
  sensitive value was, there is ciphertext no one can open. So is every form value in…").
- CLAUDE.md: "Fail closed: anything the engine can't evaluate or doesn't recognise is an error,
  never a permissive default".
- D76 covers the other case only: "A form value is in the record as the case file holds it:
  sensitive only if its field is."

Proof (`p1c_plaintext_everywhere.py`, trimmed):
```
     refused ana's answer accept to assess#1: the answer gives scratch, which accept doesn't set
BEFORE forgetting, sensitive values in clear: ['branch (sensitive option, form) in kyc-1 run 2', 'id_scan (sensitive attachment, form) in kyc-1 run 2', 'stray (form value under no field) in kyc-1 run 2', 'stray (form value under no field) in audit store kyc-1.jsonl']
  read_audit(roles=['adjuster']) shows: ['stray (form value under no field)']
  read_audit(roles=[]) shows: ['stray (form value under no field)']
AFTER forgetting, sensitive values in clear: [… the same four …]
  read_audit(roles=['claims-sensitive']) after: shows ['stray (form value under no field)']; ‹forgotten› 15 times, hidden 1 times
```
A note for the brief rather than a finding: D32's "every form value in the answers people sent"
goes is true of the answer's signal only. A value given for a field that is *not* sensitive is
kept in clear by design in the state that crosses continue-as-new, in the export's input and in
the audit store (D76), and the same probe shows it there after forgetting ("notes (plain form
field) in kyc-1 run 2 … 5", "… in audit store kyc-1.jsonl"). D32's "What stays: … every value
that wasn't sensitive where it was used" covers it, but the two sentences read against each
other; the brief could say in D32 that a form value stays wherever the case file kept it in
clear.

Proposed fix: keep a refused answer's value wrapped when its name is no field of the case (so it
is sealed in the state and in the store, with nobody able to see it), and test it.

#### 1c.8 A signal carrying `NaN` or `Infinity` stops the case for good — *breaks a promise* (reached past the supported names: a raw signal)

JSON's `NaN` and `Infinity` are read by the converter as binary floats (`parse_float=Decimal`
doesn't cover the constants). The engine refuses the answer, event or edit, rightly, and records
the refusal with the value; the converter then refuses to write a float ("is a binary float"),
so the workflow task that would send the record to the export fails, and fails again on every
retry. The case no longer decides anything nor answers its report; the well-formed answer sent
after it is never decided. This is not D17's "waits for code": no code change is expected, one
signal did it. Ventoux's own client can't send it (`exact_json` refuses a float on the way out),
so it takes a caller that writes signals itself, which D79 forbids but Temporal doesn't prevent
(Python's `json.dumps(float("nan"))` writes `NaN`).

Promise: D17, "runtime expression errors become 'needs attention'" and CLAUDE.md, "at runtime a
missing field, a wrong type or an unknown operator is an error" (a refusal, recorded), not a case
that stops.

Proof (`p1c_raw_signals.py`, 56 malformed signals, each to its own case):
```
POISONED           | answer: form value NaN          | the case no longer decides nor answers: 2 failed workflow tasks so far, and the well-formed answer sent after it is never decided
POISONED           | event: payload value Infinity   | the case no longer decides nor answers: …
POISONED           | change: edit amount to NaN      | the case no longer decides nor answers: …
```
with, in the worker's log, `Failed activation on workflow ventoux.case with ID refund-16 … (TypeError)`
repeated.

Proposed fix: read the constants as a refusal in `ExactJSON.from_payload` (`parse_constant`
raising, so the signal fails to read like any other unreadable one, see finding 9), or have the
engine never put a value it refused for its type into a record.

#### 1c.9 A signal the case can't read is dropped without a line or a record; an undeclared one waits unseen — *weakens a promise* (raw signals)

Ten of the 56 malformed signals were taken by Temporal (the send succeeded) and left nothing in
the case: no history line, no audit record. They are the ones Temporal's SDK can't turn into the
handler's dataclass (a form that is a text, a missing key, a list for the argument, roles holding
a number, a sensitive mark naming no part, an engine version as text, …): the SDK logs "Failed
deserializing signal input … dropping the signal" and goes on. A signal under a name the case
doesn't declare is buffered by the SDK, unseen. Of the others, 41 were refused and recorded, each with a clear line; 2 were accepted (below,
and finding 14); 3 stopped the case (finding 8).

Promises: D76, "One audit record per act that reaches the case … A refused act is a record too";
and D41's amendment names the same shape as a defect: "until now the client's send could succeed
and the case record nothing."

Proof: `p1c_raw_signals.py`:
```
DROPPED, no trace  | answer: form a text              | the send succeeded; the history gained no line and no record
DROPPED, no trace  | answer: no roles key             | …
DROPPED, no trace  | event: payload a list            | …
DROPPED, no trace  | migrate: engine a text           | …
DROPPED, no trace  | a signal nobody declared         | …
refused, recorded: 41   DROPPED, no trace: 10   ACCEPTED: 2   POISONED: 3
```
Also seen there, each small: an `answer` with an extra key is accepted (the key ignored);
`roles` given as the text `"support"` is read as the seven letters, so the answer is refused for
having no role (safe, but the record's roles are letters).

Proposed fix: take each signal's argument as raw data in the handler and read it in the engine's
own code, so an unreadable one is refused and recorded like any other refusal; add a dynamic
signal handler that records "a signal the case doesn't know". If instead this is the caller's
contract (D79), the deployment guide should say that a malformed signal is dropped unrecorded.

#### 1c.10 A request to forget waits in silence when the case's start doesn't read as a case — *weakens a promise*

Before anyone answers, the request reads the start of the case's latest run to learn what its
definition says of forgetting. If that start holds a definition that doesn't parse (a case
refused at its opening with `CaseInvalid`, its sealed values already in history under a key), or
isn't a case's start at all (a standalone plan run, whose key D31 makes "as a case's is"), the
look-up activity raises and Temporal retries it for ever: the request stays `waiting` with no
line, refusing nothing and saying nothing, and the sealed values can't be forgotten through
Ventoux. The repository tests a case refused at its opening for another reason (`CaseRefused`,
whose definition parses), which works.

Promises: D32, "**Twice, or a case that never existed, is refused before anyone approves**" (a
proposal that can't be carried out is said so at once); CLAUDE.md, fail closed, and D17's "never
waited for silently" spirit. `lookup_refusal` already has the sentence for a definition that
can't be read ("…'s definition can't be read: …so whether it keeps its records is unknown"), but
only for a history Temporal no longer holds.

Proof (`p1c_forget_unreadable_start.py`):
```
claim-1's workflow: FAILED
claim-1: the request is 'waiting', lines []; pending activity ventoux.forget.look_up, attempt 5; key kept
run-1: the request is 'waiting', lines []; pending activity ventoux.forget.look_up, attempt 5; key kept
RESULT: BROKEN - a request to forget waits in silence, its look-up failing again and again, …
```
(the log shows `ventoux.forget.look_up` failing with `CaseInvalid`, then `TypeError`).

Proposed fix: catch a start that doesn't read in `forgetting()` and return what the request can
decide on. For a case that never opened (its workflow failed before deciding anything) nothing
keeps records, so its key can go; for a plan run, either forget it as a run or refuse saying that
a plan run isn't forgotten this way. Decide which in the brief: D15/D32 speak of cases only,
while D31 gives a standalone plan run a key of its own and seals every form value sent to it.

#### 1c.11 A start that says it "continued as new" skips the registry, the opening and the release check — *weakens a promise* (reached past the supported names: a raw start)

`CaseStart.carried` set means "this run continues an earlier one": the workflow then asks no
registry, decides no opening, and takes the state it is handed. Nothing checks that the run
really continues another (Temporal says so: `workflow.info().continued_run_id`). So a start made
with Temporal's client and a hand-made `carried` runs a draft in a production environment, on a
state its caller wrote (here: a review already approved by the caller, the payment's approval
asked next), and the registry lists no open case. `start_case` can't do this; it takes a caller
that starts workflows itself.

Promises: D51, "**The case checks what it was given,** depending on nothing the client did"; D54,
"**An environment is production unless created for development,** where drafts open"; the
registry "keeps … each release's open cases".

Proof (`p1c_forged_continuation.py`):
```
control, start_case with the draft in production: refund-1 can't open as a draft in production: open it on a release
forged start: the case's report:
   status: open | release: draft | engine: 3
     mallory answered review#1 approve as support, setting approved_amount
     asked pay.approval#1: approval of pay by support-lead
production's registry lists as open: []
RESULT: BROKEN - a start that says it continued as new runs a draft in production, on a state its caller wrote, asking no registry
```
Proposed fix: refuse a start with `carried` when `workflow.info().continued_run_id` is empty
(fail the opening as `CaseRefused`), behind a patch marker so recorded histories replay.

#### 1c.12 An activity failure's `details` and `type` cross Temporal unsealed; the type lands in the case's line — *weakens a promise*

The failure converter seals a failure's message and stack trace. An `ApplicationError`'s
`details` (Temporal's place for data about a failure) are written to the history in clear, and
its `type`, a text the activity's code chooses, is written in clear in the history and copied
into the case's own line, its "needs attention" entry and its audit record. D31 treats the type
as safe: "a type is code, never data". That holds for a Python exception class; it doesn't for
`ApplicationError(type=…)`.

Promise, D31: "**Failures are encrypted whoever raised them.** … An activity's own message is
treated as sensitive in every case, since Ventoux can't know what it says".

Proof (`p1c_failure_details.py`):
```
the case says: ['look#1: orders.lookup@1 failed with NoRecord:TYPE-185-05: ‹sensitive›']
the failure's message: not in the history in plain text
the failure's details: IN PLAIN TEXT in the history
the failure's type: IN PLAIN TEXT in the history
```
Proposed fix: seal `details` with the message (or drop them), and either seal an
`ApplicationError`'s `type` too, naming only the exception class in the case's line, or say in
D31 and the activities guide that `type` and `details` are the author's, as an activity's own
logging is.

#### 1c.13 `report` says "open", with nothing to show, of a case that was refused at its opening — *misleads*

A case refused at its opening fails its workflow. `report(case)` returns the workflow's result
only when it *completed*; otherwise it queries, and the query replays a workflow that never
opened: `status='open'`, no history, nothing needing attention, `engine=3`. The caller is told an
open case exists where none does. (It cost this review two wrong turns: a probe whose opening was
refused looked like a case that never moved.)

Proof (`p1c_report_of_refused_opening.py`):
```
Temporal says the case's workflow is: FAILED
report(case) says: CaseReport(status='open', waiting_for=[], waiting_at=[], needs_attention=[], flags=[], history=[], timers=[], release='draft', engine=3, …)
```
Standard: fail closed ("never a permissive default"); D24, "A waiting case says what it waits
for". Proposed fix: have `report` raise for a workflow that failed, was terminated or timed out,
saying how it ended and, for a refused opening, why (the failure's message is the case's own
words).

#### 1c.14 A case with no parent closes on `close_by_parent`, with any reason and nobody named — *minor* (raw signal)

`p1c_raw_signals.py`: a raw `close_by_parent` signal to an ordinary case gives `cancelled
review#1: closed by its parent: mischief; closed: by its parent: mischief`. A person's close is
checked (a declared reason, a role: `refund has no close reason 'because'`); this one isn't, and
the engine knows whether the case has a parent. D75 says a signal "says nothing of who sent it",
which is why the doorbell carries nothing the case would take; the close signal could be refused
by a case that has no parent at no cost. Proposed fix: refuse and record it when the case's
start names no parent.

### What held

- **No sensitive value in plain text** in any run of the parent (four or five runs, across
  continue-as-new), the child case, the plan step's run or the forget request, nor in the audit
  store's files, the key file, the worker's log or the process's output, for: the opening, a
  form's sealed text, a rule's `set` to a sensitive field, an activity input and its failure's
  message, a plan step's input and its plan's failing activity, a child case's opening, an
  approved edit, the export activity's input, the continue-as-new input, the forget request's own
  history. `p1c_plaintext_everywhere.py` (its BROKEN lines are findings 1 and 7 only; "sensitive
  values in the log or stderr: none").
- **After forgetting:** the key file holds `{"kyc-1": null}` and nothing else beside it;
  `read_audit` gives `‹forgotten›` (15 times) to the role that may see and `hidden` to others;
  `view` is refused (`kyc-1 was forgotten: its case file can't be read`); `report` of the parent
  and of its child still read. Same probe.
- **read_audit with `roles=[]`** hides every sealed and every narrowed value (same probe, and
  `p1c_plan_step_audit_names.py`: `watchlist_ref … 'hidden (needs fraud)'`), apart from findings
  4 and 7.
- **A forgotten ID opens nothing again:** `start_case` and `start_plan` with the ID are refused
  (`a key was already made for claim-1`), a child-like ID is refused (`has no "/"`), another
  spelling (`Claim-1`) is another case with its own key; forgetting twice, a case that never was,
  and a child alone are each refused before anyone approves; the proposer and the opener approve
  nothing. `p1c_forgotten_id.py` (it terminates the refused requests, which never end: finding 2).
- **Close, export, then destroy, with work in flight:** a parent with a pending change request, a
  running activity on a sensitive input and an open child with its own running activity is
  forgotten only once both workflows have ended; the key was kept while both activities ran, both
  received the plain value, and the request's last record ("key destroyed") was written once the
  store, down when the key went, came back. `p1c_forget_family_in_flight.py`.
- **Signals arriving with the close:** 12 cases, 96 signals sent in the same moment as the
  closing answer; all 96 have their line in the closed case's report and their record in the
  store (about half of them `refused …: the case is closed`, 45 and 56 in two runs), numbered
  without a gap.
  `p1c_signals_with_the_close.py`.
- **Idempotency keys:** Temporal's own retry, and an operator's `retry` made after the case had
  continued as new, all gave the payment `refund-1/<first run ID>/pay#1`.
  `p1c_idempotency_keys.py`.
- **41 of 56 malformed raw signals** are refused and recorded with a clear line (bad identifiers,
  unknown entries, outcomes, events, fields, change kinds, a migration that doesn't give its
  digest, an unknown engine version, `suggested_by: evil-bot`, a `forget` signal sent to the case
  directly by one person or without the role, a doorbell for no child). `p1c_raw_signals.py`.
- **A draft in production through `start_case`** is refused by the registry (the control in
  `p1c_forged_continuation.py`).

### Unproven

- **A `visible_to` value given to a child case** whose field doesn't narrow who sees it is, I
  expect, shown to every role in the child's view and written in clear in the child's audit
  stream, the same loosening as finding 4 by another route. D74 limits only *sensitive* values
  ("a sensitive value enters a child only into a sensitive field"). Not run here; pass 1b has
  `p1b_hidden_value_into_child.py`.
- **Finding 5, wider:** a case migrated to a release that says `forgetting: never` between a
  proposal and its approval would refuse the approval and still lose its key when it later
  closes. The mechanism is the one proven (the request never reads the case's refusal); the
  migration route itself was not run.
- **Finding 6 with a destroyed key:** an activity of a plan or child workflow still running when
  its case's key is destroyed would log its failure's message the same way. Seen only with a
  harmless message; D75 records the route (a parent terminated with a child running).
- **`FileAudit` on a case-insensitive file system:** `claim-1` and `Claim-1` are two cases with
  two keys but would share one stream file there. Linux only here.
- **The codec binds a sealed part to its case and its position in the payload (`sensitive/0`),
  not to the payload:** a sealed part copied from one payload of a case into the same position of
  another would open. It needs write access to history, which D19 keeps to admins; not tried.

### Unchecked

- **The development server and a real cluster.** Every probe ran on the time-skipping test
  server. D75 notes the two differ (parent close policy); none of the findings depends on what a
  parent's end does to a child, but none was re-run on the dev server.
- **Vault.** `VaultKeys` was not run (no Vault binary; not tried, per the rules). Finding 6 uses a
  `FileKeys` subclass raising `KeyUnavailable`, the error D78 gives a key service that doesn't
  answer.
- **Releases and environments beyond finding 11:** a tampered package with its digest kept, a
  child whose pinned release is retired, a migration target not activated, a workflow type moved
  under open cases. The repository has a Temporal test for each
  (`tests/test_temporal_case_release.py`, `test_temporal_registry.py`,
  `test_temporal_children.py`); I didn't retest them, so I don't claim they hold.
- **Holding past 256 KB, and record numbers across a migration.** Not retested (the numbering
  check in `p1c_signals_with_the_close.py` covers one run only).
- **Queries' failure messages, the advisor's view, memo and search attributes.** Read in the code
  (the advisor's view holds no value; the only search-attribute event is the SDK's own for patch
  markers), not probed.
- **Heartbeat details** of an integrator's activity: not probed; they are the author's payloads,
  as outputs are (see finding 12 for `details`).


---

## Pass 2: replay

Source reviewed: 3edb471 (probes ran with the tree at 9b92c1a on `review-2026-11`, which adds only
files under reviews/). Every probe is run from the repository root with
`uv run python reviews/2026-11/probes/<name>.py`. Shared, not probes themselves: `p2_harness.py`,
`p2_fixtures.py`, `p2_time_classes.py`, `p2_seed_plugin.py`, `p2_capture_plugin.py`.

How the comparing is done (p2_harness.py). A replay that raises nothing proves little, so during
each replay an interceptor records what the workflow code hands to Temporal: each activity's
input, timeouts and retry policy, each child workflow's start, each signal sent, each timer, each
Update's answer, and the result or the next run's start. The same is read from the history's
events, and both are compared as the exact JSON text Ventoux's converter writes (key order and
number spelling included, sensitive parts opened with the fixture's key). The workflow's state at
the end of the replay (its `report`, and for a case the whole state as `state_as_data` gives it)
is read too. This reaches past the supported names into the SDK's `_WorkflowInstanceImpl`.

### Findings

#### 2.1 A migration the case refused for an engine version its code didn't know is taken when a later worker replays the history (breaks a promise)

Whether a proposed migration's engine version is acceptable is decided from the code's own lists
(`KNOWN` in `case/migrations.py`, `KNOWN`/`OPENING` in `refuse_an_engine_not_opened`,
`temporal/cases.py`), on every decision, replays included. Nothing in the history records which
versions the deciding code knew. So a refusal recorded by a worker that knew engines 2 and 1
becomes an acceptance when a worker that knows 3 replays the same run: the request the case said
it refused is open (`case.change#1`), and an answer the case recorded as refused ("case.change#1
isn't open") approves it. The case moves to another release and engine, withdraws an approval and
asks for an audit export, with no replay error where the history ends there.

The scenario is the one the refusal exists for: a client built with the newer engine proposes
while the workers still run the older one; then the workers are upgraded.

Promises touched:
- D51: "From this decision on, a change that decides a recorded path differently is the next
  version: its old branch kept behind the case's version, a fixture recorded under the old version
  that replays, and a line here."
- D53: "The engine version moves forward only, as data in the request, sent by the proposer's
  client; a version the code doesn't know, or one older than the case's, is refused."
- D76 (19a's review): "until then no case moves to version 3 on Temporal either: a migration there
  is refused when proposed".
- The code's own comment (`refuse_an_engine_not_opened`): "Checked at the proposal only: a request
  reaches a case no other way, and code that didn't know the version refused it there too." True
  of a new proposal; not of the recorded one, which is decided again on replay.

Proof 1 (time travel; recorded by the code at dc2407e, `KNOWN = (2, 1)`, on the tests'
time-skipping server; replayed by that code and by today's). Commit 9b92c1a.
`uv run python reviews/2026-11/probes/p2_refused_engine_resurrects.py`:

```
History A (ends after the refused proposal), as the case reported it when recorded at dc2407e:
    refused pia's proposal to migrate refund 2: engine 3 is one this code doesn't know (it knows 2, 1)
    waiting at: ['pay.approval#1']
  replayed by the code at dc2407e (knows engines [2, 1]):
    replay error: none
    waiting at: ['pay.approval#1']; release refund 1, engine 2; activities asked: []
  replayed by today's code (knows engines [3, 2, 1]):
    replay error: none
    waiting at: ['pay.approval#1', 'case.change#1']; release refund 1, engine 2; activities asked: []
    pia proposed case.change#1: migrate to refund 2, to be approved by platform
History B (goes on: lee's approval of case.change#1, refused too) ...
    refused lee's answer approve to case.change#1: case.change#1 isn't open
  replayed by today's code (knows engines [3, 2, 1]):
    replay error: none
    waiting at: ['fraud_check#1']; release refund 2, engine 3; activities asked: ['ventoux.audit.append']
    applied case.change#1: migrated from refund 1, engine 2 to refund 2, engine 3, proposed by pia, approved by lee
    withdrew pay.approval#1: refund 2 changed pay
RESULT: BROKEN - a migration the case refused and recorded as refused is taken when today's code replays the history ...
```

Proof 2 (the repository's own scenario of the 19a window). The test
`test_a_case_moves_on_temporal_only_to_an_engine_it_opens_cases_at` records a run with `OPENING`
set to `(2, 1)`: a proposal to engine 3 refused, then lee's answer refused. The test never
replays that run. Recorded by the code at 7913429 and replayed with today's code
(`uv run python reviews/2026-11/probes/p2_old_recordings.py 7913429`), it is the one history of
403 that today's code does not rebuild:

```
REFUSED tests/test_temporal_migrations.py::test_a_case_moves_on_temporal_only_to_an_engine_it_opens_cases_at refund-1 (ventoux.case, 9426ea3b): NondeterminismError: ... Activity machine does not handle this event: HistoryEvent(id: 30, WorkflowExecutionContinuedAsNew)
step 2, with today's code: {'equal': 383, 'its case was forgotten: no key, no replay (brief, D32)': 17, 'REFUSED by Temporal on replay': 1, 'no class to replay with': 2}
```

Here Temporal does refuse (the run went on to continue as new), so the case waits; in proof 1 it
does not, because nothing recorded follows the changed decision.

The same will happen at the next engine version, for every case that recorded such a refusal.
`problems` in `checked_migration` also reads the worker's catalog ("which this worker's catalog
doesn't have"): a refusal for a missing contract is decided again the same way once the contract
is deployed (not run; see Unproven).

Proposed fix, in words: make what the worker knew part of the history. Either fail the workflow
task for a proposal naming a version the code doesn't know or doesn't open at (the case waits for
code, as D51 does for its own version, and the proposal is decided once, by code that knows it);
or decide "known" behind a patch marker per version asked when a migration to it is proposed, so
a history without the marker replays the refusal. Add a fixture: a refusal recorded under the old
code, replayed by the new, compared by state.

#### 2.2 A request to forget stamps its audit records with the code's `ENGINE`, not with anything recorded (weakens)

`ForgetWorkflow.record` builds each record with the module constant `ENGINE`
(`temporal/forget.py`, `AuditRecord(self.recorded, at, None, ENGINE, ...)`). It holds today
because `ENGINE` has been 3 since the request began writing records. Once a fourth version exists,
a request open across the upgrade rebuilds its unwritten records saying 4 where the first run
made them saying 3, and nothing notices: Temporal compares a scheduled activity by type and ID,
never by input.

Promise touched: D76, "Each record carries its release and engine version (D51)"; D77, "The
forget request's own stream ... is written behind the patch marker `ventoux-forget-export`"; D51,
"The engine version is data in the case's state ... a replayed one at the version its history
recorded".

Proof (the fixture at_19b_forget_request, replayed with `ENGINE` set to 4 in memory only), commit
9b92c1a. `uv run python reviews/2026-11/probes/p2_forget_record_engine_from_code.py`:

```
recorded in the history: each record's engine: [3, 3, 3, 3]
replayed with ENGINE = 3: error None; engines [3, 3, 3, 3]
replayed with ENGINE = 4: error None; engines [4, 4, 4, 4]
RESULT: BROKEN - with the constant moved, the replay rebuilds records that say another engine version than the ones recorded, and nothing notices
```

Proposed fix: the request learns the version once, as a case does (a patch marker asked at its
start, or a field of its start), and stamps records with that.

#### 2.3 A case workflow's class settings decide where a recorded run switches or holds, and nothing records them (minor)

`events_per_run` and `audit_bound` are read by the workflow code on every pass of the loop. The
engine version is recorded; these are not. A deployment that lowers one replays every open run
with the new value. It fails closed (Temporal refuses the replay and the case waits, D17), but
nothing in the refusal names the setting, and neither the brief nor a guide says the setting must
not change while cases are open (the code comments say only "A test's workflow lowers it").

Promise touched: D27, "A count, never a clock, so replay switches at the same place".

Proof, commit 9b92c1a. `uv run python reviews/2026-11/probes/p2_class_settings_decide_replay.py`:

```
before_12b_paid:
  with the class that recorded it (DevelopmentCases): replays
  with SwitchesSooner: NondeterminismError: ... Continue as new workflow machine does not handle this event: HistoryEvent(id: 13, ActivityTaskScheduled)
at_19b_refund_export_retried:
  with the class that recorded it (QuicklyFailingExports): replays
  with HoldsSooner: NondeterminismError: ... Activity machine does not handle this event: HistoryEvent(id: 43, WorkflowExecutionCompleted)
RESULT: BROKEN - 2 recorded runs no longer replay once a class setting is lowered ...
```

Proposed fix: say so where the settings are declared and in the operations guide (lowering either
strands open runs until it is restored), or carry the value in the run's start as the engine
version is carried.

#### 2.4 The recorded fixtures leave whole workflow types and features with no kept history (weakens)

tests/histories holds 35 files: 34 histories and one carried state (`before_11h2_carried.json`).
Every file is loaded by a test. What no kept history exercises (read from the events of each
file):
- No history of type `ventoux.plan`: `PlanWorkflow` has none (the plan steps in three fixtures are
  seen only from the case's side).
- No `TIMER_STARTED` in any fixture: no timer (D44), no daily check of a child (D75).
- No child case (D75): no `child_ended` doorbell, no `close_by_parent`, no `ventoux.child.read`.
  The only replay of a child is of a history the test has just made with the same code
  (`test_a_history_with_a_child_replays`), which cannot show a later change.
- The registry: one history (`before_18d_registry`, 6 Updates), with no continue-as-new, no
  `ventoux-registry-keeping` marker (D81's amendment has no fixture), and no
  `ventoux.registry.ended` activity.
- Engine 3: one case history (`at_19b_refund_export_retried`); no case migrated to engine 3; no
  engine-3 run that continued as new with records unwritten.
- Signals never in a fixture: `claim`, `give_back`, `assign`, `unassign`, `change`, `migrate`,
  `shown`, `child_ended`, `close_by_parent`. No held option or attachment check (D67, D68), no
  repeated step (D73).
- The tests check "no error" only. Nothing compares what a replay rebuilds (finding 1's history A
  and the fixture `before_fix_retry_rejected_retried` below both replay with no error and rebuild
  another state).

Present: engine 1 (many), engine 2 (`ventoux-engine-2`, 7 fixtures), `ventoux-registry` (1),
`ventoux-forget-export` and `ventoux-forget-opener` (1), a state carried before 12b read as
engine 1.

Proof: the table under "What held", and for the rest
`uv run python reviews/2026-11/probes/p2_old_recordings.py 7913429`, whose 403 fresh histories do
hold these (45 plan runs, timers in 36 case runs, 57 child starts, 3 registry runs that continued
as new) and replay: the gap is in what is kept, not in what replays today.

Proposed fix: keep a few of those histories as fixtures at each merge (the probe's two plugins
do it for any commit), and compare what a replay rebuilds, not only that it raises nothing.

### What held

*Lead reviewer's check.* The three heavy probes behind this section were run again by the lead
reviewer, one after another, at source `3edb471`:

```
p2_old_recordings.py 7913429: {'equal': 384, no key (forgotten or withheld by the test): 17, 'no class to replay with': 2, 'REFUSED by Temporal on replay': 1}
RESULT: BROKEN - of the histories recorded at 7913429, today's code refuses or rebuilds differently 1 (each named above); 384 equal
p2_old_recordings.py dc2407e: {'equal': 320, no key: 16, 'no class to replay with': 2}
RESULT: HELD - 320 histories recorded at dc2407e replay with today's code and rebuild what they recorded
p2_old_recordings.py 2fde255: {'equal': 257, 'no class to replay with': 2, no key: 15}
RESULT: HELD - 257 histories recorded at 2fde255 replay with today's code and rebuild what they recorded
p2_time_travel.py
RESULT: HELD - every history read rebuilds, with today's code, each value the code that recorded it rebuilt (15 could not be read by one of the two)
p2_hash_seeds.py
RESULT: HELD - under seeds 0, 1, 2, 3, 4, every decision of every test gave the same states, lines, records, commands and refusals, in the same order
```

The one history refused at `7913429` is the one finding 1 is about. The counts differ by one from
the first run's (384 equal, where it gave 383), a test more having recorded a history this time.


**Job A: every recorded history, replayed and compared.**
`uv run python reviews/2026-11/probes/p2_replay_every_history.py` (commit 9b92c1a; the same table
under PYTHONHASHSEED 5 and 11). Columns: events; replay; how the recorded run ended; activities,
children, signals, timers, updates as recorded/on replay; patch markers; verdict.

```
at_19b_forget_request                        ventoux.forget    79 ok      completed   8/8  0/0  1/1  0/0  0/0  forget-export,forget-opener EQUAL
at_19b_refund_export_retried                 ventoux.case      43 ok      completed   3/3  0/0  0/0  0/0  0/0  engine-3 EQUAL
before_11b_proposal                          ventoux.case      19 ok      completed   1/1  0/0  0/0  0/0  0/0  -        EQUAL
before_11c_plan_closed                       ventoux.case      27 ok      completed   0/0  1/1  1/1  0/0  0/0  -        DIFFERENT
before_11c_workflow_cancelled_outside        ventoux.case      43 ok      completed   1/1  2/2  0/0  0/0  0/0  -        EQUAL
before_11c_workflow_closed                   ventoux.case      34 ok      completed   1/1  1/1  0/0  0/0  0/0  -        EQUAL
before_11f_refund                            ventoux.case      23 ok      completed   1/1  0/0  0/0  0/0  0/0  -        EQUAL
before_11f_switched                          ventoux.case      22 ok      completed   1/1  0/0  0/0  0/0  0/0  -        EQUAL
before_11h2_approved                         ventoux.case      19 ok      completed   1/1  0/0  0/0  0/0  0/0  -        EQUAL
before_11h2_carried                          no test replays this file as a history
before_11h2_switched                         ventoux.case      15 ok      completed   1/1  0/0  0/0  0/0  0/0  -        EQUAL
before_12b_paid                              ventoux.case      19 ok      completed   1/1  0/0  0/0  0/0  0/0  -        EQUAL
before_12b_settled                           ventoux.case      18 ok      completed   0/0  1/1  0/0  0/0  0/0  -        EQUAL
before_12b_switched                          ventoux.case      15 ok      completed   1/1  0/0  0/0  0/0  0/0  -        EQUAL
before_12b_waiting                           ventoux.case       8 ok      open        0/0  0/0  0/0  0/0  0/0  -        EQUAL
before_12c_forget_request                    ventoux.forget    29 ok      completed   3/3  0/0  1/1  0/0  0/0  -        EQUAL
before_12c_forgotten_by_its_opener           ventoux.case       9 ok      completed   0/0  0/0  0/0  0/0  0/0  -        EQUAL
before_12c_switched                          ventoux.case      15 ok      completed   1/1  0/0  0/0  0/0  0/0  -        EQUAL
before_12c_waiting                           ventoux.case       8 ok      open        0/0  0/0  0/0  0/0  0/0  -        EQUAL
before_12d_pending_edit_switched             ventoux.case       4 ok      open        0/0  0/0  0/0  0/0  0/0  -        EQUAL
before_12d_released_open                     ventoux.case       9 ok      open        0/0  0/0  0/0  0/0  0/0  engine-2 EQUAL
before_12d_released_waiting                  ventoux.case      13 ok      open        0/0  1/1  0/0  0/0  0/0  engine-2 EQUAL
before_12e_closed                            ventoux.case      11 ok      completed   0/0  0/0  0/0  0/0  0/0  engine-2 EQUAL
before_12e_draft_waiting                     ventoux.case      10 ok      open        0/0  0/0  0/0  0/0  0/0  engine-2 EQUAL
before_12e_migrated_switched                 ventoux.case       4 ok      open        0/0  0/0  0/0  0/0  0/0  -        EQUAL
before_12e_released_switched                 ventoux.case       4 ok      open        0/0  0/0  0/0  0/0  0/0  -        EQUAL
before_12e_released_waiting                  ventoux.case      13 ok      open        0/0  0/0  0/0  0/0  0/0  engine-2 EQUAL
before_18d_case_step_failed_switched         ventoux.case      11 ok      continued   0/0  0/0  0/0  0/0  0/0  engine-2 EQUAL
before_18d_production_case                   ventoux.case      28 ok      completed   2/2  0/0  0/0  0/0  0/0  registry,engine-2 DIFFERENT
before_18d_registry                          ventoux.registry  34 ok      open        0/0  0/0  0/0  0/0  6/6  -        EQUAL
before_fix_retry_rejected                    ventoux.case      38 ok      completed   1/1  0/0  0/0  0/0  0/0  -        DIFFERENT
before_fix_retry_rejected_retried            ventoux.case      48 ok      completed   1/1  0/0  0/0  0/0  0/0  -        DIFFERENT
before_fix_retry_rejected_unapproved         ventoux.case      62 refused completed   1/2  0/0  0/0  0/0  0/0  -        n/a (refused, as its test expects)
before_fix_untrusted_moment_closed           ventoux.case       6 refused completed   0/0  0/0  0/0  0/0  0/0  -        n/a (refused, as its test expects)
before_fix_untrusted_moment_set              ventoux.case      17 ok      completed   0/0  0/0  0/0  0/0  0/0  -        DIFFERENT
Differences in what the record holds:
```

Its RESULT line says BROKEN for the five DIFFERENT rows. Each is a recorded limit from before D51
("Version 1 is the engine as merged at b734098 ... no old branch is kept for a path merged before
it"), not a finding:
- `before_11c_plan_closed`: the `stop` signal recorded with no input is sent on replay with
  "the case is closing" (the test's comment says so; D28, D40).
- `before_fix_retry_rejected`, `..._retried`: the result's history differs (`pay#2 won't run` then,
  `pay#1 won't run ... needs attention again` now; in `_retried` 18 lines recorded, 20 on replay, a
  retry refused then and taken now). D26's amendment records it ("may not replay").
- `before_fix_untrusted_moment_set`: a `set` line names one more source on replay (D43, "Cases
  already open on a path the fix decides differently replay differently").
- `before_18d_production_case`: only the replayer's own task queue name in the registry's
  question; not a difference of the code.
The two "refused" rows are the two fixtures their tests expect Temporal to refuse.

What could not be compared beyond "no error" from the history alone: the 10 open histories (no
result recorded) and the registry's final state. For those the next probe asks the code that
recorded them.

**Each fixture rebuilt by the code that recorded it, against today's.**
`uv run python reviews/2026-11/probes/p2_time_travel.py` (worktrees at b734098, 5801ca0, 66e2cff,
2fde255, dc2407e, 43da6ca; 19 fixtures from 12b on): the report, the whole state as it would
cross continue-as-new, and everything sent are the same value for value; today's code only adds
fields (between 0 and 31). The full run was made before one comparison in the probe was corrected (an added `pinned` field in an activity input read as a difference for `before_18d_production_case`); that fixture was run again alone after the correction and is the same. So D52's "a history recorded under version 1 replays as version 1" and
D51's fixture for each version hold by state, not only by no error.
`RESULT: HELD - every history read rebuilds, with today's code, each value the code that recorded it rebuilt`.
Not covered: the 14 fixtures from before 12b (their recording commits predate what the test
comments name) and `before_12b_settled` (its class needs the test's plans).

**Job B: fresh histories recorded by older merges, replayed today.**
`p2_old_recordings.py <commit>` runs that commit's own Temporal tests in a worktree, keeps every
history, and replays each with today's code and the test's own workflow class:
- 7913429 (19b merged, engine 3): 403 histories; 383 equal, 17 forgotten (no key, D32), 2 with no
  class, 1 refused (finding 1, proof 2).
- dc2407e (18c merged, engine 2): 338 histories; 320 equal, 16 no key, 2 no class.
  `RESULT: HELD`.
- 2fde255 (12d merged, engine 2): 274 histories; 257 equal, 15 no key, 2 no class. `RESULT: HELD`.
These include registries recorded before the `ventoux-registry-keeping` patch (their Updates'
answers equal on replay, so D81's amendment holds), cases before the forget-export patch, plans,
timers, children and switches. A history fetched while a workflow task was under way is compared
only on what it recorded.

What Temporal does not compare, seen in these runs: an activity's input, timeouts and retry
policy, a signal's input, a result. Only the type and ID of a command are checked.

**Job C: non-determinism.**
- `uv run python reviews/2026-11/probes/p2_hash_seeds.py`: the 72 test files that start no server
  (4,008 tests, 58,432 results of `decide`, `interpret` and the registry's requests) under
  PYTHONHASHSEED 0 to 4: every state, history line, audit record, command and refusal the same,
  in the same order. `RESULT: HELD`.
- `... p2_hash_seeds.py --amplify 0 1 2 3`: the same with every registered role stated by whoever
  acts and two more sources on every value, so each set has an order to leak: `RESULT: HELD`.
  Control: with `role_that_counts` replaced in memory by a copy that forgets `sorted`
  (`P2_SEED_CONTROL=1`), digests do differ between seeds, so the probe sees a leak when there is
  one. Since digests match across processes, no memory address or clock reaches them either.
- Read: `core` and `case` import no clock, randomness or I/O; no `lru_cache`, no module-level
  mutable table; sets in the workflow classes (`starting`, `opened`) are used for membership
  only; `state_as_data`, `record_as_data` and the child's ending sort every set they write.
- A role's rights changed in the catalog under an open engine-3 case
  (`p2_catalog_role_change_pays.py`): the replay does take an approval the case had refused and
  asks for the payment, but the audit export that follows every decision makes Temporal refuse
  the replay, so the case waits: `RESULT: HELD`. See Unproven for a case at engine 1 or 2.

### Unproven

- **A catalog change under an open case at engine 1 or 2.** What a role may approve, and which
  roles and contracts exist, are read from the workflow class's catalog on every decision. At
  engine 3 the export trips Temporal's check (above). A case at engine 1 or 2 exports nothing, so
  a refused approval taken on replay would schedule the payment as the run's next command with
  nothing recorded to contradict it. Not run: my live two-worker attempt on the test server did
  not get the second worker to pick the task up within its bound. D22 says "a replay after
  someone's roles changed would decide differently", and guards the person's roles only.
- **A migration refused for a contract the worker's catalog lacked**, taken on replay once the
  contract is deployed: same mechanism as finding 1, read in `checked_migration`, not run.
- **A signal the old code had no handler for** (a newer client's `assign`, `retry_export`) is kept
  unhandled by Temporal's SDK and decided, at its recorded place, when newer code replays. Read in
  the SDK, not run.
- **Pydantic's own messages in history lines** (`before_activity.py` quotes `e['msg']`): a
  dependency upgrade would change a line's text on replay. Not run.

### Unchecked

- The plan interpreter under replay beyond the 45 plan histories recorded at 7913429 and those at
  the two older commits (no finding; `core/interpreter.py` is unchanged since b734098).
- A real Temporal cluster; only the SDK's Replayer and the tests' time-skipping server were used.
- Older merges than 2fde255 for fresh recordings, and 3c2ad1a (19a merged) itself: the window of
  finding 1 is shown through 7913429's test, not recorded at 3c2ad1a.
- A git worktree at `scratchpad/wt4` (f79b0e5) is listed by `git worktree list`; it is not one of
  mine and I left it. Mine were all removed.


---

## Pass 3: fail closed, and secrets

Every probe below was last run at commit `c2739ad` (the source under `src/` is unchanged since
`3edb471`; `git diff --quiet 3edb471 HEAD -- src` says so). Each is run from the repository root
with `uv run python reviews/2026-11/probes/<name>.py`. Marker secrets in the probes are made up;
their values are never printed here ("the marker").

### Tally for Part A

Sites listed by search over `src/ventoux` (every `except` and `suppress`; `.get(`, `getattr(`,
`next(…, None)`, `setdefault`, `or <default>`, `is None:`; `all(`/`any(`), and how many I read in
their function, not only on their line. The second and third numbers are approximate: I counted
functions read, not lines.

| Package | `except` sites listed | handlers read | defaults / `all`,`any` listed | read | suspicious | proven |
|---|---|---|---|---|---|---|
| core | 28 | 28 | 71 / 12 | about 40 | 3 | 2 (findings 3, 10) |
| case | 61 | about 20 | 293 / 70 | about 45 (registry.py, activation.py, guards' role comparisons, runtime's output check, releases' reading) | 3 | 0 |
| temporal | 45 | about 20 | 89 / 12 | about 35 (codec.py, converter.py, registry.py, logs.py whole) | 3 | 1 (finding 1, where it lands) |
| tooling | 88 | 88 | 59 / 9 | all (cli.py, doctor.py, vault.py, audit.py, keys.py, summary.py, conformance.py, deployment.py, environments.py, probes.py, connecting.py, releases.py, draft_sheet.py whole) | 14 | 8 (findings 1, 2, 4, 5, 6, 7, 8, 9) |
| authoring | 13 | 13 | 4 / 0 | all | 1 | 0 (held) |

`model_config`: every Pydantic model in `src/ventoux` sets `extra="forbid"` (14 configurations
over 10 base models; the contract models are refused a `model_config` and are checked field by
field). The two places that read JSON without it are plain dataclasses behind a `TypeAdapter`
(finding 7). The `case` and `temporal` packages are the least covered here: I read the parts named
above and did not sweep `runtime.py`, `cases.py`, `flow.py` or `state.py` line by line.

### Findings

#### 3.1 A `VAULT_TOKEN` ending with a line break is quoted in an error, and reaches the caller, Temporal's history and the worker's output (breaks a promise)

`Https.__call__` (`src/ventoux/tooling/vault.py`, lines 366 to 400) catches `HTTPError`, `URLError`,
`TimeoutError`, `OSError` and `HTTPException`. A token that ends with a line break (a secret
mounted from a file usually does) makes the standard library refuse the header with
`ValueError("Invalid header value b'<the token>\n'")`, which none of those catch. The error is
neither `KeyRefused` nor `KeyUnavailable`, and its text is the token. From there: `start_case`
raises it to the trusted caller; on a worker, the codec raises it while a workflow task's commands
are encoded, the SDK writes `Failed encoding completion: <the error>` as the workflow task's
failure (not through the failure converter, so it isn't sealed), Temporal stores it in the case's
history on every retry, and the SDK's core prints it on the worker's standard error, which the
log filter of `src/ventoux/temporal/logs.py` doesn't see. In some runs the Python logger
`temporalio.activity` holds it too (`Exception handling failed, original error: …`, from the audit
export activity).

Promises touched. D78: "The token is read from `VAULT_TOKEN` as each call is made, never kept on
the object, never said in a message, a log, a `repr` or a recording (D62)". D78: "**Two kinds of
error, never an empty value or a guess**". D81: "no output of doctor's, a failure included, holds a
secret's value" (doctor itself held: it says `met ValueError`).

Proof, at `c2739ad` (marker masked):

```
$ uv run python reviews/2026-11/probes/p3_vault_token_in_errors.py
VaultKeys.state raised ValueError: "Invalid header value b'<THE MARKER>\\n'"
  the token is in the error's text: True
start_case raised ValueError to the caller; the token is in its text: True
… WARN temporalio_sdk_core::worker::workflow: Failing workflow task run_id=… failure=Failure { failure: Some(Failure { message: "Failed encoding completion: Invalid header value b'<THE MARKER>\\n'", …
IN HISTORY (claim-1 run 1): …'…Failed encoding completion: Invalid header value b\'<THE MARKER>\\n\'*'…
LOGGED: Exception handling failed, original error: Invalid header value b'<THE MARKER>\n' ({'activity_id': '1', 'activity_type': 'ventoux.audit.append', …
RESULT: BROKEN - a VAULT_TOKEN ending with a line break is quoted in a ValueError that is neither KeyRefused nor KeyUnavailable; it reaches the caller, Temporal's history and the worker's log
```

The probe uses the real transport against a stand-in Vault on 127.0.0.1, a case worker on the
time-skipping server, and the public `start_case` and `answer`. The `LOGGED` line appears in some
runs only (it depends on which task meets the token first); the history and the core's line
appeared in each of three runs.

Probe: `reviews/2026-11/probes/p3_vault_token_in_errors.py`.

Proposed fix, in words: refuse a token holding anything but printable ASCII where it is read
(`KeyUnavailable`, "VAULT_TOKEN holds a character a header can't: check for a line break", never
quoting it), and have `Https.__call__` turn any other exception into `Unreachable` with its type's
name alone, so nothing a library says about a request can leave the transport. Separately, the
general path is worth closing: whatever a key provider raises during encoding is written by the
SDK into the history in clear, so the codec should let out only its own two errors, with its own
words.

#### 3.2 A `404` from anything is read as Vault's answer "never made", for good, and `ventoux doctor` passes a server that isn't Vault (breaks a promise)

`VaultKeys.key_config` and `VaultKeys.marked` read status `404` as "no key" and "no mark" without
looking at the body. A wrong address, an ingress with no backend, or a mount path that isn't
mounted answers `404` too. Against a plain web server that answers every request `404` with an
HTML page, a live case's key reads `never made`; `seal`, `open` and `destroy` raise `KeyRefused`,
the final kind that is never retried; and doctor's `keys.reachable` says `passed … answers: a key
that can't exist was never made`. A `200` is checked for Ventoux's shape; a `404` is not.

Promise touched. D78: "A key's state is `destroyed` or `never made` only on Vault's answer;
anything else is `KeyUnavailable`", and "`KeyUnavailable`, not now: Vault unreachable, timing out,
refusing the token, hanging up, or answering something unreadable". D81: "`passed` (seen to
hold)".

Proof, at `c2739ad`:

```
$ uv run python reviews/2026-11/probes/p3_any_404_is_never_made.py
state of refund-1001, asked of a server that isn't Vault: 'never made'
seal: KeyRefused (final: True): there is no key for refund-1001, so its sensitive values can't be read or written
open: KeyRefused (final: True): there is no key for refund-1001, so its sensitive values can't be read or written
destroy: KeyRefused (final: True): there is no key for refund-1001 to destroy: no case was opened with its ID
doctor: passed     keys.reachable: the key service at http://127.0.0.1:34071 answers: a key that can't exist was never made
doctor: unchecked  keys.policy: Vault answered sys/capabilities-self with status 404
doctor's output holds the token: False
RESULT: BROKEN - …
```

Probe: `reviews/2026-11/probes/p3_any_404_is_never_made.py`.

Proposed fix, in words: take a `404` as Vault's only in the shape Vault gives it (a JSON object
with an `errors` list), and anything else as `KeyUnavailable`; and have `keys.reachable` see
something only Vault says (for instance that the transit mount exists, or `sys/capabilities-self`
answering `200`) before it says `passed`. A wrong mount name still answers `404` in Vault's own
shape, so doctor is the place that would see that; I could not check it against a real Vault (see
Unchecked).

#### 3.3 A contract validator's message is copied into the history, the needs-attention line and the audit record in clear (breaks a promise)

A contract's input and output models are the team's Pydantic models. Registration accepts a
`@field_validator` on one. When it refuses a value, `one_line`
(`src/ventoux/core/before_activity.py`, line 126) copies Pydantic's `msg`, which for a validator is
`Value error, ` followed by the team's own text, into `InputRefused`
(`before_activity.py`, line 119), into the plan interpreter's `Stop`
(`src/ventoux/core/interpreter.py`, line 302) and into a case step's failure reason
(`src/ventoux/case/runtime.py`, line 1263). A message that quotes its value (`'…' is not a national
ID`) then stands in clear in the history, the needs-attention line and the audit record, for a
field declared sensitive too. The same value quoted by the activity's own exception reads
`‹sensitive›`, because the engine wraps what it can't vouch for; a validator's text is the same
team's text and isn't wrapped.

Promises touched. D30: "**A refusal or a failure names the field and the kind of value, never the
value**". D31: "everyone reads `‹sensitive›` wherever a value would be written: history lines,
refusals, failures", and "An activity's own message is treated as sensitive in every case, since
Ventoux can't know what it says".

Proof, at `c2739ad`:

```
$ uv run python reviews/2026-11/probes/p3_validator_message_in_history.py
an input refused by the contract's validator:
  history: look#1 failed: people.lookup@1 doesn't take these inputs: national_id: Value error, '<THE NATIONAL ID>' is not a national ID: write it without spaces
  the national ID is in clear in: ['history', 'needs_attention', 'audit']
an output refused by the contract's validator:
  history: look#1 failed: people.status@1 gave an output its contract doesn't declare: status: Value error, '<WHAT THE SYSTEM GAVE>' is not a status
  what the system gave is in clear in: ['history', 'needs_attention', 'audit']
the activity's own failure quoting it: look#1 failed: people.status@1 failed with RuntimeError: ‹sensitive›
RESULT: BROKEN - …
```

The probe runs on the in-memory engine (`ventoux.testing.run_case`); I did not run it on Temporal.
Pydantic's own messages for the types a contract may hold (text, boolean, decimal, day, one of
some texts) quote no value: I tried each, strict and not (`scratchpad/p3/pd.py`, not a probe).
Related, shown by a command and not made a probe: the contract hash doesn't see a validator
(two contracts differing only by one hash the same, and the catalog registers one over the other
with no conflict), so a validator added later changes what a contract takes with no new version.

Probe: `reviews/2026-11/probes/p3_validator_message_in_history.py`.

Proposed fix, in words: either refuse a contract model that defines a validator at registration
(the schema is then all a contract checks, and the hash sees all of it), or say a `value_error` by
the field and "its contract's own check refused it" and wrap the text as an activity's is.

#### 3.4 A path that isn't there reads as nothing to compare: `summary`, `conformance --since` and `check` end 0 (weakens a promise; for `summary`, breaks one)

- `ventoux summary --packages NAME` skips a folder that isn't in either tree
  (`src/ventoux/tooling/summary.py`, `found_in`: `if not folder.is_dir(): continue`). With the
  folder misspelt, the summary has an empty "Packages" section and the step ends 0, on a pull
  request whose package `ventoux release` refuses.
- `ventoux conformance --since BASE` with no `BASE/suite.json` prints `no result to compare` and
  ends 0. The code says this is for "a base with no suite (before the suite existed)"; a base path
  that is wrong reads the same.
- `ventoux check` and `ventoux check --unchanged` print nothing and end 0 when the configured
  `cases` and `packages` folders both aren't there, and when a builder file defines no case at its
  top level (for instance under `if __name__ == "__main__":`, since the file is run under another
  name).

Promise touched. D55, as amended in 13e: "Anything it can't read or the diff refuses fails the
step, saying why, never read as nothing changed". CLAUDE.md: "Fail closed: anything the engine
can't evaluate or doesn't recognise is an error, never a permissive default". With only `cases`
misnamed, `check --unchanged` does fail (the package folder reads as stale), so the gap is the
silent case, not the usual one.

Proof, at `c2739ad`:

```
$ uv run python reviews/2026-11/probes/p3_missing_paths_read_as_nothing.py
ventoux summary --packages packages: exit 1
ventoux summary --packages package (no such folder): exit 0
  its Packages section: '\n\n\n'
ventoux conformance --since no-such-folder: exit 0: no-such-folder has no suite.json: no result to compare
ventoux check, cases and packages misnamed: exit 0, output ''
ventoux check --unchanged, cases and packages misnamed: exit 0, output ''
ventoux check, a builder file defining no case at its top level: exit 0, output ''
RESULT: BROKEN - …
```

Probe: `reviews/2026-11/probes/p3_missing_paths_read_as_nothing.py`.

Proposed fix, in words: `summary` fails (exit 2) on a `--packages` folder that is in neither tree;
`conformance --since` tells a base folder that isn't there (exit 2) from one that is there with no
suite; `check` says how many builder files and cases it found, and refuses none found unless the
configuration says so.

#### 3.5 `read_audit` hands a value in a shape it doesn't know to any reader, in clear (weakens a promise)

`shown` (`src/ventoux/tooling/audit.py`, line 181) filters a stored value only when its keys are
exactly `{value, visible_to}` or `{sealed, part, visible_to}`: "in clear: seen by whoever reads the
case's records" is the fallback for every other shape. A stored value in the hidden shape with one
more key is given whole to a reader who holds none of its roles. Nothing writes that shape today;
a later writer's record read by this reader, or a damaged row, would be shown instead of refused.
A record has no format number a reader could refuse on.

Promises touched. D77: "a value whose field narrows who sees it is said hidden unless the reader
holds one of those roles". CLAUDE.md: "a view hiding more than its source", and fail closed.

Proof, at `c2739ad`:

```
$ uv run python reviews/2026-11/probes/p3_audit_unknown_shape_in_clear.py
a reader holding only `support` reads:
  the known shape  : hidden (needs fraud)
  the unknown shape: {'value': 'fraud score 97', 'visible_to': ['fraud'], 'written_by': 4}
RESULT: BROKEN - …
```

Probe: `reviews/2026-11/probes/p3_audit_unknown_shape_in_clear.py`.

Proposed fix, in words: a stored value that is an object holding `visible_to`, `sealed` or `value`
and isn't exactly one of the two shapes is refused, naming the record and the field; and a record
says its format, which `read_audit` checks.

#### 3.6 A package file with a key written twice is checked, released and run with the last one (weakens a promise)

Every reader of a definition's JSON uses `json.loads`, which keeps the last of two equal keys in
silence: `ventoux check --unchanged` for a `by_hand` package, `ventoux release`, `ventoux map`,
and the engine. The authoring loop refuses exactly this from a model (`no_key_twice`,
`src/ventoux/authoring/answers.py`: "Python's reader would keep the last one, silently"), and a
draft read back for its sheet (`reference_of`, `src/ventoux/authoring/approve.py`, line 132) is
read without that refusal. Ventoux's own readings (the map, the diff) agree with what runs; a
person reading the file, or a pull request's diff, meets the first.

Promise touched. D1: the JSON is what is reviewed and what runs ("the JSON that runs is committed
and reviewed", D59). D63, as built: a key given twice is refused in a model's answer.

Proof, at `c2739ad`:

```
$ uv run python reviews/2026-11/probes/p3_duplicate_keys_last_wins.py
`roles` is written 2 times in the step review
ventoux check --unchanged: 0 ✓ refund is valid (3 steps): written by hand, checked, not compared
ventoux release: 0 refund 1 released: digest d42dce7d7779 (method 1)
ventoux map says of who answers: ['- review is a task for adjuster, answered approve or reject. …']
the same text as a model's answer: refused (a key is given twice: roles)
RESULT: BROKEN - …
```

Probe: `reviews/2026-11/probes/p3_duplicate_keys_last_wins.py`.

Proposed fix, in words: one function reads a definition's text everywhere (packages, records,
stories, drafts), refusing a key given twice as `one_object` does, naming the key and its path.

#### 3.7 A worker's manifest file and a release record ignore keys nobody declares (weakens a promise)

`MANIFEST` (`src/ventoux/tooling/environments.py`) and `RECORD`
(`src/ventoux/tooling/releases.py`) are Pydantic `TypeAdapter`s over plain dataclasses: an unknown
key is dropped and values are converted loosely. A manifest written by hand for a worker in
another language with `binds` misspelt publishes no binding, with no word; `"development": "no"`
and `0` read as `false`; a record's unknown keys say nothing. Where it matters most the registry
still fails closed (a production case worker whose `keys` is missing or misspelt is refused), so
this is the weaker kind.

Promise touched. CLAUDE.md: "anything the engine … doesn't recognise is an error". D54: "A worker
in another SDK language publishes the same manifest as JSON".

Proof, at `c2739ad`:

```
$ uv run python reviews/2026-11/probes/p3_unknown_keys_ignored.py
manifest read: keys Provided(name='FileKeys', development=False) | audit Provided(name='FileAudit', development=False) | binds {}
record read: refund 1 (the keys `retired` and `format` said nothing)
RESULT: BROKEN - …
```

Probe: `reviews/2026-11/probes/p3_unknown_keys_ignored.py`.

Proposed fix, in words: read both strictly, with unknown keys refused, as every definition is.

#### 3.8 Doctor says "each certificate in date" of a certificate that isn't valid yet (minor; misleads)

`certificate_problems` (`src/ventoux/tooling/doctor.py`, line 178) compares the certificate's end
with now, never its start. D81: "`passed` (seen to hold)".

```
$ uv run python reviews/2026-11/probes/p3_doctor_certificate_not_yet_valid.py
the certificate is valid from 2027-11-10
temporal.identities: passed: each identity's files are there (operator): each key readable by its owner only, each certificate in date
RESULT: BROKEN - …
```

Probe: `reviews/2026-11/probes/p3_doctor_certificate_not_yet_valid.py`. Fix: compare both ends.

#### 3.9 A role registered twice takes the second `approves`, looser included, with no error (minor)

`Catalog.register_role` (`src/ventoux/core/catalog.py`, line 133) writes `approves` over the
earlier one and only ever adds `operates`, `forgets` and the others. A contract registered twice
with other content is refused (`ContractConflict`); a role isn't. CLAUDE.md: "Policies can be made
stricter downstream, never looser".

```
$ uv run python reviews/2026-11/probes/p3_role_registered_twice.py
support, then support approving high: {'support': 'high'}
lead approving high and operating, then lead alone: {'lead': None, 'support': 'high'} ['lead']
RESULT: BROKEN - …
```

Probe: `reviews/2026-11/probes/p3_role_registered_twice.py`. Fix: refuse a second registration
that says anything else, as a contract's is.

#### 3.10 A result too small for decimal128 is zero, with no error (minor)

`CONTEXT` (`src/ventoux/core/expressions/model.py`, line 43) traps `Overflow`, not `Underflow`, so
`a * a` for `a = 1E-6143` is `0E-6176` and `a * a > 0` is false, while `1E+6143 * 1E+6143` is an
`ExpressionError`. D20 doesn't say which it should be; the code's own comment says "an error rather
than a special value when something goes wrong". No realistic amount is this small.

```
$ uv run python reviews/2026-11/probes/p3_expression_underflow_is_zero.py
a * a, a = 1E-6143: Decimal('0E-6176')
a * a > 0, a = 1E-6143: False
a * a, a = 1E+6143: ExpressionError: `*` gives a number too large for an expression (decimal128)
RESULT: BROKEN - …
```

Probe: `reviews/2026-11/probes/p3_expression_underflow_is_zero.py`. Fix: trap `Underflow` too, or
record in D20 that a result below decimal128's range is zero, in both evaluators.

### What held

- **Expressions fail closed and quote no value.** 37 expressions that must be refused (wrong
  arity, `==` across types, a missing value, an int or a float in the case file, NaN, Infinity,
  `1e400`, an unknown operator, two keys, depth 40, a mixed or empty `in` list, a day that isn't
  on the calendar, `sum` over a list that isn't records) are each `ExpressionInvalid` or
  `ExpressionError`, and no error holds the recognisable value given.
  `reviews/2026-11/probes/p3_expressions_fail_closed.py`.
- **The live provider never says its key.** A refused request, a key ending with a line break and
  a key that isn't ASCII each give `ProviderFailed: the model's API failed: <kind>`; the key is in
  no error text or traceback. `reviews/2026-11/probes/p3_provider_key_never_said.py`.
- **Doctor says no secret.** With `VAULT_TOKEN` set to the marker, doctor's whole output doesn't
  hold it (in `p3_any_404_is_never_made.py`, last line before the result). With an identity whose
  `cert` and `key` files hold a marker in malformed PEM, `ventoux doctor production`, `ventoux
  environment check production` and `ventoux advise` print the files' paths and an error's kind,
  never their contents (run by hand in a temporary project: `grep -c` of the marker over all three
  outputs gave 0; `Failed client connect: … CertificateParseError`; doctor's rules that connect
  said `unchecked … met RuntimeError, which it doesn't expect`, and it ended 1 on the rules that
  failed).
- **`repr` of `VaultKeys` and its transport** holds no token (`scratchpad/p3/v1.py`, by hand: all
  three `False`).
- **Doctor never passes a rule that raised.** By reading `finding_of`, and by the run above: an
  unexpected error is `unchecked`, by its kind.
- **`ventoux hashes`** refuses a lock that isn't an object (exit 2), an empty file (exit 2), a
  missing file (exit 2), and lists every contract an empty lock doesn't record (exit 1).
- **`ventoux release`, `map`, `diff`** on an empty or missing folder: exit 2, saying it has no
  `case.json`. `release` with no releases folder named: exit 2. `--releases` naming a file: exit
  2. `schema --unchanged` on an empty folder: exit 1, naming both files. `notes` for a release that
  isn't recorded: exit 1. (Commands run by hand in a temporary project.)
- **The diff's roles.** A plan's approvers changed from `support-lead` to `support` reads
  "Stricter", which looked wrong and isn't: `support` may approve no risk, so nobody may approve
  after, and the same summary fails the step because `ventoux release` refuses it (seen in the
  summary run of finding 4). A leaf no comparison knows is `not proven` (by reading `judged`).
- **The activation check** has no empty-collection pass that I could find by reading
  `activation_problems`, `live` and `bound_problems`: no poller is a problem, a poller with no
  manifest is a problem, and a queue whose pollers are all refused is a problem. Not run against
  Temporal.
- **The codec** refuses a sensitive part with no workflow ID, and the converter refuses a part
  that arrives still encrypted (by reading; other reviewers ran the codec on Temporal).

### Unproven

- `src/ventoux/tooling/doctor.py`, `providers_are_production` (line 262): with no case worker's
  manifest in a production registry it says `passed … no case worker has published a manifest`,
  and `environment.workers` passes when nothing is active. Both are true statements about nothing;
  whether "seen to hold" should cover them is the maintainer's call. Not run (needs a registry).
- `src/ventoux/tooling/doctor.py`, `key_problems` (line 166): a key file is judged by its mode
  alone, so a directory, an empty file, or a certificate named as the key passes "each key
  readable by its owner only". By reading only.
- `src/ventoux/temporal/converter.py`, `rewrapped` (line 126): `{"‹sensitive›": -1}` would read the
  last part (Python's negative index) instead of being refused. By reading only; it needs someone
  who can write a payload.
- `src/ventoux/core/expressions/evaluate.py`, line 103: `exists` of a field holding a value no
  expression can read (a dict, a NaN) is `true`; I saw it by calling `evaluate` directly, and did
  not find a way for the case file to hold such a value through a public entry.
- `src/ventoux/tooling/keys.py`, `_read` (line 128): a `FileKeys` file that has gone reads as "no
  key was ever made" for every case, and a damaged one raises `JSONDecodeError`, neither of the two
  key errors. Development only, so not pursued.
- `ventoux conformance --suite FOLDER` with no `suite.json` ends with a traceback
  (`FileNotFoundError`) and exit 1, where the command's own table says 2 for a suite that can't be
  read. Seen once by hand (`ventoux conformance --suite nosuchdir`); minor, no probe.
- `contracts.lock.json` records `letters.draft@1`, which the development catalog no longer
  registers, and `ventoux hashes` says "every contract matches": a recorded contract that has gone
  from the catalog is not said. Seen by hand; I did not find the brief promising otherwise.

### Unchecked

- **A real Vault.** No `vault` binary was tried (the rules say not to look for one). Finding 2 is
  shown against a web server that isn't Vault, which is the point of it; what a real Vault answers
  for a mount that isn't there, or for a key-value mount of version 1 at the marks' path, I could
  not see. If a version 1 mount accepts the mark's write and answers `404` on its metadata, a
  forgotten case would read `never made` after its key is deleted: worth one test where Vault is
  installed.
- **A real Temporal cluster with mTLS.** Doctor's `temporal.mtls-required` and
  `temporal.reader-cannot-write` were read, not run against a server that authorizes.
- **Finding 3 on Temporal.** Shown on the in-memory engine only; where the reason is written on
  Temporal (the report, the audit export) follows from the same line being recorded, but I did not
  run it there.
- **The plain renderer, the "will never do" sheet and the case map on shapes they don't know**: not
  reached.
- **`scripts/check_wheel.py`**: read in outline only (it lists what must never ship; it doesn't
  list what may).
- **Roles unknown to the catalog at each runtime check** (answer, propose, close, claim, assign,
  edit, migrate, forget, retry): only `role_that_counts` was read; the other passes cover people.
- **`case/runtime.py`, `temporal/cases.py`, `case/flow.py`, `case/state.py`** were not swept line
  by line for defaults: see the tally.


---

## Pass 4: test strength

All runs are at commit f79b0e5 (source 3edb471: the two differ only under reviews/), in a detached
worktree, with `reviews/2026-11/probes/mutate.sh`. The exact command lines are in
`reviews/2026-11/probes/p4_mutations.sh`, the raw output in `reviews/2026-11/probes/p4_mutations.log`.
Each mutation is one exact-string replacement of a line that enforces a stated rule. "QUICK" is 75
test files that need no Temporal server (2,622 tests); "REST" is the other ten such files (with
QUICK: 4,385 tests, every test that isn't Temporal-backed); "TEMP" is every `tests/test_temporal*.py`.
A mutation is called a survivor only after the sets named in its row all passed.

### Counts

| package | mutations | killed | survived | equivalent/backstop |
|---|---|---|---|---|
| core | 76 | 67 | 7 | 2 |
| case | 97 | 83 | 13 | 1 |
| temporal | 32 | 29 | 3 | 0 |
| tooling | 33 | 31 | 2 | 0 |
| authoring | 25 | 24 | 1 | 0 |
| total | 263 | 234 | 26 | 3 |

(`tool22`, sampled for D81, mutates case/registry.py and is counted under case.)

#### Every mutation that passed at least one set

| mutation | file | rule | sets run | verdict |
|---|---|---|---|---|
| auth12_unfenced_prose | authoring/answers.py | D63 one fenced block only | targeted files: passed, FAST: passed | survived |
| case26_repeated_high_risk | case/runtime.py | D73 a repeated high-risk step is refused | QUICK: passed, REST: passed, TEMP: passed | survived |
| case41_closes_when_any | case/closing.py | D10 every milestone in closes_when | QUICK: passed, REST: passed, TEMP: passed | survived |
| case44_forget_family_ignores_children | case/forgetting.py | D75 strictest of the family | QUICK: passed, REST: passed, TEMP: killed | killed |
| case69_digest_method | case/releases.py | D51 a method this code knows | QUICK: passed | equiv |
| core02_approver_role_not_listed | core/approval.py | D11/D23 the approval lists its roles | QUICK: passed, FAST: passed, TEMP: passed | survived |
| core06_digest_number_as_text | core/approval.py | D11 250 and "250" never share a digest | QUICK: passed, FAST: passed | survived |
| core22_infinite_number_fits | core/form.py | D20 a number is a finite decimal | QUICK: passed, FAST: passed | survived |
| core23_empty_option_fits | core/form.py | D67 an option | QUICK: passed, FAST: passed | survived |
| core24_empty_attachment_fits | core/form.py | D68 attachment ID | QUICK: passed, FAST: passed | survived |
| core35_moment_read | core/expressions/evaluate.py | D66 a moment is not a date | QUICK: passed, FAST: passed | equiv |
| caseR01_migration_label_mismatch | case/requests.py | D53 a migration is its release and its mapping | QUICK: passed, REST: passed | survived |
| caseR02_shown_unset | case/runtime.py | D16 a reference not set has no record | QUICK: passed, REST: passed | survived |
| caseR03_notes_no_record_before | case/notes.py | D57 notes compare with the record before | QUICK: passed, REST: passed | survived |
| caseR04_notes_contract_missing | case/notes.py | D57 notes read the promise recorded | QUICK: passed, REST: passed | survived |
| caseR06_reading_unknown_type | case/reading.py | CLAUDE.md: plain reading has a negative test for an unknown input | QUICK: passed, REST: passed | survived |
| caseR07_reading_unknown_state | case/reading.py | CLAUDE.md: plan reading of an unknown state kind | QUICK: passed, REST: passed | survived |
| caseR08_plain_unknown_reading | case/plain.py | CLAUDE.md: plain reading of an unknown kind | QUICK: passed, REST: passed | survived |
| caseR09_digest_unknown_value | case/releases.py | D50 fail closed: never left out of the digest | QUICK: passed, REST: passed | survived |
| caseR10_record_other_package | case/releases.py | D50 a record of this package | QUICK: passed, REST: passed | survived |
| caseR11_diff_unknown_value | case/changes.py | D55 fail closed: never left unsaid | QUICK: passed, REST: passed | survived |
| caseR15_story_answer_names_one | case/story.py | D45 a story's answer names one | QUICK: passed, REST: passed | survived |
| coreR01_promise_key_not_text | core/promise.py | D83 a promise holds no key that isn't a text | QUICK: passed, REST: passed | survived |
| coreR11_item_outside | core/expressions/evaluate.py | fail closed: item only inside count/sum (backstop) | QUICK: passed, REST: passed | equiv |
| temp16_hold_strict | temporal/cases.py | D77 hold at the bound | targeted files: passed | survived |
| temp20_forget_child_alone | temporal/forget.py | D75 a child is not forgotten alone | targeted files: passed, TEMP: killed | killed |
| temp26_forget_identifier | temporal/forget.py | D22 identifier spelling | targeted files: passed | survived |
| temp31_carried_bool_number | temporal/carried.py | D27 carried state read fail closed | targeted files: passed | survived |
| tool11_vault_token_unset | tooling/vault.py | D62/D78 token only from env | targeted files: passed, FAST: passed | survived |
| tool21_doctor_bound | tooling/doctor.py | D81 bound | targeted files: passed, FAST: passed | survived |
| coreU02_type_check_unknown | core/expressions/check.py | CLAUDE.md: every evaluator has a negative test for an input it doesn't know: type checker | QUICK: passed, REST: passed | survived |


"Equivalent/backstop" means the mutated line can't be reached through the public reading of a
definition because an earlier check refuses first; each is explained under "What held".

### Findings

*Lead reviewer's check.* The three survivors behind F1, F2 and F4 were run again by the lead
reviewer, in the main tree, against the whole suite (`reviews/2026-11/probes/mutate.sh <name>
<file> <old> <new> tests`, at source `3edb471`):

```
== case41_closes_when_any: 4694 passed, 3 skipped in 338.99s (0:05:38)
== core02_approver_role_not_listed: 4694 passed, 3 skipped in 342.67s (0:05:42)
== case26_repeated_high_risk: 4694 passed, 3 skipped in 346.73s (0:05:46)
```

So each of those three rules can be removed and all 4,694 tests still pass. The other survivors
were run by the pass's reviewer only, against the test sets the table names.


Every finding here is *weakens one*: the rule holds today (the unmutated suite passes), and the
run shows that removing the rule changes no test's result. None is a broken promise.

#### 4.1 An approver's role need not be one the approval lists, and no test notices (weakens)

`approver_role` (core/approval.py:45) keeps only the roles "that the approval lists and that may
approve its risk". With `if role in roles` made `if True`, a person holding one listed role that
may NOT approve the risk, and another registered role the approval does not list that may, is
accepted. D23: "the person has one of its roles. An approval adds: the role may approve the
activity's risk". The same function judges a plan's approval state and a case step's approval
(case/answers.py), so the gap is in both.
Proof: `core02_approver_role_not_listed` passed QUICK, FAST (4,385 passed) and TEMP (284 passed): every test file but the three that only start a development server.
Fix: one negative test per engine: an approver with roles {listed, low risk} and {unlisted,
high risk} is refused a high-risk approval, with the risk refusal's message.

#### 4.2 `closes_when` could close on ANY of its milestones, and no test notices (weakens)

case/closing.py:213 `all(milestone in state.milestones ...)` made `any(...)`. D10: "`closes_when=
<milestones>` closes the case as soon as they are reached". Every test of `closes_when` in the
non-Temporal suite names one milestone, or reaches all of them in the same decision.
Proof: `case41_closes_when_any` passed QUICK, REST and TEMP (284 passed). Fix: a case with two `closes_when` milestones, one reached: still open.

#### 4.3 (withdrawn) The family's forgetting

`case44_forget_family_ignores_children` passed all 4,385 non-Temporal tests and is killed by one
Temporal test, `tests/test_temporal_children.py::test_the_familys_forgetting_is_the_strictest_of_its_cases`.
So D75's "The stricter `forgetting` of the parent and its pinned children applies to all" is
tested, by that one slow test only; an in-memory test of `forget` would say it in milliseconds.
Not a finding.

#### 4.4 The runtime's own refusal of a repeated high-risk step has no test (weakens)

case/runtime.py:2044 `if contract.risk == "high": raise StepStopped(... is high risk, and {name} is
repeated)` made `if False`. D73: "no approval on a repeated step, so a high-risk contract can't be
repeated, and `ventoux check` says so"; D34's title: "the runtime on its own". The check-time
refusal is tested; the runtime's, which is what stands when a definition reaches a worker
unchecked, is not. Compare `case27_high_risk_no_approval`, the same rule on a single step, killed.
Proof: `case26_repeated_high_risk` passed QUICK, REST and TEMP (284 passed). Fix: run a repeated step calling a high-risk contract through
`run_case` without validating: each item's run needs attention with that line.

#### 4.5 Stated refusals with no negative test (weakens)

Part 4 took the refusals the source raises (378 with a constant message; a scan,
`p4_refusals_scan.py`, lists those whose text appears in no test and no tested guide), sampled the
ones a decision states, and removed each. These survived every non-Temporal test:

| mutation | the refusal removed | decision |
|---|---|---|
| caseR01 | a migration request whose migration names another release than its target ("a migration to X carries that release") | D53 "by names, refused never terminated"; code: "Fail closed: a migration is its release and its mapping, never anything else" |
| caseR02 | showing a reference field that isn't set ("is not set: there is no record to show") | D16 |
| caseR03 | notes for a release with no record before it ("no record before it to compare with") | D57 "From the stored packages" |
| caseR04 | notes when a contract the earlier record names is no longer in the catalog | D57 "the notes would compare a promise that release never ran" |
| caseR09 | the behaviour digest meeting a kind of value it doesn't know ("never left out of the digest") | D50, fail closed |
| caseR10 | a record of another package in this package's folder ("is a record of") | D50 "The record is immutable"; `stored` |
| caseR11 | the diff asked to show a kind of value it doesn't know ("never left unsaid") | D55, fail closed |
| caseR15 | a story's answer naming both its step and its entry, or neither | D45 |
| coreR01 | a promise holding a key that isn't a text | D83 |

Killed, so tested: caseR05, R12, R13, R14, coreR02–R10 (see the table).
Fix: one negative test each; they are one-liners against public functions.

#### 4.6 Four readers (the type checker, the plain reading, the diff, the digest) have no negative test for an input they don't know (weakens; CLAUDE.md)

CLAUDE.md: "Every evaluator has a negative test for an input it doesn't know." Checked by
replacing each evaluator's final fail-closed `raise` with a permissive return:

| evaluator | mutation | result |
|---|---|---|
| expression evaluator | coreU01 | killed |
| type checker (core/expressions/check.py:238) | coreU02 | SURVIVED QUICK; wider rows in the table |
| renderer | coreU03 | killed |
| what an expression reads (provenance) | coreU04 | killed |
| a plan's state kinds (interpreter) | coreU05 | killed |
| policy kinds | core15 | killed |
| change-request kinds | case55 | killed |
| migration mapping sections | case64 | killed |
| a rule's moments | caseU01 | killed |
| plain reading: a field's type | caseR06 | SURVIVED |
| plain reading: a plan state's kind | caseR07 | SURVIVED |
| plain reading: a reading's kind (`parts_of`) | caseR08 | SURVIVED |
| the diff's value renderer | caseR11 | SURVIVED |
| the digest's canonical form | caseR09 | SURVIVED |

So the type checker (core/expressions/check.py:238, passed QUICK and REST), the plain reading (case/reading.py:760 and :836, case/plain.py:104), the diff's `shown` and the
digest's `canonical` each fail closed in code and have no test that an unknown input is refused.
Not sampled: the codec's part names, audit record kinds, step kinds of a case (see Unchecked).

#### 4.7 Small bounds and edge refusals nobody tests (minor)

- `core22`: a form's number may be an infinite `Decimal` (core/form.py `fits`: "a number is a finite
  `Decimal`"). Reading it later is refused (`core31`, killed) and Temporal's converter refuses it,
  so only the in-memory answer path is open.
- `core23`, `core24`: an option or an attachment may be the empty text (form.py: `value != ""`,
  `0 < len(value)`). D68 states the upper bound (200), which is tested (`core20` killed).
- `core06`: the approval digest marking a number apart from a text ("so `250` and `"250"` never
  share a digest", approval.py). I found no way to make one input change type, so this may be
  unreachable; it is untested either way.
- `tool11`: the Vault transport's refusal when `VAULT_TOKEN` is unset after the provider was built
  (tooling/vault.py:370 "unset since: said so, never asked without one").
- `tool21`: doctor's probe bound of 10 seconds (D81 "none can hang doctor"): tests pass their own bound.
- `auth12`: `unfenced` accepting text that only ENDS with a fence (prose on the first line); D63
  "Text around a block stays, and is refused as not JSON".

#### 4.8 Temporal: three rules that survived their own test files (minor)

- `temp26_forget_identifier`: the forget request's own check of how the answering person is
  written (D22 "written one way, before anything is checked against it"). The case's `forget`
  checks both names again (case/forgetting.py), so this is the first of two checks.
- `temp16_hold_strict`: the hold at exactly the bound (`>=` made `>`); D77: "Past 256 KB of
  unwritten records ... the case holds". The bound's value is tested (`temp15` killed), its edge is not.
- `temp31_carried_bool_number`: a carried time that is `True` is refused by name
  (temporal/carried.py:497); only run against three files.

### What held

- Core, the 54+ killed rows: every approval rule sampled except F1 (risk, someone else on inputs
  and on conditions, digest lapse, one approval one run, exclusions D25, identifier spelling D22),
  every input check before an activity (key, reference system D30, policies D21, steering
  D38/D39, unknown input, strict types D36), policy comparison (D55), every expression rule
  sampled (no coercion, nothing truthy, decimal128, division by zero), the 1,000-entry bound,
  D49 at validation and at runtime, the 100-item and 200-character bounds, D83's writer refusals,
  D17's idempotency key, the catalog's label and system registration.
- Case: D11/D25/D26/D39/D47 exclusions and distinct approvers, D69/D70 holder-only and nobody
  chooses their own judge, D41 sender, D73 distinct keys, D33 max_age (bound and unknown age),
  D44 due time, order and the tie rule, D40 a failed run never stopped, D17/D38/D72 what holds
  `closes_when`, D32 never / two people / opener, D52 every exclusion and both re-checks, D31
  unwrapped sensitive, D72 required never skipped, D51/D53 engine versions, type, sensitive,
  visible_to, D50 digest (wording left out, defaults left out, record re-checked), D51 rewording
  an older release, D54 every poller / environment / hash / binding, D74 one level and
  sensitive to sensitive.
- Tooling: all Vault checks sampled except `tool11` (exportable, type, http, no proxy, no
  redirect, mark outlives key, mark first), FileKeys, doctor's verdicts, D59 no default catalog,
  D64's four links, D63 nothing written when abandoned, D50 immutable record, D57 notes required.
- Authoring: D63 rounds (both ends, count of asks), D62 (no model, no key, base URL pinned,
  refusal, cut short, empty, error kind only, recordings compared), D61, D64 re-check.
- Temporal: 29 of 32 killed: the codec and failure converter (D31), the log filter, the converter's refusals, the export's refusal in clear, 10 attempts, a refusal never retried and the 256 KB bound (D77), the digest re-check at opening and for a wording (D51), every forget lookup refusal (D32), and `temp20` (D75 "any ID with a `/` is refused for forgetting alone"), which passed test_forget.py and test_temporal_forget.py and is killed only by tests/test_temporal_children.py::test_a_child_is_never_forgotten_alone.
- Equivalent/backstop, each shown: `core35` (a moment as a literal) and `coreR11` (`item` outside
  `count`/`sum`): `parse_expression` refuses both first (run: `parse_expression({"item": "sku"})`
  → `ExpressionInvalid item reads a field of the current element...`; `parse_expression(datetime(2027,1,1))`
  → `ExpressionInvalid not an expression`). `case69` (`is_release` on an unknown digest method):
  the final `behaviour_digest(...) == given` compares the method too, so the early return is redundant.
- Tests that can't fail (part 3), all checked on the worktree:
  - No `assert True`/constant assertion (AST scan, `p4_scan_tests.py`: 0).
  - 35 tests have no assertion of their own: most replay a recorded history (the replayer raises),
    the others assert that a definition is accepted by not raising. None is vacuous.
  - 28 tests assert only inside a loop or an `if`. Run with a line tracer
    (`p4_assertcount.py`): 27 execute their assertions at least twice;
    `test_builder_coverage.py::test_every_call_takes_every_key_of_its_kind` executes none, by
    design: `keys_taken` yields only the missing keys, so the assert runs only to fail.
  - `pytest.raises(Exception)`: 5 uses; 3 have `match=`, 2 (test_case_data.py:344,
    test_catalog.py:428) check the guide's text against `str(refused.value)` on the next line.
    The 18 `raises(ValueError/TypeError)` with no `match=` all compare the whole message next.
  - Skipped: 3, all in tests/test_vault_keys.py (`skipif VAULT is None`: no Vault binary here).
    xfail: `SILENT_ON_MAIN` in test_retry_rejected.py is empty, so none is expected to fail.
  - Computed parameter lists: none empty now (counts taken with `--collect-only`): the guides'
    refusal rows 15/6/27/8/4, the guides' tables 6/12/7/21, witnesses 5+20 (tied to `COMPARISONS`
    by test_diff.py:887). pytest reports an empty list as a skip, and the suite shows only the 3 above.
  - Monkeypatches replace a collaborator to inject a fault (notes.diff, hash_check.promise_changes,
    OPENING), never the function under test; conftest wraps `decide` to add an invariant.
  - Goldens: tests/digests/method-1.json is a committed pin, never rewritten by a test (and
    `case72`, `case73` are killed by it); the conformance suite's `expected` is committed data;
    `--unchanged` tests edit a copy in tmp_path.

### Unproven

- That `core06` (number/text in the approval digest) is unreachable: I found no path, and did not prove there is none.
- A computed parameter list going empty would show as a skip, not a failure: nothing fails the
  suite on a skip. Not proven by a run (it needs a change to docs/).

### Unchecked

- Only F1, F2 and F4 were run against the Temporal-backed tests (TEMP rows). The survivors of F5 to
  F8 passed every non-Temporal test (or, for F8, their own files) and a Temporal test could still
  kill one, as it did `case44` and `temp20`. tests/test_dev_server.py, test_doctor_live.py and
  test_skipping_server.py were never run.
- Part 4's sample is the mutations above, not the 60+ refusals asked for one by one; the scan
  (`p4_refusals_scan.py`) lists 96 raise sites whose message text appears in no test or guide, of
  which 26 were confirmed by mutation (17 killed through another message or path, 9 survived).
- Not sampled: step kinds of a case, audit record kinds, the codec's unknown part names, the
  non-determinism boundary test (tests/test_layers.py), the builder, `ventoux check` beyond
  `--unchanged`, the JSON Schema.
- The three Vault tests that need a Vault binary are skipped here.

### Every mutation run

| mutation | where | old → new (first line) | tests | result | rule |
|---|---|---|---|---|---|
| auth01_rounds_upper | authoring/loop.py:24 | `ROUNDS = range(1, 6)` → `ROUNDS = range(1, 7)` | authoring drafting approve draft_sheet | killed (2 failed, 56 passed in 2.92s) | D63 1 to 5 rounds |
| auth02_rounds_lower | authoring/loop.py:24 | `ROUNDS = range(1, 6)` → `ROUNDS = range(0, 6)` | authoring drafting approve draft_sheet | killed (1 failed, 57 passed in 2.97s) | D63 at least 1 round |
| auth03_rounds_unchecked | authoring/loop.py:62 | `if rounds not in ROUNDS:` → `if False:` | authoring drafting approve draft_sheet | killed (3 failed, 55 passed in 2.94s) | D63 rounds bound |
| auth04_extra_round | authoring/loop.py:68 | `for _ in range(rounds):` → `for _ in range(rounds + 1):` | authoring drafting approve draft_sheet | killed (3 failed, 55 passed in 2.88s) | D63 at most `rounds` asks |
| auth05_failed_provider_retried | authoring/loop.py:73 | `return Authored("no answer", None, tuple(done), why)` → `continue` | authoring drafting approve draft_sheet | killed (2 failed, 56 passed in 2.96s) | D62 a provider failure is never asked again |
| auth06_abandoned_keeps_plan | authoring/loop.py:81 | `return Authored(` → `return Authored(` | authoring drafting approve draft_sheet | killed (1 failed, 57 passed in 3.29s) | D63 nothing kept when abandoned |
| auth07_wrong_plan | authoring/loop.py:115 | `if drafted != plan:` → `if False:` | authoring drafting approve draft_sheet | killed (1 failed, 57 passed in 3.45s) | D63 draft of the plan its step names |
| auth08_warnings_as_errors | authoring/loop.py:123 | `errors = [said(issue) for issue in issues if is_error(issue)]` → `errors = []` | authoring drafting approve draft_sheet | killed (11 failed, 47 passed in 2.98s) | D63 checked as a release checks it |
| auth09_step_naming | authoring/loop.py:93 | `if isinstance(step, PlanStep) and step.plan == plan:` → `if isinstance(step, PlanStep):` | authoring drafting approve draft_sheet | killed (1 failed, 57 passed in 3.08s) | D63 only a plan a step names |
| auth10_key_twice | authoring/answers.py:54 | `if repeated:` → `if False:` | authoring drafting approve draft_sheet advisor | killed (2 failed, 86 passed in 3.20s) | D63 a key given twice |
| auth11_not_object | authoring/answers.py:33 | `if not isinstance(read, dict):` → `if False:` | authoring drafting approve draft_sheet advisor | killed (1 failed, 87 passed in 3.05s) | D63 one object |
| auth12_unfenced_prose | authoring/answers.py:43 | `if not (text.startswith("```") and text.endswith("```") and "\n" in te` → `if not (text.startswith("```") or text.endswith("```")):` | authoring drafting approve draft_sheet advisor | SURVIVED (88 passed in 3.21s) | D63 one fenced block only |
| auth12_unfenced_prose@FAST | authoring/answers.py:43 | `if not (text.startswith("```") and text.endswith("```") and "\n" in te` → `if not (text.startswith("```") or text.endswith("```")):` | FAST | SURVIVED (4385 passed, 3 skipped in 73.61s (0:01:13)) | D63 one fenced block only |
| auth13_no_model | authoring/anthropic.py:28 | `if not model:` → `if False:` | anthropic_provider authoring advisor | killed (1 failed, 60 passed in 2.76s) | D62 no model named |
| auth14_no_key | authoring/anthropic.py:34 | `if not key:` → `if False:` | anthropic_provider authoring advisor | killed (1 failed, 60 passed in 2.21s) | D62 key only from env |
| auth15_base_url | authoring/anthropic.py:75 | `return AsyncAnthropic(api_key=key, base_url=API)` → `return AsyncAnthropic(api_key=key)` | anthropic_provider authoring advisor | killed (1 failed, 60 passed in 2.16s) | D62 base URL pinned |
| auth16_refusal_answer | authoring/anthropic.py:60 | `if response.stop_reason == "refusal":` → `if False:` | anthropic_provider authoring advisor | killed (1 failed, 60 passed in 2.39s) | D62 refusal is no answer |
| auth17_cut_short | authoring/anthropic.py:62 | `if response.stop_reason not in WHOLE:` → `if False:` | anthropic_provider authoring advisor | killed (2 failed, 59 passed in 2.50s) | D62 cut short is no answer |
| auth18_empty_text | authoring/anthropic.py:65 | `if not text:` → `if False:` | anthropic_provider authoring advisor | killed (1 failed, 60 passed in 2.28s) | D62 no text is no answer |
| auth19_api_error_quoted | authoring/anthropic.py:58 | `raise ProviderFailed(f"the model's API failed: {type(error).__name__}"` → `raise ProviderFailed(f"the model's API failed: {error}") from None` | anthropic_provider authoring advisor | killed (1 failed, 60 passed in 2.09s) | D62 kind only, never the message |
| auth20_replay_differs | authoring/provider.py:92 | `if recorded.request is not None and (where := difference(recorded.requ` → `if False and (where := difference(recorded.request, request)):` | advisor temporal_advisor authoring drafting approve draft_sheet | killed (3 failed, 94 passed in 5.07s) | D62 recordings compare the request |
| auth21_replay_system | authoring/provider.py:100 | `if asked.system != recorded.system:` → `if False:` | advisor temporal_advisor authoring drafting approve draft_sheet | killed (1 failed, 96 passed in 5.84s) | D62 recordings compare the system text |
| auth22_advisor_admission | authoring/advisor.py:114 | `if (why := await refused(step)) is not None:` → `if False:` | advisor temporal_advisor | killed (3 failed, 36 passed in 2.60s) | D61 admission decides |
| auth23_advisor_second_key | authoring/advisor.py:139 | `if list(read) != ["step"]:` → `if False:` | advisor temporal_advisor | killed (2 failed, 37 passed in 2.36s) | D61 one step name |
| auth24_advisor_name_strict | authoring/advisor.py:145 | `return NAME.validate_python(step, strict=True)` → `return str(step)` | advisor temporal_advisor | killed (3 failed, 36 passed in 2.58s) | D61 a name written as the case writes names |
| auth25_approve_errors | authoring/approve.py:51 | `if errors:` → `if False:` | approve draft_sheet | killed (2 failed, 22 passed in 2.02s) | D64 checked again, never on the record's word |
| case01_untrusted_removes_approval | case/approvals.py:41 | `for field, untrusted in untrusted_of(read).items():` → `for field, untrusted in {}.items():` | QUICK | killed (1 failed, 298 passed in 5.10s) | D11/D39 untrusted data can't remove an approval |
| case02_approval_not_withdrawn_on_change | case/approvals.py:101 | `reason = not_admitted(case, required[name], state) or changed(approval` → `reason = not_admitted(case, required[name], state)` | QUICK | killed (1 failed, 78 passed in 3.39s) | D11 open approval follows the case file (D25) |
| case03_given_not_lapsed | case/approvals.py:107 | `if different := changed_fields(given, step, state):` → `if different := []:` | QUICK | killed (1 failed, 1623 passed in 13.69s) | D11/D25 a given approval lapses when its values change |
| case04_case_lapsed_digest | case/approvals.py:179 | `if now != given.digest:` → `if False:` | QUICK | killed (1 failed, 81 passed in 3.49s) | D11 inputs changed since approved |
| case05_approval_outcome_open | case/answers.py:70 | `if answer.outcome not in (APPROVE, REJECT):` → `if False:` | QUICK | killed (1 failed, 1972 passed in 15.60s) | D9/D23 approval's outcomes are a closed list |
| case06_approval_risk | case/answers.py:79 | `if approver is None:` → `if False:` | QUICK | killed (1 failed, 85 passed in 3.82s) | D11 approver role may approve the risk |
| case07_unseen_approves | case/answers.py:83 | `refuse_unless(unseen(case, catalog, answer, name, step))` → `pass` | QUICK | killed (1 failed, 85 passed in 3.63s) | D30 an approver judges what they see |
| case08_same_person_twice | case/answers.py:88 | `if answer.by in approved:` → `if False:` | QUICK | killed (1 failed, 72 passed in 3.64s) | D47 count different people |
| case09_opener_approves | case/answers.py:104 | `if by == state.opened_by:` → `if False:` | QUICK | killed (1 failed, 73 passed in 3.31s) | D11/D25 the opener approves none of its steps |
| case10_parent_excluded_ignored | case/answers.py:108 | `if by in state.excluded:` → `if False:` | QUICK | killed (1 failed, 761 passed in 6.23s) | D25/D74 who the parent excluded |
| case11_proposer_approves | case/answers.py:111 | `if by == state.proposers.get(name):` → `if False:` | QUICK | killed (1 failed, 38 passed in 3.29s) | D25 the proposer approves nothing |
| case12_rule_reader_approves | case/answers.py:117 | `if asked is not None and by in asked.read_from:` → `if False:` | QUICK | killed (1 failed, 73 passed in 3.57s) | D11/D39 whose answer a rule's condition read |
| case13_retry_exclusion_dropped | case/answers.py:122 | `if latest is not None and latest.status == "retrying" and by in latest` → `if False:` | QUICK | killed (1 failed, 2188 passed in 19.46s) | D26 a retried run keeps its exclusions |
| case14_claim_held_by_other | case/claims.py:40 | `if holder is not None:` → `if False:` | QUICK | killed (1 failed, 803 passed in 7.64s) | D69 the holder is asked, never overruled |
| case15_multi_approval_held | case/claims.py:65 | `if isinstance(found, OpenApproval) and found.count > 1:` → `if False:` | QUICK | killed (1 failed, 111 passed in 4.18s) | D69/D47 an approval needing several people is held by nobody |
| case16_give_back_by_other | case/claims.py:131 | `if holder.by != event.by:` → `if False:` | QUICK | killed (1 failed, 805 passed in 7.58s) | D69 only the holder gives back |
| case17_answer_held_by_other | case/claims.py:140 | `if holder is None or holder.by == by:` → `if True:` | QUICK | killed (1 failed, 92 passed in 3.89s) | D69 only the holder answers |
| case18_assigner_role | case/assigning.py:48 | `if role is None:` → `if False:` | QUICK | killed (1 failed, 91 passed in 3.98s) | D70 only a registered assigner |
| case19_own_judge | case/assigning.py:88 | `if (why := why_excluded(case, state, found.step, step, by)) is not Non` → `if False:` | QUICK | killed (1 failed, 100 passed in 3.89s) | D70 nobody chooses their own judge |
| case20_assignee_not_judged | case/assigning.py:34 | `role_to_hold(case, catalog, state, found, asked)` → `pass` | QUICK | killed (1 failed, 94 passed in 3.80s) | D69/D70 being assigned grants nothing |
| case21_sender_system | case/runtime.py:436 | `if event.by != f"system:{sent_by.system}":` → `if False:` | QUICK | killed (1 failed, 1330 passed in 13.97s) | D41 one sender, its system |
| case22_people_event_from_system | case/runtime.py:443 | `if event.by.startswith("system:"):` → `if False:` | QUICK | killed (1 failed, 1333 passed in 13.83s) | D41 an event sent by roles never from a system |
| case23_sender_role | case/runtime.py:452 | `raise EventRefused(f"{name} is sent by {roles}, and {event.by} has {kn` → `pass` | QUICK | killed (1 failed, 1214 passed in 10.78s) | D41/D22 sender's role |
| case24_event_after_close | case/runtime.py:375 | `if state.phase == "closed":` → `if False:` | QUICK | killed (1 failed, 1348 passed in 13.44s) | D41 a closed case takes no events |
| case25_duplicate_item_keys | case/runtime.py:1992 | `if len(set(keys)) < len(keys):` → `if False:` | QUICK | killed (1 failed, 2071 passed in 16.72s) | D73 key distinct |
| case26_repeated_high_risk | case/runtime.py:2044 | `if contract.risk == "high":` → `if False:` | QUICK | SURVIVED (2622 passed in 21.74s) | D73 a repeated high-risk step is refused |
| case26_repeated_high_risk@REST | case/runtime.py:2044 | `if contract.risk == "high":` → `if False:` | REST | SURVIVED (1763 passed, 3 skipped in 53.22s) | D73 a repeated high-risk step is refused |
| case26_repeated_high_risk@TEMP | case/runtime.py:2044 | `if contract.risk == "high":` → `if False:` | TEMP | SURVIVED (284 passed in 258.76s (0:04:18)) | D73 a repeated high-risk step is refused |
| case27_high_risk_no_approval | case/runtime.py:2076 | `if contract.risk == "high" and step.approval is None:` → `if False:` | QUICK | killed (1 failed, 320 passed in 4.98s) | D11 high risk needs approval, at runtime |
| case28_retry_not_failed | case/runtime.py:1403 | `if run is None or run.status != "failed":` → `if run is None:` | QUICK | killed (1 failed, 340 passed in 5.38s) | D26 only a failed run is retried |
| case29_stale_unknown_age | case/runtime.py:1606 | `if stale.age is None:  # fail closed: an age that can't be told is nev` → `if False:  # fail closed: an age that can't be told is never fresh` | QUICK | killed (1 failed, 1619 passed in 14.05s) | D18/D33 unknown age never fresh |
| case30_max_age_ge | case/freshness.py:68 | `elif at - obtained.at > seconds_in(limit):` → `elif at - obtained.at >= seconds_in(limit):` | QUICK | killed (1 failed, 2503 passed in 22.03s) | D33 max_age boundary |
| case31_max_age_no_time | case/freshness.py:66 | `if obtained is None:` → `if False:` | QUICK | killed (1 failed, 1619 passed in 14.32s) | D33 fail closed: its age is unknown |
| case32_bool_time | case/freshness.py:25 | `if isinstance(at, bool) or not isinstance(at, int):` → `if not isinstance(at, int):` | QUICK | killed (1 failed, 1597 passed in 14.24s) | fail closed: a bool is no time |
| case33_timer_wrong_time | case/timers.py:41 | `if event.at != timer.due:` → `if False:` | QUICK | killed (1 failed, 2467 passed in 21.08s) | D44 a timer fires at its due time |
| case34_timer_due_strict | case/timers.py:81 | `due = [timer for timer in state.timers if timer.due <= at]` → `due = [timer for timer in state.timers if timer.due < at]` | QUICK | killed (1 failed, 1799 passed in 15.19s) | D44 every timer due by then fires |
| case35_timer_tie | case/timers.py:85 | `first = min(due, key=lambda timer: timer.due)` → `first = min(reversed(due), key=lambda timer: timer.due)` | QUICK | killed (1 failed, 2473 passed in 21.78s) | D44 tie: earlier set wins |
| case36_timers_failed_ends | case/timers.py:58 | `if status in ("done", "rejected", "cancelled", "skipped"):` → `if status in ("done", "rejected", "cancelled", "skipped", "failed"):` | QUICK | killed (1 failed, 719 passed in 6.56s) | D44 a failed run hasn't ended for its timers |
| case37_failed_run_stopped | case/stopping.py:46 | `if latest is not None and latest.status in ("failed", "retrying"):` → `if False:` | QUICK | killed (1 failed, 1644 passed in 14.64s) | D40 a failed run is never stopped |
| case38_close_over_failed | case/closing.py:207 | `if any(run.status in ("failed", "retrying") for run in state.runs):` → `if False:` | QUICK | killed (1 failed, 371 passed in 5.65s) | D17/D26 closes_when waits for a failed run |
| case39_close_over_failed_rule | case/closing.py:209 | `if any(firing.status == "failed" for firing in state.firings):` → `if False:` | QUICK | killed (1 failed, 2183 passed in 19.49s) | D38 nor a rule that couldn't be read |
| case40_close_over_owed | case/closing.py:211 | `if owed(case, state):` → `if False:` | QUICK | killed (1 failed, 2106 passed in 18.16s) | D72 required owed blocks closes_when |
| case41_closes_when_any | case/closing.py:213 | `if all(milestone in state.milestones for milestone in case.closes_when` → `if any(milestone in state.milestones for milestone in case.closes_when` | QUICK | SURVIVED (2622 passed in 21.83s) | D10 every milestone in closes_when |
| case41_closes_when_any@REST | case/closing.py:213 | `if all(milestone in state.milestones for milestone in case.closes_when` → `if any(milestone in state.milestones for milestone in case.closes_when` | REST | SURVIVED (1763 passed, 3 skipped in 52.23s) | D10 every milestone in closes_when |
| case41_closes_when_any@TEMP | case/closing.py:213 | `if all(milestone in state.milestones for milestone in case.closes_when` → `if any(milestone in state.milestones for milestone in case.closes_when` | TEMP | SURVIVED (284 passed in 250.02s (0:04:10)) | D10 every milestone in closes_when |
| case42_close_role | case/closing.py:49 | `if role is None:` → `if False:` | QUICK | killed (1 failed, 342 passed in 5.49s) | D10 close reason's roles |
| case43_forget_never | case/forgetting.py:62 | `if family_forgetting(case, children) == "never":` → `if False:` | QUICK | killed (1 failed, 1595 passed in 14.57s) | D32 forgetting: never |
| case44_forget_family_ignores_children | case/forgetting.py:100 | `said = [case.forgetting, *(child.forgetting for child in children)]` → `said = [case.forgetting]` | QUICK | SURVIVED (2622 passed in 21.21s) | D75 strictest of the family |
| case44_forget_family_ignores_children@REST | case/forgetting.py:100 | `said = [case.forgetting, *(child.forgetting for child in children)]` → `said = [case.forgetting]` | REST | SURVIVED (1763 passed, 3 skipped in 54.92s) | D75 strictest of the family |
| case44_forget_family_ignores_children@TEMP | case/forgetting.py:100 | `said = [case.forgetting, *(child.forgetting for child in children)]` → `said = [case.forgetting]` | TEMP | killed (1 failed, 141 passed in 116.30s (0:01:56)) | D75 strictest of the family |
| case45_forget_self_approve | case/forgetting.py:45 | `if approved_by == proposed_by:` → `if False:` | QUICK | killed (1 failed, 1591 passed in 13.97s) | D32 two people |
| case46_forget_opener_approves | case/forgetting.py:77 | `if state.engine >= 2 and event.approved_by == state.opened_by:` → `if False:` | QUICK | killed (1 failed, 721 passed in 6.27s) | D32 opener can't approve forgetting (engine 2) |
| case47_forget_proposer_role | case/forgetting.py:67 | `if proposed is not None:` → `if False:` | QUICK | killed (1 failed, 1592 passed in 15.07s) | D32 forgetters role for proposing |
| case48_change_self_approve | case/requests.py:264 | `if by == request.by:` → `if False:` | QUICK | killed (1 failed, 700 passed in 7.03s) | D52 nobody approves their own |
| case49_change_opener_approves | case/requests.py:266 | `if by == state.opened_by:` → `if False:` | QUICK | killed (1 failed, 701 passed in 6.61s) | D25/D52 |
| case50_edit_setter_approves | case/requests.py:275 | `if f"person:{by}" in state.sources.get(request.target, ()):` → `if False:` | QUICK | killed (1 failed, 712 passed in 6.63s) | D11/D52 who set it doesn't judge |
| case51_edit_hidden_approves | case/requests.py:272 | `if (hidden := unseen(case, catalog, request.target, by, event.roles)) ` → `if False:` | QUICK | killed (1 failed, 711 passed in 6.59s) | D30/D52 approver sees the value |
| case52_skip_approver_approves | case/requests.py:289 | `if run.approved is not None and by in run.approved.approvers:` → `if False:` | QUICK | killed (1 failed, 714 passed in 6.67s) | D52 who approved the run can't approve its skip |
| case53_edit_recheck_changed | case/requests.py:309 | `if problem is None and inputs_digest({name: Var(var=name)}, state.valu` → `if False:` | QUICK | killed (1 failed, 196 passed in 4.45s) | D52 checked again: changed since proposed |
| case54_migrate_recheck_moved | case/requests.py:362 | `if released(case, state) != request.against:` → `if False:` | QUICK | killed (1 failed, 1715 passed in 14.85s) | D53 case moved since proposed |
| case55_change_kind_unknown | case/requests.py:88 | `if event.kind not in KINDS:` → `if False:` | QUICK | killed (1 failed, 703 passed in 6.68s) | D52 change-request kinds closed |
| case56_edit_sensitive_unwrapped | case/requests.py:176 | `if declared.sensitive and not isinstance(value, Sensitive):` → `if False:` | QUICK | killed (1 failed, 710 passed in 6.37s) | D31 unwrapped sensitive refused |
| case57_edit_same_value | case/requests.py:186 | `if plain(value) == plain(state.values[name]):` → `if False:` | QUICK | killed (1 failed, 706 passed in 6.61s) | D52 an edit that changes nothing |
| case58_skip_required | case/requests.py:206 | `if case.steps[run.step].required:` → `if False:` | QUICK | killed (1 failed, 2099 passed in 17.78s) | D72 a required step is never skipped |
| case59_mig_unknown_engine | case/migrations.py:128 | `if migration.engine not in KNOWN:` → `if False:` | QUICK | killed (1 failed, 1700 passed in 14.83s) | D51 unknown engine version |
| case60_mig_engine_back | case/migrations.py:133 | `elif migration.engine < state.engine:` → `elif False:` | QUICK | killed (1 failed, 1700 passed in 14.51s) | D53 the engine never goes back |
| case61_mig_type_change | case/migrations.py:409 | `if before.declared != after.declared:` → `if False:` | QUICK | killed (1 failed, 1705 passed in 15.13s) | D53 never changes type |
| case62_mig_loses_sensitive | case/migrations.py:416 | `if before.sensitive and not after.sensitive:` → `if False:` | QUICK | killed (1 failed, 1705 passed in 14.74s) | D53 never loses sensitive |
| case63_mig_widens_visible | case/migrations.py:420 | `if widened(case, target, name, new):` → `if False:` | QUICK | killed (1 failed, 1705 passed in 14.55s) | D53 never widens visible_to |
| case64_mig_unknown_section | case/migrations.py:199 | `if section not in SECTIONS:` → `if False:` | QUICK | killed (1 failed, 1703 passed in 15.26s) | D53 mapping sections closed list |
| case65_mig_two_to_one | case/migrations.py:209 | `if new in mapped_to:` → `if False:` | QUICK | killed (1 failed, 1703 passed in 14.62s) | D53 by names, one to one |
| case66_mig_approval_kept | case/migrations.py:523 | `if not same_behaviour(case, target, name):` → `if False:` | QUICK | killed (1 failed, 204 passed in 4.68s) | D53 approvals of what changed withdrawn |
| case67_view_unregistered_role | case/visibility.py:61 | `counting = {role for role in roles if role in registered}` → `counting = set(roles)` | QUICK | killed (1 failed, 474 passed in 5.51s) | D22/D35 an unknown role sees nothing |
| case68_child_has_cases | case/releases.py:223 | `if child.cases:` → `if False:` | QUICK | killed (1 failed, 772 passed in 7.04s) | D74 one level |
| case69_digest_method | case/releases.py:351 | `if given.method != METHOD:` → `if False:` | QUICK | SURVIVED (2622 passed in 22.10s) | D51 a method this code knows |
| case70_record_digest_recheck | case/releases.py:518 | `if digest(kept) != record.digest:` → `if False:` | QUICK | killed (1 failed, 2027 passed in 16.14s) | D50 record checked against its own package |
| case71_reword_older_release | case/releases.py:489 | `if number != newest:` → `if False:` | QUICK | killed (1 failed, 2033 passed in 16.40s) | D51 only the latest release takes new wording |
| case72_digest_default_kept | case/releases.py:299 | `if at_default and not names_its_shape:` → `if False:` | QUICK | killed (1 failed, 1227 passed in 11.48s) | D50 defaults left out |
| case73_digest_wording_kept | case/releases.py:292 | `if isinstance(value, WORDING):` → `if False:` | QUICK | killed (1 failed, 774 passed in 7.96s) | D50 display left out |
| case74_act_no_poller | case/activation.py:79 | `if not pollers.get(queue):` → `if False:` | QUICK | killed (1 failed, 3 passed in 3.35s) | D54 a worker polls |
| case75_act_unmanifested_poller | case/activation.py:106 | `if manifest is None or (manifest.environment, manifest.task_queue) != ` → `if manifest is None:` | QUICK | killed (1 failed, 2 passed in 3.23s) | D54 every poller, in this environment |
| case76_act_hash | case/activation.py:168 | `if served != needed:` → `if False:` | QUICK | killed (1 failed, 1 passed in 3.23s) | D54 same hash |
| case77_act_bind_differently | case/activation.py:132 | `if len(set(bindings.values())) > 1:` → `if False:` | QUICK | killed (1 failed, 4 passed in 3.24s) | D54/D29 one binding |
| case78_required_with_when | case/definition.py:994 | `if step.required and step.when is not None:` → `if False:` | QUICK | killed (1 failed, 2093 passed in 17.29s) | D72 a required step has no when |
| case79_report_sensitive | case/definition.py:970 | `elif field.sensitive:` → `elif False:` | QUICK | killed (1 failed, 744 passed in 6.79s) | D74 a report carries no sensitive field |
| case80_sensitive_to_child | case/calls.py:161 | `if read in case.fields and case.fields[read].sensitive:` → `if False:` | QUICK | killed (1 failed, 750 passed in 7.44s) | D74 sensitive to sensitive |
| core01_risk_not_checked_for_approver | core/approval.py:47 | `and may_approve(catalog.roles[role], contract.risk)` → `and True` | QUICK | killed (1 failed, 85 passed in 3.71s) | D11 a role approves up to its risk |
| core02_approver_role_not_listed | core/approval.py:45 | `if role in roles` → `if True` | QUICK | SURVIVED (2622 passed in 20.20s) | D11/D23 the approval lists its roles |
| core02_approver_role_not_listed@FAST | core/approval.py:45 | `if role in roles` → `if True` | FAST | SURVIVED (4385 passed, 3 skipped in 75.57s (0:01:15)) | D11/D23 the approval lists its roles |
| core02_approver_role_not_listed@TEMP | core/approval.py:45 | `if role in roles` → `if True` | TEMP | SURVIVED (284 passed in 258.23s (0:04:18)) | D11/D23 the approval lists its roles |
| core03_own_answer_approves | core/approval.py:79 | `if f"person:{person}" in sources.get(field, frozenset()):` → `if False:` | QUICK | killed (1 failed, 73 passed in 3.70s) | D11 someone else |
| core04_conditions_not_someone_else | core/approval.py:96 | `((inputs, f"{step} uses"), (conditions, f"decides whether {step} runs"` → `((inputs, f"{step} uses"),)` | QUICK | killed (1 failed, 788 passed in 7.23s) | D11 someone else, on what decides the run |
| core05_digest_of_sensitive_plain | core/approval.py:122 | `return Sensitive(digest) if read else digest` → `return digest` | QUICK | killed (1 failed, 2280 passed in 19.26s) | D31 a digest of a sensitive value is sensitive |
| core06_digest_number_as_text | core/approval.py:119 | `default=lambda number: {"number": str(number)}` → `default=str` | QUICK | SURVIVED (2622 passed in 20.23s) | D11 250 and "250" never share a digest |
| core06_digest_number_as_text@FAST | core/approval.py:119 | `default=lambda number: {"number": str(number)}` → `default=str` | FAST | SURVIVED (4385 passed, 3 skipped in 75.20s (0:01:15)) | D11 250 and "250" never share a digest |
| core07_key_given_by_definition | core/before_activity.py:64 | `if contract.idempotency_key is not None and contract.idempotency_key i` → `if False:` | QUICK | killed (1 failed, 468 passed in 5.41s) | D17/D35 the engine fills the key |
| core08_reference_wrong_system | core/before_activity.py:71 | `if field in inputs and (wrong := not_a_reference_to(system, inputs[fie` → `if False and (wrong := not_a_reference_to(system, inputs[field], types` | QUICK | killed (1 failed, 387 passed in 5.63s) | D30 a reference of its system |
| core09_input_policy_not_checked | core/before_activity.py:85 | `if policy.refuses(found) is not None:` → `if False:` | QUICK | killed (1 failed, 298 passed in 5.02s) | D21 every policy on every input |
| core10_steering_not_checked | core/before_activity.py:93 | `if policy.refuses(steering.sources) is not None:` → `if False:` | QUICK | killed (1 failed, 561 passed in 5.82s) | D38/D39 untrusted data can't choose what is sent |
| core11_unknown_input_passed | core/before_activity.py:108 | `if unknown:` → `if False:` | QUICK | killed (1 failed, 466 passed in 5.46s) | fail closed: an activity never gets an undeclared field |
| core12_inputs_not_strict | core/before_activity.py:118 | `model_validate(unwrapped(given), strict=True)` → `model_validate(unwrapped(given), strict=False)` | QUICK | killed (1 failed, 509 passed in 6.32s) | D36 the text "40" is refused |
| core13_only_from_no_source | core/policy.py:75 | `if not sources:` → `if False:` | QUICK | killed (1 failed, 1925 passed in 15.28s) | D21 only_from: no source is no system |
| core14_only_from_union | core/policy.py:124 | `systems = named if systems is None else systems & named` → `systems = named if systems is None else systems \| named` | QUICK | killed (1 failed, 1111 passed in 10.08s) | D21 every policy applies |
| core15_unknown_policy_kind | core/policy.py:117 | `if type(policy) not in KINDS:` → `if False:` | QUICK | killed (1 failed, 1114 passed in 9.70s) | D21 closed list of kinds, fail closed |
| core16_within_any | core/policy.py:139 | `return False  # an untrusted source is accepted by `inner` only` → `return True  # an untrusted source is accepted by `inner` only` | QUICK | killed (1 failed, 1100 passed in 9.88s) | D55 policies compared |
| core17_within_systems | core/policy.py:144 | `return systems <= outer_systems` → `return systems >= outer_systems` | QUICK | killed (1 failed, 1108 passed in 9.90s) | D55 policies compared |
| core18_risk_strictly_below | core/roles.py:34 | `return RISKS.index(risk) <= RISKS.index(approves)` → `return RISKS.index(risk) < RISKS.index(approves)` | QUICK | killed (1 failed, 38 passed in 3.34s) | D11 approves up to |
| core19_unregistered_role_counts | core/roles.py:43 | `if role in allowed and role in registered)` → `if role in allowed)` | QUICK | killed (1 failed, 471 passed in 5.52s) | D22 a role the catalog doesn't know counts for nothing |
| core20_longest_id_201 | core/form.py:52 | `LONGEST_ID = 200` → `LONGEST_ID = 201` | QUICK | killed (1 failed, 163 passed in 4.28s) | D68 at most 200 characters |
| core21_most_items_101 | core/form.py:55 | `MOST_ITEMS = 100` → `MOST_ITEMS = 101` | QUICK | killed (1 failed, 2047 passed in 17.24s) | D73 at most 100 items |
| core22_infinite_number_fits | core/form.py:93 | `return isinstance(value, Decimal) and value.is_finite()` → `return isinstance(value, Decimal)` | QUICK | SURVIVED (2622 passed in 21.96s) | D20 a number is a finite decimal |
| core22_infinite_number_fits@FAST | core/form.py:93 | `return isinstance(value, Decimal) and value.is_finite()` → `return isinstance(value, Decimal)` | FAST | SURVIVED (4385 passed, 3 skipped in 73.73s (0:01:13)) | D20 a number is a finite decimal |
| core23_empty_option_fits | core/form.py:105 | `return isinstance(value, str) and value != ""` → `return isinstance(value, str)` | QUICK | SURVIVED (2622 passed in 20.55s) | D67 an option |
| core23_empty_option_fits@FAST | core/form.py:105 | `return isinstance(value, str) and value != ""` → `return isinstance(value, str)` | FAST | SURVIVED (4385 passed, 3 skipped in 71.14s (0:01:11)) | D67 an option |
| core24_empty_attachment_fits | core/form.py:109 | `0 < len(value) <= LONGEST_ID` → `0 <= len(value) <= LONGEST_ID` | QUICK | SURVIVED (2622 passed in 20.77s) | D68 attachment ID |
| core24_empty_attachment_fits@FAST | core/form.py:109 | `0 < len(value) <= LONGEST_ID` → `0 <= len(value) <= LONGEST_ID` | FAST | SURVIVED (4385 passed, 3 skipped in 71.13s (0:01:11)) | D68 attachment ID |
| core25_form_extra_field | core/form.py:40 | `if field not in sets:` → `if False:` | QUICK | killed (1 failed, 1813 passed in 16.15s) | D9 the answer gives exactly the fields |
| core26_item_extra_field | core/form.py:149 | `if any(name not in declared.fields for name in item):` → `if False:` | QUICK | killed (1 failed, 2044 passed in 16.50s) | D73 each item exactly the declared fields |
| core27_outcome_any_text | core/form.py:99 | `return isinstance(value, str) and value in declared.outcomes` → `return isinstance(value, str)` | QUICK | killed (1 failed, 2296 passed in 21.34s) | D9 outcome type closed list |
| core28_role_any_spelling | core/roles.py:18 | `if not is_label(name):` → `if False:` | QUICK | killed (1 failed, 699 passed in 6.59s) | D22 roles are labels |
| core29_eq_coerces | core/expressions/evaluate.py:213 | `if kind(left) != kind(right):` → `if False:` | QUICK | killed (1 failed, 1407 passed in 13.81s) | D20 no coercion in == |
| core30_in_coerces | core/expressions/evaluate.py:104 | `if kind(found) != kind(options[0]):` → `if False:` | QUICK | killed (1 failed, 1457 passed in 14.20s) | D20 no coercion in `in` |
| core31_nonfinite_read | core/expressions/evaluate.py:167 | `if isinstance(value, Decimal) and not value.is_finite():` → `if False:` | QUICK | killed (1 failed, 1438 passed in 14.29s) | D20 non-finite number refused at runtime |
| core32_decimal128_not_checked | core/expressions/evaluate.py:171 | `if isinstance(value, Decimal) and not fits_decimal128(value):` → `if False:` | QUICK | killed (1 failed, 1583 passed in 14.01s) | D20 decimal128 |
| core33_truthy | core/expressions/evaluate.py:249 | `if not isinstance(value, bool):` → `if False:` | QUICK | killed (1 failed, 1416 passed in 14.54s) | D20 nothing is truthy |
| core34_div_zero_named | core/expressions/evaluate.py:90 | `if isinstance(expression, Div) and numbers[1] == 0:` → `if False:` | QUICK | killed (1 failed, 1430 passed in 13.53s) | D20/D30 division by zero names the expression |
| core35_moment_read | core/expressions/evaluate.py:60 | `if isinstance(expression, date) and not is_day(expression):` → `if False:` | QUICK | SURVIVED (2622 passed in 20.58s) | D66 a moment is not a date |
| core35_moment_read@FAST | core/expressions/evaluate.py:60 | `if isinstance(expression, date) and not is_day(expression):` → `if False:` | FAST | SURVIVED (4385 passed, 3 skipped in 76.09s (0:01:16)) | D66 a moment is not a date |
| core36_records_not_mappings | core/expressions/evaluate.py:181 | `if not isinstance(held, list) or not all(isinstance(element, Mapping) ` → `if not isinstance(held, list):` | QUICK | killed (1 failed, 1475 passed in 14.38s) | D20 count/sum read a list of records |
| core37_ge_as_gt | core/expressions/evaluate.py:238 | `return a >= b` → `return a > b` | QUICK | killed (1 failed, 1399 passed in 13.74s) | D20 operators |
| core38_loop_bound_1001 | core/interpreter.py:98 | `ENTRIES_WITHOUT_A_WAIT = 1000` → `ENTRIES_WITHOUT_A_WAIT = 1001` | QUICK | killed (1 failed, 1681 passed in 14.19s) | D48 1,000 states without a wait |
| core39_undeclared_outcome | core/interpreter.py:287 | `if outcome.name not in contract.outcomes:` → `if False:` | QUICK | killed (1 failed, 1654 passed in 13.96s) | D17 only outcomes the contract declares |
| core40_changed_inputs_approved | core/interpreter.py:370 | `if now != approval.digest:` → `if False:` | QUICK | killed (1 failed, 1828 passed in 15.13s) | D11 inputs changed since approval |
| core41_high_risk_unapproved | core/interpreter.py:381 | `if contract.risk == "high":` → `if False:` | QUICK | killed (1 failed, 1831 passed in 14.99s) | D11 high risk needs an approval, checked at runtime |
| core42_approval_reused | core/interpreter.py:364 | `approval = approvals.pop(here, None)` → `approval = approvals.get(here)` | QUICK | killed (1 failed, 1832 passed in 14.62s) | D11 one approval unlocks one run |
| core43_identifier_not_checked | core/interpreter.py:400 | `if answer.by is not None and (wrong := identifier_problem(answer.by)) ` → `if False and (wrong := identifier_problem(answer.by)) is not None:` | QUICK | killed (1 failed, 1844 passed in 14.46s) | D22 who answered is written one way |
| core44_excluded_approves | core/interpreter.py:441 | `if by in excluded:` → `if False:` | QUICK | killed (1 failed, 1903 passed in 15.55s) | D25 the case's opener and proposer approve nothing |
| core45_untrusted_path | core/interpreter.py:497 | `if untrusted:` → `if False:` | QUICK | killed (1 failed, 1915 passed in 15.23s) | D49 untrusted data never chooses a plan's path |
| core46_person_times_out | core/interpreter.py:454 | `if answer.by is not None:` → `if False:` | QUICK | killed (1 failed, 1669 passed in 14.76s) | D9 a timeout never from a person |
| core47_unknown_outcome | core/interpreter.py:459 | `if answer.outcome not in question.outcomes:` → `if False:` | QUICK | killed (1 failed, 1668 passed in 14.37s) | D9 outcomes are a closed list |
| core48_case_source_given | core/interpreter.py:549 | `elif CASE in given.sources:` → `elif False:` | QUICK | killed (1 failed, 1648 passed in 14.50s) | layer 5: a field given with the source `case` is refused |
| core49_no_sources_given | core/interpreter.py:541 | `elif not given.sources:` → `elif False:` | QUICK | killed (1 failed, 511 passed in 5.92s) | fail closed: no sources |
| core50_condition_not_boolean | core/interpreter.py:512 | `if not isinstance(decided, bool):` → `if False:` | QUICK | killed (1 failed, 1665 passed in 14.51s) | D20 nothing is truthy (transition) |
| core51_v_untrusted_transition | core/validate.py:201 | `if name in plan.sources:` → `if False:` | QUICK | killed (1 failed, 255 passed in 5.16s) | D49 at validation |
| core52_v_approval_role_risk | core/validate.py:262 | `if role in catalog.roles and not may_approve(catalog.roles[role], cont` → `if False` | QUICK | killed (1 failed, 1824 passed in 15.48s) | D11 APPROVAL_ROLE |
| core53_v_reserved_outcome | core/validate.py:398 | `if TIMEOUT in state.wait.outcomes:` → `if False:` | QUICK | killed (1 failed, 888 passed in 9.02s) | timeout is reserved |
| core54_v_approve_goes_elsewhere | core/validate.py:434 | `if transition.target != of:` → `if False:` | QUICK | killed (1 failed, 856 passed in 8.63s) | D23 approve leads to what it approves |
| core55_v_engine_input | core/validate.py:494 | `if name == key:` → `if False:` | QUICK | killed (1 failed, 2557 passed in 21.30s) | D17 ENGINE_INPUT |
| core56_v_missing_input | core/validate.py:513 | `if field.is_required() and name not in state.inputs:` → `if False:` | QUICK | killed (1 failed, 2556 passed in 20.79s) | MISSING_INPUT |
| core57_v_condition_boolean | core/validate.py:534 | `if condition and not isinstance(found, BooleanType):` → `if False:` | QUICK | killed (1 failed, 2567 passed in 20.24s) | D20 a condition gives a boolean |
| core58_v_approval_required | core/validate.py:605 | `if name in reached and isinstance(state, ActivityState) and is_high_ri` → `if False:` | QUICK | killed (1 failed, 1821 passed in 14.96s) | D11 APPROVAL_REQUIRED |
| core59_v_approval_reused | core/validate.py:625 | `if again:` → `if False:` | QUICK | killed (1 failed, 215 passed in 4.40s) | D11 APPROVAL_REUSED |
| core60_v_sets_unknown_field | core/validate.py:280 | `if field not in plan.fields:` → `if False:` | QUICK | killed (1 failed, 896 passed in 8.68s) | UNKNOWN_FIELD |
| caseR01_migration_label_mismatch | case/requests.py:113 | `if not isinstance(migration, Migration) or migration.label != event.ta` → `if not isinstance(migration, Migration):` | QUICK | SURVIVED (2622 passed in 22.90s) | D53 a migration is its release and its mapping |
| caseR01_migration_label_mismatch@REST | case/requests.py:113 | `if not isinstance(migration, Migration) or migration.label != event.ta` → `if not isinstance(migration, Migration):` | REST | SURVIVED (1763 passed, 3 skipped in 53.72s) | D53 a migration is its release and its mapping |
| caseR02_shown_unset | case/runtime.py:493 | `if event.field not in state.values:` → `if False:` | QUICK | SURVIVED (2622 passed in 22.97s) | D16 a reference not set has no record |
| caseR02_shown_unset@REST | case/runtime.py:493 | `if event.field not in state.values:` → `if False:` | REST | SURVIVED (1763 passed, 3 skipped in 51.80s) | D16 a reference not set has no record |
| caseR03_notes_no_record_before | case/notes.py:67 | `if not found:` → `if False:` | QUICK | SURVIVED (2622 passed in 21.56s) | D57 notes compare with the record before |
| caseR03_notes_no_record_before@REST | case/notes.py:67 | `if not found:` → `if False:` | REST | SURVIVED (1763 passed, 3 skipped in 53.31s) | D57 notes compare with the record before |
| caseR04_notes_contract_missing | case/notes.py:79 | `except NotInCatalog:` → `except NotInCatalog:` | QUICK | SURVIVED (2622 passed in 21.69s) | D57 notes read the promise recorded |
| caseR04_notes_contract_missing@REST | case/notes.py:79 | `except NotInCatalog:` → `except NotInCatalog:` | REST | SURVIVED (1763 passed, 3 skipped in 52.02s) | D57 notes read the promise recorded |
| caseR05_notes_wording_diff | case/notes.py:35 | `if kept.wording > 1 and (found.changes or found.rewritten):` → `if False:` | QUICK | killed (1 failed, 1731 passed in 15.48s) | D57 a wording revision says only wording |
| caseR06_reading_unknown_type | case/reading.py:759 | `if kind not in kinds:` → `if False:` | QUICK | SURVIVED (2622 passed in 23.06s) | CLAUDE.md: plain reading has a negative test for an unknown input |
| caseR06_reading_unknown_type@REST | case/reading.py:759 | `if kind not in kinds:` → `if False:` | REST | SURVIVED (1763 passed, 3 skipped in 55.54s) | CLAUDE.md: plain reading has a negative test for an unknown input |
| caseR07_reading_unknown_state | case/reading.py:836 | `raise ReadingRefused(f"can't read {name}: {state!r} is no kind of stat` → `return f"{name}."` | QUICK | SURVIVED (2622 passed in 22.57s) | CLAUDE.md: plan reading of an unknown state kind |
| caseR07_reading_unknown_state@REST | case/reading.py:836 | `raise ReadingRefused(f"can't read {name}: {state!r} is no kind of stat` → `return f"{name}."` | REST | SURVIVED (1763 passed, 3 skipped in 55.52s) | CLAUDE.md: plan reading of an unknown state kind |
| caseR08_plain_unknown_reading | case/plain.py:104 | `raise TypeError(f"no reading of the kind {type(reading).__name__}")  #` → `return "", ()  # fail closed` | QUICK | SURVIVED (2622 passed in 21.54s) | CLAUDE.md: plain reading of an unknown kind |
| caseR08_plain_unknown_reading@REST | case/plain.py:104 | `raise TypeError(f"no reading of the kind {type(reading).__name__}")  #` → `return "", ()  # fail closed` | REST | SURVIVED (1763 passed, 3 skipped in 54.27s) | CLAUDE.md: plain reading of an unknown kind |
| caseR09_digest_unknown_value | case/releases.py:284 | `raise TypeError(f"the behaviour digest can't read a {type(value).__nam` → `return None` | QUICK | SURVIVED (2622 passed in 22.37s) | D50 fail closed: never left out of the digest |
| caseR09_digest_unknown_value@REST | case/releases.py:284 | `raise TypeError(f"the behaviour digest can't read a {type(value).__nam` → `return None` | REST | SURVIVED (1763 passed, 3 skipped in 53.91s) | D50 fail closed: never left out of the digest |
| caseR10_record_other_package | case/releases.py:507 | `if record.name != name:` → `if False:` | QUICK | SURVIVED (2622 passed in 22.38s) | D50 a record of this package |
| caseR10_record_other_package@REST | case/releases.py:507 | `if record.name != name:` → `if False:` | REST | SURVIVED (1763 passed, 3 skipped in 54.19s) | D50 a record of this package |
| caseR11_diff_unknown_value | case/changes.py:138 | `raise DiffRefused(f"the diff can't show a {type(value).__name__}")` → `return ""` | QUICK | SURVIVED (2622 passed in 21.81s) | D55 fail closed: never left unsaid |
| caseR11_diff_unknown_value@REST | case/changes.py:138 | `raise DiffRefused(f"the diff can't show a {type(value).__name__}")` → `return ""` | REST | SURVIVED (1763 passed, 3 skipped in 55.10s) | D55 fail closed: never left unsaid |
| caseR12_event_two_senders | case/definition.py:133 | `if (self.system is None) == (self.roles is None):` → `if False:` | QUICK | killed (1 failed, 1317 passed in 13.95s) | D41 one sender |
| caseR13_assign_answered_no_step | case/definition.py:230 | `if self.to == "answered" and self.step is None:` → `if False:` | QUICK | killed (1 failed, 120 passed in 4.04s) | D71 answered names its task |
| caseR14_reminder_no_age | case/definition.py:531 | `if not ages:` → `if False:` | QUICK | killed (1 failed, 1785 passed in 15.31s) | D46 a reminder of nothing |
| caseR15_story_answer_names_one | case/story.py:73 | `if (self.step is None) == (self.entry is None):` → `if False:` | QUICK | SURVIVED (2622 passed in 21.17s) | D45 a story's answer names one |
| caseR15_story_answer_names_one@REST | case/story.py:73 | `if (self.step is None) == (self.entry is None):` → `if False:` | REST | SURVIVED (1763 passed, 3 skipped in 52.48s) | D45 a story's answer names one |
| coreR01_promise_key_not_text | core/promise.py:59 | `if not isinstance(key, str):` → `if False:` | QUICK | SURVIVED (2622 passed in 20.59s) | D83 a promise holds no key that isn't a text |
| coreR01_promise_key_not_text@REST | core/promise.py:59 | `if not isinstance(key, str):` → `if False:` | REST | SURVIVED (1763 passed, 3 skipped in 53.15s) | D83 a promise holds no key that isn't a text |
| coreR02_schema_model_config | core/contract_schema.py:38 | `if model.model_config:` → `if False:` | QUICK | killed (1 failed, 993 passed in 9.86s) | D83 a contract's model sets no model_config |
| coreR03_schema_default | core/contract_schema.py:191 | `if not field.is_required() and field.default is not None:` → `if False:` | QUICK | killed (1 failed, 985 passed in 9.69s) | D83 a default other than None |
| coreR04_schema_unknown_mark | core/contract_schema.py:194 | `if any(not isinstance(mark, MARKS) for mark in field.metadata):` → `if False:` | QUICK | killed (1 failed, 613 passed in 6.53s) | D83 an unknown constraint or mark |
| coreR05_plan_no_roles | core/plan.py:130 | `if not roles:` → `if False:` | QUICK | killed (1 failed, 1809 passed in 15.10s) | D22 no roles would mean anyone |
| coreR06_plan_source_label | core/plan.py:151 | `if f"{origin}:" != UNTRUSTED_ORIGIN or not is_label(label):` → `if False:` | QUICK | killed (1 failed, 1892 passed in 15.27s) | D12 a declared source is untrusted:<label> |
| coreR07_only_from_no_system | core/policy.py:67 | `if not self.systems:` → `if False:` | QUICK | killed (1 failed, 605 passed in 6.22s) | D21 only_from names a system |
| coreR08_idempotency_required | core/contract.py:153 | `if self.effect in ("write", "notify") and self.idempotency_key is None` → `if False:` | QUICK | killed (1 failed, 573 passed in 6.38s) | D17 a side-effecting activity names its key |
| coreR09_output_label_unregistered | core/catalog.py:204 | `if origin == "untrusted" and label not in self._labels:` → `if False:` | QUICK | killed (1 failed, 608 passed in 6.02s) | D12 an output's label registered |
| coreR10_output_system_unregistered | core/catalog.py:210 | `if origin == "system" and label not in self._systems:` → `if False:` | QUICK | killed (1 failed, 609 passed in 6.10s) | D29/D30 an output's system registered |
| coreR11_item_outside | core/expressions/evaluate.py:69 | `if element is None:` → `if False:` | QUICK | SURVIVED (2622 passed in 19.88s) | fail closed: item only inside count/sum (backstop) |
| coreR11_item_outside@REST | core/expressions/evaluate.py:69 | `if element is None:` → `if False:` | REST | SURVIVED (1763 passed, 3 skipped in 53.53s) | fail closed: item only inside count/sum (backstop) |
| temp01_codec_no_case | temporal/codec.py:81 | `if self.case is None:` → `if False:` | temporal_sensitive sensitive | killed (1 failed, 28 passed in 4.99s) | D31 a sensitive part with no case is refused |
| temp02_codec_skips_parts | temporal/codec.py:78 | `names = sorted(name for name in payload.metadata if name.startswith(be` → `names = []` | temporal_sensitive sensitive | killed (5 failed, 24 passed in 4.92s) | D31 each sensitive part sealed |
| temp03_failure_not_sealed | temporal/codec.py:111 | `"message": Sensitive(failure.message),` → `"message": failure.message,` | temporal_sensitive sensitive | killed (2 failed, 27 passed in 5.10s) | D31 a failure's message sealed |
| temp04_failure_message_kept | temporal/codec.py:115 | `failure.message, failure.stack_trace = ENCODED_FAILURE, ""` → `failure.stack_trace = ""` | temporal_sensitive sensitive | killed (2 failed, 27 passed in 5.79s) | D31 failure message moved out of the clear |
| temp05_log_keeps_exception | temporal/logs.py:33 | `record.exc_info, record.exc_text, record.stack_info = None, None, None` → `pass` | temporal_sensitive sensitive | killed (2 failed, 27 passed in 5.04s) | D31 log filter: exception type only |
| temp06_log_filter_not_installed | temporal/logs.py:45 | `logger.addFilter(TYPE_ONLY)` → `pass` | temporal_sensitive sensitive | killed (2 failed, 27 passed in 4.78s) | D31 log filter installed |
| temp07_converter_reads_encrypted | temporal/converter.py:114 | `if any(name.startswith(ENCRYPTED) for name in payload.metadata):` → `if False:` | temporal_sensitive sensitive | killed (1 failed, 28 passed in 5.80s) | D31 fail closed: encrypted part never read |
| temp08_client_without_codec | temporal/converter.py:180 | `if not isinstance(converter.payload_codec, SensitiveCodec) or (` → `if False and (` | temporal_sensitive sensitive temporal | killed (2 failed, 57 passed in 23.61s) | D31 refuse a client that doesn't encrypt |
| temp09_converter_float | temporal/converter.py:47 | `if isinstance(value, float):` → `if False:` | temporal_sensitive sensitive temporal expressions | killed (1 failed, 267 passed in 23.58s) | D20 no float crosses |
| temp10_converter_mark_key | temporal/converter.py:74 | `if MARK in value:` → `if False:` | temporal_sensitive sensitive temporal | killed (1 failed, 58 passed in 22.75s) | converter's own key never data |
| temp11_export_in_clear | temporal/audit.py:82 | `if field in sensitive and not isinstance(value, Sensitive):` → `if False:` | audit_export audit_records | killed (1 failed, 42 passed in 11.54s) | D77 a value of one in clear fails the whole call |
| temp12_export_restricted_unsaid | temporal/audit.py:178 | `if field in self.restricted:` → `if False:` | audit_export audit_records | killed (1 failed, 42 passed in 11.81s) | D30/D77 a restricted value says who may see it |
| temp13_export_retries_11 | temporal/cases.py:443 | `maximum_attempts=10,` → `maximum_attempts=11,` | audit_export audit_records | killed (1 failed, 42 passed in 11.97s) | D77 10 attempts |
| temp14_export_refused_retried | temporal/cases.py:447 | `non_retryable_error_types=["ExportRefused", "AuditRefused", "KeyRefuse` → `non_retryable_error_types=["AuditRefused", "KeyRefused"],` | audit_export audit_records | killed (1 failed, 42 passed in 11.68s) | D77 a refusal never retried |
| temp15_audit_bound_257 | temporal/cases.py:473 | `audit_bound: ClassVar[int] = 256 * 1024` → `audit_bound: ClassVar[int] = 257 * 1024` | audit_export audit_records | killed (1 failed, 42 passed in 11.81s) | D77 256 KB hold |
| temp16_hold_strict | temporal/cases.py:860 | `return waiting_size(self.state.audit) >= self.audit_bound` → `return waiting_size(self.state.audit) > self.audit_bound` | audit_export audit_records | SURVIVED (43 passed in 11.60s) | D77 hold at the bound |
| temp17_opens_unreleased | temporal/cases.py:961 | `if not is_release(case, release.plans, release.digest, release.cases):` → `if False:` | temporal_case_release temporal_children | killed (2 failed, 45 passed in 46.43s) | D51 digest recheck at opening |
| temp18_wording_unchecked | temporal/cases.py:685 | `if not is_release(case, plans, self.release.digest):` → `if False:` | temporal_case_release notes releases | killed (1 failed, 61 passed in 19.45s) | D51 a wording read is the release's |
| temp19_engine_not_opening | temporal/cases.py:1562 | `if event.value.engine in KNOWN and event.value.engine not in OPENING:` → `if False:` | temporal_migrations migrations | killed (1 failed, 29 passed in 13.56s) | D51 a known engine version no case opens at |
| temp20_forget_child_alone | temporal/forget.py:108 | `if "/" not in case:` → `if True:` | forget temporal_forget | SURVIVED (32 passed in 19.49s) | D75 a child is not forgotten alone |
| temp20_forget_child_alone@TEMP | temporal/forget.py:108 | `if "/" not in case:` → `if True:` | TEMP | killed (1 failed, 139 passed in 118.78s (0:01:58)) | D75 a child is not forgotten alone |
| temp21_forget_unreadable_definition | temporal/forget.py:123 | `if found.forgetting == "":` → `if False:` | forget temporal_forget | killed (3 failed, 29 passed in 18.08s) | D32 fail closed: unknown forgetting |
| temp22_forget_while_open_closed | temporal/forget.py:131 | `if found.forgetting == "while_open" and not found.running:` → `if False:` | forget temporal_forget | killed (3 failed, 29 passed in 18.12s) | D32 while_open refuses a closed case |
| temp23_forget_never | temporal/forget.py:129 | `if found.forgetting == "never":` → `if False:` | forget temporal_forget | killed (3 failed, 29 passed in 18.08s) | D32 never |
| temp24_forget_same_person | temporal/forget.py:150 | `if by == found.by:` → `if False:` | forget temporal_forget | killed (2 failed, 30 passed in 18.36s) | D32 two people / opener |
| temp25_closed_first_ignored | temporal/forget.py:344 | `if self.found.forgetting == "while_open":` → `if False:` | forget temporal_forget | killed (1 failed, 31 passed in 19.13s) | D32 closed before the approval reached it |
| temp26_forget_identifier | temporal/forget.py:375 | `if (wrong := identifier_problem(sent.by)) is not None:` → `if False:` | forget temporal_forget | SURVIVED (32 passed in 18.61s) | D22 identifier spelling |
| temp27_contract_check_new_work | temporal/contract_check.py:183 | `if event.event_id > asked and (what := new_work(event)) is not None:` → `if False:` | temporal_workflow_step workflow_step temporal_keys | killed (1 failed, 38 passed in 33.88s) | D29/D40 a cancellable contract schedules nothing new |
| temp28_contract_check_ends_early | temporal/contract_check.py:194 | `if started:` → `if False:` | temporal_workflow_step workflow_step temporal_keys | killed (1 failed, 38 passed in 35.10s) | cancellable: ends only once all ended |
| temp29_contract_check_undeclared_output | temporal/contract_check.py:235 | `if name not in contract.output.model_fields` → `if False` | temporal_workflow_step workflow_step temporal_keys | killed (1 failed, 38 passed in 31.88s) | contract out of date |
| temp30_manifest_refused | temporal/registry.py:313 | `if not answer.done:` → `if False:` | temporal_registry temporal_activate | killed (2 failed, 24 passed in 33.62s) | D54 a manifest the registry refuses |
| temp31_carried_bool_number | temporal/carried.py:497 | `if isinstance(number, bool) or not isinstance(number, int \| Decimal) o` → `if not isinstance(number, int \| Decimal) or number % 1 != 0:` | temporal_case repeated required | SURVIVED (150 passed in 34.58s) | D27 carried state read fail closed |
| temp32_carried_bad_date | temporal/carried.py:489 | `if day is None:` → `if False:` | temporal_dates dates temporal_case | killed (1 failed, 114 passed in 34.71s) | D66 carried date |
| tool01_vault_exportable | tooling/vault.py:320 | `if config[setting] is not False:` → `if False:` | vault_keys doctor | killed (1 failed, 71 passed, 3 skipped in 7.87s) | D78 exportable key refused |
| tool02_vault_type | tooling/vault.py:324 | `if config["type"] != KEY_TYPE:` → `if False:` | vault_keys doctor | killed (1 failed, 71 passed, 3 skipped in 5.01s) | D78 key of another type refused |
| tool03_vault_http | tooling/vault.py:342 | `if parts.scheme == "https" or (parts.scheme == "http" and parts.hostna` → `if True:` | vault_keys doctor | killed (1 failed, 71 passed, 3 skipped in 5.29s) | D78 http refused |
| tool04_vault_proxy | tooling/vault.py:366 | `urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirec` → `urllib.request.build_opener(NoRedirect())` | vault_keys doctor | killed (1 failed, 71 passed, 3 skipped in 5.14s) | D78 no proxy |
| tool05_vault_redirect | tooling/vault.py:366 | `urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirec` → `urllib.request.build_opener(urllib.request.ProxyHandler({}))` | vault_keys doctor | killed (1 failed, 71 passed, 3 skipped in 4.24s) | D78 no redirects |
| tool06_vault_mark_ignored_use | tooling/vault.py:198 | `if self.marked(case, name):` → `if False:` | vault_keys doctor | killed (6 failed, 66 passed, 3 skipped in 4.98s) | D78 mark outlives key: marked key never used |
| tool07_vault_state_mark | tooling/vault.py:163 | `if self.marked(case, name):` → `if False:` | vault_keys doctor | killed (6 failed, 66 passed, 3 skipped in 4.39s) | D78 state reads the mark |
| tool08_vault_destroy_no_mark | tooling/vault.py:151 | `self.ask(case, "POST", self.mark_path(name), mark, {200, 204})` → `pass` | vault_keys doctor | killed (1 failed, 71 passed, 3 skipped in 4.01s) | D78 mark first |
| tool09_vault_destroy_none | tooling/vault.py:145 | `if self.key_config(case, name) is None:` → `if False:` | vault_keys doctor | killed (1 failed, 71 passed, 3 skipped in 5.14s) | D78 no key to destroy refused |
| tool10_vault_name_long | tooling/vault.py:48 | `if len(name) > LONGEST:` → `if False:` | vault_keys doctor | killed (1 failed, 71 passed, 3 skipped in 4.90s) | D78 key name bound |
| tool11_vault_token_unset | tooling/vault.py:370 | `if not token:` → `if False:` | vault_keys doctor | SURVIVED (72 passed, 3 skipped in 4.79s) | D62/D78 token only from env |
| tool11_vault_token_unset@FAST | tooling/vault.py:370 | `if not token:` → `if False:` | FAST | SURVIVED (4385 passed, 3 skipped in 72.82s (0:01:12)) | D62/D78 token only from env |
| tool12_filekeys_reuse | tooling/keys.py:73 | `if case in keys:` → `if False:` | vault_keys temporal_keys forget | killed (1 failed, 34 passed, 3 skipped in 13.22s) | D31 a key never made again |
| tool13_filekeys_destroyed_used | tooling/keys.py:122 | `if stored is DESTROYED:` → `if False:` | vault_keys temporal_keys forget temporal_sensitive | killed (1 failed, 50 passed, 3 skipped in 18.61s) | D15 destroyed key unusable |
| tool14_filekeys_damaged | tooling/keys.py:107 | `except InvalidTag:` → `except InvalidTag:` | vault_keys temporal_sensitive sensitive | killed (2 failed, 47 passed, 3 skipped in 9.31s) | codec: a damaged part is an error, never a guess |
| tool15_doctor_dev_provider | tooling/doctor.py:126 | `if development is True:` → `if False:` | doctor doctor_live connecting | killed (2 failed, 74 passed in 3.67s) | D81 development provider fails |
| tool16_doctor_unsaid_provider | tooling/doctor.py:131 | `if development is not False:` → `if False:` | doctor doctor_live connecting | killed (2 failed, 74 passed in 4.03s) | D81 a provider that doesn't say fails |
| tool17_doctor_dev_catalog | tooling/doctor.py:98 | `if name == DEVELOPMENT:` → `if False:` | doctor doctor_live connecting | killed (1 failed, 75 passed in 4.12s) | D59/D81 development catalog |
| tool18_doctor_dev_env | tooling/doctor.py:233 | `if registry.development:` → `if False:` | doctor doctor_live connecting | killed (1 failed, 75 passed in 4.15s) | D81 production environment |
| tool19_doctor_outside_deny | tooling/doctor.py:357 | `if held[outside] != ["deny"]:` → `if False:` | doctor doctor_live connecting | killed (1 failed, 75 passed in 4.51s) | D78/D81 token denied other keys |
| tool20_doctor_mark_delete | tooling/doctor.py:355 | `if {"delete", "root"} & set(held[path])` → `if False` | doctor doctor_live connecting | killed (2 failed, 74 passed in 4.05s) | D78/D81 token can't delete a mark |
| tool21_doctor_bound | tooling/doctor.py:52 | `PROBE_BOUND = 10.0  # seconds` → `PROBE_BOUND = 11.0  # seconds` | doctor doctor_live connecting | SURVIVED (76 passed in 2.97s) | D81 bound |
| tool21_doctor_bound@FAST | tooling/doctor.py:52 | `PROBE_BOUND = 10.0  # seconds` → `PROBE_BOUND = 11.0  # seconds` | FAST | SURVIVED (4385 passed, 3 skipped in 73.78s (0:01:13)) | D81 bound |
| tool22_keeping_dev_keys | case/registry.py:127 | `elif manifest.keys.development:` → `elif False:` | doctor doctor_live connecting temporal_registry activation | killed (4 failed, 114 passed in 27.54s) | D81 production refusing development providers |
| tool23_deploy_no_catalog | tooling/deployment.py:171 | `if name is None:` → `if False:` | deployment_catalog check cli diff | killed (1 failed, 86 passed in 2.18s) | D59 never the development catalog by default |
| tool24_connect_identity | tooling/connecting.py:61 | `if identity is None or identity not in temporal.identities:` → `if False:` | doctor doctor_live connecting | killed (8 failed, 68 passed in 3.01s) | D81 connecting as a configured identity |
| tool25_sheet_not_drafted | tooling/draft_sheet.py:76 | `if record.verdict != "drafted":` → `if False:` | drafting draft_sheet approve authoring | killed (1 failed, 57 passed in 2.89s) | D64 only a draft that passed |
| tool26_sheet_hash | tooling/draft_sheet.py:84 | `if hashlib.sha256(written).hexdigest() != record.draft_sha256:` → `if False:` | drafting draft_sheet approve authoring | killed (1 failed, 57 passed in 2.79s) | D64 draft hash check |
| tool27_sheet_reference | tooling/draft_sheet.py:91 | `if (reference := reference_of(text)) != record.plan:` → `if False:` | drafting draft_sheet approve authoring | killed (1 failed, 57 passed in 3.54s) | D64 record's plan |
| tool28_sheet_package | tooling/draft_sheet.py:97 | `if before.name != record.package:` → `if False:` | drafting draft_sheet approve authoring | killed (1 failed, 57 passed in 3.07s) | D64 package drafted for |
| tool29_drafts_folder_default | tooling/drafting.py:93 | `if found.drafts is None:` → `if False:` | drafting draft_sheet approve authoring | killed (1 failed, 57 passed in 3.15s) | D63 no default drafts folder |
| tool30_abandoned_written | tooling/drafting.py:67 | `if authored.verdict == "drafted" and authored.plan is not None:` → `if True:` | drafting draft_sheet approve authoring | killed (3 failed, 55 passed in 2.80s) | D63 nothing written when abandoned |
| tool31_record_overwritten | tooling/releases.py:123 | `raise RecordRefused(` → `return False` | releases summary notes | killed (1 failed, 91 passed in 1.77s) | D50 immutable record |
| tool32_record_without_notes | tooling/releases.py:110 | `if kept.notes is None:` → `if False:` | releases summary notes | killed (1 failed, 91 passed in 1.62s) | D57 nothing recorded without its notes |
| tool33_unchanged_bytes | tooling/check.py:218 | `elif committed.read_bytes() != text.encode():` → `elif False:` | check unchanged cli | killed (3 failed, 24 passed in 1.69s) | D59 --unchanged |
| tool34_record_path_name | tooling/releases.py:93 | `if path.name != file_name(kept):` → `if False:` | releases summary notes | killed (1 failed, 91 passed in 1.59s) | D50 record in its own file |
| coreU01_evaluator_unknown | core/expressions/evaluate.py:134 | `raise ExpressionError(f"can't evaluate {expression!r}: it isn't a pars` → `return False` | QUICK | killed (1 failed, 1389 passed in 12.99s) | CLAUDE.md: every evaluator has a negative test for an input it doesn't know: expression evaluator |
| coreU02_type_check_unknown | core/expressions/check.py:238 | `raise refused(path, f"can't check {expression!r}")` → `return BooleanType()` | QUICK | SURVIVED (2622 passed in 21.02s) | CLAUDE.md: every evaluator has a negative test for an input it doesn't know: type checker |
| coreU02_type_check_unknown@REST | core/expressions/check.py:238 | `raise refused(path, f"can't check {expression!r}")` → `return BooleanType()` | REST | SURVIVED (1763 passed, 3 skipped in 53.21s) | CLAUDE.md: every evaluator has a negative test for an input it doesn't know: type checker |
| coreU03_render_unknown | core/expressions/render.py:74 | `raise ExpressionInvalid(f"can't render {expression!r}: it isn't a pars` → `return ""` | QUICK | killed (1 failed, 1522 passed in 13.30s) | CLAUDE.md: every evaluator has a negative test for an input it doesn't know: renderer |
| coreU04_fields_read_unknown | core/provenance.py:126 | `raise TypeError(f"not an expression: {type(expression).__name__}")` → `return []` | QUICK | killed (1 failed, 1958 passed in 15.12s) | CLAUDE.md: every evaluator has a negative test for an input it doesn't know: what an expression reads |
| coreU05_state_kind_unknown | core/interpreter.py:251 | `raise Stop(f"{here} is a kind of state this engine doesn't know: {kind` → `run.status = "succeeded"` | QUICK | killed (1 failed, 1680 passed in 14.18s) | CLAUDE.md: every evaluator has a negative test for an input it doesn't know: step kinds of a plan |
| caseU01_moment_unknown | case/rules.py:60 | `raise ValueError(f"{moment!r} is not a moment Ventoux knows")` → `return "opened"  # type: ignore` | QUICK | killed (1 failed, 2193 passed in 19.80s) | CLAUDE.md: every evaluator has a negative test for an input it doesn't know: moments |


---

## Pass 5: an outsider's run

Everything below ran at commit `c2739ad` (source as at `3edb471`; the commits between only add
review probes). The wheel was built with `uv build --out-dir <scratchpad>/p5/dist` (nothing was
written inside the repository: `git status --short` was the same before and after) and installed in
a fresh virtual environment outside the repository (`<scratchpad>/p5/project`, Python 3.13);
`python -c "import ventoux; print(ventoux.__file__)"` pointed into that environment's
`site-packages`. I worked from README.md, docs/QUICKSTART.md, docs/guides, CHANGELOG.md, `--help`
and error messages only. I did not read `src/` or `tests/`; where I used introspection
(`inspect.signature`, `dir()`), I say so. Temporal was its local development server, from the
binary the Temporal Python SDK had already cached on this machine (no download).

How long each stage of my own case took, in attempts:

| Stage | Attempts | What cost the extra attempts |
|---|---|---|
| Catalog, contract, activity, roles | 1 | I had to guess `from ventoux.core.catalog import Catalog` (finding 3) |
| Builder file and `ventoux check` | 1 (2 with the warning fixed) | nothing: the warning said what to add |
| In-memory test with `run_case` | 2 | `run_case` ran under the development catalog (finding 4) |
| On Temporal: worker, open, task, approval, close, report, audit | 3 | `start_case` wants the JSON, not the builder's `Case` (finding 5); the first ID was spent |
| Release, environment, activation | 5 | no import for `registry_worker`, `environment_worker` needs `audit=`, commands that hang with no registry worker (findings 3, 6, 8) |

### Findings

#### 5.1 The quickstart, followed to the letter, fails in six places (*misleads*; it is the brief's own test of principle 5)

Three of its commands do not exist (`ventoux init`, `ventoux dev`, `ventoux start`), `uv run
pytest` as printed cannot import `cases.refund`, the step added in section 7 is refused by `ventoux
check`, and `ventoux diff` with no arguments is refused. Sections 2, 3, 5 (with `python -m pytest`)
and 6 work as printed, word for word, including both refusals of section 6 (the only difference:
the line number is 21, not 19, once the two lines of the new field are added above the step).

Promise touched: brief, principle 5: "**Easy to adopt.** A developer runs a first case in 15
minutes, meeting at most five concepts." and "The quickstart (`QUICKSTART.md`) is the running test
of this principle." CLAUDE.md: "The quickstart's acceptance tests must stay green in every layer."
The three tests are green; the page around them is not what a newcomer can follow. The inbox is a
recorded limit (D79: "Ventoux ships no HTTP API and no inbox in v1.0; both move to \"Beyond v1.0\""), so section 4 describes
something v1.0 will not have, and the page was not changed.

Proof (`uv run python reviews/2026-11/probes/p5_quickstart_to_the_letter.py`, trimmed):

```
$ init  -> exit 2: ventoux: error: argument command: invalid choice: 'init' (choose from 'check', ...
$ check  -> exit 2: no catalog is named: name the deployment's in pyproject.toml, [tool.ventoux] catalog = "module:NAME", ...
$ check  -> exit 0: ✓ refund is valid (3 steps): packages/refund/
$ dev  -> exit 2: ventoux: error: argument command: invalid choice: 'dev' ...
$ start refund --file order_id=ord-1 amount=250  -> exit 2: ... invalid choice: 'start' ...
$ .../pytest -q -p no:cacheprovider  -> exit 2: 1 error in 0.77s      (ModuleNotFoundError: No module named 'cases')
$ .../python3 -m pytest -q -p no:cacheprovider  -> exit 0: 3 passed in 0.57s
cases/refund.py:43: steps.notify_rejection.inputs.order_id UNKNOWN_INPUT: letters.draft@2 has no input order_id: its inputs are template, to_customer
cases/refund.py:43: steps.notify_rejection.inputs MISSING_INPUT: letters.draft@2 needs the input to_customer: add it to inputs
cases/refund.py:43: steps.notify_rejection.inputs MISSING_INPUT: letters.draft@2 needs the input template: add it to inputs
$ diff  -> exit 2: ventoux diff: error: the following arguments are required: old, new
RESULT: BROKEN - 6 places where the quickstart, followed to the letter, does not work as printed
```

From the installed wheel only (not in the probe): `uv init refunds && cd refunds && uv add ventoux`
ends with "your project's requirements are unsatisfiable" (the package is not published;
CHANGELOG.md says "0.1.0 (not yet released)", so this one is expected, but the page does not say
so); and in a project made by `uv init`, `uv run pytest` runs a `pytest` from outside the project
("No module named 'ventoux'") until `uv add --dev pytest`, which the page never asks for.

Other things the page says that a newcomer cannot know are untrue: its first paragraph, "**Design
draft.** This page describes how Ventoux is meant to work; none of it is built yet"; section 1,
"`ventoux init` creates a `cases/` folder and a development catalog" and section 3, "pyproject.toml,
which `ventoux init` writes" (nothing writes it; the error message of `ventoux check` does say what
to write, which is what saved me); section 7's output of `ventoux diff` ("refund: changes since the
last release") has no command that prints it without two folders.

Concepts: the page promises five ("a **case**, its **case file**, **steps**, **approvals** and
**rules**"). To get through it I also had to take in: a reference, a task, an outcome, an activity,
the catalog, a role, a sequence, `requires`, a package folder, an untrusted source, an input
policy, and a release. That is twelve more than five, by my count; several are one-line mentions.

Proposed fix: rewrite the quickstart against what exists (install from the built wheel until it is
published; the `pyproject.toml` lines written by hand; `python -m pytest` or a `pythonpath`
setting; section 4 as a first run on Temporal or dropped; `letters.draft@2` given `template` and
`to_customer`; `ventoux diff old new`), remove the "none of it is built yet" banner, and add a test
that runs the page's blocks and commands as printed, as the builder guide's test does for imports.

Probe: `reviews/2026-11/probes/p5_quickstart_to_the_letter.py`.

#### 5.2 README.md says there is no code (*misleads*)

README.md, "Status": "Design stage. There is no code yet: Ventoux is being built in Python, one
layer at a time, starting from the design documents below. Nothing here is ready to use." and
"`docs/QUICKSTART.md`: a first case in 15 minutes, written before the code". Layers 0 to 20 are
merged and the wheel installs and runs a case on Temporal (probe `p5_own_case.py`). The README is
also the wheel's long description if `pyproject.toml` names it (not checked). It never says how to
install the package or how to start a local Temporal server; no document does (see finding 7).

Proof: `uv run python reviews/2026-11/probes/p5_public_names.py` prints
`README.md still says "There is no code yet ... Nothing here is ready to use": True` and
`some document says how to start a local Temporal server: False`.

Proposed fix: a README for 0.1.0: what works, how to install, the first page to read.

#### 5.3 Thirteen names the documents tell a team to use are not in `public.json` (*weakens one*)

To run my own case I needed two names outside the supported list, and the guides name eleven more
that a deployment cannot do without (closing a case for a reason, proposing a step, retrying a
failed run, reading the case file by role, the registry's worker).

Promise touched: D82: "**The supported imports are a committed list,** `src/ventoux/public.json`:
the names the guides tell teams to import, the builder's `__all__`, and the protocols a deployment
implements. Everything else is internal: importable, unsupported, free to change. A listed name
that disappears fails a test ... a name a guide imports that the list doesn't hold fails too." The
test reads `import` lines in docs/guides; these names are told in prose, in a snippet with no
import line, or in the quickstart, so nothing notices.

Proof (`uv run python reviews/2026-11/probes/p5_public_names.py`, trimmed to module.name and where
it is said; each line ends "exists: True; in public.json: False"):

```
ventoux.testing.run_case            docs/QUICKSTART.md: 'from ventoux.testing import run_case'
ventoux.testing.CATALOG             docs/QUICKSTART.md: 'catalog = "ventoux.testing:CATALOG"'
ventoux.core.catalog.Catalog        docs/guides/activities.md: 'catalog.register(payments_refund)'
ventoux.temporal.registry.registry_worker   docs/guides/releases.md: 'registry_worker(client)'
ventoux.temporal.registry.open_cases        docs/guides/releases.md: 'open_cases(client,'
ventoux.temporal.cases.propose / retry / close / view / shown   docs/guides/cases.md
ventoux.temporal.cases.propose_change       docs/guides/deployment.md
ventoux.temporal.sandbox.SANDBOX            docs/guides/case-data.md
ventoux.tooling.audit.same                  docs/guides/audit.md
RESULT: BROKEN - 13 names the documents tell a team to use exist and are not in public.json
```

`Catalog` is the worst for a newcomer: every guide writes `catalog.register(...)`,
`catalog.register_role(...)` or `from refunds.catalog import CATALOG`, and none shows how a catalog
is made or where the class is imported from. I guessed `ventoux.core.catalog.Catalog`; no document
told me. `registry_worker` is the same: the releases guide says "Run the registries' worker
(`registry_worker(client)`...)" with no module; I found it by trying each module of
`ventoux.temporal` for the attribute.

What held: every `import` line in every guide names something in `public.json`, and each imports
from the installed wheel (my own scan, `<scratchpad>/p5/guides_scan.py`, run in the wheel's
environment: 0 names missing in the ten guides; `run_case` in the quickstart is the only one).

Proposed fix: decide, as D82 says such things are decided, which of these are supported and list
them (at least `Catalog`, `run_case`, the development `CATALOG`, the other client functions of
`ventoux.temporal.cases`, `registry_worker`, `open_cases`); show an import line for each in a
guide; widen the test to the quickstart and to names in backticks followed by `(`.

Probe: `reviews/2026-11/probes/p5_public_names.py`.

#### 5.4 `run_case` plays a project's case under the development catalog, and the refusal names the wrong cause (*misleads*)

My case was checked by `ventoux check` against my catalog (named in `pyproject.toml`). `run_case`,
called as the cases guide and the quickstart show, used the development catalog without saying so,
did not object that the case names a contract and roles that catalog doesn't hold, and refused the
first answer with "dee has no role", although `people={"dee": ["desk"]}` gives the role.

Doc text (docs/guides/cases.md, "Testing a case"): the paragraph lists `people`, `opened_by`,
`activities`, `workflows`, `held`; it never names `catalog`. CLAUDE.md: each rule's "error message
saying what is wrong, then what to do". Here the message says something untrue and no next step. I
found `catalog=` only by `inspect.signature(run_case)`.

Proof (`uv run python reviews/2026-11/probes/p5_first_hour_surprises.py`):

```
1. run_case without catalog=: AnswerRefused: assess#1 is answered by desk, and dee has no role
```

With `catalog=CATALOG` the same script closes the case (probe `p5_own_case.py`: "in memory: closed
True reached reserve True").

Proposed fix: say `catalog=` in the guide and the quickstart's "Next"; have `run_case` check the
definition against the catalog it runs with before opening (an unknown contract or role is an
error then, saying "desk is not a role of this catalog: pass catalog=..."), or read the project's
catalog as `ventoux check` does.

Probe: `reviews/2026-11/probes/p5_first_hour_surprises.py` (item 1).

#### 5.5 `start_case` given the builder's `Case` raises a bare `AttributeError`, after spending the ID (*misleads*)

docs/guides/cases.md shows `case = await start_case(client, RefundCases, refund, file={...},
id="refund-A-1001", task_queue="refunds")` and never says what `refund` is there. In the
quickstart and in `run_case` (`run_case(refund, ...)`, whose own help says "`definition` may be the
builder's `Case`") it is the builder's object. `start_case` takes only the stored JSON
(`packages/loan/case.json`, read with `json`), or a release record.

Proof (probe, item 2): `2. start_case with the builder's Case: AttributeError: 'Case' object has no
attribute 'get'`. From the wheel, the second try under the same ID then said `KeyRefused: a key was
already made for loan-1: open the case under a new ID`: the key is made before the definition is
looked at, so a typing mistake spends an ID. (That an ID is spent when starting fails is said in
the case data guide; that a wrong argument does it is the surprise.)

Proposed fix: say in the guide where the definition comes from (the package's `case.json`); refuse
anything that isn't a definition or a release record before making the key, saying what to pass;
or accept the builder's `Case` as `run_case` does.

Probe: `reviews/2026-11/probes/p5_first_hour_surprises.py` (item 2).

#### 5.6 The releases guide's `environment_worker(...)` call is a `TypeError` (*misleads*)

docs/guides/releases.md, "Activating a release in an environment":

```python
worker = await environment_worker(client, "refunds", RefundCases, RefundPlans,
                                  {"payments.refund@2": refund, ...}, build="4f2a9c1",
                                  identity="refunds-a", activity_executor=activity_executor)
```

Run as shown (with a real mapping in place of `...`), from the wheel: `TypeError:
environment_worker() missing 1 required keyword-only argument: 'audit'`. The probe shows the
parameter has no default (item 3: `environment_worker's audit parameter has a default: False`).

Proposed fix: add `audit=store` to the snippet (the audit guide's `case_worker` snippet has it).

Probe: `reviews/2026-11/probes/p5_first_hour_surprises.py` (item 3).

#### 5.7 `report` just after `start_case` on a release says the case is a draft with no history (*misleads*)

docs/guides/cases.md, "A case runs its release":

```python
case = await start_case(client, RefundCases, refund_1, file={...}, id="refund-A-1002", task_queue="refunds")
now = await report(case)
assert (now.release, now.engine) == ("refund 1", 3)
```

With the workflow naming an environment (as the releases guide says a production one does), the
first `report` answers before the case has opened: `release='draft'`, `status='open'`, nothing
waiting, an empty history. A moment later it says `loan 1`. So the guide's assertion fails as
written, and worse, a caller reading the report at once is told a case that is opening on a
release is a draft with nothing to do. Seen three times out of three (twice from the wheel, once
in the probe).

Proof (probe, item 4):

```
   trial created: a development environment, where drafts open
   pia activated loan 1 in trial
4. report just after start_case on release loan 1: release='draft' waiting_at=[] history=[]
   a moment later: release='loan 1' waiting_at=['assess#1']
```

Without an environment the first snippet of the guide (`assert (await report(case)).waiting_at ==
["review#1"]`) held every time I ran it.

Proposed fix: until the case has opened, `report` should say so (a status of its own, or the
release it was started on), never "draft"; or `start_case` returns once the opening is decided.
The guide should say which.

Probe: `reviews/2026-11/probes/p5_first_hour_surprises.py` (item 4).

#### 5.8 Commands that need the registry's worker hang or give Temporal's own words when it isn't running (*minor*)

The releases guide says to run the registries' worker, "then" `ventoux environment create`. With no
registry worker running, from the wheel against the local server:

- `ventoux environment create production --address localhost:47233` printed `production created: a
  production environment, where drafts never open`, exit 0 (so the newcomer thinks all is well);
- `ventoux activate loan 1 --environment staging --task-queue loans2 --releases releases --by pia
  --address localhost:47233` printed, on different tries, `h2 protocol error: http2 error` (exit
  2), `no poller seen for task queue recently, worker may be down` (exit 2), and after 30 seconds
  `Timeout expired` (exit 2);
- `ventoux environment check dev2 --address localhost:47233` did not return within 30 seconds (I
  stopped it with `timeout`).

None says what to do next (CLAUDE.md: "its error message saying what is wrong, then what to do").
The guide's own list of activation problems ("`no worker polls refunds now`" and the others) is
about the case workers; with the registry worker running each of those came out as documented
(`no worker polls nobody now: start one, then activate`). These three only reproduce with a
Temporal server and timing, so they are given here as commands and not as a probe.

Proposed fix: a bounded wait and one message for all three: "production's registry isn't answering:
run its worker (registry_worker), then try again".

#### 5.9 `report` on a handle from the Temporal client is a `CaseReport` while the case is open and a plain `dict` once closed (*minor*)

The guide says of `report`: "once the case has closed, it is the report the case returned then".
The only way the guides show to get a handle to something that already runs is
`client.get_workflow_handle(...)` (cases.md, for a plan step). With such a handle to a case,
`report(handle).status` works while it is open and raises `AttributeError: 'dict' object has no
attribute 'release'` once it has closed.

Proof (probe, item 5): `5. report(client.get_workflow_handle(id)): CaseReport while open, dict once
closed`.

Proposed fix: have `report` read the closed case's result as a `CaseReport` whatever the handle,
or give teams a supported `case_handle(client, id)` and show it.

Probe: `reviews/2026-11/probes/p5_first_hour_surprises.py` (item 5).

#### 5.10 Guides run commands on folders a wheel install doesn't have (*minor*)

The guides' commands name the repository's `examples/` folder: cases.md "`uv run ventoux simulate
examples/refund/stories/nobody-reviews.json`", "`ventoux map examples/packages/refund`", "Each has
its story under `examples/checks/stories/`"; releases.md "`ventoux release
examples/packages/refund --releases releases --commit 4f2a9c1`", "`ventoux diff
examples/packages/refund refund-next`", "`ventoux summary --base base --head . --packages
examples/packages ...`". D82 says the wheel "never holds ... examples", and no guide says the
reader needs a checkout of the repository for these. With my own package in place of the example
(`ventoux release packages/loan --releases releases --commit 4f2a9c1` gave `loan 1 released:
digest d9f652b7be1b (method 1)`; `ventoux notes loan 1 --releases releases` gave `loan 1: the first
release, nothing to compare`; `ventoux diff packages/loan packages/loan` gave `loan: nothing
changed`; `ventoux map packages/loan`) each command worked. I did not run the guides' commands on
the repository's examples; the repository's own tests are said to.

Proposed fix: one sentence at the top of each guide: its examples live in the repository's
`examples/` folder, with the link.

### What held

- **D82's fresh install.** From the installed wheel, outside the repository: `ventoux version`
  printed `ventoux 0.1.0`, `engine 3`, `schema https://ventoux.dev/schema/engine-3/` (exit 0);
  `ventoux schema --unchanged` printed `✓ ...case.schema.json is unchanged` and the same for the
  plan's (exit 0); `ventoux conformance --unchanged` printed `✓ this engine conforms to
  .../ventoux/conformance` (exit 0). `ventoux conformance --export DIR` wrote 90 files.
- **The wheel's contents** (272 entries, listed with Python's `zipfile`): it holds `ventoux/py.typed`,
  `ventoux-0.1.0.dist-info/licenses/LICENSE`, `ventoux/schema/case.schema.json` and
  `plan.schema.json`, `ventoux/conformance/suite.json` with its cases, plans and catalogs, and
  `ventoux/public.json`. It holds no `tests/`, `docs/`, `scripts/` or top-level `examples/`, no
  `.pem`, `.key` or `.crt`, no key file, no recording (the two matches on "recording" and
  "history" are source modules, `case/recording.py` and `core/history.py`). See Unproven for
  `ventoux/conformance/examples/`.
- **The `anthropic` extra installs** (`uv pip install "<wheel>[anthropic]"`, then `import
  anthropic`). With no model named, `ventoux advise` says `no model is named: name it in
  pyproject.toml, [tool.ventoux] model = "…", or with --model` (exit 2); without the extra it says
  `the live provider needs the anthropic extra: pip install 'ventoux[anthropic]'`; `ventoux draft`
  with no drafts folder says `no drafts folder is named: name it in pyproject.toml, [tool.ventoux]
  drafts = "drafts"` (exit 2). No key was used.
- **My own case, end to end** (an equipment loan: three fields, a task whose outcome sets the
  deposit and reaches a milestone, an activity calling a contract I registered with my own
  implementation, a manager's approval, a second milestone): `ventoux check` passed first time and
  its one warning said exactly what to add; in memory it closed, waited "approval of reserve by
  manager", and refused "max set deposit, which reserve uses, so cannot approve it"; on Temporal
  with `case_worker`, `start_case`, `answer`, `report`, `FileKeys`, `FileAudit` and
  `data_converter` it opened, waited at `assess#1`, then `reserve.approval#1`, recorded the same
  person's approval as refused and waited on, took another manager's, ran my activity, reached
  both milestones and closed; `read_audit` gave five records (opened, answered ×3, completed) with
  the history's lines. Probe: `reviews/2026-11/probes/p5_own_case.py` (RESULT: HELD, with the two
  names outside `public.json` listed).
- **Production refuses development providers, as the deployment guide's table says:** a worker
  built with `FileKeys` and `FileAudit` in a production environment was refused with the two
  documented sentences, word for word; a worker started before its environment exists is told
  `dev2 has no registry: create it with ventoux environment create dev2`.
- **Activation, with the registry's worker running:** `pia activated loan 1 in dev2`; `ventoux
  environment check dev2` said `every release that is active or has open cases can run`; `ventoux
  retire loan 1 ...` said `loan 1 not retired: it is active in dev2: activate another first`;
  `ventoux environment harden staging --by pia` said `pia made staging a production environment:
  drafts no longer open`; a worker that polls without a manifest was named (`7260@vm polls loans
  and published no manifest in staging: it may serve anything`). All as releases.md prints them.
- **Messages that told me what to do next:** `no catalog is named: ...`; `no releases folder is
  named: ...`; `a key was already made for loan-1: open the case under a new ID`; the
  `OUTCOME_UNREAD` warning; the `INPUT_POLICY` refusal of the quickstart's section 6.
- **Docs whose every command I ran worked as shown:** docs/guides/releasing-ventoux.md (the three
  commands of the fresh install; the tag and publish steps are the maintainer's and were not run);
  docs/guides/builder.md (`uv run ventoux check`, `uv run ventoux check --unchanged`); the
  quickstart's sections 2, 3, 5 (with `python -m pytest`) and 6. For activities.md, audit.md,
  case-data.md, expressions.md and plans.md I ran no command as printed beyond `ventoux check` and
  `ventoux promises`; every Python block in all ten guides parses (three use `...` inside a
  mapping, as placeholders) and every `ventoux` import in them resolves from the installed wheel
  and is in `public.json`.

### Unproven

- D82 says the wheel "never holds tests, examples, docs, scripts ...". The wheel holds
  `ventoux/conformance/examples/` (37 entries: definitions the suite's entries point at, such as
  `examples/quickstart/packages/refund/case.json`). I read that as part of "the conformance
  suite", which the wheel must hold, so I do not call it a finding; the sentence and the folder's
  name disagree on their face, and the brief could say which it means.
- Once, `ventoux activate` printed `pia activated loan 1 in staging` and then did not exit within
  30 seconds. I could not reproduce it (the next activations exited in under a second), and my
  worker was about to stop at that moment, so I cannot say what it waited on.
- Whether README.md is the package's long description on the index (it would then say "There is
  no code yet" on the package's page): I did not read `pyproject.toml` or the wheel's METADATA for
  it.

### Unchecked

- The guides one by one, to the letter: with the budget cut, I ran the quickstart in full and the
  guides' commands by kind, on my own package, not every example of cases.md (166 KB),
  case-data.md, plans.md, expressions.md and activities.md. Plans on Temporal (`plan_worker`,
  `start_plan`), `ventoux.testing.run_plan`, `check_workflow_contract`, forgetting, migration,
  `retry_export`, `Resolvers`/`Viewer`, `ventoux simulate`, `ventoux summary`, `ventoux hashes
  --lock`, `ventoux manifest publish` and `ventoux draft-sheet` were not exercised.
- `ventoux doctor`: it takes no `--address` (`unrecognized arguments: --address
  localhost:47233`), and I did not write a `[tool.ventoux.temporal]` section to point it at my
  server on another port; the deployment guide says commands' `--address` "win over the
  section's" in a sentence that names `activate`, `retire`, `environment`, `manifest publish` and
  `advise`, not `doctor`, so this is not a disagreement.
- Vault (`VaultKeys`) and a real cluster with mTLS: not available here.
- A live model: no key was used; only the failures with no model, no extra and no drafts folder.
- How a newcomer gets a Temporal server: no document says (finding 2's probe line). I used the
  development server binary the Temporal SDK had cached under `/tmp`, on port 47233, and stopped
  it when done.


---

## Pass 6: the brief and the docs

Probes ran at `9b92c1a` on branch `review-2026-11` (source `3edb471`; nothing under `src/`,
`tests/`, `docs/` or `examples/` differs from it). Every probe is run from the repository root
with `uv run python reviews/2026-11/probes/<name>.py`.

Scope actually covered, said plainly: this pass was cut short by a usage limit and resumed on a
tighter budget. The brief was read in full from line 1 to D34 (line 1100), then D59, D60, D74's
head, D77, D79 to D83, "Simplifications adopted", the glossary, "Layers of the system", the
non-negotiables and "Out of scope for v1.0". D35 to D58, D61 to D73, D75, D76 and D78 were only
searched by phrase, not read. See "Unchecked".

### Findings

No finding here is a guarantee broken at runtime. All are documents that say something the code
no longer does (*misleads*) or small disagreements (*minor*).

#### 6.1 A decision the code doesn't follow

##### 6.1.1 `ventoux version` does not print the schema's `$id`, and the deployment guide prints an output the command never gives (*misleads*)

D82: "The package's version, the engine version (D51) and the schema's `$id` (D60) are three
things; `ventoux version` says all three." D60: the `$id` is
"`https://ventoux.dev/schema/engine-N/case.schema.json`". The command prints three lines, and the
third is a prefix that is neither schema's `$id`. The deployment guide (`docs/guides/deployment.md`
line 35) shows one line, comma-separated, ending in the full `$id`.

```
$ uv run python reviews/2026-11/probes/p6_guides_printed_output.py
docs/guides/deployment.md: $ ventoux version
  guide prints 1 line(s); the command printed 3
    -ventoux 0.1.0, engine 3, schema https://ventoux.dev/schema/engine-3/case.schema.json
    +ventoux 0.1.0
...
RESULT: BROKEN - 1 guide output(s) differ from what the command prints: docs/guides/deployment.md: `ventoux version`
```

Observed in full: `ventoux 0.1.0` / `engine 3` / `schema https://ventoux.dev/schema/engine-3/`.
Probe: `reviews/2026-11/probes/p6_guides_printed_output.py`.
Proposed fix: make the guide's block the three lines the command prints; and either print each
schema's `$id` or have D82 gain a dated line saying the command prints the `$id`'s common prefix.

##### 6.1.2 D13 names a command that does not exist: `ventoux init` (*misleads*)

D13: "the quickstart and first guides use tasks and activities only, and `ventoux init` generates
no plan." The quickstart builds on it ("`ventoux init` creates a `cases/` folder and a development
catalog", "The catalog is named in your project's `pyproject.toml`, which `ventoux init` writes").
The command line has twenty commands and `init` is not one; neither are the quickstart's
`ventoux dev` and `ventoux start`. No dated line in D13, and no entry under "Out of scope for
v1.0" or D79, says `init` is not built (D79 moves the inbox out, which covers `dev`'s "local
inbox", but says nothing of `init` or `start`).

```
$ .venv/bin/ventoux init
ventoux: error: argument command: invalid choice: 'init' (choose from 'check', 'schema', ...)
$ uv run python reviews/2026-11/probes/p6_docs_describe_what_changed.py
BRIEF.md D13
  the document: `ventoux init` generates no plan
  observed:     `init` is a command: False
```

Probe: `reviews/2026-11/probes/p6_docs_describe_what_changed.py`.
Proposed fix: a dated line on D13 saying whether `ventoux init` is in v1.0 (and if not, how a
project gets its `[tool.ventoux]` table); the quickstart follows (finding 4.2).

#### 6.2 Two decisions that contradict each other

##### 6.2.1 D74 adds a sixth kind of step without saying it adds to the list of kinds; the glossary's "Step" row still lists four (*misleads*)

"Simplifications adopted": "**Kinds of step:** `activity` ..., `task` ..., `plan` ... and, per D6,
`workflow`". The glossary: "Step | A unit of work in a case (an activity, a human task, a plan or
a workflow) and when it may run". D41 added `wait` and said so: "a fifth kind of step ... (adds to
the Simplifications' kinds of step, and to D13's choice among them". D74 adds
"`{"kind": "case", ...}`"; its header lists "Adds to D10, D24, D25, D28, D29, D40, D48, D50, D51,
D52 and D53" and names neither the Simplifications nor D13's "Which kind of step". The glossary
gained "Child case" and "Package" rows, but its "Step" row was left at four kinds.

```
$ uv run python reviews/2026-11/probes/p6_docs_describe_what_changed.py
BRIEF.md glossary, 'Step'
  the document: | Step | A unit of work in a case (an activity, a human task, a plan or a workflow) and when it may run |
  observed:     the published case schema reads these kinds of step: ['activity', 'case', 'plan', 'task', 'wait', 'workflow']
```

Proposed fix: a dated line under "Simplifications adopted" and on D13 naming `wait` (D41) and
`case` (D74); the glossary row (a table, not a decision) updated to six kinds.

##### 6.2.2 The glossary puts resolvers in the catalog; D30 puts them in `tooling`, and the catalog holds none (*minor*)

Glossary: "Catalog | What a deployment allows, never where it runs: activity and workflow
contracts, resolvers, roles and source labels". D30: "**Resolvers** are functions registered per
system in `tooling`". The `Catalog` class has no resolver, and does hold three things the row
leaves out (systems, D30; option checks, D67; document stores, D68), which D80's own list of what
the catalog holds includes.

```
BRIEF.md glossary, 'Catalog'
  observed:     Catalog's public names: ['assigners', ..., 'register_document_store', 'register_label',
  'register_option_check', 'register_role', 'register_system', 'roles', 'systems', 'workflow'];
  resolvers are registered in tooling/resolvers.py (exists: True)
```

Probe: `p6_docs_describe_what_changed.py`. Proposed fix: the row reads as D80 lists it, without
resolvers.

##### 6.2.3 The brief's status line says "decisions D1–D26" (*minor*)

Line 3: "Status: draft, 2026-10-09; decisions D1–D26 (D3 superseded by D20)." The brief holds D1
to D83, the last dated 2026-11-10 (probe output above, first check). Proposed fix: the line states
no range, or is updated with each decision.

#### 6.3 An amendment that leaves its decision untrue

None proven beyond 1.2. The phrases "to come", "not built", "comes later", "for now", "until
then", "until layer", "not yet" and "unbuilt" were searched in the whole brief (39 lines) and each
read: every one is either still true (for example D11 "shown as blocked" stays unbuilt; D28 a
plan's waits listed in the case's `waiting_for`), or names the layer or decision that later built
it, and that decision says so (D7's `four_eyes` "(D47, to come)" then D47; D29's `cancellable`
"comes with the first thing that stops a running step" then D40; D33's timers then D44; D50 and
D55 "until `ventoux check` brings the deployment's (layer 14)" then D59, whose `--catalog` every
listed command takes, checked by a run; D76's "opens new cases at 2" then D77, `ENGINE = 3`).
See "What held".

#### 6.4 A guide, README, quickstart, changelog or curriculum that describes what was later changed

All from `reviews/2026-11/probes/p6_docs_describe_what_changed.py` unless said.

##### 6.4.1 README.md says there is no code (*misleads*)

"## Status — Design stage. There is no code yet: Ventoux is being built in Python, one layer at a
time, starting from the design documents below. Nothing here is ready to use." Observed:
`src/ventoux` holds 147 Python files, `ventoux` has 20 commands, and `CHANGELOG.md` describes
release 0.1.0. The same README's "Read" list calls the quickstart "written before the code" and
lists one guide of ten. This is the page a published package's readers see first.
Proposed fix: the status says layers 0 to 20 are built, 0.1.0 is not yet released, and links the
ten guides.

##### 6.4.2 QUICKSTART.md says "none of it is built yet", and tells the reader to run three commands that don't exist (*misleads*)

Banner: "**Design draft.** This page describes how Ventoux is meant to work; none of it is built
yet." Its case is built and is the repository's acceptance test (`tests/test_quickstart.py` runs
`examples/quickstart/cases/refund.py`; `.venv/bin/ventoux check --unchanged` in
`examples/quickstart` prints "✓ refund is unchanged: packages/refund/ is what cases/refund.py
writes", exit 0). But steps 1 and 4 run `ventoux init`, `ventoux dev` ("starts Ventoux in memory
with a local inbox at http://localhost:8090") and `ventoux start`, none of which is a command
(D79 moved the inbox after v1.0). `uv add ventoux` also assumes a published package (0.1.0 is
"not yet released").

```
QUICKSTART.md, the banner and the commands it tells the reader to run
  the document: 'none of it is built yet'; it runs `ventoux` ['check', 'dev', 'diff', 'import', 'init', 'map', 'start']
  observed:     commands that exist: ['check', 'diff', 'map']; that don't: ['dev', 'init', 'start']
```

Proposed fix: the banner says which steps run today (2, 3, 5 and the diff) and which wait for
what; step 4 is rewritten around what v1.0 ships (a test with `run_case`, or the trusted caller's
client functions), or marked as after v1.0.

##### 6.4.3 The cases guide gives the schema's `$id` as engine 2 (*misleads*)

`docs/guides/cases.md` line 2505: "`https://ventoux.dev/schema/engine-2/case.schema.json` is the
format engine version 2 reads." D77: "`ENGINE` is 3". The committed schema's `$id` is
`https://ventoux.dev/schema/engine-3/case.schema.json`; `suite.json` says `"engine": 3`; the
changelog says engine 3. A reader who validates against the guide's URL names a schema that is
not the one shipped. Proposed fix: the guide says engine 3 (or says "engine-N" and points to
`ventoux version`).

##### 6.4.4 Guides and docstrings still name "the Ventoux API" and "the inbox" as what the reader has (*minor*)

D79: "In v1.0 the trusted caller is the integrator's own service ... Ventoux ships no HTTP API and
no inbox in v1.0". D79 tells the reader how to read earlier *decisions* ("read 'the trusted
caller'"), but the guides are not decisions and were not changed: "the Ventoux API" appears 4
times in `cases.md` (for example line 1115, "The Ventoux API, the only caller allowed to send
events (brief, D19), states who sent it") and once in `plans.md`, 11 times in docstrings under
`src/ventoux` (for example `temporal/client.py` line 46), and `case-data.md` and `activities.md`
describe what "the inbox" does (uploads a file, asks a resolver) in the present tense. Only
`cases.md` line 2699 and the deployment guide say "the trusted caller". Proposed fix: one sentence
at the top of each guide, or a replacement of the term, as D79 did for the brief.

##### 6.4.5 Two rows of "Promises" tables name tests that no longer exist (*minor*)

CLAUDE.md: "each claim the note makes about behaviour ..., and the test that would fail if it
weren't true." Of 503 distinct tests named in the Promises tables of layers 16 to 20, two are not
defined anywhere in `tests/`:

- `docs/layers/18-lifecycle.md`: "A child ending without reporting fails the step: ... and within
  a day" names `test_after_a_switch_a_child_terminated_unheard_is_noticed_within_a_day`; the test
  is now `test_after_a_switch_a_child_terminated_unheard_is_noticed_at_the_next_check`
  (`fix-child-switch-clock.md`).
- `docs/layers/20-deployment.md`: "pydantic is bounded below the minor after the one the hashes
  were made with" names `test_pydantic_is_bounded_to_the_minor_version_the_hashes_were_made_with`;
  D83 changed the bound and the test is `test_pydantic_is_bounded_below_its_next_major_only`. That
  row's promise itself is no longer true of `pyproject.toml` (`pydantic>=2.13.5,<3`).

Proposed fix: a dated line under each table naming the test that replaced it (and, for layer 20,
that D83 replaced the promise).

#### 6.5 docs/LEARNING.md

Exists (2,292 lines), untouched (`git status --short` shows nothing outside `reviews/`), not
quoted and not answered anywhere in this pass.

#### 6.6 The two scans: personal details and AI model names; dependency licences

##### 6.6.1 Commit messages on `main` name AI model versions, and carry session links (*minor*; the review's own rule, not a decision of the brief)

Of the 574 commits on `main`, 464 carry a `Co-Authored-By` line, 457 of them naming a model
version, and 501 carry a link to a coding session. Commit history can't be changed without
rewriting it, which the project's rules forbid, so this is recorded for whoever decides how the
repository is shared: a squashed export, or a fresh history at v1.0, would be the two ways. The
review's own commits on `review-2026-11` carry neither line.

Proof (`uv run python reviews/2026-11/probes/p6_personal_and_model_names.py`, at `3edb471`'s
history):

```
tracked files naming an AI product or model (the file name CLAUDE.md apart):
  docs/layers/15-authoring.md: 2
  docs/layers/fix-flaky-temporal.md: 1
commits on main: 574
  with a Co-Authored-By line: 464, of which naming a model version: 457
  with a session link: 501
  distinct author identities: 3; commits under an address that isn't a no-reply one: 54
LICENSE names a copyright holder: yes
RESULT: BROKEN - 3 mentions in files, 457 commit messages naming a model version, 54 commits under a personal address
```

##### 6.6.2 Three mentions of an AI coding product in tracked files (*minor*)

`docs/layers/15-authoring.md` twice names an assistant's API reference as where the SDK's current
interface would be checked, and `docs/layers/fix-flaky-temporal.md` once names a vendor's cloud
containers as where a test failed. Neither is a model's name, and the file name `CLAUDE.md` and
the provider D62 chooses (named in the brief, the code and `pyproject.toml`'s extra) are the
project's own decisions, not counted. Proposed: reword the three lines to name what was done
("the SDK's reference", "a container without IPv6"), in a pull request of the maintainer's.
Same probe as 6.1.

##### 6.6.3 Personal details: commit authorship and the licence's copyright line (*minor*)

Fifty-four commits on `main` are authored under an address that isn't a no-reply one, and the
commit authors and `LICENSE`'s copyright line name a person. A licence must name its holder, so
that line is as it should be; the addresses in history are the same question as 6.1. No email
address, private path or employer was found in any tracked file: the addresses in the guides are
`example.com` and `evil.example`, and the two `/home/...` paths are CI's runner cache and a
session's checkout path in two layer notes (`docs/layers/11-rules.md`, `12-research.md`), which
name no person. Same probe as 6.1.

### What held

- **Licences** (`p6_licences.py`, by the lead reviewer): all 39 distributions `uv sync --locked`
  installs declare a permissive licence, compatible with the project's MIT. The three runtime
  dependencies are MIT (`pydantic`, `temporalio`) and Apache-2.0 or BSD-3-Clause (`cryptography`);
  the optional `anthropic` extra is MIT; the only weak-copyleft one is `pathspec` (MPL 2.0), a
  development-only dependency the wheel never carries. Declared metadata only: no licence text
  was read.
- **The version triple agrees.** `ENGINE = 3` (`src/ventoux/case/engine.py`), both schemas' `$id`
  under `engine-3`, `suite.json` `"engine": 3`, `ventoux version` says `0.1.0` / `engine 3`,
  `pyproject.toml` `version = "0.1.0"`, `CHANGELOG.md` "0.1.0 (not yet released) ... Engine
  version 3". D60's "The engine stays at version 2" is a dated note about 14e, and D77 moves it
  with the `$id`, as D60 says it must. (Commands in the session; `p6_docs_describe_what_changed.py`
  check 7 prints the `$id` and `ENGINE`.)
- **pydantic's bound.** D82's bullet says `<2.14`, its dated amendment by D83 says `<3`;
  `pyproject.toml` has `pydantic>=2.13.5,<3`, `uv.lock` resolves 2.14.3, inside the bound; the
  test `test_pydantic_is_bounded_below_its_next_major_only` passes.
- **Schemas' place.** D60 and D4 say `schema/` at the root; D82 moves them to
  `src/ventoux/schema/`, saying so. No guide, README or CLAUDE.md names the old place
  (grep; `schema/` at the root does not exist).
- **D59:** "Every command that reads contracts or roles takes it: `check`, `release`, `summary`,
  `diff`, `map`, `notes`, `simulate`, `promises` and `hashes`": each one's `--help` shows
  `--catalog` (so do `draft` and `draft-sheet`).
- **D63:** `ventoux draft --help` says `--rounds ROUNDS  at most this many, 1 to 5 (3)`.
- **D7 as amended by D58:** no guide, README or quickstart uses `unless=` or `only_if=`.
- **D21:** "sink policy" appears exactly once in the guides, in the activities guide (line 124);
  zero times in `src/ventoux`.
- **Guides' printed outputs:** `ventoux map examples/packages/refund` (48 lines), `ventoux
  simulate examples/refund/stories/nobody-reviews.json` (44 lines) and the first `ventoux release`
  line with its digest `89420f53b3d3` are, line for line, what the commands print
  (`p6_guides_printed_output.py`).
- **Relative links and paths:** all 13 relative Markdown links in the README files, changelog,
  quickstart, curriculum and guides resolve (`p6_relative_links.py`, HELD). Every backticked
  repository path in those files and CLAUDE.md exists, except `tests/test_refund.py` (a file the
  quickstart tells the reader to create) and the curriculum's "Reference" paths, which point into
  the prototype by design.
- **CLAUDE.md, "Tracer code is temporary":** no `# TRACER:` marker remains in `src/`,
  `examples/` or `scripts/` (only `tests/test_tracer.py`, which tests the rule).
- **CLAUDE.md, strict typing and lint:** `uv run mypy` gives "Success: no issues found in 286
  source files"; `uv run ruff check --exclude reviews` "All checks passed!"; `uv run ruff format
  --check --exclude reviews` "291 files already formatted".
- **CLAUDE.md, "Decisions in the brief are never renumbered or rewritten":** across the 45 commits
  on main's first-parent line that touch the brief, no decision's heading changed and no sentence
  of a decision that had reached main was later removed or reworded (`p6_decisions_rewritten.py`,
  HELD, all 83 decisions). A second pass over all 69 non-merge commits found 21 rewordings, each
  inside the pull request that introduced the text, before it reached main (the brief's own
  "before D25 was merged" practice).
- **CLAUDE.md, citations:** of 2,055 "(brief, Dn)" citations in `src/ventoux`, every number from
  D1 to D83 that is cited exists; 45 drawn at random were read against their decision and none
  names a decision about something else.
- **Promises tables, layers 16 to 20:** 552 rows name 503 distinct tests; 501 exist. Ten drawn at
  random, plus the pydantic one, were run: `11 passed`. Two were read for whether they would fail
  if the promise weren't true (`test_the_committed_suite_names_the_engine_it_describes` asserts
  `COMMITTED.engine == ENGINE`; `test_a_carried_date_that_isnt_a_day_is_refused` changes the
  carried value and expects the refusal's exact message): both would.
- **Secrets in tracked files** (`p6_secrets_in_tracked_files.py`, HELD; 592 project files, counts
  and names only): no private-key or certificate block with a body, no provider-style key, no
  cloud or forge token, no authorization header value. Three `BEGIN PRIVATE KEY` markers with no
  body (`tests/doctor_broken.py`, `tests/test_connecting.py`, `tests/test_doctor.py`) and one
  token-shaped constant (`tests/test_vault_keys.py`) are made-up values tests search for where a
  secret must never appear. The one recording (`tests/recordings/advisor-goodwill.json`) holds
  `provider`, `request.system`, `request.messages` and `answer` only: no key, no header (D62).
  The 33 `tests/histories/*.keys.json` files hold 32 development keys for the development
  provider and 2 entries marked destroyed: they let the committed histories, sealed under those
  keys, replay. See "Unproven" for what the brief says of them.

### Unproven

- **Committed fixture keys are nowhere said to be acceptable.** D31 and D82 were searched for
  `keys.json`, "fixture key" and "development key": D82 only keeps a key file out of the wheel;
  only `docs/layers/20-deployment.md` mentions `keys.json` (the wheel's check). The keys protect
  nothing but test fixtures, so this is a gap in what is written, not a leak; a sentence in the
  deployment guide or D31 would close it. Not a finding because no text promises the contrary.
- **`renamed()` in `src/ventoux/case/diff.py` cites "(brief, D53)"** for "a rename, never judged"
  in the semantic diff. D53 is about a migration's renames; the diff is D55, and the word
  "rename" does not occur in D55's text (grep). I did not read D55 in full, so I can't say the
  rule is unrecorded or the number wrong.
- **The 18-lifecycle promise "within a day"** after a switch: the renamed test says "at the next
  check". I did not run it or read `fix-child-switch-clock.md` to see whether the bound itself
  changed or only the name.
- **README-draft.md** is described by the README as "It still describes the TypeScript
  prototype", yet it holds v1.0 checklist lines written after D79 (lines 393 to 401). Not read in
  full.

### Unchecked

- **Most of the decision-by-decision list in the task**, for lack of budget after the
  interruption: D22's identifier spelling, D27's key format, D33/D44 ages, D47 `count` readings,
  D50 exit codes and file names, D51's report wording, D55/D56 escaping, D62's key and base URL,
  D64's six parts, D66, D68, D73, D77's bounds, D78's name encoding and timeout, D80's
  `ISSUE_CODES` and `refused_first`, D81's exit codes and rule names against the deployment guide,
  D82's wheel contents and `public.json` rule, D83's writer refusals. None was run. Several are
  the subject of other passes.
- **Decisions D35 to D58, D61 to D73, D75, D76, D78** were not read, only searched; so
  contradictions between them (heading 2) are checked only for the candidates above.
- **Guides other than the blocks run:** `cases.md` was not read by section; history lines quoted
  in guides were not compared with a run, except the `simulate` story. `releases.md`'s second and
  third `release` outputs, its `activate`, `environment check`, `retire`, `diff` and `summary`
  blocks, the deployment guide's `doctor` block and `plans.md`'s `draft` blocks were not re-run
  (several need a Temporal server or uncommitted input folders).
- **BRIEF's non-negotiables against CLAUDE.md's**, line by line: read once, no contradiction seen
  (CLAUDE.md spells `importlib`/`pickle` where the brief says "import or unpickle"), not probed.
- **A note for the lead, not a project finding:** `uv run ruff check` and `uv run ruff format
  --check` exactly as CI runs them (no `--exclude`) fail at this commit because of files under
  `reviews/2026-11/probes/` ("Found 50 errors", "30 files would be reformatted"), and mypy's
  `files` list doesn't include `reviews/`. If the review branch is merged as it is, CI's lint job
  fails; either exclude `reviews/` in `pyproject.toml` (a project change, the maintainer's) or
  format the probes.


---

## Pass 6, second part: each decision's checkable claims, run

Probes ran at `b464f3f` on branch `review-2026-11` (the first runs at `cf916d8`; source `3edb471`;
nothing under `src/`, `tests/`, `docs/` or `examples/` differs from it). Each probe is run from the
repository root with `uv run python reviews/2026-11/probes/<name>.py`, prints a table
"decision | the brief's claim | what a run shows | agrees?" and ends with a `RESULT:` line.

Scope, said plainly: 168 claims of 40 decisions were run in eight probes. Read in full for this
pass: D20, D22, D23, D27, D33, D41, D44, D46, D47, D50, D51, D52, D55 (its head and its
amendments), D56, D57, D59, D61 to D64, D66 to D74 (D74's first half), D76 to D78, D80 to D83.
Not read: D35 to D40, D42, D43, D45, D48, D49, D53, D54, D58, D60, D65, D75 (see "Unchecked").

The eight probes and their last lines:

| Probe | Result |
|---|---|
| `p6b_d20_d22_d23_expressions_identifiers_answer_order.py` | HELD, 24 of 24 |
| `p6b_d33_d44_d46_d47_ages_timers_patterns_counts.py` | HELD, 19 of 19 |
| `p6b_d50_d51_d55_d56_d57_d59_command_line.py` | HELD, 29 of 29 |
| `p6b_d52_d66_to_d74_wordings_and_bounds.py` | HELD, 26 of 26 |
| `p6b_d76_d77_d78_audit_and_vault.py` | BROKEN, 1 of 24 (finding 2) |
| `p6b_d61_to_d64_advisor_providers_drafts.py` | HELD, 18 of 18 |
| `p6b_d80_d81_d82_d83_suite_doctor_package_writer.py` | BROKEN, 1 of 39 (finding 1) |
| `p6b_non_negotiables_d27_d31_d41.py` | HELD, 9 of 9 |

### Findings

No guarantee of the engine was found broken at runtime in this pass. Two findings are documents
and a list that say something the code doesn't do; two are small.

#### 6b.1 The supported imports leave out `run_case` and every script helper the guides teach, and the test that should notice can't see them (*weakens one*)

`src/ventoux/public.json` lists two names under `ventoux.testing`: `check_workflow_contract` and
`run_plan`. The guides' Python blocks call `run_case` 20 times (`cases.md` 15, `case-data.md` 4,
`releases.md` 1), the quickstart imports it (`docs/QUICKSTART.md` line 149,
`from ventoux.testing import run_case`), and the guides also call the script helpers `propose`,
`retry`, `edit`, `skip`, `assign`, `claim`, `later` and `migrate`. None of them is in the list, so
by D82's own words each is "internal: importable, unsupported, free to change", and the test that
fails when a listed name disappears doesn't protect them.

The promise it touches, D82: "**The supported imports are a committed list,**
`src/ventoux/public.json`: the names the guides tell teams to import, the builder's `__all__`, and
the protocols a deployment implements. Everything else is internal: importable, unsupported, free
to change. A listed name that disappears fails a test, so removing one is a decision, as a contract
change is; a name a guide imports that the list doesn't hold fails too." And: "`ventoux.testing`
ships, for teams' tests."

Why nothing noticed: `tests/test_package.py::test_every_name_the_docs_import_is_supported` reads
only `from ventoux… import …` lines in the Python blocks of `README.md`, `docs/guides/*.md` and
`examples/**/*.py`. The guides use `run_case(` without ever showing its import, and the quickstart,
which does show it, is not one of the files the test reads. The test passes
(`uv run pytest -q -p no:cacheprovider tests/test_package.py -k 'docs_import or supported_name'`:
3 passed).

Proof (`b464f3f`):

```
$ uv run python reviews/2026-11/probes/p6b_d80_d81_d82_d83_suite_doctor_package_writer.py
D82 | 'a name a guide imports that the list doesn't hold fails too' (the import lines of the Python
  blocks of the README, the quickstart and the guides) | imported and not listed:
  ['ventoux.testing.run_case'] | yes   (the quickstart's line; the test doesn't read that file)
D82 | 'the names the guides tell teams to import'; ... | helpers of ventoux.testing the guides'
  Python blocks call and public.json doesn't list: {'assign': ['cases.md'], 'claim': ['cases.md'],
  'edit': ['cases.md'], 'later': ['case-data.md'], 'migrate': ['releases.md'], 'propose':
  ['cases.md'], 'retry': ['cases.md'], 'run_case': ['QUICKSTART.md', 'case-data.md', 'cases.md',
  'releases.md'], 'skip': ['cases.md']}; listed under ventoux.testing:
  ['check_workflow_contract', 'run_plan'] | NO
RESULT: BROKEN - D82: 'the names the guides tell teams to import'; ...
```

(The helper names are matched by name against what `ventoux.testing` defines; `claim` in
`cases.md` is called twice and may in one place be the guide's own name. `run_case` is not in
doubt.) Probe: `reviews/2026-11/probes/p6b_d80_d81_d82_d83_suite_doctor_package_writer.py`.

Proposed fix: list `run_case` and the script helpers the guides use under `ventoux.testing` (the
count moves from 73, so D82 or the deployment note that says 73 gains a dated line); have the
guides show the import once per page; and widen the test to the quickstart and to names a block
calls that `ventoux.testing` defines, so a guide can't teach a helper the list doesn't hold.

#### 6b.2 D76's own example of a record names a decision the engine doesn't put there (*misleads*)

D76, first bullet: "An answer that approves `pay` and so starts it is one record: `approved`,
`admitted`, `started`." D76, its dated line "*Changed while building 19a, before D76 was merged*":
"`admitted` is an approval asked; a start reads its condition, its approval's condition, then its
inputs." The two disagree, and the code follows the second: the approving answer's record holds
`approved`, `started`; `admitted` is in the record of the earlier act that had the approval asked.

Proof (`b464f3f`):

```
$ uv run python reviews/2026-11/probes/p6b_d76_d77_d78_audit_and_vault.py
D76 | 'An answer that approves pay and so starts it is one record: approved, admitted, started'
  (the same decision later: 'admitted is an approval asked') | the approving answer's decisions:
  ['approved', 'started']; `admitted` is in the record of the answer that had the approval asked:
  ['answered', 'admitted'] | NO
RESULT: BROKEN - D76: ...
```

Probe: `reviews/2026-11/probes/p6b_d76_d77_d78_audit_and_vault.py`. An auditor or an implementer
of a reader of the export who takes the example as the format expects a decision that never
comes. Proposed fix: decisions aren't rewritten, so a dated line on D76 saying the example reads
`approved`, `started` since the change before merge (and what the asking answer's record holds),
and the audit guide checked for the same example.

#### 6b.3 An age has no upper bound: a wait no workflow timer can hold is accepted when the definition is read (*minor*)

D44: "`after` is an age in D33's format (`30m`, `12h`, `1d`), at least a minute". The lower bound
is enforced; nothing bounds it above. An `sla` of `999999999999999999999999999999d` is read,
validated and run in memory (the run lists the timer as due in the year 2.7e27). The same wait
can't be written as the protobuf duration Temporal's SDK puts a workflow timer's wait into.

Proof (`b464f3f`):

```
$ uv run python reviews/2026-11/probes/p6b_d33_d44_d46_d47_ages_timers_patterns_counts.py
D44 | an age with no upper bound (asked: is one that no workflow timer can hold refused when read?)
  | 999999...d (30 digits): read: ok; the same wait as a protobuf duration: ValueError Value out of
  range: 86400000000000000000000000000000000 | yes
```

(The row doesn't count against the probe's result: D44 states no upper bound, so no quoted promise
is broken.) What the case workflow does when it meets such a timer on a server was not run; see
"Unproven". The standard it touches is CLAUDE.md's "Fail closed: anything the engine can't
evaluate or doesn't recognise is an error", here at the wrong moment: at the first timer of an
open case, not at `ventoux check`. Proposed fix: a decision giving an age a largest value (for
example the ten thousand years a protobuf duration holds, or far less), refused when read, with a
negative test; the same for `max_age` and a plan's `timeout`.

#### 6b.4 Three wordings the brief quotes are printed a little differently (*minor*)

None changes what is decided; each is a quotation a reader can't find verbatim.

- D55: "each change's verdict in fixed words (\"Looser:\", \"Stricter:\", \"Changed, not proven
  either way (read it as possibly looser):\")". The plain form prints the words, then the path,
  then the colon: `- **Looser** (`fields.order_id.visible_to`): seen by support -&gt; ...`
  (`p6b_d50_d51_d55_d56_d57_d59_command_line.py`, row "fixed words": 3 of 3 printed so, 0 of 3
  with the colon right after the words).
- D74: "closes the child ..., saying why (`closed by its parent: duplicate, by ana`)". The child's
  last two lines are `cancelled fix#1: closed by its parent: duplicate, by ana` and
  `closed: by its parent: duplicate, by ana` (`p6b_d52_d66_to_d74_wordings_and_bounds.py`).
- D50: "A digest equal to an existing release makes none (`same behaviour as refund 2`)". That
  sentence is printed only for a revert to an older release (`same behaviour as refund 1; nothing
  released`); the same package released again says `refund: nothing changed since release 1;
  nothing written`. Both exit 0 and write nothing (`p6b_d50_…command_line.py`).

Proposed fix: none needed in code; if the guides quote these, quote what is printed.

### What held

Each line names the probe that shows it. All ran at `b464f3f`.

- **D20** (`p6b_d20_d22_d23_…`): the code's operator list is the brief's plus `date` (D66), no
  more and no fewer; 25 unlisted operator names (`now`, `map`, `%`, `!!`, `today`, `max`, …) are
  each refused when read; `0.1 + 0.2 == 0.3` is true; `1 / 3` gives 34 threes and `2 / 3` ends in
  7 with the process's own decimal context set to 5 digits and rounding up, so no global default
  decides; a tie rounds to even both ways; division by zero is an `ExpressionError`; `and` with a
  first operand `false` and `or` with a first `true` still fail on a missing field; a default in
  `var`, `var` of the whole data, an `if` chain, a float, truthiness, and coercion in `==` and
  `cat` are refused; 32 levels read and 33 are refused (D60); the rendering is
  `review.outcome = "approve" and (a != 1 or not(approved_amount > 100))`.
- **D22**: the spelling rule reads 5 good and 14 bad identifiers as the brief says (capitals, a
  space, `:`, a leading `.`, `_`, `@`, `-`, an empty text, a trailing line break, an accented
  letter, a full-width letter, a digit of another script); a misspelled identifier is refused
  before a closed entry or an unknown outcome is looked at.
- **D23**: with several refusals applying at once they come in the brief's order: entry not open,
  then outcome not offered, then no role.
- **D33, D44** (`p6b_d33_d44_d46_d47_…`): a timer's age accepts `30m`, `12h`, `1d`, `1m`, `59m`,
  `01d` and refuses `1w`, `90s`, `60s`, `0m`, `0d`, `1.5h`, signs, spaces, capitals, an empty
  text, digits of another script, `1_0d` and a number. `max_age` refuses `0m` and `0d` too: the
  code's comment calls that "at least a minute (brief, D33)", a bound D33's text doesn't state
  (stricter, so no finding). Two timers due at one second fire in the order they were set, and
  both before an answer stamped at that second; set timers are listed with their due time in UTC.
- **D46**: a reminder expands to `remind_review_1d`, `_2d`, `_4d`; an `sla` keeps its own name;
  `1d` and `24h` together, a reminder on an activity step, a step named like an expanded rule, an
  entry that is neither a raw rule nor a pattern, and an entry with both `on` and `sla` are each
  refused when read.
- **D47**: `count` accepts 1, 2, 3 and refuses `"2"`, `2.0` (as a float, as an exact decimal and
  as the JSON text `2.0`), `true`, 0, -1 and null; the history and `waiting_for` wordings are
  exactly the brief's; a second answer by the same person is refused, `reject` included; one
  rejection ends the entry.
- **D50, D51, D57, D59** (`p6b_d50_…command_line.py`): no catalog named is refused; a
  `[tool.ventoux]` key nobody decided is refused, and the nine decided keys are accepted; no
  releases folder named is refused; `--commit` is required; `releases/refund/1.json`, then
  `1.wording-2.json`, then `2.json`; the record holds name, release, digest, commit, contracts,
  the package as written, the changed paths and its notes, with `method: 1`; an older release
  reworded is refused with exit 1; a record whose stored package no longer gives its digest is
  refused with exit 1; a missing folder is exit 2; a stray file in a package is exit 1; `ventoux
  notes` in both forms, `ventoux promises`, `ventoux hashes --lock … --before …` run. A released
  case's history begins `opened on refund 1, engine 3` (a scratch run, not a probe).
- **D55**: `ventoux diff` exits 0 whatever it found and 2 on a folder it can't read; the summary
  line counts not-proven with looser and says it before stricter (`7 may loosen (4 looser, 3 not
  proven), 1 stricter`).
- **D56**: a literal a definition writes holding `& < > \ ` * _ [ ] ~ # | !` and a line break is
  shown in the map with entities, a backslash before each listed character and the break as
  `\n`; no value starts a line. **D45**: `ventoux simulate` plays the four-eyes story.
- **D52, D69 to D74, D66, D68, D73** (`p6b_d52_d66_to_d74_…`): `case.change#1`; an edit to the
  value held, and a proposer approving their own request, are refused; `confirm, required,
  proposed by support`; `closed: duplicate, by ana; confirm not done`; a required step with a
  `when` is refused when read; `lee assigned review#1 to sam as support-lead` with and without
  `, from ana`; `confirm#1 assigned to ana by its rule`; only the holder answers, the refusal
  naming the holder and how to free the entry; a role that doesn't assign can't; a claim of a
  `count: 2` approval is refused; 100 records accepted and 101 refused; `draft_line.1#1` and
  `.2#1`; an item with an undeclared field refused; a field named `each` refused;
  `repair#1: case repair, open`; an attachment ID of 200 characters is taken and one of 201
  refused without quoting it; every listed wrong date form (and six more) is refused at the
  opening, and `0001-01-01` and `9999-12-31` are taken; `string` of a date gives `2026-10-31`;
  `+` and `-` on dates are refused by the check; a `datetime` in a date field is an error at
  runtime and refused by the builder; `today` is not an operator.
- **D76, D77, D78** (`p6b_d76_d77_d78_…`): the code's list of decision kinds is exactly D76's 17,
  and every kind six varied runs emitted is in it; records are numbered from 1; the sealed part
  is `audit/claim-7/1/act/values/national_id` and the value is nowhere in clear, even when the
  definition's sensitive fields aren't given to the export; `FileAudit` refuses a gap and other
  content, accepts the same record again, keeps nothing of a call with one refused record, and
  writes one `.jsonl` per stream; the retry policy the case workflow passes to the export
  activity has 10 attempts and a longest wait of 5 minutes, and the bound is 262144 bytes (read
  from `CaseWorkflow.export_retries` and `audit_bound`, and the call at
  `temporal/cases.py` lines 887 to 892; not run on a server); `refund-A-1001` is
  `ventoux-refund-_41-1001`; `_`, `/`, `.` and a two-byte letter are escaped byte by byte; an
  empty ID is refused; a name of 128 characters is taken and 129 refused; eleven addresses are
  read as D78 says (`http://localhost.evil.example`, `http://localhost@evil.example`,
  `http://127.0.0.2`, `ftp://localhost` and an address with no scheme refused); the timeout is
  10; the key type is `aes256-gcm96`; the mark's path is
  `/v1/secret/data/ventoux/forgotten/<name>`; an empty mount is refused; a request the recording
  doesn't hold is refused, naming it.
- **D61 to D64** (`p6b_d61_to_d64_…`, recordings only): 4 answer forms are taken and 15 refused
  (prose, a list, a second key, a number, a list as the name, prose around a block, two blocks,
  two objects, the key twice, another key's case, an empty answer, `{}`, a name with a space, an
  empty name); the label is "Suggested by the step advisor (untrusted:llm): goodwill"; with
  `ANTHROPIC_BASE_URL` set to another host the client the provider builds still asks
  `https://api.anthropic.com` (the SDK object's `base_url`, read; no request sent, no real key);
  `ventoux advise` and `ventoux draft` exit 2 with no model named, and with a model and no key
  say `ANTHROPIC_API_KEY is not set`; `draft` exits 1 abandoned with only the record written, 0
  drafted with both files, and refuses when either file is already there; the record holds the
  goal, who asked, the provider, each round's answer and problems, the verdict, the reason and
  `draft_sha256`; the sheet's six parts come in D64's order and hold none of the model's answer;
  one space added to the draft, a record without `draft_sha256`, a verdict of `abandoned`, and a
  drafts folder given as the package are each refused with exit 2; `ventoux release` refuses a
  drafts folder.
- **D80 to D83** (`p6b_d80_d81_d82_d83_…`): each of the 62 issue codes has an entry expecting it
  or is one of the three under `refused_first`, which are exactly `UNKNOWN_PLAN`, `UNKNOWN_CASE`
  and `NESTED_CASE`; an issue with an unlisted code is refused when made; the 25 definitions
  under `examples/` are each byte for byte in the suite; `ventoux conformance --unchanged` exits
  0, `--export DIR` writes the package's 90 files and refuses a folder already there; doctor
  exits 1 when a rule fails (no `pyproject.toml`: every rule still runs), 2 on a `pyproject.toml`
  that isn't TOML, and with no Temporal reachable gives 3 FAILED and 14 unchecked lines; its 18
  rules are named `area.rule`; the deployment guide's table lists the same 18 in the same order,
  and the test that keeps them equal is an `==` of the two lists, so any difference fails it;
  `--identity` says "(else operator)" and the address "localhost:7233"; `public.json` holds 73
  names in 22 modules, each importable, and the builder's `__all__` is exactly the names under
  `ventoux`; the only extra is `anthropic`; a wheel built to a temporary folder passes
  `scripts/check_wheel.py` and holds 272 files under `ventoux/` and its `.dist-info` only; a
  description, a title, examples, an alias, three kinds of constraint, a default other than
  `None`, and a `model_config` (set, strict, or inherited) are each refused when the contract is
  made, as an input and as an output. A model's docstring is accepted and written as
  `description`, as pydantic 2.13 wrote it.
- **Non-negotiables** (`p6b_non_negotiables_d27_d31_d41.py`): the 90 modules of `core` and `case`
  import in a fresh interpreter with no `temporalio`, `anthropic`, `httpx` or `openai` module
  loaded; importing the case, plan and forget workflows and the worker loads no `anthropic` and no
  `ventoux.authoring`; `eval(`, `exec(`, `compile(`, `importlib`, `__import__`, `pickle`,
  `marshal`, `yaml.load`, `subprocess`, `os.system` and `runpy` occur on 7 lines of `src/`, in
  four files, none in `core`, `case`, `temporal` or `authoring`: `ventoux/__init__.py` imports
  the fixed module `ventoux.tooling.builder`; `tooling/deployment.py` imports the catalog, key
  service and audit store by the name in configuration (D59, D81); `tooling/check.py` runs the
  builder files named on the command line or found in the configured `cases` folder (D59);
  `tooling/cli.py` uses `importlib.metadata` for the version. Nothing read from a definition, a
  story, a draft or a record reaches any of them. **D31**: `start_case` and `start_plan` refuse
  an ID with `/` before a key is made or the client is asked anything. **D41**: an event sent to
  a closing case is refused, with a history line and a flag. **D27**: the case's key is built as
  `<workflow ID>/<first run ID>` (read in `temporal/cases.py` line 723; not run on a server).

### Unproven

- **What a case does on Temporal with the unbounded age of finding 3.** The definition is read
  and the protobuf duration refuses the wait; whether the workflow task then fails and is retried
  for ever, or the SDK refuses earlier, was not run on a server.
- **`ventoux diff` compares a package that `ventoux release` would refuse.** With a role nobody
  registered in the new package, `diff` exits 0 and prints verdicts (the command-line probe's row
  "1 when a package or the diff is refused"). D55 says "1 when a package or the diff is refused"
  without saying a package is validated first, and the summary's validation is a separate, dated
  amendment, so this is not shown to contradict the brief. I did not run `release` on that
  package to show it is refused there.
- **`suite.json` holds no `changes` key** (its keys are `engine`, `entries`, `refused_first`).
  D80: "the suite's `changes` list gains a line". An empty list left out is the likely reading;
  `--since` was not run to see how a base with no list and a head with one compare.
- **A computed field on a contract's output model is accepted** when the contract is made, and
  the writer leaves it out, as pydantic's default rendering does. Whether such a field can reach
  the case file was not followed (the runtime reads `model_fields` only, by a reading of
  `case/runtime.py` lines 1262 to 1271), so no claim.
- **D59 says `ventoux check` runs the builder files "in its own process".** The code runs them
  with `runpy` inside the command's process (`tooling/check.py` line 92). If "its own process"
  means the command's, they agree; if it means a child process, they don't. The sentence can be
  read both ways.

### Unchecked

- **Decisions not read in this pass:** D35 to D40, D42, D43, D45 (beyond `simulate` running),
  D48, D49, D53, D54, D58, D60 (beyond the 32 levels), D65, D75 and D79. D53's "forward only" and
  D54's registry were not run.
- **Anything needing a Temporal server:** D27's key seen in a real run and across a
  continue-as-new, D41's `EventRefused` at the client for a closed case, D44's one workflow
  timer, D77's retries and the 256 KB hold as a running case meets them (only the constants and
  the call that passes them were read), D75, D81's live rules and `--identity`.
- **D62 with a transport:** the provider's address was read from the SDK client it builds, with
  `ANTHROPIC_BASE_URL` set; no request was sent through a fake transport, and no key was used.
- **D78 against a Vault:** only the recording transport; the binary was not fetched.
- **D64's escaping of the goal** and D56's code-span fencing were not given hostile input beyond
  the one literal in the map.
- **D57's hash check with a contract changed in place** (the path-by-path lines) was not
  produced: the run compared the catalog with its own promises, which match.
- **Contradictions between decisions** were looked for only in the decisions read above. Beyond
  finding 2, the ones met are already recorded by the brief itself (D67's "Replay" corrected by
  D68; D82's pydantic bound changed by D83) or are in the lead's known list.


---

## After the six passes: the in-memory findings, run on a Temporal worker

Ran at `ecef3d1` (branch `review-2026-11`; source is `3edb471`). Every case below ran as a
`ventoux.case` workflow on Temporal's local time-skipping test server, served by `case_worker`
with the supported converter (`data_converter`, one key per case) and a `FileAudit` store, through
the harness an earlier pass wrote (`p1c_harness.py`). A plan step ran as a real `ventoux.plan`
child workflow, a case step's child as a real `ventoux.case` child workflow (D75). The definitions,
people and values are the in-memory probes' own: each `p7a_*` probe imports the `p1a_*`, `p1b_*` or
`p3_*` probe it carries over and reuses its definitions.

Answer in one line: **all eleven findings reproduce on Temporal, with the same wrong outcome, and
nothing on the Temporal side stops any of them.** One is worse there (3.3: the sensitive value is
also in clear in the raw workflow history). No stuck workflow task appeared anywhere.

| Finding | On Temporal | What was read there | Probe |
|---|---|---|---|
| 1a.1 repeated step drops steering | reproduced | report; what the worker was given | `p7a_trust_on_temporal.py` |
| 1a.2 case step drops steering | reproduced | parent's and child workflow's reports; worker | `p7a_trust_on_temporal.py` |
| 1a.3 child's declared untrusted mark dropped | reproduced | both reports; worker | `p7a_trust_on_temporal.py` |
| 1a.4 `max_age` refresh launders steering | reproduced (three days skipped) | report; worker | `p7a_trust_on_temporal.py` |
| 1b.1 plan wait's answerer approves | reproduced | report; worker | `p7a_people_on_temporal.py` |
| 1b.2 change request in child by parent's opener or step's proposer | reproduced (all four) | child workflow's report | `p7a_people_on_temporal.py` |
| 1b.3 child's reported field named `outcome` | reproduced | report; `view` query; `advisor_view` query | `p7a_people_on_temporal.py` |
| 1b.5 hidden value into and out of a child | reproduced | `view` query as `support`, on each workflow | `p7a_people_on_temporal.py` |
| 1b.6 parent's own close, or its rule's stop, cancels the child's failed run | reproduced (both) | both reports | `p7a_people_on_temporal.py` |
| 1b.8 a `when`'s decider approves inside a plan or child | reproduced (both) | reports; worker | `p7a_people_on_temporal.py` |
| 3.3 validator's message with a sensitive value in clear | reproduced, and worse | report; raw history bytes; audit file | `p7a_validator_message_on_temporal.py` |

### Findings

These are not new findings: each is the report's finding, now proven on Temporal too. The
severity, the promise quoted and the proposed fix stay as REPORT.md states them for each. What is
added is the proof on Temporal, and for 3.3 one more place.

#### The four trust findings reproduce on Temporal (1a.1 to 1a.4; breaks a promise, as reported)

```
$ uv run python reviews/2026-11/probes/p7a_trust_on_temporal.py      (about 12 s; ran three times, same result)
1a.1 on Temporal: REPRODUCED - the plain step is refused (untrusted:customer) and nothing reaches the worker; repeated, the worker really ran letters.draft@2 2 times with to_customer 'a@example.com', and: an untrusted `when` chose a trusted-only send; a rule on its start reached settled; a step requiring it reached settled; a repeated step requiring a steered wait sent
1a.2 on Temporal: REPRODUCED - as a plan step nothing is reached and the plan stops; as a case step the parent reached ['began', 'written', 'followed'], the child workflow's letter reached the worker ('a@example.com'), the value a rule set on its start keeps untrusted:customer: False ('mark#1 on started write: setting seen, from system:opener'; as a plan step '... from system:opener, untrusted:customer'), and the timer on the rule-started step's start reached began: True
1a.3 on Temporal: REPRODUCED - alone, summary is from system:opener, untrusted:llm and the letter is refused; as the child workflow no line names untrusted:llm, the child reached urgent (True), the worker ran its letter with to_customer 'urgent' (...), and the parent sent the reported value on to the worker (True; 'scheduled reply#1: letters.draft@2 (to_customer from case:intake, system:opener; ...')
1a.4 on Temporal: REPRODUCED - answered at once, and with no text, confirm#1 fails and the worker is given nothing; after three skipped days check#2 runs clean, the case reached ['began', 'checked', 'confirmed'] and the worker ran letters.draft@2 with to_customer 'delivered'
RESULT: BROKEN - 4 of 4 findings reproduce on Temporal: 1a.1, 1a.2, 1a.3, 1a.4
```

What the run adds to the in-memory proof:
- The trusted-only input really reaches the activity worker. The probe wraps each fake and records
  what it was called with, by the workflow that scheduled it: in each control the worker is given
  nothing, in each attack it is called.
- 1a.2 and 1a.3 hold across a real child workflow. `child_start` hands the child each opening
  field's sources (`ParentStart`), and the child's own history line reads `to_customer from
  system:opener`: neither the parent's steering nor the child's own declared `untrusted:llm` is
  there.
- 1a.4 needs time to pass: `environment.sleep` of three days on the time-skipping server gives
  `refreshing check.status for confirm: obtained 3 days ago, at most 1 day`, then a clean
  `check#2`, exactly as in memory.
- The history lines are word for word the in-memory ones, apart from the idempotency keys
  (`<case ID>/<run ID>/<entry>`) and the child's `opened on write 1, engine 3`.

#### The six findings about people reproduce on Temporal (1b.1, 1b.2, 1b.3, 1b.5, 1b.6, 1b.8; as reported)

```
$ uv run python reviews/2026-11/probes/p7a_people_on_temporal.py     (about 40 s; ran twice, same result)
1b.1 on Temporal: REPRODUCED - as a task, sam's approval of pay is refused and nothing is paid; with the decision in the plan child workflow, sam's signal answered decide#1, sam approved pay.approval#1 and the worker ran payments.refund@2 (250)
1b.2 on Temporal: REPRODUCED - in one case the opener's approval is refused; in the child workflow these were approved and applied: an edit, approved by the parent's opener; a skip of a failed run, approved by the parent's opener; an edit, approved by the case step's proposer; a skip, approved by the case step's proposer
1b.3 on Temporal: REPRODUCED - the child workflow closed by itself ('closed: nothing left to do'), yet the parent's repair.outcome is the text sam typed (from ['case:repair', 'person:sam']), so pay (when repair.outcome == 'done') never starts and the worker is given no payment; the step advisor's view holds the text: True
1b.5 on Temporal: REPRODUCED - by the `view` query on each workflow: support, who may not see fraud_score, reads 77 as the child's `score`; support, who may not see the child's margin, reads 41 as the parent's repair.margin
1b.6 on Temporal: REPRODUCED - in one case the failed pay#1 keeps the case open; in a child workflow the failed parts#1 (payments.refund@2, tried 5 times by the worker, each unreachable) was cancelled and the child closed with no person and nothing needing attention, by: the parent's closes_when (flags: none); a parent's rule's stop (flags: none)
1b.8 on Temporal: REPRODUCED - as a call step sam's approval is refused and nothing is paid; wrapped in a plan step and in a case step sam's approval is taken in the child workflow and the worker ran payments.refund@2
RESULT: BROKEN - 6 of 6 findings reproduce on Temporal: 1b.1, 1b.2, 1b.3, 1b.5, 1b.6, 1b.8
```

What the run adds:
- Each control is refused on Temporal as in memory, as a recorded line (a signal can't raise):
  `refused sam's answer approve to pay.approval#1: sam set review.outcome, which decides whether
  pay runs, so cannot approve it`; `refused lee's answer approve to case.change#1: lee opened the
  case, so cannot approve a change to it`.
- People answered by the signals the Ventoux API would send (`answer`, `propose`,
  `propose_change`, `send_event`); a plan's wait by the plan workflow's `answer` signal to
  `<case ID>/<entry>`, as the repository's own tests do.
- 1b.5 was read with the `view` query by role, as asked: on the parent, `Fraud score: hidden
  (needs fraud)`; on the child workflow, `Score given by the parent: 77, from system:opener`; and
  the parent's values for `support` hold `repair.margin` 41 while the child says `Our margin:
  hidden (needs fraud)`.
- 1b.3's second half was read with the `advisor_view` query: its answer holds the person's text.
- 1b.6: the failure is a real one on Temporal (the worker called five times, the contract's retry
  policy, each raising `ConnectionError`; time skipped between tries). The child's report said
  `needs attention ['parts#1: payments.refund@2 failed with ConnectionError: ‹sensitive›']`
  before the parent acted, and after it `cancelled parts#1: closed by its parent: reviewed
  reached`, status closed, nothing needing attention, no flag on either case.

#### 7a.3.3 reproduces on Temporal, and there the value is also in clear in the raw workflow history (breaks a promise)

The validator's message is in clear in the case's report (`history` and `needs_attention`) and in
the audit store's file, as in memory. On Temporal it is in one more place: the raw history of the
case's workflow, as the input of the `ventoux.audit.append` activity that exports the record.
For the sensitive field's value this is the only place it crosses Temporal in clear: in the
comparison case (the activity's own failure quoting the same national ID) the value is nowhere in
the raw history, since the opening value and the activity's input cross sealed with the case's key
and the failure is not kept.

Promises touched, as the report quotes them. D30: "**A refusal or a failure names the field and
the kind of value, never the value**". D31: "everyone reads `‹sensitive›` wherever a value would be
written: history lines, refusals, failures".

```
$ uv run python reviews/2026-11/probes/p7a_validator_message_on_temporal.py     (about 5 s)
=== an input refused by the contract's validator (the sensitive field's value) (case val-input)
    last line of the report's history: look#1 failed: people.lookup@1 doesn't take these inputs: national_id: Value error, '<THE NATIONAL ID>' is not a national ID: write it without spaces
    in clear in the case's report: ['history', 'needs_attention']
    in clear in the raw workflow history: ['marker in val-input run 1'] | ['event 7 ACTIVITY_TASK_SCHEDULED ventoux.audit.append']
    in clear in the audit store's files: ['val-input.jsonl'] (records not yet written: 0)
    the activity worker was called 0 times
=== an output refused by the contract's validator (what the system gave) (case val-output)
    last line of the report's history: look#1 failed: people.status@1 gave an output its contract doesn't declare: status: Value error, '<WHAT THE SYSTEM GAVE>' is not a status
    in clear in the case's report: ['history', 'needs_attention']
    in clear in the raw workflow history: ['marker in val-output run 1'] | ['event 13 ACTIVITY_TASK_COMPLETED', 'event 22 ACTIVITY_TASK_SCHEDULED ventoux.audit.append']
    in clear in the audit store's files: ['val-output.jsonl'] (records not yet written: 0)
=== comparison: the activity's own failure quoting the sensitive value (case val-fails)
    last line of the report's history: look#1 failed: people.status@1 failed with RuntimeError: ‹sensitive›
    in clear in the case's report: nowhere
    in clear in the raw workflow history: nowhere | no event
    in clear in the audit store's files: nowhere (records not yet written: 0)
3.3 on Temporal: REPRODUCED - ...
RESULT: BROKEN - 1 of 1 findings reproduce on Temporal: 3.3
```

Reading it with care:
- `val-input` is the strong case: `national_id` is declared `sensitive`, and its value is in the
  report, the history bytes (event 7) and the audit file.
- `val-output`: event 13 is the activity's own completed result, which the system gave and which
  no field declares sensitive; I don't count that event. Event 22 (the export of the record whose
  reason quotes it) and the report and audit file are the finding.
- The case needed its own case workflow class naming the probe's catalog
  (`p7a_workflows.ValidatedCases`), as a deployment's does: the development catalog has no
  contract with a validator. So this is "on Temporal with a deployment's own catalog", not with
  the development worker's catalog.

Proposed fix: the report's (never copy a validator's text into a reason; name the field and the
kind of failure). Nothing more is needed for the history: once the reason carries no value, the
export's input carries none.

### What held

- Nothing on the Temporal side stops, changes or adds to any of the eleven: the case workflow
  decides as `run_case` does, line for line. No workflow task failed or stuck in any of the runs
  (each scenario is bounded, and would have said so).
- Both controls that the in-memory probes rely on hold on Temporal too (a plain step, a plan step,
  a task, a single case: each refused, and the worker given nothing), shown by the same three
  probes.
- An activity's own failure quoting a sensitive value reads `‹sensitive›` in the report and the
  audit file, and the value is nowhere in the raw history
  (`p7a_validator_message_on_temporal.py`, case `val-fails`).

### Differences between the two runtimes met on the way (not findings of this pass)

- A number given at the opening as the integer `250`, which `run_case` takes in memory, makes the
  case workflow's start fail on Temporal (`WORKFLOW_EXECUTION_FAILED`, message "Encoded failure");
  given as `Decimal(250)` the same case opens (scratch run, not a probe: two cases of
  `p1b_plan_wait_answerer_approves.with_task()`, one with each). The repository's Temporal tests
  give `Decimal`. The probes give exact decimals for that reason, and say so in a comment. While
  it lasted, `report` on the failed start answered a blank open report (`status='open'`,
  `history=[]`), which is the report's existing finding from `p1c_report_of_refused_opening.py`.
  I did not look for which rule refuses the integer; a team moving a test's file from `run_case`
  to `start_case` would meet it.
- The `view` query hides every field of a case whose definition names no role at all (`Summary:
  hidden (needs )`), so the 1a probes' sources were read from the report's history lines
  (`to_customer from system:opener`), not from `view`. That is fail closed, and the same in
  memory, as far as I can tell; not checked further.
- A draft whose check has errors (`INPUT_POLICY`, `UNTRUSTED_TRIGGER`) opens on Temporal as it
  runs in memory: `start_case` on a definition does not run the catalog check. The in-memory
  probes already show which findings the check flags and which it is silent on; unchanged here.

### Unproven

- That the validator's message stays readable in the raw history once the case is forgotten (its
  key destroyed). It is plain text in an activity's input, so I expect it to, as the report's
  1c finding on option checks shows for their inputs, but I did not run a forget on `val-input`.

### Unchecked

- A real Temporal cluster, and the development worker started from the command line: everything
  ran on the local time-skipping test server with a worker built by `case_worker` in the probe's
  process.
- Replay of the recorded histories of these cases (another pass covers replay).
- 1b.4, 1b.7 and 1b.9 to 1b.11, and the other pass 1a and pass 3 findings: not in this task's list.

### Probes

- `reviews/2026-11/probes/p7a_trust_on_temporal.py` (1a.1 to 1a.4)
- `reviews/2026-11/probes/p7a_people_on_temporal.py` (1b.1, 1b.2, 1b.3, 1b.5, 1b.6, 1b.8; one
  finding alone: add its number, e.g. `... p7a_people_on_temporal.py 1b.6`)
- `reviews/2026-11/probes/p7a_validator_message_on_temporal.py` (3.3)
- `reviews/2026-11/probes/p7a_harness.py`, `p7a_workflows.py`: helpers, not probes.

Reached past the supported names for: `ventoux.testing` (development catalog, workflows, fakes,
`release_of`), the tests' server harness through `p1c_harness.py`, the plan workflow's `answer`
signal (`ventoux.temporal.workflow.Sent`), `Catalog`, `FileAudit`, and `activity.info()` to tell
which workflow called a fake.


---

## After the six passes: the decisions not yet checked claim by claim

Scope: D35, D36, D37, D38, D39, D40, D42, D43, D48, D49, D53, D54, D58, D65, D75, D79, and more of
D45 and D60. Each was read in full in `docs/BRIEF.md`, and its checkable claims were run. Every
command below ran from the repository root at `ecef3d1` (branch `review-2026-11`; the source is
`3edb471`). Seven probes, 212 rows in all: 211 agree with the brief, 1 does not (finding 1), and
three more rows are marked "ASKED" or "MINOR, shown not counted" (findings 2 and 3 come from
them). No guarantee was found broken; the three findings are minor.

| probe (under `reviews/2026-11/probes/`) | decisions | last line |
| --- | --- | --- |
| `p7b_d35_d36_d37_validation_and_runtime.py` | D35, D36, D37 | `RESULT: HELD - 37 of 37 claims agree` |
| `p7b_d38_d39_d40_rules.py` | D38, D39, D40 | `RESULT: HELD - 40 of 40 claims agree` |
| `p7b_d42_d43_d48_d49_set_steering_limits_transitions.py` | D42, D43, D48, D49 | `RESULT: HELD - 41 of 41 claims agree` |
| `p7b_d53_migrations.py` | D53 | `RESULT: HELD - 36 of 36 claims agree` |
| `p7b_d54_d65_d75_temporal.py` | D54, D65, D75 (time-skipping server) | `RESULT: HELD - 23 of 23 claims agree` |
| `p7b_d58_d60_d79_builder_schema_caller.py` | D58, D60, D79 | `RESULT: BROKEN - D58: MINOR: 'a value that doesn't read back the same is refused' ...` (24 of 25 agree) |
| `p7b_d45_reading_and_stories.py` | D45 | `RESULT: HELD - 10 of 10 claims agree` |

The probes reach past `public.json` for `parse_case`, `validate_case`, `ventoux.testing.run_case`
and its catalog, the plan's `parse_plan` and `validate`, `contract_hash`, `preview_migration` and
`migration_of`, the registry's functions, the builder's `written` and `package`, the rule reader,
and (the Temporal probe only) the repository's own test helpers. Each probe's header says which.

### Findings

#### 7b.1 `ventoux check` ends in a traceback, and leaves an empty `case.json`, when a definition holds a text that can't be written (*minor*)

A builder case whose condition compares a field with a text holding a lone surrogate (`"\ud800"`)
is accepted by the builder's `written`, and `ventoux check` then fails while writing the file: a
Python traceback, no sentence saying what is wrong or what to do, and a `packages/odd/case.json`
of 0 bytes left on disk.

Promise touched, D58: "**The same JSON, byte for byte.** ... a number as the decimal the engine
holds; a value that doesn't read back the same is refused." And CLAUDE.md, conventions: "its error
message saying what is wrong, then what to do." A text that can't be encoded can't read back at
all; it is not refused, the command crashes. (Numbers are refused properly: `NaN`, `Infinity`,
`1E+7000`, `1E+3` and `-0` each give a `TypeError` or `NotWritable` with a sentence; same probe.)

Proof, at `ecef3d1`:

```
$ uv run python reviews/2026-11/probes/p7b_d58_d60_d79_builder_schema_caller.py
D58 | (a text holding a lone surrogate ...: what the builder's `written` does with it) | written(): ok; its text as UTF-8: UnicodeEncodeError: 'utf-8' codec can't encode character '\ud800' in position 419 ... | yes
D58 | MINOR: 'a value that doesn't read back the same is refused' (`ventoux check` on a case whose condition holds a lone surrogate ...) | exit 1; a traceback: True; last line: ["UnicodeEncodeError: 'utf-8' codec can't encode character '\\ud800' in position 415: surrogates not allowed"]; files left: {'packages/odd/case.json': 0} | NO
RESULT: BROKEN - D58: MINOR: 'a value that doesn't read back the same is refused' ...
```

Why only minor: nothing wrong is released (exit 1, and `--unchanged` would fail on the empty
file), and the text has to be written on purpose. Proposed fix, in words: have `written` check
that its text encodes as UTF-8 (it already reads its own output back), refusing with
`NotWritable` naming the place; and write a package's files only once every file's text exists,
so a failure leaves nothing half-written.

#### 7b.2 On one moment, a later rule's `stop` acts before an earlier rule's `start`, and no document says so (*minor*)

With three rules on one moment, written in this order: `s1` starts `follow`, `s2` stops `follow`,
`s3` starts `follow`, the history shows `s2`'s stop first (it finds nothing to stop), then `s1`'s
start, and `follow` is left open. A rule's `stop`, `set` and `reach` act when the rule fires; its
`start` is queued and admitted once every rule on the moment has fired
(`src/ventoux/case/rules.py`: "admission decides, once the rules on this moment have fired
(brief, D39)"). So "start it, then stop it" written as two rules does the opposite of what its
order says.

What the brief says: D38, "**Rules run inside the decision, in order.** Moments are taken as they
happen, the rules on one moment in the definition's order; a milestone a rule reaches is a moment
too; admission runs again after"; D40, "Inside one `then`, the stop acts first, then `reach`,
then `start`" (inside one `then` only); D45, the reading's fine print: "a start being a proposal
that admission decides at once, as a person's". D38's "admission runs again after" does allow
what the code does, so this is not a broken promise; but D39 never says a rule's start is decided
after the other rules on its moment, D45's and the reading's "decided at once" reads the other
way, and the history lists the two rules against the definition's order.

Proof, at `ecef3d1`:

```
$ uv run python reviews/2026-11/probes/p7b_d38_d39_d40_rules.py
D39 | 'A step a rule has started in a decision isn't started again by a rule in it (recorded)' | s3#1 on answered review: follow not started: a rule already started it in this decision | yes
D38/D40 | ASKED, not a promise in these words: with rules written start (s1), stop (s2), start (s3) on one moment, does s1's start act before s2's stop? ... | order in the history: ['s2:stopping follow', 's2:follow not stopped: no run o', 's1:starting follow', 's3:follow not started: a rule a']; follow is left open | yes
```

Proposed fix, in words: no change to the engine. Say it where an author reads it: one sentence in
D39 as an amendment ("a rule's start is admitted once every rule on its moment has fired, so a
stop written after it on the same moment acts first"), the same in the cases guide's "Rules that
start steps", and reword the reading's fine print from "decided at once" to "decided once the
rules on this moment have fired, without waiting".

#### 7b.3 A rule's reading writes "stop pay", the words D45 gives as the reading to avoid (*minor*)

The sentence a rule reads as is "... stop pay, then set owed to amount + 1, then reach big, then
start follow." What the engine does is said only in the fine print beside it ("Stopping pay
cancels a run waiting to start, at once; a running call is only asked to stop, may still finish,
and is flagged if it does; a failed run isn't stopped.").

D45: "An action reads as what the engine does, never as its name alone: "stop pay" would read as
if the payment stops, and a running refund goes through." The fine print keeps the substance (the
action is not left alone on the page, and the probe checks the fine print is there), so this is
wording: the brief's own bad example is printed as the sentence.

Proof, at `ecef3d1`:

```
$ uv run python reviews/2026-11/probes/p7b_d45_reading_and_stories.py
D45 | 'Every rule reads as one sentence ... (stop, set, reach, start)' | Each time review is answered, whatever the outcome, if amount > 70 (read when it fires): stop pay, then set owed to amount + 1, then reach big, then start follow. | yes
D45 | MINOR, shown not counted: the sentence itself writes the action as the words D45 gives as the reading to avoid ... | 'stop pay' in the sentence: True | yes
```

Proposed fix, in words: either the sentence says "ask pay to stop" (or "stop pay's run"), or D45
is amended to say the sentence names the action and the fine print says what the engine does.

#### Where the brief reads against itself (proposals only; none is in the report's list)

- **D60 against D82, the schemas' place.** D60: "**Two schemas, generated from the models the
  engine parses with:** `schema/case.schema.json` from `CaseDefinition` and
  `schema/plan.schema.json` from `Plan`" (and D1's addition of 2026-10-25: "the schema is
  published, `schema/case.schema.json`"). D82: "the schemas moving from `schema/` at the root to
  `src/ventoux/schema/` (their `$id` unchanged)". The code follows D82 (probe row "D60/D82":
  `schema/` doesn't exist, `src/ventoux/schema/` holds both). D60 carries no "Amended ..., by D82"
  line, though other decisions get one when a later decision changes them (D53: "Amended
  2026-10-23, by D54"). Proposal: add that line to D60 and to D1's addition.
- **D45 against D38 and the code, when a rule's start is decided:** see finding 2 ("decides at
  once" against "admission runs again after").
- **D79 against D82, already in the report as 5.3; one detail to add.** D79 names "Ventoux's
  client functions (`start_case`, `answer`, `close`, `propose_change` and the others in
  `ventoux.temporal.cases`; `propose_forget` and `answer_forget`)" as what the trusted caller
  calls. All six exist; `close` and `propose_change` are not in `public.json`, and neither are
  twelve of "the others" (`approval_sheet`, `assign`, `claim`, `give_back`, `preview_migrations`,
  `propose`, `propose_migration`, `retry`, `send_event`, `shown`, `unassign`, `view`). Probe:
  `p7b_d58_d60_d79_builder_schema_caller.py`, the three D79 rows.

### What held

Every row below is a line of a probe's table, with the brief's words quoted in it.

- **D35** (`p7b_d35_d36_d37_validation_and_runtime.py`, 17 rows). Twelve errors, each with the
  runtime refusing the same definition while validation is never called (`run_case` only parses):
  `UNKNOWN_CONTRACT`, `UNKNOWN_INPUT`, `MISSING_INPUT`, `ENGINE_INPUT`, `APPROVAL_REQUIRED`,
  `APPROVAL_ROLE` (refused when the approval is answered), `UNKNOWN_ROLE`, `EXPRESSION_INVALID`,
  `WRONG_KIND`, `UNKNOWN_SOURCE` (the case doesn't open), `INPUT_TYPE`, `UNKNOWN_PLAN`. A role
  nobody registered gives sight of nothing. A message quotes the misspelt literal and neither a
  title nor an approval's reason; the runtime's refusal quotes no case-file value. One cause, one
  issue, for a missing contract and for a misspelt role.
- **D36** (9 rows). The text `"40"` refused where a decimal is taken: in a case's activity input,
  in a plan field given by a case, and in a plan run alone. A crm reference refused where an
  orders reference is taken. Contract inputs refused when the contract is made: `float`, `Any`,
  `int`, a nested model, `Literal[1, 2]`, `bytes`. `OPENER_DECIDES` is a warning, and the run
  does what it says (scheduled when a system opens, refused when a person does).
  `SENSITIVE_TO_WORKFLOW` and `NO_SOURCES` are errors the runtime meets too. `APPROVER_CANT_SEE`
  is a warning; the answer is refused for a person holding only the approving role and accepted
  for one who also holds the seeing role.
- **D37** (11 rows). Each of the four warnings with a definition that gives it and a run doing
  what it says (`OUTCOME_UNREAD`, `MAY_BE_UNSET`, `NEVER_REFRESHED`, `APPROVAL_ELSEWHERE`). `and`
  and `or` read every part (warned, and the run fails); `if` guards (no warning, the run closes).
  `SET_AFTER` is an error and an operator's retry fails the same way. The quickstart's committed
  package warns about nothing, and a declined refund leaves `call_customer` open.
- **D38** (`p7b_d38_d39_d40_rules.py`, 10 rows). Six moments are read and a seventh is refused
  naming the six; rules fire in the definition's order and a reached milestone is a moment;
  entries are `name#1`; a rule named as a step or a milestone is refused; a rule that can't be
  read needs attention, and an operator's retry reads it again and it acts; a rule reading
  untrusted data reaches nothing, naming field and source, never the value; `UNTRUSTED_TRIGGER`;
  `NEVER_FIRES` (both kinds); a firing on the closing milestone is recorded "not applied".
- **D39** (21 rows). Six "recorded, and nothing runs" cases, each one line; a missing contract
  fails needing attention; a person's proposal waits for a fresh fact, is refused while the start
  waits, and is refused when the fact can't be fetched; a rule's start doesn't wait and an
  operator's retry fetches; nothing starts beside a failed run (rule and person); a second start
  by a rule in one decision is recorded; `NEVER_STARTS`; `NEVER_CLOSES` with both endings of its
  sentence; `LOOPS_UNTIL_CLOSED` and its run; an approval whose `when` reads untrusted data is
  asked anyway, saying why; an untrusted rule condition refuses a `trusted_only` input, naming
  field and source.
- **D40** (9 rows). Order stop, set, reach, start in one `then`; one name in `stop` and `start`
  refused; a non-step in `stop` refused; an open task cancelled saying why; nothing to stop is
  recorded; a failed run is never stopped; a run failing after its stop needs attention and is
  never cancelled; a run finishing after its stop is done and flagged; untrusted data stops
  nothing; `cancellable: false` hashes as not declared, `true` differs.
- **D42** (`p7b_d42_d43_d48_d49_set_steering_limits_transitions.py`, 13 rows). One kind of writer
  per field (a person's field refused when read; a rule's field refused at the opening); a rule
  that reads nothing; sensitive to plain (in the value and in the `when`); a wider view; a list;
  a step's outcome as target; a constant under an untrusted condition is untrusted; two rules in
  order, both recorded, the latest stands; the computed value's obtained time is the oldest
  fact's; a rule acts whole or not at all; `WRITER_DECIDES` with both runs.
- **D43, on a plain activity step** (9 rows). A steered run reaches nothing, saying why; its
  output carries `untrusted:customer` beside `system:orders`; a rule on its start neither reaches
  nor stops, and a value it sets carries the source; a step it starts has it checked against a
  `trusted_only` input; a step requiring it is steered too; a task requiring it ends it (its
  `reaches` apply, and the next step is unsteered); an approval doesn't end it; a retry keeps it.
- **D48** (14 rows). Each shape refused when read: a sensitive, list or `visible_to` payload
  field; three spellings of two senders; a list set by a rule; two spellings of
  `since=first_start`; `count` on a plan's approval; three spellings of roles per approver.
  `KEPT_FROM_STARTING` is a warning, and the history line names step, field and source, never the
  value.
- **D49** (5 rows). `UNTRUSTED_TRANSITION`; `UNTRUSTED_TRIGGER` at the case's input; the
  refusal's sentence equal, word for word, to the brief's with the plan's names; a transition
  never tried refuses nothing; one tried stops the plan whatever the value.
- **D53** (`p7b_d53_migrations.py`, 36 rows). Proposer, approver and opener rules; cancelled by a
  close; six "held under a name the target lacks" refusals, every problem at once; a done run's
  outcome the target doesn't declare; nothing loosens (sensitive, a wider or dropped
  `visible_to`, a type); timers kept, measured again, due at the migration's own time when
  already past (never earlier), cancelled and said; the engine forward only, and alone; a move
  to where the case already is refused; the preview leaves the state as it was and is refused
  for a closed case; no rule fires on a migration; values keep their sources; a stale proposal
  isn't applied; "closed: nothing left to do; paid not reached".
- **D54** (`p7b_d54_d65_d75_temporal.py`, 16 rows). No registry: `environment_worker` raises
  before any worker exists, and neither it, a published manifest nor a misspelt name creates
  one; production unless created for development, a development one hardened, a second create
  refused; activation says three problems at once (a poller with no manifest, two wrong hashes
  with builds and short hashes); retiring refused while active, then with an open case, then
  done; a retired release opens no case and isn't activated again; a development audit store
  refused in production (D81's amendment); a workflow type moved under an open case refused.
  `ventoux environment check` exiting 1 on a problem: the repository's own test, run alone on
  the dev server, `uv run pytest -q -p no:cacheprovider
  "tests/test_temporal_activate.py::test_the_environment_check_fails_when_a_contract_has_no_live_worker"`
  gives `1 passed in 3.27s`; it asserts `(fine, broken) == (0, 1)` and the three printed lines.
- **D65** (1 row). `case_worker`, `plan_worker`, `registry_worker` and `environment_worker` each
  give a worker whose `workflow_runner` is `SANDBOX` itself.
- **D75** (6 rows). The child's workflow ID is `claim-7/repair#1` with parent `claim-7`; the
  parent's history starts it with `PARENT_CLOSE_POLICY_ABANDON`; forgetting the child alone is
  refused naming its parent; so is any ID with a `/`; a doorbell rung twice after the report
  landed is recorded twice as "nothing read" and the report lands once; a case's own ID with a
  `/` is refused.
- **D58** (`p7b_d58_d60_d79_builder_schema_caller.py`, 14 rows held). Asking an `Expr` for a bool
  raises in all five forms; `float` and `bool` numbers raise; a plain `True`, `250` or `"yes"`
  given as `when=` is refused at run time too (a `TypeError` with a sentence), not only by the
  type checker; both example builders write their committed packages byte for byte, and `ventoux
  check --unchanged` exits 0 in the quickstart; a default key is left out; five numbers that
  don't read back are refused; importing the builder loads no `temporalio` module.
- **D60** (7 rows). Both `$id`s are `https://ventoux.dev/schema/engine-3/...`, the engine's
  version; draft 2020-12; no object schema with properties allows an unknown key; `ventoux schema
  --unchanged` exits 0; 24 lax readings (the four kinds) are all refused by the parser; the four
  corpus tests exist, and `uv run pytest -q -p no:cacheprovider tests/test_schema.py` gives `64
  passed`.
- **D79** (1 row). The six client functions it names exist.
- **D45** (`p7b_d45_reading_and_stories.py`, 9 rows). One sentence in the engine's order; names,
  not titles; the condition as the renderer writes it; the fine print for a stop; an unknown
  moment refused; `ventoux simulate` on an example story exits 0 and prints no `1200`; a story
  with one expected line removed, or one added, exits 1; `uv run pytest -q -p no:cacheprovider
  tests/test_simulate.py` gives `43 passed`.

A note for whoever reruns probes that call the command: `python -m ventoux.tooling.cli` runs
nothing and exits 0 (the module has no `__main__` block; the entry point is
`ventoux.tooling.cli:main`). My first runs of three rows were empty for that reason; the probes
now call `main()`.

### Unproven

- D58, "the builder never runs inside the engine, and never on model output": not something a
  run of mine could show beyond the import row.
- D43, "across continue-as-new" for a plain activity step: not run here (pass 1a's probes cover
  continue-as-new for the repeated and case steps it found failing).
- D53 on Temporal ("a query on Temporal; a closed case's is refused"): shown only on the pure
  function the query calls (`preview_migration`), not through `preview_migrations` on a server.

### Unchecked

- D54: "Its workflow can't end while its registry is unreachable", the registry's
  continue-as-new "after a count of requests", "A worker in another SDK language publishes the
  same manifest as JSON", and "Polling now is what Temporal's server lists" (the time-skipping
  server lists no pollers; only the repository's dev-server test above touches it).
- D75: the daily check of open children, a child ending without ringing, continue-as-new with an
  open child, the registry's check of a pinned child's release at activation and retirement, and
  the 5-second wait of a doorbell's read. The task asked for a sample of four; six rows were run.
- D53: an event decided under the release current when its turn comes; approvals lapsing "word
  for word"; a running plan finishing on its own plan; a cohort.
- D39: "The waiting start crosses continue-as-new (D27)".
- D36: "A plan step carries its case's sources into its plan ... each activity in the plan is
  checked with that" beyond the two type rows.


---

## Summary

**Findings by severity** (one line each in the list at the top; a line that names two numbers is
one finding seen from two passes):

| Severity | Findings |
|---|---|
| Breaks a promise | 21 |
| Weakens a promise | 18 |
| Misleads | 15 |
| Minor | 19 |
| **All** | **73** |

**The three that matter most.**

1. **Forgetting doesn't reach everything, and can be done where the definition forbids it**
   (1c.1 with 1b.4, 1c.5, 1c.2, 1c.7). A sensitive option or attachment is written in plain text
   into the case's Temporal history as its check's input, and is still there once the key is
   destroyed. A closed case that keeps its records (`forgetting: while_open`) refuses the
   approval and is forgotten anyway. A second request to forget shares the first one's audit
   stream, so the request that really destroys the key leaves no record of who proposed and who
   approved. These are the promises a data-protection role would rely on, and each is reachable
   through Ventoux's own client functions.
2. **Untrusted data decides, through the two newest kinds of step, while `ventoux check` says it
   can't** (1a.1, 1a.2, with 1a.3 and 1a.4). A repeated step and a case step keep nothing of what
   steered them, so on a customer's word they send trusted-only inputs and reach the milestones a
   case closes on. For the repeated step, validation reports the very same paths as errors that
   can never happen, which is worse than silence: a reviewer reading the check is told the
   opposite of what runs.
3. **A value hidden by `visible_to` is shown to roles it is hidden from, once it crosses a join**
   (1b.5 with 1c.4). Passed into a child case's field, back through a child's report, or into a
   plan step, it is read by anyone, and from the audit store `read_audit` shows it to a reader
   with no role at all. "A view hiding more than its source" is a non-negotiable, and validation
   says nothing at any of the three places.

**One thing the passes show together.** Most of what breaks is at child cases (layer 18c and
18d): what steered the step (1a.2), a declared mark (1a.3), who may approve a change (1b.2),
who sees a value (1b.5), a failed run let go (1b.6), a report overwriting an outcome (1b.3).
Each rule holds inside one case and was not carried across the step that opens another. And the
tests would not have noticed several rules going: three rules, among them "a case closes when
all of its `closes_when` milestones are reached", can each be removed with all 4,694 tests still
passing (4.1, 4.2, 4.4).

**What stayed unchecked.**

- **The Vault binary and a real Vault.** The three development-Vault tests skip here; every
  finding about Vault (3.1, 3.2) was shown with a stand-in transport or a plain web server.
- **A real Temporal cluster with mTLS, and macOS.** Every Temporal run used the time-skipping
  test server on Linux; one pass also used the local development server. `ventoux doctor`'s live
  rules were not run against a deployment.
- **Pass 1's in-memory findings on Temporal:** since checked. All eleven (1a.1 to 1a.4, 1b.1,
  1b.2, 1b.3, 1b.5, 1b.6, 1b.8, 3.3) reproduce on a Temporal worker (section 7a); the other
  part b findings (1b.7, 1b.9, 1b.10, 1b.11) were not carried over.
- **A live model provider.** No key was used; the step advisor and the authoring loop were run on
  recordings.
- **Pass 3's sweep was not exhaustive:** every `except` handler in `core`, `tooling` and
  `authoring` was read, about a third of those in `case` and under half in `temporal`.
- **Pass 4's limits:** only three survivors were run against the Temporal-backed tests; the
  others could still be noticed by one. A case's step kinds, audit record kinds and the
  non-determinism boundary test were not sampled.
- **Pass 5:** not every example in `cases.md`, `case-data.md`, `plans.md`, `expressions.md` and
  `activities.md` was run; forgetting, a migration, plans on Temporal, `simulate`, `summary` and
  `draft-sheet` were not followed from the guides.
- **Pass 6:** D35 to D40, D42, D43, D48, D49, D53, D54, D58, D65, D75 and D79 were not checked
  claim by claim; D77's ten attempts, five minutes and 256 KB were read in the code and not seen
  in a run.
- **The TypeScript evaluator** D20 speaks of is not in this repository.
- Each pass's own "Unproven" and "Unchecked" sections, above, say the rest.

**The review's own footprint.** Nothing outside `reviews/2026-11/` was changed. The probes are
not formatted to the project's lint rules, so CI's lint job is red on this branch, as the task
allowed.
