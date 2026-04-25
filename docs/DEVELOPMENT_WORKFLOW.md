# Development Workflow

This document defines the minimum standards for commits, pull requests, reviews, and approvals for this repository.

## Commit Message Standards

- Write clear, specific commit messages that describe the change and intent.
- Keep the subject line short and action-oriented.
- Prefer one logical change per commit.
- Reference the related issue, task, or ticket when applicable.
- Avoid vague messages like `update`, `fix stuff`, or `changes`.

### Recommended Format

```text
<type>: <short summary>
```

Examples:

- `feat: add Instagram posting validation`
- `fix: handle missing speaker data in orchestrator`
- `docs: add pull request review standards`
- `test: cover partner agent fallback flow`

Suggested commit types:

- `feat`
- `fix`
- `docs`
- `refactor`
- `test`
- `chore`

## Pull Request Creation Standards

- Open a pull request for every change that is intended to be merged.
- Use a descriptive PR title that matches the core change.
- Format PR titles as `(type) - short summary`.
- Keep PRs focused and reasonably sized so they are reviewable.
- Include a short summary of what changed and why.
- List any testing completed.
- Mention known limitations, risks, or follow-up work.
- Add screenshots or sample output when the change affects user-facing behavior.

### PR Description Checklist

- What changed
- Why the change was needed
- How it was tested
- Any risks, assumptions, or rollback notes

### Example PR Titles

- `(feat) - add validation for missing Instagram access token`
- `(fix) - correct event reminder scheduling for past dates`
- `(refactor) - improve error handling in Google Sheets sync`
- `(docs) - update contributor workflow documentation`

### Example PR Description

```markdown
## Summary

- Add validation before Instagram posting starts
- Show a clearer error message when the access token is missing

## Why

- The posting flow was failing late in execution
- Earlier validation makes the failure easier to understand and debug

## Testing

- [x] Unit tests
- [x] Manual testing
- [ ] Not needed

Manual checks completed:
- Verified valid token flow still proceeds normally
- Verified missing token returns a clear validation error

## Risks / Notes

- This change only affects the Instagram posting path
- No data migration or config changes required
```

## Review Standards

- Every PR must be reviewed before it is merged.
- Reviewers should check correctness, clarity, maintainability, and test coverage.
- Reviewers should call out bugs, regressions, security concerns, and missing validation.
- Comments should be specific and actionable.
- Authors should respond to review feedback and update the PR as needed.
- If significant new changes are pushed after review, the PR should be reviewed again.

### Minimum Reviewer Expectations

- Confirm the change solves the stated problem.
- Check for edge cases and unintended side effects.
- Verify tests are present or explain why they are not needed.
- Confirm naming, structure, and documentation are clear enough to maintain.

## Approval Standards

- A PR must receive explicit approval before merge.
- Approval should only be given after the reviewer is satisfied with the current state of the PR.
- If requested changes are made later, reviewers should re-check the updated diff before approval stands.
- Self-approval is not sufficient for merge unless the repository owners explicitly define an exception outside this document.

## Merge Policy

- Do not merge a PR without review.
- Do not merge a PR without approval.
- Do not bypass reviewer feedback unless the reviewer has confirmed resolution.
- Prefer squash merge or the repository's default merge strategy unless the team agrees otherwise.

## Suggested PR Template Content

```markdown
## Summary

- Brief description of the change

## Testing

- [ ] Unit tests
- [ ] Manual testing
- [ ] Not needed

## Risks / Notes

- Any known risk, limitation, or follow-up
```
