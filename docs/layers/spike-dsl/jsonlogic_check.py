"""JsonLogic implementations on the same cases (jsonlogic_cases.json). Run each from this folder:

uv run --no-project --with json-logic==0.6.3 python jsonlogic_check.py
uv run --no-project --with panzi-json-logic==1.0.1 python jsonlogic_check.py
uv run --no-project --with python-jsonlogic==0.2.0 python jsonlogic_check.py

The JavaScript reference: jsonlogic_check.js. Not product code: evidence for spike-dsl.md.
"""

import json
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any

CASES = json.loads((Path(__file__).parent / "jsonlogic_cases.json").read_text())


def pointer(rule: Any) -> Any:
    """python-jsonlogic reads `var` as a JSON Pointer (`/assess/outcome`), not a dotted path."""
    if isinstance(rule, dict):
        return {
            op: (
                "/" + args.replace(".", "/")
                if op == "var" and isinstance(args, str)
                else pointer(args)
            )
            for op, args in rule.items()
        }
    if isinstance(rule, list):
        return [pointer(item) for item in rule]
    return rule


def implementation() -> tuple[str, Any]:
    try:
        from jsonlogic import JSONLogicExpression
        from jsonlogic.evaluation import evaluate
        from jsonlogic.operators import operator_registry

        def run(rule: Any, data: Any) -> Any:
            tree = JSONLogicExpression.from_json(pointer(rule)).as_operator_tree(operator_registry)
            return evaluate(tree, data=data, data_schema=None)

        return f"python-jsonlogic {version('python-jsonlogic')}", run
    except ImportError:
        pass
    from json_logic import jsonLogic  # both json-logic and panzi-json-logic use this module name

    for name in ("panzi-json-logic", "json-logic"):
        try:
            return f"{name} {version(name)}", jsonLogic
        except PackageNotFoundError:
            pass
    raise SystemExit("no JsonLogic implementation installed")


def main() -> None:
    name, run = implementation()
    print(name)
    for case in CASES:
        try:
            result = json.dumps(run(case["rule"], case["data"]))
        except Exception as error:  # noqa: BLE001 - every failure mode is the point
            result = f"ERROR {type(error).__name__}: {str(error)[:60]}"
        print(f"  {case['name']:32} -> {result}")


if __name__ == "__main__":
    main()
