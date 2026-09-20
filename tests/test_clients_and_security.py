"""
test_clients_and_security.py - Comprehensive Unit Tests for Gemini Client, FLUX Client, and Security
Mocked network calls for complete offline test execution.
"""

import os
import json
import base64
import unittest
import urllib.error
from unittest.mock import patch, MagicMock
from PIL import Image

from engine.gemini_client import generate_content
from engine.flux import (
    generate_flux_image,
    is_flux_in_cooldown,
    set_flux_cooldown,
    reset_flux_cooldown,
    crop_to_9_16
)
from app import validate_session_id
from engine.project import (
    create_project,
    upload_media,
    upload_bulk
)


class TestClientsAndSecurity(unittest.TestCase):

    def setUp(self):
        reset_flux_cooldown()

    def tearDown(self):
        reset_flux_cooldown()

    # ==========================================
    # GEMINI CLIENT TESTS
    # ==========================================
    @patch("engine.gemini_client.get_gemini_api_key", return_value="dummy_key")
    @patch("engine.gemini_client._post")
    def test_gemini_request_structure(self, mock_post, mock_key):
        """Verifies x-goog-api-key header and thinkingConfig with thinkingLevel."""
        mock_post.return_value = {
            "candidates": [{
                "content": {"parts": [{"text": '{"result": "success"}'}]}
            }]
        }

        text, model = generate_content("Hello Gemini", thinking_level="low")
        self.assertEqual(text, '{"result": "success"}')
        self.assertIsNotNone(model)

        # Inspect headers and body passed to _post
        call_args = mock_post.call_args
        headers = call_args[0][1]
        body = call_args[0][2]

        self.assertEqual(headers["x-goog-api-key"], "dummy_key")
        self.assertEqual(body["generationConfig"]["thinkingConfig"]["thinkingLevel"], "low")
        self.assertEqual(body["generationConfig"]["responseMimeType"], "application/json")

    @patch("engine.gemini_client.get_gemini_api_key", return_value="dummy_key")
    @patch("engine.gemini_client._post")
    def test_gemini_http_400_retry_without_thinking(self, mock_post, mock_key):
        """HTTP 400 with thinkingConfig triggers retry without thinkingConfig."""
        # 1st call raises 400, 2nd call succeeds
        err_400 = urllib.error.HTTPError("url", 400, "Bad Request", {}, None)
        mock_post.side_effect = [
            err_400,
            {"candidates": [{"content": {"parts": [{"text": "Retry OK"}]}}]}
        ]

        text, model = generate_content("Test Prompt", thinking_level="low")
        self.assertEqual(text, "Retry OK")
        self.assertEqual(mock_post.call_count, 2)

        # Second call should not have thinkingConfig
        second_body = mock_post.call_args_list[1][0][2]
        self.assertNotIn("thinkingConfig", second_body["generationConfig"])

    @patch("engine.gemini_client.get_gemini_api_key", return_value="dummy_key")
    @patch("engine.gemini_client.get_gemini_fallback_models", return_value=["gemini-2.5-flash", "gemini-2.0-flash"])
    @patch("engine.gemini_client._post")
    def test_gemini_429_fallback_models(self, mock_post, mock_fallbacks, mock_key):
        """HTTP 429 backs off and iterates to next fallback model."""
        err_429 = urllib.error.HTTPError("url", 429, "Rate Limit", {}, None)
        mock_post.side_effect = [
            err_429,
            {"candidates": [{"content": {"parts": [{"text": "Fallback OK"}]}}]}
        ]

        text, model = generate_content("Test Prompt")
        self.assertEqual(text, "Fallback OK")
        self.assertEqual(mock_post.call_count, 2)
        # Second call should use fallback model
        second_url = mock_post.call_args_list[1][0][0]
        self.assertIn("gemini-2.5-flash", second_url)

    # ==========================================
    # FLUX CLIENT TESTS
    # ==========================================
    @patch("engine.flux.get_cloudflare_account_id", return_value="cf_acc")
    @patch("engine.flux.get_cloudflare_api_token", return_value="cf_token")
    @patch("urllib.request.urlopen")
    def test_flux_success_and_crop(self, mock_urlopen, mock_tok, mock_acc):
        """FLUX generation decodes base64, saves image, and crops to 9:16."""
        os.makedirs("outputs/test_flux", exist_ok=True)
        out_img = os.path.abspath("outputs/test_flux/flux_out.jpg")

        # Create a dummy 1:1 image in base64
        dummy_img = Image.new("RGB", (512, 512), color=(255, 0, 0))
        dummy_img.save(out_img)
        with open(out_img, "rb") as f:
            b64_str = base64.b64encode(f.read()).decode("utf-8")

        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps({"result": {"image": b64_str}}).encode("utf-8")
        mock_urlopen.return_value.__enter__.return_value = mock_resp

        ok, reason = generate_flux_image("A futuristic city", out_img)
        self.assertTrue(ok)
        self.assertEqual(reason, "flux")
        self.assertTrue(os.path.exists(out_img))

        # Check crop to 9:16
        with Image.open(out_img) as cropped:
            cw, ch = cropped.size
            self.assertAlmostEqual(cw / ch, 9.0 / 16.0, delta=0.05)

        try:
            import shutil
            shutil.rmtree("outputs/test_flux", ignore_errors=True)
        except Exception:
            pass

    @patch("engine.flux.get_cloudflare_account_id", return_value="cf_acc")
    @patch("engine.flux.get_cloudflare_api_token", return_value="cf_token")
    @patch("urllib.request.urlopen")
    def test_flux_rate_limit_cooldown(self, mock_urlopen, mock_tok, mock_acc):
        """HTTP 429 triggers cooldown and immediate rejection on next call."""
        err_429 = urllib.error.HTTPError("url", 429, "Rate Limit", {}, None)
        mock_urlopen.side_effect = err_429

        out_img = os.path.abspath("outputs/test_flux_429.jpg")
        ok, reason = generate_flux_image("Prompt", out_img)
        self.assertFalse(ok)
        self.assertEqual(reason, "flux_rate_limited")
        self.assertTrue(is_flux_in_cooldown())

        # Next call should immediately return flux_rate_limited without calling urlopen
        mock_urlopen.reset_mock()
        ok2, reason2 = generate_flux_image("Prompt 2", out_img)
        self.assertFalse(ok2)
        self.assertEqual(reason2, "flux_rate_limited")
        self.assertEqual(mock_urlopen.call_count, 0)

    # ==========================================
    # SECURITY & UPLOADS TESTS
    # ==========================================
    def test_session_id_path_traversal(self):
        """Rejects session IDs with path traversal characters."""
        with self.assertRaises(Exception):
            validate_session_id("../../../etc/passwd")
        with self.assertRaises(Exception):
            validate_session_id("..\\..\\windows\\system32")
        with self.assertRaises(Exception):
            validate_session_id("session/123")

    @patch("engine.project.plan_scenes_with_director")
    def test_upload_media_magic_bytes(self, mock_dir):
        """Accepts valid image magic bytes and rejects invalid buffers."""
        import io
        mock_dir.return_value = ({
            "scenes": [
                {"scene_index": 1, "text": "First scene.", "image_prompt": "Prompt 1", "duration": 3.0}
            ]
        }, False)
        project = create_project("First scene.", start="manual")
        sc_id = project.scenes[0].id

        # Valid JPEG magic bytes
        img = Image.new("RGB", (100, 100), color=(255, 0, 0))
        buf = io.BytesIO()
        img.save(buf, format="JPEG")
        jpeg_buf = buf.getvalue()

        p_ok, err, code = upload_media(project.id, sc_id, jpeg_buf, "test.jpg")
        self.assertEqual(code, 200)
        self.assertEqual(p_ok.scenes[0].media_type, "image")

        # Invalid buffer (random text/binary without valid magic bytes)
        fake_buf = b"This is plain text pretending to be an image file."
        p_err, err_msg, code_err = upload_media(project.id, sc_id, fake_buf, "fake.jpg")
        self.assertEqual(code_err, 400)
        self.assertIn("Corrupted or invalid", err_msg)

    @patch("engine.project.plan_scenes_with_director")
    def test_bulk_upload_mapping(self, mock_dir):
        """Bulk upload assigns files sequentially to scenes."""
        import io
        mock_dir.return_value = ({
            "scenes": [
                {"scene_index": 1, "text": "Scene 1.", "image_prompt": "Prompt 1", "duration": 3.0},
                {"scene_index": 2, "text": "Scene 2.", "image_prompt": "Prompt 2", "duration": 3.0}
            ]
        }, False)
        project = create_project("Scene 1. Scene 2.", start="manual")
        img = Image.new("RGB", (100, 100), color=(0, 255, 0))
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        png_buf = buf.getvalue()

        file_tuples = [
            ("img1.png", png_buf),
            ("img2.png", png_buf),
        ]
        p_bulk, results, err, code = upload_bulk(project.id, file_tuples)
        self.assertEqual(code, 200)
        self.assertEqual(len(results), 2)
        self.assertEqual(p_bulk.scenes[0].media_type, "image")
        self.assertEqual(p_bulk.scenes[1].media_type, "image")




if __name__ == "__main__":
    unittest.main()
