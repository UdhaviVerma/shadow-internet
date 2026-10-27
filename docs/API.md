# API reference

Interactive OpenAPI: backend `/docs`; machine-readable schema: `/openapi.json`.

All private routes accept a Clerk bearer token in `Authorization`. Tenant identity is derived from the verified `sub`, never a request parameter. Demo routes accept only fixed synthetic snapshots. Reports are returned as real attachments.

| Method | Route | Purpose |
|---|---|---|
| GET | `/api/health` | Database/cache readiness, version and operating mode |
| GET | `/metrics` | Prometheus aggregate metrics, no domain/user labels |
| GET | `/api/demo` | Synthetic snapshots, graph and scoped portfolio |
| POST | `/api/demo/simulate` | Synthetic exposure traversal |
| POST | `/api/demo/analyst` | Free evidence retrieval on demo snapshot |
| GET | `/api/demo/reports/{id}/{format}` | Synthetic PDF/JSON/CSV |
| POST | `/api/scans` | Submit bounded public-domain collection |
| GET | `/api/scans` | Latest 100 own jobs including explicit failures |
| GET | `/api/scans/{id}` | Own job status |
| GET | `/api/workspace` | Up to 500 latest successful snapshots, graph and portfolio |
| POST | `/api/simulate` | Own workspace provider exposure |
| POST | `/api/analyst` | Own snapshot retrieval / optional LLM synthesis |
| GET | `/api/reports/{id}/{format}` | Own evidence report |
| GET | `/api/monitors` | Own scheduled domains |
| POST | `/api/monitors` | Upsert own scheduled domain or pause it |

## Submit scan

```http
POST /api/scans
Authorization: Bearer <clerk-session-token>
Content-Type: application/json
Idempotency-Key: 6d948f3f-afe2-467d-b4f3-a90115807737

{"domain":"github.com"}
```

Returns `202`, `Location: /api/scans/{id}` and:

```json
{
  "id": "generated-uuid",
  "domain": "github.com",
  "status": "queued",
  "created_at": "ISO-8601",
  "error": null,
  "snapshot_id": null
}
```

Poll until `completed` or `failed`, then refresh `/api/workspace`. Reusing the same key/domain returns the existing job. Reusing the key with a different domain returns `409`. Keys must be 8–100 ASCII letters, digits, hyphens or underscores.

States: `queued -> running -> completed | failed`. Tasks that exceed the five-minute execution window are explicitly failed; retry with a new key. Local inline mode is not a durable queue.

## Exposure simulation

```json
{"provider_id":"cloudflare"}
```

Returns `affected_assets`, `affected_node_ids`, observed `concentration`, and a scope warning. A missing provider returns `404`, not a fabricated zero-risk result.

## Analyst

```json
{"snapshot_id":"demo-0","question":"Which DNS dependencies are visible?"}
```

Returns `mode` (`evidence-retrieval` or `llm-rag`), `answer`, and retrieved evidence `citations`. Public demo never spends an LLM key.

## Monitoring

```json
{"domain":"github.com","interval_hours":24,"enabled":true}
```

Intervals are 6, 12 or 24 hours. Maximum ten monitored domains per owner. `enabled=false` pauses future scheduling; already-running scans are not canceled. A non-Celery deployment returns `409` rather than claiming scheduled execution.

## Errors

`401`: no/invalid Clerk session; `403`: live features disabled in demo; `404`: absent or inaccessible record; `409`: conflict/unsupported scheduler; `422`: invalid input; `429`: scan quota with `Retry-After`; `502`: analyst provider failure; `503`: identity/queue/admission outage. Collection failures are persisted in the job, not represented as a successful snapshot.
