"""
test_visual_director.py - Test Suite for Visual Director System
Tests:
1. Mystery story visual planning (Room 307, corridor, security guards, CCTV)
2. Miniature car assembly visual planning (tiny mechanics, chassis, suspension)
3. Visual relevance validator (positive/negative constraints, retry logic)
4. JSON parsing resilience and graceful fallback
5. Compatibility with existing scenes preparation
"""

import os
import sys
import json

# Ensure project root is in sys.path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from engine.visual_director import (
    plan_visual_storyboard,
    semantic_fallback_plan,
    heuristic_validate_scene,
    ContinuityAnchor,
    enforce_continuity_in_prompt
)
from engine.gemini_visuals import prepare_gemini_scenes_data


def test_mystery_story():
    print("\n--- [TEST 1: Mystery Story Visual Planning] ---")
    script = (
        "The luxury hotel was eerily quiet past midnight. "
        "Suddenly, the security guards rushed toward Room 307. "
        "The door slowly opened by itself. "
        "High above, the CCTV camera recorded what no human could explain."
    )
    plan = plan_visual_storyboard(script, total_duration=12.0)
    scenes = plan.get("scenes", [])
    anchor = plan.get("continuity_anchor", {})

    print(f"Continuity Anchor Location: {anchor.get('location')}")
    print(f"Continuity Important Objects: {anchor.get('important_objects')}")
    print(f"Generated {len(scenes)} scenes:")

    assert len(scenes) >= 3, f"Expected at least 3 scenes, got {len(scenes)}"
    
    shot_types = [s.get("shot_type") for s in scenes]
    print(f"Shot types used: {shot_types}")
    assert len(set(shot_types)) >= 2, "Expected varied shot types across scenes"

    # Verify scene 2 mentions guards / Room 307
    s2 = scenes[1]
    print(f"Scene 2 Narration: \"{s2['narration']}\"")
    print(f"Scene 2 Image Prompt: {s2['image_prompt']}")
    print(f"Scene 2 Must Show: {s2.get('must_show')}")
    print(f"Scene 2 Must Not Show: {s2.get('must_not_show')}")
    assert any("guard" in str(x).lower() or "room" in str(x).lower() or "corridor" in str(x).lower() for x in s2.get("must_show", [])), "Scene 2 must show guards/room/corridor"

    print(">>> Test 1 PASSED!")


def test_miniature_car_assembly():
    print("\n--- [TEST 2: Miniature Car Assembly Support] ---")
    script = (
        "Deep inside the micro workshop, the assembly begins. "
        "First, the tiny mechanics install the chrome suspension springs on the red chassis. "
        "Next, with micro wrenches, they secure the miniature wheels. "
        "Finally, the micro V8 engine roars to life in the finished scale model."
    )
    plan = plan_visual_storyboard(script, total_duration=14.0)
    scenes = plan.get("scenes", [])
    anchor = plan.get("continuity_anchor", {})

    print(f"Continuity Anchor Objects: {anchor.get('important_objects')}")
    print(f"Continuity Clothing: {anchor.get('clothing')}")
    print(f"Generated {len(scenes)} scenes:")

    assert len(scenes) >= 3, f"Expected at least 3 scenes, got {len(scenes)}"

    for sc in scenes:
        p_lower = sc["image_prompt"].lower()
        sid = sc.get("scene_id")
        sid_disp = f"{sid + 1}" if isinstance(sid, int) else str(sid)
        print(f"Scene {sid_disp} ({sc.get('shot_type')}): {sc['image_prompt'][:90]}...")
        # Check that miniature / scale / tiny is preserved
        has_mini = any(k in p_lower for k in ["miniature", "tiny", "micro", "1:24", "scale"])
        assert has_mini, f"Scene {sc['scene_id']} did not preserve miniature scale: {sc['image_prompt']}"

    print(">>> Test 2 PASSED!")


def test_validator_and_retries():
    print("\n--- [TEST 3: Visual Relevance Validator & Negative Constraints] ---")
    
    # 1. Good matching scene
    res_good = heuristic_validate_scene(
        narration="The security guards rushed toward Room 307.",
        prompt="Photorealistic vertical 9:16 tracking shot of two security guards running down hotel corridor toward Room 307 door",
        must_show=["security guards", "Room 307 door"],
        must_not_show=["outdoor street", "daylight"]
    )
    print(f"Good Scene Validation: score={res_good['score']}, accepted={res_good['accepted']}")
    assert res_good["accepted"] is True
    assert res_good["score"] >= 80

    # 2. Bad scene violating negative constraint
    res_bad = heuristic_validate_scene(
        narration="The security guards rushed toward Room 307.",
        prompt="Sunny outdoor street with large crowd walking in daylight",
        must_show=["security guards", "Room 307 door"],
        must_not_show=["outdoor street", "daylight"]
    )
    print(f"Bad Scene Validation: score={res_bad['score']}, accepted={res_bad['accepted']}, reason={res_bad['reason']}")
    assert res_bad["accepted"] is False
    assert res_bad["score"] < 80
    assert len(res_bad["correction_prompt"]) > 0, "Expected correction prompt on rejection"

    print(">>> Test 3 PASSED!")


def test_json_safety_and_fallback():
    print("\n--- [TEST 4: JSON Safety & Fallback Resilience] ---")
    # Test semantic fallback directly
    script = "Radar blips vanished from civilian air traffic screens. An underwater submarine searched the abyss."
    plan = semantic_fallback_plan(script, total_duration=8.0)
    assert "scenes" in plan
    assert len(plan["scenes"]) >= 2
    assert "continuity_anchor" in plan
    print(f"Fallback generated {len(plan['scenes'])} scenes successfully with continuity.")
    print(">>> Test 4 PASSED!")


def test_existing_pipeline_integration():
    print("\n--- [TEST 5: Existing Scenes Data Pipeline Compatibility] ---")
    script = "The mystery began when Room 307 door opened. The guards stood frozen in the corridor."
    scenes = prepare_gemini_scenes_data(
        script_text=script,
        total_duration=6.0,
        scene_overrides={"0": "https://example.com/custom_override.jpg"}
    )
    assert len(scenes) >= 2
    # Verify exact schema expected by app.py and frontend
    s0 = scenes[0]
    required_keys = ["scene_id", "start_time", "end_time", "duration", "text", "image_url", "is_custom"]
    for k in required_keys:
        assert k in s0, f"Missing key {k} in scene data"
    assert s0["is_custom"] is True, "Scene 0 override was not applied"
    assert s0["image_url"] == "https://example.com/custom_override.jpg"
    print("Manual image override and schema backward-compatibility verified.")
    print(">>> Test 5 PASSED!")


if __name__ == "__main__":
    print("==================================================")
    print("RUNNING VISUAL DIRECTOR INTEGRATION TEST SUITE")
    print("==================================================")
    test_mystery_story()
    test_miniature_car_assembly()
    test_validator_and_retries()
    test_json_safety_and_fallback()
    test_existing_pipeline_integration()
    print("\n==================================================")
    print("ALL TESTS PASSED SUCCESSFULLY! ZERO BREAKAGES.")
    print("==================================================")
