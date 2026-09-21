from datetime import datetime, timedelta, timezone
import os

import jwt
from pwdlib import PasswordHash

from app.models import User


SECRET_KEY = os.getenv(
    "SECRET_KEY",
    "college-portal-local-dev-key-change-this",
)

ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30

password_hash = PasswordHash.recommended()


def verify_password(password: str, hashed_password: str) -> bool:
    return password_hash.verify(password, hashed_password)


def create_access_token(username: str, role: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=ACCESS_TOKEN_EXPIRE_MINUTES
    )

    data = {
        "sub": username,
        "role": role,
        "exp": expire,
    }

    return jwt.encode(
        data,
        SECRET_KEY,
        algorithm=ALGORITHM,
    )


def get_user_by_username(db, username: str):
    return (
        db.query(User)
        .filter(User.username == username)
        .first()
    )