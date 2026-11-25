# Characterization is prospective, and classifiers are instruments

A Task's Characterization is fixed at Task start and holds only what was knowable before Execute. The Analyst never revises it. Anything observed during the Task, such as actual size, tools used, files touched or the models that actually ran, is a Metric, not an attribute. We chose this because Relationship Packages condition Metrics on Characterization, and the Advisor uses them as expectations at Task start. An attribute set after the fact would leak the Outcome into the condition, and the Advisor could never know its value when it needs it. For the same reason a mislabelled Task is not corrected. If misclassification matters, it is measured as a Metric.

Some attributes (`task_type` when no work-item label supplies it, `area`, the scrubbed summary) are assigned by an LLM. We treat that classifier as a measurement instrument, like the judge of a Judged Metric. The classifier's identity is part of the schema version, so changing it is a schema version bump. A different model draws borderline lines differently, and pooling its labels with the old ones would make baselines shift for reasons that have nothing to do with how Tasks went.

## Considered Options

- **The Analyst revises attributes after the Task**: labels would be more accurate, but this leaks the Outcome into the condition and makes the Advisor's expectations unusable at Task start. Rejected.
- **Separate start-time and retrospective Characterizations**: keeps both, but two Characterizations invite conditioning on the wrong one, and the retrospective facts are already captured as Metrics. Rejected.
- **On a classifier change, keep versions separate**: clean, but every classifier change would discard all quantitative history. Rejected.
- **On a classifier change, pool and flag**: keeps the history, but the distortion stays in the numbers unmeasured. Rejected.

## Consequences

- Each Task's start information is kept permanently, outside the Trace retention window, so Tasks can be re-characterized.
- When the classifier changes, history is re-classified from the stored start information and stored as additional Characterization records under the new version. The original records are kept, because they are what the Advisor acted on and what Holdout assignment used. Statistics use the current version. The agreement between old and new labels is recorded as a by-product. Re-classification reads only start information, so it stays prospective.
- Every attribute value records whether it was derived, supplied, declared or classified, so analysis can check whether human-labelled and LLM-labelled Tasks behave alike.
- A Task that spans several sessions is characterized once, at its first session. `agent_model` is the model the Project Agent started with.
