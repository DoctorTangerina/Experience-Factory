# Characterization schema

Version 1 of the discrete attributes and free text that make up a Characterization (see `CONTEXT.md`). The Advisor uses it to find similar experience, Applicability Scopes constrain its attributes, and Relationship Packages and Holdout comparisons are stratified by it. The schema is deliberately small. Every attribute and every value multiplies the number of strata, and Task volume per Project is still unknown.

Why a Characterization is fixed at Task start, and why classifiers count as measurement instruments, is recorded in ADR-0006.

## Structure

- **Two levels.** Project attributes are kept on the Project. A Task's Characterization is a snapshot of its Project's attributes at Task start plus the Task's own attributes. Snapshots are never updated afterwards, so recorded values are never reinterpreted.
- **One schema for the Organization.** All Projects share it, so scopes and Characterizations can be compared across Projects. There are no Project-local attributes in v1. If they are added later, they may only appear in Project-scoped Applicability Scopes and are dropped on promotion to Organization scope.
- **Value shapes.** Every attribute is either a **single** value or a **set** of values, drawn from a closed vocabulary that the schema extends over time. There are no numeric or open-string attributes. Anything numeric would be bucketed into an enum.

## Attributes

| Level | Attribute | Shape | Source |
|---|---|---|---|
| Project | `languages` | set | derived |
| Project | `frameworks` | set | derived |
| Project | `kind` | single | declared, else classified |
| Task | `task_type` | single | supplied, else classified |
| Task | `area` | set | classified |
| Task | `harness` | single | supplied |
| Task | `agent_model` | single | supplied |

### `languages`

The programming languages in the Project, derived from manifests and file extensions in the working tree.

### `frameworks`

The application frameworks the Project uses, derived from dependency manifests (`pyproject.toml`, `package.json`, `pom.xml`, …) through a curated package→framework map that belongs to the schema. Only frameworks that shape how code is structured count, for example django, fastapi, flask, rails, spring, express, nestjs, react, vue, angular, svelte and next. Test runners and ORMs are tools the agent invokes, so experience about them is scoped by Tool Packages, not by Characterization. Dependencies that are not in the map are ignored. Adding a framework to the map is a minor version bump.

### `kind`

What the Project is: `library`, `service`, `application`, `cli`, `infrastructure`, `data-pipeline`, `docs`. Declared in the project file. If it is not declared, it is classified once at Project registration and redone only on explicit request.

### `task_type`

What kind of work the Task is: `bugfix`, `feature`, `refactor`, `test`, `docs`, `chore` (config, dependencies, build), `investigation` (no code change expected), `review`. A Task has exactly one type. A feature that includes tests is a `feature`.

It is supplied from the Task's work-item labels when possible:

- A built-in default map covers common conventions:

  | Label | `task_type` |
  |---|---|
  | `bug` | `bugfix` |
  | `enhancement`, `feature` | `feature` |
  | `refactor` | `refactor` |
  | `documentation`, `docs` | `docs` |
  | `test`, `tests` | `test` |
  | `chore`, `dependencies` | `chore` |

- The project file can add to or override the map (for example `type: defect` → `bugfix`).
- If the labels map to more than one type, or none of them is mapped, or there is no work item, the type is classified.

A supplied value always beats a classified one.

### `area`

Which layers of the Project the Task touches: `ui`, `api` (public interfaces, endpoints, CLI surface), `core-logic`, `persistence` (schemas, migrations, storage), `infrastructure` (deploy, cloud, containers), `build-ci` (build, CI, dependencies), `data-ml` (pipelines, training, notebooks). Classified. `kind` says what the Project is. `area` says where in it the Task works.

### `harness`

The harness identity declared by the Harness Adapter, without a version. The harness version is recorded on the Task as plain data and exported with Data Packages, but it is not an attribute, because harnesses release too often and scopes would fragment.

### `agent_model`

The exact id of the model the Project Agent starts the Task with, supplied by the Harness Adapter. A new model is a new value and a minor version bump. Fragmentation is handled by Applicability Scopes, which start narrow and widen with evidence. The models actually used during the Task, including subagents and model switches, are a Metric.

## Free text

Both levels have a free-text description in two forms:

- **Verbatim**, kept in its Project only and used for full-text similarity retrieval. For a Task, this is the start information (work-item title and body, or the first prompt), truncated. For a Project, it is the project file's description field, or else the README's first section.
- **Scrubbed summary**, written by the classify step. This is the form that travels with Packages across Project boundaries.

The Project summary is classified once at registration, like `kind`.

## Sources

Each attribute declares where its values come from. The order of preference is **derived** (deterministic, from the repository) over **supplied** (from the Harness Adapter or the work item) over **classified** (an LLM step). **Declared** values come from the project file and are used where the attribute definition says so. Every recorded value carries the source that produced it, so analysis can check whether, for example, label-supplied and classified `bugfix` Tasks behave alike.

**Refresh.** Derived Project attributes are recomputed from the working tree at every Task start. Reading them takes milliseconds and is deterministic. Declared attributes are read from the project file at Task start. Classified Project attributes are computed once at registration.

## The classify step

At Task start, a single structured call through the foundation-model boundary returns `task_type` (when not supplied), `area` and the scrubbed summary. Its model is set in Organization config like every other Experience Factory step (ADR-0005). The Claude Code integration's default is Haiku 5.5.

If the call fails or times out, those attributes become `unknown`, the summary is empty, the failure is recorded, and the Task proceeds with the attributes it has. The timeout is listed under Numeric parameters in `docs/pending-decisions.md`.

## Matching

An Applicability Scope is a conjunction of allowed values per attribute. A single-valued attribute matches when its value is allowed. A set matches by membership, so a scope `languages ∋ python` matches a Project with `{python, typescript}`.

- **`unknown`** means derivation or classification failed. It never satisfies a constraint.
- **An empty set** means the derivation or classification succeeded and found nothing in the vocabulary (no recognized framework, or a Task touching none of the listed layers). It is a different value from `unknown`, and it does not satisfy a membership constraint either.
- **An attribute the scope does not constrain** matches anything, including `unknown`. That is why adding an attribute never widens an existing scope.

**Narrower scopes in the runtime conflict rule.** Scope A is narrower than scope B when, for every attribute, A's allowed values are a subset of B's. If two conflicting Packages' scopes cross without either containing the other, the scope tie-breaker does not apply. The rule falls through to the higher measured effect, then the more recent validation, and the conflict is recorded as usual.

## Versioning

- **Minor bump:** adding an attribute or a value. Old records read a new attribute as `unknown` and stay comparable.
- **Major bump:** renaming, splitting, merging or removing an attribute or value. It requires an explicit mapping from old values to new, which the Packager applies to Applicability Scopes and Relationship Packages.
- **Classifier change:** the classifier's identity is part of the schema version (ADR-0006). On a change, history is re-classified from each Task's stored start information into additional records under the new version. The originals are kept, statistics use the current version, and the agreement between old and new labels is recorded.

Each Task's start information is kept permanently, outside the Trace retention window, so any Task can be re-characterized under a later schema.
