"""
tests/test_phase2_director.py - Test suite for Phase 2: The Director.
Golden prompt compiler tests, basic-mode fallback, and retry logic.
"""

import os
import json
import unittest
from unittest.mock import patch, MagicMock

import engine.director as director
from engine.beats import create_story_beats


class TestPhase2Director(unittest.TestCase):

    def setUp(self):
        self.script = (
            "The luxury hotel was quiet at midnight. "
            "Suddenly, security guards ran down the corridor. "
            "The heavy wooden door opened slowly."
        )
        self.beats = create_story_beats(self.script, total_duration=9.0)

    # ---------------------------------------------------------
    # 1. Golden Prompt Compiler Tests
    # ---------------------------------------------------------
    def test_prompt_compiler_golden_format(self):
        """Compiler produces exact structure with positive exclusion clause."""
        scene = {
            "shot": "wide",
            "subject": "detective in trench coat",
            "action": "inspecting glowing footprints",
            "setting": "dimly lit cobblestone alleyway",
            "lighting": "amber streetlight reflections",
            "entities": ["e1"]
        }
        entities_map = {
            "e1": "tall weathered man with silver hair and leather gloves"
        }
        shared_style = "Cinematic noir film still, 35mm grain"
        style_lock = "8k resolution, dramatic volumetric lighting"

        compiled = director.compile_prompt(scene, entities_map, shared_style, style_lock=style_lock)

        # Assert correct components in order
        self.assertIn("8k resolution, dramatic volumetric lighting", compiled)
        self.assertIn("Cinematic noir film still, 35mm grain", compiled)
        self.assertIn("wide shot of detective in trench coat inspecting glowing footprints, dimly lit cobblestone alleyway", compiled)
        # Entity look must be copied verbatim
        self.assertIn("tall weathered man with silver hair and leather gloves", compiled)
        self.assertIn("amber streetlight reflections", compiled)
        # Exclusions clause must be positive and at the end
        self.assertTrue(compiled.endswith("Vertical 9:16, subject centered, no text, no watermark."))

    def test_prompt_compiler_trimming_preserves_entity(self):
        """When prompt exceeds ~60 words, lighting and setting are trimmed, NEVER entity looks."""
        long_setting = "extremely complex multi-layered neon-lit futuristic dystopian mega-city with towering holographic advertisements and flying vehicle streams"
        long_lighting = "deep volumetric god rays cutting through toxic smog with intense magenta rim highlights and cinematic shadow falloff"
        entity_look = "cyborg courier with a chrome mechanical arm and glowing cyan optical visor"

        scene = {
            "shot": "close-up",
            "subject": "cybernetic agent",
            "action": "decrypting a confidential data shard",
            "setting": long_setting,
            "lighting": long_lighting,
            "entities": ["e1"]
        }
        entities_map = {"e1": entity_look}
        shared_style = "Cyberpunk hyper-detailed cinematic photography"

        compiled = director.compile_prompt(scene, entities_map, shared_style)

        # Entity look MUST be preserved verbatim
        self.assertIn(entity_look, compiled)
        # Must be under or around 60 words
        self.assertLessEqual(len(compiled.split()), 65)

    def test_no_forbidden_domain_rules_in_system_prompt(self):
        """The director system prompt must have NO hardcoded domain rules."""
        sys_prompt = director.DIRECTOR_SYSTEM_PROMPT.lower()
        self.assertNotIn("room 307", sys_prompt)
        self.assertNotIn("miniature", sys_prompt)
        self.assertNotIn("radar", sys_prompt)
        self.assertNotIn("black box", sys_prompt)

    # ---------------------------------------------------------
    # 2. Basic Mode Fallback
    # ---------------------------------------------------------
    def test_basic_mode_fallback(self):
        """Basic mode uses narration lines directly as subject without ontology."""
        plan = director.basic_mode_plan(self.beats)
        self.assertTrue(plan["is_basic_mode"])
        self.assertEqual(len(plan["scenes"]), len(self.beats))

        for idx, scene in enumerate(plan["scenes"]):
            # Verbatim text preserved
            self.assertEqual(scene["text"], self.beats[idx][0])
            self.assertIn("Vertical 9:16, subject centered, no text, no watermark.", scene["image_prompt"])

    # ---------------------------------------------------------
    # 3. Director Pipeline & Retries
    # ---------------------------------------------------------
    @patch("engine.director.generate_content")
    def test_director_success(self, mock_llm):
        """Director returns full structured plan with verbatim narration preserved."""
        mock_plan = {
            "style": "Cinematic thriller aesthetic",
            "entities": [{"id": "e1", "name": "guard", "look": "tall guard in black tactical uniform"}],
            "scenes": [
                {
                    "beat": 0,
                    "subject": "ornate hotel lobby",
                    "action": "sitting silent in darkness",
                    "setting": "luxury hotel interior",
                    "shot": "wide",
                    "lighting": "dim ambient moonlight",
                    "entities": [],
                    "camera_motion": "push in"
                },
                {
                    "beat": 1,
                    "subject": "two guards",
                    "action": "sprinting past closed doors",
                    "setting": "carpeted hallway",
                    "shot": "tracking medium",
                    "lighting": "flashing emergency lights",
                    "entities": ["e1"],
                    "camera_motion": "pan right"
                },
                {
                    "beat": 2,
                    "subject": "heavy wooden door",
                    "action": "creaking open to a dark room",
                    "setting": "hallway corridor",
                    "shot": "close-up",
                    "lighting": "shadowy low-key light",
                    "entities": [],
                    "camera_motion": "push in"
                }
            ]
        }
        mock_llm.return_value = (json.dumps(mock_plan), "gemini-3.8-flash")

        plan, is_basic = director.plan_scenes_with_director(
            self.script,
            self.beats,
            api_key="test-key"
        )

        self.assertFalse(is_basic)
        self.assertEqual(len(plan["scenes"]), 3)
        self.assertEqual(plan["scenes"][0]["text"], self.beats[0][0])
        self.assertEqual(plan["scenes"][1]["text"], self.beats[1][0])
        self.assertEqual(plan["scenes"][2]["text"], self.beats[2][0])

        # Entity look in scene 1
        self.assertIn("tall guard in black tactical uniform", plan["scenes"][1]["image_prompt"])

    @patch("engine.director.generate_content")
    def test_director_retry_on_invalid_output(self, mock_llm):
        """Director retries once with specific error if initial output is missing beats."""
        bad_plan = {
            "style": "Cinematic",
            "entities": [],
            "scenes": [{"beat": 0, "subject": "hotel"}]  # Missing beats 1 and 2
        }
        good_plan = {
            "style": "Cinematic",
            "entities": [],
            "scenes": [
                {"beat": 0, "subject": "hotel lobby", "shot": "wide"},
                {"beat": 1, "subject": "guards running", "shot": "medium"},
                {"beat": 2, "subject": "door opening", "shot": "close-up"}
            ]
        }
        mock_llm.side_effect = [
            (json.dumps(bad_plan), "gemini-3.8-flash"),
            (json.dumps(good_plan), "gemini-3.8-flash")
        ]

        plan, is_basic = director.plan_scenes_with_director(
            self.script,
            self.beats,
            api_key="test-key"
        )

        self.assertFalse(is_basic)
        self.assertEqual(len(plan["scenes"]), 3)
        self.assertEqual(mock_llm.call_count, 2)
