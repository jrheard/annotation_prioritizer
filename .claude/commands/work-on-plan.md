Find the next step in the implementation plan that's ready to be worked on:
- Look for the first "### Step N:" heading that is NOT marked with ✅ or (COMPLETED)
- Verify any prerequisite steps mentioned in that step are already completed
- This is the step to implement

Implement that step completely:
- Write all code described in the step
- Write all tests described in the step
- Ensure tests pass, linting passes, type checking passes
- Implement ONLY that one step—do not continue to subsequent steps

Update the plan file BEFORE committing:
- Mark the step as completed by adding ✅ to its heading: `### Step N: [Title] ✅`
- Add a brief note under the step about any implementation deviations or discoveries
- Do NOT modify other steps

Commit your changes:
- Include ALL changes in ONE commit: code, tests, AND the updated plan file
- Use a descriptive commit message referencing the step number
- Format: "feat(step-N): <description>" or "refactor(step-N): <description>"

If you complete the final step:
- Mark it completed in the plan as usual
- Move the plan file from plans/pending/ to plans/completed/
- Include the file move in your commit

If you cannot complete the step:
- Do NOT commit partial work
- Explain what's blocking you and stop
- The user will address the blocker before re-running

<plan file>
$ARGUMENTS
</plan file>
