"""A contract's promise, and what changed between two of them, path by path (layer 13d).

The promise is what the contract hash reads: everything but `display`, its schemas as JSON
Schema. Two promises are compared leaf by leaf, as the semantic diff names paths, so a hash
failure says what changed (design question 16): `retry.maximum_attempts: 5 -> 9`. A promise is
the platform team's, written in the catalog, never a case's, so its values are shown
(brief, D57).
"""

import json
from typing import Any

from ventoux.core.contract import Contract


class PromiseUnreadable(Exception):
    """A promise holding something it can't read: refused, never skipped (brief, D57)."""


def promise_of(contract: Contract) -> dict[str, Any]:
    """What `contract` promises, as plain JSON values: everything but `display`, schemas as JSON
    Schema, outcomes sorted."""
    # Pydantic: `model_dump(mode="json")` gives the object as plain JSON values (dicts, lists,
    # texts, numbers); `model_json_schema()` describes a model class as JSON Schema.
    promise = contract.model_dump(mode="json", exclude={"display", "input", "output"})
    promise["input"] = contract.input.model_json_schema()
    promise["output"] = contract.output.model_json_schema()
    # Not cancellable is what every workflow contract promised before 11c, so it adds nothing:
    # their hashes and contracts.lock.json stay as they were (brief, D40).
    if promise.get("cancellable") is False:
        del promise["cancellable"]
    # The outcomes are a set of answers: their order promises nothing. A workflow has none.
    if "outcomes" in promise:
        promise["outcomes"] = sorted(promise["outcomes"])
    return promise


def promise_changes(before: dict[str, Any], after: dict[str, Any]) -> list[str]:
    """Each place `before` and `after` promise differently, in dotted paths, keys in order: a
    value changed as `path: before -> after`, a key one side has as `path: added value` or
    `path: removed value`, a list whole on both sides. Refused (`PromiseUnreadable`) if either
    holds a value no JSON holds."""
    readable(before, "")
    readable(after, "")
    return differing(before, after, "")


# What a promise is made of: JSON's values, read by `json.loads` or given by `promise_of`.
SCALARS = (str, int, float, bool, type(None))


def readable(value: object, path: str) -> None:
    """Refuse a value no JSON holds, anywhere in `value`, naming where it is (fail closed)."""
    if isinstance(value, dict):
        for key, inner in value.items():
            if not isinstance(key, str):
                raise PromiseUnreadable(f"{path or 'the promise'} has a key that isn't a text")
            readable(inner, joined(path, key))
    elif isinstance(value, list):
        for inner in value:
            readable(inner, path)
    elif not isinstance(value, SCALARS):
        kind = type(value).__name__
        raise PromiseUnreadable(f"{path} holds a {kind}, which a promise never holds")


def differing(before: object, after: object, path: str) -> list[str]:
    """Where two readable values differ, below `path`."""
    if before == after:
        return []
    if isinstance(before, dict) and isinstance(after, dict):
        found: list[str] = []
        for key in sorted(before.keys() | after.keys()):
            where = joined(path, key)
            if key not in after:
                found.append(f"{where}: removed {shown(before[key])}")
            elif key not in before:
                found.append(f"{where}: added {shown(after[key])}")
            else:
                found += differing(before[key], after[key], where)
        return found
    return [f"{path}: {shown(before)} -> {shown(after)}"]


def joined(path: str, key: str) -> str:
    """`retry.maximum_attempts`, from `retry` and `maximum_attempts`."""
    return f"{path}.{key}" if path else key


def shown(value: object) -> str:
    """A text as written, anything else as compact JSON: `RefundInput`, `5`, `["declined"]`."""
    if isinstance(value, str):
        return value
    return json.dumps(value, sort_keys=True, separators=(", ", ": "))
