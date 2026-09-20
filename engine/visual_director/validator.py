"""
validator.py - Visual Relevance Checker & QA Validator
Part of the Visual Director system for YouTube Shorts.

Evaluates generated visual descriptions, image prompts, and search queries against:
- Spoken narration
- Physical actions described
- must_show / must_not_show constraints
- Continuity Bible (scale, character identity, environment)

Enforces strict scoring (>= 80 accepted) and provides actionable correction prompts.
"""

import os
import re
import json
import base64
import urllib.request
from typing import Dict, Any, List, Optional
from engine.visual_director.prompts import VALIDATOR_SYSTEM_PROMPT


def heuristic_validate_scene(
    narration: str,
    prompt: str,
    must_show: List[str],
    must_not_show: List[str],
    continuity_bible: Optional[Dict[str, Any]] = None,
    visual_description: str = ""
) -> Dict[str, Any]:
    """
    Fast, reliable heuristic validation without external API latency.
    Checks positive elements, negative constraints, domain scale, and vertical framing.
    """
    score = 85
    reasons = []
    missing = []
    incorrect = []
    continuity_errs = []

    # Resolve any placeholder IDs in must_show using continuity_bible
    resolved_must_show = []
    if continuity_bible and isinstance(continuity_bible, dict):
        id_map = {}
        for sec in ["characters", "locations", "objects"]:
            for item in continuity_bible.get(sec, []):
                if isinstance(item, dict) and "id" in item:
                    desc = item.get("description") or item["id"]
                    id_map[item["id"]] = desc.split(":")[0].strip() if ":" in desc else desc
        for item in must_show:
            resolved_must_show.append(id_map.get(item, item))
    else:
        resolved_must_show = list(must_show)

    p_lower = prompt.lower()
    n_lower = narration.lower()
    d_lower = visual_description.lower()
    combined_text = f"{p_lower} {d_lower}"

    def _is_negated(match_start: int, text: str) -> bool:
        start = max(0, match_start - 30)
        prefix = text[start:match_start].lower()
        return bool(re.search(r'\b(no|not|without|avoid|zero|strictly\s+no|never)\b\s*$', prefix))

    # 1. Check must_not_show violations (-30 points each)
    for forbidden in must_not_show:
        f_lower = forbidden.lower()
        for m in re.finditer(re.escape(f_lower), combined_text):
            if _is_negated(m.start(), combined_text):
                continue  # This is an explicit negative directive, not an unwanted presence
            incorrect.append(forbidden)
            reasons.append(f"Contains forbidden element: '{forbidden}'")
            score -= 30
            break

    # 2. Check must_show elements
    matched_show = 0
    for req in resolved_must_show:
        req_words = [w for w in req.lower().split() if len(w) > 3]
        if any(w in combined_text for w in req_words):
            matched_show += 1
        else:
            missing.append(req)

    if resolved_must_show:
        coverage = matched_show / len(resolved_must_show)
        if coverage < 0.5:
            score -= 25
            reasons.append(f"Missing mandatory elements: {', '.join(missing)}")
        elif coverage < 1.0:
            score -= 10
            reasons.append(f"Partially missing elements: {', '.join(missing)}")
        else:
            score += 5

    # 3. Domain Scale & Specificity Checks
    # Miniature car assembly domain
    if any(k in n_lower for k in ["miniature", "scale", "tiny", "mechanic", "suspension", "wheel", "windshield"]):
        for bad in ["full-size", "real car", "real factory", "full size"]:
            for m in re.finditer(re.escape(bad), combined_text):
                if not _is_negated(m.start(), combined_text):
                    score -= 40
                    continuity_errs.append("Full-size vehicle or person in miniature scene")
                    reasons.append("Violates miniature scale constraint")
                    break
        if not any(good in combined_text for good in ["miniature", "tiny", "1:18", "1:24", "macro"]):
            score -= 20
            continuity_errs.append("Missing explicit miniature scale indicators")
            reasons.append("Scale not clearly miniature")

    # Mystery / Room 307 domain
    if "307" in n_lower or "room 307" in n_lower:
        if "307" not in combined_text and "room" in combined_text:
            score -= 25
            missing.append("Room 307 plaque/number")
            reasons.append("Missing specific Room 307 brass plaque or number")

    # Specific objects: red suitcase, silver key
    if "suitcase" in n_lower and "red" in n_lower:
        if "red" not in combined_text or "suitcase" not in combined_text:
            score -= 25
            missing.append("red suitcase")
            reasons.append("Missing red suitcase")
    if "key" in n_lower and "silver" in n_lower:
        if "silver" not in combined_text or "key" not in combined_text:
            score -= 25
            missing.append("silver key")
            reasons.append("Missing silver key")

    # 4. Vertical 9:16 composition check
    if "9:16" in prompt or "vertical" in p_lower:
        score += 5
    else:
        score -= 10
        reasons.append("Missing vertical 9:16 framing")

    score = max(0, min(100, score))
    accepted = score >= 80

    correction = ""
    if not accepted:
        show_str = ", ".join(resolved_must_show) if resolved_must_show else narration
        no_str = f", strictly no {', '.join(must_not_show)}" if must_not_show else ""
        correction = (
            f"Photorealistic vertical 9:16 cinematic shot strictly showing {show_str} "
            f"as narrated: '{narration}'. 8k photorealistic, detailed{no_str}"
        )

    return {
        "score": score,
        "accepted": accepted,
        "reason": "; ".join(reasons) if reasons else "Passed heuristic relevance check.",
        "missing_elements": missing,
        "incorrect_elements": incorrect,
        "continuity_errors": continuity_errs,
        "correction_prompt": correction
    }


def validate_visual_with_gemini(
    narration: str,
    visual_description: str,
    image_prompt: str,
    must_show: List[str],
    must_not_show: List[str],
    continuity_bible: Optional[Dict[str, Any]] = None,
    api_key: Optional[str] = None
) -> Dict[str, Any]:
    """
    Validates a scene visual against narration using Gemini QA or fallback heuristics.
    """
    resolved_key = api_key or os.environ.get("GEMINI_API_KEY", "")
    if not resolved_key:
        return heuristic_validate_scene(
            narration=narration,
            prompt=image_prompt,
            must_show=must_show,
            must_not_show=must_not_show,
            continuity_bible=continuity_bible,
            visual_description=visual_description
        )

    body = {
        "contents": [{
            "parts": [{
                "text": (
                    f"{VALIDATOR_SYSTEM_PROMPT}\n\n"
                    f"Narration: {narration}\n"
                    f"Visual Description: {visual_description}\n"
                    f"Image Prompt: {image_prompt}\n"
                    f"Must Show: {json.dumps(must_show)}\n"
                    f"Must Not Show: {json.dumps(must_not_show)}\n"
                    f"Continuity Bible: {json.dumps(continuity_bible or {})}"
                )
            }]
        }],
        "generationConfig": {
            "responseMimeType": "application/json",
            "maxOutputTokens": 600,
            "temperature": 0.1
        }
    }

    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-flash-latest:generateContent?key={resolved_key}"
    try:
        req = urllib.request.Request(
            url,
            data=json.dumps(body).encode("utf-8"),
            headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            raw = data["candidates"][0]["content"]["parts"][0]["text"].strip()
            if raw.startswith("```json"):
                raw = raw[7:]
            if raw.startswith("```"):
                raw = raw[3:]
            if raw.endswith("```"):
                raw = raw[:-3]
            parsed = json.loads(raw.strip())
            score = int(parsed.get("score", 85))
            return {
                "score": score,
                "accepted": score >= 80,
                "reason": str(parsed.get("reason", "Accepted by Gemini QA.")),
                "missing_elements": parsed.get("missing_elements", []),
                "incorrect_elements": parsed.get("incorrect_elements", []),
                "continuity_errors": parsed.get("continuity_errors", []),
                "correction_prompt": str(parsed.get("correction_prompt", ""))
            }
    except Exception:
        # Fall back gracefully to heuristic validator
        return heuristic_validate_scene(
            narration=narration,
            prompt=image_prompt,
            must_show=must_show,
            must_not_show=must_not_show,
            continuity_bible=continuity_bible,
            visual_description=visual_description
        )


from engine.log_utils import log_tier_failure

def validate_image_with_gemini_vision(
    narration: str,
    visual_description: str,
    must_show: List[str],
    must_not_show: List[str],
    image_path: str,
    continuity_bible: Optional[Dict[str, Any]] = None,
    api_key: Optional[str] = None,
    call_stats: Optional[Dict[str, int]] = None
) -> Dict[str, Any]:
    """
    Validates an actual downloaded or generated image file against narration, constraints,
    and continuity using Gemini Vision (multimodal prompt with inline_data base64 image).
    Falls back to heuristic_validate_scene on error or missing API key.
    """
    resolved_key = api_key or os.environ.get("GEMINI_API_KEY", "")
    if not resolved_key or not image_path or not os.path.exists(image_path):
        return heuristic_validate_scene(
            narration=narration,
            prompt=visual_description or narration,
            must_show=must_show,
            must_not_show=must_not_show,
            continuity_bible=continuity_bible,
            visual_description=visual_description
        )

    try:
        with open(image_path, "rb") as f:
            img_bytes = f.read()

        if len(img_bytes) < 1000:
            return heuristic_validate_scene(
                narration=narration,
                prompt=visual_description or narration,
                must_show=must_show,
                must_not_show=must_not_show,
                continuity_bible=continuity_bible,
                visual_description=visual_description
            )

        ext = os.path.splitext(image_path)[1].lower()
        mime_type = "image/jpeg"
        if ext == ".png":
            mime_type = "image/png"
        elif ext == ".webp":
            mime_type = "image/webp"

        b64_img = base64.b64encode(img_bytes).decode("utf-8")

        prompt_text = (
            f"{VALIDATOR_SYSTEM_PROMPT}\n\n"
            f"Narration: {narration}\n"
            f"Visual Description: {visual_description}\n"
            f"Must Show: {json.dumps(must_show)}\n"
            f"Must Not Show: {json.dumps(must_not_show)}\n"
            f"Continuity Bible: {json.dumps(continuity_bible or {})}\n\n"
            "Analyze the provided image carefully against the narration and requirements above."
        )

        body = {
            "contents": [{
                "parts": [
                    {
                        "inline_data": {
                            "mime_type": mime_type,
                            "data": b64_img
                        }
                    },
                    {
                        "text": prompt_text
                    }
                ]
            }],
            "generationConfig": {
                "responseMimeType": "application/json",
                "maxOutputTokens": 600,
                "temperature": 0.1
            }
        }

        candidates = ["gemini-flash-latest", "gemini-flash-lite-latest", "gemini-pro-latest"]
        for model in candidates:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={resolved_key}"
            try:
                if call_stats is not None:
                    call_stats["gemini_calls"] = call_stats.get("gemini_calls", 0) + 1
                req = urllib.request.Request(
                    url,
                    data=json.dumps(body).encode("utf-8"),
                    headers={"Content-Type": "application/json"}
                )
                with urllib.request.urlopen(req, timeout=12) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                    raw = data["candidates"][0]["content"]["parts"][0]["text"].strip()
                    if raw.startswith("```json"):
                        raw = raw[7:]
                    if raw.startswith("```"):
                        raw = raw[3:]
                    if raw.endswith("```"):
                        raw = raw[:-3]
                    parsed = json.loads(raw.strip())
                    score = int(parsed.get("score", 85))
                    return {
                        "score": score,
                        "accepted": score >= 80,
                        "reason": str(parsed.get("reason", "Accepted by Gemini Vision QA.")),
                        "missing_elements": parsed.get("missing_elements", []),
                        "incorrect_elements": parsed.get("incorrect_elements", []),
                        "continuity_errors": parsed.get("continuity_errors", []),
                        "correction_prompt": str(parsed.get("correction_prompt", ""))
                    }
            except Exception as e:
                log_tier_failure(f"Gemini Vision QA ({model})", e)
                continue
    except Exception as e:
        log_tier_failure("Gemini Vision Validation", e)

    return heuristic_validate_scene(
        narration=narration,
        prompt=visual_description or narration,
        must_show=must_show,
        must_not_show=must_not_show,
        continuity_bible=continuity_bible,
        visual_description=visual_description
    )
