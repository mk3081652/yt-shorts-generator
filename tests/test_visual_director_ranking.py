"""
tests/test_visual_director_ranking.py - Comprehensive tests for Visual Director,
Multi-Query Search, Hard Filtering, AI Visual Ranking, and Quality Gate Fallback.
"""

import pytest
from engine.director import basic_mode_plan
from engine.stock_video import (
    extract_broll_keywords,
    clean_query_phrase,
    extract_queries_from_gemini_prompt,
    filter_candidates,
    rank_candidates_deterministically,
    fetch_broll_for_scene
)
from engine.project import Scene, Project


def test_director_extended_schema():
    """Verifies that the Director storyboard includes all new visual intelligence fields."""
    beats = [
        ("The pilot suddenly noticed something strange on the radar.", 3.5),
        ("Then the airspeed sensors failed completely.", 3.0)
    ]
    plan = basic_mode_plan(beats)
    assert "scenes" in plan
    assert len(plan["scenes"]) == 2

    s0 = plan["scenes"][0]
    assert s0["visual_type"] in ("literal", "conceptual", "historical", "abstract", "data", "location", "person", "object")
    assert s0["visual_priority"] in ("high", "medium", "low")
    assert s0["visual_strategy"] in ("pexels", "flux", "hold")
    assert isinstance(s0["must_show"], list)
    assert isinstance(s0["should_avoid"], list)
    assert isinstance(s0["search_queries"], list)
    assert len(s0["search_queries"]) >= 1
    assert "continuity_group" in s0
    assert "shot_scale" in s0
    assert "motion_intensity" in s0


def test_extract_broll_keywords_hierarchy():
    """Verifies that search query generation strictly prioritizes Director data."""
    queries = extract_broll_keywords(
        scene_text="The pilot checked the flight data recorder.",
        image_prompt="Cinematic 9:16. Close-up shot of flight recorder in cockpit. Vertical 9:16.",
        subject="pilot",
        action="inspecting flight recorder",
        setting="airplane cockpit night",
        must_show=["flight recorder", "cockpit"],
        should_avoid=["generic airplane exterior"],
        search_queries=["flight data recorder cockpit", "pilot inspecting instruments"]
    )

    # First queries must come from Director's search_queries
    assert queries[0] == "flight data recorder cockpit"
    assert queries[1] == "pilot inspecting instruments"
    # must_show combinations should follow
    assert any("flight recorder" in q for q in queries)
    # Generic topic should not override
    assert len(queries) >= 3


def test_filter_candidates():
    """Verifies hard filtering drops corrupt, short (<1.5s), and low-res clips."""
    raw = [
        # Good portrait clip
        {"id": "1", "duration": 5.0, "width": 1080, "height": 1920, "video_url": "https://pexels.com/v1.mp4"},
        # Corrupt URL (should be dropped)
        {"id": "2", "duration": 4.0, "width": 1080, "height": 1920, "video_url": ""},
        # Too short (<1.5s) (should be dropped)
        {"id": "3", "duration": 1.1, "width": 1080, "height": 1920, "video_url": "https://pexels.com/v3.mp4"},
        # Low resolution (<480p) (should be dropped)
        {"id": "4", "duration": 4.0, "width": 320, "height": 240, "video_url": "https://pexels.com/v4.mp4"},
        # Good high-res landscape clip (>=1280x720, can center-crop to 9:16)
        {"id": "5", "duration": 6.0, "width": 1920, "height": 1080, "video_url": "https://pexels.com/v5.mp4"},
    ]

    filtered = filter_candidates(raw)
    passed_ids = [c["id"] for c in filtered]

    assert "1" in passed_ids
    assert "5" in passed_ids
    assert "2" not in passed_ids
    assert "3" not in passed_ids
    assert "4" not in passed_ids


def test_deterministic_ranking_must_show_and_penalty():
    """Verifies deterministic scoring rewards must_show and penalizes should_avoid."""
    candidates = [
        {"id": "c1", "query": "generic airplane flying daylight clouds", "orientation": "landscape", "duration": 4.0, "width": 1920, "height": 1080},
        {"id": "c2", "query": "pilot radar cockpit night", "orientation": "portrait", "duration": 5.0, "width": 1080, "height": 1920}
    ]

    scene_ctx = {
        "scene_text": "The pilot suddenly noticed something strange on the radar.",
        "subject": "pilot",
        "action": "checking radar",
        "must_show": ["pilot", "radar", "cockpit"],
        "should_avoid": ["generic airplane flying", "daylight clouds"],
        "duration": 3.5
    }

    best_cand, score, reason = rank_candidates_deterministically(candidates, scene_ctx)
    assert best_cand is not None
    assert best_cand["id"] == "c2"
    assert score > 70
    assert "radar" in reason or "cockpit" in reason or "Keyword" in reason


def test_scene_serialization_backward_compatibility():
    """Verifies Scene serialization and deserialization with extended fields and legacy dicts."""
    sc = Scene(
        id="sc123",
        text="Testing scene text",
        visual_type="conceptual",
        visual_priority="high",
        must_show=["stock charts"],
        should_avoid=["happy people"],
        search_queries=["stock market charts falling"],
        visual_strategy="pexels",
        continuity_group="trading_floor",
        shot_scale="medium",
        motion_intensity="high",
        mood="urgent",
        selected_query="stock market charts falling",
        selected_reason="Clear chart graphics",
        candidate_count=5,
        ai_ranking_score=88
    )

    d = sc.to_dict()
    assert d["visual_type"] == "conceptual"
    assert d["visual_priority"] == "high"
    assert d["must_show"] == ["stock charts"]
    assert d["ai_ranking_score"] == 88

    # Deserialize back
    restored = Scene.from_dict(d)
    assert restored.visual_type == "conceptual"
    assert restored.visual_priority == "high"
    assert restored.must_show == ["stock charts"]
    assert restored.selected_query == "stock market charts falling"
    assert restored.ai_ranking_score == 88

    # Test legacy dict without new fields loads with clean defaults
    legacy_data = {
        "id": "leg1",
        "text": "Old scene without new fields",
        "duration": 4.0
    }
    legacy_sc = Scene.from_dict(legacy_data)
    assert legacy_sc.visual_type == "literal"
    assert legacy_sc.visual_priority == "medium"
    assert legacy_sc.visual_strategy == "pexels"
    assert legacy_sc.must_show == []
    assert legacy_sc.search_queries == []
