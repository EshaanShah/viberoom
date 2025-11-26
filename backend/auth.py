# backend/auth.py

import os
import jwt
from datetime import datetime, timedelta
from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from .database import get_db
from .models import User

SECRET_KEY = os.getenv("APP_SECRET_KEY", "dev-secret-change-me")
ALGORITHM = "HS256"

auth_scheme = HTTPBearer()


def create_app_token(user_id: int) -> str:
    """Generate a JWT signed with PyJWT."""
    payload = {
        "sub": str(user_id),
        "exp": datetime.utcnow() + timedelta(days=7)
    }
    token = jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)
    return token


async def get_current_user(
        token = Depends(auth_scheme),
        db: AsyncSession = Depends(get_db)
):
    """Decode JWT and return the authenticated user."""
    raw_token = token.credentials

    try:
        payload = jwt.decode(raw_token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = int(payload["sub"])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired.")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token.")

    # Fetch user from DB
    result = await db.execute(
        select(User).where(User.id == user_id)
    )
    user = result.scalars().first()

    if not user:
        raise HTTPException(status_code=401, detail="User not found.")

    return user
