# Repository baseline

**Decision (2026-11-13, owner-authorised):** the project is committed as one atomic baseline. The grouped history below was never committed, and earlier groups would not pass the checks on their own. Later work lands as normal, meaningful commits. The checks below were rerun on the baseline.

## The grouped plan considered (superseded)

The repository at `badminton-scout/` has **no commits** yet. All 157 files to commit are
untracked (`git ls-files --others --exclude-standard`). The parent repository at `/Users/leo`
is untouched.

Files changed across milestones, so commits group the current files **by area**; they don't
replay history. Each step is one `git add` of the listed paths and one commit. The full suite
passes at the final commit, but earlier commits may not pass on their own.

| # | Commit message | Paths |
|---|---|---|
| 1 | `chore: repository foundation` | `.gitignore` `.env.example` `compose.yaml` `Makefile` `README.md` `AGENTS.md` `CLAUDE.md` |
| 2 | `docs: data rights register, ADRs 0001–0010, provider research` | `docs/kickoff-report.md` `docs/data-sources.md` `docs/adr/` `docs/bwf-access-request.md` `docs/badminton-providers.md` `docs/global-integrations.md` |
| 3 | `feat(backend): FastAPI app, models, migrations 0001–0015, rights registry, privacy` | `backend/pyproject.toml` `backend/uv.lock` `backend/.python-version` `backend/alembic.ini` `backend/migrations/` `backend/src/scout/` *except* `backend/src/scout/ingest/` |
| 4 | `feat(ingest): API Anything provider, Tournament Software portals, consent, queue and sync` | `tools/api-anything/` `backend/src/scout/ingest/` `docs/api-anything.md` |
| 5 | `feat(ops): scheduled sync (launchd/cron/systemd)` | `tools/scheduling/` `docs/operations.md` |
| 6 | `test(backend): unit, integration and live suites` | `backend/tests/` |
| 7 | `feat(web): Next.js frontend and design system` | `web/` (everything not git-ignored) `docs/design.md` |
| 8 | `ci: backend, web and end-to-end jobs` | `.github/workflows/ci.yml` |
| 9 | `docs: commit plan` | `docs/git-commit-plan.md` |

**Checked on 2026-11-13, before this plan:**
- **gitleaks v8.21.2** (official container, `dir` mode) over an exact copy of the 157 candidate
  files: no leaks found.
- **No third-party records:** the candidates were compared against every multi-word player
  name in the dev database (28,245 names). One real name was in a test
  (`test_tournamentsoftware.py`, the seeding-marker case); it is now synthetic. Rerun this
  check before committing; it prints only file names.
- **Cookie and session values:** none. The two matches for "CookiePurposes=1" are prose and code
  describing the minimal consent, not cookie values.
- **Ignored, and must stay out:**
  - `.env`;
  - `.tools/`: uv, API Anything homes with consent cookies and keychain-sealed sessions,
    Playwright browsers, `sync.log`;
  - `backend/.venv/`, `node_modules/`, `web/.next/`, `web/test-results/`,
    `web/playwright-report/` (newly ignored), `web/e2e/fixture-ids.json`, every `__pycache__/`.
- **Largest files:** `web/package-lock.json` (380 KB) and `backend/uv.lock` (232 KB). No data
  dumps, databases or binaries.

**CI readiness:**
- Every step the workflow runs passes locally: ruff, pyright, alembic on a clean database,
  pytest, `npm ci`-equivalent checks, type generation, typecheck, lint, vitest,
  `npm audit --omit=dev --audit-level=high` (0 vulnerabilities), and Playwright.
- The generated API types were stale (they would have failed the contract check) and are now
  regenerated.
- The jobs need no secrets.
- Default tests make no network calls and don't need the Node API Anything runtime; that
  runtime is only needed by `-m live`.
- `uv sync` downloads the pinned `api-anything` Python client from GitHub, so that repository
  must stay public, or the lock must point at a reachable mirror.

**Before the first push (needs the owner):**
1. Choose the GitHub repository and its visibility, and approve the remote.
2. Approve this plan. The commits are then made exactly as listed.
3. The first remote run is the first time the workflow runs on a GitHub runner, so environment
   details (runner Postgres timing, Playwright browser install) may need a fix there.
