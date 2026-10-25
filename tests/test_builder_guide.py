"""The builder guide's examples (layer 14b, choice 26): each is word for word a file in
`examples/builder/`, run by its test; the guide's own text is never run. Those with a hand-written
definition are compared with it, as data and by digest (choice 24).
See docs/guides/builder.md.
"""

import json
import runpy
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from ventoux.case.definition import parse_case
from ventoux.case.releases import behaviour_digest
from ventoux.case.validate import validate_case
from ventoux.core.plan import parse_plan
from ventoux.core.validate import Issue, validate
from ventoux.testing import CATALOG, load_definition
from ventoux.tooling.builder import Case, package
from ventoux.tooling.builder.written import written

ROOT = Path(__file__).parent.parent
EXAMPLES = ROOT / "examples" / "builder"


def built(name: str) -> Case:
    """The case the guide's example `name` defines, the only `Case` at its top level. `run_path`
    runs the repository's own builder file, code reviewed like any code (brief, D58)."""
    cases = [
        v for v in runpy.run_path(str(EXAMPLES / f"{name}.py")).values() if isinstance(v, Case)
    ]
    assert len(cases) == 1, name
    return cases[0]


def as_data(case: Case) -> Any:
    return json.loads(written(case), parse_float=Decimal)


@pytest.mark.parametrize(
    ("example", "by_hand"),
    [
        ("claim", "claim/claim.json"),
        ("four_eyes", "refund/refund-four-eyes.json"),
        ("reminded", "refund/refund-reminded.json"),
    ],
)
def test_an_example_reads_as_its_hand_written_definition(example: str, by_hand: str) -> None:
    found = as_data(built(example))
    written_by_hand = load_definition(ROOT / "examples" / by_hand)
    assert found == written_by_hand
    assert behaviour_digest(parse_case(found), {}) == behaviour_digest(
        parse_case(written_by_hand), {}
    )


def test_every_example_is_a_package_the_check_accepts() -> None:
    # The guide never teaches a definition `ventoux check` would refuse: no errors against the
    # development catalog; warnings may be shown.
    for path in sorted(EXAMPLES.glob("*.py")):
        for case in [v for v in runpy.run_path(str(path)).values() if isinstance(v, Case)]:
            files = package(case)
            plans = {}
            for name, text in files.items():
                if name != "case.json":
                    plan = parse_plan(json.loads(text, parse_float=Decimal))
                    plans[f"{plan.plan}@{plan.version}"] = json.loads(text, parse_float=Decimal)
                    assert not errors(validate(plan, CATALOG)), (path, name)
            parsed = parse_case(json.loads(files["case.json"], parse_float=Decimal))
            assert not errors(validate_case(parsed, CATALOG, plans)), path


def errors(issues: list[Issue]) -> list[str]:
    return [f"{i.path} {i.code}" for i in issues if i.severity != "warning"]


GUIDE = ROOT / "docs" / "guides" / "builder.md"


def test_the_guides_examples_are_the_files_their_tests_run() -> None:
    # Each block follows a line naming its file, and is that file word for word (choice 26).
    text = GUIDE.read_text()
    shown = text.split("```python\n")[1:]
    named = [part.rsplit("`", 2)[-2] for part in text.split("```python\n")[:-1]]
    assert len(named) == len(shown) >= 6
    for path, block in zip(named, shown, strict=True):
        assert block.split("```")[0] == (ROOT / path).read_text(), path
    assert sorted(f"examples/builder/{p.name}" for p in EXAMPLES.glob("*.py")) == sorted(
        p for p in named if p.startswith("examples/builder/")
    )
