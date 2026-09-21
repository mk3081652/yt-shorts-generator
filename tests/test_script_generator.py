"""
tests/test_script_generator.py - Test suite for AI Script Generator and Spoken Narration Sanitization.
"""

import unittest
from unittest.mock import patch
from fastapi.testclient import TestClient

from app import app, sanitize_spoken_script


class TestScriptGenerator(unittest.TestCase):

    def setUp(self):
        self.client = TestClient(app)

    def test_01_sanitize_prompt_wrapper(self):
        """Sanitizer removes prompt boilerplate and meta instructions from pasted text."""
        raw_pasted = (
            "For the MH370 mystery video, use this cinematic prompt: "
            "**Image prompt:** > Cinematic investigative documentary scene about Malaysia Airlines Flight 370. "
            "Radar screens glow in darkness as the transponder goes silent."
        )
        cleaned = sanitize_spoken_script(raw_pasted)
        self.assertNotIn("For the MH370 mystery video", cleaned)
        self.assertNotIn("**Image prompt:**", cleaned)
        self.assertNotIn(">", cleaned)
        self.assertTrue(cleaned.startswith("Cinematic investigative documentary"))

    def test_02_sanitize_normal_script_untouched(self):
        """Sanitizer leaves clean spoken scripts completely untouched."""
        normal_script = "The Roman Empire was the most formidable force on Earth. But in 476 AD, everything collapsed."
        self.assertEqual(sanitize_spoken_script(normal_script), normal_script)

    @patch("engine.gemini_client.generate_content")
    def test_03_generate_script_success(self, mock_gemini):
        """POST /api/generate_script generates high-retention narration script."""
        mock_gemini.return_value = (
            "In 2014, Malaysia Airlines Flight 370 vanished without a trace into the midnight sky. "
            "239 passengers onboard, yet not a single distress call was made. "
            "Seconds before entering Vietnamese airspace, the transponder was manually switched off. "
            "A decade later, the black box remains silent at the bottom of the sea.",
            "gemini-2.5-flash"
        )

        with patch.dict("os.environ", {"GEMINI_API_KEY": "test-key"}):
            res = self.client.post("/api/generate_script", json={"topic": "MH370 mystery"})
            self.assertEqual(res.status_code, 200)
            data = res.json()
            self.assertEqual(data["topic"], "MH370 mystery")
            self.assertIn("Malaysia Airlines Flight 370", data["script"])
            self.assertEqual(data["model"], "gemini-2.5-flash")

    def test_04_generate_script_empty_topic(self):
        """POST /api/generate_script returns 400 when topic is empty."""
        res = self.client.post("/api/generate_script", json={"topic": "   "})
        self.assertEqual(res.status_code, 400)

    def test_05_beat_splitting_mh370_regression(self):
        """create_story_beats splits cleanly on clause/sentence boundaries without naive 10-word fallback."""
        from engine.beats import create_story_beats
        script = (
            "At 12:41 a.m., Malaysia Airlines Flight MH370 took off from Kuala Lumpur with 239 people on board. "
            "Everything seemed normal… until less than an hour later, the aircraft vanished from civilian radar."
        )
        beats = create_story_beats(script, total_duration=20.0)
        self.assertEqual(len(beats), 3)
        self.assertEqual(
            beats[0][0],
            "At 12:41 a.m., Malaysia Airlines Flight MH370 took off from Kuala Lumpur with 239 people on board."
        )
        self.assertEqual(
            beats[1][0],
            "Everything seemed normal… until less than an hour later,"
        )
        self.assertEqual(
            beats[2][0],
            "the aircraft vanished from civilian radar."
        )
        # Ensure 100% verbatim word preservation
        orig_words = script.split()
        beat_words = " ".join(b for b, _ in beats).split()
        self.assertEqual(orig_words, beat_words)

    @patch("engine.llm.generate_content")
    def test_06_metadata_generation_ai(self, mock_llm):
        """POST /api/generate_metadata generates script-tailored metadata with AI."""
        import json
        mock_llm.return_value = (
            json.dumps({
                "title": "The Vanishing of Flight MH370 ✈️ #shorts",
                "description": "Malaysia Airlines Flight MH370 vanished without a trace with 239 souls onboard. What really happened? #MH370 #Shorts",
                "tags": ["MH370", "Malaysia Airlines", "Flight 370", "aviation mystery", "shorts"],
                "hashtags": "#MH370 #Shorts #AviationMystery"
            }),
            "gemini-flash-lite-latest"
        )
        res = self.client.post("/api/generate_metadata", json={
            "script": "At 12:41 a.m., Malaysia Airlines Flight MH370 took off from Kuala Lumpur with 239 people on board."
        })
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn("MH370", data["title"])
        self.assertIn("#shorts", data["title"].lower())
        self.assertIn("Malaysia Airlines", data["description"])
        self.assertIn("MH370", data["tags"])

    @patch("engine.llm.generate_content")
    def test_07_metadata_generation_nlp_fallback(self, mock_llm):
        """POST /api/generate_metadata falls back to NLP entity extraction when AI is unavailable."""
        mock_llm.side_effect = Exception("Network offline")
        res = self.client.post("/api/generate_metadata", json={
            "script": "At 12:41 a.m., Malaysia Airlines Flight MH370 took off from Kuala Lumpur with 239 people on board. Everything seemed normal… until less than an hour later, the aircraft vanished from civilian radar."
        })
        self.assertEqual(res.status_code, 200)
        data = res.json()
        # Verify it never returns the old generic placeholders
        self.assertNotIn("The Truth About This Will Shock You", data["title"])
        self.assertIn("MH370", data["title"])
        self.assertIn("#shorts", data["title"].lower())
        self.assertIn("Malaysia Airlines Flight MH370", data["tags"])
        self.assertIn("Kuala Lumpur", data["tags"])

    def test_08_metadata_generation_empty(self):
        """POST /api/generate_metadata handles empty or blank script gracefully."""
        res = self.client.post("/api/generate_metadata", json={"script": ""})
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertTrue(len(data["title"]) > 0)
        self.assertTrue(len(data["tags"]) > 0)


