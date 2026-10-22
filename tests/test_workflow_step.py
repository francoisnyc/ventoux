"""Workflow steps, in memory: an existing Temporal workflow run as one step (layer 8d).

Tests go through `run_case` and read what a run reports. See docs/layers/08-case.md (8d) and
docs/guides/cases.md, "Workflow steps".
"""

import copy
from decimal import Decimal
from pathlib import Path
from typing import Annotated, Any

from pydantic import BaseModel

from ventoux.case.definition import parse_case
from ventoux.case.runtime import decide
from ventoux.case.state import (
    Answered,
    CancelWorkflow,
    CaseState,
    CloseAsked,
    Opened,
    Proposed,
    WorkflowCancelled,
)
from ventoux.core.catalog import Catalog
from ventoux.core.contract import Display
from ventoux.core.output_sources import source
from ventoux.core.policy import trusted_only
from ventoux.core.workflow_contract import WorkflowContract
from ventoux.testing import (
    CATALOG,
    START,
    AnswerRefused,
    close,
    fake_kyc,
    finish,
    load_definition,
    propose,
    retry,
    run_case,
)

GUIDE = Path(__file__).parent.parent / "docs" / "guides" / "cases.md"


def guide_block(starting: str) -> str:
    """The lines of the guide's block whose first line starts with `starting`, to its fence."""
    lines = GUIDE.read_text().splitlines()
    first = next(n for n, line in enumerate(lines) if line.startswith(starting))
    last = next(n for n in range(first, len(lines)) if lines[n].lstrip().startswith("```"))
    return "\n".join(lines[first:last])


REFUND = load_definition(Path(__file__).parent.parent / "examples" / "refund" / "refund.json")
PEOPLE = {"ana": ["support"], "sam": ["support", "support-lead"], "omar": ["operations"]}
FILE = {"order_id": "ord-1", "amount": 40, "customer_id": "c-1"}
REVIEWED = ("review", "approve", "ana", {"approved_amount": 40})
APPROVAL = {"roles": ["support-lead"], "display": {"reason": "Opening an account is high risk"}}


def with_kyc(**steps: dict[str, Any]) -> dict[str, Any]:
    """The refund with a customer, checked by the guide's `kyc` step, and `steps` after it."""
    definition = copy.deepcopy(REFUND)
    definition["fields"]["customer_id"] = {
        "type": "reference",
        "system": "crm",
        "display": {"title": "Customer"},
    }
    definition["steps"]["kyc"] = {
        "kind": "workflow",
        "display": {"title": "Check the customer"},
        "workflow": "kyc.check@1",
        "inputs": {"customer_id": {"var": "customer_id"}},
    }
    definition["steps"] |= steps
    return definition


def welcome(to_customer: str) -> dict[str, Any]:
    """A welcome letter drafted after the check, addressed with the field `to_customer`."""
    return {
        "kind": "activity",
        "display": {"title": "Draft a welcome letter"},
        "activity": "letters.draft@2",
        "requires": ["kyc"],
        "inputs": {"to_customer": {"var": to_customer}, "template": "welcome"},
    }


def test_an_undeclared_workflow_output_cannot_reach_a_trusted_input() -> None:
    # The curriculum's negative test: nobody declared where `contact_email` comes from, so it is
    # untrusted (brief, D6), and a letter, which takes its address only from trusted data, refuses
    # it. Nothing is drafted; the case waits for a person.
    run = run_case(
        with_kyc(welcome=welcome("kyc.contact_email")),
        file=FILE,
        answers=[REVIEWED],
        people=PEOPLE,
    )
    refused = (
        "welcome#1: letters.draft@2 takes to_customer only from a system or a person, never "
        "from untrusted data, and this value comes from kyc.contact_email (untrusted:undeclared)"
    )
    assert run.needs_attention == [refused]
    assert not run.closed
    assert guide_block("welcome#1 failed") in run.history  # as the guide shows it


class AccountInput(BaseModel):
    customer_id: Annotated[str, trusted_only()]
    idempotency_key: str


class AccountOutput(BaseModel):
    account_id: Annotated[str, source("system:accounts")]


# A high-risk workflow that writes: it opens an account, so it takes a key (brief, D17).
accounts_open = WorkflowContract(
    name="accounts.open",
    version=1,
    input=AccountInput,
    output=AccountOutput,
    risk="high",
    effect="write",
    timeout=300,
    idempotency_key="idempotency_key",
    display=Display(title="Open an account", description="Opens the customer's account."),
)


def with_accounts() -> Catalog:
    """The development catalog, the accounts system, and `accounts.open@1`."""
    catalog = copy.deepcopy(CATALOG)
    catalog.register_system("accounts")  # its output's source names it (brief, D29)
    catalog.register(accounts_open)
    return catalog


def open_account(**more: Any) -> dict[str, Any]:
    """A step opening the customer's account once the check is done."""
    return {
        "kind": "workflow",
        "display": {"title": "Open the account"},
        "workflow": "accounts.open@1",
        "requires": ["kyc"],
        "inputs": {"customer_id": {"var": "customer_id"}},
    } | more


def test_a_workflow_step_naming_an_activity_contract_fails() -> None:
    definition = with_kyc()
    definition["steps"]["kyc"]["workflow"] = "orders.lookup@1"
    run = run_case(definition, file=FILE, answers=[REVIEWED], people=PEOPLE)
    refused = (
        "kyc#1: orders.lookup@1 is an activity contract, not a workflow: run it as an activity "
        "step."
    )
    assert run.needs_attention == [refused]


def test_an_unbound_workflow_fails_its_step() -> None:
    run = run_case(
        with_kyc(account=open_account(approval=APPROVAL)),
        file=FILE,
        answers=[REVIEWED, ("account", "approve", "sam")],
        people=PEOPLE,
        catalog=with_accounts(),
    )
    assert run.needs_attention == [
        "account#1: accounts.open@1 has no binding here: bind it to a workflow"
    ]


def test_a_high_risk_workflow_without_approval_fails() -> None:
    # Checked at runtime, on nothing case validation did, as an activity step is.
    run = run_case(
        with_kyc(account=open_account()),
        file=FILE,
        answers=[REVIEWED],
        people=PEOPLE,
        catalog=with_accounts(),
        workflows={"accounts.open@1": lambda inputs: {"account_id": "a-1"}},
    )
    assert run.needs_attention == [
        "account#1: accounts.open@1 is high risk, and account has no approval"
    ]


def test_the_guides_workflow_step_runs_as_written() -> None:
    run = run_case(with_kyc(), file=FILE, answers=[REVIEWED], people=PEOPLE)
    started, done = guide_block("started kyc#1").splitlines()
    assert started in run.history and done in run.history
    assert run.reached("kyc") and run.closed


def test_a_workflow_step_is_checked_like_an_activity() -> None:
    # Its approval is asked, and given by a role that may approve its risk; then it starts, its key
    # in the input its contract names, and its output lands with the contract's sources.
    given: list[dict[str, Any]] = []

    def opening(inputs: dict[str, Any]) -> dict[str, Any]:
        given.append(inputs)
        return {"account_id": "a-1"}

    definition = with_kyc(account=open_account(approval=APPROVAL), welcome=welcome("kyc.status"))
    definition["steps"]["welcome"]["inputs"]["template"] = {"var": "account.account_id"}
    definition["steps"]["welcome"]["requires"] = ["account"]
    run = run_case(
        definition,
        file=FILE,
        answers=[REVIEWED, ("account", "approve", "sam")],
        people=PEOPLE,
        catalog=with_accounts(),
        workflows={"accounts.open@1": opening},
    )
    assert given == [{"customer_id": "c-1", "idempotency_key": "memory/account#1"}]
    assert "asked account.approval#1: approval of account by support-lead" in run.history
    assert "account#1 done, giving account_id from system:accounts" in run.history
    assert run.needs_attention == [] and run.closed
    # Ana, in support, may not approve a high-risk step: the same check as an activity's.
    refused = run_case(
        with_kyc(account=open_account(approval=APPROVAL | {"roles": ["support"]})),
        file=FILE,
        answers=[REVIEWED],
        people=PEOPLE,
        catalog=with_accounts(),
    )
    assert "approval of account by support" in refused.waiting_for
    try:
        run_case(
            with_kyc(account=open_account(approval=APPROVAL | {"roles": ["support"]})),
            file=FILE,
            answers=[REVIEWED, ("account", "approve", "ana")],
            people=PEOPLE,
            catalog=with_accounts(),
        )
    except AnswerRefused as error:
        assert "high" in str(error)
    else:
        raise AssertionError("ana approved a high-risk workflow")


def test_a_failed_workflow_step_is_retried_with_the_same_key() -> None:
    keys: list[str] = []

    def down_once(inputs: dict[str, Any]) -> dict[str, Any]:
        keys.append(inputs["idempotency_key"])
        if len(keys) == 1:
            raise ConnectionError("accounts system unreachable")
        return {"account_id": "a-1"}

    script = [REVIEWED, ("account", "approve", "sam")]
    failed = run_case(
        with_kyc(account=open_account(approval=APPROVAL)),
        file=FILE,
        answers=script,
        people=PEOPLE,
        catalog=with_accounts(),
        workflows={"accounts.open@1": down_once},
    )
    assert failed.needs_attention == [
        "account#1: accounts.open@1 failed with ConnectionError: ‹sensitive›"
    ]
    keys.clear()
    retried = run_case(
        with_kyc(account=open_account(approval=APPROVAL)),
        file=FILE,
        answers=[*script, retry("account#1", "omar")],
        people=PEOPLE,
        catalog=with_accounts(),
        workflows={"accounts.open@1": down_once},
    )
    # The same run, so the same key: an account opened before the failure isn't opened twice.
    assert keys == ["memory/account#1", "memory/account#1"]
    assert retried.closed and "account#1 done, giving account_id from system:accounts" in (
        retried.history
    )


def test_a_workflow_finishing_after_the_close_flags_the_case() -> None:
    definition = with_kyc()
    definition["close_reasons"] = {
        "duplicate": {"display": {"title": "Duplicate request"}, "roles": ["support"]}
    }
    run = run_case(
        definition,
        file=FILE,
        answers=[close("duplicate", "ana"), finish("kyc#1")],
        people=PEOPLE,
        held=["kyc"],
    )
    # It ran to its end, as a running activity does (brief, D10); what it gave still lands, and a
    # person is told it finished after the close.
    done = (
        "kyc#1 done, giving analyst_notes from untrusted:llm; contact_email from "
        "untrusted:undeclared; risk_score from system:kyc; status from system:kyc"
    )
    assert done in run.history
    assert run.flags == ["kyc#1 completed after the close was requested"]
    assert run.closed


# --- Layer 11c: stopping a workflow step, cancellable or not (brief, D40) ---

KYC_CANCELLABLE = "kyc.check@3"


def with_cancellable_kyc() -> Catalog:
    """The development catalog, and `kyc.check@3`: the same check, whose team promises it stops
    cleanly when cancelled."""
    catalog = copy.deepcopy(CATALOG)
    kyc = catalog.workflow("kyc.check@1")
    catalog.register(kyc.model_copy(update={"version": 3, "cancellable": True}))
    return catalog


def cancellable_kyc(**changes: Any) -> dict[str, Any]:
    """The refund with its customer checked by `kyc.check@3`, a support task logging a
    withdrawal, a rule stopping the check once it is logged, and a close reason."""
    definition = with_kyc()
    definition["steps"]["kyc"]["workflow"] = KYC_CANCELLABLE
    definition["milestones"] = {"withdrawn": {"display": {"title": "Withdrawn"}}}
    definition["steps"]["log_withdrawal"] = {
        "kind": "task",
        "display": {"title": "Log the customer's withdrawal"},
        "roles": ["support"],
        "automatic": False,
        "proposed_by": ["support"],
        "outcomes": {"logged": {"display": {"title": "Withdrawn"}, "reaches": ["withdrawn"]}},
    }
    definition["rules"] = {
        "withdraw": {
            "display": {"title": "Stop the check when the customer withdraws"},
            "on": {"reached": "withdrawn"},
            "then": {"stop": ["kyc"]},
        }
    }
    definition["close_reasons"] = {
        "duplicate": {"display": {"title": "Duplicate request"}, "roles": ["support"]}
    }
    return definition | changes


WITHDRAWS = [propose("log_withdrawal", "ana"), ("log_withdrawal", "logged", "ana")]


def test_a_close_cancels_a_cancellable_workflow_step() -> None:
    # Closed as a duplicate while the cancellable check runs: through the one place that stops
    # every running child, it is cancelled, the case waits for it to end, and flags it, since what
    # it did before the cancellation stands. Until 11c every workflow step finished (brief, D10,
    # D29, D40); one that isn't cancellable still does (test_a_workflow_finishing_after_the_close_
    # flags_the_case, above).
    run = run_case(
        cancellable_kyc(),
        file=FILE,
        answers=[close("duplicate", "ana")],
        people=PEOPLE,
        held=["kyc"],
        catalog=with_cancellable_kyc(),
        workflows={KYC_CANCELLABLE: fake_kyc},
    )
    assert run.history[-5:] == [
        "ana closed the case as duplicate, as support",
        "cancelled review#1: closed as duplicate by ana",
        "kyc#1 cancelled: the case is closing",
        "flagged: kyc#1 cancelled after the close was requested",
        "closed: duplicate, by ana",
    ]
    assert run.flags == ["kyc#1 cancelled after the close was requested"]
    assert not run.reached("kyc")
    said = " ".join(GUIDE.read_text().split())  # the guide's lines, line breaks aside
    assert "`kyc#1 cancelled: the case is closing`" in said
    assert "`flagged: kyc#1 cancelled after the close was requested`" in said


def test_a_stopped_workflow_step_is_cancelled_only_if_cancellable() -> None:
    # A rule's stop goes through the same place: a cancellable check is cancelled and flagged; one
    # that isn't runs to its end, its output landing, and is flagged (brief, D40).
    cancelled = run_case(
        cancellable_kyc(),
        file=FILE,
        answers=WITHDRAWS,
        people=PEOPLE,
        held=["kyc"],
        catalog=with_cancellable_kyc(),
        workflows={KYC_CANCELLABLE: fake_kyc},
    )
    stopping = cancelled.history.index("withdraw#1 on reached withdrawn: stopping kyc")
    assert cancelled.history[stopping + 1 :] == [
        "kyc#1: stop requested by withdraw#1",
        "kyc#1 cancelled: stopped by withdraw#1",
        "flagged: kyc#1 cancelled after its stop was requested by withdraw#1",
    ]
    assert cancelled.status == "open"  # the review still waits
    said = " ".join(GUIDE.read_text().split())  # the guide quotes both, line breaks aside
    assert "`kyc#1 cancelled: stopped by withdraw#1`" in said
    assert "`flagged: kyc#1 cancelled after its stop was requested by withdraw#1`" in said
    uncancellable = cancellable_kyc()
    uncancellable["steps"]["kyc"]["workflow"] = "kyc.check@1"
    finished = run_case(
        uncancellable,
        file=FILE,
        answers=[*WITHDRAWS, finish("kyc#1")],
        people=PEOPLE,
        held=["kyc"],
    )
    stopping = finished.history.index("withdraw#1 on reached withdrawn: stopping kyc")
    assert finished.history[stopping + 1 :] == [
        "kyc#1: stop requested by withdraw#1",
        (
            "kyc#1 done, giving analyst_notes from untrusted:llm; contact_email from "
            "untrusted:undeclared; risk_score from system:kyc; status from system:kyc"
        ),
        "flagged: kyc#1 completed after its stop was requested by withdraw#1",
    ]


def test_a_child_is_never_stopped_twice() -> None:
    # Through `decide`, which gives the commands: the rule's stop asks for the check's
    # cancellation once; the close that follows, while the check still runs, asks nothing again
    # (brief, D40). In memory a cancelled child ends at once, so only `decide` shows it.
    case = parse_case(cancellable_kyc())
    catalog = with_cancellable_kyc()
    exact = FILE | {"amount": Decimal(40)}  # as the API passes it on
    roles = frozenset({"support"})
    state, commands = decide(case, catalog, CaseState("t"), Opened(exact, None, at=START))
    assert [type(command).__name__ for command in commands] == ["StartWorkflow"]
    state, commands = decide(
        case, catalog, state, Proposed("log_withdrawal", "ana", roles, at=START)
    )
    state, commands = decide(
        case, catalog, state, Answered("log_withdrawal#1", "logged", "ana", roles, at=START)
    )
    assert commands == [CancelWorkflow("kyc#1", "stopped by withdraw#1")]
    state, commands = decide(case, catalog, state, CloseAsked("duplicate", "ana", roles, at=START))
    assert commands == [] and state.phase == "closing"
    # Without the rule's stop, the close asks for it, once, with the close's reason.
    state, _ = decide(case, catalog, CaseState("t"), Opened(exact, None, at=START))
    state, commands = decide(case, catalog, state, CloseAsked("duplicate", "ana", roles, at=START))
    assert commands == [CancelWorkflow("kyc#1", "the case is closing")]


def test_a_cancellation_nobody_asked_for_needs_attention() -> None:
    # Fail closed, in `decide` too: a workflow step that ends cancelled though the case asked
    # nothing of it, neither a rule's stop nor a close, failed, and waits for a person; it is
    # never read as a close (brief, D17, D40).
    case = parse_case(cancellable_kyc())
    catalog = with_cancellable_kyc()
    exact = FILE | {"amount": Decimal(40)}  # as the API passes it on
    state, _ = decide(case, catalog, CaseState("t"), Opened(exact, None, at=START))
    state, _ = decide(case, catalog, state, WorkflowCancelled("kyc#1", at=START))
    assert state.history[-1] == (
        "kyc#1 failed: it ended cancelled, though the case asked nothing of it: retry it, or close "
        "the case"
    )
    assert [run.status for run in state.runs if run.entry == "kyc#1"] == ["failed"]
