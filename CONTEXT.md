# Experience Memory

Long-term, continuous memory for LLM-based agents, modelled on Basili's Experience Factory, the Quality Improvement Paradigm and Goal/Question/Metric. Agents doing work and the process that learns from that work are kept strictly apart.

## Language

### Organization

**Organization**:
All Projects that share one Experience Base. Experience flows across Projects at this level.

**Project**:
A bounded workstream with its own context and Goals, usually but not necessarily one repository. Each Project has a Sharing Policy.
_Avoid_: Repo (when meaning the workstream), session

**Sharing Policy**:
A Project's choice of whether it contributes experience to the Organization and whether it consumes experience from it. Anything crossing a Project boundary is scrubbed of secrets and identifiers.

**Task**:
One unit of agent work inside a Project, carried out by a single Project Agent, that runs through one QIP cycle. A Task may span several harness sessions and is usually bound to an external work item such as an issue. A Task may depend on earlier Tasks, its Predecessor Tasks.
_Avoid_: Session, job, request

**Predecessor Task**:
An earlier Task that a Task depends on. When a dependent Task starts, the Packager admits its Predecessor Tasks' Lessons Learned before the Advisor pushes.
_Avoid_: Parent task, previous session

**Project Agent**:
An agent carrying out a Task within a Project. Several Project Agents may run in parallel in the same Project, each on its own Task. Project Agents read the Experience Base but never write to it.
_Avoid_: Worker, executor, main agent

**Harness Adapter**:
The connection between one agent harness and the system. It must report Task boundaries, hand over Traces, inject the Advisor's push, expose pull, and collect Evidence Packs. It may add native rendering or just-in-time delivery. Only Harness Adapters render Packages into harness-specific forms.
_Avoid_: Plugin, integration, connector

**Experience Factory**:
The separate role that analyzes what agents did and turns it into reusable experience. It never performs project work itself.
_Avoid_: Memory manager, consolidator, reflector

**Advisor**:
The synchronous, read-only Experience Factory role at Task start. It characterizes the Task, selects Project Goals, chooses which Packages to push, and answers Project Agents' queries.
_Avoid_: Retriever, recommender

**Analyst**:
The Experience Factory role that examines one finished Task. It extracts Metrics by answering Questions over the Trace and Evidence Pack, assesses the Outcome, and proposes Lessons Learned.
_Avoid_: Reflector, reviewer

**Packager**:
The Experience Factory role that admits Lessons Learned to the Experience Base and works across many Tasks to generalize, validate and retire Packages. It is the only writer of the Experience Base. It runs periodically, and also on demand to admit a Predecessor Task's Lessons Learned.
_Avoid_: Consolidator, curator

**Experience Base**:
The store of packaged experience that agents read from. Only the Packager writes to it.
_Avoid_: Memory, knowledge base, vector store

**Package**:
A unit of validated, reusable experience in the Experience Base, typed by its content after Basili's package taxonomy (Product, Process, Relationship, Tool, Management, Data).
_Avoid_: Memory, note, entry

**Product Package**:
A reusable artefact such as a template, config or snippet, kept scrubbed with its provenance.

**Process Package**:
A structured procedure for doing something: when it applies, its steps, its known pitfalls and the Metrics it affects.
_Avoid_: Playbook, recipe (as terms; the Package may be rendered as a skill)

**Relationship Package**:
A baseline or simple relation over Metrics conditioned on Characterization attributes, computed from Data Packages rather than written.
_Avoid_: Model, prediction, estimate

**Tool Package**:
Knowledge about invoking a specific tool correctly, including its quirks and failure modes, scoped to the tool's identity and version.

**Management Package**:
Decision guidance about how to conduct work: when to plan, when to ask the human, how much effort to spend.

**Data Package**:
A validated dataset of per-Task Metric values with their Characterization and Goals. It is never given to Project Agents.

**Lesson Learned**:
The entry state of a Package: a lesson the Analyst proposed and the Packager admitted, but nobody has validated yet, with a tentative package type. It must be linked to at least one Goal, to its evidence and to the Characterization it came from. Only Project Agents in the Project it came from can see it.
_Avoid_: Insight, memory, note

**Candidate Package**:
A Package promoted from Lessons Learned because the same lesson recurred across Tasks and the Traces don't contradict it, but whose effect on Outcomes hasn't been measured yet.

**Validated Package**:
A Package whose effect on Outcomes has been measured as positive. Only Validated Packages cross Project boundaries. A human may fast-track or veto at any stage.

**Retired Package**:
A Package withdrawn because its effect turned neutral or negative, evidence contradicted it, it fell dormant, or it failed re-validation. Retired Packages are kept with the reason so disproven lessons are not learned again.
_Avoid_: Deleted, archived

**Superseded Package**:
A Retired Package replaced by a newer Package that covers the same experience.

**Applicability Scope**:
The constraints over Characterization attributes that say where a Package applies. It starts at the origin Project and is widened or narrowed as the Package succeeds or fails in other Projects.
_Avoid_: Tags, filter, context

**Package Index**:
The list of titles and one-line summaries of next-best matching Packages that the Advisor gives a Project Agent alongside the full Packages it pushes, so the agent can pull more on demand.

**Trace**:
The record of what a Project Agent did during a Task, captured by its harness and converted by the Harness Adapter into a harness-neutral form. Traces are kept only for a per-Project retention window. After it, only the extracted Metrics, the Evidence Pack and the spans cited by live Lessons Learned or Packages survive.
_Avoid_: Log, transcript, episode

**Evidence Pack**:
The structured record a Project Agent produces at the end of a Task. It lists the agent's claims with statuses and the evidence for each, plus its plan versus what it actually did, rejected alternatives, assumptions and risks. Its claims are assertions that the Analyst checks against the Trace.
_Avoid_: Self-report, summary, report

### Lifecycle

**Quality Improvement Paradigm (QIP)**:
The lifecycle every unit of agent work follows: Characterize, Set Goals, Choose Process, Execute, Analyze, Package. The steps may be lightweight but are never absent.
_Avoid_: Loop, pipeline

**Holdout**:
A Task for which the Advisor deliberately withholds some or all Packages, so Outcomes with and without experience can be compared. Holdouts power both package validation and the system's evaluation of itself.
_Avoid_: Control group, A/B test

**Characterization**:
The description of a Project or Task used to find similar past experience: a versioned set of discrete attributes plus a free-text description.
_Avoid_: Profile, metadata, tags

**Outcome**:
How well a Task went, judged per Goal from Trace signals, downstream signals and optional human judgment. An Outcome can be revised after the Task ends.
_Avoid_: Success, result, score

### Measurement

**Goal**:
A GQM measurement goal stating the purpose, issue, object and viewpoint for which experience is collected. Experience is organized by the Goals it serves.
_Avoid_: Objective, task goal (a Goal is about what to learn, not what to accomplish)

**Organization Goal**:
A standing Goal defined by a human that applies to every Project in the Organization.

**Project Goal**:
A Goal for one Project, proposed by the Experience Factory from the Project's Characterization and approved by a human. Tasks have no Goals of their own; they select from the Project Goals.

**Question**:
A GQM question that refines a Goal into something answerable from Traces and Evidence Packs.

**Metric**:
A GQM metric: a defined, versioned measurement that answers a Question. Changing a Metric's definition creates a new Metric.
_Avoid_: KPI, stat

**Objective Metric**:
A Metric computed deterministically from Traces or downstream signals.

**Judged Metric**:
A Metric assessed by an LLM against a rubric. The judge's identity (provider, model, effort) is part of the Metric's definition. Anything relying on a Judged Metric is flagged as such.
_Avoid_: Score, rating
