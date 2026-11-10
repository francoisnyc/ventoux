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
from dataclasses import dataclass, field
from pathlib import Path

from ventoux.core.catalog import Catalog

CONFIGURATION = "pyproject.toml"
DEVELOPMENT = "ventoux.testing:CATALOG"  # the development catalog, by its name


class Unconfigured(Exception):
    """A configuration that can't be read, or a catalog that can't be loaded: nothing runs."""


@dataclass(frozen=True)
class Identity:
    """One identity a command may connect to Temporal as: its certificate and its key, as file
    paths, never their contents (brief, D81)."""

    cert: str  # the client certificate's file: `/etc/ventoux/operator.pem`
    key: str  # its private key's file, readable by its owner only


@dataclass(frozen=True)
class Temporal:
    """Where Temporal is and who a command connects as: `[tool.ventoux.temporal]` (brief, D81)."""

    address: str  # Temporal's frontend: `ventoux-prod.a1b2c.tmprl.cloud:7233`
    namespace: str  # `ventoux-prod.a1b2c`
    server_ca: str | None = (
        None  # the file of the CA that signed the server's certificate, if private
    )
    identities: dict[str, Identity] = field(default_factory=dict[str, Identity])  # by name


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
    model: str | None = None  # the model the live provider asks; none named is refused (brief, D62)
    drafts: str | None = None  # where `ventoux draft` writes; none named is refused (brief, D63)
    # Where Temporal is and who commands connect as; None: localhost, no TLS (brief, D81).
    temporal: Temporal | None = None
    keys: str | None = None  # `module:NAME`, the deployment's key provider (brief, D81)
    audit: str | None = None  # `module:NAME`, the deployment's audit store (brief, D81)


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
    said = dict(data.get("tool", {}).get("ventoux", {}))
    temporal = temporal_of(path, said.pop("temporal")) if "temporal" in said else None
    for key in said:
        if key not in (
            "catalog",
            "cases",
            "packages",
            "releases",
            "by_hand",
            "model",
            "drafts",
            "keys",
            "audit",
        ):
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
        drafts=said.get("drafts"),
        by_hand=tuple(said.get("by_hand", ())),
        temporal=temporal,
        keys=said.get("keys"),
        audit=said.get("audit"),
    )


def temporal_of(path: Path, said: object) -> Temporal:
    """`[tool.ventoux.temporal]` as the format says, or `Unconfigured` naming the key that isn't
    (fail closed: never a default guessed for a production namespace) (brief, D81)."""
    where = f"{path}: [tool.ventoux.temporal]"
    if not isinstance(said, dict):
        raise Unconfigured(f"{where} is a table of settings")
    for key in said:
        if key not in ("address", "namespace", "server_ca", "identities"):
            raise Unconfigured(f"{where} has no setting {key}")
    examples = {"address": '"localhost:7233"', "namespace": '"default"', "server_ca": '"ca.pem"'}
    for key, example in examples.items():
        if key in said and not isinstance(said[key], str):
            raise Unconfigured(f"{where} {key} is a text, such as {example}")
    for key in ("address", "namespace"):
        if key not in said:
            raise Unconfigured(f"{where} needs {key}, such as {examples[key]}")
    identities = said.get("identities", {})
    if not isinstance(identities, dict):
        raise Unconfigured(f"{where} identities is a table, one per identity")
    return Temporal(
        said["address"],
        said["namespace"],
        said.get("server_ca"),
        {name: identity_of(path, name, given) for name, given in identities.items()},
    )


def identity_of(path: Path, name: str, said: object) -> Identity:
    """One identity's table: exactly a `cert` and a `key`, each a file's path."""
    where = f"{path}: [tool.ventoux.temporal.identities.{name}]"
    if not isinstance(said, dict):
        raise Unconfigured(f"{where} is a table: cert and key, each a file's path")
    for key in said:
        if key not in ("cert", "key"):
            raise Unconfigured(f"{where} has no setting {key}")
    cert, key = said.get("cert"), said.get("key")
    if not isinstance(cert, str) or not isinstance(key, str):
        raise Unconfigured(f"{where} needs cert and key, each a file's path")
    return Identity(cert, key)


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
    found = named(name, root, "a catalog", DEVELOPMENT)
    if not isinstance(found, Catalog):
        raise Unconfigured(f"{name} is not a Catalog: name the deployment's catalog itself")
    return found


def named(name: str, root: Path | None, what: str, example: str) -> object:
    """The object `name` (`module:NAME`) gives, imported from the project at `root`: the
    platform team's code, named in its configuration, never read from a definition (brief, D59)."""
    module, colon, attribute = name.partition(":")
    if not colon or not module or not attribute:
        raise Unconfigured(f'{what} is named "module:NAME", such as "{example}": not {name}')
    if root is not None:
        sys.path.insert(0, str(root))  # the project's own modules, as its tests import them
    try:
        loaded = importlib.import_module(module)
    except ModuleNotFoundError as error:
        raise Unconfigured(f"{module} can't be imported: {error}") from None
    except Exception as error:  # noqa: BLE001 (the platform team's code may raise anything)
        # Said by its kind alone: its message may hold anything, a secret included.
        raise Unconfigured(
            f"{module} can't be imported: it raised {type(error).__name__}"
        ) from None
    finally:
        if root is not None:
            sys.path.remove(str(root))
    if not hasattr(loaded, attribute):
        raise Unconfigured(f"{module} has no {attribute}")
    return getattr(loaded, attribute)
