"""
engine/timeline.py - Voice-First Timeline Alignment and TTS Audio Caching.
Aligns storyboard scenes to exact spoken word timestamps from Edge TTS.
"""

import os
import uuid
import hashlib
from typing import List, Dict, Any, Optional, Tuple

from engine.project import Project, Scene, load_project, save_project


def align(
    scenes: List[Any],
    words: List[Dict[str, Any]],
    total_duration: float
) -> List[Dict[str, Any]]:
    """
    Aligns scene boundaries to exact TTS word boundaries.
    Handles verbatim word matches and proportional word distribution.
    Returns list of dicts: [{"scene_id": ..., "scene_index": int, "start": float, "end": float, "duration": float, "text": str}]
    """
    if not scenes:
        return []

    # If no word boundaries available, produce sequential fallback
    if not words or total_duration <= 0:
        aligned = []
        cur_t = 0.0
        for idx, s in enumerate(scenes):
            dur = getattr(s, "duration", 3.0) if hasattr(s, "duration") else s.get("duration", 3.0)
            sc_id = getattr(s, "id", None) or getattr(s, "segment_id", f"scene_{idx}") if hasattr(s, "id") else s.get("id", s.get("segment_id", f"scene_{idx}"))
            txt = getattr(s, "text", "") if hasattr(s, "text") else s.get("text", "")
            aligned.append({
                "scene_id": sc_id,
                "segment_id": sc_id,  # Compatibility alias
                "scene_index": idx,
                "start": round(cur_t, 2),
                "end": round(cur_t + dur, 2),
                "duration": round(dur, 2),
                "text": txt
            })
            cur_t += dur
        return aligned

    # Extract word counts per scene
    counts = []
    sc_ids = []
    texts = []
    for idx, s in enumerate(scenes):
        txt = getattr(s, "text", "") if hasattr(s, "text") else s.get("text", "")
        sc_id = getattr(s, "id", None) or getattr(s, "segment_id", f"scene_{idx}") if hasattr(s, "id") else s.get("id", s.get("segment_id", f"scene_{idx}"))
        w_count = len(txt.strip().split())
        counts.append(max(1, w_count))
        sc_ids.append(sc_id)
        texts.append(txt)

    total_script_words = sum(counts)
    total_tts_words = len(words)

    aligned = []
    cum_words = 0
    prev_end = 0.0

    for idx, count in enumerate(counts):
        is_first = (idx == 0)
        is_last = (idx == len(counts) - 1)

        cum_words += count
        ratio_end = cum_words / float(max(1, total_script_words))

        start_t = 0.0 if is_first else prev_end

        if is_last:
            end_t = round(total_duration, 2)
        else:
            w_idx = min(total_tts_words - 1, max(0, int(round(ratio_end * total_tts_words)) - 1))
            end_t = round(words[w_idx]["end"], 2)
            if end_t <= start_t:
                end_t = round(start_t + 1.0, 2)

        dur = max(0.5, round(end_t - start_t, 2))
        prev_end = end_t

        aligned.append({
            "scene_id": sc_ids[idx],
            "segment_id": sc_ids[idx],  # Compatibility alias
            "scene_index": idx,
            "start": round(start_t, 2),
            "end": round(end_t, 2),
            "duration": round(dur, 2),
            "text": texts[idx]
        })

    return aligned


async def prepare_voice_timeline(
    project_id: str,
    voice: str = "en-US-ChristopherNeural",
    rate: str = "+10%"
) -> Tuple[Optional[Project], Optional[str], int]:
    """
    Generates TTS audio, word boundaries, and aligns scenes to exact timestamps.
    Caches timeline using script_hash.
    """
    project = load_project(project_id)
    if not project:
        return None, "Project not found", 404

    clean_script = project.script.strip()
    if not clean_script:
        return None, "Script cannot be empty.", 400

    script_hash = hashlib.sha256(f"{clean_script}_{voice}_{rate}".encode("utf-8")).hexdigest()

    # Check cache
    cached = project.timeline
    if cached and cached.get("script_hash") == script_hash and os.path.exists(cached.get("audio_path", "")):
        return project, None, 200

    out_name = f"voice_{project.id[:8]}_{uuid.uuid4().hex[:6]}.mp3"
    out_audio_path = os.path.join("outputs", out_name)
    os.makedirs("outputs", exist_ok=True)

    try:
        from engine.tts import generate_speech_with_words
        audio_path, word_boundaries, total_dur = await generate_speech_with_words(
            text=clean_script,
            voice=voice,
            rate=rate,
            output_audio_path=out_audio_path
        )
    except Exception as e:
        return None, f"TTS generation failed: {e}", 500

    aligned = align(project.scenes, word_boundaries, total_dur)

    for idx, a in enumerate(aligned):
        if idx < len(project.scenes):
            project.scenes[idx].duration = a["duration"]

    project.total_duration = round(total_dur, 2)
    project.timeline = {
        "audio_path": audio_path,
        "audio_url": f"/outputs/{out_name}",
        "voice": voice,
        "rate": rate,
        "total_duration": round(total_dur, 2),
        "word_boundaries": word_boundaries,
        "script_hash": script_hash,
        "scenes": aligned
    }

    project.snapshot()
    save_project(project)
    return project, None, 200
