# Project Agents never write to the Experience Base

Following Basili's Experience Factory, the agents that do project work (Project Agents) only read from the Experience Base and emit raw material: harness-captured Traces plus a few self-reported measurements. A separate Experience Factory analyzes that material asynchronously and is the only writer of packaged experience. We chose this over agents writing their own memories inline. Project Agents have the same weaknesses Basili saw in project teams: they are biased toward their current task, have no time budget for reflection, and can't validate their own conclusions. In agent memory systems this shows up as bloated, duplicated and unvalidated memories.

## Considered Options

- **Inline self-writing**: the Project Agent records lessons as it works. It is cheap and immediate, but nothing filters or validates what it writes. Rejected.
- **Hybrid (agent proposes, Experience Factory curates)**: rejected for now so the separation stays clean and testable. Self-reported measurements are still allowed as input, but they are never experience in themselves.

## Consequences

- Experience reaches the Experience Base only through the Packager. The Analyst proposes Lessons Learned, and the Packager admits them on its periodic run, or on demand when a dependent Task starts (the Packager admits that Task's Predecessor Tasks' Lessons Learned before the Advisor pushes). We chose this over letting the Analyst write Lessons Learned directly, or keeping them in a staging area outside the Experience Base, so that there is still exactly one writer. A lesson from one Task is still not available to an unrelated parallel Task until the next periodic run.
- Extraction becomes the Experience Factory's core job: it answers GQM Questions over Traces. The quality of Traces and Goals therefore bounds the quality of the memory.
