import json
from collections import Counter


NEW_VS_FAMILIAR_MAP = {
    "familiar": 0.0,
    "mix": 0.5,
    "new": 1.0
}


def generate_vibe_profile(preferences):
    if not preferences:
        return None

    all_genres = []
    all_hard_nos = set()
    energy_values = []
    new_vs_familiar_values = []
    event_types = []

    for p in preferences:
        # ✅ Parse comma-separated strings into lists
        genres = parse_comma_separated(p.genres)
        hard_nos = parse_comma_separated(p.hard_nos)

        all_genres.extend(genres)
        all_hard_nos.update(hard_nos)

        energy_values.append(p.energy_level)
        event_types.append(p.event_type)

        new_vs_familiar_values.append(
            NEW_VS_FAMILIAR_MAP.get(p.new_vs_familiar, 0.5)
        )

    # Remove hard-no genres globally
    genre_counts = Counter(all_genres)
    for g in all_hard_nos:
        genre_counts.pop(g, None)

    target_genres = [g for g, _ in genre_counts.most_common(5)]

    return {
        "target_genres": target_genres,
        "energy": round(sum(energy_values) / len(energy_values) / 10, 2),
        "new_vs_familiar": round(
            sum(new_vs_familiar_values) / len(new_vs_familiar_values), 2
        ),
        "hard_no_genres": list(all_hard_nos),
        "event_type": Counter(event_types).most_common(1)[0][0]
    }


def parse_comma_separated(value):
    """
    Parse a comma-separated string into a list of strings.
    Handles multiple formats: CSV string, JSON array, or already a list.
    """
    # If it's already a list, return it
    if isinstance(value, list):
        return value

    # If it's None or empty, return empty list
    if not value:
        return []

    # If it's a string, try to parse it
    if isinstance(value, str):
        value = value.strip()

        # Try JSON parsing first (for arrays like '["pop", "rock"]')
        if value.startswith('['):
            try:
                return json.loads(value)
            except json.JSONDecodeError:
                pass

        # Otherwise treat as comma-separated string
        if ',' in value:
            return [g.strip() for g in value.split(',') if g.strip()]

        # Single genre, no comma
        return [value] if value else []

    # Fallback
    return []