"""A release's notes: the semantic diff against the record before it (layer 13d).

Made when the record is, from the stored packages, never from the working tree, and kept in the
record, which is never written over (brief, D50) (brief, D57). Anything the notes can't read
refuses the release: nothing is recorded without them. See docs/layers/13-diff.md (13d).
"""

from collections.abc import Sequence

from ventoux.case.changes import Against, DiffRefused, Notes
from ventoux.case.diff import diff
from ventoux.case.releases import METHOD, Hash, Record, RecordRefused, changed, stored
from ventoux.core.catalog import Catalog, NotInCatalog
from ventoux.core.contract_hash import contract_hash


class NotesRefused(Exception):
    """Notes that can't be made whole: the release is refused, saying why (brief, D57)."""


def notes_for(kept: Record, records: Sequence[Record], catalog: Catalog) -> Notes:
    """The notes of `kept`, a new record, against the record before it among `records`: the
    latest wording of the release before, or of its own release for a wording revision. Both
    packages are read back from the records, each checked against its digest (`stored`)."""
    name = f"{kept.name} {kept.release}" + (f", wording {kept.wording}" if kept.wording > 1 else "")
    earlier = before(kept, records)
    if earlier is None:
        return Notes(None)  # the first release: nothing to compare
    try:
        old, new = stored(earlier, kept.name), stored(kept, kept.name)
        promised_as_recorded(earlier, catalog)
        found = diff(old, new, catalog)
    except (RecordRefused, DiffRefused, NotesRefused) as refused:
        raise NotesRefused(f"{name}'s notes can't be made: {refused}") from None
    if kept.wording > 1 and (found.changes or found.rewritten):
        # A wording revision has its release's digest: a diff saying otherwise is a bug, said.
        raise NotesRefused(
            f"{name}'s notes can't be made: a wording revision's diff says more than wording"
        )
    # Never less than the digest: every path it saw change is said (brief, D55).
    said = [change.path for change in found.changes] + [line.path for line in found.rewritten]
    missing = [
        path
        for path in changed(old, new).behaviour
        if not any(path == where or path.startswith(f"{where}.") for where in said)
    ]
    if missing:
        raise NotesRefused(
            f"{name}'s notes can't be made: they don't say {', '.join(missing)}, which the "
            "digest saw change"
        )
    against = Against(earlier.release, earlier.wording)
    return Notes(against, found.changes, found.rewritten, found.wording)


def before(kept: Record, records: Sequence[Record]) -> Record | None:
    """The record `kept` is compared with: for a release, the latest wording of the release
    before it; for a wording revision, the wording before it; None for release 1."""
    if kept.wording > 1:
        wanted = [(kept.release, kept.wording - 1)]
    else:
        wordings = [r.wording for r in records if r.release == kept.release - 1]
        wanted = [(kept.release - 1, max(wordings))] if wordings else []
    found = [r for r in records if (r.release, r.wording) in wanted]
    if kept.release == 1 and kept.wording == 1:
        return None
    if not found:
        raise NotesRefused(f"{kept.name} {kept.release}: no record before it to compare with")
    return found[0]


def promised_as_recorded(earlier: Record, catalog: Catalog) -> None:
    """Each contract `earlier` names still promises, in `catalog`, what it recorded: otherwise
    the notes would compare a promise that release never ran (brief, D57)."""
    where = f"{earlier.name} {earlier.release}"
    for reference, recorded in earlier.contracts.items():
        try:
            now = Hash(METHOD, contract_hash(catalog.lookup(reference)))
        except NotInCatalog:
            raise NotesRefused(
                f"{reference} isn't in the catalog: {where} called it, and the notes read its "
                "promise"
            ) from None
        if now != recorded:
            raise NotesRefused(
                f"{reference}'s promise in the catalog isn't the one {where} recorded"
            )
