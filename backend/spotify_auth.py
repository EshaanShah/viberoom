import os
import base64
import httpx
from urllib.parse import urlencode

from dotenv import load_dotenv

load_dotenv()

SPOTIFY_CLIENT_ID = os.getenv("SPOTIFY_CLIENT_ID")
SPOTIFY_CLIENT_SECRET = os.getenv("SPOTIFY_CLIENT_SECRET")
SPOTIFY_REDIRECT_URI = os.getenv("SPOTIFY_REDIRECT_URI")
SPOTIFY_SCOPES = os.getenv("SPOTIFY_SCOPES")

# For your own app JWT
from .auth import create_app_token


# ----------------------------------------------------------
# STEP 1 — Build Spotify Authorization URL
# ----------------------------------------------------------

def build_auth_url():
    params = {
        "client_id": SPOTIFY_CLIENT_ID,
        "response_type": "code",
        "redirect_uri": SPOTIFY_REDIRECT_URI,
        "scope": SPOTIFY_SCOPES,
    }
    return "https://accounts.spotify.com/authorize?" + urlencode(params)


# ----------------------------------------------------------
# STEP 2 — Exchange Authorization Code for Access Token
# ----------------------------------------------------------

async def exchange_code_for_token(code: str):
    token_url = "https://accounts.spotify.com/api/token"

    basic_auth = base64.b64encode(
        f"{SPOTIFY_CLIENT_ID}:{SPOTIFY_CLIENT_SECRET}".encode()
    ).decode()

    headers = {
        "Authorization": f"Basic {basic_auth}",
        "Content-Type": "application/x-www-form-urlencoded",
    }

    data = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": SPOTIFY_REDIRECT_URI,
    }

    async with httpx.AsyncClient() as client:
        res = await client.post(token_url, headers=headers, data=data)
        return res.json()


# ----------------------------------------------------------
# STEP 3 — Refresh token (used later)
# ----------------------------------------------------------

async def refresh_access_token(refresh_token: str):
    token_url = "https://accounts.spotify.com/api/token"

    basic_auth = base64.b64encode(
        f"{SPOTIFY_CLIENT_ID}:{SPOTIFY_CLIENT_SECRET}".encode()
    ).decode()

    headers = {
        "Authorization": f"Basic {basic_auth}",
        "Content-Type": "application/x-www-form-urlencoded",
    }

    data = {
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
    }

    async with httpx.AsyncClient() as client:
        res = await client.post(token_url, headers=headers, data=data)
        return res.json()


# ----------------------------------------------------------
# STEP 4 — Get Spotify Profile using Access Token
# ----------------------------------------------------------

async def get_user_profile(access_token: str):
    url = "https://api.spotify.com/v1/me"
    headers = {"Authorization": f"Bearer {access_token}"}

    async with httpx.AsyncClient() as client:
        res = await client.get(url, headers=headers)
        return res.json()

async def get_valid_access_token(user):
    token_data = await refresh_access_token(user.refresh_token)

    if "access_token" not in token_data:
        raise Exception(f"Spotify token refresh failed: {token_data}")

    return token_data["access_token"]


async def get_top_tracks(access_token: str, limit: int = 50):
    url = "https://api.spotify.com/v1/me/top/tracks"
    headers = {"Authorization": f"Bearer {access_token}"}
    params = {"limit": limit, "time_range": "medium_term"}

    async with httpx.AsyncClient() as client:
        res = await client.get(url, headers=headers, params=params)
        return res.json()["items"]

async def get_audio_features(access_token: str, track_ids: list[str]):
    url = "https://api.spotify.com/v1/audio-features"
    headers = {"Authorization": f"Bearer {access_token}"}

    params = {
        "ids": ",".join(track_ids[:1])  # max 100
    }

    async with httpx.AsyncClient() as client:
        res = await client.get(url, headers=headers, params=params)
        data = res.json()

    if "audio_features" not in data:
        raise Exception(f"Spotify audio-features error: {data}")

    return data["audio_features"]
