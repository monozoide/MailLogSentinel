# Contributing Guidelines (Detailed)

This document expands on [CONTRIBUTING.md](../docs/CONTRIBUTING.md). Read the short version first.

## Table of Contents

- [Complete Workflow](#complete-workflow)
- [Commit Signature Setup](#commit-signature-setup)
- [Quality Standards](#quality-standards)
- [Code Contributions](#code-contributions)
- [Documentation Contributions](#documentation-contributions)
- [Questions?](#questions)

## Complete Workflow

### 1. Claim the Issue

**Why:** Prevents duplicate work and lets maintainers track active contributors.

**How:**
```
Comment: "I'd like to work on this" or "Can I take this issue?"
```

> [!WARNING]
>  Wait for a maintainer to assign you. **Do not start work before assignment.**

**Rules:**
- One issue per contributor at a time
- If assigned but can't complete within 7 days, comment to release the issue
- Abandoned issues (no activity for 10 days) will be unassigned

### 2. Fork the Repository

**Use GitHub's branch-specific fork:**

1. Click "Fork" on the repository
2. **Uncheck** "Copy the main branch only"
3. **Select only the branch** mentioned in the issue (e.g., `feature/issue-123`)
4. Complete the fork

**Why:** Keeps your fork clean, makes rebasing easier, reduces merge conflicts.

**If the issue doesn't specify a branch:** Wait for a maintainer to assign you. **Do not start work before assignment.**

### 3. Understand the Context

Before coding:

- Read the **entire issue description**
- Check linked PRs or related issues
- Review existing code patterns (file structure, naming conventions, test style)
- Run the project locally to understand current behavior

**If anything is unclear:**
- Comment on the issue with specific questions
- Use [Discussions](../../../discussions) for broader topics
- **Never make assumptions** — asking takes 5 minutes, fixing wrong assumptions takes hours

### 4. Development

**General rules:**
- Follow existing code style (indentation, naming, structure)
- Keep changes focused on the issue scope
- Commit frequently with clear messages
- **Sign every commit**

**Before pushing:**

- **Run linting**

- **Run tests**

- **Check commit signatures**

## Commit Signature Setup

**All commits must be signed with GPG or SSH.**.

**Full guide:** https://docs.github.com/en/authentication/managing-commit-signature-verification

**SSH alternative:** https://docs.github.com/en/authentication/managing-commit-signature-verification/signing-commits

## Quality Standards

### What "Minimum Effort" Means

**We reject:**
- Unmodified AI-generated code (100% copy-paste from ChatGPT, Copilot, etc.)
- Code that doesn't work (untested, fails CI)
- Generic fixes that don't address the specific issue
- PRs with no description or context

**We accept:**
- AI-assisted code that you've tested, understood, and adapted
- Solutions that show problem-solving thought process
- Code with explanatory comments for complex logic

## Code Contributions

### Requirements Checklist

- [ ] Linting passes
- [ ] All tests pass
- [ ] New tests added for new functionality (minimum 80% coverage for new code)
- [ ] No breaking changes (or documented in PR)
- [ ] Commits are signed
- [ ] Branch is up-to-date with base branch

### Testing Standards

**Unit tests:**
- Test happy path + edge cases
- Mock external dependencies
- Use descriptive test names

**Integration tests (if applicable):**
- Test actual behavior, not implementation
- Cover error scenarios

## Documentation Contributions

**Requirements:**
- Follow existing Markdown style (headers, lists, code blocks)
- Verify all links work (`markdown-link-check` if available)
- Test code examples in a real environment
- Still require signed commits

**Structure:**
- Use clear headers (H2 for sections, H3 for subsections)
- Add code examples with language tags (`python`, `bash`)
- Include "Before/After" comparisons for changes

## Questions?

- **"Can I work on multiple issues?"** → No, one at a time until you have 3+ merged PRs
- **"How long until my PR is reviewed?"** → Usually 2-5 days, ping me after 5 days
- **"Can I use AI tools?"** → Yes, but you must understand and test the code
- **"What if I can't finish?"** → Comment on the issue to release it

**Still have questions?** Use [Discussions](../../../discussions) or comment on the issue.

---

Thank you for taking the time to contribute properly! These guidelines exist to keep the project maintainable and ensure everyone's time is respected. We appreciate your effort. 🚀