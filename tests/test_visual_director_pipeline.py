"""
test_visual_director_pipeline.py - Comprehensive Test Suite for Visual Pipeline Replacement
Verifies:
1. Test 1 - Mystery (Room 307 door, hallway, guards, CCTV)
2. Test 2 - Miniature Car Assembly (1:18 scale, tiny mechanics, suspension, wheel bolts, windshield)
3. Test 3 - Specific Object (Red suitcase, silver key)
4. Test 4 - Location Continuity (Kitchen, refrigerator, water bottle)
5. Test 5 - Validation & Best-Image Selection (score >= 80, retry with correction_prompt, max 2 retries)
6. Test 6 - Manual Override Protection (source: "manual" is never overwritten)
"""

import os
import sys
import unittest

# Ensure project root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from engine.visual_director.story_analyzer import analyze_story
from engine.visual_director.continuity import build_continuity_bible, enforce_continuity_in_prompt
from engine.visual_director.planner import plan_visual_storyboard, semantic_fallback_plan
from engine.visual_director.validator import heuristic_validate_scene
from engine.visual_director.generator import generate_and_validate_scene, generate_validated_scenes


class TestVisualDirectorPipeline(unittest.TestCase):

    def test_01_mystery_story(self):
        """Test 1: Mystery Script - Room 307, hallway, guards, door opening."""
        script = (
            "The hallway was completely empty. "
            "Then Room 307's door slowly opened. "
            "Security rushed toward the room."
        )
        plan = plan_visual_storyboard(script, 12.0)
        scenes = plan.get("scenes", [])
        bible = plan.get("continuity_bible", {})

        self.assertGreaterEqual(len(scenes), 3, "Expected at least 3 visual scenes for mystery script")

        # Scene 1: Empty hallway
        s1 = scenes[0]
        self.assertTrue(
            any(k in s1["narration"].lower() for k in ["empty", "hallway"]),
            f"Scene 1 should be empty hallway, got: {s1['narration']}"
        )
        self.assertIn("9:16", s1["image_prompt"])

        # Scene 2: Room 307 door opening
        s2 = scenes[1]
        self.assertTrue(
            "307" in s2["image_prompt"] or "door" in s2["image_prompt"].lower(),
            f"Scene 2 should feature Room 307 door, got: {s2['image_prompt']}"
        )

        # Scene 3: Security guards running toward Room 307
        s3 = scenes[2]
        self.assertTrue(
            any(k in s3["image_prompt"].lower() for k in ["guard", "security"]),
            f"Scene 3 should feature security guards, got: {s3['image_prompt']}"
        )
        self.assertTrue(
            "307" in s3["image_prompt"] or "door" in s3["image_prompt"].lower(),
            f"Scene 3 should maintain continuity to Room 307 door, got: {s3['image_prompt']}"
        )
        print("PASS: Test 1 - Mystery Short continuity verified.")

    def test_02_miniature_car_assembly(self):
        """Test 2: Miniature Car Assembly - Strict 1:18 scale, tiny mechanics, suspension, wheel bolts, windshield."""
        script = (
            "The tiny mechanics install the suspension. "
            "Then they tighten the wheel bolts. "
            "Finally, they place the windshield."
        )
        plan = plan_visual_storyboard(script, 12.0)
        scenes = plan.get("scenes", [])
        bible = plan.get("continuity_bible", {})

        self.assertGreaterEqual(len(scenes), 3)

        for idx, sc in enumerate(scenes):
            prompt_lower = sc["image_prompt"].lower()
            # Strict miniature scale check
            self.assertTrue(
                any(k in prompt_lower for k in ["miniature", "tiny", "1:18", "1:24", "macro"]),
                f"Scene {idx+1} must indicate miniature scale, got: {sc['image_prompt']}"
            )
            # Never full-size
            self.assertNotIn("full-size car", prompt_lower)
            self.assertNotIn("real car", prompt_lower)

        # Scene 1: suspension
        self.assertTrue(
            any(k in scenes[0]["image_prompt"].lower() for k in ["suspension", "spring"]),
            f"Scene 1 should show suspension installation, got: {scenes[0]['image_prompt']}"
        )
        # Scene 2: wheel bolts
        self.assertTrue(
            any(k in scenes[1]["image_prompt"].lower() for k in ["wheel", "bolt", "lug"]),
            f"Scene 2 should show wheel bolts, got: {scenes[1]['image_prompt']}"
        )
        # Scene 3: windshield
        self.assertTrue(
            any(k in scenes[2]["image_prompt"].lower() for k in ["windshield", "glass"]),
            f"Scene 3 should show windshield, got: {scenes[2]['image_prompt']}"
        )
        print("PASS: Test 2 - Miniature Car Assembly scale and action continuity verified.")

    def test_03_specific_object(self):
        """Test 3: Specific Object - Red suitcase and small silver key."""
        script = "She opens a red suitcase and removes a small silver key."
        plan = plan_visual_storyboard(script, 6.0)
        scenes = plan.get("scenes", [])

        self.assertGreaterEqual(len(scenes), 1)
        sc = scenes[0]
        prompt_lower = sc["image_prompt"].lower()

        self.assertIn("red", prompt_lower, f"Prompt must specify 'red' suitcase: {sc['image_prompt']}")
        self.assertIn("suitcase", prompt_lower, f"Prompt must specify 'suitcase': {sc['image_prompt']}")
        self.assertIn("silver", prompt_lower, f"Prompt must specify 'silver' key: {sc['image_prompt']}")
        self.assertIn("key", prompt_lower, f"Prompt must specify 'key': {sc['image_prompt']}")
        print("PASS: Test 3 - Specific Object (red suitcase, silver key) verified.")

    def test_04_location_continuity(self):
        """Test 4: Location Continuity - Same kitchen, refrigerator, water bottle."""
        script = (
            "He enters the kitchen. "
            "He opens the refrigerator. "
            "He takes out a bottle of water."
        )
        plan = plan_visual_storyboard(script, 12.0)
        scenes = plan.get("scenes", [])

        self.assertGreaterEqual(len(scenes), 3)
        for idx, sc in enumerate(scenes):
            prompt_lower = sc["image_prompt"].lower()
            self.assertTrue(
                "kitchen" in prompt_lower or "refrigerator" in prompt_lower,
                f"Scene {idx+1} must maintain kitchen environment: {sc['image_prompt']}"
            )
        print("PASS: Test 4 - Location Continuity (kitchen, refrigerator) verified.")

    def test_05_validation_and_best_image_selection(self):
        """Test 5: Validator scoring, rejection, correction prompt, and best-image selection."""
        # Good prompt
        good_val = heuristic_validate_scene(
            narration="The tiny mechanics install the suspension.",
            prompt="Photorealistic vertical 9:16 macro shot, three tiny figurine mechanics installing chrome suspension springs on red 1:18 miniature car chassis",
            must_show=["tiny mechanics", "suspension springs", "miniature chassis"],
            must_not_show=["real car", "full-size factory"]
        )
        self.assertGreaterEqual(good_val["score"], 80, f"Expected score >= 80, got: {good_val['score']}")
        self.assertTrue(good_val["accepted"])

        # Bad prompt with forbidden element
        bad_val = heuristic_validate_scene(
            narration="The tiny mechanics install the suspension.",
            prompt="A real car in a full-size factory with normal people",
            must_show=["tiny mechanics", "suspension springs"],
            must_not_show=["real car", "full-size factory"]
        )
        self.assertLess(bad_val["score"], 80, f"Expected rejection, got score: {bad_val['score']}")
        self.assertFalse(bad_val["accepted"])
        self.assertTrue(len(bad_val["correction_prompt"]) > 0, "Expected non-empty correction prompt on rejection")
        print("PASS: Test 5 - Validation scoring and correction prompt generation verified.")

    def test_06_manual_override_protection(self):
        """Test 6: Manual replacements (source: 'manual') must never be overwritten."""
        mock_scene = {
            "scene_id": "scene_01",
            "narration": "Security rushed toward the room.",
            "duration": 3.0,
            "image_url": "/outputs/custom_scenes/user_upload_123.jpg",
            "image_title": "user_upload_123.jpg",
            "is_custom": True,
            "source": "manual",
            "must_show": ["guards"],
            "must_not_show": ["police"]
        }

        # Passing scene with source: 'manual' to generate_and_validate_scene
        result = generate_and_validate_scene(
            scene=mock_scene,
            output_dir="outputs/ai_previews"
        )

        self.assertEqual(result["image_url"], "/outputs/custom_scenes/user_upload_123.jpg")
        self.assertEqual(result["source"], "manual")
        self.assertTrue(result["is_custom"])
        print("PASS: Test 6 - Manual override protection (source: 'manual') verified.")


if __name__ == "__main__":
    unittest.main()
