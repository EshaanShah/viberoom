# backend/schemas.py

from typing import Optional, List
from pydantic import BaseModel
from datetime import datetime


# ================================================
# BASE SCHEMAS (shared fields)
# ================================================

class UserBase(BaseModel):
    spotify_id: str
    display_name: Optional[str] = None
    avatar_url: Optional[str] = None


# ================================================
# USER SCHEMAS
# ================================================

class UserCreate(UserBase):
    """Used internally for creating user entries."""
    refresh_token: Optional[str] = None


class UserOut(UserBase):
    """Returned to frontend. Notice: refresh_token is NOT included."""
    id: int
    created_at: datetime

    class Config:
        orm_mode = True


# ================================================
# ROOM SCHEMAS
# ================================================

class RoomBase(BaseModel):
    code: str
    is_active: bool = True


class RoomCreate(BaseModel):
    """Frontend does not provide a code. Backend generates it."""
    pass


class RoomOut(BaseModel):
    id: int
    code: str
    host_user_id: int
    is_active: bool
    created_at: datetime

    class Config:
        orm_mode = True



# ================================================
# ROOM MEMBER SCHEMAS
# ================================================

class RoomMemberOut(BaseModel):
    id: int
    room_id: int
    user_id: int
    joined_at: datetime

    class Config:
        orm_mode = True


# ================================================
# PREFERENCES SCHEMAS
# ================================================

class PreferencesCreate(BaseModel):
    event_type: str
    genres: List[str]
    energy_level: int
    new_vs_familiar: str
    hard_nos: List[str]


class PreferencesOut(BaseModel):
    id: int
    room_id: int
    user_id: int
    event_type: str
    genres: List[str]
    energy_level: int
    new_vs_familiar: str
    hard_nos: List[str]
    created_at: datetime

    class Config:
        orm_mode = True


# ================================================
# PLAYLIST SCHEMAS
# ================================================

class PlaylistOut(BaseModel):
    id: int
    room_id: int
    spotify_playlist_id: str
    url: Optional[str] = None
    track_count: int
    created_at: datetime

    class Config:
        orm_mode = True

