"""
engine/render.py - Lightweight, Sequential Short Video Renderer.
Renders 1080x1920 9:16 vertical YouTube Shorts under 512MB RAM ceiling.
"""

import os
import re
import uuid
import shutil
import asyncio
import subprocess
from typing import Dict, Any, Callable, Optional, List
from PIL import Image
import imageio_ffmpeg

from engine.tts import generate_speech_with_words
from engine.subtitles import generate_ass_subtitles
from engine.audio import get_bgm_file_path
from engine.motion import (
    create_ken_burns_motion_clip,
    make_video_scene_clip,
    make_blank_clip
)
from engine.timeline import align
from engine.project import load_project, Project, Scene

FFMPEG_EXE = imageio_ffmpeg.get_ffmpeg_exe()


def preprocess_image_for_motion(image_path: str, temp_dir: str, idx: int) -> str:
    """
    Downscales large images to max 1080x1920 before Ken Burns motion to guarantee <512MB RAM.
    Returns path to preprocessed image.
    """
    try:
        with Image.open(image_path) as img:
            w, h = img.size
            # If already within bounds, return original
            if w <= 1080 and h <= 1920:
                return image_path

            # Downscale preserving aspect ratio
            img.thumbnail((1080, 1920), Image.Resampling.LANCZOS)
            scaled_path = os.path.join(temp_dir, f"prep_img_{idx:03d}.jpg")
            img.convert("RGB").save(scaled_path, "JPEG", quality=90)
            return scaled_path
    except Exception as e:
        print(f"[Render] Preprocess image error for {image_path}: {e}")
        return image_path


def render_scene_clip(
    media_path: str,
    media_type: str,
    motion: str,
    duration: float,
    out_path: str,
    temp_dir: str,
    idx: int
) -> bool:
    """
    Renders an individual scene to a 1080x1920 30fps MP4 clip:
    - Image: Downscaled & Ken Burns motion applied.
    - Video: 9:16 scaled/cropped/looped.
    - Blank / Missing: 1080x1920 black clip.
    """
    if duration <= 0:
        duration = 1.0

    is_video = (
        media_type == "video" or
        (isinstance(media_path, str) and any(media_path.lower().endswith(ext) for ext in [".mp4", ".mov", ".webm"]))
    )

    ok = False
    if is_video and media_path and os.path.exists(media_path):
        ok = make_video_scene_clip(media_path, duration, out_path)
    elif media_path and os.path.exists(media_path):
        prep_img = preprocess_image_for_motion(media_path, temp_dir, idx)
        ok = create_ken_burns_motion_clip(prep_img, duration, out_path, motion=motion)

    if not ok or not os.path.exists(out_path):
        make_blank_clip(duration, out_path)

    return os.path.exists(out_path)


def expand_scenes_to_rapid_cuts(scenes: List[Dict[str, Any]], max_cut_dur: float = 3.2) -> List[Dict[str, Any]]:
    """
    Subdivides scenes longer than max_cut_dur into dynamic sub-cuts using multi-focal camera
    framing (zoom_in, pan_right, snap_zoom, pan_left, tilt_up, parallax_25d) so videos maintain
    18-22 rapid cuts (~2.5s-3.2s per visual) to maximize viewer retention.
    """
    expanded = []
    MOTION_CYCLE = ["zoom_in", "pan_right", "snap_zoom", "pan_left", "tilt_up", "parallax_25d"]
    motion_idx = 0
    for sc in scenes:
        dur = float(sc.get("duration", 3.0))
        if dur <= max_cut_dur:
            sc_copy = dict(sc)
            if not sc_copy.get("motion"):
                sc_copy["motion"] = MOTION_CYCLE[motion_idx % len(MOTION_CYCLE)]
                motion_idx += 1
            expanded.append(sc_copy)
        else:
            num_subcuts = max(2, int(round(dur / 2.8)))
            sub_dur = dur / num_subcuts
            for i in range(num_subcuts):
                sub = dict(sc)
                sub["id"] = f"{sc.get('id', 's')}_cut{i}"
                sub["duration"] = round(sub_dur, 2)
                sub["motion"] = MOTION_CYCLE[motion_idx % len(MOTION_CYCLE)]
                motion_idx += 1
                expanded.append(sub)
    return expanded


def render_broll_clips(
    scenes: List[Dict[str, Any]],
    output_path: str,
    temp_dir: str
) -> bool:
    """Renders sequential clips and joins them with FFmpeg concat demuxer."""
    clip_paths = []

    for idx, sc in enumerate(scenes):
        dur = float(sc.get("duration", 3.0))
        m_path = sc.get("media_path") or sc.get("image_path") or ""
        m_type = sc.get("media_type") or ("video" if (m_path.endswith(".mp4") or m_path.endswith(".webm")) else "image")
        motion = sc.get("motion") or sc.get("camera_motion") or "push in"

        clip_out = os.path.join(temp_dir, f"clip_{idx:03d}.mp4")
        render_scene_clip(
            media_path=m_path,
            media_type=m_type,
            motion=motion,
            duration=dur,
            out_path=clip_out,
            temp_dir=temp_dir,
            idx=idx
        )
        clip_paths.append(clip_out)

    concat_txt = os.path.join(temp_dir, "concat.txt")
    with open(concat_txt, "w", encoding="utf-8") as f:
        for p in clip_paths:
            safe_p = os.path.abspath(p).replace("\\", "/")
            f.write(f"file '{safe_p}'\n")

    cmd = [
        FFMPEG_EXE, "-y",
        "-f", "concat",
        "-safe", "0",
        "-i", os.path.abspath(concat_txt),
        "-c", "copy",
        os.path.abspath(output_path)
    ]

    res = subprocess.run(cmd, capture_output=True)
    if res.returncode != 0 or not os.path.exists(output_path):
        # Fallback to re-encode concat
        cmd_fallback = [
            FFMPEG_EXE, "-y",
            "-f", "concat",
            "-safe", "0",
            "-i", os.path.abspath(concat_txt),
            "-c:v", "libx264",
            "-preset", "ultrafast",
            "-crf", "22",
            "-pix_fmt", "yuv420p",
            os.path.abspath(output_path)
        ]
        res_fb = subprocess.run(cmd_fallback, capture_output=True)
        return res_fb.returncode == 0 and os.path.exists(output_path)

    return True


def render_shorts_video(
    script_text: str = "",
    voice: str = "en-US-ChristopherNeural",
    voice_rate: str = "+10%",
    subtitle_style: str = "hyper_yellow",
    bgm_track: str = "mystery_suspense",
    bgm_volume: float = 0.18,
    progress_callback: Optional[Callable[[str, int], None]] = None,
    scene_overrides: Optional[Dict[str, str]] = None,
    preview_scenes: Optional[List[Dict[str, Any]]] = None,
    project_id: Optional[str] = None,
    session_id: Optional[str] = None,
    **kwargs
) -> Dict[str, Any]:
    """
    Master Shorts Renderer. Sequential clip generation keeps memory <512MB.
    1. Loads project or session.
    2. Uses or generates voiceover + word boundaries.
    3. Generates ASS word-by-word subtitles.
    4. Aligns scenes to word boundaries and renders scene B-roll sequentially.
    5. Mixes audio tracks with auto-ducking and outputs final 1080x1920 MP4.
    """
    job_id = str(uuid.uuid4())[:8]
    work_dir = os.path.abspath(f"outputs/temp_{job_id}")
    os.makedirs(work_dir, exist_ok=True)
    final_output_path = os.path.abspath(f"outputs/short_{job_id}.mp4")

    try:
        p_id = project_id or session_id
        project = load_project(p_id) if p_id else None

        if project:
            if not script_text.strip() and project.script:
                script_text = project.script
            if not preview_scenes:
                preview_scenes = [s.to_dict() for s in project.scenes]

        # 1. Voiceover Synthesis or Cached Voice
        if progress_callback:
            progress_callback("Preparing AI voiceover...", 15)

        actual_voice_path = None
        word_boundaries = None
        total_duration = None

        if project and project.timeline:
            tl = project.timeline
            if (
                tl.get("audio_path") and os.path.exists(tl.get("audio_path")) and
                tl.get("voice") == voice and
                tl.get("rate") == voice_rate and
                tl.get("word_boundaries") and
                tl.get("total_duration")
            ):
                actual_voice_path = tl["audio_path"]
                word_boundaries = tl["word_boundaries"]
                total_duration = float(tl["total_duration"])

        if not actual_voice_path:
            voice_path = os.path.join(work_dir, "voice.mp3")
            actual_voice_path, word_boundaries, total_duration = asyncio.run(
                generate_speech_with_words(
                    text=script_text,
                    voice=voice,
                    rate=voice_rate,
                    output_audio_path=voice_path
                )
            )

        video_duration = total_duration + 0.35

        # 2. Subtitle Generation
        if progress_callback:
            progress_callback("Generating viral subtitles...", 35)

        ass_path = os.path.join(work_dir, "subtitles.ass")
        generate_ass_subtitles(
            word_boundaries=word_boundaries,
            output_ass_path=ass_path,
            style_name=subtitle_style,
            max_words_per_segment=2
        )

        # 3. Scene Alignment and Sequential B-Roll Rendering
        if progress_callback:
            progress_callback("Rendering scene visuals and camera motion...", 55)

        scenes = list(preview_scenes or [])
        if not scenes:
            scenes = [{"duration": video_duration, "media_path": "", "media_type": "blank", "motion": "static"}]

        if scene_overrides:
            for idx, sc in enumerate(scenes):
                sc_id_str = str(idx)
                ov = scene_overrides.get(sc_id_str) or scene_overrides.get(idx) or scene_overrides.get(sc.get("id")) or scene_overrides.get(sc.get("segment_id"))
                if ov:
                    sc["media_path"] = ov
                    sc["media_url"] = f"/outputs/ai_previews/{os.path.basename(ov)}"
                    sc["image_path"] = ov
                    sc["image_url"] = f"/outputs/ai_previews/{os.path.basename(ov)}"
                    sc["status"] = "manual"

        aligned_timeline = align(scenes, word_boundaries, video_duration)
        for idx, a in enumerate(aligned_timeline):
            if idx < len(scenes):
                scenes[idx]["duration"] = a["duration"]

        broll_video_path = os.path.join(work_dir, "broll_master.mp4")
        render_broll_clips(
            scenes=scenes,
            output_path=broll_video_path,
            temp_dir=work_dir
        )

        # 4. Final FFmpeg Composition
        if progress_callback:
            progress_callback("Compositing master 1080x1920 Short with music & subtitles...", 80)

        norm_ass_path = ass_path.replace("\\", "/").replace(":", "\\:")
        bgm_file = get_bgm_file_path(bgm_track)

        ffmpeg_cmd = [
            FFMPEG_EXE, "-y",
            "-i", os.path.abspath(broll_video_path),
            "-i", os.path.abspath(actual_voice_path)
        ]

        video_filter_in = "[0:v]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,format=yuv420p"
        v_chain = f"{video_filter_in},subtitles=filename='{norm_ass_path}'[vout]"

        if bgm_file and os.path.exists(bgm_file):
            ffmpeg_cmd.extend(["-stream_loop", "-1", "-i", os.path.abspath(bgm_file)])
            filter_complex = (
                f"{v_chain};"
                f"[2:a]volume={bgm_volume:.2f}[bgm_clean];"
                f"[1:a]volume=1.0[v_clean];"
                f"[v_clean][bgm_clean]amix=inputs=2:duration=first:dropout_transition=2[aout]"
            )
            ffmpeg_cmd.extend([
                "-filter_complex", filter_complex,
                "-map", "[vout]",
                "-map", "[aout]"
            ])
        else:
            ffmpeg_cmd.extend([
                "-filter_complex", v_chain,
                "-map", "[vout]",
                "-map", "1:a"
            ])

        ffmpeg_cmd.extend([
            "-t", f"{video_duration:.2f}",
            "-c:v", "libx264",
            "-preset", "veryfast",
            "-threads", "2",
            "-crf", "22",
            "-c:a", "aac",
            "-b:a", "192k",
            "-pix_fmt", "yuv420p",
            final_output_path
        ])

        result = subprocess.run(ffmpeg_cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(f"FFmpeg compositing failed: {result.stderr[-800:]}")

        if progress_callback:
            progress_callback("Complete! Viral YouTube Short is ready.", 100)

        return {
            "success": True,
            "job_id": job_id,
            "video_path": final_output_path,
            "video_url": f"/outputs/short_{job_id}.mp4",
            "duration": round(video_duration, 2),
            "word_count": len(word_boundaries)
        }

    finally:
        try:
            if os.path.exists(work_dir):
                shutil.rmtree(work_dir, ignore_errors=True)
        except Exception:
            pass
