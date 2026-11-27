# PulseMonitor

- Develop on `main`. Keep the supplied brief and visual references intact.
- Use Alembic migrations for schema changes and PostgreSQL for integration tests.
- Enforce ownership at every private API route. Keep secrets in environment variables and never expose private monitor destinations in public responses.
- All resource checks must use the same destination validation and connection policy, including redirects and manually scheduled checks.
- Verify backend tests, frontend lint, types, tests and production build before publishing. Scan the exact Git payload before making it public.
