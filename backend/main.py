# backend/main.py

from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.ext.asyncio import AsyncSession

from .database import get_db, engine, Base
from .crud import (
    get_user_by_spotify_id,
    create_user,
    update_user_refresh_token,
    create_room,
    get_room_by_code,
    add_user_to_room,
    save_preferences,
    get_room, get_room_members, remove_user_from_room, end_room
)
from .models import User
from .schemas import UserOut, PreferencesCreate, RoomOut, UserCreate
from . import spotify_auth
from .auth import get_current_user
from . import models   # <-- IMPORTANT: ensures SQLAlchemy loads models

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ============================================================
# AUTH FLOW — UPDATED
# ============================================================

@app.get("/auth/login")
async def auth_login():
    url = spotify_auth.build_auth_url()
    return {"auth_url": url}


@app.get("/auth/callback")
async def auth_callback(
        code: str | None = None,
        state: str | None = None,
        db: AsyncSession = Depends(get_db)
):
    tokens = await spotify_auth.exchange_code_for_token(code)
    if "error" in tokens:
        raise HTTPException(status_code=400, detail="Invalid Spotify callback")

    access_token = tokens["access_token"]
    refresh_token = tokens.get("refresh_token")

    profile = await spotify_auth.get_user_profile(access_token)
    spotify_id = profile["id"]

    user = await get_user_by_spotify_id(db, spotify_id)

    if user:
        if refresh_token:
            user = await update_user_refresh_token(db, spotify_id, refresh_token)
    else:
        data = {
            "spotify_id": spotify_id,
            "display_name": profile.get("display_name"),
            "avatar_url": profile.get("images", [{}])[0].get("url"),
            "refresh_token": refresh_token
        }
        user = await create_user(db, UserCreate(**data))

    app_token = spotify_auth.create_app_token(user.id)
    return {"app_token": app_token}


@app.get("/me/app", response_model=UserOut)
async def get_me_route(user = Depends(get_current_user)):
    return user

# ============================================================
# ROOM ENDPOINTS
# ============================================================

@app.post("/rooms", response_model=RoomOut)
async def create_room_route(
        user = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
):
    room = await create_room(db, user.id)

    # NEW LINE: add the host to the room members automatically
    await add_user_to_room(db, room.id, user.id)

    return room

@app.post("/rooms/join/{code}")
async def join_room_route(
        code: str,
        user = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
):
    room = await get_room_by_code(db, code)
    if not room:
        raise HTTPException(status_code=404, detail="Invalid room code")

    await add_user_to_room(db, room.id, user.id)
    return {"message": "Joined room", "room_id": room.id}

# ============================================================
# PREFERENCES
# ============================================================

@app.post("/rooms/{room_id}/preferences")
async def save_preferences_route(
        room_id: int,
        prefs: PreferencesCreate,
        user = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
):
    saved = await save_preferences(db, room_id, user.id, prefs)
    return {"message": "Preferences saved", "id": saved.id}


@app.delete("/rooms/{room_id}")
async def end_room_route(
        room_id: int,
        user = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
):
    room, error = await end_room(db, room_id, user.id)

    if error == "Room not found":
        raise HTTPException(status_code=404, detail=error)
    if error == "Not authorized":
        raise HTTPException(status_code=403, detail=error)

    return {"message": "Room closed", "room_id": room_id}


@app.get("/rooms/{room_id}", response_model=RoomOut)
async def get_room_details(
        room_id: int,
        db: AsyncSession = Depends(get_db),
        current_user: User = Depends(get_current_user)
):
    room = await get_room(db, room_id)

    if not room:
        raise HTTPException(status_code=404, detail="Room not found")

    return room

@app.delete("/rooms/{room_id}/leave")
async def leave_room_route(
        room_id: int,
        user = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
):
    success = await remove_user_from_room(db, room_id, user.id)

    if not success:
        raise HTTPException(status_code=404, detail="User not in room")

    return {"message": "Left room"}


@app.get("/rooms/{room_id}/members")
async def get_members_route(
        room_id: int,
        db: AsyncSession = Depends(get_db),
        current_user: User = Depends(get_current_user)
):
    members = await get_room_members(db, room_id)
    return members

# ============================================================
# CREATE TABLES ON STARTUP
# ============================================================

@app.on_event("startup")
async def on_startup():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
