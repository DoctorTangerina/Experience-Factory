# Harness- and model-provider-neutral core

The system is not built around Claude Code or any single model provider. The core and the Experience Factory are neutral about both:

- **Traces are normalized.** Each Harness Adapter converts its harness's transcript into the core's harness-neutral Trace schema (prompts, tool calls with arguments and results, errors, end state) before handing it over. The core never stores or parses a harness-native format.
- **The foundation-model boundary is our own interface**: given instructions, input and an output schema, it returns a validated object plus the model actually used and its token usage. There is one adapter per provider, starting with Anthropic on its official SDK. Provider-specific features (batch execution, refusal fallbacks) are optional capabilities of an adapter. The deterministic test fake sits at this boundary.
- **The Experience Factory is a code-driven workflow, not an agent harness.** Python decides the steps, and each LLM step is a bounded, structured call through the boundary. Experience Factory roles never run as Claude Code (or any other harness) sessions. Such sessions would also load the user's harness configuration and register themselves as Tasks.
- **The Experience Factory's models are configured at the Organization level and per step**, independent of which harness produced a Task. Installing a Harness Adapter may ship default settings for its ecosystem. The Claude Code integration ships Haiku 5.5 for high-volume judging and Opus 5.5 for synthesis, with effort set explicitly per step.
- **A judge's identity (provider + model + effort) is part of a Judged Metric's definition.** Changing it creates a new Metric version. Every judged value records the model that actually produced it, and values from any other model (for example after a refusal fallback) are flagged.

We chose neutrality because the research claim concerns Experience Factory-based memory for LLM agents in general, not one harness. The judge belongs to the measurement, not to the agent being measured. If judges were chosen per harness, every Judged Metric would split by harness, and comparing harnesses would be confounded with comparing judges.

## Considered Options

- **Agent SDK / headless Claude Code runs for the Experience Factory**: powerful for exploring Traces, but it ties the Experience Factory to one harness, loads the user's hooks (an Analyst run would become a Task), and is harder to fake in tests. Rejected. Agentic exploration may be revisited behind the same boundary if Traces outgrow single calls.
- **Managed Agents**: Traces would leave the machine, contradicting local-first and scrubbing. Rejected.
- **A third-party multi-provider library**: reduces every provider to a lowest common denominator and adds a dependency that can change outside our control. That matters when the judge is a measurement instrument. Rejected.
- **Judges chosen per Harness Adapter**: rejected for the comparability reason above.

## Consequences

- Per-Task analysis runs synchronously by default, so a dependent Task can receive its Predecessor Tasks' Lessons Learned. Batch execution is configurable for re-analysis and backfills where the provider supports it.
- Token usage and cost are recorded per Experience Factory run, per Task and per role, as Metrics in the system's own GQM plan. No cost ceiling for now.
- Moving a judging step to a different model, for example after the agreement check in self-evaluation, is a deliberate Metric version change, never a silent configuration tweak.
