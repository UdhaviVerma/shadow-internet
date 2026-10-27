from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database import Scan, now


class ScanRepository:
    def __init__(self, session: Session):
        self.session = session

    def get(self, owner: str, scan_id: str) -> Scan | None:
        return self.session.scalar(select(Scan).where(Scan.owner == owner, Scan.id == scan_id))

    def by_key(self, owner: str, key: str) -> Scan | None:
        return self.session.scalar(select(Scan).where(Scan.owner == owner, Scan.request_key == key))

    def history(self, owner: str, domain: str | None = None) -> list[Scan]:
        query = select(Scan).where(Scan.owner == owner)
        if domain:
            query = query.where(Scan.domain == domain)
        return list(self.session.scalars(query.order_by(Scan.created_at.desc(), Scan.id.desc()).limit(100)))

    def completed(self, owner: str) -> list[Scan]:
        query = select(Scan).where(Scan.owner == owner, Scan.status == "completed")
        return list(self.session.scalars(query.order_by(Scan.created_at.desc(), Scan.id.desc()).limit(500)))

    def recent_count(self, owner: str) -> int:
        return (
            self.session.scalar(
                select(func.count())
                .select_from(Scan)
                .where(
                    Scan.owner == owner,
                    Scan.created_at >= now() - timedelta(hours=1),
                )
            )
            or 0
        )

    def create(self, owner: str, key: str, domain: str) -> Scan:
        scan = Scan(owner=owner, request_key=key, domain=domain)
        self.session.add(scan)
        self.session.commit()
        return scan
