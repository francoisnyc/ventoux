"""The conformance suite's format: `suite.json`, read as closed models, so a key the format doesn't
have is refused, never ignored (fail closed) (layer 20a) (brief, D80).

Pydantic: each class lists its fields with their types, and `model_validate` checks data against
them, saying every problem with its path. `extra="forbid"` refuses a key that isn't a field.
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict


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


class Entry(Closed):
    """One definition, what it is read against, and what validation must give."""

    name: str  # what the entry shows, said in each mismatch
    kind: Literal["package"]  # a case with its plans and children
    case: str  # its case.json, relative to the suite's folder
    plans: list[str]  # its plans' files
    cases: dict[str, str]  # its child cases, by reference: `repair@1`
    catalog: str  # the catalog file it is read against, by name: `development`
    expected: Issues | ReadRefused  # what validation must give


class Suite(Closed):
    """The whole suite: the engine version it describes, and its entries."""

    engine: int  # the engine version whose validation it states (brief, D51)
    entries: list[Entry]
