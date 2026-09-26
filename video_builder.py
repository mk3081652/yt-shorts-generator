"""
video_builder.py - Module 3: Dynamic Motion & Rapid Cut Assembly

Features:
- Enforces the 1.5 - 1.8 second cut rule: no image stays static for >1.8s.
- Automatic full-portrait scaling & cropping to 1080x1920 (no pillarboxing or black bars).
- Alternating continuous cinematic camera moves via FFmpeg zoompan:
  * Aggressive zoom-in (1.0x -> 1.35x)
  * Dramatic pull-out (1.35x -> 1.0x)
  * Kinetic snap-pans (left & right)
  * Vertical tilt-up
- Direct burn-in of styled .ass karaoke subtitles during the render pass.
"""

import os
import shutil
import subprocess
from typing import List, Dict, Any, Optional, Tuple
import imageio_ffmpeg

FFMPEG_EXE = imageio_ffmpeg.get_ffmpeg_exe()

MOTION_TYPES = [
    "zoom_in",
    "pan_right",
    "zoom_out",
    "pan_left",
    "tilt_up",
    "zoom_in_heavy"
]


def create_motion_clip(
    media_path: str,
    duration: float,
    output_path: str,
    motion_type: str = "zoom_in",
    width: int = 1080,
    height: int = 1920,
    fps: int = 30
) -> bool:
    """
    Renders an image into a vertical 1080x1920 video clip with continuous camera movement.
    Guarantees no black bars or pillarboxing by pre-scaling and center-cropping.
    """
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    total_frames = max(10, int(duration * fps))
    d_str = str(total_frames)

    # Base scaling to fill portrait frame completely
    scale_crop = (
        f"scale={width}:{height}:force_original_aspect_ratio=increase,"
        f"crop={width}:{height}"
    )

    if motion_type == "zoom_in":
        # Aggressive zoom-in: 1.0x to 1.35x
        zoom_expr = "min(zoom+0.003,1.35)"
        x_expr = "iw/2-(iw/zoom/2)"
        y_expr = "ih/2-(ih/zoom/2)"
    elif motion_type == "zoom_in_heavy":
        # Extra high-energy hook zoom: 1.0x to 1.40x
        zoom_expr = "min(zoom+0.004,1.40)"
        x_expr = "iw/2-(iw/zoom/2)"
        y_expr = "ih/2-(ih/zoom/2)"
    elif motion_type == "zoom_out":
        # Dramatic reveal pull-out: 1.35x to 1.0x
        zoom_expr = "max(1.35-0.003*on,1.0)"
        x_expr = "iw/2-(iw/zoom/2)"
        y_expr = "ih/2-(ih/zoom/2)"
    elif motion_type == "pan_right":
        # Gliding pan right with 1.20x zoom
        zoom_expr = "1.20"
        x_expr = f"(iw-iw/zoom)*(on/{d_str})"
        y_expr = "ih/2-(ih/zoom/2)"
    elif motion_type == "pan_left":
        # Gliding pan left with 1.20x zoom
        zoom_expr = "1.20"
        x_expr = f"(iw-iw/zoom)*(1-on/{d_str})"
        y_expr = "ih/2-(ih/zoom/2)"
    elif motion_type == "tilt_up":
        # Vertical tilt up
        zoom_expr = "1.18"
        x_expr = "iw/2-(iw/zoom/2)"
        y_expr = f"(ih-ih/zoom)*(1-on/{d_str})"
    else:
        zoom_expr = "min(zoom+0.002,1.25)"
        x_expr = "iw/2-(iw/zoom/2)"
        y_expr = "ih/2-(ih/zoom/2)"

    vf = (
        f"{scale_crop},"
        f"zoompan=z='{zoom_expr}':d={d_str}:x='{x_expr}':y='{y_expr}':s={width}x{height}:fps={fps},"
        f"format=yuv420p"
    )

    cmd = [
        FFMPEG_EXE, "-y",
        "-loop", "1",
        "-i", os.path.abspath(media_path),
        "-vf", vf,
        "-t", f"{duration:.3f}",
        "-r", str(fps),
        "-c:v", "libx264",
        "-preset", "ultrafast",
        "-tune", "fastdecode",
        "-pix_fmt", "yuv420p",
        os.path.abspath(output_path)
    ]

    res = subprocess.run(cmd, capture_output=True)
    return res.returncode == 0 and os.path.exists(output_path)


def plan_rapid_cuts(
    image_paths: List[str],
    total_duration: float,
    target_cut_duration: float = 1.6
) -> Tuple[List[Dict[str, Any]], List[float]]:
    """
    Subdivides the total duration into rapid visual cuts (1.4s - 1.8s each).
    Enforces that a 30s Short has 18-20 distinct cuts with alternating camera motions.

    Returns:
        Tuple of (cuts_list, cut_timestamps)
    """
    if not image_paths:
        raise ValueError("Must provide at least one image path.")

    # Calculate number of cuts needed (e.g. 30s / 1.6s ≈ 19 cuts)
    num_cuts = max(len(image_paths), int(round(total_duration / target_cut_duration)))
    actual_cut_dur = round(total_duration / num_cuts, 3)

    cuts: List[Dict[str, Any]] = []
    cut_timestamps: List[float] = []
    elapsed = 0.0

    for i in range(num_cuts):
        img_idx = i % len(image_paths)
        motion_idx = i % len(MOTION_TYPES)
        dur = actual_cut_dur if i < num_cuts - 1 else round(total_duration - elapsed, 3)

        cuts.append({
            "cut_index": i,
            "image_path": image_paths[img_idx],
            "duration": dur,
            "motion": MOTION_TYPES[motion_idx],
            "start_time": round(elapsed, 3)
        })

        if elapsed > 0.1:
            cut_timestamps.append(round(elapsed, 3))
        elapsed += dur

    return cuts, cut_timestamps


def assemble_short_video(
    image_paths: List[str],
    audio_path: str,
    subtitle_ass_path: Optional[str],
    output_path: str,
    total_duration: float,
    temp_dir: str = "tmp/video_builder",
    width: int = 1080,
    height: int = 1920
) -> Tuple[str, List[float]]:
    """
    Assembles complete YouTube Short:
    1. Plans rapid visual cuts (1.5 - 1.8s each).
    2. Renders dynamic motion clips.
    3. Concatenates video track.
    4. Merges audio and burns in ASS karaoke subtitles.

    Returns:
        Tuple of (output_path, cut_timestamps)
    """
    os.makedirs(temp_dir, exist_ok=True)
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)

    cuts, cut_timestamps = plan_rapid_cuts(image_paths, total_duration)

    # 1. Render individual rapid motion cuts
    clip_paths: List[str] = []
    for c in cuts:
        clip_file = os.path.join(temp_dir, f"cut_{c['cut_index']:03d}.mp4")
        ok = create_motion_clip(
            media_path=c["image_path"],
            duration=c["duration"],
            output_path=clip_file,
            motion_type=c["motion"],
            width=width,
            height=height
        )
        if ok and os.path.exists(clip_file):
            clip_paths.append(clip_file)

    if not clip_paths:
        raise RuntimeError("Failed to render any visual clips.")

    # 2. Concat video clips
    concat_txt = os.path.join(temp_dir, "concat_list.txt")
    with open(concat_txt, "w", encoding="utf-8") as f:
        for cp in clip_paths:
            safe = os.path.abspath(cp).replace("\\", "/")
            f.write(f"file '{safe}'\n")

    raw_video = os.path.join(temp_dir, "stitched_raw.mp4")
    concat_cmd = [
        FFMPEG_EXE, "-y",
        "-f", "concat",
        "-safe", "0",
        "-i", os.path.abspath(concat_txt),
        "-c", "copy",
        os.path.abspath(raw_video)
    ]
    subprocess.run(concat_cmd, check=True, capture_output=True)

    # 3. Merge audio and burn in subtitles
    # Prepare subtitle filter with escaped path
    video_filters = []
    if subtitle_ass_path and os.path.exists(subtitle_ass_path):
        # Escape path for FFmpeg subtitles filter on Windows/Linux
        ass_clean = os.path.abspath(subtitle_ass_path).replace("\\", "/").replace(":", "\\:")
        video_filters.append(f"subtitles='{ass_clean}'")

    vf_arg = [",".join(video_filters)] if video_filters else []

    final_cmd = [
        FFMPEG_EXE, "-y",
        "-i", os.path.abspath(raw_video),
        "-i", os.path.abspath(audio_path),
        *(["-vf", vf_arg[0]] if vf_arg else []),
        "-c:v", "libx264",
        "-preset", "fast",
        "-crf", "20",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac",
        "-b:a", "192k",
        "-shortest",
        os.path.abspath(output_path)
    ]

    res = subprocess.run(final_cmd, capture_output=True)
    if res.returncode != 0:
        # Fallback without subtitle filter if libass error occurs
        fallback_cmd = [
            FFMPEG_EXE, "-y",
            "-i", os.path.abspath(raw_video),
            "-i", os.path.abspath(audio_path),
            "-c:v", "copy",
            "-c:a", "aac",
            "-b:a", "192k",
            "-shortest",
            os.path.abspath(output_path)
        ]
        subprocess.run(fallback_cmd, check=True, capture_output=True)

    return output_path, cut_timestamps
