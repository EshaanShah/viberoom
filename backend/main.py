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
    get_room_members, remove_user_from_room, end_room, get_preferences_for_room,  get_room
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
from .playlist_engine import generate_playlist as engine_generate_playlist
from .spotify_helpers import create_spotify_playlist, add_tracks_to_playlist, get_user_top_tracks


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

@app.post("/rooms/{room_id}/generate-playlist")
async def generate_playlist_route(
        room_id: int,
        db: AsyncSession = Depends(get_db),
        current_user: User = Depends(get_current_user)
):
    """
    Generate a collaborative playlist for a room.

    Steps:
    1. Verify room exists and user is a member
    2. Get all preferences for the room
    3. Generate vibe profile
    4. Fetch top tracks for each room member
    5. Generate playlist using engine
    6. Create Spotify playlist
    7. Add tracks to playlist
    8. Save playlist metadata to DB
    """
    # Step 1: Verify room and membership
    room = await get_room(db, room_id)
    if not room:
        raise HTTPException(status_code=404, detail="Room not found")

    members = await get_room_members(db, room_id)
    member_ids = [m.id for m in members]

    if current_user.id not in member_ids:
        raise HTTPException(status_code=403, detail="Not a member of this room")

    # Step 2: Get preferences
    prefs = await get_preferences_for_room(db, room_id)
    if not prefs:
        raise HTTPException(status_code=400, detail="No preferences submitted yet")

    # Step 3: Generate vibe profile
    vibe_profile = generate_vibe_profile(prefs)

    # Step 4: Fetch top tracks for each member
    user_top_tracks = {}
    for member in members:
        try:
            access_token = await spotify_auth.get_valid_access_token(member)
            top_tracks = await get_user_top_tracks(access_token, limit=50)
            user_top_tracks[member.id] = top_tracks
        except Exception as e:
            print(f"Failed to fetch tracks for user {member.id}: {e}")
            # Continue with other users
            continue

    if not user_top_tracks:
        raise HTTPException(status_code=500, detail="Could not fetch tracks from any room member")

    # Step 5: Generate playlist
    try:
        # Use current user's access token for Spotify API calls
        access_token = await spotify_auth.get_valid_access_token(current_user)

        track_ids = await engine_generate_playlist(
            vibe_profile=vibe_profile,
            user_top_tracks_by_user=user_top_tracks,
            access_token=access_token,
            room_settings={"max_length": 30, "max_per_artist": 2}
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Playlist generation failed: {str(e)}")

    if not track_ids:
        raise HTTPException(status_code=500, detail="No tracks generated")

    # Step 6: Create Spotify playlist
    try:
        access_token = await spotify_auth.get_valid_access_token(current_user)
        profile = await spotify_auth.get_user_profile(access_token)
        spotify_user_id = profile["id"]

        playlist_name = f"VibeRooms - {room.code}"
        playlist_description = f"Collaborative playlist for room {room.code}"

        spotify_playlist = await create_spotify_playlist(
            access_token=access_token,
            user_id=spotify_user_id,
            name=playlist_name,
            description=playlist_description,
            public=True
        )

        # Step 7: Add tracks
        track_uris = [f"spotify:track:{tid}" for tid in track_ids]
        await add_tracks_to_playlist(
            access_token=access_token,
            playlist_id=spotify_playlist["id"],
            track_uris=track_uris
        )

        # Step 8: Save to DB (optional - add Playlist model if needed)
        # For now, just return the result

        return {
            "message": "Playlist generated successfully",
            "playlist_id": spotify_playlist["id"],
            "playlist_url": spotify_playlist["external_urls"]["spotify"],
            "track_count": len(track_ids)
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create Spotify playlist: {str(e)}")

@app.get("/debug/vibe-profile/{room_id}")
async def debug_vibe_profile(
        room_id: int,
        db: AsyncSession = Depends(get_db),
        current_user: User = Depends(get_current_user)
):
    """Debug endpoint to see raw vibe profile data."""
    prefs = await get_preferences_for_room(db, room_id)

    # Show raw preference data
    raw_prefs = []
    for pref in prefs:
        raw_prefs.append({
            "user_id": pref.user_id,
            "genres_raw": pref.genres,
            "genres_type": type(pref.genres).__name__,
            "hard_nos_raw": pref.hard_nos,
            "hard_nos_type": type(pref.hard_nos).__name__
        })

    # Generate vibe profile
    vibe = generate_vibe_profile(prefs)

    return {
        "raw_preferences": raw_prefs,
        "vibe_profile": vibe,
        "target_genres_type": type(vibe["target_genres"]).__name__
    }
# ============================================================
# CREATE TABLES ON STARTUP
# ============================================================



@app.on_event("startup")
async def on_startup():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
