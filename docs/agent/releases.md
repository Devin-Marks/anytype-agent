# Agent Notes: Releases

Read this when the user asks to cut a release, bump a version, prepare a version bump PR, or update release notes.

## Version Cut Workflow

When cutting a version, use repository release tooling if it exists. This project currently has a Python package version in `pyproject.toml`; do not invent release automation or tags without user approval.

1. Start from a clean working tree on the intended release base, normally `main`.
2. Inspect the changes since the last version commit/tag and summarize the release-worthy changes.
   Useful commands:

   ```bash
   git log --oneline --decorate --grep='chore(release):' --max-count=5
   git tag --sort=-version:refname | head
   git log --oneline <last-version-ref>..HEAD
   git diff --stat <last-version-ref>..HEAD
   ```

3. If the repo has a `CHANGELOG.md`, fill out `## [Unreleased]` with the changes since the last version commit. Group entries under the existing changelog style/categories when possible.
4. If a release script is added later, prefer it over hand-editing versions and follow its printed next-step instructions. If no release script exists, update `pyproject.toml` only after confirming the target version with the user.
5. Include changelog updates, version bumps, and release-specific docs together in the version bump PR. The PR should clearly call out that release notes were generated from changes since the previous version.

## Important Rules

- Do not commit, push, or tag unless the user explicitly asks.
- Do not create or modify release automation as part of a release unless the user asks for tooling changes.
- Keep version bumps minimal and scoped to files that actually declare the project version.
- If a `CHANGELOG.md` is introduced, keep the version bump PR paired with a completed changelog entry for that version.
- Run the project checks appropriate to the release change before handoff, usually `python -m pytest` and `python -m ruff check .` when practical.
