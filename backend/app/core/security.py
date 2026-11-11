from datetime import datetime, timedelta, timezone
from uuid import UUID

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from jose import JWTError, jwt

from app.config import settings

_hasher = PasswordHasher()


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except VerifyMismatchError:
        return False


def _create_token(subject: UUID, expires_delta: timedelta, token_type: str) -> str:
    now = datetime.now(timezone.utc)
    payload = {"sub": str(subject), "type": token_type, "iat": now, "exp": now + expires_delta}
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def create_access_token(user_id: UUID) -> str:
    return _create_token(user_id, timedelta(minutes=settings.access_token_expire_minutes), "access")


def create_refresh_token(user_id: UUID) -> str:
    return _create_token(user_id, timedelta(days=settings.refresh_token_expire_days), "refresh")


class InvalidTokenError(Exception):
    pass


def decode_token(token: str, expected_type: str) -> UUID:
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    except JWTError as exc:
        raise InvalidTokenError("Could not validate token") from exc

    if payload.get("type") != expected_type:
        raise InvalidTokenError(f"Expected a {expected_type} token")

    try:
        return UUID(payload["sub"])
    except (KeyError, ValueError) as exc:
        raise InvalidTokenError("Token missing subject") from exc
