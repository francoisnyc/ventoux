"""Record what pydantic writes for every shape of a contract's field (the contract hash fix)
(brief, D83): the reference `described` is held to, made once under pydantic 2.13.5, the version
every hash recorded so far was made with.

    uv run python scripts/record_described.py

Refuses to record under another version: the file says 2.13.5, and means it.
"""

import json
import sys
from pathlib import Path

import pydantic

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "tests"))

from described_shapes import SHAPES  # noqa: E402

RECORDED_UNDER = "2.13.5"


def main() -> int:
    if pydantic.VERSION != RECORDED_UNDER:
        print(f"pydantic is {pydantic.VERSION}: the recording is {RECORDED_UNDER}'s", file=sys.stderr)
        return 1
    # Pydantic: `model_json_schema()` describes a model class as JSON Schema: here, and only here,
    # as the reference Ventoux's own description is compared with.
    recorded = {model.__name__: model.model_json_schema() for model in SHAPES}
    out = ROOT / "tests" / "described" / f"pydantic-{RECORDED_UNDER}.json"
    out.write_text(json.dumps(recorded, indent=2, sort_keys=True, ensure_ascii=False) + "\n")
    print(f"✓ {out.relative_to(ROOT)}: {len(recorded)} models")
    return 0


if __name__ == "__main__":
    sys.exit(main())
