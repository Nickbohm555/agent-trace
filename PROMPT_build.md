0b. Study @IMPLEMENTATION_PLAN.md.
0c. For reference, the application source code is in `src/*`.

Before starting, completely restart the application so we have fresh builds, logs, ect;

997. Iteration scope: complete the item that is specified for you at the top of the plan.

0. Read the TOP of in @IMPLEMENTATION_PLAN.md where it says: Tracing deep-agent (harness engineering) to get context before diving in. Just know enough so you know what the app is about.

1. Take the item in  @IMPLEMENTATION_PLAN.md where it says: 'Current section to work on:'


2. Before making changes, search the codebase so existing functionality is reused when possible. Keep deep agents / subagents general architecture. Keep the same UI features. 


3. After implementing functionality, ALWAYS add logs for visibility and check what containers were changed and either restart or completely reboot depending on the task. when in doubt, restart the application entirely and check all the container logs. for any frontend tasks, check the instructions for the chromDev tool in @AGENTS.md If you see an error, fix it now and re-run to make sure it works. run the required tests from the task definition. You must provide and view logs for every item built. 

4. When the task is completed: always copy that item from @IMPLEMENTATION_PLAN.md and append it to @completed.md, as well as append any useful logs. Append any additional things needed if it didnt succeed fully. Move the specified item to work on +1 for the next turn. 


6. After completion or blocked, either way we write `.loop-commit-msg` then end this run. For `loop-commit-msg`, add every a short summary of what was built and tested. 


NOTE: Keep @AGENTS.md operational only (how to build/test/run). Keep remaining work in @IMPLEMENTATION_PLAN.md; record completed items in @completed.md.
NOTE: Prefer complete functionality over placeholders/stubs unless explicitly needed.
