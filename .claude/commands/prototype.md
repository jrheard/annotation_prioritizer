You are now in PROTOTYPE mode. Your goal is to implement a quick-and-dirty prototype of the plan to validate its feasibility - NOT to create production-ready code.

## Core Rules

1. **Single Context Window**: The entire prototype MUST fit within this one Claude Code conversation. If you absolutely need to split it, use at most 2 commits.
2. **Speed Over Quality**: Skip tests, skip full error handling, use shortcuts. The goal is to discover plan issues quickly.
3. **No Verification**: Always use `--no-verify` when committing to skip pre-commit hooks.
4. **New Branch**: Create a descriptive prototype branch before starting work.

## Implementation Approach

### Step 1: Understand the Plan
- Read the plan file carefully
- Use sequential thinking to identify the core functionality that needs prototyping
- Focus on the parts most likely to reveal issues (complex integrations, unclear steps, dependencies)

### Step 2: Create Branch
- Create a new branch with format: `prototype/descriptive-name-YYYY-MM-DD` (use `date` to see today's date)
- The branch name should reflect what's being prototyped

### Step 3: Implement Minimal Prototype
- Implement JUST enough code to validate the plan's feasibility
- Skip:
  - Comprehensive tests (add minimal tests ONLY if needed to verify something works)
  - Full error handling
  - Edge cases
  - Documentation
  - Code quality (type hints, linting, formatting)
- Focus on:
  - Core logic flow
  - Key integrations and dependencies
  - Steps that seem unclear or complex
  - Assumptions that need validation

### Step 4: Make 1-2 Commits
- Commit your prototype work with `git commit --no-verify`
- Use conventional commit format: `feat(prototype): brief description of what was prototyped`
- If you must split into 2 commits, make the first one establish the foundation, and the second one complete the prototype

### Step 5: Write Findings
- Create a file named `prototype_findings.md` in the root directory
- Include this file in your final prototype commit (don't make a separate commit for findings)

## Findings Document Structure

Your `prototype_findings.md` should answer these questions:

### What I Learned
- What do you know NOW that you wish you'd known BEFORE starting the prototype?
- What foundational work should have been step 0 but wasn't mentioned?
- What discoveries would have changed the planning?

### Plan Issues Found
- Which steps are unclear, underspecified, or need more detail?
- Which steps are in the wrong order?
- Which steps are missing entirely?
- Which steps turned out to be impossible or infeasible as written?

### Integration Challenges
- What unexpected dependencies or conflicts did you discover?
- What existing code needs to be refactored first?
- What assumptions in the plan were wrong?

### Recommendations
- Should this plan be implemented as-is? (yes/no)
- If no: What needs to change before starting the real implementation?
- If yes: What clarifications or additions would help the implementer?
- Are there alternative approaches that would work better?

### Prototype Scope
- Briefly list what you DID implement in the prototype
- Briefly list what you DIDN'T implement (and why it wasn't necessary for validation)

## Important Reminders

- **THIS IS NOT PRODUCTION CODE** - Be scrappy, take shortcuts, hard-code things
- **VALIDATE, DON'T PERFECT** - You're looking for plan problems, not writing perfect code
- **BE HONEST IN FINDINGS** - If the plan has issues, say so clearly
- The prototype code will likely be thrown away - what matters is what you learned

## After Completion

Once you've committed your prototype and findings:
1. Summarize the key findings for the user
2. Recommend whether to proceed with the plan, revise it, or reconsider the approach
3. Do NOT create a PR or merge the prototype - this is just for validation

---

<plan file>
$ARGUMENTS
</plan file>
