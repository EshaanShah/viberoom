import os
import secrets
from typing import Optional

from fastapi import FastAPI, Depends, HTTPException, status, Request
from fastapi.responses import JSONResponse, RedirectResponse
from pydantic import BaseModel
import jwt
from jwt import PyJWTError
from dotenv import load_dotenv
import httpx

# ---------- Load ENV ----------
load_dotenv()

SPOTIFY_CLIENT_ID = os.getenv("SPOTIFY_CLIENT_ID")
SPOTIFY_CLIENT_SECRET = os.getenv("SPOTIFY_CLIENT_SECRET")
SPOTIFY_REDIRECT_URI = os.getenv("SPOTIFY_REDIRECT_URI")
SPOTIFY_SCOPES = os.getenv("SPOTIFY_SCOPES", "user-top-read playlist-modify-private")
JWT_SECRET = os.getenv("JWT_SECRET", "devsecret")
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")

if not SPOTIFY_CLIENT_ID or not SPOTIFY_CLIENT_SECRET:
    raise RuntimeError("Missing SPOTIFY_CLIENT_ID or SPOTIFY_CLIENT_SECRET in .env")

app = FastAPI(title="VibeRooms Backend")

# In-memory "DB" for now — we'll move to real DB in Phase 2
fake_user_store = {}   # key: spotify_id, value: dict with tokens + profile
fake_state_store = {}  # key: state, value: True (for CSRF protection)


# ---------- Models ----------

class TokenResponse(BaseModel):
    access_token: str
    token_type: str
    expires_in: int
    refresh_token: Optional[str] = None
    scope: Optional[str] = None


class AppUser(BaseModel):
    id: str               # spotify id
    display_name: str
    avatar_url: Optional[str] = None


class AuthResult(BaseModel):
    user: AppUser
    app_token: str        # our own JWT used by frontend to call API


# ---------- JWT Helpers ----------

def create_app_jwt(spotify_id: str) -> str:
    payload = {"sub": spotify_id}
    token = jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)
    return token


def decode_app_jwt(token: str) -> str:
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return payload["sub"]
    except PyJWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication token",
        )


async def get_current_user(request: Request) -> AppUser:
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid Authorization header")

    token = auth_header.split(" ", 1)[1]
    spotify_id = decode_app_jwt(token)

    user_data = fake_user_store.get(spotify_id)
    if not user_data:
        raise HTTPException(status_code=401, detail="User not found")

    return AppUser(
        id=spotify_id,
        display_name=user_data["display_name"],
        avatar_url=user_data.get("avatar_url"),
    )


# ---------- Basic Test Route ----------

@app.get("/")
def root():
    return {"status": "ok", "message": "VibeRooms backend running"}

from urllib.parse import urlencode

SPOTIFY_AUTH_URL = "https://accounts.spotify.com/authorize"
SPOTIFY_TOKEN_URL = "https://accounts.spotify.com/api/token"
SPOTIFY_API_BASE = "https://api.spotify.com/v1"


@app.get("/auth/login")
def spotify_login():
    # Generate a random state string for CSRF protection
    state = secrets.token_urlsafe(16)
    fake_state_store[state] = True

    params = {
        "client_id": SPOTIFY_CLIENT_ID,
        "response_type": "code",
        "redirect_uri": SPOTIFY_REDIRECT_URI,
        "scope": SPOTIFY_SCOPES,
        "state": state,
        "show_dialog": "false",
    }
    url = f"{SPOTIFY_AUTH_URL}?{urlencode(params)}"
    return {"auth_url": url}

@app.get("/auth/callback")
async def spotify_callback(code: str, state: str):
    # 1) Validate state (simple CSRF protection)
    if state not in fake_state_store:
        raise HTTPException(status_code=400, detail="Invalid state")
    fake_state_store.pop(state, None)

    # 2) Exchange code for tokens
    data = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": SPOTIFY_REDIRECT_URI,
        "client_id": SPOTIFY_CLIENT_ID,
        "client_secret": SPOTIFY_CLIENT_SECRET,
    }

    async with httpx.AsyncClient() as client:
        token_resp = await client.post(SPOTIFY_TOKEN_URL, data=data)
    if token_resp.status_code != 200:
        print(token_resp.text)
        raise HTTPException(status_code=400, detail="Failed to get token from Spotify")

    tokens = token_resp.json()
    access_token = tokens["access_token"]
    refresh_token = tokens.get("refresh_token")

    # 3) Use access token to fetch Spotify profile
    headers = {"Authorization": f"Bearer {access_token}"}
    async with httpx.AsyncClient() as client:
        me_resp = await client.get(f"{SPOTIFY_API_BASE}/me", headers=headers)

    if me_resp.status_code != 200:
        print(me_resp.text)
        raise HTTPException(status_code=400, detail="Failed to get Spotify profile")

    me_data = me_resp.json()
    spotify_id = me_data["id"]
    display_name = me_data.get("display_name") or spotify_id
    images = me_data.get("images") or []
    avatar_url = images[0]["url"] if images else None

    # 4) "Save" user in our in-memory store (Phase 1; real DB in Phase 2)
    fake_user_store[spotify_id] = {
        "display_name": display_name,
        "avatar_url": avatar_url,
        "access_token": access_token,
        "refresh_token": refresh_token,
        "raw": me_data,
    }

    # 5) Create our own JWT (for frontend to call other endpoints)
    app_token = create_app_jwt(spotify_id)

    # For now just return JSON.
    # Later you might redirect back to frontend with this token as a query param.
    return AuthResult(
        user=AppUser(id=spotify_id, display_name=display_name, avatar_url=avatar_url),
        app_token=app_token,
    )

class RefreshRequest(BaseModel):
    app_token: str


@app.post("/auth/refresh")
async def refresh_spotify_token(body: RefreshRequest):
    # Decode our own app token to get spotify_id
    spotify_id = decode_app_jwt(body.app_token)
    user_data = fake_user_store.get(spotify_id)
    if not user_data:
        raise HTTPException(status_code=401, detail="User not found")

    refresh_token = user_data.get("refresh_token")
    if not refresh_token:
        raise HTTPException(status_code=400, detail="No refresh token stored")

    data = {
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
        "client_id": SPOTIFY_CLIENT_ID,
        "client_secret": SPOTIFY_CLIENT_SECRET,
    }

    async with httpx.AsyncClient() as client:
        resp = await client.post(SPOTIFY_TOKEN_URL, data=data)

    if resp.status_code != 200:
        print(resp.text)
        raise HTTPException(status_code=400, detail="Failed to refresh token")

    new_tokens = resp.json()
    new_access_token = new_tokens["access_token"]

    # Optional: Spotify sometimes returns a new refresh_token
    new_refresh_token = new_tokens.get("refresh_token") or refresh_token

    user_data["access_token"] = new_access_token
    user_data["refresh_token"] = new_refresh_token

    return {"status": "ok"}
@app.get("/me/app")
async def get_me_app(user: AppUser = Depends(get_current_user)):
    """
    Returns the currently authenticated app user (based on our JWT).
    Frontend should send:
      Authorization: Bearer <app_token>
    """
    return user

