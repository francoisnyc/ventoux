"""The audit store: where a case's records are kept, append-only, apart from Temporal (layer 19b).

A store is two methods: `append`, which keeps each record once by its stream and number, and
`read`, which gives a case's records back, each stream in order (brief, D77). In production it is
the platform team's (a database table, a bucket), written to that shape; `FileAudit` is the
development store. Ventoux never deletes from a store: its retention is the platform team's
(brief, D8) (brief, D15).
See docs/layers/19-audit-keys.md (19b) and docs/guides/audit.md.
"""

import fcntl
import json
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Protocol

# What a record is, to a store: the JSON object the export writes (`ventoux.temporal.audit`).
type Written = dict[str, Any]


class AuditRefused(Exception):
    """A record the store won't keep: why. Nothing of the call that brought it is kept."""


class AuditStore(Protocol):
    """Keeps records once, in order, by stream; gives them back. A record sent again is the same
    when it is equal with each sealed value taken by its place, never its ciphertext: sealing the
    same value again gives other bytes (`same`)."""

    def append(self, records: list[Written]) -> None: ...

    def read(self, prefix: str) -> list[Written]: ...


class FileAudit:
    """Development only: one JSON Lines file per stream, in `folder`, only ever appended to."""

    def __init__(self, folder: Path | str) -> None:
        self.folder = Path(folder)

    def append(self, records: list[Written]) -> None:
        """Keep each record once, in order: the same record again is accepted, as a retried write
        sends it; one with other content, or one whose stream lacks the number before it, is
        refused, and nothing of the call is kept (brief, D77). One write at a time: two runs of
        a case may send the same records at once, across a continue-as-new."""
        with self.locked():
            self.keep(records)

    def keep(self, records: list[Written]) -> None:
        """Check every record against what is kept, then append the new ones."""
        kept = {stream: self.stream(stream) for stream in {each["stream"] for each in records}}
        new: dict[str, list[Written]] = {stream: [] for stream in kept}
        for record in records:
            stream, number = record["stream"], record["number"]
            known = kept[stream] + new[stream]
            if number <= len(known):
                if not same(known[number - 1], record):
                    raise AuditRefused(
                        f"audit record {stream}/{number} is already kept, with other content"
                    )
                continue  # kept already: a write retried after a crash
            if number != len(known) + 1:
                # Fail closed: a gap is a record lost on the way, never filled in later.
                raise AuditRefused(
                    f"audit record {stream}/{number} can't be kept: {stream}/{len(known) + 1} is "
                    "missing"
                )
            new[stream].append(record)
        for stream, adding in new.items():
            if adding:
                path = self.path(stream)
                path.parent.mkdir(parents=True, exist_ok=True)
                with path.open("a") as file:
                    file.writelines(json.dumps(each, sort_keys=True) + "\n" for each in adding)

    @contextmanager
    def locked(self) -> Iterator[None]:
        """Hold the store's lock while a write checks and appends."""
        self.folder.mkdir(parents=True, exist_ok=True)
        with (self.folder / ".lock").open("w") as lock:
            # fcntl: an exclusive lock on the file, released when it closes.
            fcntl.flock(lock, fcntl.LOCK_EX)
            yield

    def read(self, prefix: str) -> list[Written]:
        """The records of the stream `prefix` and of every stream under it (`claim-7/forget`,
        `claim-7/repair#1`), each stream in order, the streams by name."""
        streams = [prefix] if self.path(prefix).exists() else []
        under = self.folder / prefix
        if under.is_dir():
            streams += sorted(
                str(path.relative_to(self.folder).with_suffix(""))
                for path in under.rglob("*.jsonl")
            )
        return [record for stream in streams for record in self.stream(stream)]

    def stream(self, stream: str) -> list[Written]:
        """The records kept for one stream, in order."""
        path = self.path(stream)
        if not path.exists():
            return []
        return [json.loads(line) for line in path.read_text().splitlines()]

    def path(self, stream: str) -> Path:
        """Where a stream is kept: its workflow ID as a path, `claim-7/repair#1.jsonl`."""
        return self.folder / f"{stream}.jsonl"


def same(kept: Written, sent: Written) -> bool:
    """Whether `sent` is the record already kept: equal, each sealed value compared by its place
    and who may see it. A record sent again after a crash, or by the next run of its case, is
    sealed afresh, with a fresh nonce: other bytes, the same value at the same place."""
    return by_place(kept) == by_place(sent)


def by_place(value: object) -> object:
    """`value` with each sealed value replaced by its place and who may see it."""
    if isinstance(value, dict):
        if "sealed" in value:
            return {"part": value.get("part"), "visible_to": value.get("visible_to")}
        return {name: by_place(each) for name, each in value.items()}
    if isinstance(value, list):
        return [by_place(each) for each in value]
    return value
