import os
from typing import List, Dict, Any

BGM_TRACKS = {
    "lofi_chill": {
        "name": "Lo-Fi Chill (Warm Jazz & Vinyl)",
        "file": "assets/bgm/lofi_chill.wav",
        "description": "Relaxing, thoughtful, life advice & psychology"
    },
    "phonk_energetic": {
        "name": "Phonk Viral Beat (Aggressive 808)",
        "file": "assets/bgm/phonk_energetic.wav",
        "description": "High BPM, gym, gaming, fast facts & motivation"
    },
    "epic_cinematic": {
        "name": "Epic Cinematic (Motivational Taiko Drums)",
        "file": "assets/bgm/epic_cinematic.wav",
        "description": "Grand historical facts, breakthroughs & inspiration"
    },
    "mystery_suspense": {
        "name": "Dark Mystery (Creepy Tension & Drone)",
        "file": "assets/bgm/mystery_suspense.wav",
        "description": "Unsolved mysteries, conspiracies, shocking revelations"
    },
    "none": {
        "name": "None (Voiceover Only)",
        "file": None,
        "description": "Clean vocal without any background audio"
    }
}

def get_available_bgm() -> List[Dict[str, Any]]:
    """Return available BGM tracks."""
    tracks = []
    for key, val in BGM_TRACKS.items():
        tracks.append({
            "id": key,
            "name": val["name"],
            "description": val["description"],
            "has_file": val["file"] is not None and os.path.exists(val["file"])
        })
    return tracks

def get_bgm_file_path(track_id: str) -> str:
    """Return filepath for BGM track if exists."""
    info = BGM_TRACKS.get(track_id)
    if info and info["file"] and os.path.exists(info["file"]):
        return info["file"]
    return None
