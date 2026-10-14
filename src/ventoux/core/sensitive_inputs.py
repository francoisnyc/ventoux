"""Which values computed from expressions carry a sensitive value (layer 9b).

A value computed from a sensitive one is sensitive too: an input `{"cat": ["id:", {"var":
"national_id"}]}` holds the national ID, whatever it computed. So an input, a plan step's field or
an approval's digest is wrapped whenever its expression reads a wrapped value (brief, D31).
"""

from collections.abc import Mapping

from ventoux.core.expressions import Expression
from ventoux.core.provenance import fields_read
from ventoux.core.sensitive import Sensitive


def reads_sensitive(expression: Expression, values: Mapping[str, object]) -> list[str]:
    """The fields `expression` reads whose values are sensitive, in order."""
    return [field for field in fields_read(expression) if isinstance(values.get(field), Sensitive)]


def kept_sensitive(expression: Expression, values: Mapping[str, object], value: object) -> object:
    """`value`, computed from `expression`, wrapped if it read a sensitive value: an input built
    from a national ID carries it, whatever it computed (brief, D31)."""
    return Sensitive(value) if reads_sensitive(expression, values) else value
