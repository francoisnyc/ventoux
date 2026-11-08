"""What the audit export writes: each record as JSON, every sensitive value sealed (layer 19b).

A record leaves Ventoux for a store the platform team keeps, for years. A sensitive value in it is
sealed by the key provider under the case's key, for its own place in the export, so destroying
the key makes it unreadable there too, in every copy (brief, D15). A value of a sensitive field
found in clear refuses the whole write: read from the definition, never from the wrapper, so a
value a bug unwrapped is still caught (brief, D31) (brief, D77).
See docs/layers/19-audit-keys.md (19b) and docs/guides/audit.md.
"""

import base64
import json
from collections.abc import Mapping
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

from ventoux.case.audit import Act, AuditRecord, Decision, Fact
from ventoux.case.definition import CaseDefinition
from ventoux.core.sensitive import Sensitive
from ventoux.temporal.codec import case_of
from ventoux.tooling.keys import KeyProvider

# Who may see each sensitive field, by field: what the export checks, and writes beside each
# sealed value so a reader can filter it (brief, D30).
type SensitiveFields = Mapping[str, tuple[str, ...]]


class ExportRefused(Exception):
    """A record the export won't write: why, naming the record and the field, never a value."""


def sensitive_fields(case: CaseDefinition) -> dict[str, tuple[str, ...]]:
    """Each sensitive field of `case`, with the roles that may see it."""
    return {
        name: tuple(field.visible_to or ())
        for name, field in case.fields.items()
        if field.sensitive
    }


def exported(
    stream: str, records: list[AuditRecord], sensitive: SensitiveFields, keys: KeyProvider
) -> list[dict[str, Any]]:
    """`records` of the workflow `stream` as the export writes them, each sensitive value sealed
    with `keys` under its case's key; `ExportRefused` if any holds a sensitive field's value in
    clear, before anything is sealed: nothing is written then."""
    for record in records:
        refuse_in_clear(stream, record, sensitive)
    return [as_written(stream, record, sensitive, keys) for record in records]


def refuse_in_clear(stream: str, record: AuditRecord, sensitive: SensitiveFields) -> None:
    """Fail closed: a value of a field the definition says is sensitive is never written unsealed,
    whatever let it through (brief, D77)."""
    for field, value in named_values(record):
        if field in sensitive and not isinstance(value, Sensitive):
            raise ExportRefused(
                f"audit record {stream}/{record.number} holds {field}, a sensitive field, in "
                "clear: nothing was written"
            )


def named_values(record: AuditRecord) -> list[tuple[str, object]]:
    """Every value in `record` with the field it is a value of: what the act gave, what each
    decision read and wrote."""
    named = list(record.act.values.items())
    for decision in record.decisions:
        named += [(fact.field, fact.value) for fact in decision.read]
        if decision.wrote is not None:
            named.append((decision.wrote.field, decision.wrote.value))
    return named


def as_written(
    stream: str, record: AuditRecord, sensitive: SensitiveFields, keys: KeyProvider
) -> dict[str, Any]:
    """`record` as one JSON object; each sensitive value sealed for its place, `audit/<stream>/
    <number>/<path>`, so moved anywhere else it doesn't open (brief, D31)."""
    place = f"audit/{stream}/{record.number}"
    sealer = Sealer(case_of(stream), sensitive, keys)
    return {
        "stream": stream,
        "number": record.number,
        "at": datetime.fromtimestamp(record.at, UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "release": record.release,
        "engine": record.engine,
        "act": act_as_written(record.act, sealer, f"{place}/act"),
        "decisions": [
            decision_as_written(decision, sealer, f"{place}/decisions/{index}")
            for index, decision in enumerate(record.decisions)
        ],
        "lines": list(record.lines),
    }


def act_as_written(act: Act, sealer: "Sealer", place: str) -> dict[str, Any]:
    return {
        "kind": act.kind,
        "by": act.by,
        "roles": list(act.roles),
        "entry": act.entry,
        "outcome": act.outcome,
        "values": {
            name: sealer.written(name, value, f"{place}/values/{name}")
            for name, value in act.values.items()
        },
    }


def decision_as_written(decision: Decision, sealer: "Sealer", place: str) -> dict[str, Any]:
    wrote = decision.wrote
    return {
        "kind": decision.kind,
        "step": decision.step,
        "entry": decision.entry,
        "rule": decision.rule,
        "read": [
            fact_as_written(fact, sealer, f"{place}/read/{fact.field}") for fact in decision.read
        ],
        "wrote": None if wrote is None else fact_as_written(wrote, sealer, f"{place}/wrote"),
        "target": decision.target,
        "reason": decision.reason,
    }


def fact_as_written(fact: Fact, sealer: "Sealer", place: str) -> dict[str, Any]:
    return {
        "field": fact.field,
        "sources": list(fact.sources),
        "value": sealer.written(fact.field, fact.value, place),
    }


class Sealer:
    """Writes a value as JSON, sealing a sensitive one with the case's key for its place."""

    def __init__(self, case: str, sensitive: SensitiveFields, keys: KeyProvider) -> None:
        self.case = case  # whose key seals: a child's and a plan run's are its case's (brief, D75)
        self.sensitive = sensitive
        self.keys = keys

    def written(self, field: str, value: object, place: str) -> object:
        """`value` as JSON: plain, or sealed with who may see it (brief, D30)."""
        if not isinstance(value, Sensitive):
            return plain_json(value)
        text = json.dumps(plain_json(value.value), sort_keys=True)
        sealed = self.keys.seal(self.case, text.encode(), place)
        return {
            "sealed": base64.b64encode(sealed).decode(),
            "part": place,
            "visible_to": list(self.sensitive.get(field, ())),
        }


def plain_json(value: object) -> object:
    """A value of the case file as JSON: an exact decimal as its text, so nothing is rounded
    (brief, D20); a date as `YYYY-MM-DD`; lists and objects through."""
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, list | tuple):
        return [plain_json(each) for each in value]
    if isinstance(value, Mapping):
        return {str(name): plain_json(each) for name, each in value.items()}
    return value
