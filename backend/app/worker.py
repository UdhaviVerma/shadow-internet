import logging
from datetime import timedelta

from celery import Celery
from redis import Redis
from sqlalchemy import select, update

from app.collector import PublicCollector
from app.config import get_settings
from app.database import Monitor, Scan, SessionLocal, now
from app.intelligence import changes_between, enrich
from app.schemas import Intelligence

logger = logging.getLogger(__name__)
settings = get_settings()
celery_app = Celery("shadow-internet", broker=settings.redis_url)
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    task_reject_on_worker_lost=True,
    task_soft_time_limit=100,
    task_time_limit=120,
    broker_connection_retry_on_startup=True,
    timezone="UTC",
    enable_utc=True,
)


def execute_scan(scan_id: str) -> None:
    with SessionLocal() as session:
        claimed = session.execute(
            update(Scan)
            .where(
                Scan.id == scan_id,
                Scan.status == "queued",
            )
            .values(status="running", started_at=now())
        )
        session.commit()
        if not claimed.rowcount:
            return
        scan = session.get(Scan, scan_id)
        if scan is None:
            return
        try:
            cache = (
                Redis.from_url(settings.redis_url, socket_connect_timeout=3, socket_timeout=3)
                if settings.redis_url
                else None
            )
            cached = cache.get(f"shadow:public-evidence:v1:{scan.domain}") if cache else None
            if cached:
                intel = Intelligence.model_validate_json(cached)
            else:
                intel = enrich(PublicCollector().collect(scan.domain))
                if cache:
                    cache.setex(f"shadow:public-evidence:v1:{scan.domain}", 900, intel.model_dump_json())
            previous = session.scalar(
                select(Scan)
                .where(
                    Scan.owner == scan.owner,
                    Scan.domain == scan.domain,
                    Scan.status == "completed",
                    Scan.id != scan.id,
                )
                .order_by(Scan.created_at.desc())
                .limit(1)
            )
            scan.changes = changes_between(Intelligence.model_validate(previous.result) if previous else None, intel)
            scan.result = intel.model_dump(mode="json")
            scan.status = "completed"
            scan.finished_at = now()
            session.commit()
        except Exception as exc:
            # Task boundary: preserve an explicit failed state instead of leaving a success-shaped partial result.
            logger.exception("Scan %s failed (%s)", scan_id, type(exc).__name__)
            session.rollback()
            scan = session.get(Scan, scan_id)
            if scan:
                scan.status = "failed"
                scan.error = f"Collection failed ({type(exc).__name__}). Retry later or review service logs."
                scan.finished_at = now()
                session.commit()


@celery_app.task(name="shadow.scan", ignore_result=True)
def scan_task(scan_id: str) -> None:
    execute_scan(scan_id)


@celery_app.task(name="shadow.recover", ignore_result=True)
def recover_stale_tasks() -> None:
    with SessionLocal() as session:
        stale = list(
            session.scalars(
                select(Scan)
                .where(
                    Scan.status.in_(["queued", "running"]),
                    Scan.created_at < now() - timedelta(minutes=5),
                )
                .limit(100)
            )
        )
        for scan in stale:
            scan.status = "failed"
            scan.error = "Worker did not complete within five minutes. Submit a new scan to retry."
            scan.finished_at = now()
        session.commit()
    if stale:
        logger.warning("Marked %d stale scan tasks failed", len(stale))


@celery_app.task(name="shadow.monitor", ignore_result=True)
def schedule_monitors() -> None:
    if settings.auth_mode != "clerk":
        return
    with SessionLocal() as session:
        due = list(
            session.scalars(
                select(Monitor)
                .where(
                    Monitor.enabled.is_(True),
                    Monitor.next_run <= now(),
                )
                .with_for_update(skip_locked=True)
                .limit(50)
            )
        )
        scan_ids = []
        for monitor in due:
            scan = Scan(
                owner=monitor.owner,
                domain=monitor.domain,
                request_key=f"monitor-{monitor.id}-{int(now().timestamp())}",
            )
            session.add(scan)
            session.flush()
            scan_ids.append(scan.id)
            monitor.next_run = now() + timedelta(hours=monitor.interval_hours)
        session.commit()
    for scan_id in scan_ids:
        try:
            scan_task.apply_async(args=[scan_id], retry=False)
        except Exception:
            logger.exception("Monitor queue submission failed for %s", scan_id)
            with SessionLocal() as session:
                session.execute(
                    update(Scan)
                    .where(Scan.id == scan_id)
                    .values(
                        status="failed",
                        error="Scheduled scan could not be queued",
                        finished_at=now(),
                    )
                )
                session.commit()


celery_app.conf.beat_schedule = {
    "recover-interrupted-scans": {"task": "shadow.recover", "schedule": 60.0},
    "schedule-domain-monitoring": {"task": "shadow.monitor", "schedule": 60.0},
}
