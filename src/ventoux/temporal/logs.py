"""What the worker's log may say about a failure: its exception's type, never its text (layer 9b).

Temporal's SDK logs a failed activity, and a failed workflow task, with its exception and
traceback, before the failure converter seals them. An exception may quote a sensitive value
(`no record for 1 85 05 …`), and a worker's log goes where many people read it. So the worker
keeps only the exception's type, as the history keeps only `‹sensitive›` (brief, D31). An
activity's own logging is its author's: Ventoux can't filter it.
See docs/layers/09-case-data.md (9b).
"""

import logging

# The loggers Temporal's SDK writes an exception to, from the activity and workflow workers.
# Python: a logger's filter sees only the records logged on it, not those of its children, so
# each is named.
TEMPORAL_LOGGERS = (
    "temporalio.activity",
    "temporalio.workflow",
    "temporalio.worker._activity",
    "temporalio.worker._workflow",
    "temporalio.worker._workflow_instance",
)


class ExceptionTypeOnly(logging.Filter):
    """Keeps a record, with its exception's type in place of the exception: no message, no
    traceback."""

    def filter(self, record: logging.LogRecord) -> bool:
        # Python: `exc_info` is (type, exception, traceback), or True, None or False.
        if isinstance(record.exc_info, tuple) and record.exc_info[0] is not None:
            record.msg = f"{record.msg} ({record.exc_info[0].__name__})"
        record.exc_info, record.exc_text, record.stack_info = None, None, None
        return True


TYPE_ONLY = ExceptionTypeOnly()


def keep_only_exception_types() -> None:
    """Install the filter on Temporal's worker loggers, once."""
    for name in TEMPORAL_LOGGERS:
        logger = logging.getLogger(name)
        if TYPE_ONLY not in logger.filters:
            logger.addFilter(TYPE_ONLY)
