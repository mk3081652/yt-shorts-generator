"""
engine/scene_director.py - Sequential Scene B-Roll Renderer
Replaces gemini_visuals.py with a lightweight, sequential scene renderer.
"""

import os
import subprocess
import imageio_ffmpeg
from typing import List, Dict, Any

from engine.motion import (
    create_ken_burns_motion_clip,
    make_video_scene_clip,
    make_blank_clip
)

FFMPEG_EXE = imageio_ffmpeg.get_ffmpeg_exe()


def render_broll(
    scenes: List[Dict[str, Any]],
    total_duration: float,
    output_path: str,
    temp_dir: str
) -> bool:
    """
    Renders sequential scene clips (image -> Ken Burns, video -> video clip, blank -> blank clip)
    and concats them into a single 1080x1920 master B-roll video.
    Maintains 512MB RAM ceiling by processing clips sequentially.
    """
    os.makedirs(temp_dir, exist_ok=True)
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)

    clip_paths = []

    for idx, sc in enumerate(scenes):
        duration = float(sc.get("duration", 3.0))
        if duration <= 0:
            duration = 1.0

        clip_out = os.path.join(temp_dir, f"scene_clip_{idx:03d}.mp4")
        media_type = sc.get("media_type", "")
        img_path = sc.get("image_path", "")

        # Check if media is video
        is_video = (
            media_type == "video" or
            (isinstance(img_path, str) and any(img_path.lower().endswith(ext) for ext in [".mp4", ".mov", ".webm"]))
        )

        ok = False
        if is_video and img_path and os.path.exists(img_path):
            ok = make_video_scene_clip(img_path, duration, clip_out)
        elif img_path and os.path.exists(img_path):
            ok = create_ken_burns_motion_clip(img_path, duration, clip_out, motion_index=idx)

        # If no image or clip generation failed, produce black blank clip
        if not ok or not os.path.exists(clip_out):
            make_blank_clip(duration, clip_out)

        clip_paths.append(clip_out)

    # Concat all clips
    concat_txt_path = os.path.join(temp_dir, "broll_concat.txt")
    with open(concat_txt_path, "w", encoding="utf-8") as f:
        for p in clip_paths:
            # Escape path for FFmpeg concat demuxer
            safe_p = os.path.abspath(p).replace("\\", "/")
            f.write(f"file '{safe_p}'\n")

    cmd = [
        FFMPEG_EXE, "-y",
        "-f", "concat",
        "-safe", "0",
        "-i", os.path.abspath(concat_txt_path),
        "-c", "copy",
        os.path.abspath(output_path)
    ]

    res = subprocess.run(cmd, capture_output=True)
    if res.returncode != 0 or not os.path.exists(output_path):
        # Fallback to re-encode concat if copy fails
        cmd_fallback = [
            FFMPEG_EXE, "-y",
            "-f", "concat",
            "-safe", "0",
            "-i", os.path.abspath(concat_txt_path),
            "-c:v", "libx264",
            "-preset", "ultrafast",
            "-crf", "22",
            "-pix_fmt", "yuv420p",
            os.path.abspath(output_path)
        ]
        res_fb = subprocess.run(cmd_fallback, capture_output=True)
        return res_fb.returncode == 0 and os.path.exists(output_path)

    return True


def align_scenes(
    segments: List[Any],
    words: List[Dict[str, Any]],
    total_duration: float
) -> List[Dict[str, Any]]:
    """
    Aligns scene boundaries to TTS word boundaries.
    Handles exact word matches and proportional interpolation when word counts differ.
    Returns list of dicts: [{"segment_id": ..., "start": float, "end": float, "duration": float}]
    """
    if not segments:
        return []

    if not words or total_duration <= 0:
        aligned = []
        cur_t = 0.0
        for s in segments:
            dur = getattr(s, "duration", 3.0) if hasattr(s, "duration") else s.get("duration", 3.0)
            seg_id = getattr(s, "segment_id", "") if hasattr(s, "segment_id") else s.get("segment_id", "")
            aligned.append({
                "segment_id": seg_id,
                "start": round(cur_t, 2),
                "end": round(cur_t + dur, 2),
                "duration": round(dur, 2)
            })
            cur_t += dur
        return aligned

    # Extract word counts per segment
    counts = []
    seg_ids = []
    for s in segments:
        txt = getattr(s, "text", "") if hasattr(s, "text") else s.get("text", "")
        seg_id = getattr(s, "segment_id", "") if hasattr(s, "segment_id") else s.get("segment_id", "")
        counts.append(max(1, len(txt.strip().split())))
        seg_ids.append(seg_id)

    total_script_words = sum(counts)
    total_tts_words = len(words)

    aligned = []
    cum_words = 0
    prev_end = 0.0

    for idx, count in enumerate(counts):
        is_last = (idx == len(counts) - 1)
        is_first = (idx == 0)

        cum_words += count
        ratio_end = cum_words / max(1, total_script_words)

        if is_first:
            start_t = 0.0
        else:
            start_t = prev_end

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
            "segment_id": seg_ids[idx],
            "start": round(start_t, 2),
            "end": round(end_t, 2),
            "duration": round(dur, 2)
        })

    return aligned
