"""Text a definition or the catalog writes, placed in Markdown: shown, never rendered (13e).

The plain form, the case map and the sheet print Markdown, and CI's job summary shows it rendered.
A literal, a title or a name is written by whoever wrote the definition, a pull request
included, so it is escaped where Markdown is written, never at the source: the developer forms
and the records keep plain text (brief, D56, as amended in 13e). See docs/layers/13-diff.md
(13e, choice 77).
"""

# What opens a construct inside a line, each shown as itself: raw HTML and autolinks start with
# `<`, entities with `&`, emphasis with `*`, `_` or `~`, code with a backtick, links and images
# with `[`, `]` and `!`. `#` and `|` too, should a value ever start a line.
ENTITIES = {"&": "&amp;", "<": "&lt;", ">": "&gt;"}
ESCAPED = "\\`*_[]~#|!"
# A line break would let a value start a line of its own: shown, never kept.
BREAKS = {"\n": "\\n", "\r": "\\r", "\t": "\\t"}


def text(written: str) -> str:
    """`written` in a paragraph or a list item, shown as it is written: `a <b>` reads as `a <b>`,
    never as HTML."""
    shown: list[str] = []
    for character in written:
        if character in ENTITIES:
            shown.append(ENTITIES[character])
        elif character in BREAKS:
            shown.append("\\" + BREAKS[character])  # the backslash itself escaped
        elif character in ESCAPED:
            shown.append("\\" + character)
        else:
            shown.append(character)
    return "".join(shown)


def code(written: str) -> str:
    """`written` in a code span, fenced by one backtick more than its longest run, as CommonMark
    allows, so nothing in it closes the span; a line break shown as a space."""
    flat = " ".join(written.splitlines())
    fence = "`" * (longest_run(flat) + 1)
    padded = f" {flat} " if flat.startswith("`") or flat.endswith("`") else flat
    return f"{fence}{padded}{fence}"


def block(lines: list[str]) -> list[str]:
    """`lines` as a code block, fenced by more backticks than any run in them, never fewer than
    three, so nothing in them closes the block."""
    fence = "`" * max(3, max((longest_run(line) for line in lines), default=0) + 1)
    return [fence, *lines, fence]


def longest_run(written: str) -> int:
    """The longest run of backticks in `written`."""
    longest = current = 0
    for character in written:
        current = current + 1 if character == "`" else 0
        longest = max(longest, current)
    return longest
