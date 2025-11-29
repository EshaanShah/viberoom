# backend/crud.py

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import User, Room, RoomMember, PreferenceProfile, Playlist

from backend.schemas import (
    UserCreate,
    PreferencesCreate
)
from datetime import datetime
import random
import string


# ======================================================
# USERS
# ======================================================

async def get_user_by_spotify_id(db: AsyncSession, spotify_id: str):
    """Return a user by their Spotify user ID."""
    result = await db.execute(
        select(User).where(User.spotify_id == spotify_id)
    )
    return result.scalars().first()


async def create_user(db: AsyncSession, data: UserCreate) -> User:
    """Create a new user in the database."""
    user = User(
        spotify_id=data.spotify_id,
        display_name=data.display_name,
        avatar_url=data.avatar_url,
        refresh_token=data.refresh_token,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


async def update_user_refresh_token(db: AsyncSession, spotify_id: str, new_refresh: str):
    """Update a user's refresh token when they re-login."""
    user = await get_user_by_spotify_id(db, spotify_id)
    if not user:
        return None

    user.refresh_token = new_refresh
    await db.commit()
    await db.refresh(user)
    return user


# ======================================================
# ROOMS
# ======================================================

def generate_room_code(length: int = 6) -> str:
    """Generate a random 6-character room code."""
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=length))


async def create_room(db: AsyncSession, host_user_id: int) -> Room:
    """Create a room hosted by the given user."""
    code = generate_room_code()

    room = Room(
        code=code,
        host_user_id=host_user_id,
        is_active=True
    )
    db.add(room)
    await db.commit()
    await db.refresh(room)
    return room


async def get_room_by_code(db: AsyncSession, code: str) -> Room:
    """Fetch a room using its join code."""
    result = await db.execute(
        select(Room).where(Room.code == code)
    )
    return result.scalars().first()


# ======================================================
# ROOM MEMBERS
# ======================================================

async def add_user_to_room(db: AsyncSession, room_id: int, user_id: int) -> RoomMember:
    """Add a user to a room."""
    member = RoomMember(room_id=room_id, user_id=user_id)
    db.add(member)
    await db.commit()
    await db.refresh(member)
    return member


async def get_room_members(db: AsyncSession, room_id: int):
    """Return all users in a room."""
    result = await db.execute(
        select(RoomMember).where(RoomMember.room_id == room_id)
    )
    return result.scalars().all()

async def get_room(db: AsyncSession, room_id: int):
    result = await db.execute(select(Room).where(Room.id == room_id))
    return result.scalar_one_or_none()


# ======================================================
# PREFERENCES
# ======================================================

async def save_preferences(
        db: AsyncSession,
        room_id: int,
        user_id: int,
        data: PreferencesCreate
) -> PreferenceProfile:

    """Create or update a preferences profile for a user in a room."""

    # Check if preferences already exist
    result = await db.execute(
        select(PreferenceProfile).where(
            PreferenceProfile.room_id == room_id,
            PreferenceProfile.user_id == user_id
        )
    )
    existing = result.scalars().first()

    if existing:
        # Update existing profile
        existing.event_type = data.event_type
        existing.genres = ",".join(data.genres)   # store as CSV string
        existing.energy_level = data.energy_level
        existing.new_vs_familiar = data.new_vs_familiar
        existing.hard_nos = ",".join(data.hard_nos)
        await db.commit()
        await db.refresh(existing)
        return existing

    # Create new profile
    prefs = PreferenceProfile(
        room_id=room_id,
        user_id=user_id,
        event_type=data.event_type,
        genres=",".join(data.genres),
        energy_level=data.energy_level,
        new_vs_familiar=data.new_vs_familiar,
        hard_nos=",".join(data.hard_nos)
    )
    db.add(prefs)
    await db.commit()
    await db.refresh(prefs)
    return prefs


# ======================================================
# PLAYLISTS
# ======================================================

async def save_playlist(
        db: AsyncSession,
        room_id: int,
        playlist_id: str,
        url: str,
        track_count: int
) -> Playlist:

    playlist = Playlist(
        room_id=room_id,
        spotify_playlist_id=playlist_id,
        url=url,
        track_count=track_count
    )
    db.add(playlist)
    await db.commit()
    await db.refresh(playlist)
    return playlist
