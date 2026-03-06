0b. Study @test_plan.md.
0c. For reference, the application source code is in `src/*`.

Before starting, completely restart the application so we have fresh builds, logs, etc.

997. Iteration scope: complete the item that is specified for you at the top of the plan.

1. Take the item in  @test_plan.md where it says: 'Current section to work on:'

2. Build these tests Then run the required tests from the task definition. Have a fresh build for all tests. You must provide and view logs for every item built. Complete each test before moving on. If a test fails: debug (Docker + Chrome DevTools; see @AGENTS.md for build/test/run and browser-debug workflow), fix the cause, re-run until it passes, and show that the fix worked before advancing. 

4. When the task is completed: always copy that item from @test_plan.md and append it to @test_completed.md, as well as append any useful logs. Move the specified item to work on +1 for the next turn. 


6. After completion or blocked, either way we write `.loop-commit-msg` then end this run. For `loop-commit-msg`, add every a short summary of inputs / output results of tests.


NOTE: Keep @AGENTS.md operational only (how to build/test/run). 
NOTE: Prefer complete functionality over placeholders/stubs unless explicitly needed.
