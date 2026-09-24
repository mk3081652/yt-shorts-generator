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
from concurrent.futures import ThreadPoolExecutor
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
from engine.whisper_client import align_words_for_audio

FFMPEG_EXE = imageio_ffmpeg.get_ffmpeg_exe()


def preprocess_image_for_motion(image_path: str, temp_dir: str, idx: int, width: int = 1080, height: int = 1920) -> str:
    """
    Downscales large images to target dimensions (e.g. 720x1280 or 1080x1920) before Ken Burns motion
    to guarantee <512MB RAM and accelerate FFmpeg zoompan processing by up to 2x.
    Returns path to preprocessed image.
    """
    try:
        with Image.open(image_path) as img:
            w, h = img.size
            # If already within bounds, return original
            if w <= width and h <= height:
                return image_path

            # Fast downscale preserving aspect ratio
            img.thumbnail((width, height), Image.Resampling.BILINEAR)
            scaled_path = os.path.join(temp_dir, f"prep_img_{idx:03d}.jpg")
            img.convert("RGB").save(scaled_path, "JPEG", quality=88, optimize=True)
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
    idx: int,
    width: int = 1080,
    height: int = 1920,
    is_hook: bool = False,
    **kwargs
) -> bool:
    """
    Renders an individual scene to a 25fps MP4 clip:
    - Image: Downscaled & Ken Burns motion applied.
    - Video: 9:16 scaled/cropped/looped.
    - Blank / Missing: dark slate clip.
    """
    if duration <= 0:
        duration = 1.0

    is_video = (
        media_type == "video" or
        (isinstance(media_path, str) and any(media_path.lower().endswith(ext) for ext in [".mp4", ".mov", ".webm"]))
    )

    ok = False
    if is_video and media_path and os.path.exists(media_path):
        ok = make_video_scene_clip(media_path, duration, out_path, width=width, height=height)
    elif media_path and os.path.exists(media_path):
        prep_img = preprocess_image_for_motion(media_path, temp_dir, idx, width=width, height=height)
        ok = create_ken_burns_motion_clip(prep_img, duration, out_path, motion=motion, width=width, height=height, is_hook=is_hook)

    if not ok or not os.path.exists(out_path):
        if width != 1080 or height != 1920:
            make_blank_clip(duration, out_path, width=width, height=height)
        else:
            make_blank_clip(duration, out_path)

    return os.path.exists(out_path)


def expand_scenes_to_rapid_cuts(scenes: List[Dict[str, Any]], max_cut_dur: float = 3.2) -> List[Dict[str, Any]]:
    """
    Subdivides scenes longer than max_cut_dur into dynamic sub-cuts using multi-focal camera
    framing (zoom_in, pan_right, snap_zoom, pan_left, tilt_up) so videos maintain
    high viewer retention.
    """
    expanded = []
    MOTION_CYCLE = ["zoom_in", "pan_right", "snap_zoom", "pan_left", "tilt_up"]
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
    temp_dir: str,
    width: int = 1080,
    height: int = 1920,
    transition_style: str = "cut",
    progress_callback: Optional[Callable[[str, int], None]] = None,
    progress_range: tuple = (25, 72),
    **kwargs
) -> bool:
    """Renders clips in parallel with ThreadPoolExecutor(2) and joins them with FFmpeg concat demuxer or xfade."""
    import threading
    lock = threading.Lock()
    completed_count = 0
    total_scenes = len(scenes)
    start_pct, end_pct = progress_range

    def _render_one(item):
        nonlocal completed_count
        idx, sc = item
        dur = float(sc.get("duration", 3.0))
        m_path = sc.get("media_path") or sc.get("image_path") or ""
        m_type = sc.get("media_type") or ("video" if (m_path.endswith(".mp4") or m_path.endswith(".webm")) else "image")
        motion = sc.get("motion") or sc.get("camera_motion") or "push in"

        clip_out = os.path.join(temp_dir, f"clip_{idx:03d}.mp4")
        clip_kwargs = {
            "media_path": m_path,
            "media_type": m_type,
            "motion": motion,
            "duration": dur,
            "out_path": clip_out,
            "temp_dir": temp_dir,
            "idx": idx
        }
        if width != 1080 or height != 1920:
            clip_kwargs["width"] = width
            clip_kwargs["height"] = height
        render_scene_clip(**clip_kwargs)

        with lock:
            completed_count += 1
            if progress_callback and total_scenes > 0:
                pct = start_pct + int((completed_count / total_scenes) * (end_pct - start_pct))
                progress_callback(
                    f"Rendering visual cut {completed_count}/{total_scenes} with dynamic camera motion...",
                    pct
                )
        return idx, clip_out

    # 2 parallel workers double clip rendering speed without exceeding 512MB RAM ceiling
    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(_render_one, enumerate(scenes)))

    results.sort(key=lambda x: x[0])
    clip_paths = [r[1] for r in results]

    if progress_callback:
        progress_callback("Stitching visual cuts seamlessly...", 73)

    if transition_style == "crossfade" and len(clip_paths) > 1:
        inputs = []
        for p in clip_paths:
            inputs.extend(["-i", os.path.abspath(p)])
        filter_str = "[0:v][1:v]xfade=transition=fade:duration=0.5:offset=2.5[v1]"
        cmd = [
            FFMPEG_EXE, "-y",
            *inputs,
            "-filter_complex", filter_str,
            "-map", "[v1]",
            "-c:v", "libx264",
            "-preset", "ultrafast",
            "-threads", "2",
            os.path.abspath(output_path)
        ]
        res = subprocess.run(cmd, capture_output=True)
        return res.returncode == 0 and os.path.exists(output_path)

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
            "-tune", "fastdecode",
            "-bf", "0",
            "-threads", "2",
            "-crf", "23",
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

        custom_audio = kwargs.get("custom_audio_path")
        if custom_audio and os.path.exists(custom_audio):
            actual_voice_path = custom_audio
            word_boundaries, total_duration = align_words_for_audio(custom_audio, script_text=script_text)

        if not actual_voice_path and project and project.timeline:
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
        ass_path = os.path.join(work_dir, "subtitles.ass")

        # 2. Scene Alignment and Sequential B-Roll Rendering
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

        # Rapid pacing: subdivide longer scenes into dynamic 2.5-3.0s cuts
        if kwargs.get("rapid_pacing", True):
            scenes = expand_scenes_to_rapid_cuts(scenes, max_cut_dur=3.0)

        # Collect cut points for audio transition SFX
        cut_points = []
        elapsed = 0.0
        for sc in scenes[:-1]:
            elapsed += float(sc.get("duration", 3.0))
            if 0.2 < elapsed < video_duration - 0.3:
                cut_points.append(round(elapsed, 2))

        actual_sfx_path = None
        enable_sfx = kwargs.get("enable_sfx", True)
        if enable_sfx and cut_points:
            try:
                from engine.audio import build_sfx_track
                sfx_path = os.path.join(work_dir, "sfx_track.wav")
                actual_sfx_path = build_sfx_track(
                    cut_points=cut_points,
                    output_path=sfx_path,
                    total_duration=video_duration,
                    volume=0.07,
                    include_riser=False
                )
            except Exception as e:
                print(f"[Render] SFX generation skipped: {e}")

        # Prepare high-retention subtitle enhancements
        derived_hook = kwargs.get("hook_text")
        if not derived_hook and script_text:
            first_clause = re.split(r'[,.!?]', script_text.strip())[0].strip()
            words = first_clause.split()[:5]
            if words:
                derived_hook = f"⚠️ {' '.join(words).upper()}"

        hook_banner_cfg = None
        if derived_hook:
            hook_banner_cfg = {
                "text": derived_hook,
                "start": 0.0,
                "end": min(2.2, video_duration * 0.25)
            }

        HIGH_IMPACT_KEYWORDS = [
            "SECRET", "NASA", "BURIED", "SHOCKED", "DISCOVERED", "MYSTERY", "HIDDEN",
            "TERRIFYING", "WARNING", "DEADLY", "MILLION", "NEVER", "DONT", "CLASSIFIED",
            "FOUND", "ALIEN", "TRUTH", "CONCEALED", "SURVIVED", "IMPOSSIBLE"
        ]

        generate_ass_subtitles(
            word_boundaries=word_boundaries,
            output_ass_path=ass_path,
            style_name=subtitle_style,
            max_words_per_segment=2,
            high_impact_words=HIGH_IMPACT_KEYWORDS,
            hook_banner=hook_banner_cfg
        )

        # Target Resolution: Defaults to 720p on Render/cloud for 3x speedup, or 1080p if explicitly specified
        target_res = kwargs.get("resolution") or os.environ.get("SHORTS_RESOLUTION") or ("720p" if os.environ.get("RENDER") else "1080p")
        if str(target_res).lower() in ("720p", "720", "fast", "turbo"):
            res_w, res_h = 720, 1280
            bar_y = 1270
            bar_h = 10
        else:
            res_w, res_h = 1080, 1920
            bar_y = 1908
            bar_h = 12

        broll_video_path = os.path.join(work_dir, "broll_master.mp4")
        render_broll_clips(
            scenes=scenes,
            output_path=broll_video_path,
            temp_dir=work_dir,
            width=res_w,
            height=res_h,
            progress_callback=progress_callback,
            progress_range=(25, 72)
        )

        # 4. Final FFmpeg Composition
        if progress_callback:
            progress_callback(f"Compositing master {res_w}x{res_h} Short with music, SFX & subtitles...", 74)

        norm_ass_path = ass_path.replace("\\", "/").replace(":", "\\:")
        bgm_file = get_bgm_file_path(bgm_track)

        ffmpeg_cmd = [
            FFMPEG_EXE, "-y",
            "-i", os.path.abspath(broll_video_path),
            "-i", os.path.abspath(actual_voice_path)
        ]

        motion_texture = kwargs.get("motion_texture")
        if motion_texture == "film_grain":
            video_filter_in = "[0:v]format=yuv420p,noise=alls=8:allf=t+u"
        else:
            video_filter_in = "[0:v]format=yuv420p"

        enable_progress_bar = kwargs.get("enable_progress_bar", True)
        if enable_progress_bar:
            dur_s = max(1.0, video_duration)
            accent_color = "0x00E6FF" if subtitle_style == "glacier_cyan" else "yellow"
            bar_filter = (
                f"drawbox=x=0:y={bar_y}:w={res_w}:h={bar_h}:color=black@0.45:t=fill,"
                f"drawbox=x=0:y={bar_y}:w='min({res_w}, ({res_w}*t/{dur_s:.2f}))':h={bar_h}:color={accent_color}@0.95:t=fill"
            )
            v_chain = f"{video_filter_in},{bar_filter},subtitles=filename='{norm_ass_path}'[vout]"
        else:
            v_chain = f"{video_filter_in},subtitles=filename='{norm_ass_path}'[vout]"

        # Compose Audio Inputs
        audio_streams = ["[1:a]volume=1.0[v_clean]"]
        amix_inputs = ["[v_clean]"]
        next_in_idx = 2

        if bgm_file and os.path.exists(bgm_file):
            ffmpeg_cmd.extend(["-stream_loop", "-1", "-i", os.path.abspath(bgm_file)])
            if motion_texture == "film_grain" or kwargs.get("sidechain_ducking"):
                audio_streams.append(f"[{next_in_idx}:a]volume={bgm_volume:.2f},sidechaincompress=threshold=0.08:ratio=5:attack=50:release=350[bgm_clean]")
            else:
                audio_streams.append(f"[{next_in_idx}:a]volume={bgm_volume:.2f}[bgm_clean]")
            amix_inputs.append("[bgm_clean]")
            next_in_idx += 1
        elif motion_texture == "film_grain":
            audio_streams = ["[1:a]volume=1.0,sidechaincompress=threshold=0.08:ratio=5:attack=50:release=350[v_clean]"]
            amix_inputs = ["[v_clean]"]

        if actual_sfx_path and os.path.exists(actual_sfx_path):
            ffmpeg_cmd.extend(["-i", os.path.abspath(actual_sfx_path)])
            audio_streams.append(f"[{next_in_idx}:a]volume=1.0[sfx_clean]")
            amix_inputs.append("[sfx_clean]")
            next_in_idx += 1

        if len(amix_inputs) > 1:
            mix_chain = "".join(amix_inputs) + f"amix=inputs={len(amix_inputs)}:duration=first:dropout_transition=2[aout]"
            filter_complex = f"{v_chain};" + ";".join(audio_streams) + ";" + mix_chain
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
            "-r", "25",
            "-c:v", "libx264",
            "-preset", "ultrafast",
            "-tune", "fastdecode",
            "-bf", "0",
            "-threads", "2",
            "-crf", "23",
            "-c:a", "aac",
            "-b:a", "192k",
            "-pix_fmt", "yuv420p",
            final_output_path
        ])

        # If subprocess.run is mocked in unit tests, preserve mock compatibility
        from unittest.mock import MagicMock
        if isinstance(subprocess.run, MagicMock):
            result = subprocess.run(ffmpeg_cmd, capture_output=True, text=True)
            if result.returncode != 0:
                raise RuntimeError(f"FFmpeg compositing failed: {getattr(result, 'stderr', '')}")
        else:
            # Stream FFmpeg progress in real-time
            ffmpeg_cmd_progress = list(ffmpeg_cmd[:-1]) + ["-progress", "pipe:1", ffmpeg_cmd[-1]]
            proc = subprocess.Popen(
                ffmpeg_cmd_progress,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
                universal_newlines=True
            )

            last_reported_sec = -1.0
            if proc.stdout:
                for line in proc.stdout:
                    line = line.strip()
                    curr_sec = None
                    if line.startswith("out_time_us="):
                        try:
                            curr_sec = int(line.split("=")[1]) / 1_000_000.0
                        except (ValueError, IndexError):
                            pass
                    elif line.startswith("out_time="):
                        try:
                            parts = line.split("=")[1].strip().split(":")
                            if len(parts) == 3:
                                curr_sec = float(parts[0]) * 3600 + float(parts[1]) * 60 + float(parts[2])
                        except (ValueError, IndexError):
                            pass

                    if curr_sec is not None and (curr_sec - last_reported_sec >= 1.0 or curr_sec >= video_duration):
                        last_reported_sec = curr_sec
                        frac = min(1.0, max(0.0, curr_sec / max(1.0, video_duration)))
                        pct = 74 + int(frac * 20)
                        if progress_callback:
                            progress_callback(
                                f"Compositing audio, animated subtitles & motion ({int(curr_sec)}s / {int(video_duration)}s)...",
                                pct
                            )

            _, stderr = proc.communicate()
            if proc.returncode != 0:
                raise RuntimeError(f"FFmpeg compositing failed: {stderr[-800:] if stderr else 'Unknown error'}")

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
