from datetime import datetime, timedelta
from secrets import compare_digest

import jwt
from fastapi import Depends, HTTPException, Security
from fastapi.security import APIKeyHeader, HTTPAuthorizationCredentials, HTTPBearer

from config import get_settings


bearer = HTTPBearer()
ingest_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def _jwt_secret() -> str:
    settings = get_settings()
    return settings.jwt_secret or "change-this-in-development"


def create_token(username: str) -> str:
    settings = get_settings()
    payload = {
        "sub": username,
        "exp": datetime.utcnow() + timedelta(hours=settings.jwt_exp_hours),
    }
    return jwt.encode(payload, _jwt_secret(), algorithm="HS256")


def verify_token(credentials: HTTPAuthorizationCredentials = Depends(bearer)) -> str:
    try:
        payload = jwt.decode(credentials.credentials, _jwt_secret(), algorithms=["HS256"])
        return payload["sub"]
    except jwt.ExpiredSignatureError as exc:
        raise HTTPException(status_code=401, detail="Token expired") from exc
    except jwt.InvalidTokenError as exc:
        raise HTTPException(status_code=401, detail="Invalid token") from exc


def verify_admin_password(username: str, password: str) -> bool:
    settings = get_settings()
    if username != settings.admin_username or not settings.admin_password:
        return False
    return compare_digest(password, settings.admin_password)


def verify_ingest_key(api_key: str = Security(ingest_key_header)) -> None:
    settings = get_settings()
    if not settings.ingest_api_key:
        if settings.is_production:
            raise HTTPException(status_code=500, detail="Ingestion key is not configured")
        return
    if not api_key or api_key != settings.ingest_api_key:
        raise HTTPException(status_code=401, detail="Invalid ingestion API key")
