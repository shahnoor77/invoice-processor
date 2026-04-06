"""
Auth module — JWT-based login.
TODO: Replace in-memory user store with a real DB (PostgreSQL/SQLite).
"""
import os
from datetime import datetime, timedelta
from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from pydantic import BaseModel

SECRET_KEY = os.environ.get("JWT_SECRET_KEY", "change-this-in-production-use-a-long-random-string")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 8  # 8 hours

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")

# ── Temporary in-memory user store (replace with DB) ─────────────────────────
# Format: {email: {hashed_password, name, settings}}
_users: dict = {}


class UserSettings(BaseModel):
    # Multiple ERP webhook destinations — user can add/remove anytime
    erp_webhooks: list[str] = []          # list of ERP webhook URLs
    notification_emails: list[str] = []   # list of email addresses to notify
    slack_webhooks: list[str] = []        # list of Slack webhook URLs
    google_sheet_id: Optional[str] = None # user's own private sheet


class User(BaseModel):
    email: str
    name: str
    settings: UserSettings = UserSettings()


class UserInDB(User):
    hashed_password: str


class TokenData(BaseModel):
    email: Optional[str] = None


import hashlib

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


def _prepare(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()


def hash_password(password: str) -> str:
    return _prepare(password)


def verify_password(plain: str, hashed: str) -> bool:
    return _prepare(plain) == hashed


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def get_user(email: str) -> Optional[UserInDB]:
    u = _users.get(email)
    if u:
        return UserInDB(**u)
    return None


def register_user(email: str, password: str, name: str) -> User:
    if email in _users:
        raise HTTPException(status_code=400, detail="Email already registered")
    _users[email] = {
        "email": email,
        "name": name,
        "hashed_password": hash_password(password),
        "settings": {},
    }
    return User(email=email, name=name)


def authenticate_user(email: str, password: str) -> Optional[UserInDB]:
    user = get_user(email)
    if not user or not verify_password(password, user.hashed_password):
        return None
    return user


async def get_current_user(token: str = Depends(oauth2_scheme)) -> User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired token",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        email: str = payload.get("sub")
        if email is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception
    user = get_user(email)
    if user is None:
        raise credentials_exception
    return user


def update_user_settings(email: str, settings: UserSettings):
    if email not in _users:
        raise HTTPException(status_code=404, detail="User not found")
    _users[email]["settings"] = settings.model_dump()
