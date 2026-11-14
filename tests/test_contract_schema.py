"""A contract's models, written as JSON Schema by Ventoux, never by pydantic (brief, D83).

See docs/layers/fix-contract-rendering.md.
"""

import json
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Annotated, Any, Literal

import pytest
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    GetCoreSchemaHandler,
    GetJsonSchemaHandler,
    RootModel,
    ValidationError,
)
from pydantic.json_schema import JsonSchemaValue
from pydantic_core import CoreSchema

from ventoux.core.contract import ActivityContract, Display, RetryPolicy, Timeouts
from ventoux.core.contract_schema import Unwritable, contract_schema
from ventoux.core.hash_check import check_hashes
from ventoux.core.output_sources import source
from ventoux.core.policy import only_from, trusted_only
from ventoux.core.references import reference
from ventoux.testing import CATALOG

# What pydantic 2.13.5's `model_json_schema()` wrote for each of SHAPES, recorded once under it and
# never written again: the rendering hash method 1 was made with (brief, D83).
RECORDED = Path(__file__).parent / "rendering-2.13.json"
ROOT = Path(__file__).parent.parent

# The string form of a decimal, as pydantic 2.13 wrote it; 2.14 leaves the pattern out.
DECIMAL_PATTERN = r"^(?!^[-+.]*$)[+-]?0*\d*\.?\d*$"


class LookupInput(BaseModel):
    order_id: str


class LookupOutput(BaseModel):
    status: str


def lookup_with(input: type[BaseModel], output: type[BaseModel] = LookupOutput) -> ActivityContract:
    """`orders.lookup@1`, a read-only contract, with `input` and `output` as its models."""
    fields: dict[str, Any] = {
        "name": "orders.lookup",
        "version": 1,
        "input": input,
        "output": output,
        "risk": "low",
        "effect": "read",
        "timeouts": Timeouts(start_to_close=10, schedule_to_start=60),
        "retry": RetryPolicy(maximum_attempts=3, initial_interval=1, backoff_coefficient=2),
        "idempotency_key": None,
        "outcomes": [],
        "display": Display(title="Look up an order", description="Reads an order's status."),
    }
    return ActivityContract(**fields)


def test_a_field_with_a_description_is_refused_when_the_contract_is_made() -> None:
    class Described(BaseModel):
        order_id: Annotated[str, Field(description="the order's ID")]

    with pytest.raises(ValidationError) as refused:
        lookup_with(Described)
    said = str(refused.value)
    assert "orders.lookup@1: input order_id (Described) has a description" in said
    assert "a contract's field is its type, its marks" in said


class Defaulted(BaseModel):
    order_id: str = "ord-1"


class Made(BaseModel):
    order_id: str = Field(default_factory=lambda: "ord-1")


class Aliased(BaseModel):
    order_id: Annotated[str, Field(alias="id")]


class Titled(BaseModel):
    order_id: Annotated[str, Field(title="Order")]


class WithExamples(BaseModel):
    order_id: Annotated[str, Field(examples=["ord-1"])]


class Extra(BaseModel):
    order_id: Annotated[str, Field(json_schema_extra={"x-mine": 1})]


class Constrained(BaseModel):
    amount: Annotated[Decimal, Field(gt=0)]


class Noted(BaseModel):
    order_id: Annotated[str, "a note"]


class Configured(BaseModel):
    model_config = ConfigDict(title="Lookup")

    order_id: str


@pytest.mark.parametrize(
    ("model", "said"),
    [
        (Defaulted, "input order_id (Defaulted) has a default other than None"),
        (Made, "input order_id (Made) has a default_factory"),
        (Aliased, "input order_id (Aliased) has an alias"),
        (Titled, "input order_id (Titled) has a title"),
        (WithExamples, "input order_id (WithExamples) has examples"),
        (Extra, "input order_id (Extra) has json_schema_extra"),
        (Constrained, "input amount (Constrained) has a constraint or mark Ventoux doesn't know"),
        (Noted, "input order_id (Noted) has a constraint or mark Ventoux doesn't know"),
        (Configured, "input Configured sets model_config"),
    ],
)
def test_anything_else_pydantic_would_write_is_refused(model: type[BaseModel], said: str) -> None:
    with pytest.raises(ValidationError) as refused:
        lookup_with(model)
    assert f"orders.lookup@1: {said}" in str(refused.value)


class Frozen(BaseModel):
    order_id: str = Field(frozen=True)


class Excluded(BaseModel):
    order_id: str | None = Field(default=None, exclude=True)


class ValidatedDefault(BaseModel):
    order_id: str | None = Field(default=None, validate_default=True)


@pytest.mark.parametrize(
    ("model", "setting"),
    [(Frozen, "frozen"), (Excluded, "exclude"), (ValidatedDefault, "validate_default")],
)
def test_any_other_setting_on_a_field_is_refused(model: type[BaseModel], setting: str) -> None:
    # What a field may set is listed, never what it may not: a setting a later pydantic adds is
    # refused too (fail closed) (the tutor's review of #98).
    with pytest.raises(ValidationError) as refused:
        lookup_with(model)
    assert f"orders.lookup@1: input order_id ({model.__name__}) sets {setting}" in str(
        refused.value
    )


def test_an_output_is_refused_the_same_way() -> None:
    class Described(BaseModel):
        status: Annotated[str, Field(description="the order's status")]

    with pytest.raises(ValidationError, match=r"output status \(Described\) has a description"):
        lookup_with(LookupInput, Described)


# A model whose value isn't the object of its fields, or that writes its own schema: the promise
# would say something it isn't (the tutor's review of #98).
class Root(RootModel[str]):
    pass


class Hooked(BaseModel):
    order_id: str

    @classmethod
    def __get_pydantic_json_schema__(
        cls, core_schema: CoreSchema, handler: GetJsonSchemaHandler
    ) -> JsonSchemaValue:
        schema = handler(core_schema)
        schema["x-mine"] = 1
        return schema


class CoreHooked(BaseModel):
    order_id: str

    @classmethod
    def __get_pydantic_core_schema__(cls, source: Any, handler: GetCoreSchemaHandler) -> CoreSchema:
        return handler(source)


class WritesItsOwn(BaseModel):
    @classmethod
    def __get_pydantic_json_schema__(
        cls, core_schema: CoreSchema, handler: GetJsonSchemaHandler
    ) -> JsonSchemaValue:
        return handler(core_schema)


class InheritsAHook(WritesItsOwn):
    order_id: str


A_ROOT_MODEL = (
    "Root is a RootModel, whose value is its root alone, never an object holding it: a "
    "contract's model is a BaseModel with named fields. Make it one"
)


def writes_its_own(model: str, hook: str, where: str) -> str:
    return (
        f"{model} defines {hook} (in {where}): a contract's model writes no schema of its own; "
        "Ventoux writes it. Remove it"
    )


@pytest.mark.parametrize(
    ("side", "model", "said"),
    [
        ("input", Root, A_ROOT_MODEL),
        ("output", Root, A_ROOT_MODEL),
        ("input", Hooked, writes_its_own("Hooked", "__get_pydantic_json_schema__", "Hooked")),
        ("output", Hooked, writes_its_own("Hooked", "__get_pydantic_json_schema__", "Hooked")),
        (
            "input",
            CoreHooked,
            writes_its_own("CoreHooked", "__get_pydantic_core_schema__", "CoreHooked"),
        ),
        (
            "output",
            CoreHooked,
            writes_its_own("CoreHooked", "__get_pydantic_core_schema__", "CoreHooked"),
        ),
        (
            "input",
            InheritsAHook,
            writes_its_own("InheritsAHook", "__get_pydantic_json_schema__", "WritesItsOwn"),
        ),
        (
            "output",
            InheritsAHook,
            writes_its_own("InheritsAHook", "__get_pydantic_json_schema__", "WritesItsOwn"),
        ),
    ],
    ids=[
        "a RootModel input",
        "a RootModel output",
        "an input writing its own JSON Schema",
        "an output writing its own JSON Schema",
        "an input writing its own core schema",
        "an output writing its own core schema",
        "an input inheriting a hook",
        "an output inheriting a hook",
    ],
)
def test_a_model_that_isnt_what_its_schema_would_say_is_refused(
    side: str, model: type[BaseModel], said: str
) -> None:
    with pytest.raises(ValidationError) as refused:
        lookup_with(model) if side == "input" else lookup_with(LookupInput, model)
    assert f"orders.lookup@1: {side} {said} (brief, D83)." in str(refused.value)


# Every shape a contract's field may have (choice 2 of the note), each possibly optional and
# marked, under names whose titles pydantic derives oddly.


class Plain(BaseModel):
    text: str
    yes_or_no: bool
    amount: Decimal
    day: date
    one: Literal["only"]
    one_of: Literal["low", "high"]


class Optional(BaseModel):
    text: str | None
    text_or_none: str | None = None
    yes_or_no: bool | None = None
    amount: Decimal | None = None
    day: date | None = None
    one: Literal["only"] | None = None
    one_of: Literal["low", "high"] | None


class Marked(BaseModel):
    customer: Annotated[str, trusted_only(), reference("crm")]
    amount: Annotated[Decimal, only_from("opener", "crm")]
    maybe: Annotated[Decimal | None, trusted_only()] = None
    status: Annotated[str, source("system:kyc")]
    notes: Annotated[str, source("untrusted:llm")]


class Named(BaseModel):
    address_2nd: str
    URL_v2: str
    camelCase: str  # noqa: N815 -- a name as a team may write it: the titles' test reads it
    a: str


class Documented(BaseModel):
    """What it is.

    Indented, then not.
    """

    order_id: str


class Inherited(Documented):
    status: str


class Empty(BaseModel):
    pass


class Twice(BaseModel):
    # Two policies, in the order written: the order is in the hash. And names ending in `_`,
    # whose titles pydantic strips (the tutor's review of #98).
    checked: Annotated[str, trusted_only(), only_from("opener", "crm")]
    reversed_: Annotated[str, only_from("opener", "crm"), trusted_only()]
    class_: str
    kind_: str | None = None


SHAPES: list[type[BaseModel]] = [
    Plain,
    Optional,
    Marked,
    Named,
    Documented,
    Inherited,
    Empty,
    Twice,
]


@pytest.mark.parametrize("model", SHAPES, ids=lambda model: model.__name__)
def test_each_shape_is_written_as_pydantic_2_13_wrote_it(model: type[BaseModel]) -> None:
    recorded = json.loads(RECORDED.read_text())
    assert contract_schema(model) == recorded["models"][model.__name__]


def as_written_by(version: str, schema: Any) -> Any:
    """`schema` with each decimal's string form as pydantic `version` writes it: with the pattern
    under 2.13, without it under 2.14."""
    if isinstance(schema, list):
        return [as_written_by(version, inner) for inner in schema]
    if not isinstance(schema, dict):
        return schema
    written = {key: as_written_by(version, inner) for key, inner in schema.items()}
    if written.get("anyOf", [None])[0] == {"type": "number"}:  # a decimal
        string = {"type": "string"} | ({"pattern": DECIMAL_PATTERN} if version == "2.13" else {})
        written["anyOf"][1] = string
    return written


@pytest.mark.parametrize("rendering", ["2.13", "2.14", "none"])
def test_a_contracts_hash_doesnt_depend_on_pydantics_rendering(
    monkeypatch: pytest.MonkeyPatch, rendering: str
) -> None:
    # Pydantic's own rendering made to be 2.13's, 2.14's, or to fail if it is read at all: every
    # development contract still hashes as contracts.lock.json records it (brief, D83).
    # Python: `vars` gives the class's own attributes; a classmethod's `__func__` is its function.
    pydantics = vars(BaseModel)["model_json_schema"].__func__

    def rendered(model: type[BaseModel], /, *args: Any, **kwargs: Any) -> dict[str, Any]:
        if rendering == "none":
            raise AssertionError(f"pydantic's rendering of {model.__name__} was read")
        written: dict[str, Any] = as_written_by(rendering, pydantics(model, *args, **kwargs))
        return written

    monkeypatch.setattr(BaseModel, "model_json_schema", classmethod(rendered))
    recorded = json.loads((ROOT / "contracts.lock.json").read_text())
    assert check_hashes(CATALOG, recorded) == []


class Floating(BaseModel):
    ratio: float


class Either(BaseModel):
    value: str | bool


class Nested(BaseModel):
    inner: LookupInput


@pytest.mark.parametrize("model", [Floating, Either, Nested], ids=lambda model: model.__name__)
def test_a_type_the_writer_doesnt_know_is_refused(model: type[BaseModel]) -> None:
    # Fail closed: the contract's own checks refuse these first; the writer never guesses either.
    with pytest.raises(Unwritable, match=f"\\({model.__name__}\\) is .*a contract's field is"):
        contract_schema(model)
