"""Packages written from Python, byte for byte the committed JSON (layer 14b, choices 23 and 24).
See docs/layers/14-builder.md.
"""

import json
import runpy
from decimal import Decimal
from pathlib import Path
from typing import Any

from ventoux.case.releases import digest
from ventoux.case.releases import package as read_package
from ventoux.tooling.builder import Case, package

ROOT = Path(__file__).parent.parent


def built(path: Path, name: str) -> Case:
    """The case `name` a builder file defines. `run_path` runs the repository's own builder file,
    code reviewed like any code (brief, D58)."""
    case = runpy.run_path(str(path))[name]
    assert isinstance(case, Case)
    return case


def as_data(text: str) -> Any:
    return json.loads(text, parse_float=Decimal)


def test_the_refund_package_reads_as_the_committed_one() -> None:
    refund = built(ROOT / "examples" / "cases" / "refund.py", "refund")
    files = package(refund)
    folder = ROOT / "examples" / "packages" / "refund"
    assert sorted(files) == ["case.json", "plans/refund-order.json"]
    for name, text in files.items():
        assert as_data(text) == as_data((folder / name).read_text()), name
    committed = read_package(
        (folder / "case.json").read_text(), [(folder / "plans" / "refund-order.json").read_text()]
    )
    assert digest(read_package(files["case.json"], [files["plans/refund-order.json"]])) == digest(
        committed
    )


def test_every_package_is_the_committed_json_byte_for_byte() -> None:
    # Both packages the repository holds, their plans included (choice 24), where git keeps them.
    for builder_file, name, folder in (
        (ROOT / "examples" / "cases" / "refund.py", "refund", ROOT / "examples" / "packages"),
        (
            ROOT / "examples" / "quickstart" / "cases" / "refund.py",
            "refund",
            ROOT / "examples" / "quickstart" / "packages",
        ),
    ):
        files = package(built(builder_file, name))
        committed = sorted(
            str(path.relative_to(folder / name)) for path in (folder / name).rglob("*.json")
        )
        assert sorted(files) == committed, builder_file
        for path, text in files.items():
            assert text == (folder / name / path).read_text(), f"{builder_file}: {path}"
