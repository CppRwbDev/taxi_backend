from passlib.context import CryptContext
from jose import JWTError, jwt
from datetime import datetime, timedelta, timezone
from typing import Optional
from app.config import settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def create_token(data: dict, secret: str, expire_minutes: int) -> str:
    """JWT token yaratish."""
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(minutes=expire_minutes)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, secret, algorithm="HS256")


def decode_token(token: str, secret: str) -> Optional[dict]:
    """JWT token decode qilish. Xato bo'lsa None qaytaradi."""
    try:
        return jwt.decode(token, secret, algorithms=["HS256"])
    except JWTError:
        return None


def create_admin_token(username: str) -> str:
    return create_token(
        {"sub": username, "type": "admin"},
        settings.ADMIN_JWT_SECRET,
        settings.ADMIN_JWT_EXPIRE_MINUTES,
    )


def create_dev_token(username: str) -> str:
    return create_token(
        {"sub": username, "type": "dev"},
        settings.DEV_JWT_SECRET,
        settings.DEV_JWT_EXPIRE_MINUTES,
    )
