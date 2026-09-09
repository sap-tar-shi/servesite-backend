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


## P2-T9 — Live webhook delivery verification

Deferred to production deployment. Razorpay's dashboard rejects
`localhost` webhook URLs outright, and ngrok isn't available in the
current dev environment (office laptop restrictions).

Current state:
- Signature verification and idempotency logic are fully covered by
  automated tests (payments/tests.py::PaymentFlowTests) using a synthetic
  signed payload - the code path is proven correct.
- NOT yet verified: the actual field names/nesting Razorpay sends in a
  real payment.captured/payment.failed webhook. The assumed shape
  (payload.event, payload.payload.payment.entity.order_id, payload.id for
  event_id) is written from general knowledge, not a live delivery.
- webhook_secret is currently a placeholder, not a real Razorpay-issued one.

Before going live: deploy publicly reachable, set up a real Test Mode
webhook in Razorpay's dashboard, trigger a real test payment, confirm the
payload matches what PaymentWebhookView expects, adjust if not.


## Platform billing (P3-T2)

- `sync_razorpay_plans` and `SubscriptionView.post` both call the platform's
  own Razorpay account (`PLATFORM_RAZORPAY_KEY_ID/SECRET`) - this account is
  currently not authorizing API requests at all (401 Unauthorized on `/v1/plans`
  even with freshly regenerated Test keys, confirmed via direct curl, not a
  code bug). Root cause not yet isolated - candidates: account-level
  activation/KYC gate on the Subscriptions product, or the API not being
  enabled for this particular account. Needs a working Razorpay account
  before `sync_razorpay_plans` or the subscribe flow can be exercised live.
- `BillingWebhookView` is unverified against a live delivery for the same
  reason `PaymentWebhookView` is (§ existing note above): Razorpay refuses
  localhost URLs, ngrok unavailable. Proven only via synthetic signed
  payloads in `billing/tests.py`.
- Before production rollout: (1) resolve the Razorpay account issue, (2) run
  `sync_razorpay_plans` for real, (3) configure the platform webhook URL in
  Razorpay Dashboard -> Settings -> Webhooks pointing at
  `https://<prod-domain>/api/billing/webhook/` with
  `PLATFORM_RAZORPAY_WEBHOOK_SECRET` matching what's configured there, (4)
  do one real end-to-end subscribe+authenticate+webhook test before trusting
  this in prod.


## Super-admin origin (P3-T5/P3-T6)

- Real SSO (SAML/OIDC, e.g. against Google Workspace) was NOT implemented -
  `SuperAdmin` currently uses its own email/password login, gated by
  `PLATFORM_ADMIN_ALLOWED_IPS` (empty in dev = no IP restriction at all).
  Before production: (1) set `PLATFORM_ADMIN_ALLOWED_IPS` to the real
  office/VPN egress IP(s), (2) decide whether SSO is actually required for
  launch or whether IP-restriction + strong passwords is an acceptable v1.
- `platform_admin/permissions.py::_client_ip` reads `REMOTE_ADDR` directly.
  This breaks once a real reverse proxy/load balancer sits in front in
  production - needs `X-Forwarded-For` parsing against a trusted proxy
  list instead, or the IP allowlist will silently see the proxy's IP, not
  the real client's, and either block everyone or (worse) allow anyone
  routed through the same proxy.
- `admin.localhost` was added to dev `hosts` file and `RESERVED_HOSTS`;
  production needs `admin.platform.com` DNS + TLS provisioned (same
  wildcard-DNS/TLS deferral already noted for tenant subdomains applies
  here too).
- Tenant provisioning (`TenantListCreateView.post`) has no email delivery
  wired up for the owner's temp password - it's returned directly in the
  API response for now (fine for a super-admin operator using it
  manually; NOT fine if this ever becomes a self-serve signup flow without
  a human in the loop reading the response).