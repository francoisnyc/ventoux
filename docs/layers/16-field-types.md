# Layer 16: More field types: dates, options, attachments

Status: 2026-11-01, agreed. This note starts from `main` at `12f26a7`, with layers
0 to 15 merged. The warm-up was answered and recorded (learning question 43). The guides were
written first (curriculum step 2): `docs/guides/expressions.md`, `docs/guides/case-data.md` and
`docs/guides/builder.md` describe the date as if 16a worked, with the recommendations below. If a
choice is answered otherwise, the guides change with it.

**Answered 2026-11-01.** Choices A to C and 1 to 10 as recommended. D66 is written before 16a is
built.

Prior art: none in the prototype (the curriculum says so). Read for the date: the code a date
touches today, `src/ventoux/core/expressions/` (the types, the check, the evaluator, the
rendering), `src/ventoux/core/form.py` (`fits`), `src/ventoux/case/types.py` (`case_types`,
`output_type`, `fits_type`) and `src/ventoux/temporal/converter.py` (how a `Decimal` crosses a
payload). FEEL, whose one-line style D20 adopted, writes a date literal `date("2026-10-31")`; its
`today()` is exactly what Ventoux leaves out.

## Warm-up: learning question 43, what an injected instruction can still influence

Recorded in `docs/LEARNING.md`, entry 43. The step advisor is shielded from the words, never the
facts: arrivals still shape what it is shown, so it can tilt which admissible step a person is
shown, never a value or a run. The authoring-loop half was filled in on request, so the question
stays open.

## What this layer is for

**A field type is a check as much as a shape.** Today a case can hold a number, a text, a boolean,
an outcome, a reference or a list. A day on the calendar has to be a text, so `"31/10/2026"`,
`"yesterday"` and `"2026-02-30"` are all accepted, and two of them can't even be ordered: `<`
compares numbers only. The layer adds three types, each checked where its value enters the case:

| Type | What the check is | Where it runs |
|---|---|---|
| **date** (16a) | a real day on the calendar, ordered | pure: at validation and in the evaluator |
| **option** (16b) | one of a registered system's list (a branch, a product) | when the answer is given, through an activity, recorded |
| **attachment** (16c) | a reference to a registered document store; never the bytes | when it is given; the history holds the reference |

**A date is a value, not a clock.** `incident_date >= policy_start` reads two facts the case file
holds, recorded when they were given: the same answer today, tomorrow and on replay. "Was it in
the last 30 days?" would read the calendar, and decide differently on replay (learning question
32, for `now`); a day also depends on a time zone, which a moment doesn't carry. So no expression
reads today. "Within 30 days" is said with two recorded dates, or with a timer (brief, D44), whose
firing the history records.

## The split

| PR | What it builds | Its negative test |
|---|---|---|
| **16a: the date** | A `date` field type and a `date` literal; equality, ordering and `string` on dates; a date checked wherever a value enters the case (the opening, a form, an activity's output, an event's payload); the rendering; the builder's `Field.date()`; the JSON Schema; the diff and the plain forms naming the type. | **curriculum:** a date compared with a number is refused before anything runs. Also: `{"today": []}` has no shape; `"2026-02-30"`, `"20261031"` and a moment (`2026-10-31T23:30`) are not dates; a date compared with a text is refused. |
| **16b: the option** | A field whose values are a registered system's list, checked through a read-only activity when the answer is given, the check recorded. | **curriculum:** an option the system's list doesn't hold is refused, and the refusal recorded. |
| **16c: the attachment** | A reference to a registered document store, given with an answer; the history holds the reference, never the bytes. | **curriculum:** an attachment that names no registered store is refused. |

**Why this order.** The date is entirely inside the expression language and the pure layers:
nothing new crosses a payload but a value. The option leans on activities, called when an answer
is given, which is new for a form. The attachment builds on references (brief, D16) and on a store
the platform team registers. Each part's choices are written when that part starts, so 16b and 16c
are only sketched here.

### Where each point of the curriculum's layer 16 lands

1. **A field type is a check as much as a shape:** every part; for the date, choices 1 and 7.
2. **A date is a value, not a clock; no expression reads today:** choices 2 and 5.
3. **An answer checked against a system when it is given:** 16b.
4. **A document kept as a reference, never its bytes:** 16c.
5. **In the definition format, the JSON Schema, the builder, the diff and the plain forms:** for
   the date, choices 8 and 9.

## Choices for the whole layer

A. **The split:** 16a, 16b, 16c, as in the table, in that order, one pull request each
   (`layer-16a-dates`, …). *Recommended.*

B. **Decisions: one per part,** recorded in the brief before its part is built, added and never
   rewriting an earlier one: D66 for the date. 16b and 16c take the next numbers when they start.
   D20's operator list is not rewritten: D66 says what it adds to it ("Adds to D20, whose text is
   kept"), as earlier decisions have. *Recommended.*

C. **No new dependency.** The date is Python's `datetime.date`; the check is a small named
   function. *Recommended.*

## Choices for 16a: the date

1. **How a date is written in JSON.** JSON has no date, so it is text, and the declared type makes
   it a date.
   - **In a case file, an answer, an event or an output:** exactly `YYYY-MM-DD`, ten characters,
     a real day: `"2026-10-31"`. Refused: `"2026-02-30"`, `"2026-1-5"`, `"31/10/2026"`, and a
     moment, `"2026-10-31T23:30:00Z"`. *Note:* Python's `date.fromisoformat` accepts more than this
     since 3.11 (`"20261031"`, the week date `"2026-W44-6"`), so the check is its own named
     function, `calendar_date`, and a test pins each of those refusals.
   - **The years:** 0001 to 9999, Python's range, four digits. *Recommended.*
   - **As a literal in an expression:** `{"date": "2026-10-31"}`, read `date("2026-10-31")`, FEEL's
     notation. A bare `"2026-10-31"` stays a text, so `incident_date == "2026-10-31"` is refused
     (same type on both sides, D20). The alternatives: no literal at all (a fixed date, such as a
     regulation's start, would then have to be a field the opener fills), or treating any text
     shaped like a date as one (a guess, and a text field could change meaning). *Recommended:*
     the literal.

2. **Which comparisons and operators it gets.**
   - `==`, `!=` between two dates; `<`, `<=`, `>`, `>=` between two dates (until now, numbers
     only); `string` of a date gives `"2026-10-31"`; `exists` as for any field; `if` and `in`
     with dates as for any type (`in` takes a list of date literals).
   - **No date arithmetic in 16a:** no `date + days`, no "days between". "Reported within 30
     days" is then `reported_on <= date(…)`, a compute activity, or a timer. The alternative is
     a named operator, `days(from, to)` giving a number, which a deadline written as data would
     want. It would be a decision of its own, recorded in D20's list with its reason; nothing in
     16a needs it, and the README draft's "Beyond v1.0" (timers anchored to a date) is where it
     would come with a use. *Recommended:* none now.
   - The messages change for the ordering operators: "`>` compares two numbers or two dates, and
     this is a string", and "…, and this is a number, not a date" when one side is a date. The
     guide quotes both.

3. **Where a date may come from, and its provenance.** From where every value comes from, with
   that place's source, unchanged: the opener (`system:opener`), a person's form (the person, as
   any answer), an activity's output (its contract's sources, D29; an output annotated
   `datetime.date` is read as a date by `output_type`), an event's payload (as declared, D41), and
   a field declared untrusted (`untrusted:customer`: it may inform, never decide, D38). **The
   engine never gives one:** no field is filled with today's date, the case's opening day
   included. *Recommended.* The alternative, an `opened_on` date the engine fills from workflow
   time, would need choice 4's time zone, and is the clock by another door.

4. **What a date has to do with time zones.** Nothing: a date is a day, the same everywhere. A
   moment becomes a day only in a time zone (23:30 on 31 October in New York is 1 November in
   UTC), so **Ventoux never turns a moment into a day**. Whoever gives the date chooses which day
   it means: the adjuster, or the activity whose system knows its business's zone, whose contract
   then says it returns a date. *Recommended.* The alternative, a deployment-wide zone used to
   turn workflow time into a day, makes a case's decisions depend on where it is deployed.

5. **No expression may read today.** Written into D66 in plain words, as D20 says it for the
   clock: no operator reads the calendar, and `today` has no shape, so it can't be written, by a
   person or a model under the JSON Schema (D60). `{"today": []}` is refused with the list of
   operators, as `{"now": []}` is. The tests: the check's refusal, and the published schema
   holding no `today`. *Recommended.*

6. **A date inside the engine is a `datetime.date`, never a `datetime`.** The evaluator works on
   Python values (a number is a `Decimal`, D20), so a date is a `date`, compared as one. Two traps:
   - **`datetime` is a subclass of `date` in Python,** so `isinstance(moment, date)` is true.
     Every place that takes a date (`fits`, the evaluator, the builder) refuses a `datetime`
     explicitly, with a negative test each.
   - **On a payload, a date is text.** Temporal's JSON can't hold a date, and reading it back
     gives a `str`. So the converter writes a `date` as `"YYYY-MM-DD"`, and the engine reads a
     value into a date **by its field's declared type** where a value enters: the opening, an
     answer, an event, an activity's output, and the state a case continues as new with (D27).
     Nothing is guessed from a text's shape. *Corrected in the tutor's review of the design:* this
     said an output "is already read by its contract's Pydantic model", but outputs are read with
     lax `model_validate` (`case/runtime.py`), unlike inputs (strict, D36): a timestamp
     `1793145600` landed as 2026-10-28, a day Pydantic picked in UTC, and `"2026-10-31T00:00:00Z"`
     and a `datetime` at midnight as 2026-10-31. Strict mode alone would refuse `"2026-10-31"`,
     which is how a date comes back over Temporal. So an output's date fields are read by
     `calendar_date`, as the other entry points are, before Pydantic reads the rest: a moment, a
     number or any other text fails the step, and nothing it gave lands.
     *Recommended.* The alternative, keeping dates as text inside the engine and comparing texts,
     works for `YYYY-MM-DD` by luck of the format, but then a date and a text look the same at
     runtime, and "a field holds a value of the wrong type" can't be told (fail closed lost).
   - A consequence for the form: D9's form "converts nothing" today. Reading a date from its text
     by its declared type is the one reading added, written in D66: a text that isn't a date is
     refused, never guessed.

7. **What is refused, and where.**
   - At validation (`ventoux check`, case validation): a date compared with a number or a text;
     an ordering between a date and anything else; a literal that isn't a day; `today`.
   - Where a value is given: a date field given a text that isn't a day, a number, or a moment,
     each refused with what is wrong, then what to do: `incident_date is a date, written
     YYYY-MM-DD, and the answer gives a string that isn't one`. *Corrected while building:* this
     quoted the value, `"31/10/2026"`; a refusal names the kind, never the value, since it reaches
     people who may not see it (brief, D30).
   - At runtime, failing closed: a date field holding a `str`, a `datetime` or a number is an
     error (`` `<` compares two numbers or two dates, and it was given a string ``), never `false`.
     *Corrected while building:* the evaluator is untyped and refuses by operator, so the message
     names the operator, not the field.

8. **Shown, and where the type appears.**
   - **The one-line rendering:** a field by its name; a literal as `date("2026-10-31")`.
   - **The plain forms, the case map and the diff (D55, D56):** a date as `2026-10-31`, never a
     day name or a local format, so the same everywhere and in every language. A field whose type
     changes (a text to a date) is reported by the diff as a change of type, as for any field.
     Formatting a date for a person's locale is the inbox's, later. *Recommended.*
   - **The JSON Schema (D60):** a date field as `{"type": "date"}`, and the literal as an object
     with one key, `date`, a string matching `^[0-9]{4}-[0-9]{2}-[0-9]{2}$`; the schema stays
     shape only (D60), and the calendar check is the engine's. *Corrected in the tutor's review of
     the design:* "ten characters" let `"31/10/2026"` through, so the pattern says the shape.

9. **The builder (D58).** `Field.date()`, and a `datetime.date` as a literal, written `{"date":
   "…"}`. A `datetime` is refused (choice 6). `date.today()` in a builder file is the build day
   written in as a fixed date; the builder can't tell it from any other date, and `--unchanged`
   catches it the next day. The guide says so. *Recommended.*

10. **What 16a leaves out.** Times, moments and durations as field types; date arithmetic (choice
    2); timers anchored to a date field (README draft, "Beyond v1.0"); a locale's formatting.

## Seams and tests for 16a (curriculum step 4)

*Asked before the seams were agreed (2026-11-01): "we don't deal with UTC or time zones; what if
workers run in different datacenters?"* The engine is safe: its time is seconds since the epoch,
from the history, and a date compares the same anywhere. The gap is an activity turning a moment
into a day with the machine's zone: two workers would give the same moment different days.
**Answered:** the activities guide says an activity names its zone; a test runs the date tests
under two process time zones; D66 gains a bullet (it is unmerged and nothing cites it yet).

11. **The seams the tests use,** all public today; no test reads an internal:
    - **Expressions** (`ventoux.core.expressions`): `parse_expression(data)` refuses a literal
      that isn't a day (`ExpressionInvalid`); `check(expression, types)` with a new `DateType`
      (`{"type": "date"}`) in the types; `evaluate(expression, values)` with a `datetime.date`
      among the values; `render(expression)`.
    - **A case, in memory** (`ventoux.case`): `parse_case(data)` reading a `{"type": "date"}`
      field; `run_case_in_memory(case, catalog, implementations, events)` with `Opened(file=…)`,
      `Answered(form=…)` and an event's arrival giving dates, as text and as `date`; what the run
      reports (its history, a refusal's message, the view's values).
    - **Validation:** `ventoux check` on a definition (a date compared with a number refused
      before anything runs), and the type an activity's output annotated `datetime.date` is read
      as, through a step's condition reading it.
    - **On Temporal:** one test on the test server: a case opened with a date, answered with one,
      sent one by an event, continued as new, then a proposal whose condition reads two dates,
      decided in the new run; its view queried. *Corrected while building:* this said "the dates
      come back as dates", but a query's answer is a payload, where a date is its text (D66), so
      the view gives `"2026-10-31"`; what comes back as a day is the case's own state, which the
      proposal's admission proves.
    - **The builder, the schema, the readings:** `Field.date()` and a `datetime.date` literal
      producing the JSON; `case_schema()` (a date field and the literal, no `today`); the plain
      diff and the case map, through `ventoux diff` and `ventoux map` output as the guides show.
    - **The guides:** the existing guide tests (`test_the_guide_reads_as_the_renderer_renders`,
      `test_the_guide_refuses_as_the_check_refuses`, `test_the_guides_examples_are_the_files_their_tests_run`)
      run the new rows, so the docs can't drift; a new one runs the runtime table, which no test
      read until now.

12. **The tests, in order, negative first,** each watched failing for the right reason:
    1. `{"date": "2026-02-30"}` is refused (then `"20261031"`, `"2026-W44-6"`, `"2026-1-5"`, a
       moment, year 0); `{"date": "2026-10-31"}` reads `date("2026-10-31")`.
    2. **The curriculum's:** a date compared with a number is refused by `check`; then with a text;
       two dates order; `string` of a date is a text; `{"today": []}` refused with the list.
    3. `evaluate`: a date field holding a text, or a `datetime`, is an error, never `false`; two
       dates compare; `string` gives `YYYY-MM-DD`.
    4. A case: a form giving `"31/10/2026"`, a number or a `datetime` for a date is refused with
       what to do; `"2026-10-31"` is read into a date by its type, and a condition reads it.
    5. The opening and an event's payload, the same; an activity's output annotated
       `datetime.date` is read as a date by a condition, and a contract output that is a
       `datetime` is refused at registration.
    6. On Temporal: the round trip, through continue-as-new (choice 6).
    7. The builder: `Field.date()`, a literal, a `datetime` refused; `examples/builder/dates.py`.
    8. The schema: a date field and literal; no `today` anywhere in it.
    9. The plain diff and the case map name a date field's type; a type changed from text to date
       is reported.
    10. The date tests, run in a subprocess with `TZ=America/New_York` and again with
        `TZ=Pacific/Kiritimati` (UTC+14), give the same results: the engine reads no local zone.

## Decided while building 16a

- **The clock behind `date`** (asked 2026-11-01, answered (a)). The boundary test banned
  `datetime` in `core` and `case`, and `date.today()` lives on the `date` class. (a): a pure layer
  imports exactly `from datetime import date`, and the boundary test refuses `today`, `now`,
  `utcnow`, `fromtimestamp` and `astimezone`, as attributes and through `getattr` with the name
  written out, each with a negative test; a moment is refused by its exact type, `is_day`. (b),
  set aside: Ventoux's own day type, with no clock, and a conversion at every edge. D66 says so.
  *A known limit:* `getattr(date, name)` with a name computed at runtime isn't seen; nothing in
  `core` or `case` reads an attribute by a name from data on a date.
- **No new engine version.** Every definition readable before 16a decides as it did; no recorded
  history holds a message that changed. By D60's dated line the format's `$id` stays `engine-2`.
- **The guide's runtime table isn't run by any test,** and one row (`approved_amount should be a
  number, and it holds a string`) is a message nothing produces: the evaluator is untyped and
  refuses by operator. Raised for the promises (step 6).
- **A sensitive date** (slice 4). The wrapper holds "the plain value, of its field's type"
  (brief, D31), but the reading skipped wrapped values, so a sensitive date was kept as
  `Sensitive("2026-10-31")` and its condition could never read it as a day. Now the day is read
  inside the wrapper, with a test. The opening keeps its values as a form does, through the same
  `kept`, so a date given at the opening is read into a day too.
- **Four walkers over expressions** (slice 5). Besides the parser, the check, the evaluator and the
  renderer, four functions walk an expression and fail closed on a node they don't know:
  `fields_read` (`core/provenance.py`), `given_as_reference` (`core/before_activity.py`), and the
  readings in `case/warnings.py` and `case/known.py`. Each now takes a date literal as a literal,
  reading no field, and each has a test that fails without it (one by mutation: the reference
  input's message said "a computed value" for a date literal, not "a value written in the
  definition"). Found because `parse_case` raised `TypeError: not an expression: date` on a
  condition holding a literal. *Worth a later check:* a test that every walker knows every kind
  of literal, so a fifth kind can't be missed the same way.
- **An activity's date output is read as a date by validation** (`output_type`, `case/types.py`),
  so a condition comparing it with a number is refused before anything runs.
- **The Temporal round trip** (slice 6). The converter writes a `date`, matched exactly, as its
  text, and refuses a `datetime`; `state_from_data` takes the declared types (`case_types`) and
  reads each date back into a day, a sensitive one inside its wrapper, refusing one that isn't.
  The types are required, so a caller can't forget them; the tests whose states hold no date pass
  `{}`. The first version of the Temporal test passed with the reading removed: `settle` was
  admitted before the crossing, so nothing read a date after it. Now the adjuster proposes it in
  the new run, and with the reading removed the proposal is refused, failing closed.
- **The builder** (slice 7). `Field.date()` reads as a `DateExpr`, compared with another date or
  a `datetime.date`, written `{"date": "…"}`; `string` and `in_` take a date. *A limit of the type
  check:* a `datetime` is a `date` to mypy too, so `incident < datetime(…)` type-checks, and the
  builder refuses it only when the file runs, by its exact type. The guide quotes that refusal,
  and a test reads the guide's line.
- **The release digest couldn't read a date** (slice 7): `canonical` fails closed on a value it
  doesn't know, so no package with a date literal could have been released. A date now digests as
  `{"#date": "2026-10-31"}`, as a decimal is `{"#decimal": …}`, so a date and its text digest
  apart (a test, watched failing with the plain text). No package pinned before 16a holds a date,
  so method 1 gives each the digest it pinned (brief, D51).
- **A pinned package of its own for the date** (`tests/digests/dates`), not a date added to
  `every-shape`: every-shape's digest is pinned for ever, and changing its content would change
  it. The new package gets its first pin; every existing pin is unchanged.
- **A plan's fields take dates too.** A case's and a plan's fields share one list of types
  (`DeclaredType`, `core/plan.py`), so adding the date there gives both, and the plan schema says
  so. Nothing in 16a promises more about plans than that the type parses.
- **Two schema refusals test nothing** (`tests/test_schema.py`, layer 14e): "an operator D20
  doesn't list" and "a number written as a string" put an approval on `settle`, a plan step,
  which takes none, so the schema refuses them for that. Left to 14e's owner; 16a's literal test
  uses `settle`'s own `when`, with a control the schema accepts.

## Sketched, decided when their parts start

- **16b, the option.** Which activity checks it, and its contract's shape; whether the list is
  read once or at each answer; what is recorded when an answer is refused; whether an expression
  compares an option as a text or only with `==`.
- **16c, the attachment.** How a store is registered (beside resolvers, D16); what an answer gives
  (a reference the store issued, never bytes); what the history and the plain forms show; who may
  open it (the viewer, through the store, as D16's resolvers).

## Promises

To be written with 16a's tests (curriculum step 6): each claim this note and the guides make
about the date, and the test that fails if it isn't true.
