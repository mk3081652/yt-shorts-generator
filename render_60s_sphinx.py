"""
Script to render a 60-61 second full-length cinematic mystery YouTube Short:
'The Secret Chamber Beneath the Great Sphinx'
With 6 cinematic scenes, 2.5D parallax, safe-zone kinetic subtitles,
automated sidechain ducking, sub-bass riser, whoosh SFX, 35mm grain, and YPP metadata.
"""

import os
import sys
import shutil
import json

# Windows UTF-8 console output fix
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

from engine.render import render_shorts_video
from engine.metadata import generate_youtube_metadata

img_dir = r"C:\Users\mk308\.gemini\antigravity\brain\8f84bef5-5fa8-4d43-9df8-8816f6204ee6"
img1 = os.path.join(img_dir, "sphinx_radar_expedition_1790093101569.jpg")
img2 = os.path.join(img_dir, "sphinx_subterranean_chamber_1790093114786.jpg")
img3 = os.path.join(img_dir, "sphinx_tunnel_to_pyramid_1790093502288.jpg")
img4 = os.path.join(img_dir, "sphinx_classified_telemetry_1790093127744.jpg")
img5 = os.path.join(img_dir, "sphinx_relic_anomaly_1790093517300.jpg")
img6 = os.path.join(img_dir, "sphinx_ancient_vault_seal_1790093142093.jpg")

os.makedirs("outputs/custom_scenes", exist_ok=True)
dest1 = os.path.abspath("outputs/custom_scenes/sphinx60_s1.jpg")
dest2 = os.path.abspath("outputs/custom_scenes/sphinx60_s2.jpg")
dest3 = os.path.abspath("outputs/custom_scenes/sphinx60_s3.jpg")
dest4 = os.path.abspath("outputs/custom_scenes/sphinx60_s4.jpg")
dest5 = os.path.abspath("outputs/custom_scenes/sphinx60_s5.jpg")
dest6 = os.path.abspath("outputs/custom_scenes/sphinx60_s6.jpg")

shutil.copyfile(img1, dest1)
shutil.copyfile(img2, dest2)
shutil.copyfile(img3, dest3)
shutil.copyfile(img4, dest4)
shutil.copyfile(img5, dest5)
shutil.copyfile(img6, dest6)

script_text = (
    "Stop scrolling right now, because historians are desperately hiding what seismologists discovered beneath the Great Sphinx! "
    "In 1993, geophysicist Dr. Thomas Dobecki and his team conducted advanced seismic and ground-penetrating radar surveys across the Giza plateau. "
    "When their sensors probed beneath the limestone paws of the monument, the acoustic echograms revealed something that defies modern archaeology: "
    "a massive, hollow rectangular chamber carved directly into bedrock, over thirty feet underground. "
    "Even stranger, secondary scans detected a subterranean tunnel network winding directly toward the Great Pyramid. "
    "But before independent excavation could begin, Egyptian antiquities authorities abruptly terminated the research permits, expelled the scientists, and classified the raw telemetry. "
    "Decades later, unredacted field notes suggest the chamber holds ancient metallurgical anomalies predating known dynastic history. "
    "Could this be the legendary Hall of Records, or evidence of a lost advanced civilization? "
    "Drop what you believe in the comments, and subscribe for part two."
)

preview_scenes = [
    {
        "id": "scene_1",
        "text": "Stop scrolling right now, because historians are desperately hiding what seismologists discovered beneath the Great Sphinx! In 1993, geophysicist Dr. Thomas Dobecki and his team conducted advanced seismic and ground-penetrating radar surveys across the Giza plateau.",
        "media_path": dest1,
        "media_type": "image",
        "motion": "zoom_in",
        "duration": 11.5,
        "hook_text": "WHAT'S UNDER THE SPHINX?",
        "high_impact_words": ["Stop", "scrolling", "desperately", "hiding", "Sphinx", "1993", "seismic", "radar"]
    },
    {
        "id": "scene_2",
        "text": "When their sensors probed beneath the limestone paws of the monument, the acoustic echograms revealed something that defies modern archaeology: a massive, hollow rectangular chamber carved directly into bedrock, over thirty feet underground.",
        "media_path": dest2,
        "media_type": "image",
        "motion": "parallax_25d",
        "duration": 11.0,
        "high_impact_words": ["defies", "massive", "hollow", "rectangular", "chamber", "thirty", "bedrock"]
    },
    {
        "id": "scene_3",
        "text": "Even stranger, secondary scans detected a subterranean tunnel network winding directly toward the Great Pyramid.",
        "media_path": dest3,
        "media_type": "image",
        "motion": "pan_left",
        "duration": 8.0,
        "high_impact_words": ["stranger", "tunnel", "network", "Great", "Pyramid", "subterranean"]
    },
    {
        "id": "scene_4",
        "text": "But before independent excavation could begin, Egyptian antiquities authorities abruptly terminated the research permits, expelled the scientists, and classified the raw telemetry.",
        "media_path": dest4,
        "media_type": "image",
        "motion": "pan_right",
        "duration": 11.0,
        "high_impact_words": ["terminated", "expelled", "classified", "telemetry", "authorities", "permits"]
    },
    {
        "id": "scene_5",
        "text": "Decades later, unredacted field notes suggest the chamber holds ancient metallurgical anomalies predating known dynastic history.",
        "media_path": dest5,
        "media_type": "image",
        "motion": "zoom_in",
        "duration": 9.5,
        "high_impact_words": ["unredacted", "metallurgical", "anomalies", "predating", "dynastic", "history"]
    },
    {
        "id": "scene_6",
        "text": "Could this be the legendary Hall of Records, or evidence of a lost advanced civilization? Drop what you believe in the comments, and subscribe for part two.",
        "media_path": dest6,
        "media_type": "image",
        "motion": "zoom_out",
        "duration": 10.0,
        "high_impact_words": ["legendary", "Hall", "Records", "evidence", "advanced", "civilization", "subscribe"]
    }
]

def progress(msg, pct):
    print(f"[{pct}%] {msg}", flush=True)

print("=== Starting 60s Mystery Short Generation ===", flush=True)
res = render_shorts_video(
    script_text=script_text,
    voice="en-US-ChristopherNeural",
    voice_rate="+11%",  # Tuned for ~61 seconds
    subtitle_style="hyper_yellow",
    bgm_track="mystery_suspense",
    bgm_volume=0.18,
    progress_callback=progress,
    preview_scenes=preview_scenes,
    motion_texture="film_grain",
    transition_style="crossfade"
)

output_video = os.path.abspath("outputs/sphinx_mystery_60s_short.mp4")
shutil.copyfile(res["video_path"], output_video)

# Generate and save YouTube Metadata with YPP disclosures
metadata = generate_youtube_metadata(script_text)
meta_path = os.path.abspath("outputs/sphinx_mystery_60s_metadata.json")
with open(meta_path, "w", encoding="utf-8") as f:
    json.dump(metadata, f, indent=2, ensure_ascii=False)

print("\n" + "=" * 50, flush=True)
print(f"SUCCESS! 60s Mystery YouTube Short rendered in {res['duration']}s", flush=True)
print(f"Video File: {output_video}", flush=True)
print(f"Metadata File: {meta_path}", flush=True)
print(f"Title: {metadata.get('title')}", flush=True)
print(f"YPP Disclosure: {metadata.get('compliance_notes')}", flush=True)
print("=" * 50, flush=True)
