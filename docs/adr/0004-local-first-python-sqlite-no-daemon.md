# Local-first Python core on SQLite, without a daemon

The system runs local-first: one Experience Base per machine, shared by all of the user's Projects. The core is written in Python (3.13+, managed with `uv`) as a library plus a CLI, with no long-running daemon. Harness hooks call the CLI. The MCP pull server is the stdio process the harness spawns. Work is queued in the database: ending a Task starts a detached worker for the Analyst, and a scheduled timer (a systemd user timer or cron) runs the periodic Packager and retries failed work. Operational state lives in SQLite in WAL mode, with FTS5 behind a retrieval interface for free-text similarity. Traces are compressed files referenced from the database. Retention copies cited spans into the database and deletes the file. Data Packages are exported as Parquet for analysis outside the system. The database is the source of truth, and a read-only git mirror of Goals and Packages provides diffable history.

We chose Python because the expensive work in this research project is statistical (Holdout comparisons, baselines, agreement figures), and one language for the core, the adapters and the analysis keeps everything in one test suite. SQLite fits concurrent but light writers (a few Project Agents plus Experience Factory workers) without operating a server. Having no daemon means there is nothing to keep alive and a crash affects only one invocation.

## Considered Options

- **TypeScript**: native to Claude Code, but weaker for the statistical analysis, which would likely end up in Python anyway.
- **Rust**: fastest hooks, but no official agent SDK, and slow to iterate while the design still moves.
- **DuckDB as the operational store**: excellent for analytics, but its locking model fits concurrent hook and worker processes poorly. It remains the tool for analyzing exported Data Packages.
- **Postgres in Docker**: robust under concurrency, but a service to operate. It stays the migration path if the Organization ever becomes multi-user, which is why storage sits behind an interface.
- **A local daemon**: revisit only if measured hook latency becomes a problem.
- **Embedding-based similarity from the start**: deferred until the "experience used" Metric shows that retrieval quality is the bottleneck. Deterministic retrieval keeps early Holdout results easier to interpret.

## Consequences

- Tooling: `uv` for environments and dependencies, `pytest` for tests, `ruff` for linting and formatting, `pyright` for type checking.
- Project identity comes from an explicit project file in the repository (Project id and Sharing Policy) if present, otherwise from the git remote, otherwise from the repository path.
- The Claude Code Harness Adapter is distributed as a Claude Code plugin that calls the CLI. The core package contains nothing specific to Claude Code.
