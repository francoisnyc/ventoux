"""Reading a model's answer that should be one JSON object: strictly, and never scraped.

The step advisor and the authoring loop read their answers here, so both refuse the same things:
prose around the object, two objects, a key given twice (brief, D61) (brief, D63).
"""

import json
from decimal import Decimal
from typing import Any


class NotOneObject(Exception):
    """The answer is not one JSON object. The message says where, never what the model wrote."""


def one_object(answer: str) -> dict[str, Any]:
    """The one JSON object `answer` is, at most inside one fenced block; `NotOneObject` for
    anything else: prose around it, a list, a key given twice, text that isn't JSON. Numbers are
    read as exact decimals, as a definition's are (brief, D20)."""
    try:
        read = json.loads(unfenced(answer), object_pairs_hook=no_key_twice, parse_float=Decimal)
    except json.JSONDecodeError as error:
        # The decoder's position only: its message never quotes the text.
        raise NotOneObject(f"not JSON: {error.msg} at line {error.lineno}, column {error.colno}")
    if not isinstance(read, dict):
        raise NotOneObject("JSON, but not one object")
    return read


def unfenced(answer: str) -> str:
    """`answer` without the one fenced block around it, if it is one: a model often writes
    ```json on the line before and ``` on the line after. Text around a block stays, and is
    refused as not JSON."""
    text = answer.strip()
    if not (text.startswith("```") and text.endswith("```") and "\n" in text):
        return text
    inside = text[: -len("```")]
    return inside[inside.index("\n") + 1 :]


def no_key_twice(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    """An object read from JSON, refusing a key given twice: Python's reader would keep the
    last one, silently."""
    keys = [key for key, _ in pairs]
    repeated = sorted({key for key in keys if keys.count(key) > 1})
    if repeated:
        raise NotOneObject(f"a key is given twice: {', '.join(repeated)}")
    return dict(pairs)
