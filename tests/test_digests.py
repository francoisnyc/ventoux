"""Method 1's digests, pinned for packages that between them use every shape of the format
(layer 12b, from the tutor review; brief, D50, D51).

Every open case recomputes its release's digest at each run, so method 1 must give the same digest
for ever: a model renamed, a default changed or a field made `Literal` would otherwise change the
digest of every package using it, and stop their open cases until the code is fixed. A change of
the method is method 2, a decision of its own. See docs/layers/12-releases.md (12b).
"""

import json
import typing
from pathlib import Path
from typing import Literal

from pydantic import BaseModel

from ventoux.case.definition import CaseDefinition
from ventoux.case.releases import METHOD, Package, digest, package
from ventoux.core.plan import Plan

ROOT = Path(__file__).parent.parent
PINNED = Path(__file__).parent / "digests" / f"method-{METHOD}.json"


def packages() -> dict[str, Package]:
    """Every package pinned, by its path in the repository: each example definition as a package
    of its own, the example package, and the package written to use what the examples don't."""
    found: dict[str, Package] = {}
    for path in sorted((ROOT / "examples").glob("*/*.json")):
        found[str(path.relative_to(ROOT))] = package(path.read_text(), [])
    for folder in (
        ROOT / "examples" / "packages" / "refund",
        ROOT / "tests" / "digests" / "every-shape",
    ):
        plans = [plan.read_text() for plan in sorted((folder / "plans").glob("*.json"))]
        found[str(folder.relative_to(ROOT))] = package((folder / "case.json").read_text(), plans)
    return found


def test_method_1_gives_the_digests_it_pinned() -> None:
    pinned: dict[str, str] = json.loads(PINNED.read_text())
    now = {name: digest(each).sha256 for name, each in packages().items()}
    changed = sorted(name for name in pinned if now.get(name) != pinned[name])
    assert changed == [], (
        f"method {METHOD} gives another digest for {', '.join(changed)}: method {METHOD} must give "
        f"the same digest for ever, or every open case on such a package stops at its next run. "
        f"Undo the change to the models or to the digest; a new method is method {METHOD + 1}, a "
        "decision of its own (brief, D50, D51)"
    )
    unpinned = sorted(set(now) - set(pinned))
    assert unpinned == [], f"pin {', '.join(unpinned)} in {PINNED.name}"


def shapes(kind: object, found: set[type[BaseModel]]) -> None:
    """Every model the format can hold, reached from `kind` through its fields' types."""
    if typing.get_origin(kind) is typing.Annotated:
        shapes(typing.get_args(kind)[0], found)
    elif isinstance(kind, typing.TypeAliasType):
        shapes(kind.__value__, found)
    elif isinstance(kind, type) and issubclass(kind, BaseModel):
        if kind not in found:
            found.add(kind)
            for declared in kind.model_fields.values():
                shapes(declared.annotation, found)
    else:
        for argument in typing.get_args(kind):
            shapes(argument, found)


def written_fields(value: object, found: set[tuple[type[BaseModel], str]]) -> None:
    """Each model field written in `value` with something other than its default. A field that
    names its object's shape (`"type": "number"`) is always written: the digest keeps it."""
    if isinstance(value, BaseModel):
        for name, declared in type(value).model_fields.items():
            item = getattr(value, name)
            names_its_shape = typing.get_origin(declared.annotation) is Literal
            default = (
                None if declared.is_required() else declared.get_default(call_default_factory=True)
            )
            if declared.is_required() or names_its_shape or item != default:
                found.add((type(value), name))
            written_fields(item, found)
    elif isinstance(value, dict):
        for item in value.values():
            written_fields(item, found)
    elif isinstance(value, tuple | list):
        for item in value:
            written_fields(item, found)


def test_the_pinned_packages_use_every_shape() -> None:
    # Every field of every model a case or a plan can hold is written, other than at its default,
    # in some pinned package: so no model can change without a pinned digest saying so.
    models: set[type[BaseModel]] = set()
    shapes(CaseDefinition, models)
    shapes(Plan, models)
    every = {(model, name) for model in models for name in model.model_fields}
    used: set[tuple[type[BaseModel], str]] = set()
    for each in packages().values():
        written_fields(each.case, used)
        for plan in each.plans.values():
            written_fields(plan, used)
    unused = sorted(
        f"{model.__module__}.{model.__qualname__}.{name}" for model, name in every - used
    )
    assert unused == [], f"no pinned package writes {', '.join(unused)}: write it in every-shape"
