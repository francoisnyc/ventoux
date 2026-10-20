"""The `ventoux` command: `ventoux simulate STORY.json` (layer 11g2).

Reading files and printing happen here, never in `core` or `case`, which read no clock and do no
I/O (brief, D45). `ventoux check` comes with the Python builder (brief, D34).
See docs/layers/11-rules.md (11g) and docs/guides/cases.md, "Simulating a story".
"""

import argparse
import json
import sys
from collections.abc import Sequence
from decimal import Decimal
from pathlib import Path
from typing import Any

from ventoux.case.definition import CaseDefinition, CaseInvalid, parse_case
from ventoux.case.simulate import StoryRefused, simulate
from ventoux.case.story import Story, StoryInvalid, parse_story
from ventoux.testing import CATALOG

# What `ventoux simulate` exits with.
HOLDS = 0  # what the story expects holds, or it expects nothing
FAILS = 1  # what it expects doesn't hold: the first difference is printed
CANT_READ = 2  # the story or its definition can't be read, or can't run


class Unreadable(Exception):
    """A file that can't be read as what it should be: one line per problem, each naming it."""

    def __init__(self, path: Path, problems: str) -> None:
        super().__init__("\n".join(f"{path}: {line}" for line in problems.splitlines()))


def main(argv: Sequence[str] | None = None) -> int:
    """Run `ventoux` with `argv` (the command line's own when None), and say how it ended."""
    # argparse: the standard library's command-line parser; it prints `--help` and refuses an
    # unknown command by itself.
    parser = argparse.ArgumentParser(prog="ventoux", description="Ventoux, from the command line.")
    commands = parser.add_subparsers(dest="command", required=True)
    simulating = commands.add_parser(
        "simulate", help="play a story on the in-memory engine, and check what it expects"
    )
    simulating.add_argument("story", type=Path, help="the story's JSON file")
    arguments = parser.parse_args(argv)
    return simulate_story(arguments.story)


def simulate_story(path: Path) -> int:
    """Print the story's simulation, then whether what it expects holds."""
    try:
        story, case = read_story(path)
        simulation = simulate(story, case, CATALOG)
    except StoryRefused as refused:
        print(Unreadable(path, str(refused)), file=sys.stderr)
        return CANT_READ
    except Unreadable as unreadable:
        print(unreadable, file=sys.stderr)
        return CANT_READ
    print(simulation, end="")
    difference = simulation.difference()
    if difference is not None:
        print(difference)
        return FAILS
    return HOLDS


def read_story(path: Path) -> tuple[Story, CaseDefinition]:
    """The story at `path`, and the definition it names, relative to the story's own file.
    Raises `Unreadable`, naming the file, for one that can't be read."""
    try:
        story = parse_story(read_json(path))
    except StoryInvalid as invalid:
        raise Unreadable(path, str(invalid)) from None
    definition = path.parent / story.definition
    try:
        case = parse_case(read_json(definition))
    except CaseInvalid as invalid:
        raise Unreadable(definition, str(invalid)) from None
    return story, case


def read_json(path: Path) -> Any:
    """The JSON in `path`, numbers read as exact decimals, never binary floats (brief, D20)."""
    try:
        return json.loads(path.read_text(), parse_float=Decimal)
    except OSError as error:
        raise Unreadable(path, f"can't be read: {error.strerror}") from None
    except json.JSONDecodeError as error:
        raise Unreadable(path, f"isn't JSON: {error.msg}, at line {error.lineno}") from None
