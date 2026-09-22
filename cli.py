#!/usr/bin/env python3
"""
cli.py - Standalone CLI Entrypoint for YouTube Shorts AI Studio.
Allows direct local rendering and headless pipeline execution meeting
YouTube Partner Program (YPP) monetization criteria.
"""

import os
import sys
import argparse
import json
import shutil
import logging

# Ensure project root is in sys.path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Windows UTF-8 stdout encoding fix
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger("shorts_cli")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="YouTube Shorts AI Studio CLI - High-Retention Monetizable Shorts Engine"
    )

    # Content inputs
    parser.add_argument("--topic", type=str, help="Topic to automatically generate script for.")
    parser.add_argument("--script", type=str, help="Raw script text or path to .txt script file.")
    parser.add_argument(
        "--angle",
        type=str,
        default="investigative_mystery",
        choices=["investigative_mystery", "contrarian_myth", "forensic_details"],
        help="Narrative perspective to avoid repetitive programmatic scripting."
    )

    # Audio inputs
    parser.add_argument(
        "--audio-input", "--custom-voice",
        dest="custom_audio_path",
        type=str,
        default=None,
        help="Human-in-the-loop: Path to custom voiceover audio file (skips TTS generation)."
    )
    parser.add_argument(
        "--tts-provider",
        type=str,
        default=None,
        choices=["edge", "elevenlabs", "openai"],
        help="TTS engine provider (elevenlabs, openai, or edge fallback)."
    )
    parser.add_argument(
        "--voice",
        type=str,
        default="en-US-ChristopherNeural",
        help="Voice name or ElevenLabs voice ID."
    )
    parser.add_argument(
        "--voice-rate",
        type=str,
        default="+10%",
        help="Voice speech speed adjustment (e.g. '+10%%')."
    )

    # Visual & Styling
    parser.add_argument(
        "--subtitle-style",
        type=str,
        default="hyper_yellow",
        help="Subtitle style preset (hyper_yellow, hormozi_red, mrbeast, clean, cyberpunk, etc.)."
    )
    parser.add_argument(
        "--bgm",
        dest="bgm_track",
        type=str,
        default="mystery_suspense",
        help="Background music track preset."
    )
    parser.add_argument(
        "--bgm-volume",
        type=float,
        default=0.18,
        help="Background music volume multiplier (0.0 to 1.0)."
    )
    parser.add_argument(
        "--transition-style",
        type=str,
        default="crossfade",
        choices=["crossfade", "none"],
        help="Scene cut transition style."
    )
    parser.add_argument(
        "--motion-texture",
        type=str,
        default=None,
        choices=["film_grain", "none"],
        help="Visual texture layer (35mm procedural film grain)."
    )

    # Output destination
    parser.add_argument(
        "-o", "--output",
        type=str,
        default=None,
        help="Destination path for final rendered .mp4 video."
    )
    parser.add_argument(
        "--save-metadata",
        action="store_true",
        help="Save YouTube SEO and YPP monetization disclosure metadata as a .json file."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate parameters and test configuration without rendering video."
    )

    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()

    # 1. Resolve Script
    script_text = ""
    if args.script:
        if os.path.isfile(args.script):
            with open(args.script, "r", encoding="utf-8") as f:
                script_text = f.read().strip()
        else:
            script_text = args.script.strip()
    elif args.topic:
        logger.info(f"Generating script for topic: '{args.topic}' with angle '{args.angle}'...")
        from app import synthesize_fallback_script
        api_key = os.environ.get("GEMINI_API_KEY", "").strip()
        if api_key:
            try:
                from engine.gemini_client import generate_content
                prompt = (
                    f"You are an elite, viral YouTube Shorts narrative specialist.\n"
                    f"Write a full-length, high-retention 50-60 second spoken voiceover script about: '{args.topic}'.\n"
                    f"Editorial Angle: {args.angle.replace('_', ' ').title()}.\n"
                    f"Keep total words between 130 and 150 words. Output spoken voiceover words only."
                )
                txt, _ = generate_content(prompt, thinking_level=None, max_output_tokens=3000, api_key=api_key)
                if txt and txt.strip():
                    script_text = txt.strip()
            except Exception as e:
                logger.warning(f"AI script generation error, using fallback: {e}")
        if not script_text:
            script_text = synthesize_fallback_script(args.topic, angle=args.angle)
    elif args.custom_audio_path:
        # User provided an audio file directly without script text
        script_text = ""
    else:
        parser.error("Must provide either --script, --topic, or --audio-input.")

    logger.info("=== YouTube Shorts AI Studio CLI ===")
    if script_text:
        logger.info(f"Script words: {len(script_text.split())}")
        logger.info(f"Preview: {script_text[:100]}...")
    if args.custom_audio_path:
        logger.info(f"Human voiceover override: {args.custom_audio_path}")

    # 2. Dry Run Mode
    if args.dry_run:
        logger.info("[Dry Run] Parameters validated successfully.")
        from engine.metadata import generate_youtube_metadata
        meta = generate_youtube_metadata(script_text or "Viral Story")
        logger.info(f"[Dry Run] Generated Title: {meta.get('title')}")
        logger.info(f"[Dry Run] YPP Disclosure: {meta.get('compliance_notes')}")
        sys.exit(0)

    # 3. Progress callback
    def on_progress(msg: str, pct: int):
        logger.info(f"[{pct}%] {msg}")

    # 4. Render Video
    from engine.render import render_shorts_video
    try:
        res = render_shorts_video(
            script_text=script_text,
            voice=args.voice,
            voice_rate=args.voice_rate,
            subtitle_style=args.subtitle_style,
            bgm_track=args.bgm_track,
            bgm_volume=args.bgm_volume,
            progress_callback=on_progress,
            transition_style=args.transition_style,
            custom_audio_path=args.custom_audio_path,
            tts_provider=args.tts_provider,
            motion_texture=args.motion_texture
        )

        rendered_path = res["video_path"]
        duration = res["duration"]
        final_dest = rendered_path

        # If user specified custom output path, copy it
        if args.output:
            dest = os.path.abspath(args.output)
            os.makedirs(os.path.dirname(dest) or ".", exist_ok=True)
            shutil.copyfile(rendered_path, dest)
            final_dest = dest
            logger.info(f"Saved final video to: {final_dest}")

        # 5. Metadata generation
        from engine.metadata import generate_youtube_metadata
        metadata = generate_youtube_metadata(script_text or "Viral YouTube Short")

        if args.save_metadata or args.output:
            meta_path = (
                f"{os.path.splitext(final_dest)[0]}_metadata.json"
                if args.output else f"{os.path.splitext(rendered_path)[0]}_metadata.json"
            )
            with open(meta_path, "w", encoding="utf-8") as f:
                json.dump(metadata, f, indent=2, ensure_ascii=False)
            logger.info(f"Saved YouTube metadata & YPP disclosures to: {meta_path}")

        logger.info("=" * 45)
        logger.info(f"SUCCESS: Video rendered ({duration}s)")
        logger.info(f"Path: {final_dest}")
        logger.info(f"Title: {metadata.get('title')}")
        logger.info(f"YPP Monetization Flag: altered_or_synthetic_content={metadata.get('altered_or_synthetic_content')}")
        logger.info("=" * 45)

    except Exception as e:
        logger.error(f"Render failed: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
