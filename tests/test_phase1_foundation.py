"""
tests/test_phase1_foundation.py - Unit tests for Phase 1 Foundation:
- config.py typed getters
- llm.py Gemini 3.8 Flash client (headers, thinkingConfig, retries, fallbacks)
- flux.py Cloudflare Workers AI FLUX generator (cooldown, 9:16 crop, failures)
- app.py /healthz endpoint
"""

import os
import io
import time
import base64
import unittest
import urllib.error
from unittest.mock import patch, MagicMock
from PIL import Image
from fastapi.testclient import TestClient

from app import app
import engine.config as config
import engine.llm as llm
import engine.flux as flux


class TestPhase1Foundation(unittest.TestCase):

    def setUp(self):
        self.client = TestClient(app)
        flux.clear_cooldown()

    def tearDown(self):
        flux.clear_cooldown()

    # ---------------------------------------------------------
    # 1. Config Getters
    # ---------------------------------------------------------
    def test_config_defaults(self):
        """Test default values of config getters."""
        with patch.dict("os.environ", {}, clear=True):
            self.assertEqual(config.get_gemini_model(), "gemini-3.8-flash")
            self.assertEqual(config.get_gemini_fallback_models(), ["gemini-3.7-flash", "gemini-flash-latest"])
            self.assertEqual(config.get_gemini_thinking_level(), "low")
            self.assertEqual(config.get_vision_qa(), 0)
            self.assertEqual(config.get_flux_model(), "@cf/black-forest-labs/flux-1-schnell")
            self.assertEqual(config.get_flux_steps(), 4)
            self.assertEqual(config.get_flux_timeout(), 45)
            self.assertEqual(config.get_flux_cooldown_seconds(), 900)

    def test_config_overrides(self):
        """Test that environment variables properly override config getters."""
        overrides = {
            "GEMINI_API_KEY": "test-gemini-key",
            "GEMINI_MODEL": "custom-gemini-model",
            "GEMINI_FALLBACK_MODELS": "model-a, model-b",
            "GEMINI_THINKING_LEVEL": "medium",
            "VISION_QA": "1",
            "CLOUDFLARE_ACCOUNT_ID": "cf-acc-123",
            "CLOUDFLARE_API_TOKEN": "cf-token-456",
            "FLUX_STEPS": "6",
            "FLUX_TIMEOUT": "60",
            "FLUX_COOLDOWN_SECONDS": "300"
        }
        with patch.dict("os.environ", overrides, clear=True):
            self.assertEqual(config.get_gemini_api_key(), "test-gemini-key")
            self.assertEqual(config.get_gemini_model(), "custom-gemini-model")
            self.assertEqual(config.get_gemini_fallback_models(), ["model-a", "model-b"])
            self.assertEqual(config.get_gemini_thinking_level(), "medium")
            self.assertEqual(config.get_vision_qa(), 1)
            self.assertEqual(config.get_cloudflare_account_id(), "cf-acc-123")
            self.assertEqual(config.get_cloudflare_api_token(), "cf-token-456")
            self.assertEqual(config.get_flux_steps(), 6)
            self.assertEqual(config.get_flux_timeout(), 60)
            self.assertEqual(config.get_flux_cooldown_seconds(), 300)

    def test_flux_steps_clamped(self):
        """Flux steps should be clamped between 1 and 8."""
        with patch.dict("os.environ", {"FLUX_STEPS": "20"}, clear=True):
            self.assertEqual(config.get_flux_steps(), 8)
        with patch.dict("os.environ", {"FLUX_STEPS": "0"}, clear=True):
            self.assertEqual(config.get_flux_steps(), 1)

    # ---------------------------------------------------------
    # 2. LLM Gemini Client
    # ---------------------------------------------------------
    @patch("engine.llm._post")
    def test_llm_header_and_body_rules(self, mock_post):
        """Verify API key is sent in header (not URL), and no forbidden parameters in body."""
        mock_post.return_value = {
            "candidates": [{"content": {"parts": [{"text": '{"result": "success"}'}]}}]
        }

        with patch.dict("os.environ", {"GEMINI_API_KEY": "secret-key", "GEMINI_MODEL": "gemini-3.8-flash"}):
            text, model = llm.generate_content("hello world", thinking_level="low")

            self.assertEqual(text, '{"result": "success"}')
            self.assertEqual(model, "gemini-3.8-flash")
            self.assertEqual(mock_post.call_count, 1)

            url, headers, body = mock_post.call_args[0][0], mock_post.call_args[0][1], mock_post.call_args[0][2]
            # Key MUST be in header, not in URL
            self.assertNotIn("secret-key", url)
            self.assertEqual(headers.get("x-goog-api-key"), "secret-key")

            # Generation config checks
            gen_cfg = body.get("generationConfig", {})
            self.assertNotIn("temperature", gen_cfg)
            self.assertNotIn("topP", gen_cfg)
            self.assertNotIn("topK", gen_cfg)
            self.assertNotIn("candidateCount", gen_cfg)
            self.assertIn("thinkingConfig", gen_cfg)
            self.assertNotEqual(gen_cfg["thinkingConfig"].get("thinkingLevel"), "minimal")
            self.assertEqual(gen_cfg["thinkingConfig"].get("thinkingLevel"), "low")

    @patch("engine.llm._post")
    def test_llm_http_400_retry_without_thinking(self, mock_post):
        """On HTTP 400 with thinkingConfig, retry once without thinkingConfig."""
        err_400 = urllib.error.HTTPError("http://test", 400, "Bad Request", {}, None)
        success_data = {
            "candidates": [{"content": {"parts": [{"text": "recovered response"}]}}]
        }
        mock_post.side_effect = [err_400, success_data]

        with patch.dict("os.environ", {"GEMINI_API_KEY": "secret-key"}):
            text, model = llm.generate_content("prompt", thinking_level="low")
            self.assertEqual(text, "recovered response")
            self.assertEqual(mock_post.call_count, 2)

            # Second call must NOT have thinkingConfig
            second_body = mock_post.call_args_list[1][0][2]
            self.assertNotIn("thinkingConfig", second_body.get("generationConfig", {}))

    @patch("engine.llm._post")
    def test_llm_fallback_on_429(self, mock_post):
        """On HTTP 429, fall back to the next model in sequence."""
        err_429 = urllib.error.HTTPError("http://test", 429, "Rate Limited", {}, None)
        success_data = {
            "candidates": [{"content": {"parts": [{"text": "fallback response"}]}}]
        }
        mock_post.side_effect = [err_429, success_data]

        with patch.dict("os.environ", {
            "GEMINI_API_KEY": "secret-key",
            "GEMINI_MODEL": "gemini-3.8-flash",
            "GEMINI_FALLBACK_MODELS": "gemini-3.7-flash"
        }):
            with patch("time.sleep"):  # Speed up test
                text, model = llm.generate_content("prompt")
                self.assertEqual(text, "fallback response")
                self.assertEqual(model, "gemini-3.7-flash")

    # ---------------------------------------------------------
    # 3. FLUX Image Generator
    # ---------------------------------------------------------
    def test_flux_not_configured(self):
        """Returns flux_not_configured when credentials are missing."""
        with patch.dict("os.environ", {}, clear=True):
            ok, reason = flux.generate("a test prompt", "outputs/test_fail.jpg")
            self.assertFalse(ok)
            self.assertEqual(reason, "flux_not_configured")

    @patch("engine.flux._post_cf")
    def test_flux_success_with_9_16_crop(self, mock_post):
        """Successful FLUX call saves a 1080x1920 9:16 cropped JPEG."""
        # Create a test square image in memory
        test_img = Image.new("RGB", (512, 512), color=(255, 0, 0))
        buf = io.BytesIO()
        test_img.save(buf, format="JPEG")
        b64_img = base64.b64encode(buf.getvalue()).decode("utf-8")

        mock_post.return_value = {
            "success": True,
            "result": {"image": b64_img}
        }

        out_path = "outputs/test_crop_out.jpg"
        if os.path.exists(out_path):
            os.remove(out_path)

        with patch.dict("os.environ", {
            "CLOUDFLARE_ACCOUNT_ID": "acc-id",
            "CLOUDFLARE_API_TOKEN": "token"
        }):
            ok, reason = flux.generate("a test prompt", out_path)
            self.assertTrue(ok)
            self.assertEqual(reason, "flux")
            self.assertTrue(os.path.exists(out_path))

            # Verify saved image is 1080x1920 (9:16)
            with Image.open(out_path) as saved_img:
                self.assertEqual(saved_img.size, (1080, 1920))

        # Cleanup
        if os.path.exists(out_path):
            os.remove(out_path)

    @patch("engine.flux._post_cf")
    def test_flux_rate_limited_cooldown(self, mock_post):
        """HTTP 429 sets cooldown timestamp and subsequent calls fail fast without network."""
        err_429 = urllib.error.HTTPError("http://test", 429, "Too Many Requests", {}, None)
        mock_post.side_effect = err_429

        out_path = "outputs/test_rate_out.jpg"
        with patch.dict("os.environ", {
            "CLOUDFLARE_ACCOUNT_ID": "acc-id",
            "CLOUDFLARE_API_TOKEN": "token",
            "FLUX_COOLDOWN_SECONDS": "900"
        }):
            ok1, reason1 = flux.generate("prompt 1", out_path)
            self.assertFalse(ok1)
            self.assertEqual(reason1, "flux_rate_limited")
            self.assertTrue(flux.is_rate_limited())

            # Second call should fail immediately without calling _post_cf again
            ok2, reason2 = flux.generate("prompt 2", out_path)
            self.assertFalse(ok2)
            self.assertEqual(reason2, "flux_rate_limited")
            self.assertEqual(mock_post.call_count, 1)  # Only called once

            # Cooldown expiration
            flux.clear_cooldown()
            self.assertFalse(flux.is_rate_limited())

    @patch("engine.flux._post_cf")
    def test_flux_failure_writes_no_file(self, mock_post):
        """When FLUX fails, no file is left on disk."""
        mock_post.side_effect = Exception("General network error")
        out_path = "outputs/test_should_not_exist.jpg"
        if os.path.exists(out_path):
            os.remove(out_path)

        with patch.dict("os.environ", {
            "CLOUDFLARE_ACCOUNT_ID": "acc-id",
            "CLOUDFLARE_API_TOKEN": "token"
        }):
            with patch("time.sleep"):
                ok, reason = flux.generate("prompt", out_path)
                self.assertFalse(ok)
                self.assertEqual(reason, "flux_error")
                self.assertFalse(os.path.exists(out_path))

    # ---------------------------------------------------------
    # 4. Endpoints Health Check
    # ---------------------------------------------------------
    def test_healthz_endpoint(self):
        """GET /healthz returns 200 with status: ok."""
        res = self.client.get("/healthz")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json(), {"status": "ok"})

    def test_home_endpoint(self):
        """GET / returns 200 HTML."""
        res = self.client.get("/")
        self.assertEqual(res.status_code, 200)
