import os
from typing import List, Dict, Any

SMART_BROLL_PRESETS = [
    {
        "id": "ai_gemini",
        "name": "✨ Gemini AI Ultra (Custom Generated 9:16 Scenes)",
        "description": "Google Gemini 3.6 crafts photorealistic visuals per sentence with zero repeats",
        "target_cut": 2.2
    },
    {
        "id": "smart_fast",
        "name": "⚡ Rapid Authentic Archive (Image Cut Every ~1.8s)",
        "description": "High-retention historical archive cuts with dynamic camera motion",
        "target_cut": 1.8
    },
    {
        "id": "smart_standard",
        "name": "🎬 Dynamic Documentary (Image Cut Every ~2.4s)",
        "description": "Professional documentary pacing matching words of script",
        "target_cut": 2.4
    },
    {
        "id": "smart_cinematic",
        "name": "🎥 Cinematic Storytelling (Image Cut Every ~3.2s)",
        "description": "Grand atmospheric camera drifts for deep stories & history",
        "target_cut": 3.2
    }
]


def get_available_backgrounds(backgrounds_dir: str = "assets/backgrounds") -> List[Dict[str, Any]]:
    """List Smart AI B-Roll pacing styles and any user-uploaded files."""
    items = []
    
    # 1. Smart AI B-Roll Pacing Presets (Only auto-fetch smart b-roll)
    for p in SMART_BROLL_PRESETS:
        items.append({
            "id": p["id"],
            "type": "smart",
            "name": p["name"],
            "description": p["description"],
            "target_cut": p["target_cut"]
        })

    # 2. Only custom uploaded files if user explicitly dropped one
    if os.path.exists(backgrounds_dir):
        for fname in sorted(os.listdir(backgrounds_dir)):
            if fname.lower().endswith(('.mp4', '.mov', '.mkv', '.webm')):
                base = os.path.splitext(fname)[0].replace('_', ' ').replace('-', ' ').title()
                items.append({
                    "id": f"file_{fname}",
                    "type": "file",
                    "filename": fname,
                    "name": f"📁 Uploaded: {base}",
                    "description": f"Custom clip ({fname})"
                })

    return items

def get_target_cut_duration(bg_choice: str) -> float:
    """Return cut duration for the chosen style."""
    if bg_choice == "ai_gemini":
        return 2.2
    elif bg_choice == "smart_fast":
        return 1.8
    elif bg_choice == "smart_cinematic":
        return 3.2
    return 2.4 # default standard

