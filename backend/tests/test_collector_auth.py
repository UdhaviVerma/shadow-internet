import time
from types import SimpleNamespace

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from pydantic import ValidationError

from app import auth, collector
from app.collector import CollectionError, PublicCollector
from app.config import Settings


def test_collector_rejects_mixed_private_answers_before_probe(monkeypatch):
    def handler(request):
        record_type = request.url.params.get("type")
        return httpx.Response(
            200,
            json={
                "Status": 0,
                "AD": False,
                "Answer": [{"type": 1, "data": "8.8.8.8"}, {"type": 1, "data": "127.0.0.1"}]
                if record_type == "A"
                else [],
            },
        )

    original = httpx.Client
    monkeypatch.setattr(collector.httpx, "Client", lambda **kwargs: original(transport=httpx.MockTransport(handler)))
    monkeypatch.setattr(collector, "pinned_probe", lambda *_: pytest.fail("Unsafe target was probed"))
    with pytest.raises(CollectionError, match="non-public"):
        PublicCollector().collect("github.com")


def test_collector_partial_outage_retains_unknowns(monkeypatch):
    def handler(request):
        if request.url.params.get("type") == "NS":
            return httpx.Response(503)
        return httpx.Response(200, json={"Status": 0, "AD": False, "Answer": []})

    original = httpx.Client
    monkeypatch.setattr(collector.httpx, "Client", lambda **kwargs: original(transport=httpx.MockTransport(handler)))
    result = PublicCollector().collect("github.com")
    assert "NS" not in result.dns
    assert any("NS lookup unavailable" in w for w in result.warnings)
    assert result.tls is None


def test_nxdomain_is_failed_not_empty_success(monkeypatch):
    original = httpx.Client
    monkeypatch.setattr(
        collector.httpx,
        "Client",
        lambda **kwargs: original(
            transport=httpx.MockTransport(lambda request: httpx.Response(200, json={"Status": 3})),
        ),
    )
    with pytest.raises(CollectionError, match="no successful"):
        PublicCollector().collect("doesnotexist-domain.com")


def test_production_guards():
    with pytest.raises(ValidationError):
        Settings(_env_file=None, environment="production", auth_mode="development")
    with pytest.raises(ValidationError):
        Settings(_env_file=None, environment="production", database_url="sqlite:///data.db")
    with pytest.raises(ValidationError):
        Settings(_env_file=None, auth_mode="clerk")


def test_clerk_verification_signature_issuer_expiry_and_azp(monkeypatch):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    settings = Settings(_env_file=None, auth_mode="clerk", clerk_issuer="https://clerk.example.org")
    monkeypatch.setattr(auth, "get_settings", lambda: settings)
    monkeypatch.setattr(
        auth,
        "jwks_client",
        lambda _: SimpleNamespace(
            get_signing_key_from_jwt=lambda _: SimpleNamespace(key=key.public_key()),
        ),
    )
    claims = {
        "sub": "user-001",
        "exp": int(time.time()) + 60,
        "iat": int(time.time()),
        "nbf": int(time.time()) - 1,
        "iss": settings.clerk_issuer,
        "azp": settings.frontend_origin,
    }

    def credentials(values):
        return HTTPAuthorizationCredentials(scheme="Bearer", credentials=jwt.encode(values, key, algorithm="RS256"))

    assert auth.current_owner(credentials(claims)) == "user-001"
    for changes in [{"azp": "https://other.example"}, {"exp": 1}, {"iss": "https://evil.example"}]:
        with pytest.raises(HTTPException) as exc:
            auth.current_owner(credentials(claims | changes))
        assert exc.value.status_code == 401
