import unittest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

from app import app, format_edge_tts_rate
from engine.project import create_project, edit_scene_duration, load_project


class TestCapCutVoiceoverFeatures(unittest.TestCase):

    def setUp(self):
        self.client = TestClient(app)

    def test_format_edge_tts_rate(self):
        """Rates convert properly to Edge TTS percentage strings."""
        self.assertEqual(format_edge_tts_rate("0.85"), "-15%")
        self.assertEqual(format_edge_tts_rate("0.85x"), "-15%")
        self.assertEqual(format_edge_tts_rate("1.00"), "+0%")
        self.assertEqual(format_edge_tts_rate("1.10"), "+10%")
        self.assertEqual(format_edge_tts_rate("+15%"), "+15%")
        self.assertEqual(format_edge_tts_rate(None), "+0%")

    def test_edit_scene_duration(self):
        """Updating scene duration updates scene and project total duration."""
        script = "Scene 1: First scene.\n\nScene 2: Second scene."
        project = create_project(script=script, start="manual")
        self.assertEqual(len(project.scenes), 2)
        sc1_id = project.scenes[0].id

        updated, err, code = edit_scene_duration(project.id, sc1_id, 5.5)
        self.assertEqual(code, 200)
        self.assertIsNone(err)
        self.assertEqual(updated.scenes[0].duration, 5.5)
        self.assertAlmostEqual(updated.total_duration, 5.5 + updated.scenes[1].duration, places=1)

    def test_api_edit_duration_endpoint(self):
        """POST /api/projects/{id}/edit_duration updates duration via HTTP."""
        script = "Scene 1: Alpha.\n\nScene 2: Beta."
        project = create_project(script=script, start="manual")
        sc2_id = project.scenes[1].id

        res = self.client.post(
            f"/api/projects/{project.id}/edit_duration",
            json={"segment_id": sc2_id, "duration": 4.2}
        )
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["scenes"][1]["duration"], 4.2)

    @patch("app.search_pexels_videos")
    def test_api_stock_search(self, mock_search):
        """POST /api/stock/search queries stock videos and returns list."""
        mock_search.return_value = [
            {"id": "12345", "duration": 6.5, "thumbnail": "https://img.jpg", "download_url": "https://vid.mp4"}
        ]
        res = self.client.post(
            "/api/stock/search",
            json={"query": "ocean waves", "limit": 5}
        )
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["query"], "ocean waves")
        self.assertEqual(len(data["results"]), 1)
        self.assertEqual(data["results"][0]["id"], "12345")


if __name__ == "__main__":
    unittest.main()
