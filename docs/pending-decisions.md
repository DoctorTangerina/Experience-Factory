# Pending decisions

Questions that are open on purpose. They are implementation-level or later-phase choices, not domain decisions, and nothing in `CONTEXT.md` or `docs/adr/` assumes an answer to them.

How to maintain this file:
- **Deferring a question:** add a section that states the question, the options raised so far, and what it **Blocks**.
- **Deciding a question:** record the answer where it belongs (an ADR in `docs/adr/` if it qualifies, otherwise `CONTEXT.md`, the README or the relevant spec), then delete the section from this file. Only open questions are listed here.
- Resolve each question before the work it blocks starts.

## Human interface for approvals

How a human approves proposed Project Goals, Questions and Metrics, defines Organization Goals, and vetoes or fast-tracks Packages at any stage. It might be a CLI, issues in the tracker, a web page or files in the repo.

**Blocks:** Goal lifecycle, package validation fast-track and veto, conflict flags raised to a human.

## Offline replay benchmark

ADR-0002 keeps offline replay as a complement to Holdouts. Open questions: which past Tasks form the benchmark, how a Task is replayed (environment snapshot, frozen repository revision), and how replay Outcomes are compared with live ones.

**Blocks:** controlled experiments beyond Holdouts.

## Initial Characterization schema

The first version of the discrete Characterization attributes (candidates raised: domain, language/stack, task type, size, tools involved). The schema is versioned and extensible, so this is a starting point rather than a commitment.

**Blocks:** Advisor characterization, Applicability Scopes, Relationship Packages.

## Default Organization Goals

The standing Goals shipped by default (examples raised: "understand why Tasks fail", "reduce wasted tool calls"), with their Questions and Metrics.

**Blocks:** Analyst extraction on a fresh install; "no Goal, no Lesson" means nothing can be learned without at least one Goal.

## Numeric parameters

Values the design depends on but did not fix:
- Trace retention window (30 days proposed as a starting guess, to be calibrated from how long downstream signals take to arrive)
- Push budget per Task and the size of the slot for Lessons Learned
- Recurrence count N for promoting a Lesson Learned to a Candidate Package
- Number of Projects needed to promote a Package to Organization scope
- Expiry window for Lessons Learned that never recur
- Age T after which a Validated Package must be re-validated
- Default Holdout fraction
- Thresholds for "measured effect" counting as positive, neutral or negative

## Claude Code facts to verify

Before building the Claude Code Harness Adapter, confirm against current Claude Code documentation: the hook names (`SessionStart`, `PreToolUse`, `Stop`, `SessionEnd`), what input each hook receives (including the transcript path), the transcript format, how hooks inject context, and how plugins package hooks, MCP servers and skills.
