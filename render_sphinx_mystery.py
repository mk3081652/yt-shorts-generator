"""
Script to automatically render a cinematic mystery YouTube Short:
'The Secret Chamber Beneath the Great Sphinx'
Uses generated 9:16 images, sidechain audio ducking, sub-bass riser, whoosh SFX,
safe-zone kinetic subtitles, 35mm film grain, and YPP monetization metadata.
"""

import os
import sys
import shutil
import json
import uuid

# Windows UTF-8 stdout fix
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

from engine.render import render_shorts_video
from engine.metadata import generate_youtube_metadata

img_dir = r"C:\Users\mk308\.gemini\antigravity\brain\8f84bef5-5fa8-4d43-9df8-8816f6204ee6"
img1 = os.path.join(img_dir, "sphinx_radar_expedition_1790093101569.jpg")
img2 = os.path.join(img_dir, "sphinx_subterranean_chamber_1790093114786.jpg")
img3 = os.path.join(img_dir, "sphinx_classified_telemetry_1790093127744.jpg")
img4 = os.path.join(img_dir, "sphinx_ancient_vault_seal_1790093142093.jpg")

os.makedirs("outputs/custom_scenes", exist_ok=True)
dest1 = os.path.abspath("outputs/custom_scenes/sphinx_s1.jpg")
dest2 = os.path.abspath("outputs/custom_scenes/sphinx_s2.jpg")
dest3 = os.path.abspath("outputs/custom_scenes/sphinx_s3.jpg")
dest4 = os.path.abspath("outputs/custom_scenes/sphinx_s4.jpg")

shutil.copyfile(img1, dest1)
shutil.copyfile(img2, dest2)
shutil.copyfile(img3, dest3)
shutil.copyfile(img4, dest4)

script_text = (
    "Stop scrolling right now, because historians are hiding what seismologists discovered beneath the Great Sphinx! "
    "In 1993, geophysicists conducted ground-penetrating radar scans around the limestone paws of the monument. "
    "Their acoustic sensors registered something impossible: a massive, hollow geometric chamber carved directly into bedrock, thirty feet underground. "
    "But before independent excavation could begin, government authorities abruptly halted the expedition and classified the raw telemetry. "
    "Could this be the legendary Hall of Records, or proof of an advanced civilization predating ancient Egypt? "
    "Drop your theory in the comments, and subscribe for the truth."
)

preview_scenes = [
    {
        "id": "scene_1",
        "text": "Stop scrolling right now, because historians are hiding what seismologists discovered beneath the Great Sphinx! In 1993, geophysicists conducted ground-penetrating radar scans around the limestone paws of the monument.",
        "media_path": dest1,
        "media_type": "image",
        "motion": "zoom_in",
        "duration": 9.0,
        "hook_text": "WHAT'S UNDER THE SPHINX?",
        "high_impact_words": ["Stop", "scrolling", "hiding", "Sphinx", "1993", "radar"]
    },
    {
        "id": "scene_2",
        "text": "Their acoustic sensors registered something impossible: a massive, hollow geometric chamber carved directly into bedrock, thirty feet underground.",
        "media_path": dest2,
        "media_type": "image",
        "motion": "parallax_25d",
        "duration": 9.5,
        "high_impact_words": ["impossible", "massive", "hollow", "chamber", "thirty", "bedrock"]
    },
    {
        "id": "scene_3",
        "text": "But before independent excavation could begin, government authorities abruptly halted the expedition and classified the raw telemetry.",
        "media_path": dest3,
        "media_type": "image",
        "motion": "pan_right",
        "duration": 9.0,
        "high_impact_words": ["halted", "classified", "telemetry", "expedition", "authorities"]
    },
    {
        "id": "scene_4",
        "text": "Could this be the legendary Hall of Records, or proof of an advanced civilization predating ancient Egypt? Drop your theory in the comments, and subscribe for the truth.",
        "media_path": dest4,
        "media_type": "image",
        "motion": "zoom_out",
        "duration": 9.5,
        "high_impact_words": ["legendary", "Hall", "Records", "advanced", "civilization", "Egypt", "subscribe"]
    }
]

def progress(msg, pct):
    print(f"[{pct}%] {msg}")

print("=== Starting Automatic Mystery Short Generation ===")
res = render_shorts_video(
    script_text=script_text,
    voice="en-US-ChristopherNeural",
    voice_rate="+10%",
    subtitle_style="hyper_yellow",
    bgm_track="mystery_suspense",
    bgm_volume=0.18,
    progress_callback=progress,
    preview_scenes=preview_scenes,
    motion_texture="film_grain",
    transition_style="crossfade"
)

output_video = os.path.abspath("outputs/sphinx_mystery_short.mp4")
shutil.copyfile(res["video_path"], output_video)

# Generate and save YouTube Metadata with YPP disclosures
metadata = generate_youtube_metadata(script_text)
meta_path = os.path.abspath("outputs/sphinx_mystery_short_metadata.json")
with open(meta_path, "w", encoding="utf-8") as f:
    json.dump(metadata, f, indent=2, ensure_ascii=False)

print("\n" + "=" * 50)
print(f"SUCCESS! Mystery YouTube Short rendered in {res['duration']}s")
print(f"Video File: {output_video}")
print(f"Metadata File: {meta_path}")
print(f"Title: {metadata.get('title')}")
print(f"YPP Disclosure: {metadata.get('compliance_notes')}")
print("=" * 50)
