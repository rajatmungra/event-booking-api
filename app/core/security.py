import uuid
from datetime import UTC, datetime, timedelta

import jwt
from pwdlib import PasswordHash

from app.core.config import settings
from app.core.exceptions import NotAuthenticated

ALGORITHM = "HS256"
ACCESS_TOKEN_LIFETIME = timedelta(minutes=60)

# Argon2 with pwdlib's recommended parameters.
password_hash = PasswordHash.recommended()


def create_access_token(user_id: uuid.UUID) -> str:
    payload = {"sub": str(user_id), "exp": datetime.now(UTC) + ACCESS_TOKEN_LIFETIME}
    return jwt.encode(payload, settings.jwt_secret, algorithm=ALGORITHM)


def decode_access_token(token: str) -> uuid.UUID:
    try:
        payload = jwt.decode(
            token, settings.jwt_secret, algorithms=[ALGORITHM], options={"require": ["exp", "sub"]}
        )
        return uuid.UUID(payload["sub"])
    except (jwt.InvalidTokenError, ValueError) as exc:
        raise NotAuthenticated() from exc
