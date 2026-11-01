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
     answer, an event, and the state a case continues as new with (D27). An activity's output is
     already read by its contract's Pydantic model. Nothing is guessed from a text's shape.
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
     each refused with what is wrong, then what to do: `incident_date should be a date, written
     YYYY-MM-DD, and "31/10/2026" is not one`.
   - At runtime, failing closed: a date field holding a `str`, a `datetime` or a number is an
     error (`incident_date should be a date, and it holds a string`), never `false`.

8. **Shown, and where the type appears.**
   - **The one-line rendering:** a field by its name; a literal as `date("2026-10-31")`.
   - **The plain forms, the case map and the diff (D55, D56):** a date as `2026-10-31`, never a
     day name or a local format, so the same everywhere and in every language. A field whose type
     changes (a text to a date) is reported by the diff as a change of type, as for any field.
     Formatting a date for a person's locale is the inbox's, later. *Recommended.*
   - **The JSON Schema (D60):** a date field as `{"type": "date"}`, and the literal as an object
     with one key, `date`, a string of ten characters; the schema stays shape only (D60), and the
     calendar check is the engine's.

9. **The builder (D58).** `Field.date()`, and a `datetime.date` as a literal, written `{"date":
   "…"}`. A `datetime` is refused (choice 6). `date.today()` in a builder file is the build day
   written in as a fixed date; the builder can't tell it from any other date, and `--unchanged`
   catches it the next day. The guide says so. *Recommended.*

10. **What 16a leaves out.** Times, moments and durations as field types; date arithmetic (choice
    2); timers anchored to a date field (README draft, "Beyond v1.0"); a locale's formatting.

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
