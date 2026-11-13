@AGENTS.md

## Claude Code notes
- Use plan mode for any milestone-sized change. Implement small fixes directly.
- Spawn parallel agents only for independent work against a frozen contract, each in its own worktree.
- Run a review (`/code-review` or `ponytail-review`) on the diff before proposing a PR.
