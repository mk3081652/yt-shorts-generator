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

    def test_api_auto_sync_voice_lock(self):
        """POST /api/projects/{id}/auto_sync locks durations to timeline voice timestamps."""
        script = "Scene 1: First spoken sentence.\n\nScene 2: Second spoken sentence."
        project = create_project(script=script, start="manual")
        # Give project a timeline with specific timestamps
        project.timeline = {
            "scenes": [
                {"scene_id": project.scenes[0].id, "start": 0.0, "end": 2.2, "duration": 2.2, "text": project.scenes[0].text},
                {"scene_id": project.scenes[1].id, "start": 2.2, "end": 5.4, "duration": 3.2, "text": project.scenes[1].text},
            ]
        }
        from engine.project import save_project
        save_project(project)

        res = self.client.post(
            f"/api/projects/{project.id}/auto_sync",
            json={"mode": "voice_lock"}
        )
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertAlmostEqual(data["scenes"][0]["duration"], 2.2, places=1)
        self.assertAlmostEqual(data["scenes"][1]["duration"], 3.2, places=1)
        self.assertAlmostEqual(data["total_duration"], 5.4, places=1)

    def test_api_auto_sync_rapid_cuts(self):
        """POST /api/projects/{id}/auto_sync subcuts long clips for viral retention."""
        script = "Scene 1: This is a very long dramatic scene that definitely needs to be split up for retention."
        project = create_project(script=script, start="manual")
        # Set scene duration to 6.0 seconds
        project.scenes[0].duration = 6.0
        from engine.project import save_project
        save_project(project)

        res = self.client.post(
            f"/api/projects/{project.id}/auto_sync",
            json={"mode": "rapid_cuts", "max_cut_dur": 2.5}
        )
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertGreaterEqual(len(data["scenes"]), 2)
        for sc in data["scenes"]:
            self.assertLessEqual(sc["duration"], 3.0)

    def test_api_split_at_playhead(self):
        """POST /api/projects/{id}/split_at_playhead cuts scene at exact playhead time."""
        script = "Scene 1: Lightning struck the quiet town without any warning."
        project = create_project(script=script, start="manual")
        project.scenes[0].duration = 4.0
        from engine.project import save_project
        save_project(project)

        res = self.client.post(
            f"/api/projects/{project.id}/split_at_playhead",
            json={"segment_id": project.scenes[0].id, "playhead_time": 2.0}
        )
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(len(data["scenes"]), 2)
        self.assertAlmostEqual(data["scenes"][0]["duration"], 2.0, places=1)
        self.assertAlmostEqual(data["scenes"][1]["duration"], 2.0, places=1)

    def test_api_set_color_filter(self):
        """POST /api/projects/{id}/set_color_filter stores LUT preset."""
        script = "Scene 1: Simple script."
        project = create_project(script=script, start="manual")

        res = self.client.post(
            f"/api/projects/{project.id}/set_color_filter",
            json={"color_filter": "viral_punch"}
        )
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["color_filter"], "viral_punch")

    def test_api_reorder_scene(self):
        """POST /api/projects/{id}/reorder_scene moves scene left or right."""
        script = "Scene 1: First.\n\nScene 2: Second.\n\nScene 3: Third."
        project = create_project(script=script, start="manual")
        sc1_id = project.scenes[0].id
        sc2_id = project.scenes[1].id

        # Move scene 1 to the right (later)
        res = self.client.post(
            f"/api/projects/{project.id}/reorder_scene",
            json={"segment_id": sc1_id, "direction": "right"}
        )
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["scenes"][0]["id"], sc2_id)
        self.assertEqual(data["scenes"][1]["id"], sc1_id)


if __name__ == "__main__":
    unittest.main()

