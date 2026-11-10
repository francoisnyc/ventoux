# Fix: three rules no test would have missed

A fix, not a layer: no warm-up, and nothing new to build. Found by the whole-project review of
November 2026 (its findings 4.1, 4.2 and 4.4, kept on the branch `review-2026-11`): three rules
the engine enforces could each be removed with every test still passing. This fix adds the tests
that notice. No source file changes, so no decision changes meaning, none gets an amendment, and
there is no new engine version (D51).

## The three rules

1. **A case closes on `closes_when` once every milestone it names is reached, never on one of
   them** (D10: "closes the case as soon as they are reached"). In `case/closing.py` the rule is
   `all(...)`. Every test named one milestone, or reached all of them in the same decision, so
   `any(...)` passed them all.
2. **An approver's role is one the approval lists** (D23: "the person has one of its roles. An
   approval adds: the role may approve the activity's risk"). `approver_role` in
   `core/approval.py` keeps a role only if the approval lists it and it may approve the risk.
   Without "lists it", a person holding a listed role that may approve no risk, and another role
   that may approve high risk and isn't listed, approves. The same function judges a plan's
   approval state and a case step's approval, so each engine gets a test.
3. **The runtime stops a repeated high-risk step, on nothing validation did** (D34: "the runtime
   depends on nothing validation did"; D73: "no approval on a repeated step, so a high-risk
   contract can't be repeated"). Only the refusal at the check was tested. With the runtime's own
   refusal removed, each item's refund is scheduled with no approval.

## The seams

`ventoux.testing.run_case` and `run_plan`, as the tests beside them use. Nothing internal is
tested.

## Shown failing for the right reason

The code is right already, so a new test passes as soon as it is written. To see that it can
fail, each was run once with its rule taken out of the source, and the source restored at once:

| Test | With the rule taken out | What the test then says |
|---|---|---|
| `test_closes_when_waits_for_every_one_of_its_milestones` | `all(` read as `any(` in `case/closing.py` | `assert 'closed' == 'open'` |
| `test_a_role_the_approval_doesnt_list_never_approves_for_it` (`test_people.py`, a plan) | `if role in roles` read as `if True` in `core/approval.py` | no refusal recorded: `assert [] == ["refused sam's answer approve: …"]` |
| `test_a_role_the_approval_doesnt_list_never_approves_for_it` (`test_approvals.py`, a case) | the same | `DID NOT RAISE AnswerRefused` |
| `test_a_repeated_high_risk_step_is_stopped_by_the_runtime_alone` | `if contract.risk == "high":` read as `if False:` in `case/runtime.py` | nothing needs attention: `assert [] == ['draft_line.1#1: … is repeated', …]` |

## Promises

| The note says | The test that fails if it weren't true |
|---|---|
| With one of two `closes_when` milestones reached, the case stays open and still asks its survey; with both, it closes, saying both | `tests/test_case.py::test_closes_when_waits_for_every_one_of_its_milestones` |
| A plan's approval refuses a person whose only role allowed the risk isn't listed, on the listed role, and nobody has approved | `tests/test_people.py::test_a_role_the_approval_doesnt_list_never_approves_for_it` |
| A case step's approval refuses the same, never validated | `tests/test_approvals.py::test_a_role_the_approval_doesnt_list_never_approves_for_it` |
| A repeated high-risk step, never validated, fails each item's run, needing attention, and schedules nothing | `tests/test_repeated.py::test_a_repeated_high_risk_step_is_stopped_by_the_runtime_alone` |
