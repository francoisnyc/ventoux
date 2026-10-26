"""A deployment's configuration, and the catalog it names: the platform team's code, never guessed
(layer 14c) (brief, D59).

A project names its catalog in its own `pyproject.toml`:

    [tool.ventoux]
    catalog = "acme_platform.catalog:CATALOG"

or on the command line, `--catalog acme_platform.catalog:CATALOG`, which wins. No catalog named is
refused: a check against the wrong catalog would say "valid" for a definition the deployment
refuses. The development catalog comes only when named, `ventoux.testing:CATALOG`.
See docs/layers/14-builder.md, choice 34.
"""

import importlib
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path

from ventoux.core.catalog import Catalog

CONFIGURATION = "pyproject.toml"
DEVELOPMENT = "ventoux.testing:CATALOG"  # the development catalog, by its name


class Unconfigured(Exception):
    """A configuration that can't be read, or a catalog that can't be loaded: nothing runs."""


@dataclass(frozen=True)
class Configuration:
    """What a project's `pyproject.toml` says under `[tool.ventoux]`."""

    root: Path | None  # the folder holding it; None when there is none
    catalog: str | None = None  # `module:NAME`, the deployment's catalog
    cases: str = "cases"  # where `ventoux check` finds the builder files
    packages: str = "packages"  # where it writes the packages
    # Packages written by hand, as JSON, with no builder file: checked, never compared. Named,
    # since stale output of a removed case looks the same on disk (brief, D58).
    by_hand: tuple[str, ...] = ()
    releases: str | None = None  # where `ventoux release` keeps its records (brief, D59)
    model: str | None = None  # the model the live provider asks; none named is refused (D62)


def configuration(start: Path) -> Configuration:
    """The configuration of the project `start` is in: the nearest `pyproject.toml` at or above
    it, as tools such as pytest and ruff find theirs."""
    for folder in (start, *start.parents):
        found = folder / CONFIGURATION
        if found.is_file():
            return read(found)
    return Configuration(root=None)


def read(path: Path) -> Configuration:
    """`[tool.ventoux]` in the `pyproject.toml` at `path`."""
    try:
        data = tomllib.loads(path.read_text())
    except tomllib.TOMLDecodeError as error:
        raise Unconfigured(f"{path} isn't TOML: {error}") from None
    said = data.get("tool", {}).get("ventoux", {})
    for key in said:
        if key not in ("catalog", "cases", "packages", "releases", "by_hand", "model"):
            raise Unconfigured(f"{path}: [tool.ventoux] has no setting {key}")
    for key, value in said.items():
        if key == "by_hand":
            if not isinstance(value, list) or not all(isinstance(n, str) for n in value):
                raise Unconfigured(
                    f'{path}: [tool.ventoux] by_hand is a list of package names, such as ["legacy"]'
                )
        elif not isinstance(value, str):
            raise Unconfigured(f'{path}: [tool.ventoux] {key} is a text, such as "cases"')
    return Configuration(
        root=path.parent,
        catalog=said.get("catalog"),
        cases=said.get("cases", "cases"),
        packages=said.get("packages", "packages"),
        releases=said.get("releases"),
        model=said.get("model"),
        by_hand=tuple(said.get("by_hand", ())),
    )


def deployment_catalog(flag: str | None, found: Configuration) -> Catalog:
    """The catalog the command line names, or else the configuration. Neither is refused, never
    read as the development catalog (fail closed) (brief, D59)."""
    name = flag if flag is not None else found.catalog
    if name is None:
        raise Unconfigured(
            "no catalog is named: name the deployment's in pyproject.toml, "
            '[tool.ventoux] catalog = "module:NAME", or with --catalog module:NAME '
            f"(the development catalog is {DEVELOPMENT})"
        )
    return catalog_named(name, found.root)


def catalog_named(name: str, root: Path | None) -> Catalog:
    """The catalog `name` (`module:NAME`) gives, imported from the project at `root`.

    The platform team writes this name in its own configuration, or a person types it: it is
    never read from a definition, a story or a package. Importing it runs the platform team's code,
    as any of its modules does; nothing from a definition is ever imported (CLAUDE.md)
    (brief, D58).
    """
    module, colon, attribute = name.partition(":")
    if not colon or not module or not attribute:
        raise Unconfigured(f'a catalog is named "module:NAME", such as "{DEVELOPMENT}": not {name}')
    if root is not None:
        sys.path.insert(0, str(root))  # the project's own modules, as its tests import them
    try:
        loaded = importlib.import_module(module)
    except ImportError as error:
        raise Unconfigured(f"{module} can't be imported: {error}") from None
    finally:
        if root is not None:
            sys.path.remove(str(root))
    found = getattr(loaded, attribute, None)
    if not isinstance(found, Catalog):
        raise Unconfigured(f"{name} is not a Catalog: name the deployment's catalog itself")
    return found
