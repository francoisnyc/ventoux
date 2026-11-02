"""Attachments: the ID a document store issued for a file, checked when a person gives it.

See docs/layers/16-field-types.md (16c), docs/guides/case-data.md ("Attachments") and brief D68.
"""

from typing import Annotated, Any

import pytest
from pydantic import BaseModel
from test_case import contract

from ventoux.case.definition import parse_case
from ventoux.case.validate import validate_case
from ventoux.core.catalog import Catalog
from ventoux.core.output_sources import source
from ventoux.core.references import reference


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


# --- Slice 2: a store is a registered system with a read-only check that it issued an ID ---


class DocumentAsked(BaseModel):
    attachment: Annotated[str, reference("documents")]  # the ID a person gave


class DocumentIssued(BaseModel):
    issued: Annotated[bool, source("system:documents")]  # whether the store issued it


class Code(BaseModel):
    code: str  # not a reference: the store isn't said


class Found(BaseModel):
    found: Annotated[bool, source("system:documents")]


class IssuedByCrm(BaseModel):
    issued: Annotated[bool, source("system:crm")]  # another system's word for it


def registered(catalog: Catalog, name: str, given: type[BaseModel], gives: type[BaseModel]) -> str:
    catalog.register(contract(name, given, gives))
    return f"{name}@1"


def test_a_stores_check_that_writes_is_refused() -> None:
    # A store's check only asks: it never changes the store it asks (brief, D68).
    catalog = no_stores()
    catalog.register(
        contract(
            "documents.keep",
            DocumentAsked,
            DocumentIssued,
            effect="write",
            idempotency_key="attachment",
        )
    )
    with pytest.raises(ValueError) as refused:
        catalog.register_document_store("documents", "documents.keep@1")
    assert str(refused.value) == (
        "documents.keep@1 is effect: write, and a document store's check only reads: register a "
        "read-only activity that says whether documents issued an ID"
    )


@pytest.mark.parametrize(
    ("given", "gives", "refused"),
    [
        (
            Code,
            DocumentIssued,
            (
                "documents.code@1 takes code, and a document store's check takes one value, "
                "attachment, a reference to documents: declare it Annotated[str, "
                'reference("documents")]'
            ),
        ),
        (
            DocumentAsked,
            Found,
            (
                "documents.code@1 gives found (system:documents), and a document store's check "
                "gives one truth value, issued, from system:documents: declare it "
                'Annotated[bool, source("system:documents")]'
            ),
        ),
        (
            DocumentAsked,
            IssuedByCrm,
            (
                "documents.code@1 gives issued (system:crm), and a document store's check gives "
                "one truth value, issued, from system:documents: declare it Annotated[bool, "
                'source("system:documents")]'
            ),
        ),
    ],
    ids=["input not a reference", "output not issued", "issued by another system"],
)
def test_a_stores_check_of_another_shape_is_refused(
    given: type[BaseModel], gives: type[BaseModel], refused: str
) -> None:
    catalog = no_stores()
    check = registered(catalog, "documents.code", given, gives)
    with pytest.raises(ValueError) as said:
        catalog.register_document_store("documents", check)
    assert str(said.value) == refused


def test_a_second_check_for_one_store_is_refused() -> None:
    # One way to ask a store, so two cases never check one ID two ways (brief, D68).
    catalog = no_stores()
    catalog.register_document_store(
        "documents", registered(catalog, "documents.issued", DocumentAsked, DocumentIssued)
    )
    other = registered(catalog, "documents.known", DocumentAsked, DocumentIssued)
    with pytest.raises(ValueError) as refused:
        catalog.register_document_store("documents", other)
    assert str(refused.value) == (
        "documents is a document store already, checked by documents.issued@1: a store has one "
        "check"
    )


def test_a_read_only_check_of_the_right_shape_makes_its_system_a_store() -> None:
    catalog = no_stores()
    catalog.register_document_store(
        "documents", registered(catalog, "documents.issued", DocumentAsked, DocumentIssued)
    )
    assert catalog.document_store("documents") == "documents.issued@1"
    assert errors(claim(), catalog) == []
