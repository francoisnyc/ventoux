"""Timers: a rule's moment that is time passing after another moment (layer 11f).

A timer is set when its moment comes, and fires once, as an event stamped with its own due time:
the case reads no clock, so the same history decides the same way in memory and on Temporal
replay (brief, D33) (brief, D44). Until then it is pending work, and it ends early once its
purpose does. See docs/layers/11-rules.md (11f).
"""

from ventoux.case.freshness import seconds_in
from ventoux.case.state import CaseState, Moment, Timer, TimerDue


class TimerRefused(Exception):
    """A firing the case won't take: no such timer is set, or it is stamped with another time."""


def set_timer(state: CaseState, rule: str, after: str, moment: Moment, at: int) -> None:
    """Set the rule's timer on `moment`, come in the decision made at `at`: due `after` then. One
    set on a run's start lives while that run does (brief, D44)."""
    timer = Timer(rule, after, occurrence(moment), at + seconds_in(after), moment.run)
    state.timers.append(timer)
    state.history.append(f"set {shown(timer)}")


def occurrence(moment: Moment) -> str:
    """The moment as a timer set on it names it, with its entry: `started review#1`, `answered
    review#2`, `event cancelled#2`; `reached paid` and `opened` come once, and need none."""
    if not moment.entry:
        return moment.said
    kind = moment.said.split(" ")[0]  # `started`, `answered` or `event`
    return f"{kind} {moment.entry}"


def fire_timer(state: CaseState, event: TimerDue) -> None:
    """The timer's time has come: it is no longer set, and its firing is its rule's moment. A
    firing for no timer set, or stamped with another time, is refused, and changes nothing (fail
    closed)."""
    timer = next((t for t in state.timers if t.rule == event.rule and t.since == event.since), None)
    if timer is None:
        raise TimerRefused(f"{event.rule} has no timer set on {event.since}: nothing fires")
    if event.at != timer.due:
        raise TimerRefused(
            f"{named(timer)} is due at {utc(timer.due)}, and this firing is stamped "
            f"{utc(event.at)}: a timer fires at its due time"
        )
    state.timers.remove(timer)
    state.moments.append(Moment(f"{timer.after} after {timer.since}", timer.run, rule=timer.rule))


def next_due(state: CaseState, at: int) -> TimerDue | None:
    """The firing due first by `at`, stamped with its due time; None if none is. Soonest first,
    and two due the same second in the order they were set (brief, D44). A driver asks again after
    each firing, which may set or end timers: so before an event stamped `at`, every timer due by
    then fires, in order, and replay decides the same."""
    due = [timer for timer in state.timers if timer.due <= at]
    if not due:
        return None
    # Python: `min` keeps the first of equals, so the earlier set wins a tie.
    first = min(due, key=lambda timer: timer.due)
    return TimerDue(first.rule, first.since, at=first.due)


def named(timer: Timer) -> str:
    """A timer as a line names it: `chase_review, 2d after started review#1`."""
    return f"{timer.rule}, {timer.after} after {timer.since}"


def shown(timer: Timer) -> str:
    """A timer as a report lists it, with its due time in UTC: `chase_review: 2d after started
    review#1, due 2026-01-03T00:00:00Z`. Where a due date reads from (brief, D44)."""
    return f"{timer.rule}: {timer.after} after {timer.since}, due {utc(timer.due)}"


def utc(seconds: int) -> str:
    """A time in whole seconds since the epoch, as a date and time in UTC:
    `2026-01-03T00:00:00Z`. Worked out by hand, since `case` imports no `datetime` (layer 0's
    boundary): Howard Hinnant's `civil_from_days`, which counts days in 400-year eras of 146 097
    days, each year starting on 1 March, so the leap day comes last."""
    days, rest = divmod(seconds, 24 * 60 * 60)
    hour, rest = divmod(rest, 60 * 60)
    minute, second = divmod(rest, 60)
    era, day_of_era = divmod(days + 719_468, 146_097)  # 719 468 days from 0000-03-01 to 1970
    year_of_era = (
        day_of_era - day_of_era // 1460 + day_of_era // 36_524 - day_of_era // 146_096
    ) // 365
    day_of_year = day_of_era - (365 * year_of_era + year_of_era // 4 - year_of_era // 100)
    month_from_march = (5 * day_of_year + 2) // 153  # 0 is March, 11 February
    day = day_of_year - (153 * month_from_march + 2) // 5 + 1
    month = month_from_march + 3 if month_from_march < 10 else month_from_march - 9
    year = era * 400 + year_of_era + (1 if month <= 2 else 0)
    return f"{year:04d}-{month:02d}-{day:02d}T{hour:02d}:{minute:02d}:{second:02d}Z"
