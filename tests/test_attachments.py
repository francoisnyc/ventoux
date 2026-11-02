"""Attachments: the ID a document store issued for a file, checked when a person gives it.

See docs/layers/16-field-types.md (16c), docs/guides/case-data.md ("Attachments") and brief D68.
"""

from typing import Any

from ventoux.case.definition import parse_case
from ventoux.case.validate import validate_case
from ventoux.core.catalog import Catalog


def claim(store: str = "documents") -> dict[str, Any]:
    """A claim whose adjuster attaches the receipt, an attachment in `store`."""
    return {
        "case": "claim",
        "display": {"title": "Insurance claim"},
        "fields": {
            "receipt": {
                "type": "attachment",
                "store": store,
                "display": {"title": "The receipt"},
            }
        },
        "steps": {
            "assess": {
                "kind": "task",
                "display": {"title": "Assess the claim"},
                "roles": ["adjuster"],
                "outcomes": {
                    "accept": {"display": {"title": "Accept the claim"}, "sets": ["receipt"]},
                    "deny": {"display": {"title": "Deny the claim"}},
                },
            }
        },
    }


def no_stores() -> Catalog:
    """A catalog with the systems `documents` and `crm`, neither of them a document store yet."""
    catalog = Catalog()
    for system in ("crm", "documents"):
        catalog.register_system(system)
    catalog.register_role("adjuster")
    return catalog


def errors(definition: dict[str, Any], catalog: Catalog) -> list[str]:
    """What validation refuses, as `path: CODE: message`."""
    found = validate_case(parse_case(definition), catalog)
    return [f"{i.path}: {i.code}: {i.message}" for i in found if i.severity == "error"]


# --- Slice 1: the curriculum's: an attachment naming no registered store is refused ---


def test_an_attachment_in_a_system_nobody_registered_is_refused() -> None:
    # A typo in the store's name is caught before any case opens (brief, D30) (brief, D68).
    assert errors(claim("ledgers"), no_stores()) == [
        (
            "fields.receipt: UNKNOWN_SYSTEM: receipt is an attachment in ledgers, which is not a "
            "registered system: the systems are crm, documents; use one of them, or ask the "
            "platform team to register it"
        )
    ]


def test_an_attachment_in_a_system_that_is_not_a_store_is_refused() -> None:
    # Fail closed: nothing could say the ID was issued, nor open the file (brief, D68).
    assert errors(claim("crm"), no_stores()) == [
        (
            "fields.receipt: NOT_A_STORE: crm is not a document store: register it with "
            "register_document_store, or make receipt a reference to crm"
        )
    ]
