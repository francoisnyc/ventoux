"""Layer 9c: forgetting a case. The key provider's part, the definition's, and the case's.

See docs/layers/09-case-data.md (9c) and docs/guides/case-data.md ("Forgetting a person").
"""

import json
from pathlib import Path

import pytest

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
