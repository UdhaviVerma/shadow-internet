import json
import logging
import re
import time
from contextlib import asynccontextmanager
from datetime import timedelta
from uuid import uuid4

import httpx
from fastapi import BackgroundTasks, Depends, FastAPI, Header, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest
from redis import Redis
from redis.exceptions import RedisError
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.analyst import answer
from app.auth import current_owner
from app.config import get_settings
from app.database import Base, Monitor, Scan, engine, get_db, now
from app.demo import demo_snapshots
from app.intelligence import graph_for, portfolio, simulate
from app.reports import csv_report, pdf_report
from app.repository import ScanRepository
from app.schemas import AnalystRequest, Intelligence, MonitorRequest, ScanRequest, SimulationRequest

logger = logging.getLogger("shadow.api")
settings = get_settings()
HTTP_REQUESTS = Counter("shadow_http_requests_total", "HTTP requests", ["method", "route", "status"])
HTTP_LATENCY = Histogram("shadow_http_request_seconds", "HTTP latency", ["route"])
SCAN_REQUESTS = Counter("shadow_scan_requests_total", "Accepted scan requests")


@asynccontextmanager
async def lifespan(app: FastAPI):
    if settings.environment != "production":
        Base.metadata.create_all(engine)
    yield
    engine.dispose()


app = FastAPI(
    title="Shadow Internet",
    version="0.1.0",
    lifespan=lifespan,
    description="Evidence-based public infrastructure intelligence. OpenAPI documents all endpoints. Observed dependencies are not actual outage predictions.",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_origin],
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Authorization", "Content-Type", "Idempotency-Key"],
)


@app.middleware("http")
async def telemetry(request: Request, call_next):
    started = time.monotonic()
    request_id = str(uuid4())
    response = await call_next(request)
    route = request.scope.get("route")
    label = route.path if route else "unmatched"
    HTTP_REQUESTS.labels(request.method, label, str(response.status_code)).inc()
    HTTP_LATENCY.labels(label).observe(time.monotonic() - started)
    response.headers["X-Request-ID"] = request_id
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Cache-Control"] = "no-store"
    return response


def serialize_scan(scan: Scan) -> dict:
    status = scan.status
    error = scan.error
    if status in {"queued", "running"} and scan.created_at.replace(tzinfo=now().tzinfo) < now() - timedelta(minutes=5):
        status = "failed"
        error = "Scan exceeded the five-minute execution window. Submit a new scan to retry."
    return {
        "id": scan.id,
        "domain": scan.domain,
        "status": status,
        "created_at": scan.created_at.isoformat(),
        "error": error,
        "snapshot_id": scan.id if scan.result else None,
    }


def snapshot(scan: Scan) -> dict:
    return {
        "id": scan.id,
        "domain": scan.domain,
        "created_at": scan.created_at.isoformat(),
        "intelligence": scan.result,
        "changes": scan.changes,
    }


def owned_snapshots(db: Session, owner: str) -> list[dict]:
    return [snapshot(scan) for scan in ScanRepository(db).completed(owner)]


def find_snapshot(scan_id: str, db: Session, owner: str | None) -> dict:
    if scan_id.startswith("demo-"):
        found = next((s for s in demo_snapshots() if s["id"] == scan_id), None)
    else:
        scan = ScanRepository(db).get(owner or "", scan_id)
        found = snapshot(scan) if scan and scan.result else None
    if found is None:
        raise HTTPException(404, "Snapshot not found")
    return found


@app.get("/api/health", tags=["operations"])
def health(db: Session = Depends(get_db)):
    db.execute(text("SELECT 1"))
    if settings.redis_url:
        try:
            Redis.from_url(settings.redis_url, socket_connect_timeout=2, socket_timeout=2).ping()
        except RedisError as exc:
            logger.warning("Readiness failed: Redis unavailable")
            raise HTTPException(503, "Queue/cache unavailable") from exc
    return {"status": "ok", "version": "0.1.0", "auth_mode": settings.auth_mode, "queue_mode": settings.queue_mode}


@app.get("/metrics", tags=["operations"])
def metrics():
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.get("/api/demo", tags=["demo"])
def demo():
    snapshots = demo_snapshots()
    return {"snapshots": snapshots, "portfolio": portfolio(snapshots), "graph": graph_for(snapshots), "mode": "demo"}


@app.post("/api/demo/simulate", tags=["demo"])
def demo_simulate(payload: SimulationRequest):
    try:
        return simulate(demo_snapshots(), payload.provider_id)
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc


@app.post("/api/demo/analyst", tags=["demo"])
def demo_analyst(payload: AnalystRequest, db: Session = Depends(get_db)):
    if not payload.snapshot_id.startswith("demo-"):
        raise HTTPException(404, "Demo snapshot not found")
    intel = Intelligence.model_validate(find_snapshot(payload.snapshot_id, db, None)["intelligence"])
    # Public demo deliberately uses retrieval only; paid provider usage is authenticated.
    from app.analyst import retrieve

    return {
        "mode": "evidence-retrieval",
        "answer": (
            f"Public demo evidence for {intel.domain}. Relationships are synthetic and inferred, not real-company findings.\n\n"
            + "\n\n".join(f"[{e['id']}] {e['value']}" for e in retrieve(payload.question, intel))
            + "\n\nInternal architecture, WAF enforcement and actual outage impact are not established by these observations."
        ),
        "citations": retrieve(payload.question, intel),
    }


@app.get("/api/demo/reports/{snapshot_id}/{format}", tags=["reports"])
def demo_report(snapshot_id: str, format: str, db: Session = Depends(get_db)):
    if not snapshot_id.startswith("demo-"):
        raise HTTPException(404, "Demo snapshot not found")
    return report_response(find_snapshot(snapshot_id, db, None), format)


@app.post("/api/scans", status_code=202, tags=["scans"])
def create_scan(
    payload: ScanRequest,
    background: BackgroundTasks,
    response: Response,
    owner: str = Depends(current_owner),
    db: Session = Depends(get_db),
    idempotency_key: str = Header(min_length=8, max_length=100),
):
    if not re.fullmatch(r"[a-zA-Z0-9_-]+", idempotency_key):
        raise HTTPException(422, "Idempotency-Key must contain only letters, numbers, underscores or hyphens")
    repo = ScanRepository(db)
    existing = repo.by_key(owner, idempotency_key)
    if existing:
        if existing.domain != payload.domain:
            raise HTTPException(409, "Idempotency-Key was already used for a different domain")
        return serialize_scan(existing)
    if settings.redis_url:
        try:
            redis = Redis.from_url(settings.redis_url, socket_timeout=3, socket_connect_timeout=3)
            bucket = f"shadow:rate:{owner}:{int(time.time() // 3600)}"
            count = redis.eval(
                "local n=redis.call('INCR',KEYS[1]); if n==1 then redis.call('EXPIRE',KEYS[1],3600) end; return n",
                1,
                bucket,
            )
        except RedisError as exc:
            logger.warning("Scan admission failed: rate limiter unavailable")
            raise HTTPException(503, "Rate limiter unavailable; scan was not accepted") from exc
        if count > settings.scan_limit_per_hour:
            raise HTTPException(429, "Hourly scan limit reached", headers={"Retry-After": "3600"})
    elif repo.recent_count(owner) >= settings.scan_limit_per_hour:
        raise HTTPException(429, "Hourly scan limit reached", headers={"Retry-After": "3600"})
    try:
        scan = repo.create(owner, idempotency_key, payload.domain)
    except IntegrityError:
        db.rollback()
        scan = repo.by_key(owner, idempotency_key)
        if scan is None or scan.domain != payload.domain:
            raise HTTPException(409, "Conflicting scan request")
        return serialize_scan(scan)
    if settings.queue_mode == "celery":
        from app.worker import scan_task

        try:
            scan_task.apply_async(args=[scan.id], retry=False)
        except Exception as exc:
            logger.exception("Queue admission failed for scan %s", scan.id)
            scan.status = "failed"
            scan.error = "Queue rejected the scan. Submit a new request to retry."
            db.commit()
            raise HTTPException(503, "Worker queue unavailable; scan was not scheduled") from exc
    else:
        from app.worker import execute_scan

        background.add_task(execute_scan, scan.id)
    SCAN_REQUESTS.inc()
    response.headers["Location"] = f"/api/scans/{scan.id}"
    return serialize_scan(scan)


@app.get("/api/scans", tags=["scans"])
def scans(owner: str = Depends(current_owner), db: Session = Depends(get_db)):
    return [serialize_scan(scan) for scan in ScanRepository(db).history(owner)]


@app.get("/api/scans/{scan_id}", tags=["scans"])
def scan_status(scan_id: str, owner: str = Depends(current_owner), db: Session = Depends(get_db)):
    scan = ScanRepository(db).get(owner, scan_id)
    if scan is None:
        raise HTTPException(404, "Scan not found")
    return serialize_scan(scan)


@app.get("/api/workspace", tags=["workspace"])
def workspace(owner: str = Depends(current_owner), db: Session = Depends(get_db)):
    snapshots = owned_snapshots(db, owner)
    return {"snapshots": snapshots, "portfolio": portfolio(snapshots), "graph": graph_for(snapshots), "mode": "live"}


@app.post("/api/simulate", tags=["workspace"])
def simulation(payload: SimulationRequest, owner: str = Depends(current_owner), db: Session = Depends(get_db)):
    try:
        return simulate(owned_snapshots(db, owner), payload.provider_id)
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc


@app.get("/api/monitors", tags=["monitoring"])
def monitors(owner: str = Depends(current_owner), db: Session = Depends(get_db)):
    rows = db.scalars(select(Monitor).where(Monitor.owner == owner).order_by(Monitor.domain))
    return [
        {
            "id": row.id,
            "domain": row.domain,
            "enabled": row.enabled,
            "interval_hours": row.interval_hours,
            "next_run": row.next_run.isoformat(),
        }
        for row in rows
    ]


@app.post("/api/monitors", tags=["monitoring"])
def save_monitor(payload: MonitorRequest, owner: str = Depends(current_owner), db: Session = Depends(get_db)):
    if settings.queue_mode != "celery":
        raise HTTPException(409, "Scheduled monitoring requires Redis, a Celery worker and one beat scheduler")
    row = db.scalar(select(Monitor).where(Monitor.owner == owner, Monitor.domain == payload.domain))
    if row is None:
        count = db.scalar(select(func.count()).select_from(Monitor).where(Monitor.owner == owner)) or 0
        if count >= 10:
            raise HTTPException(409, "Workspace monitor limit reached (10 domains)")
        row = Monitor(owner=owner, domain=payload.domain)
        db.add(row)
    row.enabled = payload.enabled
    row.interval_hours = payload.interval_hours
    row.next_run = now() + timedelta(hours=payload.interval_hours)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, "Monitor changed concurrently. Reload and retry.") from exc
    return {
        "domain": row.domain,
        "enabled": row.enabled,
        "interval_hours": row.interval_hours,
        "next_run": row.next_run.isoformat(),
    }


@app.post("/api/analyst", tags=["analyst"])
def analyst(payload: AnalystRequest, owner: str = Depends(current_owner), db: Session = Depends(get_db)):
    if len(ScanRepository(db).completed(owner)) == 0:
        raise HTTPException(404, "Complete a scan before asking the analyst")
    intel = Intelligence.model_validate(find_snapshot(payload.snapshot_id, db, owner)["intelligence"])
    try:
        return answer(payload.question, intel)
    except (httpx.HTTPError, ValueError, KeyError) as exc:
        logger.warning("Analyst provider failed: %s", type(exc).__name__)
        raise HTTPException(502, "Analyst provider unavailable; your evidence remains accessible") from exc


def report_response(data: dict, format: str) -> Response:
    if format == "json":
        content = json.dumps(data, indent=2)
        media_type = "application/json"
    elif format == "csv":
        content = csv_report(data)
        media_type = "text/csv"
    elif format == "pdf":
        content = pdf_report(data)
        media_type = "application/pdf"
    else:
        raise HTTPException(422, "Report format must be json, csv or pdf")
    return Response(
        content,
        media_type=media_type,
        headers={
            "Content-Disposition": f'attachment; filename="shadow-{data["domain"]}.{format}"',
        },
    )


@app.get("/api/reports/{snapshot_id}/{format}", tags=["reports"])
def report(snapshot_id: str, format: str, owner: str = Depends(current_owner), db: Session = Depends(get_db)):
    return report_response(find_snapshot(snapshot_id, db, owner), format)
