"""Provenance: where a value came from, as a set of sources (brief, D12).

A source is a text, `origin:name`. See docs/layers/04-provenance.md.
"""

# The origins a value can come from: a system, or a person's answer, both trusted; or something a
# developer declared untrusted, such as `untrusted:llm` (brief, D12).
TRUSTED_ORIGINS = ("system:", "person:")
UNTRUSTED_ORIGIN = "untrusted:"
# A plan field with no declared source: the case gives it, and the plan can't see its origin. Only
# the static check uses it; the runtime check sees the real sources (docs/layers/04-provenance.md).
CASE = "case"


def is_trusted(source: str) -> bool:
    """Whether `source` is one the engine trusts: from a system, a person, or the case."""
    return source == CASE or source.startswith(TRUSTED_ORIGINS)


def is_untrusted(source: str) -> bool:
    """Whether `source` was declared untrusted, such as `untrusted:llm`."""
    return source.startswith(UNTRUSTED_ORIGIN)
