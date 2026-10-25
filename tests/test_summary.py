"""The CI step's job summary, layer 13e (brief, D55, as amended in 13e).

On each pull request, for each package: what merging does (12a's digest, the merge commit
against its first parent), then the diff in the plain form; and the hash check with the base
commit's own promises. See docs/layers/13-diff.md (13e) and docs/guides/releases.md, "On each
pull request".
"""

import json
import shutil
from pathlib import Path
from typing import Any

import pytest
from pydantic import BaseModel
from test_catalog import catalog_of, lookup_contract
from test_diff import LOOSE, ROOT, calling, refund

from ventoux.case.markdown import code, text
from ventoux.case.releases import PackageRefused
from ventoux.core.catalog import Catalog
from ventoux.core.contract_hash import contract_hash, promise_hash
from ventoux.core.promise import promise_of
from ventoux.testing import CATALOG
from ventoux.tooling.cli import main
from ventoux.tooling.releases import checked, read_package
from ventoux.tooling.summary import Summary, for_summary_file, summarize

PACKAGES = "examples/packages"
EXAMPLE = ROOT / PACKAGES / "refund"


def tree(root: Path, *cases: dict[str, Any]) -> Path:
    """A checkout at `root` holding a package per case under `examples/packages`, each case alone
    (a case with no plan steps), named by its `case`."""
    folder = root / PACKAGES
    folder.mkdir(parents=True)
    for case in cases:
        (folder / case["case"]).mkdir()
        (folder / case["case"] / "case.json").write_text(json.dumps(case))
    return root


def with_example(root: Path) -> Path:
    """A checkout at `root` holding the releases guide's refund package, as it is."""
    shutil.copytree(EXAMPLE, root / PACKAGES / "refund")
    return root


def summarized(base: Path, head: Path, catalog: Catalog = CATALOG) -> Summary:
    """The summary of merging `head` onto `base`, every contract of `catalog` recorded and given
    as the base's promise: its contracts match."""
    recorded = {c.reference: contract_hash(c) for c in catalog.contracts()}
    before: dict[str, object] = {c.reference: promise_of(c) for c in catalog.contracts()}
    return summarize(base, head, [PACKAGES], catalog, recorded, before)


# --- Slice 1: what merging does, per package -----------------------------------------------------


def test_a_package_only_in_the_base_is_said_removed(tmp_path: Path) -> None:
    # Never left out: a package the head drops is said, as one it adds is (13e, choice 65).
    base = with_example(tmp_path / "base")
    head = tree(tmp_path / "head")
    found = summarized(base, head)
    assert found.outcomes == (
        (
            "- **refund**: removed: merging it releases nothing; its records and the cases open on "
            "them are untouched."
        ),
    )
    assert found.code == 0


def edited(root: Path, change: Any) -> Path:
    """The refund package in `root`, its case changed by `change`."""
    path = root / PACKAGES / "refund" / "case.json"
    case = json.loads(path.read_text())
    change(case)
    path.write_text(json.dumps(case, indent=2))
    return root


def retitled(case: dict[str, Any]) -> None:
    case["steps"]["settle"]["display"]["title"] = "Pay the refund"


def unrequired(case: dict[str, Any]) -> None:
    case["steps"]["settle"]["requires"] = []  # settle no longer waits for the review


def test_what_merging_does_to_each_package(tmp_path: Path) -> None:
    # 12a's digest and wording, the merge commit against its first parent (brief, D50).
    base = with_example(tmp_path / "base")
    same = with_example(tmp_path / "same")
    reworded = edited(with_example(tmp_path / "reworded"), retitled)
    released = edited(with_example(tmp_path / "released"), unrequired)
    said = {
        "same": summarized(base, same).outcomes,
        "reworded": summarized(base, reworded).outcomes,
        "released": summarized(base, released).outcomes,
        "first": summarized(tree(tmp_path / "empty"), same).outcomes,
    }
    assert said == {
        # Only what the two trees show: the summary reads no records (13e, choice 78).
        "same": ("- **refund**: the same behaviour and wording as the base.",),
        "reworded": (
            (
                "- **refund**: the same behaviour as the base, other wording: a wording revision, "
                "if the base's behaviour is the latest release's (`ventoux release` decides on "
                "merge, from the records)."
            ),
        ),
        "released": (
            (
                "- **refund**: a new release, unless an earlier release has this behaviour "
                "(`ventoux release` decides on merge, from the records)."
            ),
        ),
        "first": ("- **refund**: a new package: its first release.",),
    }


def test_packages_are_matched_by_name_not_by_folder(tmp_path: Path) -> None:
    # A record names a package by its case's `case` (brief, D50): a folder moved is the same one.
    base = with_example(tmp_path / "base")
    head = tmp_path / "head"
    shutil.copytree(EXAMPLE, head / PACKAGES / "refunds")
    assert summarized(base, head).outcomes == (
        "- **refund**: the same behaviour and wording as the base.",
    )


# --- Slice 2: the diff and the contracts ---------------------------------------------------------


def test_an_input_policy_loosened_reads_as_looser_in_the_summary(tmp_path: Path) -> None:
    # The curriculum's negative test, end to end: one character in the JSON, and a customer's
    # amount could reach the payment. The summary says so, in the diff's own words (13e, choice
    # 68).
    base = tree(tmp_path / "base", refund())
    head = tree(tmp_path / "head", calling("payments.refund@3"))
    found = summarized(base, head, LOOSE)
    assert found.code == 0  # a looser change is the reviewer's to judge, never a failure
    assert "- **refund**: a new release, unless an earlier release has this behaviour" in found.text
    assert (
        "- **Looser** (`steps.pay.activity`): payments.refund@2 -&gt; payments.refund@3: input "
        "amount: was only from a system or a person, never from untrusted data; now any value "
        "(no input policy)."
    ) in found.text


def test_a_contract_changed_in_place_says_what_changed_and_fails(tmp_path: Path) -> None:
    # The base commit's own promise, checked against the lockfile, says each path (brief, D57).
    base, head = with_example(tmp_path / "base"), with_example(tmp_path / "head")
    before: dict[str, Any] = {c.reference: promise_of(c) for c in CATALOG.contracts()}
    before["orders.lookup@1"]["timeouts"]["start_to_close"] = 5
    recorded = {c.reference: contract_hash(c) for c in CATALOG.contracts()}
    recorded["orders.lookup@1"] = promise_hash(before["orders.lookup@1"])
    found = summarize(base, head, [PACKAGES], CATALOG, recorded, before)
    assert found.code == 1
    assert found.text.endswith(
        "## Contracts\n\n```\norders.lookup@1 changed without a new version: register it as "
        "orders.lookup@3.\n  timeouts.start_to_close: 5 -> 10\n```\n"
    )


def test_contracts_that_match_are_said_to(tmp_path: Path) -> None:
    found = summarized(with_example(tmp_path / "base"), with_example(tmp_path / "head"))
    assert found.text == (
        "# What merging changes\n\n## Packages\n\n- **refund**: the same behaviour and wording as "
        "the base.\n\n"
        "## Contracts\n\nEvery contract matches `contracts.lock.json`.\n"
    )


# --- Slice 3: fail closed, never hidden ----------------------------------------------------------


def test_a_package_that_cant_be_read_fails_the_step_and_is_never_read_as_removed(
    tmp_path: Path,
) -> None:
    # Fail closed: the head's refund can't be read, so the base's refund is never said removed,
    # and the step fails saying why (13e, choice 67).
    base = with_example(tmp_path / "base")
    head = with_example(tmp_path / "head")
    (head / PACKAGES / "refund" / "case.json").write_text("{")
    found = summarized(base, head)
    assert found.code == 1
    assert found.outcomes == (
        "- **refund**: not compared: a package in the head can't be read (below).",
    )
    assert found.text.endswith(
        "## Why the step fails\n\n- examples/packages/refund, in the head: case.json isn't JSON: "
        "Expecting property name enclosed in double quotes: line 1 column 2 (char 1)\n"
    )


def test_a_diff_the_catalog_cant_make_fails_the_step(tmp_path: Path) -> None:
    # The base calls what the catalog no longer holds, so the head passes `ventoux release`'s
    # check and only the diff refuses.
    base = tree(tmp_path / "base", calling("payments.refund@9"))
    head = tree(tmp_path / "head", refund())
    found = summarized(base, head)
    assert found.code == 1
    assert found.failures == (
        (
            "refund: the diff can't be made: payments.refund@9 is not in the catalog. Registered: "
            "payments.refund@2. Use a registered version, or register this one first. The diff "
            "compares contracts from the catalog."
        ),
    )


def test_a_base_that_isnt_a_folder_cant_be_read(tmp_path: Path) -> None:
    found = summarized(tmp_path / "nowhere", with_example(tmp_path / "head"))
    assert (found.code, found.outcomes) == (2, ())
    nowhere = text(str(tmp_path / "nowhere"))  # a folder's name, shown as written
    assert found.text.endswith(
        f"## Why the step fails\n\n- the base can't be read: {nowhere} isn't a folder\n"
    )


def test_a_summary_past_the_limit_says_where_the_whole_text_is(tmp_path: Path) -> None:
    # Never cut silently: past GitHub's limit, one line per package, the contracts, and where the
    # whole text is (13e, choice 69).
    base = with_example(tmp_path / "base")
    head = edited(with_example(tmp_path / "head"), unrequired)
    found = summarized(base, head)
    assert for_summary_file(found, limit=len(found.text.encode())) == found.text
    short = for_summary_file(found, limit=200)
    assert short == (
        "# What merging changes\n\n## Packages\n\n" + found.outcomes[0] + "\n\n## Contracts\n\n"
        "Every contract matches `contracts.lock.json`.\n\n"
        f"The whole summary is {len(found.text.encode())} bytes, past the job summary's limit of "
        "200 bytes: it is in this step's log, under `ventoux summary`.\n"
    )


# --- Slice 4: the command the workflow calls -----------------------------------------------------

LOCK = ROOT / "contracts.lock.json"


def run_summary(
    tmp_path: Path, base: Path, head: Path, before: Path, *more: str
) -> tuple[int, list[str]]:
    """`ventoux summary` as the workflow calls it, the job summary file already holding an
    earlier step's line: its exit code, and the arguments it was given."""
    arguments = ["summary", "--base", str(base), "--head", str(head), "--packages", PACKAGES]
    arguments += ["--lock", str(LOCK), "--before", str(before)]
    arguments += ["--summary-file", str(tmp_path / "summary.md"), *more]
    (tmp_path / "summary.md").write_text("an earlier step's summary\n")
    return main(arguments), arguments


def test_base_promises_that_cant_be_read_fail_and_say_so(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # Fail closed: the base's `ventoux promises` gave nothing readable (exit 2), said in the log
    # and in the summary, never read as nothing changed.
    before = tmp_path / "base-promises.json"
    before.write_text("")
    base, head = with_example(tmp_path / "base"), with_example(tmp_path / "head")
    code, _ = run_summary(tmp_path, base, head, before)
    assert code == 2
    said = f"{before}: isn't JSON: Expecting value, at line 1"
    assert capsys.readouterr().err == f"{said}\n"
    assert (tmp_path / "summary.md").read_text() == (
        "an earlier step's summary\n# What merging changes\n\n## Why the step fails\n\n"
        f"- {text(said)}\n"
    )


def test_the_command_logs_the_whole_summary_and_appends_it(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # As the workflow runs it: the base's own promises, the development catalog, the commits
    # named by CI. The whole text to the log; appended to the job summary, never written over.
    assert main(["promises"]) == 0
    before = tmp_path / "base-promises.json"
    before.write_text(capsys.readouterr().out)
    base = with_example(tmp_path / "base")
    head = edited(with_example(tmp_path / "head"), unrequired)
    code, _ = run_summary(
        tmp_path, base, head, before, "--base-commit", "231a0e7", "--head-commit", "9004cbd"
    )
    logged = capsys.readouterr().out
    assert code == 0
    assert logged.startswith(
        "# What merging changes\n\nThe merge commit `9004cbd`, against its base `231a0e7`.\n\n"
        "## Packages\n\n- **refund**: a new release"
    )
    assert "- **Looser** (`steps.settle.requires`): review -&gt; nothing." in logged
    assert logged.endswith("## Contracts\n\nEvery contract matches `contracts.lock.json`.\n")
    assert (tmp_path / "summary.md").read_text() == f"an earlier step's summary\n{logged}"


def test_the_command_says_where_a_summary_too_long_is(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["promises"]) == 0
    before = tmp_path / "base-promises.json"
    before.write_text(capsys.readouterr().out)
    base = with_example(tmp_path / "base")
    head = edited(with_example(tmp_path / "head"), unrequired)
    code, _ = run_summary(tmp_path, base, head, before, "--limit", "300")
    logged = capsys.readouterr().out
    kept = (tmp_path / "summary.md").read_text()
    assert code == 0 and "**Looser**" in logged and "**Looser**" not in kept
    assert kept.endswith(
        f"The whole summary is {len(logged.encode())} bytes, past the job summary's limit of 300 "
        "bytes: it is in this step's log, under `ventoux summary`.\n"
    )


# --- Slice 4: the workflow -----------------------------------------------------------------------

WORKFLOW = ROOT / ".github" / "workflows" / "ci.yml"


def job(name: str) -> str:
    """The text of the workflow's job `name`, up to the next job."""
    text = WORKFLOW.read_text()
    start = text.index(f"\n  {name}:\n")
    following = [text.find(f"\n  {other}:\n", start + 1) for other in ("check", "changes")]
    end = min([index for index in following if index > start], default=len(text))
    return text[start:end]


def test_the_workflow_sends_nothing_and_reads_only(tmp_path: Path) -> None:
    # The job summary only, a token that reads and nothing more, and never pull_request_target,
    # which would run the head's code with the base's rights (13e, choice 70). Read as text: no
    # YAML parser is a dependency.
    text = WORKFLOW.read_text()
    assert "\npermissions:\n  contents: read\n" in text
    # What the workflow does, its comments left out: a comment may name what it never does.
    doing = [line for line in text.splitlines() if not line.strip().startswith("#")]
    assert not [line for line in doing if "pull_request_target" in line]
    assert not [line for line in doing if line.strip().endswith(": write")]
    for forbidden in ("gh ", "github-script", "pull-requests"):
        assert not [line for line in doing if forbidden in line], forbidden


def test_the_summary_runs_on_pull_requests_from_the_base_s_own_promises() -> None:
    changes = job("changes")
    assert "    if: github.event_name == 'pull_request'\n" in changes
    assert "fetch-depth: 2" in changes  # the merge commit and its first parent
    assert "git rev-parse HEAD^1" in changes
    assert "path: base" in changes
    assert changes.count("persist-credentials: false") == 2
    assert "uv run --directory base --locked ventoux promises > base-promises.json" in changes
    assert "uv run ventoux summary" in changes
    assert '--summary-file "$GITHUB_STEP_SUMMARY"' in changes
    # The base's commit reaches the shell through the environment, never written into its line.
    assert '--base-commit "$BASE_COMMIT"' in changes


def test_the_existing_checks_are_as_they_were() -> None:
    # A push to main runs these only, the cached CLI included (13e, choices 71 and 72).
    check = job("check")
    for line in (
        "TEMPORAL_CLI_DIR: /home/runner/.cache/temporal-cli",
        "key: temporal-cli-${{ hashFiles('uv.lock') }}",
        "- run: uv sync --locked",
        "- run: uv run ruff format --check",
        "- run: uv run ruff check",
        "- run: uv run mypy",
        "- run: uv run pytest",
    ):
        assert line in check, line
    assert "if:" not in check


GUIDE = ROOT / "docs" / "guides" / "releases.md"


def test_the_guides_summary_runs_as_written(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    # As the job runs it, from the repository's root: the head checked out at `.`, its base at
    # `base`, the base's promises beside them.
    monkeypatch.chdir(tmp_path)
    with_example(tmp_path / "base")
    edited(with_example(tmp_path), unrequired)
    shutil.copy(LOCK, tmp_path / "contracts.lock.json")
    assert main(["promises"]) == 0
    (tmp_path / "base-promises.json").write_text(capsys.readouterr().out)
    section = GUIDE.read_text().split("\n## On each pull request\n")[1]
    command, printed = section.split("```\n")[1].split("\n", 1)
    assert command.startswith("$ ventoux ")
    assert main(command.removeprefix("$ ventoux ").split()) == 0
    assert capsys.readouterr().out == printed


def test_two_packages_of_one_name_in_a_tree_are_refused(tmp_path: Path) -> None:
    # A record names a package by its case's `case` (brief, D50): which one merging releases
    # would be a guess.
    base = with_example(tmp_path / "base")
    head = with_example(tmp_path / "head")
    shutil.copytree(EXAMPLE, head / PACKAGES / "refund-copy")
    found = summarized(base, head)
    assert found.code == 1
    assert found.failures == (
        "examples/packages/refund-copy, in the head: another folder holds refund too",
    )


# --- From the tutor review of #52: what a pull request writes is shown, never rendered -----------

HIDING = "approve</li></ul><details><summary>checked: nothing loosens</summary>"


def hiding() -> dict[str, Any]:
    """The review's head: a task before pay whose condition hides what follows in a collapsed
    <details>, and pay moved to an @3 that takes any amount."""
    case = calling("payments.refund@3")
    case["steps"]["vet"] = {
        "kind": "task",
        "display": {"title": "Vet the refund"},
        "roles": ["support"],
        "when": {"==": [{"var": "review.outcome"}, HIDING]},
        "outcomes": {"done": {"display": {"title": "Done"}}},
    }
    case["steps"]["pay"]["requires"] = ["vet"]
    return case


def test_html_a_pull_request_writes_never_reaches_the_summary(tmp_path: Path) -> None:
    # The review's run: the literal is shown escaped, the Looser line stays visible, and nothing a
    # definition writes opens an HTML tag (brief, D56, as amended in 13e).
    base = tree(tmp_path / "base", refund())
    head = tree(tmp_path / "head", hiding())
    found = summarized(base, head, LOOSE)
    assert "<" not in found.text
    assert (
        "approve&lt;/li&gt;&lt;/ul&gt;&lt;details&gt;&lt;summary&gt;checked: nothing loosens"
        "&lt;/summary&gt;"
    ) in found.text
    assert "- **Looser** (`steps.pay.activity`): payments.refund@2 -&gt; payments.refund@3" in (
        found.text
    )


def test_markdown_a_definition_writes_is_shown_as_written(tmp_path: Path) -> None:
    # A backtick, a `*`, a `[` and a `#` in a literal: each escaped, so each reads as itself once
    # rendered, never as code, emphasis, a link or a heading; a line break shown, never kept.
    case = refund()
    case["steps"]["pay"]["when"] = {"==": [{"var": "review.outcome"}, "a`b *c* [d](e) #f\ng"]}
    found = summarized(tree(tmp_path / "base", refund()), tree(tmp_path / "head", case))
    assert 'review.outcome = "a\\`b \\*c\\* \\[d\\](e) \\#f\\\\ng"' in found.text


def test_a_backtick_in_a_contract_never_closes_the_hash_checks_block(tmp_path: Path) -> None:
    # The head's own code writes the catalog: a docstring holding three backticks stays inside
    # the block, fenced by more than any run in it.
    class Fenced(BaseModel):
        """Looks an order up.

        ```
        </details>
        ```
        """

        order_id: str

    earlier, later = lookup_contract(), lookup_contract(input=Fenced)
    recorded = {earlier.reference: contract_hash(earlier)}
    before: dict[str, object] = {earlier.reference: promise_of(earlier)}
    # No package: the test's catalog holds one contract, which no package could run on.
    base, head = tree(tmp_path / "base"), tree(tmp_path / "head")
    found = summarize(base, head, [PACKAGES], catalog_of(later), recorded, before)
    contracts = found.text.split("## Contracts\n\n")[1]
    assert contracts.startswith("````\norders.lookup@1 changed without a new version")
    assert contracts.endswith("\n````\n")
    assert contracts.count("````") == 2


def test_a_path_in_a_code_span_is_fenced_past_its_backticks() -> None:
    # Not every key that becomes a path is checked against a name's pattern: a code span is
    # fenced by one backtick more than its longest run, padded where it starts or ends with one.
    assert code("steps.pay") == "`steps.pay`"
    assert code("steps.a``b") == "```steps.a``b```"
    assert code("`steps") == "`` `steps ``"
    assert code("a\nb") == "`a b`"  # a line break shown as a space: a span is one line


# --- The summary validation fix: the head checked as `ventoux release` checks it -----------------


def unreleasable(case: dict[str, Any]) -> None:
    """Two errors `ventoux release` refuses: a condition reading an undeclared field, and a role
    nobody registered."""
    case["steps"]["settle"]["when"] = {"==": [{"var": "nosuch"}, "approve"]}
    case["steps"]["call_customer"]["roles"] = ["nobody-has-this"]


def test_a_package_release_would_refuse_fails_the_step(tmp_path: Path) -> None:
    # Found in layer 13's walk-through: said "a new release" and exit 0, while `ventoux release`
    # refuses it on merge. The same check, never a copy (fix-summary-validation, choices 2, 3).
    base = with_example(tmp_path / "base")
    head = edited(with_example(tmp_path / "head"), unreleasable)
    found = summarized(base, head)
    assert found.code == 1
    assert found.outcomes == (
        "- **refund**: can't be released as it is: `ventoux release` refuses it (below).",
    )
    assert found.failures == (
        (
            "refund, in the head: steps.settle.when: EXPRESSION_INVALID: ==[0]: nosuch is not a "
            "declared field"
        ),
        (
            "refund, in the head: steps.call_customer.roles: UNKNOWN_ROLE: nobody-has-this is a role "
            "nobody registered: the roles are adjuster, claims-sensitive, fraud, operations, "
            "platform, privacy, support, support-lead; use one of them, or ask the platform team to "
            "register it"
        ),
    )
    assert "### steps.settle" in found.text  # the diff is still shown


def unregistered_role(case: dict[str, Any]) -> None:
    """A role nobody registered, on a task: `ventoux release` refuses the package."""
    case["steps"]["call_customer"]["roles"] = ["nobody-has-this"]


def test_an_unchanged_package_release_would_refuse_fails_the_step(tmp_path: Path) -> None:
    # A pull request can break a package without touching it: its code changes the catalog, or
    # the checks. `ventoux release` checks before it compares, so it refuses it on merge
    # (fix-summary-validation, choice 1).
    base = edited(with_example(tmp_path / "base"), unregistered_role)
    head = edited(with_example(tmp_path / "head"), unregistered_role)
    found = summarized(base, head)
    assert found.code == 1
    assert found.outcomes == (
        "- **refund**: can't be released as it is: `ventoux release` refuses it (below).",
    )


def test_the_base_is_never_checked(tmp_path: Path) -> None:
    # The base isn't what merging releases, and its issues aren't this pull request's.
    base = edited(with_example(tmp_path / "base"), unreleasable)
    head = with_example(tmp_path / "head")
    found = summarized(base, head)
    assert found.code == 0
    assert found.failures == ()
    assert "EXPRESSION_INVALID" not in found.text


MAY_BE_UNSET = (
    "## refund: what `ventoux release` warns\n\n"
    "- steps.settle.when: MAY\\_BE\\_UNSET: settle reads review.outcome, and doesn't wait for "
    "review, which gives it: if settle runs first, it fails and needs attention: require review\n"
)


def test_a_changed_packages_warnings_are_shown_after_its_diff(tmp_path: Path) -> None:
    # The guide's own pull request: `settle` no longer waits for the review, so every new case
    # would start with settle#1 failed. `ventoux release` warns and releases; the reviewer reads
    # it before merge, and the step fails nothing (fix-summary-validation, choice 4).
    base = with_example(tmp_path / "base")
    head = edited(with_example(tmp_path / "head"), unrequired)
    found = summarized(base, head)
    assert found.code == 0
    assert found.text.split("## Contracts")[0].endswith(
        "- **Looser** (`steps.settle.requires`): review -&gt; nothing.\n\n" + MAY_BE_UNSET + "\n"
    )


def test_an_unchanged_packages_warnings_arent_shown(tmp_path: Path) -> None:
    # Not this pull request's: repeated on every one, they would teach people to skip them.
    base = edited(with_example(tmp_path / "base"), unrequired)
    head = edited(with_example(tmp_path / "head"), unrequired)
    found = summarized(base, head)
    assert found.code == 0
    assert "MAY\\_BE\\_UNSET" not in found.text


def test_an_issues_message_is_shown_as_written(tmp_path: Path) -> None:
    # A message quotes what the definition writes; here a condition's field name, since a role's
    # name is refused by its pattern before any check (fix-summary-validation, choice 6).
    def quoting(case: dict[str, Any]) -> None:
        case["steps"]["settle"]["when"] = {"==": [{"var": "no<such*"}, "approve"]}

    base = with_example(tmp_path / "base")
    head = edited(with_example(tmp_path / "head"), quoting)
    found = summarized(base, head)
    assert found.code == 1
    assert (
        "- refund, in the head: steps.settle.when: EXPRESSION\\_INVALID: ==\\[0\\]: no&lt;such\\* is "
        "not a declared field\n"
    ) in found.text


def test_past_the_limit_a_refused_package_and_its_errors_stay(tmp_path: Path) -> None:
    # The short form keeps each package's line and why the step fails; the warnings are in the
    # whole text, in the log (fix-summary-validation, choice 5).
    base = with_example(tmp_path / "base")
    head = edited(with_example(tmp_path / "head"), unreleasable)
    short = for_summary_file(summarized(base, head), limit=100)
    assert (
        "- **refund**: can't be released as it is: `ventoux release` refuses it (below)." in short
    )
    assert short.count("- refund, in the head: steps.") == 2
    assert "it is in this step's log" in short


def test_a_new_package_and_a_wording_revision_show_their_warnings_too(tmp_path: Path) -> None:
    # Merging changes them too: a first release, and a wording revision (choice 4).
    head = edited(with_example(tmp_path / "head"), unrequired)
    first = summarized(tree(tmp_path / "empty"), head)
    base = edited(with_example(tmp_path / "base"), unrequired)
    reworded = edited(edited(with_example(tmp_path / "reworded"), unrequired), retitled)
    revision = summarized(base, reworded)
    for found in (first, revision):
        assert found.code == 0
        assert MAY_BE_UNSET in found.text


def test_the_summary_refuses_exactly_what_release_refuses(tmp_path: Path) -> None:
    # The same check, never a copy (choice 2): each error as `ventoux release` says it.
    head = edited(with_example(tmp_path / "head"), unreleasable)
    with pytest.raises(PackageRefused) as refused:
        checked(read_package(head / PACKAGES / "refund"), CATALOG)
    found = summarized(with_example(tmp_path / "base"), head)
    assert found.failures == tuple(
        f"refund, in the head: {line}" for line in str(refused.value).splitlines()
    )
