Update an existing GitHub pull request for the current branch. Follow these steps:

1. **Check PR Exists:**
   - Use `gh pr view` to check if a PR exists for the current branch
   - If no PR exists, inform the user and end your turn early

2. **Gather Context:**
   - Identify which commits have NOT YET been pushed to origin using `git log origin/$(git branch --show-current)..HEAD --oneline`
   - If there are no unpushed commits, inform the user and end your turn early
   - Run `git diff origin/$(git branch --show-current)..HEAD` to see what's about to be pushed
   - Review the commit messages for the unpushed commits
   - Read the current PR description using `gh pr view --json body -q .body`

3. **Analyze Changes:**
   - Compare what's already described in the PR vs. what's about to be pushed
   - Determine if this is a **minor update** or **substantial change**:

   **Minor/Incremental (add "Updated" section):**
   - Completing planned work already outlined in the PR
   - Bug fixes in already-described implementation
   - Adding tests, docs, or polish to existing implementation
   - Small refactors or typo fixes
   - Example: PR says "Implement feature X with algorithm Y", now pushing "Add 5 edge case tests and fix docstring typo"

   **Substantial/Architectural (rewrite from scratch):**
   - Going from groundwork/setup to complete feature implementation
   - Core algorithm or architecture changes from what PR describes
   - Significant scope expansion beyond original PR intent
   - Fundamental approach changed from what's described
   - Example: PR says "Add basic context tracking", now pushing "Complete two-pass resolution algorithm with 30 unit tests and new scope iteration logic"

4. **Update PR Description:**

   **If minor update** - Add "Updated" section at the end:
   - Use `gh pr edit --body` to append an "Updated" section
   - Format: `## Updated (YYYY-MM-DD)\n\n- Bullet points describing the new changes`
   - Keep the existing PR description intact

   **If substantial change** - Rewrite from scratch:
   - Follow the same format and guidance from `.claude/commands/make-pr.md`
   - Include: Summary, Background, Changes, Breaking Changes, Testing, Review Focus, Related Documents, Checklist
   - Use `gh pr edit --body` with a heredoc to replace the entire description
   - Make sure the new description accurately reflects the CURRENT complete state of the branch

5. **Push Changes:**
   - Push to origin with: `git push` (NEVER use --force or --force-with-lease)
   - Confirm the push succeeded

6. **Confirm Completion:**
   - Report what you did (updated PR description + pushed X commits)
   - Provide the PR URL for reference
