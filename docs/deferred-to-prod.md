# Deferred to Production Build

Items blocked locally by environment policy (no Docker, no WSL) — must be
completed before go-live, not just "nice to have":

1. **PgBouncer transaction-pooling mode** (P0-T3)
   - Local dev connects Django directly to Postgres.
   - Prod MUST run PgBouncer in `pool_mode = transaction` in front of Postgres.
   - Re-run the GUC-survives-pooling spike (see Implementation Plan §9, spike #2)
     against the real PgBouncer instance before RLS (P1-T5) is trusted in prod.
   - GUC-setting code (core/db.py) is already pooler-agnostic — no app changes
     expected, but verification is mandatory.

2. **Docker** — local dev uses native services (Postgres, Memurai, Mailhog).
   Prod/staging should containerize per the original docker-compose.yml /
   Dockerfile drafted in P0-T2 (kept in repo, unused locally for now).