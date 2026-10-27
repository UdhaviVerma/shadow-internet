import re
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator


def normalize_domain(value: str) -> str:
    value = value.strip().rstrip(".").lower()
    if "://" in value or any(c in value for c in "/\\:@?#%"):
        raise ValueError("Enter a domain only, without scheme, path, port or credentials")
    try:
        value = value.encode("idna").decode("ascii")
    except UnicodeError as exc:
        raise ValueError("Invalid international domain") from exc
    if len(value) > 253 or not re.fullmatch(
        r"(?=.{1,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}", value
    ):
        raise ValueError("Enter a valid public domain, for example github.com")
    if value.endswith((".localhost", ".local", ".internal", ".test", ".invalid", ".example")):
        raise ValueError("Reserved or private domains cannot be scanned")
    return value


class ScanRequest(BaseModel):
    domain: str

    @field_validator("domain")
    @classmethod
    def validate_domain(cls, value: str) -> str:
        return normalize_domain(value)


class Evidence(BaseModel):
    id: str
    category: str
    source: str
    observed_at: datetime
    value: str
    confidence: Literal["observed", "inferred", "unknown"] = "observed"


class Provider(BaseModel):
    id: str
    name: str
    roles: list[str]
    evidence_ids: list[str]
    confidence: Literal["observed", "inferred"] = "inferred"


class Location(BaseModel):
    ip: str
    country: str
    latitude: float
    longitude: float
    source: str
    label: str = "Approximate IP geolocation; not an origin or routing-path measurement"


class TLSDetails(BaseModel):
    issuer: str
    subject: str
    not_after: datetime
    days_remaining: int
    protocol: str
    fingerprint: str
    verified: bool


class CategoryScore(BaseModel):
    name: str
    score: int | None
    explanation: str
    evidence_ids: list[str] = Field(default_factory=list)


class Intelligence(BaseModel):
    domain: str
    collected_at: datetime
    mode: Literal["live", "demo"]
    dns: dict[str, list[str]]
    dnssec_validated: bool | None
    addresses: list[str]
    headers: dict[str, str]
    tls: TLSDetails | None
    providers: list[Provider]
    locations: list[Location]
    evidence: list[Evidence]
    warnings: list[str]
    scores: list[CategoryScore] = Field(default_factory=list)
    overall_score: int | None = None
    coverage: int = 0


class SnapshotView(BaseModel):
    id: str
    domain: str
    created_at: datetime
    intelligence: Intelligence
    changes: list[str]


class AnalystRequest(BaseModel):
    snapshot_id: str = Field(max_length=80)
    question: str = Field(min_length=5, max_length=1200)


class SimulationRequest(BaseModel):
    provider_id: str = Field(min_length=1, max_length=100)


class MonitorRequest(ScanRequest):
    interval_hours: Literal[6, 12, 24] = 24
    enabled: bool = True
