# Layer 14: the Python builder

Status: 2026-10-25, from `main` at `a2ea563` (layers 0 to 13 merged). The warm-up was answered and
recorded. Prior art read: the `chartering` prototype at `81389b3` (its `main`), whose
`thoughts/qrspi/2026-10-01-01/task.md` defers three research questions to this layer. Layer 14 is
explained and split into five parts below. Each choice, for the whole layer and for 14a, has a
recommendation. Answered "all as recommended", the same day: choices 1 to 16, `jsonschema` as a
dev dependency included (choice 10, for 14e). D58 and the dated line on D7 written before
building 14a.

## Warm-up: learning question 1, JSON or code first

> An AI drafts a new case definition. A developer then wants to change one rule in it. What happens
> if code is the only way people edit definitions? And what if JSON is the contract?

Open since the design sessions, and never answered before. It is the question this layer rests on:
the builder is code, and the JSON it writes is what everything checks, diffs and runs (brief, D1).

Answered 2026-10-25: "the developer changes the code and regenerates the contract?", then, after a
nudge towards the AI's half, "AI produces JSON directly?". Both are right, but neither half was
put in its own case. They were discussed and recorded, and the question stays open until both
cases come back from memory, each with its reason.

## Prior art

**What the prototype has: no builder.** `chartering` was written straight in JSON. Its task file
leaves three research questions "for the builder task":

1. how Pulumi (`Output<T>`, `apply`) and AWS CDK tell build-time values from runtime ones;
2. how CDK keeps synthesis deterministic (`cdk.context.json`), and how both tools map errors in
   what they generate back to source lines;
3. what escape hatches each tool offers, and how Camunda's fluent BPMN builder and XState type
   their definitions.

Answered from what is known of these tools, not checked against their documentation again here
(choice 12 offers that):

1. **Build time and runtime, told apart by type.** Pulumi never lets you read an `Output<T>` while
   the program runs. You transform it with `apply`, and the result is another `Output`. CDK
   encodes a value known only at deploy time as a *token*, a placeholder string resolved when the
   template is written. Pulumi's way is the safer one: the type says what isn't known yet.
   Ventoux takes it, and goes further: a runtime value (`Expr[...]`) can't be turned into a
   Python value at all, not even inside an `apply` (choice 3).
2. **Determinism.** A CDK app may look things up in an account. It caches the answers in
   `cdk.context.json`, committed, so synthesis gives the same template every time. Ventoux's
   builder looks nothing up: the catalog is read by `ventoux check`, never by the builder. So
   nothing outside the file can change its output, and CI makes sure the output stays the same
   (choice 8). **Source lines:** CDK records a stack trace for each construct, in its metadata
   (`aws:cdk:trace`), and `cdk synth` can point back to the line that made it. Ventoux records
   one line per builder call and maps each problem's path to it (choice 5).
3. **Escape hatches.** CDK lets you override any property of the generated template
   (`addPropertyOverride`) because its higher-level constructs don't cover everything. Ventoux's
   builder is one-to-one with the JSON (brief, D1), so it needs no hatch inside it. The hatch is
   the JSON itself: a definition may still be written as JSON, and is checked the same way.
   Camunda's fluent builder (`Bpmn.createProcess().startEvent().serviceTask()…`) types the next
   *call*, not the values in conditions, which stay strings. XState types its machine's context
   and events, and checks guards as functions. Neither gives typed expressions that become data,
   which is what D20 needs.

## What this layer is for

Until now, every definition has been JSON written by hand. The quickstart has always shown
Python (brief, D1): a typed builder that writes the JSON. **The builder is code that produces
data.** The JSON it writes is what is checked, released and run. The builder never runs inside
the engine, and never on model output. Nothing is evaluated, executed or imported from a
definition.

A small example, the quickstart's `pay`:

```python
LIMIT = 100  # build time: a Python value, known when the file runs

pay = refund.activity(
    "pay",
    "payments.refund@2",
    title="Refund the customer",
    inputs={"order_id": order_id, "amount": approved},
    when=review.outcome == "approve",
    approval=Approval(
        when=approved > LIMIT,
        roles=["support-lead"],
        reason="Refunds over 100 need a team lead",
    ),
)
```

`approved > LIMIT` isn't `True` or `False`. `approved` is a field, a value only a case holds, so
the comparison is a **runtime expression**, `Expr[bool]`, decided by each case when `pay` may run.
`LIMIT` is a **build-time value**: Python knows it now, and it is written into the JSON as a
literal:

```json
"approval": {
  "when": {">": [{"var": "approved_amount"}, 100]},
  ...
}
```

Two mistakes the types catch:

- `when=True`, or `inputs={"amount": 250}`: a plain Python value where a runtime expression is
  required. mypy refuses it before anything runs, roughly: `Argument "when" … has incompatible type
  "bool"; expected "Expr[bool] | None"`. This is the curriculum's first negative test.
- `if approved > LIMIT:` in the builder file: a build-time decision taken on a runtime value.
  Python asks the expression for a `bool`, and the builder refuses: "approved_amount > 100 is
  decided by each case, when it runs, never when the file runs: give it as `when=`".

And a mistake only the bytes catch: someone edits `packages/refund/case.json` by hand, or changes
`refund.py` and forgets to regenerate. CI writes the JSON again from the Python, compares it byte
for byte with what is committed, and fails on any difference. This is the curriculum's second
negative test.

## The split

| PR | What it builds | Its negative test |
|---|---|---|
| **14a: the quickstart's builder, and the same JSON** | `Case`, `Field`, `Outcome`, `Approval`, typed runtime expressions (`Expr[T]`) for the quickstart's refund: fields, a reference, tasks, activities, an approval, `requires`, `when`, `sequence`. The JSON written in one layout, byte for byte the same each time. `run_case` takes the builder's case and runs the JSON it writes. The quickstart's tests switch to the Python definition, as the quickstart shows. | **curriculum:** a plain Python value where a runtime expression is required fails mypy; and a build-time `if` on a runtime value is refused |
| **14b: the rest of the format** | everything else a case and a plan can say, one-to-one: milestones, events and wait steps, workflow and plan steps, rules, `sla`, `reminder`, `four_eyes`, close reasons, `sensitive`, `visible_to`, `max_age`, `forgetting`; plans and their states | a key the format has and the builder can't write fails a coverage test |
| **14c: `ventoux check` and the deployment's catalog** | the command: runs the builder files, checks each package against the deployment's catalog, says each problem at its source line, writes the package folders. How a team's catalog is loaded, and which commands take it. The D48 warning. `ventoux simulate` against a team's catalog. | a problem is reported at the line that made it; no catalog configured is refused, never read as the development one |
| **14d: the same JSON, checked in CI** | `ventoux check --unchanged`: generates again and compares byte for byte, writing nothing; a step in CI's `check` job; where a deployment keeps its release records | **curriculum:** regenerated output that differs from the committed JSON fails CI |
| **14e: the JSON Schema, published from Pydantic** | `ventoux schema`: the case and plan schemas generated from the models, describing the JSON as written; committed, and checked unchanged in CI like 14d | an expression with an operator D20 doesn't list is refused by the schema, as `parse_case` refuses it |

**Why this order.** 14a is the core idea, typed runtime expressions and bytes that don't move, on
the smallest definition that runs end to end. It carries the first curriculum test. 14b widens
the same pattern to the whole format. It is mechanical once 14a's shape is agreed, so it comes
second. 14c needs a whole format to check. 14d needs `ventoux check` to regenerate. 14e is
independent, but its CI check reuses 14d's.

### Where each point lands

- **The builder is code that produces data; definitions are data:** every part. The rule is
  written once, in D58 (choice 11).
- **The same JSON, byte for byte:** 14a writes it (choice 4); 14d checks it in CI (choice 8).
- **Typed runtime expressions:** 14a (choice 3).
- **`ventoux check`, source lines, the deployment's catalog:** 14c (choices 5 to 7).
- **The JSON Schema:** 14e (choice 10).
- **Names the brief gives the builder:** 14a and 14b (choice 9).
- **Carried notes:** the D48 warning, 14c (choice 7c); `ventoux simulate` against a team's
  catalog, 14c (choice 7b); where release records live, 14d (choice 8c).

## Choices for the whole layer

Answer by number. "Recommended" is what I'd do; the options set aside are named.

1. **The split:** 14a to 14e as in the table, in that order. *Recommended.* Set aside: the whole
   format in the first part. That would be about thirty kinds of entry in one pull request, before
   the shape of one is agreed.

2. **Where the builder lives.** `src/ventoux/tooling/builder/`, a few small files (the case, the
   expressions, the writer, the source lines). The brief already puts the builder in `tooling`
   (brief, "Layers of the system"). The quickstart's names are re-exported from `ventoux`
   (`from ventoux import Case, Field, Approval, Outcome`). The builder imports no Temporal, and a
   test checks that `import ventoux` loads no `temporalio`. Without that test, the re-export would
   pull Temporal into every `core` import, because Python runs `ventoux/__init__.py` first.
   *Recommended.* Set aside: a separate package (`ventoux-builder`). It is one more thing to
   release, for no reader.

3. **Build time and runtime, told apart by type** (the curriculum's first negative test):
   - A field, a step's outcome and an output are **runtime values**: `Expr[T]`, where `T` says
     what each case will hold (`Decimal`, `str`, `bool`, an outcome, a reference, a list).
     Comparisons and arithmetic on them (`>`, `==`, `+`, …) give another `Expr`, never a Python
     value. A Python value on the other side of an operator (`approved > 100`) is a build-time
     literal, written into the JSON as it is.
   - Where the format needs an expression (`when=`, an approval's `when=`, `inputs=`, a rule's
     `set=`), the parameter is typed `Expr[…]`. A plain `True` or `250` fails mypy. A literal
     input is written explicitly: `literal(250)`. That keeps "this is a constant" visible, and
     matches what D55 shows as "a literal input".
   - `bool()` on an `Expr` raises, naming the expression and saying to give it as `when=`. So
     `if`, `and`, `or`, `not` and chained comparisons (`0 < amount < 100`) on runtime values are
     refused when the file runs: each of them asks Python for a `bool` (fail closed).
   - `and`, `or` and `!` (D20) are functions, `and_(a, b)`, `or_(a, b)` and `not_(a)`, named after
     the JSON operators as Python's `operator` module names them. Set aside: overloading `&`, `|`
     and `~`. Python binds them tighter than comparisons, so `amount > 1 & urgent` would build
     `amount > (1 & urgent)`. That type-checks and means something else.
   - Numbers are `int` or `Decimal`, never `float` (D20: exact decimals) and never `bool`. A
     `float` fails mypy and raises if it reaches the builder anyway. `True` is refused as a number
     wherever one is wanted, as D47 refuses it for `count`.
   - `==` and `!=` return an `Expr`. That breaks Python's own typing of `__eq__`, so the two
     methods carry `# type: ignore[override]`, with a comment saying why. SQLAlchemy does the
     same.

   *Recommended.*

4. **The written JSON: one layout, byte for byte** (brief, D1, D50):
   - The writer is `json.dumps(…, indent=2, ensure_ascii=False)`, then one line break. That is
     the standard library's own layout, with no home-made formatter.
   - Keys are in the order the format writes them (the order of the models' fields: `case`,
     `display`, `fields`, `milestones`, `steps`, …). Maps (steps, fields, rules) are in the order
     the builder calls made them, since that order is behaviour (D38, D50).
   - A key at its default is left out unless the author gave it. One meaning, one text, as the
     digest already reads it (D50).
   - Numbers are written as the decimal the engine holds: `100` stays `100`, and `Decimal("100.0")`
     stays `100.0` (D50: they differ). A `Decimal` in exponent form (`1E+2`), NaN or infinity is
     refused, naming the field. JSON has no NaN, and an exponent would read back as another text.
   - The writer reads its own output back (`json.loads(…, parse_float=Decimal)`) and checks it
     gives the same definition. A value that doesn't survive the round trip is refused, never
     written.

   The hand-written JSON the builder takes over is written once in this layout. Its bytes change;
   its digest doesn't, since the digest reads the parsed definition, never the text (D50). A test
   shows the digests equal. *Recommended.* Set aside: reproducing the hand-written files' compact
   style (`{"var": "order_id"}` on one line). That needs a formatter of our own: more code, and
   one more thing that must be deterministic.

5. **Errors at source lines.** Each builder call records the file and line it was called from
   (the caller's frame, read with `inspect` when the file runs, in `tooling`). Each entry it makes
   (a field, a step, an approval, an outcome) keeps that line. `ventoux check` gives every
   problem its path, as the validators already do (`steps.pay.inputs.amount`). It is placed at
   the line of the longest recorded path it starts with:
   `cases/refund.py:24: steps.pay.inputs.amount: INPUT_POLICY …`. A path no entry records gets the
   `Case(…)` line, never dropped. Shape errors (`parse_case`'s) and validation issues (layers 3
   and 10) are mapped the same way. A Python error while the file runs is Python's, with its own
   traceback. *Recommended.*

6. **`ventoux check`** (brief, D34: "reads the Python file and maps errors to source lines"):
   - `ventoux check [PATH …] [--out DIR]`. A `.py` path is run as Python (`runpy.run_path`, the
     standard library): it is code the team wrote and reviewed. A package folder is **read as
     JSON, never run**, so a definition someone wrote as JSON, or one a model drafted, is checked
     with no Python at all. With no path given, every `*.py` in `cases/` is run.
   - From a `.py` file, every `Case` and `Plan` defined at its top level, found by type, never by
     name. Each case and the plans its plan steps name make one package (D50).
   - Each package is checked as `ventoux release` checks it (layers 3 and 10), against the
     deployment's catalog (choice 7). Each problem is printed at its line (choice 5), errors
     before warnings, and then the quickstart's summary (`✓ refund is valid (3 steps)`, one line
     per step).
   - The package folder is written only when nothing refuses it: `build/refund/case.json` and
     `build/refund/plans/…`, with the case map beside it (`build/refund.md`, 13c's `case_map`).
     A refused package writes nothing, and says so.
   - Exit 0 when every package is valid (warnings printed), 1 when one is refused, 2 when a path
     can't be read or the file raises. The same codes as `ventoux release`.
   - **The quickstart changes, with a dated line:** it says `build/refund.json`; D50 later made a
     package a folder, so `build/refund/case.json`. Then `ventoux release` reads `build/refund/`
     as it is.

   *Recommended.*

   *Amended 2026-10-25, from the tutor review of #56* (the text above stands; 14c decides the
   rest): the written JSON is committed and is what runs, so it never goes in `build/`, which
   Python's usual `.gitignore` ignores. A team's repository very likely ignores it too, and the
   JSON would then pass on the developer's machine, never reach review, and be missing in CI.
   14c's choice of where `ventoux check` writes package folders starts from `packages/<case>/`
   (`packages/refund/case.json`), the layout 14a's quickstart project already uses.

7. **The deployment's catalog, and which commands take it:**
   - **How it is loaded.** The catalog is the platform team's Python, never anything from a
     definition. The deployment names it in its project's `pyproject.toml` (read with `tomllib`,
     from the standard library):
     ```toml
     [tool.ventoux]
     catalog = "acme_platform.catalog:CATALOG"
     ```
     or on the command line, `--catalog acme_platform.catalog:CATALOG`, which wins. The module is
     imported by that name (`importlib.import_module`), and the attribute must be a `Catalog`,
     else it is refused. CLAUDE.md's ban on `importlib` is about definitions: this name is written
     by the platform team in its own configuration, never read from a definition, a story or a
     package. A comment says so where it is imported.
   - **Fail closed.** No catalog named is an error, saying both ways to name one. It is never
     silently the development catalog: a check against the wrong catalog says "valid" for a
     definition the deployment refuses. This repository names `ventoux.testing:CATALOG` in its
     own `pyproject.toml`, so its commands, tests and CI work as today.
   - **Which commands take it:** every command that reads contracts or roles: `check`, `release`,
     `diff`, `map`, `notes`, `simulate`, `summary`, `promises` and `hashes`. "Against the
     development catalog until `ventoux check` brings the deployment's" (D50, D55, D56, and 13e's
     choice 63) ends, with a dated line on each. The environment commands read manifests and the
     registry, not the catalog, and don't change.
   - **7b. `ventoux simulate` against a team's catalog:** it takes the catalog like the others.
     Activities still run only the story's fakes, so nothing real is reached (D45): the catalog
     gives contracts and roles, never implementations.
   - **7c. The D48 warning,** with `ventoux check`: a new warning in case validation,
     `KEPT_FROM_STARTING`. It is raised on a step whose own `when` reads untrusted data, and on a
     rule that starts a step under a condition that reads untrusted data, unless the step reaches
     a `closes_when` milestone (then the case can't close without it). The message names the
     step, the field and its source, never a value. It says that false keeps the step from
     starting, so the case may close without it, and how to guard a step that must happen: a
     `closes_when` milestone only it reaches, or a task. It is a warning, so it refuses nothing
     (D48). It lives in `case/warnings.py`, so `ventoux release` and CI's summary print it too.
     The history line D48 promised was already built (`say_kept_from_starting`).

   *Recommended.*

8. **The same JSON in CI** (the curriculum's second negative test):
   - **8a.** `ventoux check --unchanged` generates every package again, in memory, and compares
     each file with the committed one byte for byte. It writes nothing. A file that differs, is
     missing or isn't generated by anything fails with exit 1, naming it and its first differing
     line, then "run `ventoux check` and commit what it writes".
   - **8b.** CI's `check` job gains one step, `uv run ventoux check --unchanged` (plus `ventoux
     schema --unchanged`, 14e). It keeps 13e's care: `permissions: contents: read` unchanged, no
     `pull_request_target`, nothing that writes. The `changes` job (the summary) is unchanged.
     `test_the_existing_checks_are_as_they_were` gains the new lines.
   - **8c. Where a deployment keeps its release records** (13e's choice 76): in a folder the
     deployment names, `[tool.ventoux] releases = "…"` in the same configuration, which `ventoux
     release` and `ventoux notes` use when `--releases` isn't given. The tool only reads and
     writes a folder (D50's `FolderStore`), never git or a network. Keeping it is the
     deployment's job: a checkout of a records repository, or a mounted bucket. CI in this
     repository still doesn't run `ventoux release`: writing records needs a token that writes,
     which 13e's read-only workflow refuses on purpose. A deployment runs it on merge, in its own
     pipeline. The releases guide says so.

   *Recommended.*

9. **Names the brief gives the builder: kept, except one.**
   - **Kept:** `Case`, `.field`, `.reference(…, system=)`, `.task`, `.activity`, `Field.number()`,
     `Outcome(…, sets=[…])`, `Approval(when=, roles=, reason=)`, `.sequence(…)`, `requires=[…]`,
     `source="untrusted:customer"` (the quickstart); the patterns `sla` and `reminder` (D7, D46);
     **`four_eyes`** (D47), a function giving `Approval(count=2, …)`, which writes `"count": 2`.
     `count=n` is there too, one-to-one with the JSON. `since=first_start` isn't offered (D46).
   - **Changed, with a dated line on D7:** D7 says that "in the Python builder, conditions use
     `unless=` / `only_if=`, since `if` is reserved". That was written when a rule was *when / if
     / then*. Since D38 a rule's condition is written `when` in the JSON, and `if` is no key. So
     the builder says `when=`, one-to-one with the JSON, as the quickstart already does for steps.
     `unless=` would be a second spelling of `not_`.

   *Recommended.*

10. **The JSON Schema, published from Pydantic** (brief, D4, D20):
    - `ventoux schema [--out DIR] [--unchanged]` writes `schema/case.schema.json` and
      `schema/plan.schema.json`, generated by `model_json_schema` from the models `parse_case` and
      `parse_plan` use. They are committed, and CI checks them unchanged, as in choice 8.
    - **It must describe the JSON as written, and today it doesn't.** I generated it while
      planning. A field's type comes out under `declared`, which is the model's internal name,
      not the JSON's flat `type`. The name patterns (`[a-z][a-z0-9_]*`) are missing, since they
      are checked by validators the schema can't see. And an expression comes out as Python's
      models, not D20's operators. 14e fixes each where it is declared, with Pydantic's own
      means (`WithJsonSchema`, `json_schema_extra`), and keeps no second, hand-written schema.
    - **The schema is looser than validation, and says so.** It constrains shape (keys, types,
      patterns, operators). Whether an expression fits its fields, or a step can be reached, is
      `ventoux check`'s to prove. Layer 15 gives the schema to a model, and everything it writes
      is still validated.
    - **Tested against the examples:** every JSON definition in `examples/` is accepted by the
      schema, and the refusals named in the guides (an unknown operator, `"count": "2"`, a field
      with no `type`) are refused by both the schema and `parse_case`. That needs a JSON Schema
      validator. **I'm asking first:** `jsonschema`, as a **dev dependency only** (tests, never
      at runtime). The alternative is no validator, testing the schema's text for known pieces.
      That is weak: a schema nobody validates against could say what the format doesn't.

    *Recommended:* add `jsonschema` to the dev group, if you agree.

11. **Where it is recorded:**
    - **New decisions:** D58, "The Python builder: code that produces data, typed runtime
      expressions, the same JSON byte for byte, never run inside the engine or on model output";
      D59, "`ventoux check` and the deployment's catalog"; D60, "The JSON Schema, published from
      Pydantic".
    - **Dated lines,** each decision's text kept: D1 (the layout and the CI check), D7
      (`when=`, choice 9), D34 (`ventoux check` built), D48 (the warning built), D50 and D55 and
      D56 (the deployment's catalog), D50 again (where records live, choice 8c).
    - **The guides:** the quickstart, written first, as the builder's tutorial (the package
      folder, the catalog's configuration), with every Python example run by a test; and a new
      guide, `docs/guides/builder.md`, for the whole builder from 14b, with each example run by
      a test.

    *Recommended.*

12. **The deferred research questions:** answered above, in "Prior art", from what is known of
    Pulumi, CDK, Camunda and XState, not checked against their documentation. *Recommended:* no
    separate research note. Each choice that leans on them (3, 4, 5) stands on its own reasons,
    and none depends on a detail of those tools. Set aside: a short research note from their
    documentation before 14a. That is worth it only if you'd like the analogy checked.

## 14a. The quickstart's builder, and the same JSON

User-facing description, written first once you agree: the quickstart's sections 2, 3 and 5
(the Python file, `ventoux check`, the tests), as they already read, with the package folder.

### What this part is for

The quickstart's `cases/refund.py` runs. Its `refund` writes the JSON the engine runs, the same
bytes every time. The quickstart's tests pass `refund` to `run_case`.

### What the code does today

- `case/definition.py`: `CaseDefinition`, `parse_case`. The builder writes what `parse_case`
  reads, and checks its output with it.
- `core/expressions/`: the expression model, `parse_expression`, and `render`, the one-line form.
  An `Expr` renders through `render`, so its error says `approved_amount > 100` as diffs do.
- `testing.py`: `run_case(definition: dict, …)`, and `load_definition`, which reads numbers as
  `Decimal`.
- `tests/test_quickstart.py`: the acceptance tests, on `examples/refund/refund.json`.

### Choices for 14a

13. **The seams the tests use:**
    - `Case`, `Field`, `Outcome`, `Approval`, `literal`, `and_`, `or_`, `not_` from `ventoux`;
    - `written(case) -> str`: the package's `case.json`, as bytes would be written;
    - `run_case(refund, …)`: a builder case is accepted where a definition was;
    - mypy, run on small source snippets through `mypy.api` (it is already a dev dependency), for
      the type tests. That is the only way to test "fails the type check". One test module runs
      every snippet in one mypy call, to keep it fast.

    *Recommended.*

14. **`run_case` runs the JSON, never the Python objects.** Given a builder case, it writes it
    (`written`), reads the text back as `load_definition` does, and runs that. So a test runs
    exactly the bytes the engine would get. *Recommended.*

15. **Where the quickstart lives in this repository:** `examples/quickstart/cases/refund.py`, and
    the package it writes, `examples/quickstart/build/refund/case.json`, a project laid out as
    the quickstart shows. *(Amended 2026-10-25, from the tutor review of #56: the package is
    `examples/quickstart/packages/refund/case.json`, where git keeps it; see choice 6's line.)* `tests/test_quickstart.py` imports `refund` from it, exactly as the
    quickstart writes it (curriculum, tracer bullet). `examples/refund/refund.json` stays as
    hand-written JSON: stories and other tests read it, and a definition may still be written as
    JSON (choice 12's hatch). A test checks that it and the built one have the same behaviour
    digest, so the two can't drift apart in behaviour. *Recommended.*

16. **What 14a's builder covers:** what the quickstart writes, and no more. That is fields of
    each type the quickstart uses (`number`, and a `reference` with its system), `source=`,
    tasks with outcomes and `sets`, activities with `inputs`, `when`, `requires` and one
    `approval`, and `sequence`. Anything else waits for 14b. *Recommended.*

### Slices, in order (14a)

Each starts with its negative test, seen failing for the right reason.

0. **A plain Python value where a runtime expression is required fails mypy** (the curriculum's
   test), and `bool()` on an expression raises.
1. **Fields and expressions:** `approved > 100` writes `{">": [{"var": "approved_amount"}, 100]}`;
   a `float` and `True` are refused as numbers.
2. **Tasks, activities, the approval, `sequence`:** the quickstart's whole `refund`.
3. **The bytes:** `written(refund)` is the same text every time, and reads back to the same
   definition; a `Decimal` in exponent form is refused; the built refund's digest equals the
   hand-written one's.
4. **The quickstart's tests on the Python definition,** through `run_case(refund, …)`.

### Decided while building (14a)

- **`ventoux` is marked as typed** (`src/ventoux/py.typed`, PEP 561). Found by slice 0's first run:
  without the marker mypy skips the package, so a team's builder file would type-check against
  nothing, and the curriculum's negative test would pass nowhere outside this repository.
- **The layout is written by one small function, `layout`,** not by `json.dumps`: the standard
  library can write a `Decimal` only through a binary float. It writes `json.dumps`'s `indent=2`
  layout exactly, and a test holds the two together on the quickstart's JSON (choice 4).
- **A number is written with every digit** (`format(value, "f")`): `Decimal("1E-7")` is written
  `0.0000001`, which reads back as the same decimal. `Decimal("1E+2")` would be written `100` and
  read back as another one, so it is refused, saying to write `Decimal("100")`.
- **The keys' order is the guides' and the hand-written JSON's, not the models' fields':** a step
  writes `kind` and `display` first, then what it is (`roles`, or `activity` and `inputs`), then
  when it may start (`requires`, `when`), then what it gives or needs (`outcomes`, `approval`).
  The models put `kind` last, through inheritance. The built refund is the hand-written one as
  data, key for key.
- **A number operator takes numbers only:** `amount + True` is refused when the file runs, as a
  `float` is, found writing slice 1's negative test (`operand` let `True` through as a literal).
- **Two entries of one name are refused** (`refund already has a field named amount`): a dict
  would keep the second and drop the first without a word.
- **`==` and `!=` accept any operand at type level,** checked when the file runs: a misspelled
  outcome (`"aprove"`) is `ventoux check`'s to catch, as the quickstart says, since it needs the
  task's declared outcomes.
- **The quickstart's project is on pytest's and mypy's paths** (`examples/quickstart`), so its
  tests import `cases.refund` as the quickstart writes it. The quickstart's import line is sorted
  as ruff sorts it (`Approval, Case, Field, Outcome`), the one change to its text.
- **The written JSON lives in `packages/`, never `build/`** (found by CI on #56, decided in the
  tutor review): the repository's Python template ignores every `build/`, so
  `examples/quickstart/build/refund/case.json` was written in the working tree, passed locally,
  was never committed, and was missing in CI (`FileNotFoundError`). A first fix un-ignored the
  quickstart's `build/`; the review asked instead for a folder git keeps by default, since a
  team's own repository very likely ignores `build/` too. So the package is
  `examples/quickstart/packages/refund/case.json`, `.gitignore` is `main`'s, and 14c's choice of
  where `ventoux check` writes starts from `packages/<case>/` (choice 6's dated line). Confirmed
  the way CI sees it: a fresh clone of the pushed head, then the full test run.
- **From the tutor review of #56, the optional items, each decided:**
  - *a form never sets a step's outcome:* tested on its own. The earlier test gave
    `[amount + 1, review.outcome]`, and `amount + 1` was refused first, so the outcome was never
    reached. The guard already held; it was broken once to see the new test fail.
  - *`sequence()` called twice is refused,* as a second entry of one name is: a case has one
    `sequence`, and a second call replaced the first without a word. Test first, seen failing.
  - *the engine's processes never load the builder:* `ventoux` re-exports the builder's names
    lazily (a module `__getattr__`, PEP 562), so `import ventoux.temporal.worker` leaves
    `ventoux.tooling.builder` unloaded. That makes "never runs inside the engine" (D58) checkable.
    `__all__` is written out, since strict mypy reads exports only from a literal one, found by
    the type tests.
  - *`==` typed by the expression's `T`:* deferred to 14b, which adds the other kinds of `Expr`
    (outcomes, references, truth values, lists). Typing `==` then covers every kind in one place,
    where doing it now would type only numbers. A misspelled outcome still needs the task's
    declared outcomes, so it stays `ventoux check`'s to catch either way.
- **The built package was written once with `written`;** `ventoux check` writes it from 14c, and
  CI checks it from 14d. Until then a test holds the committed bytes to `written`.
- **Code ahead of its test, said plainly:** the task, the activity and the approval were written
  in one go with slice 1, so slice 2's test passed on its first run instead of failing first.
  Each refusal in them got a negative test afterwards, and each was broken once to see it fail.

### Promises (14a)

Each claim this part makes about behaviour, and the test that would fail if it weren't true. `T`
is `tests/test_builder_types.py` (new), `B` is `tests/test_builder.py` (new), `Q` is
`tests/test_quickstart.py`, `L` is `tests/test_layers.py`. Checked against the tests, 2026-10-25,
and again after the tutor review of #56: every test named here exists, every test in `T` and `B`
is named here, and every guard was broken once to see its test fail.

| Promise | Test |
|---|---|
| A plain Python value where a runtime expression is required fails mypy: `when=True` (the curriculum's test) | T `test_a_plain_value_where_a_runtime_expression_is_required_fails_the_type_check` |
| A plain value as an input fails mypy; `literal(250)` type-checks | T `test_a_plain_value_as_an_input_fails_the_type_check` |
| A text beside a number fails mypy | T `test_a_text_beside_a_number_fails_the_type_check` |
| The quickstart's builder file type-checks clean, so each refusal above comes from its own line | T `test_the_quickstarts_builder_file_type_checks` |
| A runtime value asked for a build-time decision (`if`, a chained comparison) raises, naming the expression | B `test_a_runtime_value_asked_for_a_build_time_decision_is_refused` |
| Operators write D20's JSON, a Python value beside one as a literal, either side | B `test_a_comparison_writes_d20s_json` |
| `and_`, `or_` and `not_` write `and`, `or` and `!` | B `test_and_or_and_not_are_functions_writing_d20s_operators` |
| A `float`, NaN or `True` is refused as a number, the float saying to write a `Decimal` | B `test_a_float_or_a_truth_value_is_refused_as_a_number` |
| A plain value the type checker missed is refused when the file runs | B `test_a_plain_value_the_type_checker_missed_is_refused_when_the_file_runs` |
| A form sets fields only: an expression is refused | B `test_a_form_sets_fields_only` |
| A form never sets a step's outcome | B `test_a_form_never_sets_a_steps_outcome` |
| Two entries of one name are refused | B `test_two_entries_of_one_name_are_refused` |
| A second `sequence` is refused | B `test_a_second_sequence_is_refused` |
| The built refund is the hand-written one as data, with the same behaviour digest | B `test_the_quickstarts_refund_reads_as_the_hand_written_one` |
| The written JSON is the committed one, byte for byte, the same every time, in `packages/`, where git keeps it | B `test_the_written_json_is_the_committed_one_byte_for_byte`, run on a fresh clone |
| The layout is `json.dumps(indent=2, ensure_ascii=False)`'s | B `test_the_layout_is_the_standard_librarys` |
| A number that would read back as another is refused | B `test_a_number_that_would_read_back_as_another_is_refused` |
| `run_case` runs a builder case's written JSON; the quickstart's tests run the Python definition | Q every test passing `refund`, among them `test_small_refund_needs_no_team_lead`, `test_large_refund_waits_for_a_team_lead`, `test_an_undeclared_outcome_is_refused` |
| The quickstart's Python, word for word, is the file its tests run | Q `test_the_quickstarts_python_file_is_the_one_its_tests_run` |
| Importing `ventoux` brings no Temporal | L `test_importing_ventoux_brings_no_temporal` |
| The engine's processes never load the builder | L `test_the_engines_processes_never_load_the_builder` |

## 14b. The rest of the format

Status: choices drafted 2026-10-25, from `main` at `b6a8aa5` (14a merged as #56). The warm-up
answered and recorded; choices 17 to 28 answered "all as recommended", the same day. The dated line
on D58 written before building.

### Warm-up: learning question 28, the card: catalog, contract, binding

> Three words, three questions. Without looking: what question does each answer, give an example,
> and say what happens when it changes.

Open, a card kept in the rotation; last asked at 12e's warm-up, where the binding came back and
the catalog was "steps and contracts" for the fourth time. It is 14b's question: a workflow step
and a plan step name a contract or a plan, and the builder must write that reference without
knowing the catalog. What the reference promises is the catalog's, checked by `ventoux check`
(14c), never by the builder. Answer from memory first.

Answered 2026-10-25: "catalog contains contracts and policies and binding." Contracts came back
for the catalog; policies are inside a contract, and a binding is per environment, never in the
catalog. The contract and the binding, the examples and the "changes when…" column didn't come
back. Discussed and recorded; the card stays open.

### What this part is for

14a wrote the quickstart's refund. 14b writes everything else a case or a plan can say, one entry
per call, with the names the JSON uses: milestones, events and wait steps, workflow and plan
steps, rules and the two patterns, approvals by several people, close reasons, what a field
hides or narrows, how old a fact may be, forgetting, and plans with their states. A package, a
case and the plans it runs, is written in Python and committed as JSON, byte for byte.

A small example: a claim with a rule and a timer, and a plan step:

```python
paid = claim.milestone("paid", title="Claim paid")
assess = claim.task("assess", title="Assess the claim", roles=["adjuster"], outcomes={...})
claim.sla(
    "assess_late",
    title="Escalate an assessment late by 5 days",
    step=assess,
    within="5d",
    then=Then(start=[escalate]),
)
settle = claim.plan_step("settle", plan=settle_claim, inputs={"amount": payout}, reaches=[paid])
```

`settle_claim` is a `Plan` built in the same file. The package written is `case.json` and
`plans/settle-claim@1.json`.

### What the code does today

- `case/definition.py`: the case's models (`CaseDefinition` and around 30 shapes). Steps come in
  five kinds, rules in three (a raw rule, `sla`, `reminder`), moments in six.
- `core/plan.py`: `Plan` and its four kinds of state. A transition is a target and an optional
  `when`; a bare target is shorthand for one transition with no `when`.
- `core/expressions/model.py`: D20's operators as models (`Var`, the comparisons, `and`, `or`, `!`,
  arithmetic, `if`, `in`, `cat`, `string`, `exists`, `item`, `count`, `sum`) and the field types.
- `tooling/builder/` (14a): `Expr` and `NumberExpr`, `Case` with fields, references, tasks,
  activities, an approval and `sequence`; `written`.
- The repository's example packages: `examples/packages/refund/` (a case and
  `plans/refund-order.json`) and 14a's `examples/quickstart/packages/refund/`. Every other example
  JSON (`examples/refund/`, `claim/`, `witnesses/`, `checks/`) is a single definition, read by
  stories and tests.

### Choices for 14b

17. **The coverage test, read from the format's own models** (the negative test):
    - It walks every model reachable from `CaseDefinition` and `Plan` through their annotations,
      expression nodes included, and lists each key as the JSON writes it: the field's alias
      (`rules`, `==`), or its name. It also lists each value of a field that picks a shape
      (`kind`, `type`, `final`, `forgetting`, the `"opened"` moment).
    - **Two places where a model keeps a key differently from the JSON,** each a line in the test,
      which fails if it names a field no model has: a field's `declared` is written flat (`type`
      and what goes with it), and a plan's `sources` is written on each field as `source`.
    - **Covered** means: some JSON the builder writes in the repository (the example packages and
      the guide's examples, below), parsed with `parse_case` or `parse_plan`, has the key *given*,
      not defaulted (Pydantic's `model_fields_set`), and has every shape-picking value.
    - So a key added to the format later fails the test, naming the key and its model, until the
      builder writes it and an example uses it.

    *Recommended.* Set aside: a list of keys written in the test, which would pass a key added to
    the format later.

18. **Every D20 operator is written from Python,** since operators are keys of the format too
    (`{"count": …}`):
    - **Functions named after the JSON's operator,** with a trailing `_` where Python has the name
      already, as 14a's `and_` does: `if_(c, a, b)`, `in_(x, [1, 2])`, `cat(a, b)`, `string(x)`,
      `exists(field)`, `count(lines, where=…)`, `sum_(lines, value=…, where=…)`.
    - **`item`:** a list field is declared `Field.list(amount=Field.number(), sku=Field.string())`,
      and read with `lines.number("amount")` or `lines.text("sku")`. These are typed accessors, and
      each is refused if the list doesn't declare that field with that type, since that would write
      a different definition. Whether an `item` is used outside `count` or `sum` is the engine's
      to refuse (choice 25).

    *Recommended.*

19. **The other kinds of `Expr`, and `==` typed by `T`** (deferred from 14a):
    - `TextExpr` (`string`), `BoolExpr` (`boolean`, and what comparisons give), `OutcomeExpr` (a
      step's outcome), `ReferenceExpr` (a reference) and `ListExpr` (a list), beside 14a's
      `NumberExpr`.
    - `==` and `!=` take the same kind or its Python literal: a number with `int` or `Decimal`, a
      text or an outcome with `str`, a truth value with `bool`, a reference with a reference. So
      `review.outcome == 5` and `amount == "x"` fail mypy. Each override carries `# type:
      ignore[override]`, since narrowing a parameter breaks Python's own typing of `__eq__`, with
      the comment saying why.
    - **Every condition is `Expr[bool]`:** a step's `when`, an approval's, a rule's, an sla's, a
      reminder's, and a plan transition's.

    *Recommended.*

20. **What the builder can't know is written as the developer says it:**
    - **A step's output:** `kyc.output("risk_score", Field.number())` writes
      `{"var": "kyc.risk_score"}`, typed as the developer declares it. The contract is the
      catalog's, so whether it gives `risk_score`, and as a number, is `ventoux check`'s (14c),
      never the builder's guess.
    - **An event's payload is declared in the case,** so the builder types it from that
      declaration: `cancelled.field("note")`.
    - **`max_age`:** keys are written as the JSON writes them, `{"lookup.status": "1d"}`. An `Expr`
      can't be a dict key, since its `==` builds an expression.

    *Recommended.*

21. **Moments, rules and the patterns:**
    - **Moments as values:** `OPENED`, `review.started`, `review.answered`, `paid.reached`,
      `cancelled.arrived`, and a timer, `after("2d", since=review.started)`.
    - **A rule:** `claim.rule(name, title=, on=, when=, then=Then(set={field: expr}, reach=[…],
      start=[…], stop=[…]))`. `Then` mirrors the JSON's `then`, so a reader of the diff finds the
      same shape. `set=` takes the field object as its key, `{approved: amount}`, written by name.
    - **The two patterns:** `claim.sla(name, title=, step=, within=, when=, then=)` and
      `claim.reminder(name, title=, task=, after=["2d", "4d"], start=, when=)` (brief, D46). There
      is no `since=` parameter: `since=first_start` isn't offered, so writing it fails the type
      check and the call (brief, D46).

    *Recommended.*

22. **`four_eyes`** (brief, D47): `four_eyes(roles=, reason=, when=)` gives `Approval(count=2, …)`,
    which writes `"count": 2`; `Approval(count=n)` is there too, one-to-one. A `bool` or a number
    under 1 is refused as a count, as D47 refuses it in the JSON. *Recommended.*

23. **Plans and packages:**
    - `Plan("refund-order", 1, title=)` with `.field(name, Field…, source=)` (a plan's fields have
      no `display`), and states made by `.activity`, `.wait`, `.approval` and `.final`.
      `.initial(state)` is called once, refused a second time, as `sequence` is.
    - A state's `on` maps outcomes to targets **by name**, as the JSON does:
      `on={"done": "approve_refund", "not_found": "failed"}`. Names, because a plan may loop back
      to a state made later, which an object can't name. A target with a condition is
      `Transition("pay", when=…)`, and a list of them is written as a list. A single target with no
      condition is written as the shorthand, as the guides write it.
    - A case's plan step takes the `Plan` itself, `claim.plan_step("settle", plan=settle_claim, …)`,
      and writes its reference, `"plan": "settle-claim@1"`. `package(case)` gives the package's
      files: `case.json`, and each plan its plan steps name under `plans/`. A plan written but
      named by no step is not written, as D50 refuses a plan nobody names.

    *Recommended.*

24. **Which examples are written in Python, and compared byte for byte:**
    - **Both packages the repository holds,** each with its plans: 14a's quickstart, and
      `examples/packages/refund/` (its case and `refund-order@1`), written from
      `examples/cases/refund.py`. Its `case.json` and `plans/refund-order.json` become the
      builder's layout once. Their digest doesn't change, and a test shows it. CI's summary then
      reads "the same behaviour and wording as the base".
    - **The single definitions** (`examples/refund/*.json`, `claim/`, `witnesses/`, `checks/`)
      stay hand-written JSON, for two reasons. First, they are the engine's fixtures: stories name
      them by path, and several are written to be refused or warned about. Second, a definition
      may still be written as JSON (brief, D58), and these show it. Those the builder guide writes
      in Python are compared with them **as data and by digest**, not byte for byte: the four-eyes
      refund, the reminded refund and the claim.
    - **Coverage comes from both:** the packages and the guide's examples, together, must give
      every key (choice 17).

    *Recommended.* Set aside: rewriting all 30 example definitions in Python. That is two copies of
    every fixture, for no reader.

25. **It writes data and decides nothing.** The builder refuses only what keeps it from writing
    the JSON as given: a Python value where an expression is required, a number that wouldn't read
    back, two entries of one name, a second `sequence` or `initial`, a list accessor for a field
    the list doesn't declare. Everything the engine refuses is written as given and refused by
    `parse_case`, `parse_plan` and validation, so by `ventoux check`. Tests write such
    definitions through the builder and assert the refusal comes from the engine:
    - a plan transition whose condition reads an untrusted field (`UNTRUSTED_TRANSITION`) (brief, D49);
    - a sensitive field given to a workflow step (brief, D31) (brief, D36);
    - a transition to a state that doesn't exist (`UNKNOWN_TARGET`);
    - an `item` outside `count`.

    *Recommended.*

26. **The builder guide, `docs/guides/builder.md`,** for workflow developers, beside the cases guide:
    - One section per part of the format, in the cases guide's order: fields, steps, approvals,
      milestones and closing, events, rules and patterns, plans, packages.
    - Each example is word for word a file in `examples/builder/`, compared with the guide by a
      test, as 14a's quickstart is. That file is run by its test: the guide's text is never run
      itself.
    - Where a hand-written example exists, the guide says which, and its test compares the two.

    *Recommended.*

27. **`description` everywhere `display` has it,** and the approval's `reason`, as keywords on
    each call (`description=`). Wording is written as given (brief, D5). *Recommended.*

28. **Where it is recorded:** a dated line on D58 naming 14b's names (`if_`, `in_`, `sum_`,
    `output`, `Then`, `OPENED`, `after`, `four_eyes`, `plan_step`, `Transition`, `package`). No new
    decision: 14b builds what D58 decided for the whole format. *Recommended.*

### Slices, in order (14b)

Each starts with its negative test, seen failing for the right reason.

0. **The coverage test** (choice 17): it fails, listing every key 14a's builder doesn't write.
1. **The kinds of `Expr`, typed `==`, the operators, outputs** (choices 18 to 20): `review.outcome
   == 5` fails mypy.
2. **Milestones, step options, closing, field options, `description`** (choice 27): a step given
   where a milestone is required (`reaches=[pay]`) fails mypy.
3. **Events, wait steps, moments, rules, `sla`, `reminder`** (choices 21 and 22): `since=` doesn't
   type-check.
4. **Plans, plan and workflow steps, packages** (choice 23): `examples/packages/refund/` byte for
   byte.
5. **Decides nothing** (choice 25): the engine's refusals, through the builder.
6. **The guide and its examples** (choices 24 and 26), until the coverage test passes; the
   Promises.

### Decided while building (14b)

- **A key is counted on the model that declares it** (`Step requires`, not `ActivityStep
  requires`), found writing slice 0: counted per subclass, every kind of step would need an example
  of every common option. A second test reads each kind's model and checks its own call takes every
  key (`test_every_call_takes_every_key_of_its_kind`), a nested object taken flat (an sla's `sla`,
  a wait state's `wait`) by its own keys. Models are named with their module, since a case and a
  plan each have an `Approval`.
- **A mismatched `==` fails mypy where a condition is required, and raises when the file runs.**
  mypy reads `review.outcome == 5` as Python's own comparison: when `OutcomeExpr.__eq__` doesn't
  take an `int`, it tries the reflected `int.__eq__(object)`, which gives a `bool`. So
  `when=review.outcome == 5` fails the type check (a `bool` where an `Expr[bool]` is required), and
  the comparison alone raises at once when the file runs. Choice 19 holds where it matters, in a
  condition; a comparison standing alone type-checks as a `bool`.
- **A rule's `set` takes pairs, `Then(set=[(approved, amount)])`,** not the dict choice 21 wrote:
  an `Expr` can't be a dict key, since its `==` builds an expression (choice 20 says it for
  `max_age`).
- **An event's payload is read with typed accessors, `cancelled.text("note")`,** not
  `cancelled.field("note")` as choice 20 wrote: a name in a string can't carry a type to mypy. Each
  accessor is refused if the payload doesn't declare that field with that type, as a list's are.
- **A truth-value field is a condition itself:** `when=urgent`, never `urgent == True`.
- **`reference(...)` is `field(name, Field.reference(system), ...)`,** with every field option, and
  `Field.outcome(...)` and `Field.list(...)` were added for the format's other field types.
- **A count the engine refuses is written as given,** `Approval(count=True)`, and refused by
  `parse_case` (brief, D47). That is choice 25 over choice 22's wording: the builder decides
  nothing.
- **A package holds one file per plan name,** `plans/<plan>.json`, as the repository's package
  does. Two versions of one plan in one case are refused, naming both: two files of one name can't
  be written. A plan joins the package through a plan step only.
- **`examples/packages/refund/` was rewritten in the builder's layout.** Before rewriting, a test
  showed the built package was the hand-written one as data and by behaviour digest; it now holds
  the committed bytes to the builder's. CI's summary for this pull request says the same: the same
  behaviour and wording as the base.
- **The household example was refused six times by the engine while I wrote it,** each time
  rightly, and each fixed in the example, never in the builder: a high-risk payment reachable
  without an approval (`APPROVAL_REQUIRED`), a rule setting a field a person's form sets, a rule
  that can never act (`NEVER_FIRES`), a plan field set by its own wait given as an input
  (`UNKNOWN_INPUT`), a plan input left out (`MISSING_INPUT`), and a step that reaches `paid` steered
  by an undeclared output (`UNTRUSTED_TRIGGER`; `orders.lookup@2` declares it). That is choice 25
  seen working: the builder wrote each, the check refused each.
- **Every guide example passes validation against the development catalog with no error,** only
  warnings, and a test keeps it so: the guide never teaches what `ventoux check` would refuse.
- **mypy checks `examples/builder` and `examples/cases`,** as a team's builder files would be.
- **`requires=[]` writes no `requires`,** an empty list meaning none, as a default; `proposed_by=[]`
  writes `[]`, since an empty `proposed_by` is a choice the JSON can say.
- **Code ahead of its tests, again, said plainly:** the case builder and the plan builder were
  written whole after slice 1, so slices 2 to 4's tests passed on their first run. Each guard was
  broken once afterwards and its test seen failing: a value no example writes, a kind's call
  dropping a key, `closes_when` and `initial` twice, a payload's or a list's field read as another
  type, two versions of one plan, a transition's condition typed loosely or dropped, the guide
  drifting from its file, the committed package edited by hand.

### Promises (14b)

Each claim this part makes about behaviour, and the test that would fail if it weren't true. `C`
is `tests/test_builder_coverage.py`, `F` is `tests/test_builder_format.py`, `P` is
`tests/test_builder_packages.py`, `G` is `tests/test_builder_guide.py`, `N` is
`tests/test_builder_decides_nothing.py` (all new); `T` and `B` are 14a's. Checked against the tests,
2026-10-25: every test named here exists, every test in the new files and every test 14b added to
`T` and `B` is named here, and every guard was broken once to see its test fail.

| Promise | Test |
|---|---|
| Every key of the format, read from its own models, and every shape-picking value, is written by some builder file in the repository; a key added later fails until it is | C `test_the_builder_writes_every_key_of_the_format` |
| The keys a model holds otherwise than the JSON writes them are fields of their models | C `test_every_key_written_otherwise_is_a_field_of_its_model` |
| Each kind's call takes every key of its model | C `test_every_call_takes_every_key_of_its_kind` |
| `==` is typed by what the expression holds: a mismatch fails mypy where a condition is required | T `test_equality_is_typed_by_what_the_expression_holds` |
| A mismatched comparison raises when the file runs | B `test_a_mismatched_comparison_is_refused_when_the_file_runs` |
| Every D20 operator is a function writing its JSON; `item` through typed list accessors | B `test_every_operator_writes_its_json` |
| A list's field is read only as its list declares it | B `test_a_list_item_is_read_as_its_list_declares_it` |
| An output is written as the developer declares it | B `test_an_output_is_written_as_the_developer_declares_it` |
| A step where a milestone is required fails mypy | T `test_a_step_where_a_milestone_is_required_fails_the_type_check` |
| `since=first_start` is not offered | T `test_since_first_start_is_not_offered` |
| A timer is never set on a timer | T `test_a_timer_is_never_set_on_a_timer` |
| A transition's condition is a condition | T `test_a_transitions_condition_is_a_condition` |
| Milestones, step options, close reasons, `closes_when`, `stays_open`, `forgetting` and `description` are written as given | F `test_milestones_step_options_and_closing_are_written_as_given` |
| `closes_when` is said once | F `test_closes_when_is_said_once` |
| A field's `visible_to`, `sensitive`, `source` and an outcome type are written as given | F `test_a_fields_options_are_written_as_given` |
| Events, their senders and payloads, and wait steps are written as given | F `test_events_wait_steps_and_payloads` |
| A payload field is read only as its event declares it | F `test_a_payload_field_is_read_as_its_event_declares_it` |
| Rules, every moment and a timer are written as the JSON writes them | F `test_rules_moments_and_timers` |
| `sla` and `reminder` are written as patterns | F `test_sla_and_reminder_are_written_as_patterns` |
| `four_eyes` is an approval by two people | F `test_four_eyes_is_an_approval_by_two_people` |
| A plan, its fields, sources and states, and its transitions are written as its JSON | F `test_a_plan_is_written_as_its_json` |
| A plan's `initial` is said once | F `test_initial_is_said_once` |
| A package holds one file per plan name | F `test_a_package_holds_one_file_per_plan_name` |
| The refund package built in Python is the committed one, as data and by digest | P `test_the_refund_package_reads_as_the_committed_one` |
| Both packages the repository holds are the committed JSON, byte for byte, their plans included | P `test_every_package_is_the_committed_json_byte_for_byte` |
| The guide's rewrites read as their hand-written definitions, as data and by digest | G `test_an_example_reads_as_its_hand_written_definition` |
| Every guide example passes the check with no error | G `test_every_example_is_a_package_the_check_accepts` |
| The guide's examples are the files their tests run, word for word | G `test_the_guides_examples_are_the_files_their_tests_run` |
| A sensitive field given to a workflow step is written, and refused by the check | N `test_a_sensitive_field_given_to_a_workflow_step_is_written_and_refused_by_the_check` |
| A plan path chosen by untrusted data is written, and refused by the check | N `test_a_plan_path_chosen_by_untrusted_data_is_written_and_refused_by_the_check` |
| A transition to no state is written, and refused by the check | N `test_a_transition_to_no_state_is_written_and_refused_by_the_check` |
| An `item` outside `count` or `sum` is written, and refused when read | N `test_an_item_outside_count_or_sum_is_written_and_refused_when_read` |
| A count the engine refuses is written, and refused when read | N `test_a_count_the_engine_refuses_is_written_and_refused_when_read` |

### Not in 14b

- `ventoux check`, source lines, the deployment's catalog (14c); CI's regeneration check (14d);
  the schema (14e).
- Rewriting the single example definitions in Python (choice 24).

## 14c. `ventoux check` and the deployment's catalog

Status: choices drafted 2026-10-25, from `main` at `8a766d8` (14b merged as #57). The warm-up
answered and recorded; choices 29 to 39 answered "all as recommended", the same day. D59, its
dated lines and the quickstart's sections 3 and 6 written before building.

### Warm-up: learning question 33, why plans can be checked and code can't

> Why is this impossible to check on ordinary workflow code? ("This": what the validator proves
> before anything runs, such as "every path to `pay` passes an approval".)

Open since layer 3. Its follow-up (why `reach` ends on a cycle, and why slice 8's loop is unsafe)
came back in parts at 5, 10a and 11f. It is 14c's question: `ventoux check` *runs* Python, the
builder files, and then checks what they wrote, never the Python itself. Answer the main question
from memory first.

Answered 2026-10-25: "the code can loop, so no one can list all paths", after asking whether it
is impossible (in general, yes). Half of it: a plan loops too and is still checked, since its
moves are written down; code's paths depend on values computed as it runs. The other half, that a
plan declares its meaning (an approval, a risk) where code doesn't, didn't come back. Discussed
and recorded; the question stays open.

### What this part is for

14a and 14b write the JSON from Python, through a test or by hand. 14c is the command a developer
runs, as the quickstart's section 3 shows:

```sh
uv run ventoux check
```

```text
✓ refund is valid (3 steps): packages/refund/
```

It runs the builder files, checks each package as `ventoux release` would against the
deployment's catalog, says each problem at the line of Python that made it, and writes the package
folders only if every one passes:

```text
cases/refund.py:24: steps.pay.inputs.amount INPUT_POLICY: amount comes from customer_amount, …
✗ refund is refused: 1 error. Nothing was written.
```

### What the code does today

- `tooling/releases.py`: `issues_of(package, catalog)`, every issue of a package (each plan's,
  layer 3, then the case's, layer 10). `ventoux release` refuses on its errors (`checked`), and the
  CI summary uses the same list since #54.
- `tooling/builder/` (14a, 14b): `package(case)` gives a package's files by path; `written` writes
  them. No builder call records where it was made.
- `tooling/cli.py`: every command that reads contracts or roles imports `ventoux.testing.CATALOG`,
  the development catalog: `simulate`, `release`, `diff`, `map`, `notes`, `summary`, `promises`,
  `hashes`.
- `case/closing.py`: the D48 history line, `say_kept_from_starting`, said when a case closes. There
  is no warning for it before a case runs.

### Choices for 14c

29. **How `ventoux check` runs a builder file:**
    - In the same process, with `runpy.run_path` (the standard library), the project's root on
      `sys.path` for the run, so a builder file may import the team's own modules
      (`from cases.plans import settle`).
    - The files are named on the command line (`ventoux check cases/refund.py`), or, with none
      named, every `*.py` in `[tool.ventoux] cases` (default `cases`).
    - A builder file is the team's own code, reviewed in a pull request like any code. It is never
      a file named by a definition, a story or a package, and never model output (brief, D58).
      The command's help and the guide say so.
    - **A file that raises** is refused: exit 2, with the file and line inside it where it raised,
      the exception's type and message (`cases/refund.py:31: BuildTimeDecision: approved_amount >
      100 is decided by each case…`), and nothing written for any package.

    *Recommended.* Set aside: a subprocess per file. It isolates nothing the team doesn't already
    trust, and it would make the line mapping go through text.

30. **Which packages:** every `Case` at a file's top level, found by type, each one package with
    the plans its plan steps name (14b's `package`). Two cases of one name, in one file or two, are
    refused, naming both files: a package is known by its case's name (brief, D50). *Recommended.*

31. **Each problem at the line that made it** (the negative test):
    - Each builder call records where it was made: the first frame outside
      `ventoux.tooling.builder`, its file and line. A multi-line call gives its first line. The
      record is kept by the path the call wrote: `Case(...)` the case itself, `refund.activity("pay",
      …)` `steps.pay`, `plan.wait("confirm", …)` `plans.settle-claim@1.states.confirm`.
    - Each issue, as `issues_of` gives it (its path, code, severity and message), is printed at the
      line of the longest recorded path it starts with:
      `cases/refund.py:24: steps.pay.inputs.amount INPUT_POLICY: …`.
    - A path no call recorded gets the `Case(...)` line, never dropped.
    - A shape refused when the package is read (`parse_case`'s `CaseInvalid`, one line per path)
      is mapped the same way.

    *Recommended.*

32. **One check, `issues_of`:** the very list `ventoux release` refuses on and the CI summary
    reports, against the deployment's catalog, never a second set of rules. An error refuses the
    package; warnings are printed and let it through (brief, D34). *Recommended.*

33. **The package folders:**
    - Written by 14b's `package`, into `[tool.ventoux] packages` (default `packages`), each in
      `<packages>/<case>/`.
    - **Never `build/`** (14a's lesson, from the review of #56): most repositories' `.gitignore`
      hides it, and the JSON that runs would never reach review.
    - **All or nothing:** every file is run and every package checked first; only if every package
      passes is anything written. A refused package, or a file that raises, writes nothing at all.
    - **A folder holds exactly its package:** the package's `case.json` and `plans/*.json`; a
      `.json` file there the package no longer writes (a plan no step names now) is removed, since
      `ventoux release` refuses a package folder holding any other file (brief, D50). Folders of
      cases no builder file defines are left as they are, and said.

    *Recommended.*

34. **The deployment's catalog, named in configuration:**
    - `[tool.ventoux] catalog = "acme_platform.catalog:CATALOG"` in the project's
      `pyproject.toml`, found from the current folder upwards, read with `tomllib` (the standard
      library); or `--catalog acme_platform.catalog:CATALOG` on any command that takes it, which
      wins.
    - **Loaded as the platform team's code:** `importlib.import_module` on the name before the
      colon, with the project's root on `sys.path`; the attribute must be a `Catalog`, else
      refused. This name is written by the platform team in its own configuration, never read
      from a definition, a story or a package. CLAUDE.md forbids `importlib` on definitions, and a
      comment where it is called says why this isn't one.
    - **No catalog named is refused** (the other negative test): exit 2, saying both ways to name
      one. It is never read as the development catalog, which comes only when asked for by name:
      `ventoux.testing:CATALOG`. This repository's `pyproject.toml` names it, so its own commands
      and CI keep working; tests that run a command from a temporary folder name it with
      `--catalog`.

    *Recommended.*

35. **Which commands take it, each by the same configuration or `--catalog`:**
    - `check`, `release` and `summary`: they check packages (`issues_of`);
    - `diff`, `map` and `notes`: they read contracts and roles to judge and render;
    - `simulate`: contracts and roles, the story's fakes still the only implementations (choice
      38);
    - `promises` and `hashes`: the contracts the lockfile records are the deployment's.

    The environment commands read manifests and the registry, never the catalog, and don't
    change.

    **The CI summary's caveat (from #55):** the summary runs the head's own code, so its catalog
    is the head's, configuration included: a pull request can change the catalog's code, and its
    name. #55's hash check against the base's lockfile already catches a contract changed in place.
    The name is said too: the summary reads the base's `pyproject.toml` as text (`tomllib`,
    nothing imported) and, when the head names another catalog than the base, says so under
    "Contracts", in the summary's own words, failing nothing (a reviewer judges it, as with a
    looser change). *Recommended.*

36. **Exit codes, as `ventoux release`'s:** 0 when every package is valid (warnings printed), 1
    when one is refused, 2 when something can't be read or run: a file missing or raising, no
    catalog named, a catalog that isn't one, a configuration that isn't TOML. *Recommended.*

37. **The D48 warning, `KEPT_FROM_STARTING`** (choice 7c, carried): in case validation's warnings,
    so `check`, `release` and the summary all say it. A step that starts by itself (`automatic`),
    whose own `when` reads a value that may be untrusted, as validation's flow already works out
    sources: false keeps it from starting, and the case may close without it. Not said when the
    step reaches a `closes_when` milestone, since the case can't close without it then. The message
    names the step, the field and its source, never a value, and says how to guard a step that
    must happen. A warning refuses nothing (brief, D48). Set aside, for now: a rule's untrusted
    condition that starts a step. A rule's start is a proposal admission decides (brief, D39), and
    saying it needs the same analysis on rules; it can follow if you want it. *Recommended.*

38. **`ventoux simulate` against a team's catalog** (choice 7b, carried): it takes the catalog like
    the others; the story's fakes stay the only implementations that run, so nothing real is
    reached (brief, D45). A test simulates against a catalog of its own, and a contract the
    development catalog doesn't hold. *Recommended.*

39. **The guides and the brief:**
    - The quickstart's section 3, written first: `ventoux check`'s output, `packages/refund/` and
      the catalog's line in `pyproject.toml`, with a dated line where it changes what it said
      (`build/refund.json`).
    - The builder guide gains "Checking a builder file", and the sentence #57's review asked for:
      a mismatched `==` is reported where it is used, as `incompatible type "bool"; expected
      "Expr[bool] | None"`.
    - The releases guide's and the cases guide's "until `ventoux check` brings the deployment's"
      sentences, and "the command arrives with the builder", updated.
    - **D59, "`ventoux check` and the deployment's catalog"**, a new decision; dated lines on D34
      (`ventoux check` built), D48 (the warning built), D50, D55 and D56 (the deployment's catalog
      in place of the development one).

    *Recommended.*

### Slices, in order (14c)

Each starts with its negative test, seen failing for the right reason.

0. **No catalog named is refused** (choices 34 and 36); a catalog by name, from the configuration
   or `--catalog`; one that isn't a `Catalog` refused.
1. **`ventoux check` runs the builder files** (choices 29 and 30): a file that raises is refused at
   its line, nothing written.
2. **Each problem at its line** (choices 31 and 32): `INPUT_POLICY` at `refund.activity("pay", …)`'s
   line, with the path and code `issues_of` gives.
3. **The package folders** (choice 33): all or nothing, exactly the package's files.
4. **Every command takes the catalog** (choice 35), and the summary says a catalog renamed.
5. **The D48 warning** (choice 37).
6. **`simulate` against a team's catalog, the guides, D59, the Promises** (choices 38 and 39).

### Not in 14c

- `ventoux check --unchanged` in CI, and where release records live (14d).
- The JSON Schema (14e).
- A rule's untrusted condition that starts a step, as a warning (choice 37, set aside).

## Not in layer 14

- Turning a JSON definition into builder code. A model's kept draft (D1) is written as builder
  code by a developer, in a reviewed pull request. A generator for it is a later decision.
- A Java builder (D1: "may follow").
- AI drafting and the step advisor, layer 15, which uses the schema from 14e.
