"""Layer 9c: forgetting a case. The key provider's part, the definition's, and the case's.

See docs/layers/09-case-data.md (9c) and docs/guides/case-data.md ("Forgetting a person").
"""

import json
from pathlib import Path

import pytest
from test_case import LARGE, REVIEWED, SMALL, SMALL_REVIEW, closable
from test_sensitive import claim

from ventoux.case.definition import CaseInvalid, parse_case
from ventoux.case.forgetting import ForgetRefused
from ventoux.testing import close, finish, forget, run_case
from ventoux.tooling.keys import FileKeys, KeyRefused

NATIONAL_ID = "1 85 05 78 006 084 36"


def test_a_destroyed_key_is_gone_for_good(tmp_path: Path) -> None:
    keys = FileKeys(tmp_path / "keys.json")
    # Fail closed: a key never made can't be destroyed; there is no case to forget.
    with pytest.raises(
        KeyRefused, match="^there is no key for claim-9 to destroy: no case was opened with its ID$"
    ):
        keys.destroy("claim-9")
    keys.create("claim-7")
    sealed = keys.seal("claim-7", NATIONAL_ID.encode(), "sensitive/0")
    key = json.loads((tmp_path / "keys.json").read_text())["claim-7"]
    keys.destroy("claim-7")
    # The key's bytes are gone from the provider: nothing sealed with it opens again, nothing is
    # sealed with it again, and it is never made again, so the ID never opens a case again.
    assert key not in (tmp_path / "keys.json").read_text()
    forgotten = (
        "^the key of claim-7 was destroyed when it was forgotten: its sensitive values can't be "
        "read or written$"
    )
    with pytest.raises(KeyRefused, match=forgotten):
        keys.open("claim-7", sealed, "sensitive/0")
    with pytest.raises(KeyRefused, match=forgotten):
        keys.seal("claim-7", NATIONAL_ID.encode(), "sensitive/0")
    with pytest.raises(KeyRefused, match="^a key was already made for claim-7: open the case"):
        keys.create("claim-7")


def test_a_keys_state_tells_which_case_it_is(tmp_path: Path) -> None:
    # Temporal says the same of a case that ended and one that never was (slice 0): the provider
    # tells them apart, and remembers a destroyed key after Temporal has dropped its case.
    keys = FileKeys(tmp_path / "keys.json")
    keys.create("claim-7")
    assert keys.state("claim-9") == "never made"
    assert keys.state("claim-7") == "kept"
    keys.destroy("claim-7")
    assert FileKeys(tmp_path / "keys.json").state("claim-7") == "destroyed"
    # Destroying it again does nothing: a request retried after destroying it is safe.
    keys.destroy("claim-7")
    assert keys.state("claim-7") == "destroyed"


def test_a_definition_says_whether_it_may_be_forgotten() -> None:
    # Fail closed: a setting the engine doesn't know is refused, never read as a default.
    for wrong in ("sometimes", True, None):
        with pytest.raises(
            CaseInvalid, match="^forgetting: Input should be 'allowed', 'while_open' or 'never'$"
        ):
            parse_case({**claim(), "forgetting": wrong})
    # Unsaid, a case may be forgotten, open or closed; a definition keeping its records says so.
    assert parse_case(claim()).forgetting == "allowed"
    for kept in ("allowed", "while_open", "never"):
        assert parse_case({**claim(), "forgetting": kept}).forgetting == kept


# Ana and Sam work the refund; Pia and Olu may forget a case; Lee may not.
PEOPLE = {
    "ana": ["support"],
    "sam": ["support", "support-lead"],
    "lee": ["support-lead"],
    "pia": ["privacy"],
    "olu": ["privacy"],
}


def test_the_proposer_cannot_approve_forgetting() -> None:
    # The curriculum's negative test: erasure is a decision two people make (brief, D15, D32).
    with pytest.raises(
        ForgetRefused, match="^pia proposed forgetting memory, so cannot approve it$"
    ):
        run_case(closable(), file=SMALL, answers=[forget("pia", "pia")], people=PEOPLE)


@pytest.mark.parametrize(
    ("proposed_by", "approved_by", "message"),
    [
        ("lee", "olu", "forgetting memory is proposed by privacy, and lee has support-lead"),
        ("pia", "lee", "forgetting memory is approved by privacy, and lee has support-lead"),
        ("pia", "max", "forgetting memory is approved by privacy, and max has no role"),
    ],
)
def test_forgetting_needs_a_role_registered_to_forget(
    proposed_by: str, approved_by: str, message: str
) -> None:
    with pytest.raises(ForgetRefused, match=f"^{message}$"):
        run_case(closable(), file=SMALL, answers=[forget(proposed_by, approved_by)], people=PEOPLE)


def test_the_case_checks_forgetting_itself() -> None:
    # The request checks the same things first (slice 4); the case depends on nothing it did.
    # Each person is written as an identifier: `Pia` and `pia` would otherwise be two people.
    with pytest.raises(ForgetRefused, match="^'Pia' is not written as a person's identifier"):
        run_case(
            closable(),
            file=SMALL,
            answers=[forget("pia", "Pia")],
            people={**PEOPLE, "Pia": ["privacy"]},
        )
    # A case whose definition keeps its records is never forgotten (brief, D32).
    with pytest.raises(
        ForgetRefused,
        match=r"^memory keeps its records \(forgetting: never\): it can't be forgotten$",
    ):
        run_case(
            {**closable(), "forgetting": "never"},
            file=SMALL,
            answers=[forget("pia", "olu")],
            people=PEOPLE,
        )
    # A closed case has nothing left to close: on Temporal the request destroys its key without
    # it (slice 6); here the case refuses, as it refuses anything after it closed.
    with pytest.raises(ForgetRefused, match="^the case is closed: nothing records it any more$"):
        run_case(
            closable(),
            file=SMALL,
            answers=[SMALL_REVIEW, forget("pia", "olu")],
            people=PEOPLE,
        )


def test_forgetting_closes_an_open_case() -> None:
    # Waiting for its review: the task is cancelled, saying why, and the case closes at once.
    waiting = run_case(closable(), file=SMALL, answers=[forget("pia", "olu")], people=PEOPLE)
    assert waiting.closed
    assert waiting.waiting_for == []
    assert waiting.history[-3:] == [
        "forgetting approved by olu as privacy, proposed by pia as privacy",
        "cancelled review#1: the case is being forgotten",
        "closed: forgotten",
    ]
    # Paying: the payment can't be cut off halfway (brief, D10). It finishes, the case is
    # flagged for a person, and only then is it closed; its key goes after that (slice 5).
    paying = [SMALL_REVIEW, forget("pia", "olu")]
    closing = run_case(closable(), file=SMALL, answers=paying, people=PEOPLE, held=["pay"])
    assert closing.status == "closing"
    run = run_case(
        closable(), file=SMALL, answers=[*paying, finish("pay#1")], people=PEOPLE, held=["pay"]
    )
    assert run.flags == ["pay#1 completed after the close was requested"]
    assert run.history[-4:] == [
        "forgetting approved by olu as privacy, proposed by pia as privacy",
        "pay#1 done, giving refund_id from untrusted:undeclared",
        "flagged: pay#1 completed after the close was requested",
        "closed: forgotten",
    ]
    # Already closing (Ana closed it as a duplicate): it closes with its own reason, and the
    # request is recorded.
    run = run_case(
        closable(),
        file=SMALL,
        answers=[SMALL_REVIEW, close("duplicate", "ana"), forget("pia", "olu"), finish("pay#1")],
        people=PEOPLE,
        held=["pay"],
    )
    assert "forgetting approved by olu as privacy, proposed by pia as privacy" in run.history
    assert run.history[-1] == "closed: duplicate, by ana"
    # Waiting for a team lead's approval of the payment: the approval is cancelled too.
    approving = run_case(
        closable(), file=LARGE, answers=[REVIEWED, forget("pia", "olu")], people=PEOPLE
    )
    assert approving.history[-2:] == [
        "cancelled pay.approval#1: the case is being forgotten",
        "closed: forgotten",
    ]
