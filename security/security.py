
import os
from datetime import datetime, timedelta, timezone

import jwt

from dotenv import load_dotenv
from pwdlib import PasswordHash
from fastapi import HTTPException, status


load_dotenv()


# =====================================
# CONFIGURATION
# =====================================

JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY")

JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")

ACCESS_TOKEN_EXPIRE_MINUTES = int(
    os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "30")
)

if not JWT_SECRET_KEY:
    raise RuntimeError("JWT_SECRET_KEY is missing from .env")


# =====================================
# PASSWORD HASHING
# =====================================

password_hash = PasswordHash.recommended()


def hash_password(password: str) -> str:
    """
    Convert plain password into a secure password hash.
    """

    return password_hash.hash(password)


def verify_password(
    plain_password: str,
    hashed_password: str
) -> bool:
    """
    Verify a plain password against its stored hash.
    """

    return password_hash.verify(
        plain_password,
        hashed_password
    )


# =====================================
# JWT TOKEN GENERATION
# =====================================

def create_access_token(
    user_id: int,
    role: str,
    expires_delta: timedelta | None = None
) -> str:

    now = datetime.now(timezone.utc)

    if expires_delta is None:
        expires_delta = timedelta(
            minutes=ACCESS_TOKEN_EXPIRE_MINUTES
        )

    expire = now + expires_delta

    payload = {
        "sub": str(user_id),
        "role": role,
        "iat": now,
        "exp": expire,
    }

    token = jwt.encode(
        payload,
        JWT_SECRET_KEY,
        algorithm=JWT_ALGORITHM
    )

    return token


# =====================================
# JWT TOKEN VERIFICATION
# =====================================

def decode_access_token(token: str) -> dict:

    try:
        payload = jwt.decode(
            token,
            JWT_SECRET_KEY,
            algorithms=[JWT_ALGORITHM],
            options={"require": ["sub", "exp"]}
        )

        return payload

    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired",
            headers={"WWW-Authenticate": "Bearer"}
        )

    except jwt.InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication token",
            headers={"WWW-Authenticate": "Bearer"}
        )
