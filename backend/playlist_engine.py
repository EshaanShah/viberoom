from typing import List, Dict, Any, Tuple
import random


async def generate_playlist(
        vibe_profile: Dict[str, Any],
        user_top_tracks_by_user: Dict[int, List[Dict]],  # {user_id: [tracks]}
        access_token: str,
        room_settings: Dict[str, Any] = None
) -> List[str]:
    """
    Main playlist generation logic.
    
    Args:
        vibe_profile: Output from vibe_engine.generate_vibe_profile()
        user_top_tracks_by_user: Dict mapping user_id to their top tracks
        access_token: Valid Spotify access token for one user in the room
        room_settings: Optional constraints (max_length, max_per_artist)
    
    Returns:
        List of Spotify track IDs in ranked order
    """
    from . import spotify_helpers, reccobeats

    # Step 1: Build candidate pool
    candidate_songs = await build_candidate_pool(
        vibe_profile,
        user_top_tracks_by_user,
        access_token
    )

    if not candidate_songs:
        raise Exception("No candidate songs found")

    # Step 2: Fetch audio features from ReccoBeats
    track_ids = [s["id"] for s in candidate_songs]
    audio_features = await reccobeats.get_audio_features_batch(track_ids)

    # Step 3: Enrich songs with audio features
    enriched_songs = []
    for song in candidate_songs:
        features = audio_features.get(song["id"])
        if not features:
            # Skip songs without audio features
            continue

        enriched_songs.append({
            "id": song["id"],
            "name": song["name"],
            "artist": song["artists"][0]["name"] if song.get("artists") else "Unknown",
            "genres": song.get("genres", []),
            "energy": features["energy"],
            "popularity": song.get("popularity", 50),
        })

    # Step 4: Score and rank
    scored_songs = score_songs(vibe_profile, enriched_songs)
    ranked_songs = rank_songs(scored_songs)

    # Step 5: Apply constraints
    final_songs = apply_constraints(ranked_songs, vibe_profile, room_settings)

    # Return just the track IDs
    return [s["id"] for s in final_songs]


async def build_candidate_pool(
        vibe_profile: Dict[str, Any],
        user_top_tracks_by_user: Dict[int, List[Dict]],
        access_token: str
) -> List[Dict]:
    """
    Build candidate song pool by mixing user history and Spotify recommendations.
    
    Mix ratio determined by new_vs_familiar:
    - 0.0 = 100% user history, 0% recommendations
    - 0.5 = 50% user history, 50% recommendations  
    - 1.0 = 0% user history, 100% recommendations
    """
    from . import spotify_helpers

    new_vs_familiar = vibe_profile.get("new_vs_familiar", 0.5)

    # Combine all users' top tracks
    all_user_tracks = []
    for user_id, tracks in user_top_tracks_by_user.items():
        all_user_tracks.extend(tracks)

    # Deduplicate by track ID
    seen_ids = set()
    unique_user_tracks = []
    for track in all_user_tracks:
        if track["id"] not in seen_ids:
            seen_ids.add(track["id"])
            unique_user_tracks.append(track)

    # Calculate mix ratios
    target_total = 150  # Target candidate pool size
    familiar_count = int(target_total * (1 - new_vs_familiar))
    discovery_count = int(target_total * new_vs_familiar)

    # Sample from user tracks
    familiar_tracks = random.sample(
        unique_user_tracks,
        min(familiar_count, len(unique_user_tracks))
    )

    # Get discovery tracks from Spotify recommendations
    # Use some user tracks as seeds for better personalization
    seed_tracks = [t["id"] for t in random.sample(unique_user_tracks, min(3, len(unique_user_tracks)))]

    discovery_tracks = await spotify_helpers.get_spotify_recommendations(
        access_token=access_token,
        vibe_profile=vibe_profile,
        seed_tracks=seed_tracks,
        limit=discovery_count
    )

    # Combine and deduplicate
    all_candidates = familiar_tracks + discovery_tracks
    final_candidates = []
    final_ids = set()

    for track in all_candidates:
        if track["id"] not in final_ids:
            final_ids.add(track["id"])
            final_candidates.append(track)

    return final_candidates


def score_songs(
        vibe: Dict[str, Any],
        songs: List[Dict[str, Any]]
) -> List[Tuple[Dict[str, Any], float]]:
    """Score songs based on similarity to vibe profile."""
    scored = []
    for song in songs:
        score = compute_similarity_score(vibe, song)
        scored.append((song, score))
    return scored


def compute_similarity_score(
        vibe: Dict[str, Any],
        song: Dict[str, Any]
) -> float:
    """
    Compute similarity score between vibe profile and song.
    
    Weights:
    - 60% genre matching
    - 25% energy matching
    - 15% familiarity (popularity) matching
    """
    # Genre score
    song_genres = set(song.get("genres", []))
    target_genres = set(vibe.get("target_genres", []))

    if target_genres:
        genre_matches = len(song_genres.intersection(target_genres))
        genre_score = genre_matches / len(target_genres)
    else:
        genre_score = 0.5  # Neutral if no target genres

    # Energy score (vibe energy is 1-10, song energy is 0-1)
    vibe_energy_normalized = vibe.get("energy", 5.0) / 10.0
    song_energy = song.get("energy", 0.5)
    energy_score = 1 - abs(vibe_energy_normalized - song_energy)

    # Familiarity score (based on popularity and new_vs_familiar)
    popularity_norm = clamp(song.get("popularity", 50) / 100.0)
    new_vs_familiar = vibe.get("new_vs_familiar", 0.5)

    # If new_vs_familiar is high (want new), prefer low popularity
    # If new_vs_familiar is low (want familiar), prefer high popularity
    if new_vs_familiar > 0.5:
        familiarity_score = 1 - popularity_norm
    else:
        familiarity_score = popularity_norm

    # Weighted final score
    return (
            0.6 * genre_score +
            0.25 * energy_score +
            0.15 * familiarity_score
    )


def rank_songs(
        scored_songs: List[Tuple[Dict[str, Any], float]]
) -> List[Dict[str, Any]]:
    """Sort songs by score (highest first)."""
    scored_songs.sort(key=lambda x: x[1], reverse=True)
    return [song for song, score in scored_songs]


def apply_constraints(
        ranked_songs: List[Dict[str, Any]],
        vibe_profile: Dict[str, Any],
        room_settings: Dict[str, Any] = None
) -> List[Dict[str, Any]]:
    """
    Apply final constraints:
    - Remove duplicates
    - Limit tracks per artist
    - Filter hard-no genres
    - Enforce max playlist length
    """
    max_length = 50
    max_per_artist = 2

    if room_settings:
        max_length = room_settings.get("max_length", max_length)
        max_per_artist = room_settings.get("max_per_artist", max_per_artist)

    hard_no_genres = set(vibe_profile.get("hard_no_genres", []))

    seen_ids = set()
    artist_counts = {}
    final = []

    for song in ranked_songs:
        # Skip duplicates
        if song["id"] in seen_ids:
            continue

        # Skip hard-no genres
        song_genres = set(song.get("genres", []))
        if song_genres.intersection(hard_no_genres):
            continue

        # Limit per artist
        artist = song.get("artist")
        if artist:
            artist_counts[artist] = artist_counts.get(artist, 0) + 1
            if artist_counts[artist] > max_per_artist:
                continue

        seen_ids.add(song["id"])
        final.append(song)

        if len(final) >= max_length:
            break

    return final


def clamp(val: float, min_val: float = 0.0, max_val: float = 1.0) -> float:
    """Clamp value between min and max."""
    try:
        return max(min_val, min(max_val, float(val)))
    except (TypeError, ValueError):
        return 0.5