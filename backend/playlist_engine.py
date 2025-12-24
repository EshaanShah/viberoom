from typing import List, Dict, Any, Tuple


# ---------------------------
# Public entry point
# ---------------------------

def generate_playlist(
        room_vibe_profile: Dict[str, Any],
        candidate_songs: List[Dict[str, Any]],
        room_settings: Dict[str, Any] | None = None
) -> List[Dict[str, Any]]:

    if not room_vibe_profile or not candidate_songs:
        return []

    # Normalize inputs
    vibe = normalize_vibe_profile(room_vibe_profile)
    songs = normalize_songs(candidate_songs)

    # Filter hard-no genres
    hard_nos = set(vibe["hard_no_genres"])
    songs = [
        s for s in songs
        if not hard_nos.intersection(s["genres"])
    ]

    if not songs:
        return []

    # Score songs
    scored = score_songs(vibe, songs)

    # Rank songs
    ranked = rank_songs(scored)

    # Apply constraints
    final_playlist = apply_constraints(ranked, room_settings)

    return final_playlist


# ---------------------------
# Vibe handling
# ---------------------------

def normalize_vibe_profile(vibe: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "target_genres": [g.lower() for g in vibe.get("target_genres", [])],
        "energy": clamp(vibe.get("energy", 0.5)),
        "new_vs_familiar": clamp(vibe.get("new_vs_familiar", 0.5)),
        "hard_no_genres": [g.lower() for g in vibe.get("hard_no_genres", [])],
        "event_type": vibe.get("event_type")
    }


# ---------------------------
# Song preparation
# ---------------------------

def normalize_songs(songs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    normalized = []

    for s in songs:
        song_id = s.get("id") or s.get("uri")
        if not song_id:
            continue

        genres = s.get("genres", [])
        if isinstance(genres, str):
            genres = [genres]

        normalized.append({
            "id": song_id,
            "genres": [g.lower() for g in genres],
            "energy": clamp(s.get("energy", 0.5)),
            "popularity": s.get("popularity", 50),
            "artist": s.get("artist")
        })

    return normalized


# ---------------------------
# Scoring logic
# ---------------------------

def score_songs(
        vibe: Dict[str, Any],
        songs: List[Dict[str, Any]]
) -> List[Tuple[Dict[str, Any], float]]:

    scored = []

    for song in songs:
        score = compute_similarity_score(vibe, song)
        scored.append((song, score))

    return scored


def compute_similarity_score(
        vibe: Dict[str, Any],
        song: Dict[str, Any]
) -> float:
    # Genre score
    genre_matches = len(
        set(song["genres"]).intersection(vibe["target_genres"])
    )
    genre_score = genre_matches / max(1, len(vibe["target_genres"]))

    # Energy score (closer is better)
    energy_score = 1 - abs(song["energy"] - vibe["energy"])

    # Familiarity proxy (using popularity)
    popularity_norm = clamp(song["popularity"] / 100)
    familiarity_score = (
        1 - popularity_norm
        if vibe["new_vs_familiar"] > 0.5
        else popularity_norm
    )

    # Final weighted score
    return (
            0.6 * genre_score +
            0.25 * energy_score +
            0.15 * familiarity_score
    )


# ---------------------------
# Ranking & constraints
# ---------------------------

def rank_songs(
        scored_songs: List[Tuple[Dict[str, Any], float]]
) -> List[Dict[str, Any]]:
    scored_songs.sort(key=lambda x: x[1], reverse=True)
    return [s for s, _ in scored_songs]


def apply_constraints(
        ranked_songs: List[Dict[str, Any]],
        room_settings: Dict[str, Any] | None
) -> List[Dict[str, Any]]:

    max_length = 50
    max_per_artist = 2

    if room_settings:
        max_length = room_settings.get("max_length", max_length)
        max_per_artist = room_settings.get("max_per_artist", max_per_artist)

    seen = set()
    artist_counts = {}
    final = []

    for song in ranked_songs:
        if song["id"] in seen:
            continue

        artist = song.get("artist")
        if artist:
            artist_counts[artist] = artist_counts.get(artist, 0) + 1
            if artist_counts[artist] > max_per_artist:
                continue

        seen.add(song["id"])
        final.append(song)

        if len(final) >= max_length:
            break

    return final


# ---------------------------
# Utilities
# ---------------------------

def clamp(val: float, min_val: float = 0.0, max_val: float = 1.0) -> float:
    try:
        return max(min_val, min(max_val, float(val)))
    except (TypeError, ValueError):
        return 0.5
