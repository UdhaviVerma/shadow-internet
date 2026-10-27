# Operations and release boundaries

## Data and privacy

Store domains, public DNS/HTTP/TLS evidence, provider inferences, public IP locations, job timestamps/errors and verified Clerk user IDs. Never store target passwords, website session cookies, private API keys, or target response bodies. Account isolation is enforced in API queries. Public-evidence Redis caching is shared across owners because it contains public observations only; scan records and history remain separate.

Database backups and an organization retention/deletion policy must be configured before real customer onboarding. The current 500-snapshot workspace view is a bounded query window, not automatic retention cleanup. Dormant monitors can continue creating snapshots; pause unused monitors and plan storage quotas.

## External data sources

| Source | Purpose | Limits |
|---|---|---|
| `cloudflare-dns.com/dns-query` | Public DNS and resolver AD signal | Not a global DNS-consistency measurement; DNS-over-HTTPS network access required |
| Pinned public IP, TCP 443 | TLS certificate and HEAD `/` headers | No redirects, no page body; at most two address attempts; custom origins/WAF may block |
| `stat.ripe.net` | ASN and prefix holder | Public network registration/routing metadata; not proof of origin hosting |
| `ipwho.is` | Approximate IP coordinates | Free service limits and terms apply; no SLA; locations may be unavailable |
| OpenAI (optional) | Cited analyst synthesis | Only authenticated route; provider usage charges possible; no key by default |
| Mapbox (optional) | Basemap tiles | Public token restrictions and provider quotas apply; keyless map remains available |

Service errors and missing probes must remain visible. Review provider terms/rate limits before increasing volume. The collector does not enumerate subdomains, inspect user traffic, or scan internal targets.

## Queue behavior

API writes queued jobs before publishing. Failed publication is explicitly persisted. Atomic database claim prevents duplicate workers from collecting the same job. A lost worker can leave a running row; beat marks five-minute-old queued/running jobs failed, and the status endpoint also reports stale work explicitly. This favors honest retry over silently repeating network side effects.

This is not exactly-once execution. A broker loss between persistence and publication may leave queued work until stale recovery. A transactional outbox is a future improvement. Beat advances a monitor's next run when scheduling; failed schedules are visible and do not silently retry forever.

## Observability

`/metrics` exposes request counters by route/status, latency histograms, and accepted-scan count. Labels deliberately exclude domain, user and arbitrary paths. Grafana provisions an HTTP rate/status panel, p95 latency and scan admission count. It does not claim distributed tracing, provider SLA monitoring or worker-latency instrumentation.

Error logs contain task IDs and exception types, not bearer tokens or request bodies. Follow hosting-provider log retention rules. Restrict operational metrics at the ingress if required.

## Current release gates

- Production uses PostgreSQL, never ephemeral SQLite.
- `AUTH_MODE=development` is rejected in production.
- Production live mode requires Redis/Celery and a configured HTTPS Clerk issuer.
- Run one beat scheduler; do not expose Redis or PostgreSQL publicly.
- No billing/Stripe implementation, enterprise RBAC, SSO organizations, guaranteed WAF detection, comprehensive TLS/mail auditing, or routing-path measurement.
- Optional AI needs per-user cost quotas before broad customer rollout. Current public demo cannot access it.
- Compose/image runtime and live provider deployment must be verified in the target environment; a local build alone is insufficient.

Do not market a portfolio deployment as an audited enterprise security service.
