"""
test_fast_editor.py - Test suite for Step 2 Fast Scene Editor (Auto & Manual Segment)
Tests all new endpoints and operations with offline mocks.
"""

import os
import unittest
from unittest.mock import patch
from fastapi.testclient import TestClient

from app import app
from engine.visual_director.segment_session import (
    create_session,
    generate_auto_session,
    load_session,
    Segment,
    StoryboardSession
)


class TestFastEditor(unittest.TestCase):

    def setUp(self):
        self.client = TestClient(app)
        self.script = (
            "The luxury hotel was quiet at midnight. "
            "Suddenly, security guards ran to Room 307. "
            "The heavy wooden door opened slowly."
        )

    def test_01_create_manual_session(self):
        """Manual Segment mode: creates scenes with prompts without calling image gen."""
        res = self.client.post("/api/segments/create", json={
            "script": self.script,
            "mode": "manual",
            "manual_delimiter": False
        })
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["mode"], "manual")
        self.assertGreaterEqual(len(data["segments"]), 2)
        
        # Verify prompts and blank media
        for seg in data["segments"]:
            self.assertTrue(len(seg["image_prompt"]) > 0)
            self.assertTrue(len(seg["video_prompt"]) > 0)
            self.assertEqual(seg["media_type"], "blank")
            self.assertEqual(seg["image_url"], "")

    @patch("engine.flux.generate_flux_image")
    def test_02_auto_generate_session(self, mock_flux):
        """Auto mode: splits script, plans prompts, calls FLUX image generation."""
        mock_flux.return_value = (True, "flux")

        res = self.client.post("/api/auto/generate", json={
            "script": self.script
        })
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["mode"], "auto")
        self.assertGreaterEqual(len(data["segments"]), 2)

        for seg in data["segments"]:
            self.assertTrue(len(seg["image_prompt"]) > 0)
            self.assertTrue(len(seg["video_prompt"]) > 0)

    def test_03_edit_prompts(self):
        """Tests editing image_prompt and video_prompt individually."""
        res = self.client.post("/api/segments/create", json={
            "script": self.script,
            "mode": "manual"
        })
        data = res.json()
        session_id = data["session_id"]
        seg_id = data["segments"][0]["segment_id"]

        # Edit image prompt
        res_img = self.client.post(f"/api/segments/{session_id}/edit_prompt", json={
            "segment_id": seg_id,
            "new_prompt": "Custom 9:16 vertical photorealistic image prompt",
            "kind": "image"
        })
        self.assertEqual(res_img.status_code, 200)
        data_img = res_img.json()
        self.assertEqual(data_img["segments"][0]["image_prompt"], "Custom 9:16 vertical photorealistic image prompt")

        # Edit video prompt
        res_vid = self.client.post(f"/api/segments/{session_id}/edit_prompt", json={
            "segment_id": seg_id,
            "new_prompt": "Custom 9:16 vertical video prompt with camera pan",
            "kind": "video"
        })
        self.assertEqual(res_vid.status_code, 200)
        data_vid = res_vid.json()
        self.assertEqual(data_vid["segments"][0]["video_prompt"], "Custom 9:16 vertical video prompt with camera pan")

    def test_04_media_upload_and_clear(self):
        """Tests uploading media and clearing media on a segment."""
        res = self.client.post("/api/segments/create", json={
            "script": self.script,
            "mode": "manual"
        })
        data = res.json()
        session_id = data["session_id"]
        seg_id = data["segments"][0]["segment_id"]

        # Upload dummy image
        dummy_content = b"\xFF\xD8\xFF\xE0\x00\x10JFIF" + b"\x00" * 200
        res_upload = self.client.post(
            f"/api/segments/{session_id}/upload_media",
            data={"segment_id": seg_id},
            files={"file": ("test_pic.jpg", dummy_content, "image/jpeg")}
        )
        self.assertEqual(res_upload.status_code, 200)
        data_upload = res_upload.json()
        s0 = data_upload["segments"][0]
        self.assertTrue(s0["is_custom"])
        self.assertEqual(s0["source"], "manual")
        self.assertEqual(s0["media_type"], "image")
        self.assertTrue(len(s0["image_url"]) > 0)

        # Clear media
        res_clear = self.client.post(f"/api/segments/{session_id}/clear_media", json={
            "segment_id": seg_id
        })
        self.assertEqual(res_clear.status_code, 200)
        data_clear = res_clear.json()
        s0_cleared = data_clear["segments"][0]
        self.assertFalse(s0_cleared["is_custom"])
        self.assertEqual(s0_cleared["image_url"], "")
        self.assertEqual(s0_cleared["media_type"], "blank")

    def test_05_verbatim_script_sync(self):
        """Tests that editing segment text synchronizes session.script_text."""
        res = self.client.post("/api/segments/create", json={
            "script": "First sentence here. Second sentence follows.",
            "mode": "manual"
        })
        data = res.json()
        session_id = data["session_id"]
        seg_id = data["segments"][0]["segment_id"]

        res_edit = self.client.post(f"/api/segments/{session_id}/edit_text", json={
            "segment_id": seg_id,
            "new_text": "Modified first sentence here."
        })
        self.assertEqual(res_edit.status_code, 200)
        data_edit = res_edit.json()
        self.assertIn("Modified first sentence here.", data_edit["script_text"])


if __name__ == "__main__":
    unittest.main()
