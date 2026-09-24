import os
import subprocess
from typing import List, Dict, Any, Optional
import imageio_ffmpeg

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


SFX_DIR = os.path.abspath("assets/sfx")

def get_available_sfx() -> List[str]:
    """Return list of valid local SFX files (whoosh/swipes)."""
    if not os.path.exists(SFX_DIR):
        return []
    valid_exts = {".wav", ".mp3", ".ogg", ".aac"}
    files = []
    for f in sorted(os.listdir(SFX_DIR)):
        if os.path.splitext(f.lower())[1] in valid_exts:
            full_path = os.path.join(SFX_DIR, f)
            if os.path.getsize(full_path) > 500:
                files.append(full_path)
    return files


def get_random_sfx(idx: int = 0, kind: str = "whoosh") -> Optional[str]:
    """Deterministically pick a soft SFX (air swipe or riser) by index, excluding boomy whoops."""
    sfx_list = get_available_sfx()
    if not sfx_list:
        return None
    if kind == "riser":
        risers = [f for f in sfx_list if "riser" in os.path.basename(f).lower()]
        if risers:
            return risers[idx % len(risers)]
    # Use soft airy swipes/whooshes, explicitly avoiding boomy bass 'whoop' effects
    whooshes = [f for f in sfx_list if "riser" not in os.path.basename(f).lower() and "deep" not in os.path.basename(f).lower()]
    if not whooshes:
        whooshes = [f for f in sfx_list if "riser" not in os.path.basename(f).lower()]
    if whooshes:
        return whooshes[idx % len(whooshes)]
    return sfx_list[idx % len(sfx_list)]


def build_sfx_track(
    cut_points: List[float],
    output_path: str,
    total_duration: float,
    volume: float = 0.07,
    include_riser: bool = False
) -> Optional[str]:
    """
    Builds a single mixed SFX track with subtle, airy transition swooshes spaced
    at least 7.5s apart (max 3-4 across the whole video) so it never sounds annoying or repetitive.
    """
    sfx_files = get_available_sfx()
    if not sfx_files:
        return None

    # Filter out rapid micro-cuts: space transitions at least 7s apart on full Shorts, or 2s on short previews/tests
    min_interval = 2.0 if total_duration < 10.0 else 7.0
    min_bound = 1.0 if total_duration < 10.0 else 2.5
    max_bound = total_duration - min_bound
    spaced_cuts = []
    last_cp = 0.0
    for cp in (cut_points or []):
        if (cp >= last_cp + min_interval or not spaced_cuts) and min_bound <= cp <= max_bound:
            spaced_cuts.append(cp)
            last_cp = cp
    valid_cuts = spaced_cuts[:4]

    try:
        inputs = []
        filter_parts = []

        # 1. Opening hook riser (very soft)
        riser_file = get_random_sfx(0, kind="riser")
        if include_riser and riser_file and os.path.exists(riser_file) and total_duration >= 2.0:
            inputs.extend(["-i", os.path.abspath(riser_file)])
            r_idx = len(inputs) // 2 - 1
            filter_parts.append(f"[{r_idx}:a]adelay=50|50,volume={min(0.06, volume):.2f},lowpass=f=4000[s_riser]")

        # 2. Soft airy swooshes on major transitions
        for i, cp in enumerate(valid_cuts):
            whoosh_file = get_random_sfx(i, kind="whoosh")
            if not whoosh_file or not os.path.exists(whoosh_file):
                continue
            inputs.extend(["-i", os.path.abspath(whoosh_file)])
            w_idx = len(inputs) // 2 - 1
            delay_ms = max(0, int((cp - 0.05) * 1000))
            # High-pass filter removes the boomy 'whoop' resonance; gentle volume sits warmly in background
            filter_parts.append(f"[{w_idx}:a]adelay={delay_ms}|{delay_ms},volume={volume:.2f},highpass=f=250,lowpass=f=5500[s{i}]")

        if not filter_parts:
            return None

        num_parts = len(filter_parts)
        if num_parts == 1:
            first_label = "[s_riser]" if "s_riser" in filter_parts[0] else "[s0]"
            full_filter = f"{filter_parts[0].replace(first_label, '[aout]')}"
        else:
            labels = []
            if any("s_riser" in p for p in filter_parts):
                labels.append("[s_riser]")
            for i in range(len(valid_cuts)):
                if any(f"[s{i}]" in p for p in filter_parts):
                    labels.append(f"[s{i}]")
            mix_ins = "".join(labels)
            mix_cmd = f"{mix_ins}amix=inputs={len(labels)}:dropout_transition=0:normalize=0[aout]"
            full_filter = ";".join(filter_parts) + ";" + mix_cmd

        cmd = [
            imageio_ffmpeg.get_ffmpeg_exe(), "-y",
            *inputs,
            "-filter_complex", full_filter,
            "-map", "[aout]",
            "-t", f"{total_duration:.2f}",
            "-c:a", "pcm_s16le",
            os.path.abspath(output_path)
        ]
        res = subprocess.run(cmd, capture_output=True)
        if res.returncode == 0 and os.path.exists(output_path):
            return output_path
        else:
            return None
    except Exception as e:
        print(f"[Audio] SFX track generation error: {e}")
        return None


