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

1. **Code Reuse Investigation** (REQUIRED before proposing implementation)
   - Search for existing helper functions, utilities, or patterns that can be reused
   - Identify common logic that should be extracted rather than duplicated
   - List specific modules/functions from the codebase to leverage
   - Note any patterns that appear multiple times and could be consolidated
   - **It's perfectly fine to conclude "None found" after thorough investigation**

2. **Prerequisite Refactoring Assessment**
   - Identify foundational improvements that would simplify the implementation
   - Propose extractions or abstractions that multiple features would benefit from
   - Note any architectural changes that would make the code more maintainable
   - List refactors that should be done FIRST to make subsequent steps cleaner
   - **"No refactoring needed" is a valid conclusion - don't force unnecessary changes**

3. **Implementation Steps** (as numbered list)
   - Each step should represent a logical atomic commit
   - Include brief description of what each step accomplishes
   - Order steps by dependencies and logical progression
   - **CRITICAL REQUIREMENT**: Every commit must pass pre-commit hooks
     - Each commit description MUST specify BOTH:
       1. What code/functionality is being added/changed
       2. What tests are being added/updated in THE SAME COMMIT
     - Example: "Add User model with fields + Add comprehensive User model tests"
     - NEVER defer tests to a later commit (e.g., avoid "Add tests for User model" as separate step)
     - Exception: Pure refactoring commits may not need new tests
     - Each commit must maintain 100% test coverage
     - Each commit must pass pyright and ruff checks

4. **Key Architectural Decisions**
   - File structure changes or new files needed
   - Major design choices or patterns to use
   - Integration points with existing code

5. **Assumptions and Dependencies**
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
  - **EACH COMMIT DESCRIPTION MUST EXPLICITLY STATE**:
    - The implementation changes being made
    - The test changes/additions in that SAME commit
    - Example format: "Step 3: Add validation logic to User.validate() method and corresponding unit tests testing all validation rules"
  - Each commit must maintain 100% test coverage
  - Each commit must pass all pre-commit hooks (pyright, ruff, pytest)
  - Pure refactoring commits are the only exception to the test requirement
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

## Code Reuse Investigation
- Leverage existing AST visitor pattern from call_counter.py
- Reuse priority calculation logic from analyzer.py
- Use existing display utilities from output.py for consistent formatting
- Extract common AST node inspection patterns into helper functions

## Prerequisite Refactoring Assessment
- Extract AST node type checking into reusable predicates (is_method_call, is_function_call)
- Create shared pattern for visitor result accumulation
- Consider abstracting visitor state management for reuse in future visitors

## Implementation Steps

### Data Model Changes
1. Add UnresolvableCategory enum + tests for enum values and string representations
2. Create UnresolvableCall dataclass + tests for initialization, equality, and frozen behavior
3. Add AnalysisResult dataclass + tests for bundling priorities with unresolvable calls

### Core Logic Implementation
4. Implement categorize_unresolvable_call() + comprehensive unit tests for each category
5. Update CallCountVisitor + tests verifying both resolved and unresolvable tracking
6. Modify count_function_calls() + update existing tests to verify new return type
7. Update analyzer.py + tests for AnalysisResult handling

### CLI Integration
8. Integrate unresolvable summary into main() + update CLI integration tests
9. Add display_unresolvable_summary() + tests for various display scenarios

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
