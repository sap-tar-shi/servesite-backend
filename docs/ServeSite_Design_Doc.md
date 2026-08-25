# Restaurant PaaS — Architecture & Design Document

**Version 1.0 · India-first · Status: design complete, pre-build**

---

## 0. Context for continuation (read first)

This document is the authoritative design reference for a multi-tenant SaaS platform
that lets restaurant owners launch customizable websites with QR-based dine-in and
online ordering. It was produced through an iterative design discussion and consolidates
every decision made.

**If you are an LLM or collaborator picking this up:** all major architectural forks are
already resolved (multi-tenancy model, template system, payments, realtime, staff model,
edge/TLS, scale posture). Do not re-litigate settled decisions unless new constraints are
introduced. Open items awaiting confirmation are listed in §17. The natural next steps are
(a) expanding §7 into a full field-level data-model spec, or (b) a Phase 1 implementation plan.

**Fixed constraints:**
- Stack: **Next.js** (frontend) + **Django/DRF** (backend) + **PostgreSQL** + **Redis** + **Celery**.
- Jurisdiction: **India first**. Assume India incorporation and India data-localization.
- Revenue: **SaaS subscription only** — no per-order commission.
- Primary use case: **QR-based dine-in ordering**; online/takeaway supported; delivery deferred.

---

## 1. Product summary

A multi-tenant SaaS platform where restaurant owners select a fixed, well-designed website
template, apply bounded customizations (name, images, menu, blog, branding), and get a live
restaurant website on a dedicated URL. Each site supports **QR-based dine-in ordering** (the
primary use case) plus **online/takeaway ordering**, with customers choosing to pay online
(via the restaurant's own gateway) or at the counter. Owners and staff manage the site and
live orders through a branded admin; platform super-admins manage tenants, plans, billing,
and templates.

**Revenue model:** SaaS subscription from restaurants to the platform. No per-order commission.

---

## 2. Architecture principles

1. **Isolation is structural, not discretionary.** Cross-tenant separation is enforced at four
   independent layers, so a single coding mistake cannot leak data.
2. **The platform never holds order money.** Diners pay restaurants directly on the restaurants'
   own Razorpay accounts. The platform only bills restaurants for subscriptions.
3. **Content is separate from presentation.** A restaurant's data is portable across templates.
   Switching or upgrading a template never destroys content.
4. **Build for hundreds, design so thousands is an ops change, not a rewrite.** No premature
   sharding or microservices; but isolation, indexing, and partition-friendliness are done from
   day one because they are expensive to retrofit.
5. **Hard origin boundaries between surfaces.** Public sites, admin, and super-admin are separated
   at the origin level to contain blast radius.
6. **Prefer the simplest mechanism that fully works.** Polling before WebSockets; managed edge
   before self-hosted TLS; a toggle before a second architecture.

---

## 3. System topology

### 3.1 Surfaces

| Surface | Host | Rendering | Auth | Who |
|---|---|---|---|---|
| Marketing / signup | `platform.com` | Static | none | Prospective owners |
| Public restaurant site | `{slug}.platform.com` + custom domains | SSR / ISR, cached | Anonymous (+ optional customer accounts) | Diners |
| Owner/staff admin | `{slug}.platform.com/manage` | Authenticated, dynamic | Tenant users, RBAC | Owners, managers, staff |
| Platform super-admin | `admin.platform.com` (IP-restricted / SSO) | Authenticated | Super-admins only | Platform operators |

**Rationale for `{slug}.platform.com/manage`:** auth cookies live on `.platform.com` (one session
across a multi-restaurant owner's restaurants); the admin origin is isolated from the public custom
domain (XSS on a public site can't reach admin tokens); and public ISR caching doesn't collide with
authenticated admin traffic. The admin is white-labeled with the restaurant's branding so it *feels*
like theirs — but it is one shared application, tenant-aware after login. Admin is **never** served
on a restaurant's customer-facing custom domain.

### 3.2 High-level component map

- **Next.js frontend** (one codebase): public site renderer, admin app, super-admin app, marketing.
- **Django + DRF backend**: single API and business-logic tier for all surfaces.
- **PostgreSQL**: single primary, shared-DB multi-tenant, RLS-enforced. PgBouncer in front. Read
  replicas added when reporting load demands.
- **Redis**: cache, Celery broker, (later) Channels layer.
- **Celery workers**: async/background work.
- **Object storage (S3-compatible) + CDN**: all media.
- **Managed edge**: wildcard subdomain + custom-domain TLS provisioning.
- **External services**: Razorpay (subscriptions + restaurants' own gateways), transactional
  email/SMS/WhatsApp provider.

---

## 4. Multi-tenancy & isolation

**Model:** shared database, row-level isolation via a `tenant_id` foreign key on every tenant-scoped
table. Schema-per-tenant is explicitly rejected (per-schema migrations at thousands of tenants and
cross-tenant admin analytics make it the wrong fit).

**Four defense layers:**

1. **Tenant-scoped default manager.** The default model manager auto-filters by the current
   `tenant_id`, read from a request-scoped context variable. Crossing tenants requires an explicit,
   auditable `unscoped` manager — opt-out, not opt-in.
2. **Middleware sets tenant context.** Resolves tenant from the request host, stores it in an
   async-safe `contextvars.ContextVar`. Rejects any authenticated request whose tenant context
   doesn't match the user's membership.
3. **PostgreSQL Row-Level Security.** A session GUC (`app.current_tenant`) is set on connection
   checkout; RLS policies on every tenant-scoped table return zero rows if a query is ever unscoped.
   This backstop turns a "forgotten filter" from a breach into a no-op. Requires setting the GUC
   after each PgBouncer checkout (per-transaction).
4. **Isolation tests as a CI gate.** Automated tests create two tenants and assert tenant A can
   never read tenant B's rows across every endpoint. Merge is blocked if isolation fails.

**Indexing rule:** `tenant_id` leads every composite index (`(tenant_id, created_at)`,
`(tenant_id, status)`, etc.).

**Partition-friendliness:** `orders` and `order_events` are designed for time-based partitioning
from the start, so high-volume tables never require a scary migration later.

---

## 5. Tenant resolution & edge

**Subdomains** (`{slug}.platform.com`): one wildcard DNS record + wildcard TLS cert. Next.js
middleware reads the `Host` header, extracts the slug, resolves the tenant, and rewrites to the
correct render path.

**Custom domains** (paid tiers): a `Domain` entity maps hostname → tenant with a verification flow
(owner adds a DNS record; platform verifies before activation).

**Edge/TLS recommendation:** use a **managed edge with a custom-domains API** (Vercel-style) so
certificate provisioning for `joes-diner.com` is an API call, not hand-rolled ACME. Django stays on
your own India-region infra behind it. Migrate to self-hosted **Caddy on-demand TLS** later only if
edge cost becomes material.

**Region:** host in an India region for latency and to keep payment data in-country.

---

## 6. Template & CMS system

Core principle that makes the template library expandable: **separate Content, Structure, and
Presentation.**

- **Content** (tenant data in Postgres): name, description, hours, address, menu, photos, blog.
  Portable across templates.
- **Structure** (which pages/sections exist): constrained by the chosen template's capabilities.
  Rearranging is out of scope — no page builder.
- **Presentation** (template + theme tokens): selected template + version, plus a bounded
  `theme_config` (brand colors within a palette, logo, font pairing, hero image).

Because content is separate, switching or upgrading a template re-renders the same content —
nothing is lost.

**Templates are code, not data.** Each template is a React component package implementing a common
contract: a defined set of typed sections that accept a content + theme payload. A template is a
*renderer for a standard content schema*, not a bespoke site.

**Template Registry** (DB-backed, managed from super-admin): template id, display name, version,
preview image, and a **capability manifest** (which sections/features it supports, which theme
tokens and editable fields it exposes). The owner admin reads the registry to render the picker and
the correct set of edit controls.

**Versioning is mandatory.** Live sites are pinned to a specific version (e.g. `A@1.2.0`). Publishing
`A@2.0.0` never silently mutates live sites; owners opt into upgrades. Designed in before template #2.

**Editable = whitelisted.** Each template declares exactly which fields an owner may edit. This keeps
"minor edits" bounded and prevents scope creep into a builder. Start narrow.

**Rendering:** public sites are **SSR/ISR** for SEO and mobile speed. On owner edits, the admin
triggers **on-demand ISR revalidation** for just that tenant's affected pages, so edits appear
near-instantly while anonymous traffic is served from cache.

---

## 7. Complete entity model

Every tenant-scoped entity carries `tenant_id`, is covered by RLS, and leads its indexes with
`tenant_id`.

### 7.1 Platform & tenancy
- **Tenant** — `id`, `slug`, `name`, `status` (active/suspended/trial), `staff_account_mode`
  (shared/individual), `online_payment_enabled`, timestamps.
- **Plan** — `id`, `name`, `price`, `billing_interval`, `feature_limits` (JSON: template count,
  custom-domain allowed, blog allowed, max menu items, etc.).
- **Subscription** — `tenant_id`, `plan_id`, `status`, `razorpay_subscription_id`,
  `current_period_end`, `mandate_status`. *(Platform-billing only — money restaurants pay you.)*
- **Domain** — `tenant_id`, `hostname`, `type` (subdomain/custom), `verification_status`, `tls_status`.
- **RazorpayConnection** — `tenant_id`, `connection_type` (oauth/api_key), encrypted token reference,
  `status`, `connected_at`. *(The restaurant's own gateway — platform never holds these funds.)*
- **FeatureFlag** — optional per-tenant overrides.

### 7.2 Templates
- **TemplateRegistry** — `id`, `name`, `preview_image`, `status`.
- **TemplateVersion** — `template_id`, `version`, `capability_manifest` (JSON: sections, editable
  fields, theme tokens), `changelog`, `published_at`.

### 7.3 Identity & access
- **User** — `id`, `email`/`phone`, `password_hash`, global attributes only. Not tied to one tenant.
- **Membership** — `user_id`, `tenant_id`, `role` (`owner`/`manager`/`kitchen`/`waiter`/`staff`).
  Enables multi-restaurant owners and the shared-vs-individual staff toggle. Permissions attach here,
  never to the user globally.
- **SuperAdmin** — separate privileged identity for `admin.platform.com`.

### 7.4 Site / CMS
- **SiteConfig** — `tenant_id`, `template_id`, `template_version`, `theme_config` (JSON), `status`.
- **Page** — `tenant_id`, `type` (landing/menu/blog/contact), `enabled`, `seo_meta`.
- **Section / Block** — `page_id`, `type`, `ordered_position`, typed `content` (JSON), constrained
  to the template's manifest.
- **MediaAsset** — `tenant_id`, storage key, `type`, dimensions. Served via CDN.
- **BlogPost** — `tenant_id`, `title`, `body`, `status`, `published_at`.

### 7.5 Menu
- **MenuCategory** — `tenant_id`, `name`, `ordered_position`, `visible`.
- **MenuItem** — `tenant_id`, `category_id`, `name`, `description`, `price`, `image`,
  `is_available` (86-ing toggle).
- **ModifierGroup** — `tenant_id`, `item_id` (or reusable), `name`, `min/max_select`.
- **Modifier** — `group_id`, `name`, `price_delta`.

### 7.6 Tables & ordering
- **Table** — `tenant_id`, `label`, `table_token` (unguessable, rotatable). QR encodes the token.
- **Order** — `tenant_id`, `order_type` (`dine_in`/`takeaway`/`online`), `table_id` (nullable),
  `payment_mode` (`prepaid`/`pay_at_counter`), `status`, `customer_ref` (nullable),
  `delivery_address` (free-text, nullable), totals.
- **OrderItem** — `order_id`, `menu_item_id`, **snapshotted** `name` + `price`, selected modifiers
  snapshot, quantity. (Snapshots so historical orders don't mutate when the menu changes.)
- **Payment** — `order_id`, `provider_ref` (restaurant's Razorpay payment id), `status`, `amount`.
  Confirmed via webhook, never client-reported.
- **OrderEvent** — `order_id`, `from_status`, `to_status`, `actor` (acting `Membership` or shared
  staff account), `timestamp`. Audit trail that gains granularity when a tenant switches to
  individual staff accounts.

### 7.7 Fulfillment (seam only, no build)
- **FulfillmentProvider** interface — an extension point the order state machine can call. **No
  provider integrations built in v1.** Online orders carry an address; the restaurant marks them
  fulfilled manually.

---

## 8. Ordering subsystem

### 8.1 QR flow
The QR encodes `{site}/order?table={table_token}`. A valid token → **dine-in mode** (order tied to a
table, no address). Absence → **takeaway/online mode**. One codebase, one order pipeline, a context flag.

### 8.2 Payment choice at checkout
Customer chooses:
- **Pay now** → via the restaurant's own Razorpay gateway (shown only if `online_payment_enabled`).
- **Pay at counter** → always available; the order flows to the kitchen regardless.

A restaurant can go live with **zero payment integration** (pay-at-counter only) and switch on online
payment once it connects Razorpay — without blocking launch. `payment_mode` records the customer's
actual choice.

### 8.3 State machine
`cart → placed → (accepted → preparing → ready) → served / handed_over → completed`, with `paid`
inserted where relevant (mandatory on prepaid, deferred to counter otherwise), plus `cancelled` and
`refunded`. Every transition writes an `OrderEvent` with actor and timestamp.

---

## 9. Payments

Two cleanly separated systems; the platform **operates only the first**.

| Flow | Merchant | Mechanism | Platform's role |
|---|---|---|---|
| Restaurant → Platform (SaaS subscription) | Platform | **Razorpay Subscriptions** (UPI Autopay / e-mandate) | Fully operated: plan tiers, e-mandate, feature gating, dunning |
| Diner → Restaurant (food order) | The restaurant | Restaurant's **own** Razorpay account, connected via **OAuth/Partner** (preferred) or encrypted per-tenant keys (fallback) | Facilitate only — never holds or splits funds |

**Why this shape:** subscription-only revenue means the platform never takes an order cut, so it never
sits in the order money path. That removes the RBI Payment-Aggregator burden entirely — no escrow, no
sub-merchant KYC obligation, no split-settlement reconciliation. Each restaurant's KYC is between it
and Razorpay.

**Guardrails:** UPI is a first-class method; webhooks are idempotent; payment success is confirmed via
webhook only; refunds are the restaurant's own Razorpay transaction.

> **To confirm before build:** current Razorpay Partner/OAuth onboarding mechanics — those capabilities
> shift; verify directly with Razorpay before finalizing the connection UX.

---

## 10. Realtime (live orders / KDS)

**v1: short polling (3–5s).** The KDS calls an "orders changed since timestamp X?" endpoint — cached,
`tenant_id`-indexed. No ASGI, no held connections, no channel layer, no reconnection logic. A 3–5s
new-order delay is invisible in a kitchen. Lowest-risk approach that fully works and requires no infra
detour.

**Migrate to Django Channels + Redis WebSockets (skipping SSE)** when a concrete trigger appears:
genuine two-way interaction (waiter app, live table map), order volumes where polling latency hurts,
or polling request cost becoming material. By then Redis is already running (cache/Celery), so the
channel layer is a small addition. SSE is skipped deliberately — it fits neither stage best for this
product.

---

## 11. Staff account model (shared vs individual)

One data model, one per-tenant toggle — not two architectures.

- **`staff_account_mode` on Tenant**, owner-controlled in admin.
- **Shared mode (default):** one auto-provisioned `staff`-role login per tenant; zero setup. The KDS
  tablet stays logged in.
- **Individual mode (opt-in):** owner invites each staff member; each gets their own `staff`-role
  `Membership`.

**Both modes are identical in permission scope** — the `staff` role reaches only the live-orders
module, never customization, menu pricing, billing, or staff management. Switching modes changes *how
many logins exist*, never *what they can do*.

**Audit degrades gracefully:** `OrderEvent.actor` records the shared account in shared mode and real
people in individual mode — same schema, more granularity when switched. Switching affects only future
logins; historical events keep their original actor.

---

## 12. RBAC (permission matrix)

Enforced **server-side on every API call**, keyed off `Membership.role` for the tenant in context. The
frontend hides controls; the API is the enforcement point (a crafted request from a `staff` role
hitting a pricing endpoint must return 403).

| Module | owner | manager | staff (kitchen/waiter) |
|---|---|---|---|
| Site customization (name, images, blog, theme) | ✅ | optional | ❌ |
| Menu management (items, prices, 86-ing) | ✅ | ✅ | ❌ |
| Live orders / KDS | ✅ | ✅ | ✅ |
| Billing, plan, staff management, domain setup | ✅ | ❌ | ❌ |

Super-admin is a separate identity on a separate, IP-restricted origin.

---

## 13. API surface (by surface)

**Public site API** (anonymous, cached where possible):
- Read site config + rendered content for a resolved tenant/domain.
- Read menu (categories, items, modifiers, availability).
- Create order (dine-in via table token / takeaway / online).
- Initiate payment (restaurant's Razorpay) or select pay-at-counter.
- Read blog posts.
- Optional customer account: order history.

**Admin API** (authenticated, RBAC-gated, tenant-scoped):
- Site customization: read/update whitelisted content fields, theme config, media upload → triggers
  ISR revalidation.
- Menu management: CRUD categories/items/modifiers, availability toggles.
- Live orders: list/stream (poll), transition order state, mark paid-at-counter.
- Table management: create tables, generate/rotate QR tokens.
- Staff: mode toggle, invite/manage individual accounts (owner only).
- Billing: view plan, manage subscription/mandate, connect Razorpay.
- Domains: add/verify custom domain.

**Super-admin API** (super-admins only, isolated origin):
- Tenant lifecycle: create, suspend, inspect.
- Plans & billing oversight.
- Template registry: publish templates/versions, manage capability manifests.
- Cross-tenant operational metrics (uses the `unscoped` manager path, audited).

---

## 14. Async, infrastructure & observability

- **Redis:** cache, Celery broker, later Channels layer.
- **Celery** handles everything slow or external: transactional email/SMS/WhatsApp; image
  processing/thumbnailing; Razorpay webhook side-effects; ISR revalidation fan-out; periodic reports.
- **Object storage + CDN** for all media — Django never serves user images.
- **Caching posture:** anonymous public traffic served from ISR/CDN; DB load dominated by
  admin/dashboard and order writes.
- **Observability from day one:** structured logs tagged with `tenant_id`; error tracking (Sentry);
  per-tenant metrics.
- **Noisy-neighbor control:** CDN caching absorbs most public spikes; per-tenant API rate limits
  handle the rest.
- **Scaling levers (add when numbers demand, not now):** PgBouncer (from early on), read replicas for
  reporting, more Celery/API workers, table partitioning on `orders`/`order_events`.

---

## 15. Phased build plan

**Phase 1 — Foundation**
Tenant model + full four-layer isolation; auth + `Membership`/RBAC; one template with fixed content
schema; owner admin for menu + whitelisted text/branding edits; subdomains only; SSR/ISR public site
with on-demand revalidation.

**Phase 2 — Ordering**
Menu + modifiers; per-table QR (table tokens); cart; order state machine; dine-in + takeaway/online
order types; customer payment choice (Pay now via restaurant's Razorpay / Pay at counter); live-order
view via **polling**; shared/individual staff toggle.

**Phase 3 — Platform business**
Plans; **Razorpay Subscriptions** (e-mandate) for SaaS billing; feature gating off active plan;
super-admin portal (tenant / plan / template management).

**Phase 4 — Expansion**
Second and third templates + **template versioning**; custom domains + automated TLS; blog; realtime
upgrade to Channels + WebSockets *if* triggered; `FulfillmentProvider` integrations
(Pidge/Porter/Shadowfax) *if/when* delivery is pursued.

---

## 16. Top risks & mitigations

| Risk | Severity | Mitigation |
|---|---|---|
| Cross-tenant data leak | Breach-level | Four-layer isolation (§4) + CI isolation tests |
| Template refactor breaks live sites | High | Version pinning before template #2 (§6) |
| Scope creep in "minor edits" → builder | High | Whitelisted editable fields per template (§6) |
| Custom-domain TLS ops | Medium | Managed edge with custom-domains API (§5) |
| Payment/regulatory (India) | High | Subscription-only + restaurants' own Razorpay accounts → platform never holds funds (§9); confirm Razorpay Partner mechanics before build |
| Menu schema churn | Medium | Modifiers + price-snapshotting designed up front (§7.5–7.6) |
| Premature scaling effort | Medium | Build for hundreds; scaling is drop-in infra (§14) |

---

## 17. Assumptions & items to confirm before build

1. **Razorpay Partner/OAuth onboarding** — confirm current capabilities directly with Razorpay; the
   connection UX depends on it.
2. **India incorporation** — assumed; locks in the Razorpay/PA-free path and India data-localization.
   Foreign parent entity is out of scope for now.
3. **Custom domains** — assumed a paid-tier, Phase-4 feature, not MVP-critical.
4. **Delivery** — assumed design-seam only; restaurants self-fulfill; no provider integration in v1.
5. **Customer accounts** — assumed optional/guest-first for ordering; confirm whether mandatory
   customer login is wanted anywhere.

---

## 18. Decision log (settled — do not re-litigate without new constraints)

- Multi-tenancy: **shared-DB + `tenant_id` + RLS + scoped manager + middleware** (not schema-per-tenant).
- Templates: **fixed, versioned templates + whitelisted bounded customization** (not a page builder).
- Surfaces: public sites, **branded admin at `{slug}.platform.com/manage`**, separate super-admin —
  hard origin boundaries.
- Payments: **platform operates Razorpay Subscriptions only**; order money runs on each restaurant's
  **own** Razorpay account; platform never holds/splits funds.
- Ordering: per-table QR (tokens); customer-chosen `payment_mode` with pay-at-counter always available.
- Staff: per-tenant `staff_account_mode` (shared/individual); single `staff` role scoped to live orders;
  full `Membership` model retained.
- Realtime: **polling for v1**; Channels + WebSockets later (skip SSE).
- Edge: **managed edge / custom-domains API** first; self-hosted Caddy on-demand TLS later.
- Scale: build for hundreds, launch to a few; scaling is drop-in infra, not a rewrite.

---

*End of document.*
