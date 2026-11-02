"""Attachments: the ID a document store issued for a file, checked when a person gives it.

See docs/layers/16-field-types.md (16c), docs/guides/case-data.md ("Attachments") and brief D68.
"""

import copy
from typing import Annotated, Any

import pytest
from pydantic import BaseModel
from test_case import contract

from ventoux.case.answers import AnswerRefused
from ventoux.case.definition import parse_case
from ventoux.case.validate import validate_case
from ventoux.core.catalog import Catalog
from ventoux.core.expressions import (
    AttachmentType,
    BooleanType,
    ExpressionInvalid,
    FieldType,
    OptionType,
    ReferenceType,
    StringType,
    check,
    parse_expression,
)
from ventoux.core.output_sources import source
from ventoux.core.references import reference
from ventoux.core.sensitive import Sensitive
from ventoux.testing import CATALOG, CaseRefused, ChangeRefused, edit, finish, run_case
from ventoux.tooling.resolvers import Resolvers, ShowRefused, Viewer


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


# --- Slice 3: only a person attaches a file, in a task's answer ---


def stored() -> Catalog:
    """The development catalog, with `documents` a store, checked by `documents.issued@1`."""
    catalog = copy.deepcopy(CATALOG)
    catalog.register_document_store(
        "documents", registered(catalog, "documents.issued", DocumentAsked, DocumentIssued)
    )
    return catalog


def with_photo() -> dict[str, Any]:
    """The claim, with `photo`, an attachment no task sets: a person's answer sets `receipt`,
    and the one-source rule already keeps rules and the opening off it."""
    definition = claim()
    definition["fields"]["photo"] = {
        "type": "attachment",
        "store": "documents",
        "display": {"title": "A photo of the damage"},
    }
    return definition


def test_an_event_carrying_an_attachment_is_refused() -> None:
    # Only a person attaches a file: nothing would check an ID an event carried (brief, D68).
    definition = claim()
    definition["events"] = {
        "uploaded": {
            "display": {"title": "The customer uploaded a file"},
            "sent_by": {"system": "portal"},
            "payload": {
                "file": {"type": "attachment", "store": "documents", "display": {"title": "File"}}
            },
        }
    }
    assert errors(definition, stored()) == [
        (
            "events.uploaded.payload.file: ATTACHMENT_NOT_GIVEN_BY_A_PERSON: file is an attachment "
            "in documents, and only a person's answer gives one, when it can be checked: make it a "
            "reference to documents"
        )
    ]


def test_a_rule_setting_an_attachment_is_refused() -> None:
    definition = with_photo()
    definition["rules"] = {
        "photo_is_receipt": {
            "display": {"title": "Use the receipt as the photo"},
            "on": {"answered": "assess"},
            "then": {"set": {"photo": {"var": "receipt"}}},
        }
    }
    assert errors(definition, stored()) == [
        (
            "rules.photo_is_receipt.then.set.photo: ATTACHMENT_NOT_GIVEN_BY_A_PERSON: photo is an "
            "attachment in documents, and only a person's answer gives one, when it can be "
            "checked: set it in a task's form"
        )
    ]


def test_an_attachment_given_at_the_opening_is_refused() -> None:
    with pytest.raises(CaseRefused) as refused:
        run_case(
            with_photo(),
            file={"photo": "doc-7f3a"},
            answers=[],
            people={"ana": ["adjuster"]},
            catalog=stored(),
        )
    assert str(refused.value) == (
        "photo is an attachment in documents, and only a person's answer gives one, when it can "
        "be checked: leave it out of the opening"
    )


@pytest.mark.parametrize(
    ("declared", "refused"),
    [
        (
            {"type": "attachment", "store": "documents"},
            (
                "fields.seen: CHECKED_IN_A_LIST: seen.item is an attachment in documents, and a "
                "list's fields are never checked: make it a reference to documents"
            ),
        ),
        (
            {"type": "option", "system": "branches"},
            (
                "fields.seen: CHECKED_IN_A_LIST: seen.item is an option of branches, and a list's "
                "fields are never checked: make it a reference to branches"
            ),
        ),
    ],
    ids=["an attachment", "an option"],
)
def test_a_checked_field_in_a_list_is_refused(declared: dict[str, str], refused: str) -> None:
    # Nothing could fill it, and nothing would check it: a form and the opening give no list, and
    # an activity's contract declares neither (brief, D67) (brief, D68).
    definition = claim()
    definition["fields"]["seen"] = {
        "type": "list",
        "fields": {"item": declared},
        "display": {"title": "Seen"},
    }
    assert errors(definition, stored()) == [refused]


# --- Slice 4: an ID the store didn't issue is refused and recorded; one it issued is taken ---

ISSUED = {"doc-7f3a"}  # what the documents store issued, in these tests
ADJUSTERS = {"ana": ["adjuster"]}


def issued(inputs: dict[str, Any]) -> dict[str, Any]:
    """The documents store's answer: whether it issued the ID asked about."""
    return {"issued": inputs["attachment"] in ISSUED}


def test_an_id_the_store_did_not_issue_is_refused_and_the_refusal_recorded() -> None:
    run = run_case(
        claim(),
        file={},
        answers=[
            ("assess", "accept", "ana", {"receipt": "doc-0000"}),  # no such document
            ("assess", "accept", "ana", {"receipt": "doc-7f3a"}),  # corrected
        ],
        people=ADJUSTERS,
        activities={"documents.issued@1": issued},
        catalog=stored(),
    )
    # The refusal names the field and the store, never the ID (brief, D30) (brief, D68); the task
    # stays open, and the corrected answer is taken, saying which check vouched for it.
    assert run.history == [
        "opened by system:opener, with nothing",
        "started assess#1: waiting for accept or deny by adjuster",
        "refused ana's answer accept: receipt is not a document documents issued",
        "ana answered assess#1 accept as adjuster, setting receipt, checked by documents.issued@1",
        "assess#1 done",
        "closed: nothing left to do",
    ]
    assert run.state.values["receipt"] == "doc-7f3a"


def test_an_attachment_comes_from_the_person_and_the_store() -> None:
    run = run_case(
        claim(),
        file={},
        answers=[("assess", "accept", "ana", {"receipt": "doc-7f3a"})],
        people=ADJUSTERS,
        activities={"documents.issued@1": issued},
        catalog=stored(),
    )
    # Ana attached it, and the store vouched that it issued it (brief, D68).
    assert run.state.sources["receipt"] == frozenset({"person:ana", "system:documents"})
    assert run.state.sources["assess.outcome"] == frozenset({"person:ana"})


# --- Slice 5: never the bytes: an ID of more than 200 characters is refused, never quoted ---


def test_an_id_longer_than_200_characters_is_refused_before_the_store_is_asked() -> None:
    # A file pasted where its ID belongs never lands, and the store is never asked: the refusal
    # says how an attachment is given, never what was given (brief, D30) (brief, D68).
    asked: list[str] = []

    def counted(inputs: dict[str, Any]) -> dict[str, Any]:
        asked.append(inputs["attachment"])
        return issued(inputs)

    pasted = "%PDF-1.7 " + "x" * 192  # 201 characters
    with pytest.raises(AnswerRefused) as refused:
        run_case(
            claim(),
            file={},
            answers=[("assess", "accept", "ana", {"receipt": pasted})],
            people=ADJUSTERS,
            activities={"documents.issued@1": counted},
            catalog=stored(),
        )
    assert str(refused.value) == (
        "receipt is an attachment, the ID a store issued, at most 200 characters: upload the file "
        "to documents and give its ID"
    )
    assert asked == []
    # 200 is an ID: asked, and refused by the store as any ID it didn't issue.
    run = run_case(
        claim(),
        file={},
        answers=[("assess", "accept", "ana", {"receipt": "d" * 200})],
        people=ADJUSTERS,
        activities={"documents.issued@1": counted},
        catalog=stored(),
    )
    assert asked == ["d" * 200]
    assert "refused ana's answer accept: receipt is not a document documents issued" in run.history


# --- Slice 6: a check that can't be made takes nothing; one answer may wait for two checks ---


def broken(inputs: dict[str, Any]) -> dict[str, Any]:
    """The documents store is down."""
    raise RuntimeError("documents is down")


@pytest.mark.parametrize(
    ("check", "why"),
    [
        (broken, "documents.issued@1 failed with RuntimeError: ‹sensitive›"),
        (
            lambda _: {"yes": True},
            (
                "documents.issued@1 gave an output its contract doesn't declare: issued: Field "
                "required"
            ),
        ),
        (
            lambda _: {"issued": "yes"},
            (
                "documents.issued@1 gave issued as a string, and a document store's check "
                "answers true or false"
            ),
        ),
    ],
    ids=["the check fails", "another shape", "not true or false"],
)
def test_an_attachment_whose_check_cannot_be_made_is_not_taken(check: Any, why: str) -> None:
    # Fail closed: never read as issued; and answering again fixes it, so the case doesn't need
    # attention (brief, D68).
    run = run_case(
        claim(),
        file={},
        answers=[("assess", "accept", "ana", {"receipt": "doc-7f3a"})],
        people=ADJUSTERS,
        activities={"documents.issued@1": check},
        catalog=stored(),
    )
    assert run.history[-1] == (
        f"ana's answer accept to assess#1 is not taken: {why}; the task waits for an answer"
    )
    assert "receipt" not in run.state.values
    assert list(run.state.waiting) == ["assess#1"]
    assert run.needs_attention == []


def with_branch() -> dict[str, Any]:
    """The claim, its acceptance also saying which branch handles it, an option of branches."""
    definition = claim()
    definition["fields"]["branch"] = {
        "type": "option",
        "system": "branches",
        "display": {"title": "Branch handling the claim"},
    }
    definition["steps"]["assess"]["outcomes"]["accept"]["sets"] = ["branch", "receipt"]
    return definition


BOTH = ("assess", "accept", "ana", {"branch": "BR-0142", "receipt": "doc-7f3a"})
CHECKS = {
    "branches.holds@1": lambda i: {"held": i["option"] == "BR-0142"},
    "documents.issued@1": issued,
}


def test_an_answer_with_an_option_and_an_attachment_waits_for_both_checks() -> None:
    def answered(*more: Any) -> Any:
        return run_case(
            with_branch(),
            file={},
            answers=[BOTH, *more],
            people=ADJUSTERS,
            activities=CHECKS,
            catalog=stored(),
            held=["assess"],  # both checks keep running until finished
        )

    # One check back: the answer still waits for the other, and nothing has landed.
    one = answered(finish("assess#1.receipt"))
    assert "receipt" not in one.state.values and "branch" not in one.state.values
    # Both back: taken, saying both checks, each value from the person and its own system.
    both = answered(finish("assess#1.receipt"), finish("assess#1.branch"))
    assert (
        "ana answered assess#1 accept as adjuster, setting branch and receipt, checked by "
        "branches.holds@1 and documents.issued@1"
    ) in both.history
    assert both.state.sources["branch"] == frozenset({"person:ana", "system:branches"})
    assert both.state.sources["receipt"] == frozenset({"person:ana", "system:documents"})


def test_one_check_that_doesnt_vouch_refuses_the_whole_answer() -> None:
    run = run_case(
        with_branch(),
        file={},
        answers=[("assess", "accept", "ana", {"branch": "BR-0142", "receipt": "doc-0000"})],
        people=ADJUSTERS,
        activities=CHECKS,
        catalog=stored(),
    )
    # The branch was held, the receipt not issued: nothing the answer set lands (brief, D68).
    assert "refused ana's answer accept: receipt is not a document documents issued" in run.history
    assert "branch" not in run.state.values and "receipt" not in run.state.values
    assert list(run.state.waiting) == ["assess#1"]


# --- Slice 7: an edit never sets an attachment ---


def test_an_edit_of_an_attachment_is_refused_when_it_is_proposed() -> None:
    # An edit is checked for its type, never by the store: an attachment is given only in a
    # person's answer, where its store vouches for it (brief, D52) (brief, D68).
    definition = claim() | {
        "stays_open": True,
        "close_reasons": {"done": {"display": {"title": "Done"}, "roles": ["adjuster"]}},
    }
    both = ["adjuster", "support-lead"]  # each sees the receipt, and may edit or approve
    with pytest.raises(ChangeRefused) as refused:
        run_case(
            definition,
            file={},
            answers=[
                ("assess", "accept", "ana", {"receipt": "doc-7f3a"}),
                edit("receipt", "doc-0000", "sam"),  # not a document the store issued
                ("case.change#1", "approve", "lee"),
            ],
            people={"ana": ["adjuster"], "sam": both, "lee": both},
            activities={"documents.issued@1": issued},
            catalog=stored(),
        )
    assert str(refused.value) == (
        "receipt is an attachment in documents, given only by a person's answer, where documents "
        "checks it: an edit is never checked, so give it in the answer to the task that sets it"
    )


# --- Slice 8: expressions read an attachment like a reference to its store ---

TYPES: dict[str, FieldType] = {
    "receipt": AttachmentType(store="documents"),
    "photo": AttachmentType(store="documents"),
    "scan": ReferenceType(system="documents"),
    "kept_as": OptionType(system="documents"),  # an option, naming the same system
    "elsewhere": AttachmentType(store="crm"),
}


@pytest.mark.parametrize(
    "other", ["photo", "scan"], ids=["an attachment in its store", "a reference to its store"]
)
def test_an_attachment_compares_with_a_value_of_its_store(other: str) -> None:
    compared = parse_expression({"==": [{"var": "receipt"}, {"var": other}]})
    assert check(compared, TYPES) == BooleanType()


@pytest.mark.parametrize(
    ("other", "refused"),
    [
        (
            "elsewhere",
            (
                "==[1]: `==` compares values of the same type, and this is an attachment in "
                "crm, not an attachment in documents"
            ),
        ),
        (
            "kept_as",
            (
                "==[1]: `==` compares values of the same type, and this is an option of "
                "documents, not an attachment in documents"
            ),
        ),
    ],
    ids=["an attachment in another store", "an option of the same system"],
)
def test_an_attachment_never_compares_with_another_kind_or_store(other: str, refused: str) -> None:
    # An option is checked against a list, an attachment against what a store issued: the same
    # system's name says nothing of which (brief, D68).
    with pytest.raises(ExpressionInvalid) as raised:
        check(parse_expression({"==": [{"var": "receipt"}, {"var": other}]}), TYPES)
    assert str(raised.value) == refused


def test_string_and_exists_read_an_attachment() -> None:
    assert check(parse_expression({"string": [{"var": "receipt"}]}), TYPES) == StringType()
    assert check(parse_expression({"exists": "receipt"}), TYPES) == BooleanType()


class Filed(BaseModel):
    document: Annotated[str, reference("documents")]  # a reference to the document to file


class Filing(BaseModel):
    filed: bool


def test_an_attachment_goes_where_a_reference_to_its_store_is_wanted() -> None:
    # An attachment is a reference to its store, and a checked one (brief, D68).
    catalog = stored()
    catalog.register(contract("documents.file", Filed, Filing))
    definition = claim()
    definition["steps"]["file"] = {
        "kind": "activity",
        "display": {"title": "File the receipt"},
        "activity": "documents.file@1",
        "requires": ["assess"],
        "inputs": {"document": {"var": "receipt"}},
    }
    assert errors(definition, catalog) == []


# --- Slice 9: a file is opened through its store's resolver, as the person looking ---

ADJUSTER = Viewer("lee", ("adjuster",))


def attached(definition: dict[str, Any] | None = None, people: Any = None) -> Any:
    """The claim with its receipt attached by Ana, `doc-7f3a`, issued by the store."""
    return run_case(
        definition or claim(),
        file={},
        answers=[("assess", "accept", "ana", {"receipt": "doc-7f3a"})],
        people=people or {"ana": ["adjuster"], "lee": ["adjuster"]},
        activities={"documents.issued@1": issued},
        catalog=stored(),
    )


def store_resolvers(asked: list[tuple[str, Viewer]]) -> Resolvers:
    """The documents store's resolver, recording what it is asked: a link, as the viewer."""

    def documents_file(reference: str, viewer: Viewer) -> dict[str, object]:
        asked.append((reference, viewer))
        return {"link": f"https://documents.example/{reference}?as={viewer.person}"}

    resolvers = Resolvers(stored())
    resolvers.register("documents", documents_file)
    return resolvers


def test_an_attachment_is_opened_through_its_store_as_the_viewer() -> None:
    # The store is asked on the viewer's behalf, so its own permissions decide; what it returns
    # never enters the case (brief, D16) (brief, D68).
    asked: list[tuple[str, Viewer]] = []
    run = attached()
    shown = store_resolvers(asked).show(run.view(roles=ADJUSTER.roles), "receipt", ADJUSTER)
    assert shown == {"link": "https://documents.example/doc-7f3a?as=lee"}
    assert asked == [("doc-7f3a", ADJUSTER)]
    assert "link" not in " ".join(run.history)


def test_a_hidden_attachment_has_nothing_to_open() -> None:
    # Ventoux may hide more than the store, never show more (brief, D16).
    definition = claim()
    definition["fields"]["receipt"]["visible_to"] = ["claims-sensitive"]
    asked: list[tuple[str, Viewer]] = []
    run = attached(definition, {"ana": ["adjuster", "claims-sensitive"], "lee": ["adjuster"]})
    with pytest.raises(ShowRefused) as refused:
        store_resolvers(asked).show(run.view(roles=ADJUSTER.roles), "receipt", ADJUSTER)
    assert str(refused.value) == "receipt is hidden from you: it needs claims-sensitive"
    assert asked == []


def test_a_sensitive_attachment_keeps_its_id_wrapped() -> None:
    # Its ID is sealed as any sensitive value is, so forgetting the case's key forgets it; the
    # store keeps the file under its own rules (brief, D31) (brief, D68).
    definition = claim()
    definition["fields"]["receipt"] |= {"sensitive": True, "visible_to": ["adjuster"]}
    run = attached(definition)
    kept = run.state.values["receipt"]
    assert isinstance(kept, Sensitive)
    assert kept.value == "doc-7f3a"
    assert all("doc-7f3a" not in line for line in run.history)
    # Whoever may see it opens it: the view is filtered for them, so the ID is theirs to resolve.
    asked: list[tuple[str, Viewer]] = []
    store_resolvers(asked).show(run.view(roles=ADJUSTER.roles), "receipt", ADJUSTER)
    assert asked == [("doc-7f3a", ADJUSTER)]
