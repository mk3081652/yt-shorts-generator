"""
generator.py - Visual Generation, Validation & Regeneration Pipeline
Part of the Visual Director module for YouTube Shorts.

Generates vertical 9:16 scene images using Cloudflare FLUX.1-schnell,
validates relevance, and manages regeneration.
"""

import os
import re
import json
import time
import hashlib
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, Any, List, Optional, Set, Tuple

from engine.visual_director.validator import (
    heuristic_validate_scene,
    validate_image_with_gemini_vision
)
from engine.flux import generate_flux_image
from engine.config import get_gemini_api_key
from engine.log_utils import log_tier_failure

# Backward compatibility alias
generate_cloudflare_flux_image = generate_flux_image


def single_visual_attempt(
    prompt: str,
    search_query: str = "",
    output_path: str = "",
    scene_text: str = "",
    used_urls: Optional[Set[str]] = None,
    api_key: Optional[str] = None,
    generation_mode: str = "flux"
) -> Tuple[bool, str]:
    """
    Executes a single visual acquisition attempt using FLUX.
    Zero stock/archive photo fallback tiers.
    """
    return generate_flux_image(prompt=prompt, output_path=output_path)


def generate_and_validate_scene(
    scene: Dict[str, Any],
    output_dir: str,
    continuity_bible: Optional[Dict[str, Any]] = None,
    api_key: Optional[str] = None,
    used_urls: Optional[Set[str]] = None,
    max_retries: int = 2,
    generation_mode: str = "flux",
    call_stats: Optional[Dict[str, int]] = None
) -> Dict[str, Any]:
    """
    Executes visual generation, validation, and regeneration loop for a single scene:
    - Checks if manual override exists (source: 'manual'); if so, preserves it completely.
    - Attempt 1: generate with scene['image_prompt'] using FLUX.
    - Validate against narration, must_show, must_not_show.
    - If score < 80: regenerate using correction_prompt (up to max_retries).
    - Best-Image Selection: picks the attempt with highest validation score.
    """
    scene_id = scene.get("scene_id", "scene_01")
    narration = scene.get("narration", "")
    vis_desc = scene.get("visual_description", "")
    must_show = scene.get("must_show", [])
    must_not_show = scene.get("must_not_show", [])
    sq = scene.get("search_query", "")

    # If already manual, do not touch
    if scene.get("source") == "manual" or scene.get("is_custom"):
        return scene

    attempts: List[Dict[str, Any]] = []
    current_prompt = scene.get("image_prompt", "")

    for attempt_idx in range(1 + max_retries):
        p_hash = hashlib.md5(f"{scene_id}_{attempt_idx}_{current_prompt}".encode('utf-8')).hexdigest()[:8]
        attempt_filename = f"{scene_id}_att{attempt_idx}_{p_hash}.jpg"
        attempt_path = os.path.join(output_dir, attempt_filename)

        ok, tier = single_visual_attempt(
            prompt=current_prompt,
            search_query=sq,
            output_path=attempt_path,
            scene_text=narration,
            used_urls=used_urls,
            api_key=api_key,
            generation_mode=generation_mode
        )

        if not ok:
            val_res = {
                "score": 0,
                "accepted": False,
                "reason": f"FLUX generation failed ({tier})",
                "correction_prompt": ""
            }
        else:
            resolved_key = api_key or get_gemini_api_key()
            if resolved_key and os.path.exists(attempt_path) and os.path.getsize(attempt_path) > 1000:
                val_res = validate_image_with_gemini_vision(
                    narration=narration,
                    visual_description=vis_desc,
                    must_show=must_show,
                    must_not_show=must_not_show,
                    image_path=attempt_path,
                    continuity_bible=continuity_bible,
                    api_key=resolved_key,
                    call_stats=call_stats
                )
            else:
                val_res = heuristic_validate_scene(
                    narration=narration,
                    prompt=current_prompt,
                    must_show=must_show,
                    must_not_show=must_not_show,
                    continuity_bible=continuity_bible,
                    visual_description=vis_desc
                )

        score = val_res.get("score", 0)
        attempts.append({
            "attempt": attempt_idx + 1,
            "path": attempt_path,
            "filename": attempt_filename,
            "prompt": current_prompt,
            "score": score,
            "accepted": val_res.get("accepted", False),
            "source_tier": tier if ok else "flux_failed",
            "fail_reason": tier if not ok else "",
            "val_res": val_res
        })

        if val_res.get("accepted", False):
            print(f"[{scene_id}] Attempt {attempt_idx+1} ACCEPTED (Score: {score}/100, Tier: {tier})")
            break
        else:
            print(f"[{scene_id}] Attempt {attempt_idx+1} REJECTED (Score: {score}/100, Tier: {tier}). Reason: {val_res.get('reason', '')}")
            if val_res.get("correction_prompt"):
                current_prompt = val_res["correction_prompt"]

    best_attempt = max(attempts, key=lambda a: a["score"])
    scene_copy = dict(scene)

    if best_attempt["score"] > 0 and os.path.exists(best_attempt["path"]):
        scene_copy["image_url"] = f"/outputs/ai_previews/{best_attempt['filename']}"
        scene_copy["image_path"] = best_attempt["path"]
        scene_copy["validation_score"] = best_attempt["score"]
        scene_copy["accepted"] = best_attempt["accepted"]
        scene_copy["prompt"] = best_attempt["prompt"]
        scene_copy["source"] = "generated"
        scene_copy["source_tier"] = best_attempt.get("source_tier", "flux")
        scene_copy["needs_manual"] = not best_attempt["accepted"]
        scene_copy["fail_reason"] = ""
    else:
        scene_copy["image_url"] = ""
        scene_copy["image_path"] = ""
        scene_copy["validation_score"] = 0
        scene_copy["accepted"] = False
        scene_copy["prompt"] = current_prompt
        scene_copy["source"] = "generated"
        scene_copy["source_tier"] = "flux_failed"
        scene_copy["needs_manual"] = True
        scene_copy["fail_reason"] = best_attempt.get("fail_reason") or "flux_failed"

    scene_copy["is_custom"] = False
    return scene_copy


def generate_validated_scenes(
    planned_scenes: List[Dict[str, Any]],
    output_dir: str = "outputs/ai_previews",
    continuity_bible: Optional[Dict[str, Any]] = None,
    scene_overrides: Optional[Dict[str, str]] = None,
    api_key: Optional[str] = None,
    generation_mode: Optional[str] = None,
    call_stats: Optional[Dict[str, int]] = None
) -> List[Dict[str, Any]]:
    """
    Coordinates visual generation and validation for all planned scenes in parallel.
    Preserves manual overrides and enforces best-image selection.
    """
    os.makedirs(output_dir, exist_ok=True)
    if scene_overrides is None:
        scene_overrides = {}

    used_urls: Set[str] = set()
    scenes_to_process = []

    for idx, sc in enumerate(planned_scenes):
        sc_id_str = str(idx)
        override_val = scene_overrides.get(sc_id_str) or scene_overrides.get(idx) or scene_overrides.get(sc.get("scene_id"))

        if override_val:
            sc_copy = dict(sc)
            sc_copy["image_url"] = override_val
            sc_copy["image_title"] = os.path.basename(override_val)
            sc_copy["is_custom"] = True
            sc_copy["source"] = "manual"
            sc_copy["source_tier"] = "manual_upload"
            sc_copy["validation_score"] = 100
            sc_copy["needs_manual"] = False
            scenes_to_process.append((sc_copy, True))
        else:
            scenes_to_process.append((sc, False))

    def _worker(item):
        _sc, _is_override = item
        if _is_override:
            return _sc
        try:
            return generate_and_validate_scene(
                scene=_sc,
                output_dir=output_dir,
                continuity_bible=continuity_bible,
                api_key=api_key,
                used_urls=used_urls,
                generation_mode="flux",
                call_stats=call_stats
            )
        except Exception as err:
            log_tier_failure("Generator Worker", err, context=_sc.get('scene_id'))
            return _sc

    with ThreadPoolExecutor(max_workers=2) as executor:
        final_scenes = list(executor.map(_worker, scenes_to_process))

    return final_scenes
