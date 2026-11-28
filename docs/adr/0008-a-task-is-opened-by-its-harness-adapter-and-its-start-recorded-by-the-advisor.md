# A Task is opened by its Harness Adapter; its start is recorded by the Advisor

A Task has one identity: the one the core gives it when a Harness Adapter reports the session that opens it. The Task's start record (its Characterization, selected Goals and Holdout assignment) is recorded against that identity as a separate, later step by the Advisor. Recording a start for a Task that was never opened is refused. We chose two steps because that is the real order of events. The session's Task has to be resolved before the Advisor's push can be requested, and characterizing the Task is the Advisor's job, not the harness's. Folding the start record into the boundary report would make every Harness Adapter carry the Advisor's output, against ADR-0005.

## Considered Options

- **One step: the Harness Adapter reports the boundary together with the start record**: a single call and no Task without a start record, but the harness-neutral adapter would have to characterize, select Goals and assign Holdouts. Rejected.
- **Caller-chosen Task ids for the start record, kept apart from Task boundaries**: what the core first had. Data Packages and Traces or Evidence Packs ended up describing different Tasks, with nothing linking them. Rejected.

## Consequences

- Only Data Package entries need a recorded start: a Metric value for a Task without one is refused. A Task can still be opened, ended and reopened, and keep its Trace and Evidence Pack, with no start record, for example when no Advisor pushed.
- A start can be recorded only while the Task is open for the first time, and only once. A start recorded after the Task ended could leak its Outcome into the condition (ADR-0006). A reopened Task keeps the start record it already has.
