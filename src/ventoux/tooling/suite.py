"""The conformance suite's format: `suite.json`, read as closed models, so a key the format doesn't
have is refused, never ignored (fail closed) (layer 20a) (brief, D80).

Pydantic: each class lists its fields with their types, and `model_validate` checks data against
them, saying every problem with its path. `extra="forbid"` refuses a key that isn't a field.
"""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Discriminator, Field, Tag


class Closed(BaseModel):
    """A part of the format: every key named, any other refused."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class ExpectedIssue(Closed):
    """One issue an entry must give. Never a message: wording is free to change."""

    path: str  # where in the definition, as validation writes it: `steps.pay.when`
    code: str  # which rule it breaks: `UNKNOWN_FIELD`
    severity: Literal["error", "warning"]  # an error refuses the definition; a warning doesn't


class Issues(Closed):
    """What a definition that reads must give: exactly these issues; none, when it is valid."""

    issues: list[ExpectedIssue]


class ReadRefused(Closed):
    """What a definition refused when read must give: the paths it is refused at. Reading gives no
    code, so the paths alone are compared."""

    read: Literal["refused"]  # says which kind of result this is
    at: list[str]  # each path a problem is at, as its line says it; "" is the root


def expected_shape(value: object) -> str:
    """Which shape an `expected` is: refused when read if it says `read`, else a list of issues."""
    return "refused" if isinstance(value, dict) and "read" in value else "issues"


# Pydantic: a `Discriminator` picks the shape by calling `expected_shape`; each shape is `Tag`ged
# with the name it returns, so a problem is said against that shape alone.
Expected = Annotated[
    Annotated[Issues, Tag("issues")] | Annotated[ReadRefused, Tag("refused")],
    Discriminator(expected_shape),
]


class Child(Closed):
    """A child case a package's case step opens: its case and its plans, as files."""

    case: str  # its case.json, relative to the suite's folder
    plans: list[str]  # its plans' files


class PackageEntry(Closed):
    """A case with its plans and child cases, what it is read against, and what it must give."""

    name: str  # what the entry shows, said in each mismatch
    kind: Literal["package"]  # says which shape of entry this is
    case: str  # its case.json, relative to the suite's folder
    plans: list[str]  # its plans' files
    cases: dict[str, Child]  # its child cases, by reference: `repair@1`
    catalog: str  # the catalog file it is read against, by name: `development`
    expected: Expected  # what validation must give


class PlanEntry(Closed):
    """A plan alone, what it is read against, and what it must give."""

    name: str  # what the entry shows, said in each mismatch
    kind: Literal["plan"]  # says which shape of entry this is
    plan: str  # its file, relative to the suite's folder
    catalog: str  # the catalog file it is read against, by name: `development`
    expected: Expected  # what validation must give


# Pydantic: `Field(discriminator="kind")` picks the shape by the entry's `kind`, so a problem is said
# against that shape alone.
Entry = Annotated[PackageEntry | PlanEntry, Field(discriminator="kind")]


class Suite(Closed):
    """The whole suite: the engine version it describes, and its entries."""

    engine: int  # the engine version whose validation it states (brief, D51)
    entries: list[Entry]


def path_of(loc: tuple[int | str, ...]) -> str:
    """Where a problem is in `suite.json`, as it is written: `entries.0.expected.issues.0.code`.
    Pydantic's `loc` also names the shape it picked, an entry's kind after `entries.N` and the
    shape of `expected` after it; neither is in the file, so both are left out."""
    parts = [str(part) for part in loc]
    if parts[:1] == ["entries"] and len(parts) > 2:
        del parts[2]  # the entry's kind: `package` or `plan`
    if "expected" in parts and parts.index("expected") + 1 < len(parts):
        del parts[parts.index("expected") + 1]  # the shape of `expected`: `issues` or `refused`
    return ".".join(parts)
