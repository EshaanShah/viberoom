import httpx
from typing import List, Dict, Optional

RECCOBEATS_BASE_URL = "https://reccobeats.com/api"

async def get_audio_features_batch(track_ids: List[str]) -> Dict[str, Dict]:
    """
    Fetch audio features from ReccoBeats for multiple tracks.

    Returns:
        {
            "track_id_1": {"energy": 0.8, "valence": 0.6, ...},
            "track_id_2": {"energy": 0.5, "valence": 0.3, ...},
            ...
        }
    """
    if not track_ids:
        return {}

    features_map = {}

    async with httpx.AsyncClient(timeout=30.0) as client:
        # ReccoBeats API takes comma-separated IDs
        ids_param = ",".join(track_ids)

        try:
            response = await client.get(
                f"{RECCOBEATS_BASE_URL}/track/audio-features",
                params={"ids": ids_param}
            )
            response.raise_for_status()
            data = response.json()

            # Expected format: {"audio_features": [{id, energy, valence, ...}, ...]}
            for feature in data.get("audio_features", []):
                if feature and feature.get("id"):
                    features_map[feature["id"]] = {
                        "energy": feature.get("energy", 0.5),
                        "valence": feature.get("valence", 0.5),
                        "danceability": feature.get("danceability", 0.5),
                        "tempo": feature.get("tempo", 120),
                    }

        except httpx.HTTPError as e:
            # Log error but don't crash - caller will handle missing features
            print(f"ReccoBeats API error: {e}")
            raise Exception(f"Failed to fetch audio features from ReccoBeats: {str(e)}")

    return features_map


async def get_audio_features_single(track_id: str) -> Optional[Dict]:
    """Fetch audio features for a single track."""
    result = await get_audio_features_batch([track_id])
    return result.get(track_id)