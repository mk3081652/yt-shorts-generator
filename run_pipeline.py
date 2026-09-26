"""
run_pipeline.py - Automated Daily YouTube Shorts Batch Orchestrator

Executes an automated end-to-end production run of 4 viral Shorts daily:
- 2 Motivational Shorts (am_adam & am_onyx at 1.15x speed)
- 2 Mystery Shorts (am_michael at 0.99x speed & bm_george at 0.97x speed)

Full pipeline:
1. Script Generation (Module 1) - 65-80 words, 1.5s hook, seamless loop.
2. Local Kokoro TTS (Module 0) - 24kHz master vocal, +10% pacing boost.
3. Subtitle Generation (Module 2) - Whisper word timestamps, yellow karaoke pop.
4. Layered Audio Design (Module 4) - 0.0s sub-bass impact, whoosh cuts, sidechain ducking.
5. Video Assembly (Module 3) - 1.5-1.8s rapid cuts, portrait crop, subtitle burn-in.
"""

import os
import sys
import time
import logging
from typing import List, Dict, Any
from PIL import Image, ImageDraw, ImageFont

# Enforce UTF-8 console output on Windows
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

# Module imports
from tts_engine import KokoroTTSEngine
from script_generator import generate_viral_script
from subtitles import extract_word_timestamps, generate_ass_subtitles
from audio_processor import build_master_audio
from video_builder import assemble_short_video, plan_rapid_cuts

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("daily_pipeline")

# Daily Batch Schedule: 2 Motivational + 2 Mystery
DAILY_BATCH = [
    {
        "id": "motivational_01",
        "channel": "motivational",
        "voice_type": "primary",   # am_adam (1.15x)
        "topic": "The Brutal Rule of the Top One Percent",
        "bgm_id": "assets/bgm/phonk_energetic.wav"
    },
    {
        "id": "motivational_02",
        "channel": "motivational",
        "voice_type": "alternative", # am_onyx (1.15x)
        "topic": "Why Comfort Destroys Every Man",
        "bgm_id": "assets/bgm/epic_cinematic.wav"
    },
    {
        "id": "mystery_01",
        "channel": "mystery",
        "voice_type": "primary",   # am_michael (0.99x)
        "topic": "The Stolen Boeing 727 That Vanished Off Radar",
        "bgm_id": "assets/bgm/mystery_suspense.wav"
    },
    {
        "id": "mystery_02",
        "channel": "mystery",
        "voice_type": "alternative", # bm_george (0.97x)
        "topic": "Flight 19 and the Disappearing Rescue Plane",
        "bgm_id": "assets/bgm/mystery_suspense.wav"
    }
]


def create_aesthetic_backdrop(output_path: str, title: str, theme: str = "motivational", width: int = 1080, height: int = 1920) -> str:
    """Generates a high-contrast cinematic portrait backdrop if no image is supplied."""
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    img = Image.new("RGB", (width, height), color=(10, 14, 26))
    draw = ImageDraw.Draw(img)

    # Gradient background
    if theme == "mystery":
        c_top = (8, 12, 22)
        c_bot = (18, 28, 48)
        accent = (0, 230, 255)
    else:
        c_top = (18, 10, 10)
        c_bot = (38, 20, 16)
        accent = (255, 200, 0)

    for y in range(height):
        ratio = y / height
        r = int(c_top[0] * (1 - ratio) + c_bot[0] * ratio)
        g = int(c_top[1] * (1 - ratio) + c_bot[1] * ratio)
        b = int(c_top[2] * (1 - ratio) + c_bot[2] * ratio)
        draw.line([(0, y), (width, y)], fill=(r, g, b))

    # Center aesthetic motif
    draw.rectangle([80, 80, width - 80, height - 80], outline=accent, width=4)
    img.save(output_path, "JPEG", quality=92)
    return output_path


def run_single_short(job: Dict[str, Any], output_dir: str = "outputs/daily_batch") -> Dict[str, Any]:
    """Runs a single Short through the complete pipeline end-to-end."""
    short_id = job["id"]
    channel = job["channel"]
    voice_type = job["voice_type"]
    topic = job["topic"]
    bgm_path = job.get("bgm_id")

    job_dir = os.path.join(output_dir, short_id)
    os.makedirs(job_dir, exist_ok=True)

    print(f"\n=======================================================")
    print(f"🎬 PRODUCING SHORT: {short_id.upper()}")
    print(f"Channel: {channel.capitalize()} | Voice: {voice_type.capitalize()} | Topic: '{topic}'")
    print(f"=======================================================")

    # 1. Script Generation
    logger.info("Step 1: Generating viral high-retention script...")
    script_data = generate_viral_script(topic=topic, channel=channel)
    script_text = script_data["script"]
    word_count = script_data["word_count"]
    print(f"📝 Script ({word_count} words):\n\"{script_text}\"")

    # 2. Local Kokoro TTS Synthesis
    logger.info(f"Step 2: Synthesizing voiceover via Kokoro TTS ({channel} - {voice_type})...")
    raw_vo_path = os.path.join(job_dir, "voiceover_raw.wav")
    tts_engine = KokoroTTSEngine.get_instance()
    vo_path, vo_duration = tts_engine.synthesize(
        text=script_text,
        output_path=raw_vo_path,
        channel=channel,
        voice_type=voice_type
    )
    print(f"🎙️ Voiceover generated: {vo_duration:.2f}s -> {vo_path}")

    # 3. Dynamic Word-Level Subtitles
    logger.info("Step 3: Extracting word timestamps and building karaoke subtitles...")
    words = extract_word_timestamps(vo_path, script_text=script_text)
    ass_path = os.path.join(job_dir, "subtitles.ass")
    generate_ass_subtitles(words, ass_path, font_name="Montserrat Black", font_size=78)
    print(f"💬 Styled ASS Karaoke Subtitles created -> {ass_path}")

    # 4. Visual Imagery Setup
    logger.info("Step 4: Preparing portrait visual plates...")
    image_paths: List[str] = []
    # Create 4 distinct complementary visual backdrops for rapid cutting
    for i in range(4):
        bg_path = os.path.join(job_dir, f"plate_{i:02d}.jpg")
        create_aesthetic_backdrop(bg_path, title=topic, theme=channel)
        image_paths.append(bg_path)

    # Plan cut timestamps for audio SFX sync
    _, cut_timestamps = plan_rapid_cuts(image_paths, total_duration=vo_duration, target_cut_duration=1.6)

    # 5. Layered Audio Design
    logger.info("Step 5: Mixing layered audio (0.0s sub-bass impact, whooshes, sidechain ducking)...")
    master_audio_path = os.path.join(job_dir, "master_audio.wav")
    build_master_audio(
        voiceover_path=vo_path,
        output_path=master_audio_path,
        total_duration=vo_duration,
        cut_timestamps=cut_timestamps,
        bgm_path=bgm_path,
        include_hook_impact=True
    )
    print(f"🔊 Master Audio rendered -> {master_audio_path}")

    # 6. Final Video Assembly
    logger.info("Step 6: Assembling 1080x1920 Short with burnt-in subtitles...")
    final_video_path = os.path.join(job_dir, f"{short_id}_final.mp4")
    assemble_short_video(
        image_paths=image_paths,
        audio_path=master_audio_path,
        subtitle_ass_path=ass_path,
        output_path=final_video_path,
        total_duration=vo_duration,
        temp_dir=os.path.join(job_dir, "temp_render")
    )

    file_size_mb = os.path.getsize(final_video_path) / (1024 * 1024)
    print(f"✅ RENDER COMPLETE: {final_video_path} ({file_size_mb:.2f} MB)")

    return {
        "id": short_id,
        "channel": channel,
        "video_path": final_video_path,
        "duration": vo_duration,
        "word_count": word_count,
        "size_mb": round(file_size_mb, 2)
    }


def main():
    print("""
========================================================================
   YOUTUBE SHORTS RETENTION UPGRADE PIPELINE - DAILY BATCH AUTOMATION
========================================================================
Batch: 4 Shorts (2 Motivational + 2 Mystery)
Specs: 1080x1920 Portrait | Kokoro Neural TTS | 1-3 Word Center ASS Karaoke
       Rapid Cuts (1.5-1.8s) | 0.0s Hook Impact | Sidechain Ducking (-22dB)
========================================================================
""")
    start_time = time.time()
    results = []

    for job in DAILY_BATCH:
        try:
            res = run_single_short(job)
            results.append(res)
        except Exception as e:
            logger.error(f"Failed to produce {job['id']}: {e}", exc_info=True)

    elapsed = round(time.time() - start_time, 2)

    print("\n" + "="*60)
    print(f"🎉 DAILY BATCH SUMMARY ({len(results)}/4 Shorts Rendered in {elapsed}s)")
    print("="*60)
    for r in results:
        print(f"• [{r['channel'].upper()}] {r['id']}: {r['duration']:.1f}s | {r['word_count']} words | {r['size_mb']}MB -> {r['video_path']}")
    print("="*60)


if __name__ == "__main__":
    main()
