0a. Study `specs/*` to learn the application specifications.
0b. Study @IMPLEMENTATION_PLAN.md (if present) to understand the plan so far.
0c. Study `src/lib/*` to understand shared utilities and components.
0d. For reference, the application source code is in `src/*`.

1. Study @IMPLEMENTATION_PLAN.md (if present; it may be incorrect) and compare existing source code in `src/*` against `specs/*`. For each task in the plan, derive required tests from acceptance criteria in specs - what specific outcomes need verification (behavior, performance, edge cases). Tests verify WHAT works, not HOW it's implemented. Include as part of task definition.
2. Create or update @IMPLEMENTATION_PLAN.md as a prioritized bullet list of items yet to be implemented.
3. For each task, derive verification requirements from acceptance criteria in specs (what outcomes must be validated, not implementation details).
4. Keep @IMPLEMENTATION_PLAN.md up to date with complete/incomplete status.
5. At the end of the run, write one line to `.loop-commit-msg` in the repo root so the loop can use it for the commit (e.g. `Planned: <brief summary of what was added/updated>.`).

NOTE: Keep this run focused on planning. Avoid implementation and commits in this mode.
NOTE: Try to confirm missing functionality with code search before marking gaps.
NOTE: Treat `src/lib/*` as the project's shared standard library and prefer consolidated implementations.
