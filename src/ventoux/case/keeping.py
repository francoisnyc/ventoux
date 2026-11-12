"""How the case file keeps a value it is given: wrapped if its field is sensitive, plain
otherwise, a date read into its day (layer 9b, layer 16a). Used where a value lands in the case
file, and where an audit record says what an act gave (brief, D76).
"""

from ventoux.case.definition import CaseDefinition
from ventoux.core.form import read_as
from ventoux.core.sensitive import Sensitive, plain


def kept(case: CaseDefinition, name: str, value: object) -> object:
    """A form's value as the case file keeps it: wrapped for a sensitive field, plain otherwise.
    The client wraps every value of a form, since it can't tell which are sensitive."""
    # Fail closed: `name` is a declared field. A name that is none has no rule to follow, so its
    # value is never unwrapped here: asking is an error (KeyError), never "not sensitive"
    # (brief, D89).
    field = case.fields[name]
    # A date's text is read into the day it names, by the field's type (brief, D66); a sensitive
    # one inside its wrapper, which holds the plain value of the field's type (brief, D31).
    read = read_as(plain(value), field.declared)
    if field.sensitive and isinstance(value, Sensitive):
        return Sensitive(read)
    return value if field.sensitive else read
