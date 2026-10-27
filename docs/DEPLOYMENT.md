# Deployment: Vercel + Railway

Do not treat example URLs as deployed services. Only record real URLs after health checks succeed. Keep provider credentials in provider environment settings, never Git or chat.

## Approved demo alternative: Render

When Railway account access is unavailable, the root `render.yaml` provisions a single **Free** Docker API in demo mode. Use an external free Neon PostgreSQL database, not local SQLite or a 30-day Render trial database. Set the exact Vercel `FRONTEND_ORIGIN`. Render Free sleeps after inactivity and has shared workspace quotas; cold starts can delay the first Vercel API request. It is not a continuous worker host. The Vercel setup below is unchanged; point `API_BASE_URL` at the actual Render API origin. No paid resources are required by the demo Blueprint.

## Budget and account prerequisites

- Vercel Hobby is intended for eligible personal/noncommercial projects; review its current terms before operating a commercial SaaS.
- Railway Free currently provides a small monthly usage credit, not an always-on API + worker + Redis + scheduler entitlement. Deploy only within your approved budget. Never automatically upgrade plans.
- PostgreSQL can be hosted externally on a free Neon project with TLS. Free quotas and availability can change.
- A public synthetic demo uses **one Railway API service**, external PostgreSQL, no Redis/worker/beat, no Clerk or AI key. It cannot run live scans.
- Live SaaS mode requires Clerk plus Railway API, worker, **one** beat scheduler, Redis and PostgreSQL. Do not advertise a live queue unless those services are running and verified.

## 1. Railway API

Connect the repository, use the repository root as the build context, and use root `railway.toml` / `Dockerfile`. The separate `backend/Dockerfile` is for Compose's backend build context.

Required environment:

| Variable | Demo | Authenticated live |
|---|---|---|
| `ENVIRONMENT` | `production` | `production` |
| `AUTH_MODE` | `demo` | `clerk` |
| `DATABASE_URL` | persistent `postgresql+psycopg://...?...sslmode=require` | same |
| `QUEUE_MODE` | `inline` | `celery` |
| `REDIS_URL` | omit | internal Redis URL or TLS external broker |
| `FRONTEND_ORIGIN` | exact HTTPS Vercel origin | exact HTTPS Vercel origin |
| `CLERK_ISSUER` | omit | exact issuer from your Clerk instance |
| `CLERK_AUDIENCE` | omit | optional if explicitly configured |
| `SCAN_LIMIT_PER_HOUR` | `10` | `10` or approved quota |
| `OPENAI_API_KEY` | omit | optional; can create usage charges |
| `OPENAI_MODEL` | omit | optional model name |

The Docker startup runs Alembic before Uvicorn, respects `$PORT`, and runs as an unprivileged user. Configure `/api/health` as readiness and generate a Railway public domain.

## 2. Vercel frontend

Import the same GitHub repository. Set the **Root Directory to `frontend`**. Next.js 15 and the lockfile are detected automatically. Configure:

- `API_BASE_URL`: the real HTTPS Railway backend origin; no trailing API path.
- `NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY`: omit for demo; configure before build for live.
- `CLERK_SECRET_KEY`: Clerk server SDK configuration for live sign-in if required by your instance; never a public-prefixed variable.
- `NEXT_PUBLIC_MAPBOX_TOKEN`: optional restricted public map token; omitted uses the keyless D3 projection.
- `NEXT_PUBLIC_DEVELOPMENT_AUTH=false` (or omit).

Next.js proxies `/api/*` server-side to the Railway origin. The browser does not need a public backend URL. Redeploy when `API_BASE_URL` changes because Next rewrites are captured at build time.

Use the resulting exact Vercel production origin for `FRONTEND_ORIGIN`, and configure Clerk's allowed frontend origins/redirects. JWT `azp` must match this origin. Development Clerk keys/instances are not a substitute for configuring a production instance and domain.

## 3. Live queue and historical monitoring

Use the same source, environment and image for API, worker and scheduler.

Worker start command:

```text
celery -A app.worker.celery_app worker --loglevel=info --concurrency=2
```

Scheduler start command:

```text
celery -A app.worker.celery_app beat --loglevel=info --schedule=/tmp/shadow-beat
```

Override/remove the API HTTP health check for worker/beat services; they do not listen on an HTTP port. Run exactly one beat instance. Keep Redis on a private network with persistence and `noeviction`. Create a test monitor and verify an actual scheduled scan appears; an API health response alone does not prove worker execution.

## 4. Release checklist

- `/api/health` returns 200 with the expected auth and queue mode.
- Vercel `/api/health` proxies to the same API.
- Homepage, graph, assets and keyless map load without console errors.
- Demo provider simulation and PDF/JSON/CSV export work.
- Demo mode rejects `/api/scans` and `/api/workspace`.
- Live mode rejects missing/expired/wrong-issuer/wrong-origin tokens.
- A scan completes; rescan records history; account B cannot retrieve account A's snapshot.
- Infrastructure state survives a service restart and a redeploy.
- Free-tier usage and spending controls are confirmed.
- Repository-linked deployments are enabled; GitHub Actions are green.

Do not mark unchecked release gates as complete.
