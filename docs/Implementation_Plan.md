# Restaurant PaaS — Implementation Plan

**Version 1.0 · Companion to "Restaurant PaaS — Architecture & Design Document v1.0"**

---

## 0. How to use this document

This is the build plan. It converts the architecture (`restaurant-paas-architecture.md`) into
sequenced, verifiable work. Read the architecture document first — this plan assumes every decision
in it (§18 decision log) as fixed.

**Conventions used here:**
- **Task IDs** are stable references (e.g. `P1-T3`). Use them in issue trackers and when asking an
  LLM to expand a task into code.
- **AC** = Acceptance Criteria. A task is "done" only when all its AC are demonstrably true.
- **Dep** = hard dependencies (must be complete first).
- **DoD** = the phase-level Definition of Done gate.
- Estimates are in **relative effort (S/M/L/XL)**, not calendar time, because team size isn't fixed.
  S ≈ hours, M ≈ 1–2 days, L ≈ 3–5 days, XL ≈ 1–2 weeks for one competent engineer.

**Golden rule of sequencing:** isolation and tenancy come before any tenant feature. Never build a
tenant-scoped feature before §Phase 1 isolation is proven, or you will retrofit `tenant_id` and RLS
into working code — the most expensive mistake available here.

---

## 1. Pre-work (Phase 0 — environment & rails)

Do this before Phase 1 features. It is not optional scaffolding; several items (RLS, PgBouncer GUC)
are load-bearing for isolation.

| ID | Task | Effort | AC |
|---|---|---|---|
| P0-T1 | Repo + monorepo layout (Next.js app, Django app, shared infra dir) | S | Both apps boot locally; single `README` documents run steps |
| P0-T2 | Dockerized local stack: Postgres, Redis, Django, Next.js, Celery, mailhog | M | `docker compose up` yields a working end-to-end local environment |
| P0-T3 | Postgres + **PgBouncer** in transaction-pooling mode | M | App connects through PgBouncer; a documented hook sets a per-transaction session GUC after checkout |
| P0-T4 | CI pipeline (lint, type-check, test, build) | M | PR cannot merge unless all stages pass |
| P0-T5 | Secrets management + per-env config (local/staging/prod) | S | No secret is committed; envs load from a secret store |
| P0-T6 | Error tracking (Sentry) + structured logging with a `tenant_id` field slot | S | A thrown error appears in Sentry tagged with request + (later) tenant context |
| P0-T7 | India-region infra baseline (hosting account, object storage bucket, CDN) | M | A static asset served from CDN in-region; storage reachable from app |

**Phase 0 DoD:** a developer can clone, `docker compose up`, and hit a "hello" endpoint through
PgBouncer with logging and error tracking live; CI blocks a failing PR.

---

## 2. Phase 1 — Foundation (tenancy, isolation, auth, one template, admin editing, public site)

This is the most important phase. Its output is: a real restaurant can be created, its owner can log
in, edit whitelisted content and menu, and see a live SSR/ISR public site on a subdomain — with
proven cross-tenant isolation.

### 2.1 Tenancy & isolation (build first, in order)

| ID | Task | Effort | Dep | AC |
|---|---|---|---|---|
| P1-T1 | `Tenant` model + slug + status + `staff_account_mode` + `online_payment_enabled` | S | P0 | Tenant can be created via a management command/seed |
| P1-T2 | Request-scoped tenant context via `contextvars.ContextVar` | M | P1-T1 | Context is set per request and is async-safe; unit test proves no bleed across concurrent requests |
| P1-T3 | Tenant-resolution middleware (Host → slug → tenant) | M | P1-T2 | Unknown host → 404/routing error; known subdomain resolves the right tenant |
| P1-T4 | Tenant-scoped **default manager** + explicit `unscoped` manager | L | P1-T2 | `Model.objects.all()` returns only current-tenant rows; `unscoped` requires explicit call and is logged |
| P1-T5 | **Postgres RLS** policies on all tenant-scoped tables + GUC set on checkout | L | P0-T3, P1-T4 | With app filtering bypassed, a raw query still returns zero foreign-tenant rows |
| P1-T6 | Base abstract model: `tenant_id` FK + `(tenant_id, …)` index convention | S | P1-T1 | New tenant models inherit tenant scoping + indexing by default |
| P1-T7 | **Isolation test suite** (two-tenant, every endpoint asserts no cross-read) | L | P1-T4, P1-T5 | Suite runs in CI; deliberately introducing an unscoped query makes it fail |
| P1-T8 | CI gate wiring for isolation suite | S | P1-T7 | PR merge blocked if isolation tests fail |

> **Do not start §2.2 until P1-T7 passes.** Isolation is the foundation every later table stands on.

### 2.2 Identity, membership, RBAC

| ID | Task | Effort | Dep | AC |
|---|---|---|---|---|
| P1-T9 | `User` (global) + auth (email/phone + password), session cookies on `.platform.com` | L | P1-T3 | A user session is valid across `{slug}.platform.com` subdomains |
| P1-T10 | `Membership` (user × tenant × role) | M | P1-T9, P1-T1 | One user can hold memberships in ≥2 tenants; login resolves memberships |
| P1-T11 | RBAC enforcement layer (server-side, per request, keyed on membership role) | L | P1-T10, P1-T3 | A `staff`-role request to a pricing endpoint returns 403; matrix in arch §12 fully enforced |
| P1-T12 | Auth-tenant match guard (reject request whose tenant context ≠ membership) | M | P1-T10, P1-T3 | Authenticated user cannot act on a tenant they lack membership in (403) |
| P1-T13 | RBAC negative tests (each role × each protected module) | M | P1-T11 | Test matrix covers every cell of arch §12; CI-enforced |

### 2.3 Template engine (single template) & CMS

| ID | Task | Effort | Dep | AC |
|---|---|---|---|---|
| P1-T14 | `TemplateRegistry` + `TemplateVersion` with **capability manifest** schema | L | P1-T6 | One template registered at a pinned version with a manifest listing sections, editable fields, theme tokens |
| P1-T15 | CMS content models: `SiteConfig`, `Page`, `Section/Block`, `MediaAsset` | L | P1-T14 | Content stored separately from presentation; a tenant's content is queryable independent of template |
| P1-T16 | First React template package implementing the section contract | XL | P1-T14 | Template renders landing + menu + contact from a content+theme payload |
| P1-T17 | Whitelisted edit-field resolution (admin reads manifest → renders only allowed controls) | L | P1-T14, P1-T15 | Owner can edit only manifest-declared fields; a non-whitelisted field is not editable via API (403) |
| P1-T18 | Media upload → object storage + CDN URL + thumbnailing (Celery) | M | P0-T7 | Uploaded image is stored, thumbnailed async, served via CDN, scoped to tenant |

### 2.4 Menu management (admin)

| ID | Task | Effort | Dep | AC |
|---|---|---|---|---|
| P1-T19 | `MenuCategory`, `MenuItem` (with `is_available`) CRUD API + admin UI | L | P1-T11, P1-T15 | Owner/manager can CRUD; `staff` cannot (403); items scoped to tenant |
| P1-T20 | Menu render on public site | M | P1-T16, P1-T19 | Public menu page reflects current menu; unavailable items handled per template |

*(Modifiers are deferred to Phase 2 with ordering — see P2-T2.)*

### 2.5 Public site rendering & tenant resolution

| ID | Task | Effort | Dep | AC |
|---|---|---|---|---|
| P1-T21 | Wildcard subdomain DNS + wildcard TLS via managed edge | M | P0-T7 | `{slug}.platform.com` serves the correct tenant's site |
| P1-T22 | Next.js middleware: Host → slug → render path rewrite | M | P1-T21, P1-T3 | Correct tenant site renders; unknown slug → 404 |
| P1-T23 | SSR/ISR rendering of public pages | L | P1-T16, P1-T22 | Public pages are server-rendered/cached; Lighthouse SEO + mobile pass a set threshold |
| P1-T24 | **On-demand ISR revalidation** triggered by admin edits (via Celery) | L | P1-T15, P1-T23 | Editing content revalidates only that tenant's affected pages; anonymous traffic served from cache otherwise |

### 2.6 Admin shell

| ID | Task | Effort | Dep | AC |
|---|---|---|---|---|
| P1-T25 | Admin app at `{slug}.platform.com/manage`, branded per tenant, RBAC-aware nav | L | P1-T11, P1-T22 | Admin is origin-isolated from public custom domains; nav reflects role; branding pulls from tenant |

**Phase 1 DoD (all must hold):**
1. Isolation suite (P1-T7) and RBAC matrix (P1-T13) green in CI.
2. A seeded restaurant has a live SSR/ISR site on its subdomain.
3. Its owner can log in, edit whitelisted content + branding + menu, and see changes live within
   seconds via ISR revalidation.
4. A `staff`-role account is confined to nothing beyond what §12 allows.
5. No tenant can read another tenant's data through any endpoint or raw query.

---

## 3. Phase 2 — Ordering (QR, cart, order lifecycle, payment choice, live orders, staff modes)

Output: diners can order via a table QR or online, choose to pay now (restaurant's Razorpay) or at
the counter, and the kitchen sees orders live via polling.

### 3.1 Tables & QR

| ID | Task | Effort | Dep | AC |
|---|---|---|---|---|
| P2-T1 | `Table` model + unguessable rotatable `table_token`; QR generation in admin | M | P1-T19 | Owner creates tables and downloads/prints per-table QR; token rotation invalidates old QR |

### 3.2 Menu completion & cart

| ID | Task | Effort | Dep | AC |
|---|---|---|---|---|
| P2-T2 | `ModifierGroup` + `Modifier` (min/max select) + admin UI | L | P1-T19 | Items can carry modifier groups with selection rules; enforced at order time |
| P2-T3 | Cart (client + server validation, price computed server-side) | L | P2-T2 | Prices/totals computed server-side (client cannot tamper); modifier rules enforced |

### 3.3 Order lifecycle

| ID | Task | Effort | Dep | AC |
|---|---|---|---|---|
| P2-T4 | `Order` + `OrderItem` with **price/name snapshotting** | L | P2-T3 | Later menu edits never mutate historical orders |
| P2-T5 | `order_type` resolution from QR context (token → dine_in; none → takeaway/online) | M | P2-T1, P2-T4 | Valid table token → dine_in + table_id; no token → takeaway/online with address field |
| P2-T6 | Order **state machine** + `OrderEvent` audit on every transition | L | P2-T4 | Transitions follow arch §8.3; each writes an event with actor + timestamp; illegal transitions rejected |

### 3.4 Payments (customer-facing, restaurant's own gateway)

| ID | Task | Effort | Dep | AC |
|---|---|---|---|---|
| P2-T7 | `RazorpayConnection` (OAuth/Partner preferred; encrypted key fallback) + connect flow in admin | XL | P1-T25 | Owner connects the restaurant's Razorpay account; `online_payment_enabled` flips true; tokens stored encrypted |
| P2-T8 | Checkout payment choice: Pay now vs Pay at counter (Pay now shown only if connected) | L | P2-T6, P2-T7 | Customer sees both options iff connected; pay-at-counter always available; `payment_mode` recorded |
| P2-T9 | `Payment` create on restaurant's account + **webhook confirmation** (idempotent) | L | P2-T7, P2-T8 | Success recognized only via webhook; duplicate webhooks are no-ops; platform never holds/splits funds |
| P2-T10 | Refund path (restaurant's own Razorpay transaction) | M | P2-T9 | Refund issued on restaurant's account; order → refunded; event logged |

> **Confirm Razorpay Partner/OAuth mechanics before starting P2-T7** (arch §17 item 1). If OAuth
> connect isn't available as assumed, fall back to encrypted per-tenant keys and adjust P2-T7 UX.

### 3.5 Live orders (KDS) via polling

| ID | Task | Effort | Dep | AC |
|---|---|---|---|---|
| P2-T11 | "Orders changed since timestamp X" endpoint (cached, `(tenant_id, updated_at)`-indexed) | M | P2-T6 | Returns only new/changed orders for the tenant since a cursor; efficient under repeated polling |
| P2-T12 | KDS UI (poll 3–5s, new-order alert, status action buttons) | L | P2-T11, P1-T25 | Kitchen sees new orders within ~5s; can advance state; actions respect RBAC |
| P2-T13 | Mark paid-at-counter action | S | P2-T12, P2-T8 | Staff can mark a pay-at-counter order paid; event logged with actor |

### 3.6 Staff account modes

| ID | Task | Effort | Dep | AC |
|---|---|---|---|---|
| P2-T14 | `staff_account_mode` toggle + auto-provisioned shared `staff` login | M | P1-T10, P1-T11 | Default shared login exists per tenant; scoped to live-orders only |
| P2-T15 | Individual-account invite flow (opt-in mode) | L | P2-T14 | Owner invites staff; each gets own `staff` membership; `OrderEvent.actor` now names individuals |
| P2-T16 | Mode-switch semantics (future logins only; history keeps original actor) | S | P2-T15 | Switching modes never re-attributes past events |

**Phase 2 DoD:**
1. A diner scans a table QR, builds a cart, and places a dine-in order that appears on the KDS within ~5s.
2. Customer can choose Pay now (restaurant's Razorpay) or Pay at counter; a restaurant with no
   connection can still take pay-at-counter orders.
3. Online payment success is webhook-confirmed and idempotent; refunds work.
4. Order history is immutable to later menu edits (snapshots).
5. A restaurant can run shared or individual staff accounts, with the audit trail behaving per §11.

---

## 4. Phase 3 — Platform business (plans, SaaS billing, gating, super-admin)

Output: the platform can charge restaurants, gate features by plan, and be operated by super-admins.

| ID | Task | Effort | Dep | AC |
|---|---|---|---|---|
| P3-T1 | `Plan` model + `feature_limits` (template count, custom domain, blog, max menu items…) | M | P1 | Plans defined with machine-readable limits |
| P3-T2 | `Subscription` + **Razorpay Subscriptions** (UPI Autopay / e-mandate) | XL | P3-T1, P2-T7 infra | Restaurant subscribes; recurring mandate set up; status synced via webhook |
| P3-T3 | Subscription lifecycle: activation, renewal, failure/dunning, suspension | L | P3-T2 | Failed payment triggers dunning; unpaid tenant transitions to suspended per policy |
| P3-T4 | **Feature gating** enforced off active plan | L | P3-T1, P3-T3 | Exceeding a plan limit (e.g. extra menu items, custom domain) is blocked server-side |
| P3-T5 | `SuperAdmin` identity + `admin.platform.com` origin (IP-restricted/SSO) | L | P0 | Super-admin origin is isolated and access-controlled |
| P3-T6 | Super-admin: tenant lifecycle (create/suspend/inspect) | L | P3-T5 | Operator can provision and suspend tenants; actions audited |
| P3-T7 | Super-admin: plan & billing oversight | M | P3-T5, P3-T2 | Operator views subscription status across tenants |
| P3-T8 | Super-admin: template registry management (publish templates/versions/manifests) | L | P1-T14, P3-T5 | Operator publishes a template version without touching live-site pins |
| P3-T9 | Super-admin cross-tenant metrics via audited `unscoped` path | M | P1-T4, P3-T5 | Cross-tenant reads are possible only through the logged `unscoped` manager |

**Phase 3 DoD:**
1. A restaurant can self-subscribe to a plan via e-mandate; renewals and failures are handled.
2. Feature access matches the active plan, enforced server-side.
3. Super-admins can provision/suspend tenants, oversee billing, and manage the template registry from
   an isolated origin, with cross-tenant access audited.

---

## 5. Phase 4 — Expansion (multi-template + versioning, custom domains, blog, realtime upgrade, delivery)

Each item here is independently triggerable; none blocks Phase 3 launch.

| ID | Task | Effort | Dep | AC |
|---|---|---|---|---|
| P4-T1 | Second & third templates against the section contract | XL | P1-T16 | New templates render existing tenant content with no content migration |
| P4-T2 | **Template versioning + owner-initiated upgrades** | L | P1-T14, P4-T1 | Publishing a new version never mutates pinned live sites; owner opts in to upgrade |
| P4-T3 | Template switch flow (content preserved across templates) | L | P4-T2 | Owner switches template; all content re-renders; nothing lost |
| P4-T4 | `Domain` custom-domain add + DNS verification + automated TLS via edge API | L | P1-T21, P3-T4 | Verified custom domain serves the tenant's public site with valid TLS; admin never served on it |
| P4-T5 | Blog (`BlogPost`) admin + public rendering | M | P1-T15, P1-T23 | Owner publishes posts; public blog renders and is cached/revalidated |
| P4-T6 | **Realtime upgrade to Channels + Redis WebSockets** *(only if a §10 trigger fires)* | XL | P2-T12 | Two-way/low-latency KDS works over WebSockets; falls back gracefully; polling retired only after parity |
| P4-T7 | `FulfillmentProvider` integration(s) — Pidge/Porter/Shadowfax *(only if delivery pursued)* | XL | P2-T6 | An online order can be dispatched via a provider through the existing fulfillment seam without changing order logic |

**Phase 4 DoD:** feature-by-feature — each shipped item meets its AC; no phase-wide gate, since these
are triggered by business need, not sequence.

---

## 6. Cross-cutting workstreams (run continuously, all phases)

| Stream | What | Cadence |
|---|---|---|
| **Isolation integrity** | Every new tenant-scoped table gets `tenant_id` + RLS + isolation test in the same PR | Every PR |
| **Security** | Encrypted secrets/tokens, webhook signature verification, rate limits, dependency scanning | Every phase |
| **Observability** | `tenant_id`-tagged logs, per-tenant error/latency dashboards, alerting | From P0-T6 onward |
| **Testing** | Unit + integration + isolation + RBAC negative tests; e2e for order + payment happy paths | Every PR / phase gate |
| **Performance** | Composite indexes `(tenant_id, …)`; keep `orders`/`order_events` partition-ready; CDN cache hit-rate watch | Reviewed each phase |
| **Docs** | Keep architecture §18 decision log current; log any new decision here as it's made | On each decision |

---

## 7. Critical path & recommended sequencing

The dependency spine that everything else hangs off:


P0 (env + PgBouncer GUC)
→ P1-T1..T8 (tenancy + RLS + isolation gate)   ← hard gate, do not skip ahead
→ P1-T9..T13 (auth + membership + RBAC)
→ P1-T14..T18 (template engine + CMS)
→ P1-T19..T20 (menu)  +  P1-T21..T25 (public render + admin shell)
→ PHASE 1 DoD
→ P2 ordering (QR → cart → order machine → payments → KDS → staff modes)
→ PHASE 2 DoD
→ P3 (plans → Razorpay Subscriptions → gating → super-admin)
→ PHASE 3 DoD  ← minimum commercially operable product
→ P4 (templates/versioning, custom domains, blog, realtime, delivery — as triggered)
Unknown
**Parallelization opportunities** (once P1-T8 isolation gate passes):
- Template/CMS (P1-T14–T18) and public rendering setup (P1-T21–T23) can proceed in parallel with menu
  work (P1-T19).
- In Phase 2, tables/QR (P2-T1) and modifiers/cart (P2-T2–T3) can run in parallel before converging at
  the order machine (P2-T4–T6).
- The Razorpay connect track (P2-T7) can start early (spike/POC) since it has the most external
  uncertainty — de-risk it first.

**Minimum commercially operable product = end of Phase 3.** Phases 1–2 alone don't monetize; Phase 4
items are demand-triggered, not prerequisites.

---

## 8. Milestone gates (what "ready to demo/ship" means)

| Milestone | Gate condition |
|---|---|
| **M1 — Isolation proven** | P1-T7 + P1-T8 green; a two-tenant breach attempt returns zero rows |
| **M2 — First live site** | A seeded restaurant edits content/menu and sees it live via ISR (Phase 1 DoD) |
| **M3 — First real order** | A QR dine-in order reaches the KDS and can be paid at counter (Phase 2, pre-payment) |
| **M4 — Online payments live** | Webhook-confirmed online payment on a restaurant's own Razorpay (P2-T9) |
| **M5 — Monetized** | A restaurant self-subscribes via e-mandate; gating enforced (Phase 3 DoD) |
| **M6 — Operable at scale of "a few → hundreds"** | Super-admin can run the estate; observability + rate limits live |

---

## 9. Early de-risking spikes (do these before their phase, in parallel with Phase 1)

1. **Razorpay Partner/OAuth spike** — confirm the actual connect mechanism and settlement model.
   Highest external uncertainty; gates P2-T7 design. *(Arch §17.1.)*
2. **RLS + PgBouncer GUC spike** — prove the session GUC is correctly set per transaction under
   transaction pooling. If this is wrong, isolation layer 3 silently fails. Gates P1-T5.
3. **ISR on-demand revalidation spike** — confirm per-tenant page revalidation works on the chosen
   edge/host at expected latency. Gates P1-T24.

Running these three spikes during Phase 1 removes the three biggest "find out late" risks.

---

## 10. Open items feeding the plan (from architecture §17)

| Item | Blocks | Action |
|---|---|---|
| Razorpay Partner/OAuth capability | P2-T7 | Spike #1; confirm with Razorpay before building connect UX |
| India incorporation | P3-T2 (mandate/UPI Autopay), payment posture | Confirm entity before billing build |
| Mandatory vs guest customer accounts | Public order flow, P2-T5 | Decide before Phase 2 checkout UX freeze |
| Custom domains as paid feature | P4-T4, plan limits P3-T1 | Confirm tier placement in Phase 3 plan design |
| Delivery pursuit | P4-T7 | Decide only when delivery is on the roadmap |

---

*End of document.*