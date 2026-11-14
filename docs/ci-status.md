# CI status

**GitHub Actions jobs do not start.** Since 2026-11-13 every run fails before a runner is assigned
with "The job was not started because your account is locked due to a billing issue". The owner's
licensing page says the account is disabled for an unpaid charge. Making the repository public
(2026-11-14) did not change this.

- **Not a code failure.** No job has run, so there is no remote result, green or red.
- **Local results in the meantime:** pull requests report `make check` and the Playwright suite
  run locally, and say so. They never describe local runs as CI.
- **Rechecked 2026-11-15:** PRs #2 to #4 queued runs; every job failed in about 3 s with 0 steps
  run, with the same "account is locked due to a billing issue" message. Still blocked.
- **Once the account is unlocked:** re-run the workflows on the open pull requests (#1, #2, #3 and
  later) and review the actual results before merging.
- **No workaround.** No other CI service, self-hosted runner or account is used to get around the
  lock.
