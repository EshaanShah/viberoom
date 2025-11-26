from sqlalchemy import Column, Integer, String, Boolean, ForeignKey, DateTime, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from .database import Base


# =====================
# USERS TABLE
# =====================
class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    spotify_id = Column(String, unique=True, nullable=False)
    display_name = Column(String)
    avatar_url = Column(String)
    refresh_token = Column(String)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    hosted_rooms = relationship("Room", back_populates="host")
    room_memberships = relationship("RoomMember", back_populates="user")


# =====================
# ROOMS TABLE
# =====================
class Room(Base):
    __tablename__ = "rooms"

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String, unique=True, nullable=False)
    host_user_id = Column(Integer, ForeignKey("users.id"))
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    host = relationship("User", back_populates="hosted_rooms")
    members = relationship("RoomMember", back_populates="room")
    preferences = relationship("PreferenceProfile", back_populates="room")
    playlists = relationship("Playlist", back_populates="room")


# =====================
# ROOM MEMBERS TABLE
# =====================
class RoomMember(Base):
    __tablename__ = "room_members"

    id = Column(Integer, primary_key=True, index=True)
    room_id = Column(Integer, ForeignKey("rooms.id"))
    user_id = Column(Integer, ForeignKey("users.id"))
    joined_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    room = relationship("Room", back_populates="members")
    user = relationship("User", back_populates="room_memberships")


# =====================
# PREFERENCE PROFILES TABLE
# =====================
class PreferenceProfile(Base):
    __tablename__ = "preferences"

    id = Column(Integer, primary_key=True, index=True)
    room_id = Column(Integer, ForeignKey("rooms.id"))
    user_id = Column(Integer, ForeignKey("users.id"))

    event_type = Column(String)
    genres = Column(Text)  # store JSON-encoded list
    energy_level = Column(Integer)
    new_vs_familiar = Column(String)
    hard_nos = Column(Text)

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    room = relationship("Room", back_populates="preferences")
    user = relationship("User")


# =====================
# PLAYLIST TABLE
# =====================
class Playlist(Base):
    __tablename__ = "playlists"

    id = Column(Integer, primary_key=True, index=True)
    room_id = Column(Integer, ForeignKey("rooms.id"))
    spotify_playlist_id = Column(String, nullable=False)
    url = Column(String)
    track_count = Column(Integer)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    room = relationship("Room", back_populates="playlists")
