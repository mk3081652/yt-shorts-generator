"""
engine/compositor.py - Master Compositing Pipeline for YouTube Shorts
Combines TTS voiceover, ASS subtitles, BGM auto-ducking, and scene B-roll into 1080x1920 MP4.
"""

import os
import uuid
import subprocess
import imageio_ffmpeg
from typing import Dict, Any, Callable, Optional, List

from engine.tts import generate_speech_with_words
from engine.subtitles import generate_ass_subtitles
from engine.audio import get_bgm_file_path
from engine.scene_director import render_broll
from engine.visual_director.segment_session import load_session

FFMPEG_EXE = imageio_ffmpeg.get_ffmpeg_exe()


def align_scenes_to_word_boundaries(
    scenes: List[Dict[str, Any]],
    word_boundaries: List[Dict[str, Any]],
    total_duration: float
) -> List[Dict[str, Any]]:
    """
    Derives scene start and end times from TTS word_boundaries (cumulative word counts).
    Ensures scene transitions match spoken narration timestamps exactly.
    """
    if not scenes:
        return []

    total_words = len(word_boundaries)
    if total_words == 0:
        dur_each = max(1.0, total_duration / len(scenes))
        aligned = []
        for s in scenes:
            sc_copy = dict(s)
            sc_copy["duration"] = dur_each
            aligned.append(sc_copy)
        return aligned

    aligned = []
    curr_word_idx = 0
    prev_end_time = 0.0

    for i, sc in enumerate(scenes):
        sc_copy = dict(sc)
        sc_text = sc.get("narration") or sc.get("text") or ""
        num_words = max(1, len(sc_text.split()))
        next_word_idx = min(curr_word_idx + num_words, total_words)

        start_time = prev_end_time
        if i == len(scenes) - 1 or next_word_idx >= total_words:
            end_time = total_duration
        else:
            end_time = word_boundaries[next_word_idx - 1]["end"]
            if end_time <= start_time:
                end_time = start_time + 1.0

        dur = max(0.5, end_time - start_time)
        sc_copy["duration"] = dur
        aligned.append(sc_copy)
        curr_word_idx = next_word_idx
        prev_end_time = end_time

    sum_dur = sum(s["duration"] for s in aligned)
    if sum_dur > 0 and abs(sum_dur - total_duration) > 0.1:
        diff = total_duration - sum_dur
        aligned[-1]["duration"] = max(0.5, aligned[-1]["duration"] + diff)

    return aligned


def render_shorts_video(
    script_text: str,
    voice: str = "en-US-ChristopherNeural",
    voice_rate: str = "+10%",
    subtitle_style: str = "mrbeast",
    bgm_track: str = "mystery_suspense",
    bgm_volume: float = 0.18,
    progress_callback: Optional[Callable[[str, int], None]] = None,
    scene_overrides: Optional[Dict[str, str]] = None,
    preview_scenes: Optional[List[Dict[str, Any]]] = None,
    session_id: Optional[str] = None,
    **kwargs
) -> Dict[str, Any]:
    """
    Renders 1080x1920 YouTube Short:
    1. Synthesizes voiceover + extracts word timestamps.
    2. Builds custom ASS viral subtitles.
    3. Aligns scenes to word boundaries and renders scene B-roll sequentially.
    4. Mixes audio tracks with auto-ducking and renders final MP4.
    """
    job_id = str(uuid.uuid4())[:8]
    work_dir = os.path.abspath(f"outputs/temp_{job_id}")
    os.makedirs(work_dir, exist_ok=True)
    final_output_path = os.path.abspath(f"outputs/short_{job_id}.mp4")

    try:
        # Check if session has prepared voice timeline matching current voice/rate
        actual_voice_path = None
        word_boundaries = None
        total_duration = None

        if session_id:
            sess = load_session(session_id)
            if sess:
                if not script_text.strip() and sess.script_text:
                    script_text = sess.script_text
                if not preview_scenes:
                    preview_scenes = [s.to_dict() for s in sess.segments]

                tl = getattr(sess, "timeline", {}) or {}
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

        # Step 1: Voiceover synthesis
        if progress_callback:
            progress_callback("Generating hyper-realistic AI voiceover...", 15)

        if not actual_voice_path:
            voice_path = os.path.join(work_dir, "voice.mp3")
            import asyncio
            actual_voice_path, word_boundaries, total_duration = asyncio.run(
                generate_speech_with_words(
                    text=script_text,
                    voice=voice,
                    rate=voice_rate,
                    output_audio_path=voice_path
                )
            )

        video_duration = total_duration + 0.35

        # Step 2: Subtitle Generation
        if progress_callback:
            progress_callback("Designing viral word-by-word subtitles...", 35)

        ass_path = os.path.join(work_dir, "subtitles.ass")
        generate_ass_subtitles(
            word_boundaries=word_boundaries,
            output_ass_path=ass_path,
            style_name=subtitle_style,
            max_words_per_segment=2
        )

        # Step 3: Align scenes and render B-roll
        if progress_callback:
            progress_callback("Rendering scene visuals and camera motion...", 55)

        # Handle scene overrides
        scenes = list(preview_scenes or [])
        if scene_overrides:
            for idx, sc in enumerate(scenes):
                sc_id_str = str(idx)
                ov = scene_overrides.get(sc_id_str) or scene_overrides.get(idx) or scene_overrides.get(sc.get("scene_id"))
                if ov:
                    sc["image_path"] = ov
                    sc["image_url"] = f"/outputs/ai_previews/{os.path.basename(ov)}"
                    sc["source"] = "manual"
                    sc["is_custom"] = True

        aligned_scenes = align_scenes_to_word_boundaries(
            scenes=scenes,
            word_boundaries=word_boundaries,
            total_duration=video_duration
        )

        broll_video_path = os.path.join(work_dir, "broll_master.mp4")
        render_broll(
            scenes=aligned_scenes,
            total_duration=video_duration,
            output_path=broll_video_path,
            temp_dir=work_dir
        )

        # Step 4: Final FFmpeg composition
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
            for f in os.listdir(work_dir):
                os.remove(os.path.join(work_dir, f))
            os.rmdir(work_dir)
        except Exception:
            pass
