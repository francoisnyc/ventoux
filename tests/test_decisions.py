"""Decision references: every decision cited in `src/` is written "(brief, Dn", is in the brief,
and isn't superseded (layer 3).

See docs/layers/03-validation.md.
"""

import re
from pathlib import Path

ROOT = Path(__file__).parent.parent
BRIEF = ROOT / "docs" / "BRIEF.md"

# A decision: `D` and a number, as a whole word. `\b` is a word boundary, so `D10` matches but
# `ID10`, `0xD5` and `D10x` don't.
DECISION = re.compile(r"\bD(\d+)\b")

# A heading in the brief, `### D3. Expressions are ... (superseded by D20)`: its number, then the
# rest of the line.
HEADING = re.compile(r"^### D(\d+)\. (.*)$", re.MULTILINE)
SUPERSEDED = re.compile(r"superseded by D(\d+)")

CITED = "(brief, "  # what comes right before a decision cited with its source


def decisions(brief: str) -> dict[int, int | None]:
    """Each decision in the brief, and the decision that superseded it, if any."""
    found: dict[int, int | None] = {}
    for number, title in HEADING.findall(brief):
        replaced = SUPERSEDED.search(title)
        found[int(number)] = int(replaced.group(1)) if replaced else None
    return found


def citation_problems(source: str, known: dict[int, int | None]) -> list[str]:
    """What is wrong with each decision `source` cites: written bare, superseded, or unknown."""
    problems = []
    for line_number, line in enumerate(source.splitlines(), start=1):
        for match in DECISION.finditer(line):
            number = int(match.group(1))
            where = f"line {line_number}: D{number}"
            if not line[: match.start()].endswith(CITED):
                problems.append(f"{where} is cited without its source: write (brief, D{number})")
            elif number not in known:
                problems.append(f"{where} is not a decision in the brief: check the number")
            elif (replacement := known[number]) is not None:
                problems.append(
                    f"{where} is superseded by D{replacement}: cite D{replacement}, or the rule "
                    "that replaced it"
                )
    return problems


BRIEF_EXAMPLE = """\
### D3. Expressions are a small JSONata subset (superseded by D20)
### D10. A case closes when nothing is left to do
### D20. Expressions are structured JSON with a fixed list of operators (supersedes D3)
"""


def test_a_bare_decision_is_refused() -> None:
    source = "# A case closes when nothing is left to do (D10).\n"
    assert citation_problems(source, decisions(BRIEF_EXAMPLE)) == [
        "line 1: D10 is cited without its source: write (brief, D10)"
    ]


def test_a_superseded_decision_is_refused() -> None:
    source = "# Expressions are a JSONata subset (brief, D3).\n"
    assert citation_problems(source, decisions(BRIEF_EXAMPLE)) == [
        "line 1: D3 is superseded by D20: cite D20, or the rule that replaced it"
    ]


def test_a_decision_the_brief_does_not_have_is_refused() -> None:
    source = '"""Retries live in the contract (brief, D99)."""\n'
    assert citation_problems(source, decisions(BRIEF_EXAMPLE)) == [
        "line 1: D99 is not a decision in the brief: check the number"
    ]


def test_a_decision_cited_with_its_source_is_accepted() -> None:
    source = "# Nothing is truthy (brief, D20); a case closes when idle (brief, D10).\n"
    assert citation_problems(source, decisions(BRIEF_EXAMPLE)) == []


def test_every_decision_cited_in_src_is_in_the_brief_and_current() -> None:
    known = decisions(BRIEF.read_text())
    problems = [
        f"{path.relative_to(ROOT)}, {problem}"
        for path in sorted((ROOT / "src").rglob("*.py"))
        for problem in citation_problems(path.read_text(), known)
    ]
    assert problems == []
