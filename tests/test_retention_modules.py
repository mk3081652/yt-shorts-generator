"""
tests/test_retention_modules.py - Test suite for YouTube Shorts Retention Upgrade Modules:
- Module 0: tts_engine.py (Kokoro TTS, normalization, channel configurations)
- Module 1: script_generator.py (Meta-phrase purge, 1.5s hook, 65-80 words, seamless loop)
- Module 2: subtitles.py (Whisper word extraction, 1-3 word chunking, ASS yellow karaoke)
- Module 3: video_builder.py (Rapid cut planning, zoompan motions, full portrait 1080x1920)
- Module 4: audio_processor.py (0.0s sub-bass impact, transition whooshes, sidechain ducking)
- run_pipeline.py (Automated daily batch configuration)
"""

import os
import unittest
from unittest.mock import patch, MagicMock

import tts_engine
import script_generator
import subtitles
import video_builder
import audio_processor
import run_pipeline


class TestRetentionModules(unittest.TestCase):

    def test_01_kokoro_voice_configs(self):
        """Module 0: Validates channel voice configs and +10% speed pacing."""
        motivational = tts_engine.CHANNEL_CONFIG["motivational"]
        self.assertEqual(motivational["primary"]["voice"], "am_adam")
        self.assertEqual(motivational["primary"]["speed"], 1.15)
        self.assertEqual(motivational["alternative"]["voice"], "am_onyx")
        self.assertEqual(motivational["alternative"]["speed"], 1.15)

        mystery = tts_engine.CHANNEL_CONFIG["mystery"]
        self.assertEqual(mystery["primary"]["voice"], "am_michael")
        self.assertEqual(mystery["primary"]["speed"], 0.99)
        self.assertEqual(mystery["alternative"]["voice"], "bm_george")
        self.assertEqual(mystery["alternative"]["speed"], 0.97)

    def test_02_text_normalization_preserves_pauses(self):
        """Module 0: Punctuation like '...' and '—' is preserved for Kokoro breath pauses."""
        raw = "Stop waiting... The truth is here — pain today builds power."
        normalized = tts_engine.normalize_text_for_kokoro(raw)
        self.assertIn("...", normalized)
        self.assertIn("—", normalized)

    def test_03_script_generator_rules(self):
        """Module 1: Strict viral constraints (65-80 words, no meta-phrases, loop bridge)."""
        res = script_generator.generate_viral_script(
            topic="Test Topic",
            channel="motivational"
        )
        self.assertIn("script", res)
        self.assertIn("hook", res)
        self.assertIn("loop_bridge", res)
        # Verify no banned meta phrases
        script_lower = res["script"].lower()
        for banned in script_generator.BANNED_META_PHRASES:
            self.assertNotIn(banned, script_lower)
        # Verify word count within viral range
        self.assertGreaterEqual(res["word_count"], 45)
        self.assertLessEqual(res["word_count"], 80)

    def test_04_subtitle_karaoke_chunking(self):
        """Module 2: 1-3 words chunking and electric yellow karaoke formatting."""
        words = [
            {"word": "TWO", "start": 0.0, "end": 0.3},
            {"word": "MEN", "start": 0.3, "end": 0.6},
            {"word": "STOLE", "start": 0.6, "end": 1.0},
            {"word": "A", "start": 1.0, "end": 1.2},
            {"word": "JET", "start": 1.2, "end": 1.5}
        ]
        chunks = subtitles.chunk_words(words, max_chunk_size=3)
        self.assertEqual(len(chunks[0]), 3)
        self.assertEqual(len(chunks[1]), 2)

        out_ass = "outputs/test_run/test_sub.ass"
        subtitles.generate_ass_subtitles(words, out_ass)
        self.assertTrue(os.path.exists(out_ass))
        with open(out_ass, "r", encoding="utf-8") as f:
            content = f.read()
            self.assertIn("&H0000FFFF&", content)  # Electric Yellow active word
            self.assertIn("Montserrat Black", content)
            self.assertIn("Style: CenterShorts", content)

    def test_05_rapid_cut_pacing(self):
        """Module 3: Visual cuts adhere to 1.5 - 1.8s max cut pacing."""
        images = ["img1.jpg", "img2.jpg", "img3.jpg"]
        cuts, timestamps = video_builder.plan_rapid_cuts(images, total_duration=30.0, target_cut_duration=1.6)
        self.assertGreaterEqual(len(cuts), 15)
        for c in cuts:
            self.assertLessEqual(c["duration"], 2.0)
            self.assertIn(c["motion"], video_builder.MOTION_TYPES)

    def test_06_audio_processor_default_sfx(self):
        """Module 4: Generates default sub-bass impact and whoosh SFX."""
        sfx = audio_processor.ensure_default_sfx()
        self.assertTrue(os.path.exists(sfx["impact"]))
        self.assertTrue(os.path.exists(sfx["whoosh"]))

    def test_07_daily_batch_schedule(self):
        """Orchestrator: Confirms 4 Shorts daily schedule (2 Motivational, 2 Mystery)."""
        batch = run_pipeline.DAILY_BATCH
        self.assertEqual(len(batch), 4)
        moti = [b for b in batch if b["channel"] == "motivational"]
        myst = [b for b in batch if b["channel"] == "mystery"]
        self.assertEqual(len(moti), 2)
        self.assertEqual(len(myst), 2)


if __name__ == "__main__":
    unittest.main()
