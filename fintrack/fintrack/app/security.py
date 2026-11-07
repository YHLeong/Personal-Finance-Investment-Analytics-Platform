import os
from datetime import datetime, timedelta, timezone
from typing import Annotated

import bcrypt
import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from .db import get_db
from .models import User

SECRET = os.getenv("SECRET_KEY", "dev-only-secret")
ALGO = "HS256"
oauth2 = OAuth2PasswordBearer(tokenUrl="/auth/token")


def hash_pw(pw: str) -> str:
    return bcrypt.hashpw(pw.encode(), bcrypt.gensalt()).decode()


def verify_pw(pw: str, hashed: str) -> bool:
    return bcrypt.checkpw(pw.encode(), hashed.encode())


def make_token(user_id: int, minutes: int = 60) -> str:
    exp = datetime.now(timezone.utc) + timedelta(minutes=minutes)
    return jwt.encode({"sub": str(user_id), "exp": exp}, SECRET, algorithm=ALGO)


def current_user(token: Annotated[str, Depends(oauth2)], db: Annotated[Session, Depends(get_db)]) -> User:
    try:
        uid = int(jwt.decode(token, SECRET, algorithms=[ALGO])["sub"])
    except (jwt.PyJWTError, ValueError, KeyError):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid token")
    user = db.get(User, uid)
    if not user:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "User not found")
    return user
