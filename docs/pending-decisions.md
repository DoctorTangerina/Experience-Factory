# Pending decisions

Questions that are open on purpose. They are implementation-level or later-phase choices, not domain decisions, and nothing in `CONTEXT.md` or `docs/adr/` assumes an answer to them.

How to maintain this file:
- **Deferring a question:** add a section that states the question, the options raised so far, and what it **Blocks**.
- **Deciding a question:** record the answer where it belongs (an ADR in `docs/adr/` if it qualifies, otherwise `CONTEXT.md`, the README or the relevant spec), then delete the section from this file. Only open questions are listed here.
- Resolve each question before the work it blocks starts.

## Human interface for approvals

How a human approves proposed Project Goals, Questions and Metrics, defines and retires Organization Goals, and vetoes or fast-tracks Packages at any stage. It might be a CLI, issues in the tracker, a web page or files in the repo. It also covers how the human finds what is waiting for them: the core does not yet list pending proposals (#10).

**Blocks:** Goal lifecycle, package validation fast-track and veto, conflict flags raised to a human.

## Recording a Task against a Goal not in force

Recording a Task's measurement context accepts any Goal, including one that is proposed, rejected or retired (#10). Open question: should recording refuse a Goal that is not in force, or is that left to the Advisor, which selects only from Project Goals in force? A Task that started before its Goal was retired may still need recording, which argues against refusing at record time.

**Blocks:** Advisor Goal selection (Advisor spec).

## Task boundary edge cases

Carried over from #12. The core refuses, rather than resolves, a session that names a work item and also declares it continues a Task bound to something else (`ConflictingContinuationError`). That is an interim answer that can be loosened. Still undecided:
- What happens when a second Project Agent tries to join a Task that already has one. Tasks have one Project Agent for now (CONTEXT.md, Task), but whether to reject the join or open a new Task was not agreed. The core does not track Project Agents per session yet.
- How a dependency is detected without an explicit declaration, for example from issue links such as "depends on #11". The core only records Predecessor Tasks a Harness Adapter declares.

**Blocks:** a scenario for concurrent joins; inferred Predecessor Tasks.

## Offline replay benchmark

ADR-0002 keeps offline replay as a complement to Holdouts. Open questions: which past Tasks form the benchmark, how a Task is replayed (environment snapshot, frozen repository revision), and how replay Outcomes are compared with live ones.

**Blocks:** controlled experiments beyond Holdouts.

## Excluding a value from a set-valued attribute

`docs/characterization-schema.md` matches set-valued attributes by membership: a scope allows a set of values and matches when any of the Project's or Task's values is allowed. Narrowing a scope to exclude a value (#4, #37: "its Applicability Scope excludes language `go`") is not defined under that rule. If exclusion only removes `go` from the allowed set, a Project with languages `{python, go}` still matches through `python` and keeps receiving the Package that failed in Go Projects. Options raised so far:
- Exclusion as removal from the allowed set (the polyglot Project still matches).
- Exclusion as a separate "none of" constraint: the scope fails if any of the values is excluded.
- Narrowing on the combination instead of the single value, e.g. scoping out Projects whose languages include both `python` and `go`.

**Blocks:** Applicability Scope narrowing (#37).

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
- Timeout for the classify step at Task start (see `docs/characterization-schema.md`)

## Claude Code facts to verify

Before building the Claude Code Harness Adapter, confirm against current Claude Code documentation: the hook names (`SessionStart`, `PreToolUse`, `Stop`, `SessionEnd`), what input each hook receives (including the transcript path), the transcript format, how hooks inject context, and how plugins package hooks, MCP servers and skills.
