import os
import uuid
import subprocess
import imageio_ffmpeg
from typing import Dict, Any, Callable, Optional, List

from engine.tts import generate_speech_with_words
from engine.subtitles import generate_ass_subtitles
from engine.backgrounds import get_target_cut_duration
from engine.audio import get_bgm_file_path
from engine.smart_visuals import generate_smart_broll_video

FFMPEG_EXE = imageio_ffmpeg.get_ffmpeg_exe()

def render_shorts_video(
    script_text: str,
    voice: str = "en-US-ChristopherNeural",
    voice_rate: str = "+10%",
    subtitle_style: str = "mrbeast",
    bg_choice: str = "smart_fast",
    bgm_track: str = "mystery_suspense",
    bgm_volume: float = 0.18,
    progress_callback: Optional[Callable[[str, int], None]] = None,
    scene_overrides: Optional[Dict[str, str]] = None,
    preview_scenes: Optional[List[Dict[str, Any]]] = None
) -> Dict[str, Any]:
    """
    Dedicated Smart AI B-Roll rendering pipeline for viral YouTube Shorts:
    1. Synthesizes voiceover + extracts word timestamps.
    2. Builds custom ASS viral subtitles (proper curly brackets, no raw tags).
    3. Auto-fetches topic images per words of script with 5 continuous Ken Burns motion animations.
    4. Guarantees ZERO repeating images.
    5. Supports manual scene image overrides.
    6. Mixes audio tracks with auto-ducking and renders 1080x1920 MP4.
    """
    job_id = str(uuid.uuid4())[:8]
    work_dir = os.path.abspath(f"outputs/temp_{job_id}")
    os.makedirs(work_dir, exist_ok=True)
    
    final_output_path = os.path.abspath(f"outputs/short_{job_id}.mp4")
    
    try:
        # Step 1: Voiceover synthesis
        if progress_callback:
            progress_callback("Generating hyper-realistic AI voiceover...", 15)
            
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
        
        # Step 3: Visual Background Generation (Smart AI B-Roll with continuous motion)
        if progress_callback:
            progress_callback("Auto-fetching unique images & rendering camera motion per word...", 55)

        norm_ass_path = ass_path.replace("\\", "/").replace(":", "\\:")
        bgm_file = get_bgm_file_path(bgm_track)
        
        ffmpeg_cmd = [FFMPEG_EXE, "-y"]
        video_filter_in = "[0:v]"
        
        # Handle user-uploaded video if chosen
        if bg_choice.startswith("file_"):
            filename = bg_choice.replace("file_", "")
            local_file = os.path.abspath(os.path.join("assets/backgrounds", filename))
            if os.path.exists(local_file):
                ffmpeg_cmd.extend(["-stream_loop", "-1", "-i", local_file])
                video_filter_in = "[0:v]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,format=yuv420p"
            else:
                bg_choice = "smart_fast"

        # Smart AI B-Roll (Gemini AI Ultra or Authentic Archive)
        if not bg_choice.startswith("file_"):
            cut_duration = get_target_cut_duration(bg_choice)
            broll_video_path = os.path.join(work_dir, "broll_master.mp4")
            if bg_choice == "ai_gemini":
                from engine.gemini_visuals import generate_gemini_ai_broll
                generate_gemini_ai_broll(
                    script_text=script_text,
                    total_duration=video_duration,
                    output_path=broll_video_path,
                    temp_dir=work_dir,
                    target_cut_duration=cut_duration,
                    scene_overrides=scene_overrides,
                    preview_scenes=preview_scenes
                )
            else:
                generate_smart_broll_video(
                    script_text=script_text,
                    total_duration=video_duration,
                    output_path=broll_video_path,
                    temp_dir=work_dir,
                    target_cut_duration=cut_duration,
                    scene_overrides=scene_overrides,
                    preview_scenes=preview_scenes
                )
            # NEVER loop smart b-roll; it is uniquely rendered to exact duration
            ffmpeg_cmd.extend(["-i", broll_video_path])
            video_filter_in = "[0:v]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,format=yuv420p"


            
        # Input 1: Voiceover Audio
        ffmpeg_cmd.extend(["-i", actual_voice_path])
        
        # Video filter chain with burned subtitles
        v_chain = f"{video_filter_in},subtitles=filename='{norm_ass_path}'[vout]"

        # Audio mixing & Auto-Ducking
        if bgm_file and os.path.exists(bgm_file):
            # Input 2: Background Music
            ffmpeg_cmd.extend(["-i", os.path.abspath(bgm_file)])
            filter_complex = (
                f"{v_chain};"
                f"[2:a]aloop=loop=-1:size=2e+09,volume={bgm_volume:.2f}[bgm_loop];"
                f"[1:a]volume=1.0[v_clean];"
                f"[v_clean][bgm_loop]amix=inputs=2:duration=first:dropout_transition=2[aout]"
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
            "-crf", "21",
            "-c:a", "aac",
            "-b:a", "192k",
            "-pix_fmt", "yuv420p",
            final_output_path
        ])
        
        if progress_callback:
            progress_callback("Compositing master 1080x1920 Short with music & subtitles...", 80)

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
