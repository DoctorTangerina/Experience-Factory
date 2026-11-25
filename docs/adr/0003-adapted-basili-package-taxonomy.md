# Adapted Basili package taxonomy

The Experience Base types its Packages using Basili's six content categories, adapted to LLM agents, rather than collapsing them into fewer generic types such as procedure, model and note. Keeping all six preserves fidelity to the Experience Factory, which makes the adaptation itself a defensible research contribution. It also forces quantitative experience (Data and Relationship Packages) into the design, which existing agent-memory systems, mostly storing process- and product-like notes, lack. Every Package starts as a Lesson Learned, which must be linked to at least one Goal ("no Goal, no Lesson"). That rule is how GQM's role as a capture filter is enforced.

| Type | Agent adaptation | Derived how | Delivered how | First milestone |
|---|---|---|---|---|
| Product | Reusable artefacts (templates, configs, snippets), stored scrubbed with provenance | Recurrence in Trace diffs | Pull only | No |
| Process | Structured procedures: trigger/preconditions → steps → pitfalls → affected Metrics | Action sequences across similar Tasks | Pushed; rendered natively where the harness supports it (e.g. skills) | Yes, top priority |
| Relationship | Descriptive baselines and simple relations, conditioned on Characterization | Computed deterministically from Data Packages, never written by an LLM | Expectations block in the push | Yes |
| Tool | Invocation knowledge, quirks and failure modes, scoped by tool identity and version | Error → retry → success patterns in Traces | Just in time on first tool use | Yes |
| Management | Decision guidance for the Project Agent, and recommendations to the harness and human (never auto-applied) | Relationship Packages plus Outcomes | Pushed | No (needs mature Relationship Packages) |
| Data | Validated per-Task Metric datasets with Characterization and Goals | Analyst extraction | Never pushed; internal to the Experience Factory and exportable for research | Yes, as foundation |

## Considered Options

- **Collapsed taxonomy (Procedure / Model / Lesson)**: simpler, but it loses the distinction between computed and written experience and weakens the link to Basili. Rejected.

## Consequences

- Relationship Packages depend on Data Packages, and Management Packages depend on Relationship Packages, so the milestones follow that dependency order.
- A Lesson Learned's type is tentative. The Packager may retype it on promotion.
