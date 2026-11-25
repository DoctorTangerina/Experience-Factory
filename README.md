# Experience Factory

Long-term, continuous memory for LLM-based agents, modelled on Victor Basili's **Experience Factory**, the **Quality Improvement Paradigm (QIP)** and **Goal/Question/Metric (GQM)**.

Most agent memory systems let the working agent write down whatever seems interesting. This project instead treats memory as *packaged experience*: collected for an explicit measurement goal, extracted and validated by a separate process, and kept only while it measurably helps.

## Core ideas

- **Separation of roles.** The agents doing project work (Project Agents) only read experience. A separate Experience Factory analyzes their work and is the only writer of the Experience Base (ADR-0001).
  - The **Advisor** pushes relevant experience at the start of each Task.
  - The **Analyst** extracts Metrics and lessons from each finished Task.
  - The **Packager** generalizes, validates and retires experience.
- **Goal-driven capture.** Experience is organized by GQM Goals, and nothing is learned unless it serves a Goal ("no Goal, no Lesson").
- **QIP lifecycle.** Every Task goes through Characterize → Set Goals → Choose Process → Execute → Analyze → Package.
- **Basili's package types, adapted to agents.** Product, Process, Relationship, Tool, Management and Data Packages (ADR-0003). Relationship Packages are computed from data, never written by an LLM.
- **Evidence over self-report.** Project Agents submit structured Evidence Packs whose claims are checked against the harness-captured Trace.
- **Measured validation.** Holdout Tasks deliberately withhold experience, so each Package's effect, and the system's overall effect, can be measured (ADR-0002).
- **Neutral by design.** The core works with any agent harness and any model provider. Claude Code is only the first Harness Adapter (ADR-0005).

## Status

Design complete, implementation not started.

- Domain glossary: [`CONTEXT.md`](CONTEXT.md)
- Architecture decisions: [`docs/adr/`](docs/adr/)
- Pending decisions: [`docs/pending-decisions.md`](docs/pending-decisions.md)
- Specs: issues #1–#7. Implementation tickets: #8–#43.

## Planned stack

Local-first Python library and CLI on SQLite, with no daemon, using `uv`, `pytest`, `ruff` and `pyright` (ADR-0004). Data Packages can be exported as Parquet for research analysis.
