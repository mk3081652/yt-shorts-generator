"""
validator.py - Visual Relevance Checker & Validator
Part of the isolated Visual Director module for YouTube Shorts.
Evaluates visual descriptions against narration, must_show, must_not_show, and continuity.
Enforces a strict maximum of 2 retry attempts to prevent infinite loops.
"""

import json
import urllib.request
import time
from typing import Dict, Any, List, Optional
from engine.visual_director.prompts import VALIDATOR_SYSTEM_PROMPT


def heuristic_validate_scene(
    narration: str,
    prompt: str,
    must_show: List[str],
    must_not_show: List[str]
) -> Dict[str, Any]:
    """
    Fast, reliable heuristic validation without external API latency.
    Checks positive keywords, negative constraints, and prompt quality.
    """
    score = 85
    reasons = []
    p_lower = prompt.lower()
    n_lower = narration.lower()

    # Check must_not_show violations (-30 points each)
    violations = []
    for forbidden in must_not_show:
        if forbidden.lower() in p_lower:
            violations.append(forbidden)
            score -= 30

    if violations:
        reasons.append(f"Contains forbidden element(s): {', '.join(violations)}")

    # Check must_show coverage (+5 if present, -15 if completely missing key subject)
    missing_must_show = []
    for req in must_show:
        req_words = req.lower().split()
        if not any(w in p_lower for w in req_words if len(w) > 3):
            missing_must_show.append(req)

    if missing_must_show and len(missing_must_show) == len(must_show):
        score -= 20
        reasons.append(f"Missing core subject: {', '.join(missing_must_show)}")
    else:
        score += 5

    # Check vertical 9:16 directive
    if "9:16" in prompt or "vertical" in p_lower:
        score += 5
    else:
        score -= 10
        reasons.append("Missing vertical 9:16 framing")

    score = max(0, min(100, score))
    accepted = score >= 80

    correction = ""
    if not accepted:
        correction = f"Vertical 9:16 cinematic shot strictly showing {', '.join(must_show)} while narration states '{narration}', photorealistic 8k, no {', '.join(must_not_show)}"

    return {
        "score": score,
        "accepted": accepted,
        "reason": "; ".join(reasons) if reasons else "Passed heuristic relevance check.",
        "correction_prompt": correction
    }


def validate_visual_with_gemini(
    narration: str,
    visual_description: str,
    image_prompt: str,
    must_show: List[str],
    must_not_show: List[str],
    continuity_anchor: Dict[str, Any],
    api_key: Optional[str] = None
) -> Dict[str, Any]:
    """
    Validates a scene visual against the narration using Gemini QA or fallback heuristics.
    """
    if not api_key:
        return heuristic_validate_scene(narration, image_prompt, must_show, must_not_show)

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
                    f"Continuity Anchor: {json.dumps(continuity_anchor)}"
                )
            }]
        }],
        "generationConfig": {
            "responseMimeType": "application/json",
            "maxOutputTokens": 600,
            "temperature": 0.1
        }
    }

    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-flash-latest:generateContent?key={api_key}"
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
            return {
                "score": int(parsed.get("score", 85)),
                "accepted": bool(parsed.get("accepted", True)),
                "reason": str(parsed.get("reason", "Accepted by Gemini QA.")),
                "correction_prompt": str(parsed.get("correction_prompt", ""))
            }
    except Exception:
        # Fall back gracefully to fast heuristic validator
        return heuristic_validate_scene(narration, image_prompt, must_show, must_not_show)
