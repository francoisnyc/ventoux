"""A person's identifier: how who answered is written, so one person is one name (brief, D22).

The trusted caller says who answered (brief, D19); the engine still refuses what isn't written as
an identifier, since "someone else" compares names exactly: `Sam` and `sam` would be two people.
"""

import re

# How an identifier is written, `ana` or `ana.lee@example.com`: a lowercase letter or digit, then
# lowercase letters, digits, `.`, `_`, `@` or `-`. No capitals, spaces or `:`.
IDENTIFIER = re.compile(r"[a-z0-9][a-z0-9._@-]*")


def identifier_problem(by: str) -> str | None:
    """Why `by` is not written as a person's identifier, or None if it is."""
    if IDENTIFIER.fullmatch(by) is not None:
        return None
    return (
        f"{by!r} is not written as a person's identifier: lowercase letters, digits, ., _, @ and "
        "-, starting with a letter or digit, such as ana or ana.lee@example.com"
    )
