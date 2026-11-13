# Badminton Scout web

Next.js 16 (App Router, Cache Components) frontend for the Badminton Scout API. Design: `../docs/design.md`.

```sh
npm ci
SCOUT_API_URL=http://127.0.0.1:8000 npm run dev   # API from `make dev` at the repo root
npm run check                                    # typecheck + lint + unit/component tests
npm run e2e                                      # Playwright, desktop + mobile, synthetic fixture
```

- **Data** comes only from the server-side client in `src/lib/api/client.ts`. `SCOUT_API_URL` is a server-only variable. Nothing is cached, and privacy filtering happens in the API (ADR-0009).
- **API types** are generated, never hand-edited: run `npm run api:openapi && npm run api:types` after any backend contract change. CI fails when they drift.
- **End-to-end tests** start `e2e/backend.sh`, which migrates and seeds a `*_e2e` database, plus a production build on port 3100. Set `PLAYWRIGHT_BROWSERS_PATH` to keep browsers out of your home cache.
