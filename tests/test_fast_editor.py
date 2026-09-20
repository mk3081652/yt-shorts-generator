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

    def test_06_align_scenes(self):
        """Tests scene alignment with both fallback and word boundaries."""
        from engine.scene_director import align_scenes
        segs = [
            {"segment_id": "s1", "text": "The luxury hotel was quiet at midnight.", "duration": 3.0},
            {"segment_id": "s2", "text": "Suddenly security guards ran to Room 307.", "duration": 3.0},
        ]
        
        # Test fallback when no words
        fallback = align_scenes(segs, [], 0.0)
        self.assertEqual(len(fallback), 2)
        self.assertEqual(fallback[0]["start"], 0.0)
        self.assertEqual(fallback[0]["end"], 3.0)
        self.assertEqual(fallback[1]["start"], 3.0)
        self.assertEqual(fallback[1]["end"], 6.0)

        # Test alignment with word boundaries
        words = [
            {"word": "The", "start": 0.0, "end": 0.4},
            {"word": "luxury", "start": 0.4, "end": 0.8},
            {"word": "hotel", "start": 0.8, "end": 1.2},
            {"word": "was", "start": 1.2, "end": 1.5},
            {"word": "quiet", "start": 1.5, "end": 2.0},
            {"word": "at", "start": 2.0, "end": 2.2},
            {"word": "midnight.", "start": 2.2, "end": 2.8},
            {"word": "Suddenly", "start": 2.8, "end": 3.4},
            {"word": "security", "start": 3.4, "end": 4.0},
            {"word": "guards", "start": 4.0, "end": 4.5},
            {"word": "ran", "start": 4.5, "end": 4.8},
            {"word": "to", "start": 4.8, "end": 5.0},
            {"word": "Room", "start": 5.0, "end": 5.4},
            {"word": "307.", "start": 5.4, "end": 6.0},
        ]
        aligned = align_scenes(segs, words, 6.0)
        self.assertEqual(len(aligned), 2)
        self.assertEqual(aligned[0]["start"], 0.0)
        self.assertEqual(aligned[1]["end"], 6.0)
        self.assertGreater(aligned[0]["duration"], 1.0)
        self.assertGreater(aligned[1]["duration"], 1.0)

    @patch("engine.tts.generate_speech_with_words")
    def test_07_prepare_voice_timeline_api(self, mock_tts):
        """Tests POST /api/segments/{id}/prepare_voice, caching, and cache invalidation."""
        async def mock_gen(*args, **kwargs):
            out_path = kwargs.get("output_audio_path", "outputs/mock_tts.mp3")
            os.makedirs(os.path.dirname(out_path) or "outputs", exist_ok=True)
            with open(out_path, "wb") as f:
                f.write(b"mock_mp3_data")
            words = [
                {"word": "The", "start": 0.0, "end": 0.4},
                {"word": "luxury", "start": 0.4, "end": 0.8},
                {"word": "hotel", "start": 0.8, "end": 1.2},
                {"word": "was", "start": 1.2, "end": 1.5},
                {"word": "quiet", "start": 1.5, "end": 2.0},
                {"word": "at", "start": 2.0, "end": 2.2},
                {"word": "midnight.", "start": 2.2, "end": 2.8},
                {"word": "Suddenly,", "start": 2.8, "end": 3.4},
                {"word": "security", "start": 3.4, "end": 4.0},
                {"word": "guards", "start": 4.0, "end": 4.5},
                {"word": "ran", "start": 4.5, "end": 4.8},
                {"word": "to", "start": 4.8, "end": 5.0},
                {"word": "Room", "start": 5.0, "end": 5.4},
                {"word": "307.", "start": 5.4, "end": 6.0},
            ]
            return out_path, words, 6.0

        mock_tts.side_effect = mock_gen

        res = self.client.post("/api/segments/create", json={
            "script": "The luxury hotel was quiet at midnight. Suddenly, security guards ran to Room 307.",
            "mode": "manual"
        })
        session_id = res.json()["session_id"]

        # Call prepare_voice
        prep_res = self.client.post(f"/api/segments/{session_id}/prepare_voice", json={
            "voice": "en-US-ChristopherNeural",
            "rate": "+10%"
        })
        self.assertEqual(prep_res.status_code, 200)
        data = prep_res.json()
        self.assertIn("timeline", data)
        self.assertEqual(data["timeline"]["voice"], "en-US-ChristopherNeural")
        self.assertEqual(len(data["timeline"]["scenes"]), len(data["segments"]))
        self.assertEqual(mock_tts.call_count, 1)

        # Call prepare_voice again -> should hit cache without calling generate_speech_with_words again
        prep_res_cached = self.client.post(f"/api/segments/{session_id}/prepare_voice", json={
            "voice": "en-US-ChristopherNeural",
            "rate": "+10%"
        })
        self.assertEqual(prep_res_cached.status_code, 200)
        self.assertEqual(mock_tts.call_count, 1)

        # Edit text on segment -> should invalidate timeline cache
        seg_id = data["segments"][0]["segment_id"]
        edit_res = self.client.post(f"/api/segments/{session_id}/edit_text", json={
            "segment_id": seg_id,
            "new_text": "A luxury resort was silent at midnight."
        })
        self.assertEqual(edit_res.status_code, 200)
        edit_data = edit_res.json()
        self.assertEqual(edit_data.get("timeline"), {})

    def test_08_sequential_rendering(self):
        """Tests sequential low-RAM clip generation and B-roll concat."""
        from PIL import Image
        from engine.motion import make_blank_clip, create_ken_burns_motion_clip
        from engine.scene_director import render_broll

        os.makedirs("outputs/test_render", exist_ok=True)
        img_path = os.path.abspath("outputs/test_render/test_img.jpg")
        img = Image.new("RGB", (1080, 1920), color=(120, 60, 200))
        img.save(img_path)

        blank_clip = os.path.abspath("outputs/test_render/test_blank.mp4")
        ok_blank = make_blank_clip(1.0, blank_clip)
        self.assertTrue(ok_blank)
        self.assertTrue(os.path.exists(blank_clip))

        push_clip = os.path.abspath("outputs/test_render/test_push.mp4")
        ok_push = create_ken_burns_motion_clip(img_path, 1.0, push_clip, motion="push in")
        self.assertTrue(ok_push)
        self.assertTrue(os.path.exists(push_clip))

        static_clip = os.path.abspath("outputs/test_render/test_static.mp4")
        ok_static = create_ken_burns_motion_clip(img_path, 1.0, static_clip, motion="static")
        self.assertTrue(ok_static)
        self.assertTrue(os.path.exists(static_clip))

        broll_out = os.path.abspath("outputs/test_render/broll_out.mp4")
        scenes = [
            {"image_path": img_path, "media_type": "image", "duration": 1.0, "motion": "push in"},
            {"image_path": "", "media_type": "blank", "duration": 1.0}
        ]
        ok_broll = render_broll(scenes, 2.0, broll_out, "outputs/test_render/temp")
        self.assertTrue(ok_broll)
        self.assertTrue(os.path.exists(broll_out))

        # Cleanup
        try:
            import shutil
            shutil.rmtree("outputs/test_render", ignore_errors=True)
        except Exception:
            pass


if __name__ == "__main__":
    unittest.main()

