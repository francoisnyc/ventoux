"""Tracer code is temporary: every `# TRACER:` comment names the layer that replaces it.

The layer goes on the same line, so `grep "TRACER:"` lists what is crude and when it goes away.
"""

import re
from pathlib import Path

SRC = Path(__file__).parent.parent / "src"


def tracers_without_a_layer(source: str) -> list[str]:
    """The `# TRACER:` lines in `source` that don't name a layer."""
    tracers = [
        line[line.index("# TRACER:") :] for line in source.splitlines() if "# TRACER:" in line
    ]
    return [tracer for tracer in tracers if not re.search(r"\blayer \d+\b", tracer)]


def test_a_tracer_comment_must_name_its_layer() -> None:
    source = "x = 1  # TRACER: a crude stand-in\n"
    assert tracers_without_a_layer(source) == ["# TRACER: a crude stand-in"]


def test_every_tracer_comment_in_the_source_names_its_layer() -> None:
    unnamed = [
        f"{path.relative_to(SRC)}: {tracer}"
        for path in sorted(SRC.rglob("*.py"))
        for tracer in tracers_without_a_layer(path.read_text())
    ]
    assert unnamed == [], "say which layer replaces it, on the TRACER line itself"
