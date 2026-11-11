# Ventoux documentation

Start with the [quickstart](QUICKSTART.md), whoever you are: a refund case in 15 minutes, and the
five ideas everything else builds on (a case, its case file, steps, approvals and rules). Then
follow the path for what you do.

Most of what the guides describe is built: layers 0 to 20 of the [curriculum](CURRICULUM.md).
Not yet: a published package; the quickstart's `ventoux init`, `ventoux dev` and `ventoux start`,
which are still design; and the inbox, which comes after v1.0.

## You write cases

For **workflow developers**: you describe a piece of work, its steps and its rules, in Python.

1. [Cases](guides/cases.md): steps, the case file, approvals, rules, events and time, testing,
   and running on Temporal. The long one: read its first sections, then the rest as you need them.
2. [The Python builder](guides/builder.md): each part of a definition as you write it.
3. [Expressions](guides/expressions.md): conditions and values, and what is refused.
4. [Case data](guides/case-data.md): what goes in a case file (facts and references), who sees
   what, sensitive fields, forgetting a person, and facts that go stale.
5. [Plans](guides/plans.md): several calls and waits as one step. An advanced concept: most cases
   need only tasks and activities.
6. [Releases](guides/releases.md): how a change becomes a release, and what happens to the cases
   already open.

## You run Ventoux for your team

For the **platform team**: you decide what cases may call, and you run them on your Temporal
server.

1. [Activities](guides/activities.md): contracts, input policies, where outputs come from,
   existing workflows as steps, systems and resolvers.
2. [Releases](guides/releases.md): publishing a package, activating it in an environment,
   rolling back.
3. [Cases, "Running a case on Temporal"](guides/cases.md#running-a-case-on-temporal): the
   workflow, the worker, and opening a case from your own code.
4. [Case data](guides/case-data.md): resolvers and the key provider behind sensitive fields.
5. [Running Ventoux in production](guides/deployment.md): what a deployment is made of, what it
   must lock down, and how `ventoux doctor` checks it.
6. [Audit](guides/audit.md): the case export, kept apart from Temporal's history, and the key
   service.

## You want to know why

The [brief](BRIEF.md) is what we are building and why, with every design decision. It is long:
read up to "Decisions" (about a hundred lines), and its [concepts](BRIEF.md#concepts), the
glossary. Decisions are numbered (D1, D2, …) and never rewritten, so the docs cite them by
number: look one up when a page points to it.

## You are building Ventoux, or learning from it

Ventoux is built layer by layer, as a teaching project.

- [Curriculum](CURRICULUM.md): the layers, in order, each with what to learn, what to build and
  its check-yourself questions.
- [Layer notes](layers/): the design note of each layer (`00-repository.md` to
  `20-deployment.md`), and of the fixes, spikes and checkpoints between them. Each ends with its
  promises and the tests that keep them.
- [Releasing Ventoux](guides/releasing-ventoux.md): the maintainer's procedure for releasing the
  `ventoux` package.
- [Learning log](LEARNING.md): the check-yourself questions, answered and discussed.
- [README draft](README-draft.md): what the project's README will grow into. Its roadmap is
  current; its examples still come from the TypeScript prototype.

## Elsewhere in the repository

- [`examples/`](../examples/): the definitions the docs and tests use, such as the quickstart's
  refund and the case data guide's claim.
- [`src/ventoux/schema/`](../src/ventoux/schema/): the definition format, as JSON Schema, shipped
  in the package (`ventoux schema` writes it out).
