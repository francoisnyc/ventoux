"""The JSON Schema, published from the parser's models (layer 14e, choices 48 to 53): it describes
the JSON as written, and agrees with the parser on every committed definition and on a fixed set
of wrong shapes. See docs/layers/14-builder.md and docs/BRIEF.md, D60.
"""

import json
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator

from ventoux.case.definition import CaseInvalid, parse_case
from ventoux.core.plan import PlanInvalid, parse_plan
from ventoux.tooling.schema import case_schema, plan_schema

ROOT = Path(__file__).parent.parent
EXAMPLES = ROOT / "examples"

# Every committed case definition: the packages, the quickstart's, and the examples the guides
# and the checks read. Stories are not definitions.
CASES = sorted(
    [
        *EXAMPLES.glob("packages/*/case.json"),
        *EXAMPLES.glob("quickstart/packages/*/case.json"),
        *EXAMPLES.glob("refund/*.json"),
        *EXAMPLES.glob("claim/*.json"),
        *EXAMPLES.glob("checks/*.json"),
        *EXAMPLES.glob("witnesses/*.json"),
    ]
)
PLANS = sorted(
    [
        *EXAMPLES.glob("packages/*/plans/*.json"),
        *EXAMPLES.glob("quickstart/packages/*/plans/*.json"),
    ]
)


def loaded(path: Path) -> dict[str, Any]:
    """A definition as the engine reads it: numbers as decimals (brief, D20)."""
    data: dict[str, Any] = json.loads(path.read_text(), parse_float=Decimal)
    return data


def schema_accepts(schema: dict[str, Any], data: Any) -> bool:
    Draft202012Validator.check_schema(schema)
    return bool(Draft202012Validator(schema).is_valid(data))


def parser_accepts_case(data: Any) -> bool:
    try:
        parse_case(data)
    except CaseInvalid:
        return False
    return True


def parser_accepts_plan(data: Any) -> bool:
    try:
        parse_plan(data)
    except PlanInvalid:
        return False
    return True


def test_the_corpus_is_not_empty() -> None:
    assert len(CASES) >= 20
    assert len(PLANS) >= 1


@pytest.mark.parametrize("path", CASES, ids=lambda p: str(p.relative_to(EXAMPLES)))
def test_every_committed_case_is_accepted_by_the_schema_as_by_the_parser(path: Path) -> None:
    data = loaded(path)
    assert parser_accepts_case(data), f"{path} is not a valid case; the corpus holds only those"
    assert schema_accepts(case_schema(), data)


@pytest.mark.parametrize("path", PLANS, ids=lambda p: str(p.relative_to(EXAMPLES)))
def test_every_committed_plan_is_accepted_by_the_schema_as_by_the_parser(path: Path) -> None:
    data = loaded(path)
    assert parser_accepts_plan(data)
    assert schema_accepts(plan_schema(), data)


# --- Wrong shapes, refused by both (choice 51) ---------------------------------------------------

REFUND = EXAMPLES / "packages" / "refund" / "case.json"
REFUND_ORDER = EXAMPLES / "packages" / "refund" / "plans" / "refund-order.json"


def a_case(**changes: Any) -> dict[str, Any]:
    """The refund case, with top-level keys replaced."""
    return {**loaded(REFUND), **changes}


def with_approval(approval: dict[str, Any]) -> dict[str, Any]:
    case = loaded(REFUND)
    case["steps"]["settle"]["approval"] = approval
    return case


def with_field(name: str, field: dict[str, Any]) -> dict[str, Any]:
    case = loaded(REFUND)
    case["fields"][name] = field
    return case


def with_step(name: str, **changes: Any) -> dict[str, Any]:
    case = loaded(REFUND)
    case["steps"][name] |= changes
    return case


WRONG_CASES: dict[str, dict[str, Any]] = {
    # The curriculum's negative test: an operator D20 doesn't list matches no shape.
    "an operator D20 doesn't list": with_approval(
        {"when": {"now": []}, "roles": ["support-lead"], "display": {"title": "x"}}
    ),
    "an unknown key at the root": a_case(owner="ana"),
    "an unknown key in a step": {
        **a_case(),
        "steps": {
            **loaded(REFUND)["steps"],
            "review": {**loaded(REFUND)["steps"]["review"], "x": 1},
        },
    },
    "a count written as a string": with_approval(
        {"roles": ["support-lead"], "count": "2", "display": {"title": "x"}}
    ),
    "a field with no type": with_field("note", {"display": {"title": "Note"}}),
    "a field of an unknown type": with_field("note", {"type": "text", "display": {"title": "x"}}),
    "a case name the pattern refuses": a_case(case="Refund"),
    "a field name the pattern refuses": with_field(
        "Approved Amount", {"type": "number", "display": {"title": "x"}}
    ),
    "a number written as a string": with_approval(
        {
            "when": {">": [{"var": "amount"}, "100"]},
            "roles": ["support-lead"],
            "display": {"title": "x"},
        }
    ),
    "a step of no kind": {**a_case(), "steps": {"review": {"display": {"title": "x"}}}},
    "no steps at all": a_case(steps={}),
    # From the tutor review of #62: a type is written with its `type` wherever one is written.
    "a list's field with no type": with_field(
        "lines", {"type": "list", "fields": {"amount": {}}, "display": {"title": "x"}}
    ),
    "a reference field with no type": with_field(
        "order", {"system": "crm", "display": {"title": "x"}}
    ),
    # Booleans as written, `true` or `false`: never "no", "yes", "on", 1 or 1.0 (brief, D60).
    # Each the lax reading of its field's default, so nothing else refuses it.
    "automatic written as a word": with_step("review", automatic="yes"),
    "repeatable written as a number": with_step("review", repeatable=0),
    "sensitive written as a letter": with_field(
        "note", {"type": "string", "sensitive": "f", "display": {"title": "x"}}
    ),
    "stays_open written as a word": a_case(stays_open="off"),
}


@pytest.mark.parametrize("wrong", WRONG_CASES, ids=str)
def test_a_wrong_case_is_refused_by_the_schema_as_by_the_parser(wrong: str) -> None:
    data = WRONG_CASES[wrong]
    assert not parser_accepts_case(data), f"the parser accepts {wrong}; the list holds refusals"
    assert not schema_accepts(case_schema(), data)


def test_a_boolean_written_as_a_word_is_refused_at_its_path() -> None:
    # The parser's side of the promise, with its path, as `ventoux check` would say it.
    with pytest.raises(CaseInvalid, match=r"steps\.review\.automatic: "):
        parse_case(with_step("review", automatic="no"))


def a_plan(**changes: Any) -> dict[str, Any]:
    return {**loaded(REFUND_ORDER), **changes}


WRONG_PLANS: dict[str, dict[str, Any]] = {
    "version zero": a_plan(version=0),
    "a version written as a string": a_plan(version="1"),
    "a version written as a decimal": a_plan(version=Decimal("1.0")),
    "a version written as true": a_plan(version=True),
    "an unknown key": a_plan(owner="ana"),
    "a sources key of the plan's own": a_plan(sources={"amount": "untrusted:x"}),
    "a state of no kind": a_plan(states={**loaded(REFUND_ORDER)["states"], "limbo": {"on": {}}}),
    "a state name the pattern refuses": a_plan(initial="Check Order"),
    "an operator D20 doesn't list": a_plan(
        states={
            **loaded(REFUND_ORDER)["states"],
            "check_order": {
                **loaded(REFUND_ORDER)["states"]["check_order"],
                "on": {"done": [{"target": "paid", "when": {"now": []}}]},
            },
        }
    ),
}


@pytest.mark.parametrize("wrong", WRONG_PLANS, ids=str)
def test_a_wrong_plan_is_refused_by_the_schema_as_by_the_parser(wrong: str) -> None:
    data = WRONG_PLANS[wrong]
    assert not parser_accepts_plan(data), f"the parser accepts {wrong}; the list holds refusals"
    assert not schema_accepts(plan_schema(), data)


# --- `ventoux schema`, and `--unchanged` (choices 48, 50, 52, 53) --------------------------------

from ventoux.case.engine import ENGINE
from ventoux.tooling.cli import main

SCHEMAS = ("case.schema.json", "plan.schema.json")


def snapshot(folder: Path) -> dict[str, bytes]:
    return {str(p.relative_to(folder)): p.read_bytes() for p in folder.rglob("*") if p.is_file()}


def test_ventoux_schema_writes_both_files_naming_the_format_they_describe(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.chdir(tmp_path)
    assert main(["schema"]) == 0
    said = capsys.readouterr().out
    for name in SCHEMAS:
        written = tmp_path / "schema" / name
        assert f"✓ schema/{name}" in said
        text = written.read_text()
        assert text.endswith("}\n")
        assert text == json.dumps(json.loads(text), indent=2, ensure_ascii=False) + "\n"
        schema = json.loads(text)
        # Draft 2020-12, named by the engine version that parses the format (brief, D51, D60).
        assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
        assert schema["$id"] == f"https://ventoux.dev/schema/engine-{ENGINE}/{name}"
        assert list(schema)[:4] == ["$schema", "$id", "title", "description"]
        # Shape only, never a trust boundary: said in the schema itself (choices 50, 53).
        assert "ventoux check" in schema["description"]
        assert "never runs on model output" in schema["description"]
    case = json.loads((tmp_path / "schema" / "case.schema.json").read_text())
    assert case["title"] == "Ventoux case definition"
    assert {k: v for k, v in case.items() if not k.startswith("$") and k != "title"} == {
        k: v for k, v in case_schema().items() if k not in ("title", "description", "$defs")
    } | {"description": case["description"]}
    # `--out` names another folder.
    assert main(["schema", "--out", "elsewhere"]) == 0
    assert (tmp_path / "elsewhere" / "plan.schema.json").read_text() == (
        tmp_path / "schema" / "plan.schema.json"
    ).read_text()


def test_unchanged_fails_on_a_changed_or_missing_schema_naming_the_line_and_writes_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.chdir(tmp_path)
    assert main(["schema"]) == 0
    capsys.readouterr()
    assert main(["schema", "--unchanged"]) == 0
    assert "✓ schema/case.schema.json is unchanged" in capsys.readouterr().out
    # A model changed and the schema not regenerated looks like this: one line differs.
    committed = tmp_path / "schema" / "case.schema.json"
    text = committed.read_text()
    line = text.splitlines().index('  "title": "Ventoux case definition",') + 1
    committed.write_text(text.replace('"Ventoux case definition"', '"An old format"'))
    (tmp_path / "schema" / "plan.schema.json").unlink()
    before = snapshot(tmp_path)
    assert main(["schema", "--unchanged"]) == 1
    said = capsys.readouterr().out
    assert (
        f"schema/case.schema.json differs from what the models say, first at line {line}:" in said
    )
    assert '  committed: "title": "An old format",' in said
    assert '  written:   "title": "Ventoux case definition",' in said
    assert "schema/plan.schema.json is missing: ventoux schema writes it" in said
    assert "Run `ventoux schema` and commit what it writes." in said
    assert snapshot(tmp_path) == before  # nothing written


def test_the_committed_schemas_are_what_the_models_say() -> None:
    # What CI checks, checked here too: the two files at the repository's root.
    for name in SCHEMAS:
        committed = (ROOT / "schema" / name).read_text()
        assert json.loads(committed)["$id"].endswith(name)
    from ventoux.tooling.schema import schema_files

    assert {name: (ROOT / "schema" / name).read_text() for name in SCHEMAS} == schema_files()


def test_ci_checks_the_committed_schemas_unchanged() -> None:
    # One line in `check`, after 14d's; 13e's care kept: read-only, the `changes` job untouched.
    from test_unchanged import WORKFLOW, ci_runs

    assert ci_runs("- run: uv run ventoux schema --unchanged")
    text = WORKFLOW.read_text()
    doing = [l for l in text.splitlines() if not l.strip().startswith("#")]
    assert text.count("permissions:") == 1
    assert "  contents: read" in doing
    assert not any("pull_request_target" in l for l in doing)
    changes = text.split("\n  changes:")[1]
    assert "schema" not in changes


def test_unchanged_fails_on_a_missing_schema_alone(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.chdir(tmp_path)
    assert main(["schema"]) == 0
    (tmp_path / "schema" / "plan.schema.json").unlink()
    before = snapshot(tmp_path)
    assert main(["schema", "--unchanged"]) == 1
    said = capsys.readouterr().out
    assert "✓ schema/case.schema.json is unchanged" in said
    assert "schema/plan.schema.json is missing: ventoux schema writes it" in said
    assert snapshot(tmp_path) == before


def test_unchanged_fails_on_other_line_endings_alone(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.chdir(tmp_path)
    assert main(["schema"]) == 0
    committed = tmp_path / "schema" / "case.schema.json"
    committed.write_bytes(committed.read_bytes().replace(b"\n", b"\r\n"))
    before = snapshot(tmp_path)
    assert main(["schema", "--unchanged"]) == 1
    said = capsys.readouterr().out
    assert "schema/case.schema.json differs from what the models say, first at line 1:" in said
    assert "the committed line ends with \\r\\n" in said
    assert snapshot(tmp_path) == before
