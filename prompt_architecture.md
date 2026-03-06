0a. reference @completed.md 
0b. For reference, the application source code is in `src/*`.
0c. **Priorities:** Data flow and tradeoffs are top priorities. Every architecture document (section and system) must emphasize data flow and include an explicit tradeoffs section.

997. Iteration scope: document the architecture for the section specified at the top of the architecture tracker, or produce the total system architecture when past the last section.

1. Open @ARCHITECTURE_TRACKER.md. It must contain a line: `Current section to work on: section N`. If the file is missing, create it with that line and N = 1. Use this N as the current section number for this run.

2. Parse @completed.md for all section headers (`## Section N: ...`). Determine the last section number (e.g. 14). If the current section number (from the tracker) is greater than the last section in completed.md, go to step 6 (total system architecture). Otherwise continue to step 3.

3. Take the section in @completed.md that matches the current section number. Read that section’s goal, details, files, and implemented behavior. Inspect the relevant files under `src/*` to understand structure, data flow, and interfaces.

4. Write the architecture for this section to a single markdown file. The audience is a beginner / intermediate programmer that needs a clean view of how each part works. Use `docs/section-NN-title.md` (e.g. `docs/section-01-coordinator-flow.md`), where the title is a short slug from the section name. **Required content:** purpose, components, **data flow** (inputs, outputs, transformations, and how data moves between components—prioritize clarity here), key interfaces or APIs, how it fits with adjacent sections, and **tradeoffs** (design choices made, alternatives considered or rejected, and their pros/cons). Create `docs/` if it does not exist.

5. Update @ARCHITECTURE_TRACKER.md: set `Current section to work on: section M` where M = N + 1. Write `.loop-commit-msg` with a short summary of the section architecture documented, then end this run.

6. **Total system architecture (only when current section > last section):** Produce one document that describes the full system: **data flow** end-to-end (how data moves through the system, key pipelines, and boundaries), high-level flow, all major components, how sections connect, deployment/runtime boundaries, and **tradeoffs** (system-wide design decisions, alternatives, and their pros/cons). Write it to `docs/SYSTEM_ARCHITECTURE.md`. Update @ARCHITECTURE_TRACKER.md to record that the total system architecture is done (e.g. add a line “Total system architecture: done”). Write `.loop-commit-msg` with a short summary, then end this run.

NOTE: Do not modify @IMPLEMENTATION_PLAN.md or @completed.md. Keep @AGENTS.md operational only. Use @ARCHITECTURE_TRACKER.md only for “Current section to work on” and total-architecture completion.
