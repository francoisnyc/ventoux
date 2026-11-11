# Fix: the ten decisions the review's fixes wait on

A fix, not a layer: no warm-up, and nothing is built here. The whole-project review of November
2026 (kept on the branch `review-2026-11`, `reviews/2026-11/FIXES.md`, part 1) listed ten
questions, A to J, that need an answer in the brief before any code is written. They were settled
on 2026-11-11. This pull request records them in `docs/BRIEF.md` and changes nothing else: no
source, no test, no guide.

The placements and the wording below were proposed here first, agreed on 2026-11-11, then
written into the brief. The brief is the record; this note says how it was put together.

## How they are recorded

- **No decision is renumbered or rewritten.** A rule that stands on its own gets the next number,
  from D84. A rule that adds to one decision is a dated line under it, "Amended 2026-11-11 …
  (the text above stands; this adds to it)".
- **A new decision also leaves one dated line under each decision it adds to,** as D43 to D83 do,
  so a reader of the older decision meets the newer one.
- **Nothing here is built yet, and each entry says so.** Every entry ends with the same two
  facts: "Not built on 2026-11-11", and the review's findings it will close. A fix that builds it
  adds its own dated line when it merges. So the brief never claims behaviour `main` doesn't have.
- **Where they sit:** D84 to D90 after D83, in the order below.

| | Question | Goes in as | Adds to (one dated line under each) | Findings it will close |
|---|---|---|---|---|
| A | Is a fix a new engine version? | **D84** | D51, D68 | none; fixes 3 to 15 wait on it |
| B | A child's failed run when its parent closes | amendment under **D74** | | 1b.6 |
| C | How far steering goes | **D85** | D43, D48, D73, D74 | 1a.1, 1a.2, 1a.3, 1a.5 |
| D | Who is excluded across a join | **D86** | D11, D28, D39, D74 | 1b.1, 1b.8, 1b.7 |
| E | `visible_to` at a join | **D87** | D42, D74, D77 | 1b.5, 1c.4 |
| F | Form values, and a name that is no field | amendments under **D76** and **D9** | | 1c.7 |
| G | "Drafts by default" is checked | **D88** | D56, the non-negotiables | 1b.9 |
| H | Refusals that depend on what the code knows | **D89** | D27, D53, D77 | 2.1, 2.2, 2.3 |
| I | Messages sent with Temporal's client directly | **D90** | D79 | 1c.8, 1c.9, 1c.11, 1c.14 |
| J | Which names are supported | amendment under **D82** | | 5.3, 6b.1 |

## The wording, as proposed

### A. D84. Until the first published release, a fix changes engine 3 in place


> *Decided 2026-11-11, after the whole-project review of November 2026
> (`docs/layers/fix-review-decisions.md`, A). Adds to D51 and D68, whose text is kept.*
>
> - **Nothing before the first published release is owed an old branch.** Until `ventoux` 0.1.0 is
>   published (D82), a fix that decides a recorded path differently changes engine 3 in place: no
>   new engine version, no old branch kept behind the case's version.
> - **It stands on one fact, confirmed by the maintainer on 2026-11-11:** no case outside the tests
>   runs on engine 3. D68 made this exception for one shape, in code "merged on 2026-11-02 and
>   never released (0.0.0)"; this extends it to every fix, for the same reason.
> - **What it covers:** fixes merged after `main` at `830ed3f`, until the first published release.
> - **Fixtures that replay a changed path are recorded again,** and the fix's note says which and
>   why. A fixture whose path a fix doesn't change must still replay as it is.
> - **After the first published release, D51 applies in full:** a change that decides a recorded
>   path differently is the next version, its old branch kept, a fixture, and a line there.

Under D51 and D68: "Amended 2026-11-11, by D84 (the text above stands; this adds to it): until
the first published release, a fix changes engine 3 in place; after it, this decision applies in
full."

### B. Under D74: a child's failed run holds its parent

> **Amended 2026-11-11, after the review of November 2026** (`docs/layers/fix-review-decisions.md`,
> B; the text above stands, this narrows it): a child case holding a failed run holds its parent's
> automatic close (`closes_when`), and refuses a rule's stop of its case step, as a failed run
> does inside one case (D17, D26, D40). A person's close of the parent still closes both. "A
> close never waits for a person" was written of open tasks; a failed run waits for one. Not
> built on 2026-11-11: until its fix, both cancel the child's failed run (the review's finding
> 1b.6).

### C. D85. Steering crosses a case step, a list and an absence

> *Adds to D43, D48, D73 and D74, whose text is kept.*
>
> - **A case step keeps what steered it, and its child's opening carries it,** as a plan step's
>   does (D39, D43). It is checked against each input's policy in the child, counted at the case
>   step's `reaches` and at rules on its start, and ends at a person's task (D43). A field the
>   child declares `untrusted:` keeps its mark whoever gives the value, its parent included
>   (D12, D41). `ventoux check` says the same. (Findings 1a.2, 1a.3.)
> - **A step repeated over a list is steered by the list's sources:** each run exists because the
>   item was listed. A run over an untrusted list is a steered run, as D43 reads one. (1a.1.)
> - **The absence of a person's work carries what steered it,** as an activity's unset output
>   does. A task kept from starting by untrusted data, or an empty untrusted list meeting
>   `requires`, doesn't reach a milestone. D48's limit stands as written: untrusted data may keep
>   something from happening, and the case may close with nothing left to do; what it may not do
>   is reach a milestone by it. (1a.5.)
> - Not built on 2026-11-11.

### D. D86. Who is excluded across a plan step and a case step

> *Adds to D11, D28, D39 and D74, whose text is kept.*
>
> - **A plan's outcome carries the person whose answer inside the plan chose it,** as a child's
>   outcome carries its closer (D74): `person:<answerer>, system:<plan>`. That person approves
>   nothing the outcome decides (D11). (1b.1.)
> - **The person whose answer a step's own `when` read approves nothing inside its plan or its
>   child,** as on a call step. D28 and D74 name the opener and the proposer; this is the third.
>   (1b.8.)
> - **D39's recorded gap stands:** a person whose answer only brought the moment, or whose run a
>   step `requires`, is not excluded. `ventoux check` warns where a definition relies on it.
>   (1b.7.)
> - Not built on 2026-11-11.

### E. D87. A value hidden by `visible_to` is never given to more roles at a join

> *Adds to D42, D74 and D77, whose text is kept.*
>
> - **Validation refuses each of these, and the runtime refuses the same when validation didn't
>   run** (D34): a parent's value given to a child's field that more roles may see; a child's
>   reported field read by more roles than see it in the child; a plan step's input that the
>   audit record would show under another name. A view hides more than its source, never less,
>   as D42 says of a set field and D74 of a sensitive value. (1b.5, 1c.4.)
> - Not built on 2026-11-11.

### F. Under D76 and D9

> Under D76: **Amended 2026-11-11** (F; the text above stands, this narrows one sentence): D32
> stands, "every form value in the answers people sent" goes with forgetting. So the values an
> act gave, in its record, stay sealed whatever their field; what a decision wrote is recorded as
> the case file holds it, sensitive only if its field is. Not built on 2026-11-11.
>
> Under D9: **Amended 2026-11-11** (F; the text above stands, this adds to it): an answer giving
> a value under a name its task doesn't set is refused, as an undeclared answer is, and the
> refusal never keeps the value in clear. Not built on 2026-11-11 (finding 1c.7).

### G. D88. "Drafts by default" is checked by the engine

> *Adds to D56, whose text is kept, and to the non-negotiables.*
>
> - **A contract says it talks to people by its effect, `notify`,** which every contract already
>   declares and its hash already covers (D5): no new key. A contract that only drafts is `write`.
> - **In a case, a `notify` contract runs only on a step with an approval that has no `when`.**
>   Refused at validation, and at the start on nothing validation did (D34). So a person sees
>   each message before it goes.
> - **In a plan, a state calling a `notify` contract is the target of an approval state** (D23),
>   refused when the plan is read and when the run would enter it otherwise.
> - **What follows:** a repeated step takes no approval (D73), so it can't call one; a refresh
>   never runs one (D33: only a `read`).
> - **Built before layer 21.** Not built on 2026-11-11 (finding 1b.9). The "will never do" sheet
>   may say "drafts, never sends" once it is (D56).

### H. D89. A refusal that depends on what the code knew is recorded as data

> *Adds to D27, D53 and D77, whose text is kept.*
>
> - **What the code knew is kept in the state when it refuses,** so a replay by later code
>   refuses the same: the engine versions a refused migration was judged against. (2.1.)
> - **The same goes for** the forget request's engine version, learned once and carried, never
>   read from a constant (2.2); and the class settings `events_per_run` and `audit_bound`, carried
>   by the run that started under them (2.3).
> - Not built on 2026-11-11.

### I. D90. The engine is hardened against messages sent with Temporal's client directly

> *Adds to D79, whose text is kept.*
>
> - D79 forbids them and Temporal doesn't prevent them. So: **a number that isn't finite is
>   refused and recorded** (1c.8); **a signal that can't be read is recorded as refused, never
>   dropped** (1c.9); **a start claiming to have continued as new is checked against the run's
>   own history** (1c.11); **a close by a parent is refused and recorded by a case whose start
>   names no parent** (1c.14).
> - **The deployment guide says** that direct access to the namespace is inside the trusted
>   caller's boundary.
> - Not built on 2026-11-11.

### J. Under D82

> **Amended 2026-11-11** (J; the text above stands, this adds to it): every name a guide tells a
> team to use is supported: it is in `public.json`, or the guide stops using it. The guard test
> reads the calls in the guides' Python blocks and the quickstart, not only import lines. Not
> built on 2026-11-11 (findings 5.3, 6b.1); the fix's note says, name by name, which was listed
> and which a guide stopped using.

## Asked, and answered on 2026-11-11

1. **A stands on a fact:** no case outside the tests runs on engine 3 today. Confirmed by the
   maintainer.
2. **A's commit:** `main` was at `d88e9d9` when this was written, since #100 (the sensitive check)
   merged after #99; its note says it changes no recorded path. D84 says "after `main` at
   `830ed3f`", as settled.
3. **F:** D76's amended sentence reads as above: an act's values sealed whatever their field;
   what a decision wrote as the case file holds it.
4. **G, how a contract says it talks to people:** by its effect, `notify`. Every contract already
   declares an effect and its hash covers it, and the development catalog holds no `notify`
   contract (its letters are drafted by a `write`), so no contract gains a version. A new key was
   the other way, and would have been a new version of each contract gaining it.
5. **G, inside a plan,** which has no step approval: a state calling a `notify` contract is the
   target of an approval state (D23). Refusing `notify` in a plan was the other way.
6. **I and finding 1c.14,** which matched none of I's three rules: D90 gains a fourth, a close by
   a parent refused and recorded by a case whose start names no parent.

## What stays out

- Layer 9's check-yourself question, which F touches, is answered nowhere here.
- The brief's status line ("decisions D1–D26") and the other housekeeping are fix 30's.
- No guide changes, the deployment guide's line under I included: it comes with fix 25.

## Promises

Nothing here is behaviour, so no test is added. The one claim that can be checked:

| The note says | What fails if it weren't true |
|---|---|
| No decision's earlier text is changed or renumbered: the brief only gains lines | `git diff --numstat origin/main -- docs/BRIEF.md` gives `188 0`: 188 lines added, none removed. Run before the pull request was opened and quoted in it |
