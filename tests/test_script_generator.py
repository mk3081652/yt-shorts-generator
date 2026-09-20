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
