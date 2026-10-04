"""The claim case's conditions, inputs and updates in the JSONata subset, CEL and structured JSON.

Run (from this folder): uv run --no-project --with jsonata-python==0.7.0 --with cel-python==0.5.0
--with cel-expr-python==0.1.3 --with pydantic==2.13.5 --with jsonschema==4.26.0 python expressions.py

Evidence for docs/layers/spike-dsl.md, not product code. Four engines:
- jsonata-python (the JSONata subset of D3; the subset check walks the library's internal AST),
- cel-python, imported as `celpy` (pure Python CEL, no type checker),
- cel-expr-python (Google's wrapper of the C++ CEL implementation, with its type checker),
- structured.py (structured JSON, written for this spike).
"""

import hashlib
import json
from typing import Any

import celpy
import jsonata
import jsonschema
import structured
from cel_expr_python import cel
from pydantic import ValidationError

# The claim case's expressions in the shape Ventoux intends (steps, task outcomes with forms, one
# when/if/then rule). Conditions read the case file by field name, like examples/refund/refund.json.
# The prototype's `result.signal.name = 'ASSESSED' ? result.signal.payload.amount : 0` is gone:
# with D9, the `approve` outcome of `assess` sets `payout` through its form.
EXAMPLES: list[dict[str, Any]] = [
    {
        "where": "pay: when",
        "jsonata": 'assess.outcome = "approve" and payout > 0',
        "cel": 'assess.outcome == "approve" && payout > 0.0',
        "structured": {
            "and": [
                {"=": [{"field": "assess.outcome"}, "approve"]},
                {">": [{"field": "payout"}, 0]},
            ]
        },
    },
    {
        "where": "pay: approval when",
        "jsonata": "payout > 1000",
        "cel": "payout > 1000.0",
        "structured": {">": [{"field": "payout"}, 1000]},
    },
    {
        "where": "deny: when",
        "jsonata": 'assess.outcome = "deny"',
        "cel": 'assess.outcome == "deny"',
        "structured": {"=": [{"field": "assess.outcome"}, "deny"]},
    },
    {
        "where": "rule documents_arrived: if",
        "jsonata": "event.count > 0",
        "cel": "event.count > 0",
        "structured": {">": [{"field": "event.count"}, 0]},
    },
    {
        "where": "pay: input amount",
        "jsonata": "payout",
        "cel": "payout",
        "structured": {"field": "payout"},
    },
    {
        "where": "deny: input subject",
        "jsonata": '"Claim " & claim_id & ": decision"',
        "cel": '"Claim " + claim_id + ": decision"',
        "structured": {"concat": ["Claim ", {"field": "claim_id"}, ": decision"]},
    },
    {
        "where": "intake: update estimated_damage",
        "jsonata": "result.facts.estimated_damage",
        "cel": "result.facts.estimated_damage",
        "structured": {"field": "result.facts.estimated_damage"},
    },
    {
        "where": "rule customer_wrote: update",
        "jsonata": "event.text",
        "cel": "event.text",
        "structured": {"field": "event.text"},
    },
    {
        "where": "learning question 7 (not in the case)",
        "jsonata": '$sum(items[risk = "high"].amount) > 10000',
        "cel": None,  # CEL's standard library has no sum; it would need a custom function
        "structured": {
            ">": [
                {
                    "sum": {
                        "over": {"field": "items"},
                        "where": {"=": [{"item": "risk"}, "high"]},
                        "value": {"item": "amount"},
                    }
                },
                10000,
            ]
        },
    },
]

CASE: dict[str, Any] = {
    "claim_id": "CLM-7",
    "policy_id": "POL-1",
    "estimated_damage": 2000.0,
    "payout": 1500.0,
    "assess": {"outcome": "approve"},
    "event": {"count": 2, "text": "Here are the photos"},
    "result": {"facts": {"incident_date": "2026-09-30", "estimated_damage": 2000.0}},
    "items": [
        {"risk": "high", "amount": 6000},
        {"risk": "low", "amount": 9000},
        {"risk": "high", "amount": 5000},
    ],
}

# Declared field types, as the case definition would give them.
FIELDS: dict[str, structured.Type] = {
    "claim_id": "string",
    "policy_id": "string",
    "estimated_damage": "number",
    "payout": "number",
    "assess.outcome": ("approve", "deny"),
    "event.count": "number",
    "event.text": "string",
    "result.facts.estimated_damage": "number",
}

T = cel.Type
CEL_ENV = cel.NewEnv(
    variables={
        "claim_id": T.STRING,
        "policy_id": T.STRING,
        "estimated_damage": T.DOUBLE,
        "payout": T.DOUBLE,
        "assess": T.Map(T.STRING, T.STRING),
        "event": T.Map(T.STRING, T.DYN),
        "result": T.DYN,
        "items": T.List(T.Map(T.STRING, T.DYN)),
    }
)


def outcome(run: Any) -> str:
    """Run one evaluation; show its value or the error, never hide either."""
    try:
        value = run()
    except Exception as error:  # noqa: BLE001 - the point is to see every failure mode
        return f"ERROR {type(error).__name__}: {str(error).splitlines()[0][:90]}"
    return "undefined (None)" if value is None else repr(value)


def run_jsonata(source: str, context: dict[str, Any]) -> Any:
    return jsonata.Jsonata(source).evaluate(context)


def run_celpy(source: str, context: dict[str, Any]) -> Any:
    env = celpy.Environment()
    program = env.program(env.compile(source))
    return program.evaluate({name: celpy.json_to_cel(value) for name, value in context.items()})


def run_cel_expr(source: str, context: dict[str, Any]) -> Any:
    result = CEL_ENV.compile(source).eval(data=context)
    if result.type() == T.ERROR:  # returned, not raised: `.value()` is then a non-empty string
        raise RuntimeError(f"error value returned (truthy if read with .value()): {result.value()}")
    return result.value()


# CEL can be narrowed by configuration: the standard macros (map, filter, …) excluded.
CEL_NO_MACROS = cel.NewEnv(
    config=cel.NewEnvConfigFromYaml(
        """
name: ventoux
stdlib:
  exclude_macros: [map, filter, all, exists, exists_one]
variables:
- name: items
  type: list
"""
    )
)


def run_structured(data: Any, context: dict[str, Any]) -> Any:
    return structured.evaluate(structured.parse(data), context)


def evaluate_all(example: dict[str, Any], context: dict[str, Any]) -> None:
    print(f"\n{example['where']}")
    print(
        f"  jsonata    {example['jsonata']!s:48} -> {outcome(lambda: run_jsonata(example['jsonata'], context))}"
    )
    if example["cel"] is None:
        print("  celpy      (no standard CEL form)")
        print("  cel-expr   (no standard CEL form)")
    else:
        print(
            f"  celpy      {example['cel']!s:48} -> {outcome(lambda: run_celpy(example['cel'], context))}"
        )
        print(
            f"  cel-expr   {example['cel']!s:48} -> {outcome(lambda: run_cel_expr(example['cel'], context))}"
        )
    rendered = structured.render(structured.parse(example["structured"]))
    print(
        f"  structured {rendered!s:48} -> {outcome(lambda: run_structured(example['structured'], context))}"
    )


# --- The JSONata subset check (D3), on jsonata-python's internal AST ----------------------------

D3_FUNCTIONS = {"exists", "count", "sum", "contains", "string", "number", "not"}
ALLOWED_NODES = {
    "binary",
    "path",
    "name",
    "string",
    "number",
    "value",
    "function",
    "condition",
    "filter",
    "unary",
}
ALLOWED_BINARY = {"=", "!=", "<", "<=", ">", ">=", "and", "or", "+", "-", "*", "/", "%", "&"}


def children(node: Any) -> list[Any]:
    found: list[Any] = []
    for key in ("lhs", "rhs", "expression", "condition", "then", "_else", "expr", "procedure"):
        child = getattr(node, key, None)
        if child is not None and hasattr(child, "type"):
            found.append(child)
    for key in ("steps", "arguments", "stages", "expressions"):
        for child in getattr(node, key, None) or []:
            if hasattr(child, "type"):
                found.append(child)
    return found


def jsonata_check(source: str, fields: set[str]) -> tuple[list[str], set[str]]:
    """Problems found, and the fields read. Relies on jsonata-python's undocumented AST."""
    problems: list[str] = []
    read: set[str] = set()

    def walk(node: Any, relative: bool) -> None:
        if node.type not in ALLOWED_NODES:
            problems.append(f"`{node.type}` is outside the subset")
            return
        if node.type == "binary" and node.value not in ALLOWED_BINARY:
            problems.append(f"operator `{node.value}` is outside the subset")
        if node.type == "function":
            name = node.procedure.value if node.procedure.type == "variable" else None
            if name not in D3_FUNCTIONS:
                problems.append(f"function `${name}` is not allowed")
            for argument in node.arguments:
                walk(argument, relative)
            return
        if node.type == "path":
            names = []
            for step in node.steps:
                if step.type != "name":
                    walk(step, relative)
                    break
                names.append(step.value)
                for stage in getattr(step, "stages", None) or []:
                    walk(stage.expr, True)  # inside a filter, names are the item's fields
                if getattr(step, "stages", None):
                    break
            if not relative:
                dotted = ".".join(names)
                read.add(dotted)
                if dotted not in fields and names[0] not in fields:
                    problems.append(f"`{dotted}` is not a declared field")
            return
        for child in children(node):
            walk(child, relative)

    walk(jsonata.Jsonata(source).ast, relative=False)
    return problems, read


# --- Fields read from CEL, through celpy's parse tree (cel-expr-python exposes no AST) ----------


def cel_reads(source: str) -> set[str]:
    """Dotted names read, from celpy's parse tree (a concrete grammar tree, not a small AST)."""
    tree = celpy.Environment().compile(source)

    def dotted(node: Any) -> list[str] | None:
        if node.data == "member_dot":
            base = dotted(node.children[0])
            return None if base is None else [*base, str(node.children[1])]
        if node.data == "member" and node.children[0].data == "member_dot":
            return dotted(node.children[0])
        idents = list(node.find_data("ident"))
        if (
            node.data in ("member", "primary")
            and len(idents) == 1
            and not list(node.find_data("member_dot"))
        ):
            return [str(idents[0].children[0])]
        return None

    read: set[str] = set()
    inner = {id(m.children[0].children[0]) for m in tree.find_data("member_dot")}
    for member in tree.find_data("member_dot"):
        if id(member) not in inner and (path := dotted(member)):
            read.add(".".join(path))
    for ident in tree.find_data("ident"):
        name = str(ident.children[0])
        if not any(r == name or r.startswith(name + ".") for r in read):
            read.add(name)
    return read


def main() -> None:
    print("# 1. The claim case, evaluated on a sample case file")
    for example in EXAMPLES:
        evaluate_all(example, CASE)

    print("\n# 2. `payout` has no value yet (fail closed?)")
    missing = {k: v for k, v in CASE.items() if k != "payout"}
    variants = [
        EXAMPLES[1],
        {
            "where": "approval when, as a conditional",
            "jsonata": 'payout > 1000 ? "approval needed" : "no approval"',
            "cel": 'payout > 1000.0 ? "approval needed" : "no approval"',
            "structured": {
                "if": [{">": [{"field": "payout"}, 1000]}, "approval needed", "no approval"]
            },
        },
        {
            "where": "approval when, with an `or`",
            "jsonata": "payout > 1000 or estimated_damage > 5000",
            "cel": "payout > 1000.0 || estimated_damage > 5000.0",
            "structured": {
                "or": [
                    {">": [{"field": "payout"}, 1000]},
                    {">": [{"field": "estimated_damage"}, 5000]},
                ]
            },
        },
        EXAMPLES[5]
        | {
            "jsonata": '"Pay " & $string(payout) & " on " & claim_id',
            "cel": '"Pay " + string(payout) + " on " + claim_id',
            "structured": {
                "concat": ["Pay ", {"string": {"field": "payout"}}, " on ", {"field": "claim_id"}]
            },
            "where": "an input built from the missing value",
        },
    ]
    for example in variants:
        evaluate_all(example, missing)

    print("\n# 3. Rejected before anything runs?")
    bad = [
        ("non-deterministic", "$now()", "now()", {"now": []}),
        (
            "higher-order",
            "$map(items, function($i) { $i.amount })",
            "items.map(i, i.amount)",
            {"map": [{"field": "items"}, {"item": "amount"}]},
        ),
        (
            "variable binding",
            "($limit := 1000; payout > $limit)",
            "cel.bind(limit, 1000.0, payout > limit)",
            {"let": ["limit", 1000]},
        ),
        (
            "misspelled outcome",
            'assess.outcome = "aprove"',
            'assess.outcome == "aprove"',
            {"=": [{"field": "assess.outcome"}, "aprove"]},
        ),
        (
            "text compared with a number",
            'payout > "1000"',
            'payout > "1000"',
            {">": [{"field": "payout"}, "1000"]},
        ),
        ("misspelled field", "payot > 1000", "payot > 1000.0", {">": [{"field": "payot"}, 1000]}),
        (
            "int literal on a number field",
            "payout > 1000",
            "payout > 1000",
            {">": [{"field": "payout"}, 1000]},
        ),
    ]
    for name, js, ce, st in bad:
        print(f"\n{name}")
        problems, _ = jsonata_check(js, set(FIELDS) | {"assess", "event", "result", "items"})
        print(
            f"  jsonata (our AST walk)    {js!s:42} -> {'REJECTED: ' + problems[0] if problems else 'accepted'}"
        )
        try:
            celpy.Environment().compile(ce)
            print(f"  celpy (parse only)        {ce!s:42} -> accepted")
        except Exception as error:  # noqa: BLE001
            print(
                f"  celpy (parse only)        {ce!s:42} -> REJECTED: {str(error).splitlines()[0][:70]}"
            )
        print(
            f"  cel-expr (type checker)   {ce!s:42} -> {outcome(lambda ce=ce: CEL_ENV.compile(ce) and 'accepted')}"
        )
        if name == "higher-order":
            print(
                f"  cel-expr, macros excluded {ce!s:42} -> {outcome(lambda ce=ce: CEL_NO_MACROS.compile(ce) and 'accepted')}"
            )
        try:
            structured.type_of(structured.parse(st), FIELDS)
            print(f"  structured (Pydantic+type){json.dumps(st)[:42]:42} -> accepted")
        except ValidationError as error:
            print(
                f"  structured (Pydantic+type){json.dumps(st)[:42]:42} -> REJECTED: {error.error_count()} union errors"
            )
        except structured.Rejected as error:
            print(f"  structured (Pydantic+type){json.dumps(st)[:42]:42} -> REJECTED: {error}")

    print("\n# 4. Which fields does it read? (provenance analysis, layer 4)")
    for example in EXAMPLES:
        _, js_reads = jsonata_check(example["jsonata"], set(FIELDS) | {"items"})
        cel_read = sorted(cel_reads(example["cel"])) if example["cel"] else "-"
        st_reads = sorted(structured.reads(structured.parse(example["structured"])))
        print(
            f"  {example['where']:38} jsonata {sorted(js_reads)}  celpy {cel_read}  structured {st_reads}"
        )
    print("  cel-expr-python: no public API for the syntax tree or the references it resolved")

    print("\n# 5. Exact diffs and the release digest (D5): the same condition, written three ways")
    for text in ("payout > 1000", "payout>1000", "(payout > 1000)"):
        digest = hashlib.sha256(text.encode()).hexdigest()[:12]
        print(f"  string {text!r:20} digest {digest}")
    for data in (
        {">": [{"field": "payout"}, 1000]},
        json.loads('{ ">" : [ {"field":"payout"}, 1000 ] }'),
    ):
        canonical = json.dumps(
            structured.parse(data).model_dump(by_alias=True), sort_keys=True, separators=(",", ":")
        )
        print(
            f"  structured {canonical:30} digest {hashlib.sha256(canonical.encode()).hexdigest()[:12]}"
        )

    print("\n# 6. A JSON Schema for model output (layer 15)")
    schema = structured.EXPR.json_schema()
    print("  jsonata / cel: the schema can only say {'type': 'string'}")
    print(
        f"  structured: {len(schema.get('$defs', {}))} definitions, {len(json.dumps(schema))} bytes, recursive via $ref"
    )
    validator = jsonschema.Draft202012Validator(schema)
    for data in (
        {">": [{"field": "payout"}, 1000]},
        {"now": []},
        {">": [{"field": "payout"}, 1000], "or": [1, 2]},
    ):
        verdict = "valid" if validator.is_valid(data) else "invalid"
        print(f"  {json.dumps(data):58} -> {verdict}")


if __name__ == "__main__":
    main()
