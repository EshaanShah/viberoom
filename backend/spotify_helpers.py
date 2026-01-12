import httpx
from typing import List, Dict, Any

SPOTIFY_API_BASE = "https://api.spotify.com/v1"


async def get_user_top_tracks(access_token: str, limit: int = 50) -> List[Dict]:
    """
    Fetch user's top tracks from Spotify.

    Returns list of track objects with id, name, artists, popularity, etc.
    """
    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"{SPOTIFY_API_BASE}/me/top/tracks",
            headers={"Authorization": f"Bearer {access_token}"},
            params={"limit": limit, "time_range": "medium_term"}
        )
        response.raise_for_status()
        data = response.json()
        return data.get("items", [])


async def get_spotify_recommendations(
        access_token: str,
        vibe_profile: Dict[str, Any],
        seed_tracks: List[str] = None,
        limit: int = 100
) -> List[Dict]:
    """
    Get track recommendations from Spotify based on vibe profile.

    Args:
        access_token: Valid Spotify access token
        vibe_profile: Output from vibe_engine.generate_vibe_profile()
        seed_tracks: Optional list of track IDs to seed recommendations
        limit: Number of recommendations to fetch (max 100)

    Returns:
        List of track objects
    """
    # Convert vibe profile to Spotify parameters
    target_genres = vibe_profile.get("target_genres", [])[:5]  # Spotify limit
    energy_normalized = vibe_profile.get("energy", 5.0) / 10.0  # Convert 1-10 to 0-1
    new_vs_familiar = vibe_profile.get("new_vs_familiar", 0.5)

    # Calculate popularity range based on new_vs_familiar
    # 0 = familiar (high popularity), 1 = new (low popularity)
    if new_vs_familiar < 0.5:
        # Lean familiar
        min_popularity = int(50 + (50 * (1 - new_vs_familiar * 2)))
        max_popularity = 100
    else:
        # Lean discovery
        min_popularity = 0
        max_popularity = int(50 - (50 * (new_vs_familiar - 0.5) * 2))

    params = {
        "limit": min(limit, 100),
        "target_energy": energy_normalized,
    }

    # Add seed genres
    if target_genres:
        params["seed_genres"] = ",".join(target_genres[:5])

    # Add seed tracks if provided (max 5 total seeds)
    if seed_tracks:
        available_seed_slots = 5 - len(target_genres)
        if available_seed_slots > 0:
            params["seed_tracks"] = ",".join(seed_tracks[:available_seed_slots])

    # Add popularity constraints
    params["min_popularity"] = min_popularity
    params["max_popularity"] = max_popularity

    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"{SPOTIFY_API_BASE}/recommendations",
            headers={"Authorization": f"Bearer {access_token}"},
            params=params
        )
        response.raise_for_status()
        data = response.json()
        return data.get("tracks", [])


async def create_spotify_playlist(
        access_token: str,
        user_id: str,
        name: str,
        description: str = "",
        public: bool = True
) -> Dict:
    """Create a new Spotify playlist."""
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{SPOTIFY_API_BASE}/users/{user_id}/playlists",
            headers={"Authorization": f"Bearer {access_token}"},
            json={
                "name": name,
                "description": description,
                "public": public
            }
        )
        response.raise_for_status()
        return response.json()


async def add_tracks_to_playlist(
        access_token: str,
        playlist_id: str,
        track_uris: List[str]
) -> None:
    """Add tracks to an existing Spotify playlist."""
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{SPOTIFY_API_BASE}/playlists/{playlist_id}/tracks",
            headers={"Authorization": f"Bearer {access_token}"},
            json={"uris": track_uris}
        )
        response.raise_for_status()


def extract_track_genres(track: Dict) -> List[str]:
    """
    Extract genres from a Spotify track object.
    Spotify tracks don't have genres directly, so we get them from artists.
    """
    genres = []
    for artist in track.get("artists", []):
        # Note: Artist objects in track responses don't include genres
        # You'll need to fetch full artist objects separately if needed
        # For now, return empty list - we'll filter at recommendation stage
        pass
    return genres