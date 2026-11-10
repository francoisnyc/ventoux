# Shows each installed dependency's declared licence beside the project's own (MIT), runtime dependencies first.
"""Reads only the metadata of the packages `uv sync --locked` installed; prints no path and no person."""

import tomllib
from importlib import metadata
from pathlib import Path

project = tomllib.loads(Path("pyproject.toml").read_text())["project"]
runtime = {
    line.split(">")[0].split("=")[0].split("<")[0].split("[")[0].strip().lower()
    for line in project["dependencies"]
}
extras = {
    line.split(">")[0].split("=")[0].split("<")[0].strip().lower()
    for lines in project.get("optional-dependencies", {}).values()
    for line in lines
}
PERMISSIVE = (
    "mit",
    "bsd",
    "apache",
    "isc",
    "psf",
    "python software foundation",
    "mpl",
    "unlicense",
    "0bsd",
)


def licence(dist: metadata.Distribution) -> str:
    meta = dist.metadata
    said = meta.get("License-Expression") or ""
    if not said:
        said = "; ".join(
            c.split("::")[-1].strip()
            for c in meta.get_all("Classifier") or []
            if c.startswith("License")
        )
    if not said:
        said = (
            (meta.get("License") or "").strip().splitlines()[0][:60] if meta.get("License") else ""
        )
    return said or "NOT DECLARED"


print(f"project: {project['name']} {project['version']}, licence {project['license']}")
rows = []
for dist in metadata.distributions():
    name = dist.metadata["Name"].lower()
    kind = "runtime" if name in runtime else "extra" if name in extras else "transitive/dev"
    rows.append((kind, name, dist.version, licence(dist)))
doubts = 0
for kind, name, version, said in sorted(set(rows)):
    ok = any(word in said.lower() for word in PERMISSIVE)
    doubts += not ok
    print(f"{'ok ' if ok else '?? '} {kind:15} {name:28} {version:12} {said}")
print(
    f"RESULT: {'HELD' if not doubts else 'BROKEN'} - {len(set(rows))} distributions, {doubts} without a permissive licence declared"
)
