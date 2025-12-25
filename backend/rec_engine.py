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
        # Parse JSON fields
        genres = json.loads(p.genres) if p.genres else []
        hard_nos = json.loads(p.hard_nos) if p.hard_nos else []

        all_genres.extend(genres)
        all_hard_nos.update(hard_nos)

        energy_values.append(p.energy_level)
        event_types.append(p.event_type)

        # Convert string → numeric
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
        "energy": round((sum(energy_values) / len(energy_values)) / 10, 2),
        "new_vs_familiar": round(
            sum(new_vs_familiar_values) / len(new_vs_familiar_values), 2
        ),
        "hard_no_genres": list(all_hard_nos),
        "event_type": Counter(event_types).most_common(1)[0][0]
    }
