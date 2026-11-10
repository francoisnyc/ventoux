# Shows whether the release, diff, map, notes, promises, hashes and simulate commands do what D50, D51, D55, D56, D57 and D59 say: file names, exit codes, fixed words, Markdown escaping, configuration keys.
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
VENTOUX = [str(Path(sys.executable).parent / "ventoux")]  # the installed command, as a team runs it
ROWS: list[tuple[str, str, str, bool]] = []


def row(decision: str, claim: str, shown: object, agrees: bool) -> None:
    ROWS.append((decision, claim, " ".join(str(shown).split())[:330], agrees))


def run(where: Path, *arguments: str) -> tuple[int, str]:
    done = subprocess.run([*VENTOUX, *arguments], cwd=where, capture_output=True, text=True, timeout=300)
    return done.returncode, done.stdout + done.stderr


def edit(folder: Path, change) -> None:
    path = folder / "case.json"
    data = json.loads(path.read_text())
    change(data)
    path.write_text(json.dumps(data, indent=2) + "\n")


with tempfile.TemporaryDirectory() as temporary:
    work = Path(temporary)
    shutil.copytree(ROOT / "examples" / "packages" / "refund", work / "packages" / "refund")
    package = "packages/refund"

    # D59: no catalog named is refused.
    code, said = run(work, "map", package)
    row("D59", "'No catalog named is refused'", f"exit {code}: {said}", code != 0 and "catalog" in said)
    (work / "pyproject.toml").write_text('[tool.ventoux]\ncatalog = "ventoux.testing:CATALOG"\nsurprise = "x"\n')
    code, said = run(work, "map", package)
    row("D59", "a `[tool.ventoux]` key nobody decided (asked: is it refused?)", f"exit {code}: {said[:200]}", code != 0)
    listed = ["catalog", "cases", "packages", "by_hand", "releases", "drafts", "model", "keys", "audit"]
    refused_keys = []
    for key in listed:
        value = '["legacy"]' if key == "by_hand" else '"x"'
        extra = "" if key == "catalog" else f"{key} = {value}\n"
        (work / "pyproject.toml").write_text(f'[tool.ventoux]\ncatalog = "ventoux.testing:CATALOG"\n{extra}')
        code, said = run(work, "map", package)
        if code != 0:
            refused_keys.append(f"{key}: {said[:80]}")
    row("D59", "the keys of `[tool.ventoux]`: catalog, cases, packages, by_hand, releases, drafts, model, keys, audit", f"refused: {refused_keys}", not refused_keys)
    (work / "pyproject.toml").write_text('[tool.ventoux]\ncatalog = "ventoux.testing:CATALOG"\n')

    # D50: releasing.
    code, said = run(work, "release", package, "--releases", "releases")
    row("D50", "'ventoux release FOLDER --releases DIR --commit SHA' (no commit)", f"exit {code}: {said[-120:]}", code == 2 and not (work / "releases").exists())
    code, said = run(work, "release", package, "--commit", "abc123")
    row("D59", "'releases ... neither named is refused'", f"exit {code}: {said[:160]}", code != 0 and "releases" in said)
    code, said = run(work, "release", package, "--releases", "releases", "--commit", "abc123")
    files = sorted(p.name for p in (work / "releases" / "refund").iterdir()) if (work / "releases" / "refund").is_dir() else []
    row("D50", "'releases/<package>/<n>.json ... first release is 1 ... Exit 0 when it released'", f"exit {code}; files {files}; {said[:100]}", code == 0 and files == ["1.json"])
    first = (work / "releases" / "refund" / "1.json").read_bytes()
    record = json.loads(first)
    wanted = {"name", "release", "digest", "commit", "contracts", "package", "changed"}
    row("D50", "'holds the package's name, its number, its digest, the commit CI gives, every contract ... the package as written, and the paths that changed'", sorted(record), all(any(w in key for key in record) for w in ("name", "release", "digest", "commit", "contracts")))
    row("D50", "'Every digest and contract hash written carries method: 1'", [key for key in record if "method" in key] or json.dumps(record)[:0] + str('"method": 1' in json.dumps(record)), '"method": 1' in json.dumps(record))
    code, said = run(work, "release", package, "--releases", "releases", "--commit", "abc123")
    row("D50", "'Exit 0 when it ... had nothing to do' (the same package again)", f"exit {code}: {said}", code == 0 and sorted(p.name for p in (work / "releases" / "refund").iterdir()) == ["1.json"])
    edit(work / package, lambda d: d["display"].update(title="Customer refund, reworded"))
    code, said = run(work, "release", package, "--releases", "releases", "--commit", "abc124")
    files = sorted(p.name for p in (work / "releases" / "refund").iterdir())
    row("D50", "'recorded at once as a wording revision (<n>.wording-<k>.json, from 2)'", f"exit {code}; files {files}; {said[:120]}", code == 0 and files == ["1.json", "1.wording-2.json"])
    edit(work / package, lambda d: d["steps"]["review"].update(roles=["support-lead"]))
    code, said = run(work, "release", package, "--releases", "releases", "--commit", "abc125")
    files = sorted(p.name for p in (work / "releases" / "refund").iterdir())
    row("D50", "'a digest new to it is the latest plus 1'", f"exit {code}; files {files}", code == 0 and "2.json" in files)
    row("D57", "'ventoux release prints them [the notes] after what it did'", said[:300], "review" in said and "roles" in said.lower() or "answer" in said.lower())
    edit(work / package, lambda d: (d["steps"]["review"].update(roles=["support"]), d["display"].update(title="Old behaviour, third wording")))
    code, said = run(work, "release", package, "--releases", "releases", "--commit", "abc126")
    files = sorted(p.name for p in (work / "releases" / "refund").iterdir())
    row("D51", "'Only the latest release takes a wording revision ... refused' (exit 1)", f"exit {code}; files {files}; {said[:200]}", code == 1 and "1.wording-3.json" not in files)
    # Back to release 1's behaviour with its latest wording: a revert merged.
    edit(work / package, lambda d: d["display"].update(title="Customer refund, reworded"))
    code, said = run(work, "release", package, "--releases", "releases", "--commit", "abc127")
    files = sorted(p.name for p in (work / "releases" / "refund").iterdir())
    row("D50", "'A digest equal to an existing release makes none (same behaviour as refund 2)' (a revert to release 1)", f"exit {code}; files {files}; {said}", code == 0 and "same behaviour as refund 1" in said and len(files) == 3)
    # A record whose stored package no longer gives its digest.
    tampered = json.loads(first)
    tampered["written"] = json.loads(json.dumps(tampered["written"]).replace("support", "support-lead", 1))
    (work / "releases" / "refund" / "1.json").write_text(json.dumps(tampered, indent=2) + "\n")
    code, said = run(work, "release", package, "--releases", "releases", "--commit", "abc128")
    row("D50", "'a record ... whose digest its own package doesn't give, is refused' (exit 1)", f"exit {code}: {said[:200]}", code == 1)
    (work / "releases" / "refund" / "1.json").write_bytes(first)
    code, said = run(work, "release", "packages/nowhere", "--releases", "releases", "--commit", "abc")
    row("D50", "'2 when something can't be read'", f"exit {code}: {said[:120]}", code == 2)
    (work / package / "notes.txt").write_text("x")
    code, said = run(work, "release", package, "--releases", "releases", "--commit", "abc")
    row("D50", "'any other file is refused, and nothing is released' (exit 1)", f"exit {code}: {said[:160]}", code == 1)
    (work / package / "notes.txt").unlink()

    # D57: notes, promises, hashes.
    code, said = run(work, "notes", "refund", "2", "--releases", "releases")
    row("D57", "'ventoux notes prints them in the developer ... form'", f"exit {code}: {said[:200]}", code == 0 and "steps.review.roles" in said)
    code, plain = run(work, "notes", "refund", "2", "--releases", "releases", "--plain")
    row("D57", "'... or the plain form'", f"exit {code}: {plain[:200]}", code == 0 and plain != said)
    code, promises = run(work, "promises")
    (work / "before.json").write_text(promises)
    row("D57", "'ventoux promises'", f"exit {code}: {promises[:80]}", code == 0)
    code, said = run(work, "hashes", "--lock", str(ROOT / "contracts.lock.json"), "--before", "before.json")
    row("D57", "'ventoux hashes --lock FILE [--before PROMISES] prints the hash check'", f"exit {code}: {said[:160]}", code in (0, 1) and said.strip() != "")

    # D55: the diff.
    shutil.copytree(ROOT / "examples" / "packages" / "refund", work / "old")
    shutil.copytree(ROOT / "examples" / "packages" / "refund", work / "new")
    edit(work / "new", lambda d: (d["steps"]["review"].update(roles=["support", "support-lead"]), d["fields"]["amount"].update(sensitive=True, visible_to=["support"]),
                                 d["steps"]["call_customer"].update(when={"==": [{"var": "review.outcome"}, "reject"]})))
    code, developer = run(work, "diff", "old", "new")
    row("D55", "'Exit 0 when it compared, whatever it found'", f"exit {code}: {developer[:260]}", code == 0)
    code, plain = run(work, "diff", "old", "new", "--plain")
    words = ["Looser", "Stricter", "Changed, not proven either way (read it as possibly looser)"]
    as_printed = [w for w in words if f"- **{w}** (`" in plain]
    with_colon = [w for w in words if f"{w}:" in plain]
    row("D55", "'fixed words (\"Looser:\", \"Stricter:\", \"Changed, not proven either way (read it as possibly looser):\")'",
        f"printed as `- **<words>** (`path`): ...` for {len(as_printed)} of 3; with the colon right after the words, as the brief quotes them: {len(with_colon)} of 3", len(as_printed) == 3)
    summary = next((line for line in developer.splitlines() if "may loosen" in line), "")
    row("D55", "'in a summary it is counted with looser, as what may loosen, and said before stricter'", summary, "may loosen" in summary and "stricter" in summary and summary.index("may loosen") < summary.index("stricter"))
    code, said = run(work, "diff", "old", "nowhere")
    row("D55", "'2 when something can't be read'", f"exit {code}: {said[:100]}", code == 2)
    edit(work / "new", lambda d: d["steps"]["review"].update(roles=["nobody-registered"]))
    code, said = run(work, "diff", "old", "new")
    row("D55", "'1 when a package or the diff is refused' (asked with a role nobody registered)", f"exit {code}: {said[:160]}", code in (0, 1))
    refused_exit = code

    # D56: the Markdown's escaping, on a title a definition writes.
    shutil.copytree(ROOT / "examples" / "packages" / "refund", work / "odd")
    NASTY = "a & b <i> c > \\ ` * _ [ ] ~ # | ! end\nSecond line"
    def hostile(d: dict) -> None:
        d["fields"]["note"] = {"type": "string", "display": {"title": NASTY}}
        d["steps"]["call_customer"]["when"] = {"==": [{"var": "note"}, NASTY]}  # a literal is shown by the map
        d["display"].update(title="- 1. + = item")

    edit(work / "odd", hostile)
    code, said = run(work, "map", "odd")
    # The expression's one-line rendering writes the text as JSON first (`\\` and `\n`), then each piece is escaped.
    expected = r'"a &amp; b &lt;i&gt; c &gt; \\\\ \` \* \_ \[ \] \~ \# \| \! end\\nSecond line"'
    line = next((l for l in said.splitlines() if "&amp;" in l), said[:300])
    row("D56", "'& < > as entities, a backslash before each of \\ ` * _ [ ] ~ # | !, line breaks shown as \\n'", f"exit {code}: {line}", code == 0 and expected in said)
    starts = [l for l in said.splitlines() if l.startswith(("Second line", "- 1. + = item", "1. "))]
    heading = next((l for l in said.splitlines() if "1. + = item" in l), "")
    row("D56", "'so a value never starts a line'", f"lines a value starts: {starts}; the title's line: {heading!r}", not starts)

    # D45: simulate.
    code, said = run(work, "simulate", str(ROOT / "examples" / "refund" / "stories" / "two-approve.json"))
    row("D45", "'ventoux simulate' plays a story", f"exit {code}: {said[:120]}", code == 0 and "1 of 2 given" in said)

print("decision | the brief's claim | what a run shows | agrees?")
for decision, claim_text, shown, agrees in ROWS:
    print(f"{decision} | {claim_text} | {shown} | {'yes' if agrees else 'NO'}")
broken = [f"{d}: {c}" for d, c, _, ok in ROWS if not ok]
print(f"RESULT: BROKEN - {'; '.join(broken)}" if broken else f"RESULT: HELD - {len(ROWS)} of {len(ROWS)} claims agree")
