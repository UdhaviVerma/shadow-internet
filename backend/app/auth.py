from functools import lru_cache

import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import PyJWKClient

from app.config import get_settings

bearer = HTTPBearer(auto_error=False)


@lru_cache
def jwks_client(issuer: str) -> PyJWKClient:
    return PyJWKClient(f"{issuer.rstrip('/')}/.well-known/jwks.json", timeout=5)


def current_owner(credentials: HTTPAuthorizationCredentials | None = Depends(bearer)) -> str:
    settings = get_settings()
    if settings.auth_mode == "development" and settings.environment != "production":
        return "local-developer"
    if settings.auth_mode == "demo":
        raise HTTPException(403, "Live workspaces require Clerk authentication. The synthetic demo remains available.")
    if credentials is None:
        raise HTTPException(401, "Sign in to your workspace")
    try:
        key = jwks_client(settings.clerk_issuer or "").get_signing_key_from_jwt(credentials.credentials)
        claims = jwt.decode(
            credentials.credentials,
            key.key,
            algorithms=["RS256"],
            issuer=settings.clerk_issuer,
            audience=settings.clerk_audience,
            options={"require": ["sub", "exp", "iat", "nbf"], "verify_aud": bool(settings.clerk_audience)},
        )
        if claims.get("azp") != settings.frontend_origin:
            raise HTTPException(401, "Token is not authorized for this frontend")
        if not isinstance(claims["sub"], str) or not claims["sub"]:
            raise HTTPException(401, "Invalid subject")
        return claims["sub"]
    except jwt.PyJWKClientConnectionError as exc:
        raise HTTPException(503, "Identity provider is temporarily unavailable") from exc
    except jwt.PyJWTError as exc:
        raise HTTPException(401, "Invalid or expired session") from exc
