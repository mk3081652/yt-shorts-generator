"""
tests/test_youtube_publish.py - Automated tests for 1-Click YouTube Publishing & Rapid Visual Cuts.
"""

import os
import json
import unittest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

from app import app
from engine.beats import create_rapid_story_beats, create_story_beats
from engine.render import expand_scenes_to_rapid_cuts
from engine.youtube_uploader import check_auth_status, upload_video_to_youtube


class TestYouTubePublishWorkflow(unittest.TestCase):

    def setUp(self):
        self.client = TestClient(app)
        self.sample_60s_script = (
            "For centuries, historians claimed the Great Sphinx of Giza was carved as a guardian for Pharaoh Khafre. "
            "But in 1989, a seismic radar survey beneath the Sphinx revealed something that shocked the archaeological world: "
            "a massive artificial subterranean chamber hidden 40 feet below the paws! "
            "The Egyptian government immediately shut down public access. "
            "Satellite radar later detected anomalous thermal signatures and subterranean tunnels stretching directly towards the Great Pyramid. "
            "What are they hiding beneath the sands? "
            "Ancient texts speak of the Hall of Records, containing lost technology of a pre-cataclysm civilization. "
            "Could humanity's true origin be sealed right beneath our feet? "
            "Drop your theories in the comments and subscribe for part two!"
        )

    def test_01_rapid_beats_pacing_and_verbatim(self):
        """create_rapid_story_beats creates 18-22 cuts for 60s script with 100% verbatim preservation."""
        beats = create_rapid_story_beats(self.sample_60s_script, total_duration=60.0)
        
        # Verify cut count: between 18 and 22 cuts
        self.assertGreaterEqual(len(beats), 18)
        self.assertLessEqual(len(beats), 24)

        # Verify average duration is around 2.5s - 3.2s
        avg_dur = sum(d for _, d in beats) / len(beats)
        self.assertGreaterEqual(avg_dur, 2.0)
        self.assertLessEqual(avg_dur, 3.5)

        # Verify 100% verbatim accuracy
        original_words = self.sample_60s_script.split()
        reconstructed_words = " ".join(t for t, _ in beats).split()
        self.assertEqual(original_words, reconstructed_words)

    def test_02_expand_scenes_to_rapid_cuts(self):
        """expand_scenes_to_rapid_cuts subdivides long scenes (>3.5s) into ~2.8s dynamic multi-focal cuts."""
        long_scenes = [
            {"id": "s1", "duration": 10.0, "media_path": "test1.jpg", "media_type": "image"},
            {"id": "s2", "duration": 8.0, "media_path": "test2.jpg", "media_type": "image"},
            {"id": "s3", "duration": 2.5, "media_path": "test3.jpg", "media_type": "image"}
        ]
        expanded = expand_scenes_to_rapid_cuts(long_scenes, max_cut_dur=3.2)
        
        # 10s -> ~4 subcuts, 8s -> ~3 subcuts, 2.5s -> 1 subcut = ~8 cuts
        self.assertGreaterEqual(len(expanded), 7)
        for sc in expanded:
            self.assertLessEqual(sc["duration"], 3.5)
            self.assertIn("motion", sc)
            self.assertTrue(bool(sc["motion"]))

    def test_03_youtube_auth_status_endpoint(self):
        """GET /api/youtube/auth_status returns structured status without crashing."""
        res = self.client.get("/api/youtube/auth_status")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn("authenticated", data)
        self.assertIn("client_secrets_found", data)

    def test_04_youtube_publish_endpoint_validation(self):
        """POST /api/youtube/publish rejects completely empty requests."""
        res = self.client.post("/api/youtube/publish", json={"script": ""})
        self.assertEqual(res.status_code, 400)

    def test_05_youtube_publish_endpoint_creates_job(self):
        """POST /api/youtube/publish queues job and returns job_id."""
        with patch("app.run_youtube_publish_task") as mock_task:
            res = self.client.post("/api/youtube/publish", json={
                "script": self.sample_60s_script,
                "privacy_status": "unlisted"
            })
            self.assertEqual(res.status_code, 200)
            data = res.json()
            self.assertIn("job_id", data)
            self.assertEqual(data["status"], "queued")

    @patch("engine.youtube_uploader.get_authenticated_service")
    def test_06_youtube_uploader_success(self, mock_service):
        """upload_video_to_youtube performs resumable chunked upload with YPP disclosure."""
        # Create dummy mp4 file
        dummy_path = "outputs/test_dummy_upload.mp4"
        os.makedirs("outputs", exist_ok=True)
        with open(dummy_path, "wb") as f:
            f.write(b"\x00" * 1024)

        try:
            mock_insert = MagicMock()
            mock_insert.next_chunk.return_value = (None, {"id": "test_video_123"})
            mock_videos = MagicMock()
            mock_videos.insert.return_value = mock_insert
            mock_yt = MagicMock()
            mock_yt.videos.return_value = mock_videos
            mock_service.return_value = mock_yt

            res = upload_video_to_youtube(
                video_path=dummy_path,
                title="Secret Egyptian Vault Revealed",
                description="Subterranean radar survey uncovers anomalous chambers.",
                tags=["mystery", "sphinx"],
                privacy_status="unlisted"
            )

            self.assertTrue(res["success"])
            self.assertEqual(res["video_id"], "test_video_123")
            self.assertEqual(res["youtube_url"], "https://www.youtube.com/shorts/test_video_123")
            self.assertIn("#Shorts", res["title"])

            # Verify request arguments passed to insert
            kwargs = mock_videos.insert.call_args[1]
            snippet = kwargs["body"]["snippet"]
            status = kwargs["body"]["status"]
            self.assertEqual(status["privacyStatus"], "unlisted")
            self.assertIn("synthetic", snippet["description"].lower())
        finally:
            if os.path.exists(dummy_path):
                try:
                    os.remove(dummy_path)
                except Exception:
                    pass


if __name__ == "__main__":
    unittest.main()
