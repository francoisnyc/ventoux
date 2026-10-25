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

And a mistake only the bytes catch: someone edits `build/refund/case.json` by hand, or changes
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
    the quickstart shows. `tests/test_quickstart.py` imports `refund` from it, exactly as the
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

### Promises (14a)

Filled in while building, each claim named with the test that would fail without it, and checked
both ways before the pull request.

## Not in layer 14

- Turning a JSON definition into builder code. A model's kept draft (D1) is written as builder
  code by a developer, in a reviewed pull request. A generator for it is a later decision.
- A Java builder (D1: "may follow").
- AI drafting and the step advisor, layer 15, which uses the schema from 14e.
