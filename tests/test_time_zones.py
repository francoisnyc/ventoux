"""Workers may run in any time zone: the date tests give the same results in two of them.

The engine keeps time as seconds since the epoch, from the history, and a date compares the same on
every machine; nothing in it reads the machine's zone (brief, D66). So the date tests are run in
two processes, one in New York (UTC-5) and one on Kiritimati (UTC+14), the two calendars furthest
apart, and must pass and fail alike, test by test. See docs/layers/16-field-types.md (16a).
"""

import os
import subprocess
import sys
from pathlib import Path
from xml.etree import ElementTree

ROOT = Path(__file__).parent.parent
ZONES = ("America/New_York", "Pacific/Kiritimati")


def outcomes_in(zone: str, report: Path) -> dict[str, str]:
    """Each date test's outcome, `passed` or `failed`, run in a process whose zone is `zone`."""
    subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "tests/test_dates.py",
            "-q",
            "-p",
            "no:cacheprovider",
            f"--junitxml={report}",
        ],
        cwd=ROOT,
        env={**os.environ, "TZ": zone},
        capture_output=True,
        check=False,  # a failure is read from the report, test by test
    )
    found: dict[str, str] = {}
    for case in ElementTree.parse(report).getroot().iter("testcase"):
        failed = case.find("failure") is not None or case.find("error") is not None
        found[case.attrib["name"]] = "failed" if failed else "passed"
    return found


def test_the_date_tests_give_the_same_results_in_any_time_zone(tmp_path: Path) -> None:
    east, west = (outcomes_in(zone, tmp_path / f"{n}.xml") for n, zone in enumerate(ZONES))
    assert east, "no date test ran"  # never pass by comparing nothing
    differing = sorted(
        name for name in east.keys() | west.keys() if east.get(name) != west.get(name)
    )
    assert differing == [], f"these date tests depend on the machine's time zone: {differing}"
    assert set(east.values()) == {"passed"}
