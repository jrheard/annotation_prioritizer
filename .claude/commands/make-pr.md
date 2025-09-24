Create a detailed GitHub pull request using the `gh pr create` command. Follow these steps:

1. **Gather Context:**
   - Identify the current branch name
   - Search for relevant plan files in `plans/` that match the branch name or related features
   - Run `git diff main...HEAD` to understand all changes in the branch
   - Review recent commit messages to understand the progression of work
   - Check for any TODOs or FIXMEs in the changed files

2. **Analyze Changes:**
   - Group changes by type (features, refactors, bug fixes, tests, docs)
   - Identify breaking changes or API modifications
   - Note any dependencies or configuration changes
   - Assess test coverage for new functionality

3. **Create PR Description:**
   The PR description should include:
   - **Summary**: 2-3 sentences explaining the high-level purpose
   - **Background**: Context from plan documents and why these changes were made
   - **Changes**: Detailed bullet list of all modifications, organized by category
   - **Breaking Changes**: Clearly marked section if any exist
   - **Testing**: Description of test coverage and how to verify the changes
   - **Review Focus**: Specific areas where reviewer attention is needed
   - **Related Documents**: Links to relevant plan files or issues
   - **Checklist**: Standard review items (tests pass, linting clean, docs updated)

4. **Implementation Notes:**
   - Use `gh pr create` with `--title` and `--body` flags
   - Use a heredoc for the body to ensure proper formatting
   - Include the branch's plan context to help reviewers understand design decisions
   - Highlight any deviations from the original plan and explain why
   - Note any follow-up work that might be needed

5. **Post-Creation:**
   - Provide the PR URL for reference

Focus on creating a PR description that gives reviewers all the context they need to understand not just what changed, but why it changed and how to verify it works correctly.
