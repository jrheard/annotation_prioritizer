You are now in PROPOSE_PLAN_DOC mode. In this mode, you will work with the user to create an outline for an implementation plan for the proposed work we've been discussing. Once we're done, we'll use this outline to write that full implementation plan.

## IMPORTANT RULES FOR PROPOSE_PLAN_DOC MODE:
- DO NOT edit, create, or modify ANY files while in PROPOSE_PLAN_DOC mode
- DO NOT use any file editing tools (Edit, Write, MultiEdit, NotebookEdit)
- Your goal is to present and refine an OUTLINE with the user
- Continue iterating until the user indicates they're ready to proceed with the full plan

## Step 1: Present the Plan Outline

IMPORTANT: Before presenting the outline, PROACTIVELY ASK QUESTIONS if:
- Any requirements seem ambiguous or unclear
- There are apparent contradictions in the instructions
- Multiple implementation approaches exist with significantly different trade-offs
- You need clarification on priorities or use cases
- The scope seems too large or too small for what was discussed
- Dependencies or assumptions need validation

Present a structured outline for the implementation plan that includes:

1. **Implementation Steps** (as numbered list)
   - Each step should represent a logical atomic commit
   - Include brief description of what each step accomplishes
   - Order steps by dependencies and logical progression
   - **IMPORTANT**: This project enforces 100% test coverage. Each commit must:
     - Include both implementation AND tests (except for pure refactoring)
     - Pass all pre-commit hooks (ruff, pyright, pytest with 100% coverage)
     - Leave the codebase in a working state

2. **Key Architectural Decisions**
   - File structure changes or new files needed
   - Major design choices or patterns to use
   - Integration points with existing code

3. **Assumptions and Dependencies**
   - What existing functionality you're building on
   - External libraries or tools required
   - Any constraints or requirements

Keep the outline concise but comprehensive. Each item should be a single line or brief bullet point that can be easily discussed and modified.

## Step 2: Iterate on the Outline

Work with the user to refine the outline:
- Add new steps or details as requested
- Remove unnecessary items
- Reorder steps for better flow
- Clarify any ambiguous points
- Adjust scope based on feedback

During iteration, continue to PROACTIVELY ASK QUESTIONS when:
- User feedback seems to conflict with earlier requirements
- A suggested change would have significant downstream effects
- You notice potential issues or edge cases not yet discussed
- The user's intent behind a change request is unclear

Continue iterating until the user indicates they're satisfied.

## Step 3: Exit PROPOSE_PLAN_DOC Mode and Write Full Plan

When the user says something like:
- "looks good, write the plan"
- "finalize the plan"
- "exit propose-plan-doc mode"
- "let's proceed with this plan"
- Or similar confirmation

Then:
1. Exit PROPOSE_PLAN_DOC mode
2. Write the full implementation plan to `plans/pending/descriptive-name-YYYY-MM-DD.md` (first run `date` to see today's date)

The full plan should expand the outline into a detailed document following this format:
- Full implementation steps with detailed context for each. The plan should lay out this work as a series of small-to-medium-sized atomic commits.
  - Each commit must include both implementation AND tests (except for pure refactoring)
  - Each commit must maintain 100% test coverage
  - Each commit must pass all pre-commit hooks
- Recommended file structures with explanations
- Example code snippets where helpful
- Comprehensive list of assumptions and dependencies
- NO time estimates or duration sections

Note: This is a single-developer project with no backward compatibility requirements. Feel free to propose breaking changes if they improve the codebase.

Remember: Use the sequential thinking tool when creating both the outline and the full plan to ensure thoroughness and clarity.

## Example Outline

Here's what an outline would look like for adding unresolvable call reporting (a completed feature):

```markdown
# Unresolvable Call Reporting - Outline

## Implementation Steps

### Data Model Changes
1. Add UnresolvableCategory enum for categorizing why calls can't be resolved
2. Create UnresolvableCall dataclass to store unresolvable call information
3. Add AnalysisResult dataclass to bundle priorities with unresolvable calls

### Core Logic Implementation
4. Implement categorize_unresolvable_call() pure function for categorization logic
5. Update CallCountVisitor to track unresolvable calls alongside resolved ones
6. Modify count_function_calls() to return both resolved and unresolvable calls
7. Update analyzer.py to handle the new AnalysisResult type

### CLI Integration
8. Integrate unresolvable summary display into CLI main()
9. Add display_unresolvable_summary() to output.py for formatting

### Testing
10. Write comprehensive unit tests for categorization logic
11. Add integration tests for CLI output

## Key Architectural Decisions
- New data models in models.py (UnresolvableCategory, UnresolvableCall, AnalysisResult)
- Pure function approach for categorization logic
- Track unresolvable calls in visitor alongside normal counting
- Always show unresolvable summary in CLI output (not behind a flag)

## Assumptions and Dependencies
- Requires completed class-detection-improvements first
- Assumes users want transparency about what can't be analyzed
- No backward compatibility concerns (single-developer project)
- Categories based on AST node structure patterns
```

This outline gives the high-level structure that can be refined through discussion before expanding into the full plan.

Once the user has accepted your outline, exit PROPOSE_PLAN_DOC mode and write the full plan.
