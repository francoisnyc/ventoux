# Shared pytest plugin for p2_hash_seeds.py: writes a digest of everything each in-memory test's decisions gave, in the order given, so runs under different PYTHONHASHSEED values can be compared.
"""Not a probe itself. Loaded with `-p p2_seed_plugin`. For every call of the pure deciding
functions (a case's `decide`, a plan's `interpret`, the registry's requests), in every test, it
writes the result as text: the whole state (every field, its history lines and audit records
included, dict and list order kept), each command, or the refusal raised with its message. A set is written sorted (a set has no order to differ); a list, a tuple, a dict's
keys and a text are written as they are, so an order that came from a set shows.

The functions are watched by swapping each one's code object in memory for a forwarding one, so
every caller is seen, however it imported the function. No file is changed."""

import dataclasses
import hashlib
import json
import os
import types
from datetime import date
from decimal import Decimal
from typing import Any

import pytest

import ventoux.case.registry as registry
import ventoux.case.runtime as runtime
import ventoux.core.interpreter as interpreter

OUT = os.environ.get("P2_SEED_OUT")
FULL = os.environ.get("P2_SEED_FULL")  # a test's node ID: its whole text is kept too
LOG: list[str] = []


def canon(value: Any, depth: int = 0) -> Any:
    """`value` as JSON-shaped data that keeps every order but a set's."""
    if depth > 40:
        return "<deep>"
    if value is None or isinstance(value, bool | int | str):
        return value
    if isinstance(value, Decimal | date):
        return f"{type(value).__name__}:{value}"
    if isinstance(value, float):
        return f"float:{value!r}"
    if isinstance(value, set | frozenset):
        return {"<set>": sorted(json.dumps(canon(each, depth + 1)) for each in value)}
    if isinstance(value, dict) or hasattr(value, "items") and hasattr(value, "keys"):
        return [[canon(key, depth + 1), canon(item, depth + 1)] for key, item in value.items()]
    if isinstance(value, list | tuple):
        return [canon(each, depth + 1) for each in value]
    if hasattr(value, "model_dump"):
        return [type(value).__name__, canon(value.model_dump(), depth + 1)]
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return [
            type(value).__name__,
            [[f.name, canon(getattr(value, f.name), depth + 1)] for f in dataclasses.fields(value)],
        ]
    if isinstance(value, BaseException):
        return [type(value).__name__, str(value)]
    if hasattr(value, "__dict__"):
        return [type(value).__name__, canon(vars(value), depth + 1)]
    return f"<{type(value).__name__}>"


AMPLIFY = bool(os.environ.get("P2_SEED_AMPLIFY"))


def amplified(case: Any, catalog: Any, state: Any, event: Any) -> tuple[Any, Any, Any, Any]:
    """The same decision asked with more in every set, so that wherever a set's order could
    reach a line, there is an order to differ: whoever acts states every registered role beside
    their own, and every value in the case file has two more trusted sources. The tests' own
    assertions may then fail; only the digests are compared, seed against seed."""
    import copy

    roles = getattr(event, "roles", None)
    if isinstance(roles, frozenset) and roles:
        event = dataclasses.replace(event, roles=roles | frozenset(catalog.roles))
    state = copy.deepcopy(state)
    for field in list(state.sources):
        state.sources[field] = state.sources[field] | {"person:zed", "system:opener"}
    return case, catalog, state, event


def said(kind: str, value: Any) -> None:
    LOG.append(kind + " " + json.dumps(canon(value), ensure_ascii=False))


def watch(module: types.ModuleType, name: str, is_async: bool = False) -> None:
    """Make every call of `module.name` go through a logger, whoever holds the function."""
    function = getattr(module, name)
    original = types.FunctionType(
        function.__code__, function.__globals__, name, function.__defaults__, function.__closure__
    )
    original.__kwdefaults__ = function.__kwdefaults__
    key = f"_p2_{name}"

    def logged(*args: Any, **kwargs: Any) -> Any:
        if AMPLIFY and name == "decide" and len(args) == 4:
            args = amplified(*args)
        try:
            result = original(*args, **kwargs)
        except Exception as refused:
            said(f"{name} raised", refused)
            raise
        if name == "decide":
            state, commands = result
            said("decide state", state)  # every field, the audit records included
            said("decide commands", commands)
        else:
            said(name, result)
        return result

    async def logged_async(*args: Any, **kwargs: Any) -> Any:
        try:
            result = await original(*args, **kwargs)
        except Exception as refused:
            said(f"{name} raised", refused)
            raise
        said(name, result)
        said(f"{name} lines", [str(event) for event in getattr(result, "history", [])])
        return result

    function.__globals__[key] = logged_async if is_async else logged
    source = (
        f"async def forward(*args, **kwargs):\n    return await {key}(*args, **kwargs)\n"
        if is_async
        else f"def forward(*args, **kwargs):\n    return {key}(*args, **kwargs)\n"
    )
    scope: dict[str, Any] = {}
    exec(source, function.__globals__, scope)  # noqa: S102 (the probe's own two lines)
    function.__code__ = scope["forward"].__code__
    function.__defaults__ = None
    function.__kwdefaults__ = None


watch(runtime, "decide")
watch(interpreter, "interpret", is_async=True)
for request in ("publish", "activate", "opened", "moved", "closed", "retire", "harden"):
    watch(registry, request)


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_call(item: pytest.Item) -> Any:
    LOG.clear()
    yield
    if OUT:
        text = "\n".join(LOG)
        with open(OUT, "a", encoding="utf-8") as out:
            out.write(f"{item.nodeid}\t{len(LOG)}\t{hashlib.sha256(text.encode()).hexdigest()}\n")
        if FULL and FULL in item.nodeid:
            with open(OUT + ".full", "a", encoding="utf-8") as out:
                out.write(f"### {item.nodeid}\n{text}\n")
    LOG.clear()


if os.environ.get("P2_SEED_CONTROL"):
    # The control: with this set, one function is replaced IN MEMORY by a copy that forgets to
    # sort a set, to show that the digests do change with the seed when an order leaks.
    import ventoux.core.roles as roles

    def unsorted_role(allowed: Any, stated: Any, registered: Any) -> Any:
        counting = [role for role in stated if role in allowed and role in registered]
        return counting[0] if counting else None

    roles.role_that_counts.__code__ = unsorted_role.__code__
