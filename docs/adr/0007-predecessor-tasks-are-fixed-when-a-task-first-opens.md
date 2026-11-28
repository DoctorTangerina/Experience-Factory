# Predecessor Tasks are fixed when a Task first opens

A Task's Predecessor Tasks are the dependencies declared by the session that first opens it. No later session can add any: neither one that joins the open Task nor one that reopens it after it ended. Such a session is refused, not silently ignored. We chose this because Predecessor Tasks exist so the Packager can admit their Lessons Learned before the Advisor's first push. A dependency declared later would bring in experience after the Advisor has already acted on the Task. Its Outcome would then reflect experience it started without, and the start-time context that Relationship Packages condition on would quietly change. This is the same "only what was knowable at start" rule as ADR-0006.

## Considered Options

- **Allow joining sessions to add Predecessor Tasks**: catches dependencies discovered mid-Task, but the Advisor's push has already happened, so the new Predecessor's Lessons Learned would arrive too late to shape it. Rejected.
- **Allow a reopening session to add Predecessor Tasks**: reopening feels like a fresh start, but it is the same Task with the same Characterization and Holdout assignment. Letting its dependencies change would make it two Tasks under one id. Rejected.
- **Ignore dependencies declared by a joining or reopening session**: no refusal, but the Harness Adapter would believe a dependency was recorded when it was not. Rejected.

## Consequences

- A dependency found only after a Task has opened is not recorded on that Task. If it matters, the work belongs in a new Task that declares the dependency when it opens.
