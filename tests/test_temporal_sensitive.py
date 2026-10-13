"""Layer 9b on Temporal: keys, the codec, and no sensitive value in plain text anywhere.

See docs/layers/09-case-data.md (9b) and docs/guides/case-data.md ("On Temporal").
"""

from pathlib import Path

import pytest

from ventoux.tooling.keys import FileKeys, KeyRefused

NATIONAL_ID = "1 85 05 78 006 084 36"


def test_a_key_is_made_once(tmp_path: Path) -> None:
    keys = FileKeys(tmp_path / "keys.json")
    keys.create("claim-7")
    # Never made again, even by another provider on the same file: a reused ID never inherits
    # or remakes a case's key (brief, D31).
    with pytest.raises(KeyRefused, match="^a key was already made for claim-7: open the case"):
        FileKeys(tmp_path / "keys.json").create("claim-7")
    # A case without one has nothing to seal or open with: fail closed, never plain text.
    no_key = "^there is no key for claim-8, so its sensitive values can't be read or written$"
    with pytest.raises(KeyRefused, match=no_key):
        keys.seal("claim-8", NATIONAL_ID.encode(), "sensitive/0")
    with pytest.raises(KeyRefused, match=no_key):
        keys.open("claim-8", b"anything", "sensitive/0")


def test_a_part_opens_only_where_it_was_sealed(tmp_path: Path) -> None:
    keys = FileKeys(tmp_path / "keys.json")
    keys.create("claim-7")
    keys.create("claim-8")
    sealed = keys.seal("claim-7", NATIONAL_ID.encode(), "sensitive/0")
    assert NATIONAL_ID.encode() not in sealed
    assert keys.open("claim-7", sealed, "sensitive/0") == NATIONAL_ID.encode()
    # The key never leaves the provider: it seals and opens, and nothing else reads it.
    assert not any(
        name.startswith(("key", "get")) for name in dir(keys) if not name.startswith("_")
    )
    damaged = sealed[:-1] + bytes([sealed[-1] ^ 1])
    for case, data, part in [
        ("claim-8", sealed, "sensitive/0"),  # another case
        ("claim-7", sealed, "sensitive/1"),  # another place in the payload
        ("claim-7", damaged, "sensitive/0"),
    ]:
        with pytest.raises(KeyRefused, match=f"^a sealed part of {case} doesn't open"):
            keys.open(case, data, part)
