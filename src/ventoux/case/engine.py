"""The engine version: which version of Ventoux's deciding code a case decides as (layer 12b).

A case keeps the version it opened under to its end: it is data in its state, crossing
continue-as-new, and `decide` reads it like any value. When a later version decides some path
differently, its old branch stays, chosen by the case's version, so a history replays as it was
recorded (brief, D51). See docs/layers/12-releases.md (12b).
"""

# The version this code opens new cases at. Version 1 is the engine as merged at `b734098`: every
# path decided before then is version 1's, with no older branch kept (brief, D51).
ENGINE = 1

# Every version this code can still decide as, newest first. A version leaves this list only once
# no open case decides as it, as Temporal's patches are deprecated, then removed.
KNOWN = (1,)


class EngineUnknown(Exception):
    """A case decided as a version this code doesn't know. Not a refusal of the case: on Temporal
    it fails the workflow task, which is retried until code that knows it is deployed (brief,
    D17)."""


def known(version: int) -> int:
    """`version`, if this code can decide as it; otherwise `EngineUnknown`. Never read as an older
    version: that would decide a recorded history differently (brief, D51)."""
    if version not in KNOWN:
        versions = ", ".join(str(each) for each in KNOWN)
        raise EngineUnknown(
            f"this case decides as engine {version}, which this code doesn't know (it knows "
            f"{versions}): deploy code that knows it"
        )
    return version
