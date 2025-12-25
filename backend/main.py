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
    get_room, get_room_members, remove_user_from_room, end_room, get_preferences_for_room
)
from .models import User
from .schemas import UserOut, PreferencesCreate, RoomOut, UserCreate
from . import spotify_auth, playlist_engine
from .auth import get_current_user
from . import models   # <-- IMPORTANT: ensures SQLAlchemy loads models
from typing import List
from sqlalchemy import select
from .models import PreferenceProfile
from .schemas import PreferencesOut, VibeProfile
import json
from .rec_engine import generate_vibe_profile

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

@app.get("/rooms/{room_id}/preferences", response_model=List[PreferencesOut])
async def get_room_preferences(
        room_id: int,
        db: AsyncSession = Depends(get_db),
        current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(PreferenceProfile).where(PreferenceProfile.room_id == room_id)
    )
    prefs = result.scalars().all()

    return [
        PreferencesOut(
            id=p.id,
            user_id=p.user_id,
            room_id=p.room_id,
            genres=safe_json_load(p.genres, []),
            hard_nos=safe_json_load(p.hard_nos, []),
            energy_level=p.energy_level,
            new_vs_familiar=p.new_vs_familiar,
            event_type=p.event_type,
            created_at=p.created_at
        )
        for p in prefs
    ]


@app.get("/rooms/{room_id}/preferences/me")
async def check_my_preferences(
        room_id: int,
        db: AsyncSession = Depends(get_db),
        current_user: User = Depends(get_current_user)
):
    result = await db.execute(
        select(PreferenceProfile).where(
            PreferenceProfile.room_id == room_id,
            PreferenceProfile.user_id == current_user.id
        )
    )
    pref = result.scalars().first()
    return {"completed": pref is not None}

@app.get("/rooms/{room_id}/vibe-profile", response_model=VibeProfile)
async def get_vibe_profile(
        room_id: int,
        db: AsyncSession = Depends(get_db),
        current_user: User = Depends(get_current_user)
):
    result = await db.execute(
        select(PreferenceProfile).where(PreferenceProfile.room_id == room_id)
    )
    prefs = result.scalars().all()

    if not prefs:
        raise HTTPException(status_code=400, detail="No preferences found.")

    vibe = generate_vibe_profile(prefs)
    return vibe



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

# backend/main.py

from backend.rec_engine import generate_vibe_profile
from backend.crud import get_preferences_for_room

@app.get("/test/vibe-profile/{room_id}")
async def test_vibe_profile(
        room_id: int,
        user=Depends(get_current_user),
        db: AsyncSession = Depends(get_db),
):
    prefs = await get_preferences_for_room(db, room_id)

    if not prefs:
        raise HTTPException(404, "No preferences found")

    vibe_profile = generate_vibe_profile(prefs)

    return {
        "raw_preferences": prefs,
        "vibe_profile": vibe_profile,
    }

def safe_json_load(value, default):
    if not value:
        return default
    if isinstance(value, (list, dict)):
        return value
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return default

@app.get("/test/playlist-engine-spotify/{room_id}")
async def test_playlist_engine_spotify(
        room_id: int,
        user=Depends(get_current_user),
        db: AsyncSession = Depends(get_db),
):
    prefs = await get_preferences_for_room(db, room_id)
    if not prefs:
        raise HTTPException(404, "No preferences found")

    vibe_profile = generate_vibe_profile(prefs)

    access_token = await spotify_auth.get_valid_access_token(user)

    # 1) Get top tracks
    tracks = await spotify_auth.get_top_tracks(access_token)
    track_ids = [t["id"] for t in tracks if t.get("id")]
    print("ABOUT TO CALL SPOTIFY /me")
    profile = await spotify_auth.get_user_profile(access_token)
    print("PROFILE:", profile)
    track_ids = [t for t in track_ids if t][:50]
    print("USING TRACK IDS:", track_ids)
    # 2) Get audio features for those tracks
    #audio_features = await spotify_auth.get_audio_features(access_token, track_ids)
    print("first track audio feature", spotify_auth.get_audio_features(access_token, ["2mNGL7mZILSqZHxGboJaO9"]).get("genres"))
    #features_by_id = {f["id"]: f for f in audio_features if f and f.get("id")}

    # 3) Build candidate_songs in the shape your engine expects
#    candidate_songs = []
#    for t in tracks:
#        tid = t.get("id")
#        f = features_by_id.get(tid)
#        if not tid or not f:
#            continue
#
#        candidate_songs.append({
#            "id": tid,
#            "genres": t.get("genres", []),                 # may be [] (fine for now)
#            "energy": f.get("energy", 0.5),                # 0–1
#            "popularity": t.get("popularity", 50),         # 0–100
#            "artist": (t.get("artists") or [{}])[0].get("name"),
#        })

    # 4) Run your playlist engine
 #   ranked = playlist_engine.generate_playlist(vibe_profile, candidate_songs)

    #return ranked[:25]
    return "here"
# ============================================================
# CREATE TABLES ON STARTUP
# ============================================================

@app.on_event("startup")
async def on_startup():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
