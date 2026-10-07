"""Input policies: which sources an activity's input accepts (layer 4).

See docs/layers/04-provenance.md and docs/guides/activities.md.
"""

import pytest

from ventoux.core.policy import only_from, trusted_only


def test_trusted_only_refuses_untrusted_data() -> None:
    refused = trusted_only().refuses(frozenset({"system:crm", "untrusted:llm"}))
    assert refused == "it comes from untrusted:llm"


def test_a_source_the_engine_does_not_know_is_refused() -> None:
    # Fail closed: `trusted:` is no origin (brief, D12), so it is unknown, never trusted.
    refused = trusted_only().refuses(frozenset({"trusted:portal"}))
    assert refused == "it comes from trusted:portal, a source Ventoux doesn't recognise"


def test_only_from_refuses_a_value_from_no_system() -> None:
    # A value written in the definition has no source: it comes from no system at all.
    assert only_from("payments").refuses(frozenset()) == "it comes from no system"


def test_only_from_refuses_another_system() -> None:
    refused = only_from("payments").refuses(frozenset({"system:payments", "system:crm"}))
    assert refused == "it comes from system:crm"


def test_only_from_names_a_system() -> None:
    # With no system named, no value could ever pass: a mistake, refused where it is written.
    with pytest.raises(ValueError, match="only_from names at least one system"):
        only_from()


@pytest.mark.parametrize(
    "sources",
    [
        frozenset({"system:crm", "person:ana"}),  # a system and a person: both trusted
        frozenset({"case"}),  # a plan field the case gives, checked again when the step runs
        frozenset(),  # a value written in the definition, reviewed like code
    ],
)
def test_trusted_only_accepts_a_system_a_person_and_the_definition(
    sources: frozenset[str],
) -> None:
    assert trusted_only().refuses(sources) is None


def test_only_from_accepts_the_systems_named() -> None:
    policy = only_from("payments", "ledger")
    assert policy.refuses(frozenset({"system:payments", "system:ledger"})) is None


@pytest.mark.parametrize("sources", [frozenset({"person:ana"}), frozenset({"case"})])
def test_only_from_refuses_a_person_and_the_case(sources: frozenset[str]) -> None:
    # A person or a plan field is trusted, but no system: `only_from` asks for a system.
    assert only_from("payments").refuses(sources) is not None


def test_each_policy_reads_as_one_sentence() -> None:
    # The same words in validator errors, approval sheets and diffs (brief, D21).
    assert trusted_only().describe() == (
        "only from a system or a person, never from untrusted data"
    )
    assert only_from("payments", "ledger").describe() == "only from payments or ledger"
