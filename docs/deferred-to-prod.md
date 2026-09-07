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

## P1-T21 — Wildcard DNS + TLS

Deferred to actual production deployment (no real domain registered yet).

Plan for when `platform.com` is registered:
- DNS: `*.platform.com` A/ALIAS record → the edge/load balancer IP, plus
  `platform.com` and `www.platform.com` for the marketing site.
- TLS: wildcard cert for `*.platform.com` via the hosting provider's managed
  edge (e.g. a wildcard ACM cert behind CloudFront/ALB if deploying to AWS,
  matching the S3/CloudFront setup already used for media in P0-T7; or the
  hosting platform's built-in wildcard cert if deploying Next.js to Vercel/
  similar - confirm which before provisioning).
- `RESERVED_HOSTS` in `tenants/middleware.py` already excludes
  `platform.com`/`www.platform.com`/`admin.platform.com` from tenant
  resolution - no code change needed here when the real domain goes live,
  only DNS + cert provisioning.
- Local dev unaffected: `.localhost` wildcard (P1-T3) continues to work
  exactly as-is.

AC ("`{slug}.platform.com` serves the correct tenant's site") is proven
today via the `.localhost` equivalent; re-verify once real DNS/TLS is live.