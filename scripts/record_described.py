"""Record what pydantic writes for every shape of a contract's field (the contract hash fix)
(brief, D83): the reference `described` is held to, made once under pydantic 2.13.5, the version
every hash recorded so far was made with; and every development contract's promise and hash,
made under it.

    uv run python scripts/record_described.py

Refuses to record under another version: the file says 2.13.5, and means it.
"""

import json
import sys
from collections.abc import Mapping
from pathlib import Path

import pydantic

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "tests"))

from described_shapes import SHAPES

from ventoux.core.contract_hash import contract_hash
from ventoux.core.promise import promise_of
from ventoux.testing import CATALOG

RECORDED_UNDER = "2.13.5"


def main() -> int:
    if pydantic.VERSION != RECORDED_UNDER:
        print(
            f"pydantic is {pydantic.VERSION}: the recording is {RECORDED_UNDER}'s", file=sys.stderr
        )
        return 1
    # Pydantic: `model_json_schema()` describes a model class as JSON Schema: here, and only here,
    # as the reference Ventoux's own description is compared with.
    recorded = {model.__name__: model.model_json_schema() for model in SHAPES}
    written(ROOT / "tests" / "described" / f"pydantic-{RECORDED_UNDER}.json", recorded)
    # Every development contract's promise and hash, as the locks and records hold them.
    promises = {
        contract.reference: {"promise": promise_of(contract), "hash": contract_hash(contract)}
        for contract in CATALOG.contracts()
    }
    written(ROOT / "tests" / "described" / "development-promises.json", promises)
    return 0


def written(out: Path, recorded: Mapping[str, object]) -> None:
    out.write_text(json.dumps(recorded, indent=2, sort_keys=True, ensure_ascii=False) + "\n")
    print(f"✓ {out.relative_to(ROOT)}: {len(recorded)} recorded")


if __name__ == "__main__":
    sys.exit(main())
