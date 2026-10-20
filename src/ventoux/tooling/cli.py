"""The `ventoux` command: `ventoux simulate STORY.json` (layer 11g2).

Reading files and printing happen here, never in `core` or `case`, which read no clock and do no
I/O (brief, D45). `ventoux check` comes with the Python builder (brief, D34).
See docs/layers/11-rules.md (11g) and docs/guides/cases.md, "Simulating a story".
"""

import json
from decimal import Decimal
from pathlib import Path

from ventoux.case.definition import CaseDefinition, parse_case
from ventoux.case.story import Story, parse_story


def read_story(path: Path) -> tuple[Story, CaseDefinition]:
    """The story at `path`, and the definition it names, relative to the story's own file.
    Numbers are read as exact decimals, never binary floats (brief, D20)."""
    story = parse_story(json.loads(path.read_text(), parse_float=Decimal))
    definition = json.loads((path.parent / story.definition).read_text(), parse_float=Decimal)
    return story, parse_case(definition)
