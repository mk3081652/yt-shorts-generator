"""
engine/llm.py - Gemini 3.8 Flash Client
Text-in / JSON-out only. Uses thinkingConfig, header-based auth, and graceful fallback.
"""

import json
import time
import urllib.request
import urllib.error
from typing import Dict, Any, List, Optional, Tuple, Union

from engine.config import (
    get_gemini_api_key,
    get_gemini_model,
    get_gemini_fallback_models,
    get_gemini_thinking_level
)


def _post(url: str, headers: Dict[str, str], body: Dict[str, Any], timeout: int = 30) -> Dict[str, Any]:
    """Helper for sending JSON POST requests, easily monkeypatched in tests."""
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def generate_content(
    prompt_or_contents: Union[str, List[Dict[str, Any]]],
    thinking_level: Optional[str] = "low",
    max_output_tokens: int = 8000,
    json_mode: bool = True,
    api_key: Optional[str] = None,
    timeout: int = 30
) -> Tuple[Optional[str], Optional[str]]:
    """
    Calls Gemini API sequentially across primary and fallback models.
    Returns (response_text, model_name) or (None, None) on total failure.

    Rules:
    - Never uses deprecated temperature, top_p, top_k, candidate_count.
    - Sends api key in x-goog-api-key header, never in the URL.
    - thinking_level: 'low', 'medium', or 'high' (never 'minimal').
    - On HTTP 400: retries once without thinkingConfig.
    - On 429/5xx: backs off, tries next model in sequence.
    - Uses _post() so tests can monkeypatch it directly.
    """
    resolved_key = api_key or get_gemini_api_key()
    if not resolved_key:
        return None, None

    if isinstance(prompt_or_contents, str):
        contents = [{"parts": [{"text": prompt_or_contents}]}]
    else:
        contents = prompt_or_contents

    # Build model sequence: primary model followed by unique fallback models
    primary_model = get_gemini_model()
    fallback_models = get_gemini_fallback_models()
    models = [primary_model]
    for m in fallback_models:
        if m not in models:
            models.append(m)

    headers = {
        "x-goog-api-key": resolved_key,
        "Content-Type": "application/json"
    }

    # Normalize thinking level (never 'minimal')
    req_thinking = thinking_level or get_gemini_thinking_level()
    safe_thinking = req_thinking if req_thinking in ("low", "medium", "high") else "low"

    for model_name in models:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent"

        # Build request body
        gen_config: Dict[str, Any] = {
            "maxOutputTokens": max_output_tokens
        }
        if json_mode:
            gen_config["responseMimeType"] = "application/json"
        if safe_thinking:
            gen_config["thinkingConfig"] = {"thinkingLevel": safe_thinking}

        body: Dict[str, Any] = {
            "contents": contents,
            "generationConfig": gen_config
        }

        # Attempt 1 (with thinkingConfig if specified)
        try:
            resp_data = _post(url, headers, body, timeout=timeout)
            text = _extract_text_from_candidate(resp_data)
            if text:
                return text, model_name
        except urllib.error.HTTPError as e:
            if e.code == 400 and safe_thinking:
                # Retry once without thinkingConfig
                try:
                    body_no_think = {
                        "contents": contents,
                        "generationConfig": {k: v for k, v in gen_config.items() if k != "thinkingConfig"}
                    }
                    resp_data = _post(url, headers, body_no_think, timeout=timeout)
                    text = _extract_text_from_candidate(resp_data)
                    if text:
                        return text, model_name
                except Exception as retry_err:
                    print(f"[LLM] Retry without thinking failed on {model_name}: {retry_err}")
            elif e.code in (429, 500, 502, 503, 504):
                print(f"[LLM] HTTP {e.code} on {model_name}, trying next fallback model...")
                time.sleep(1.0)
            else:
                print(f"[LLM] HTTP {e.code} on {model_name}: {e}")
        except Exception as e:
            print(f"[LLM] Error on {model_name}: {e}")
            time.sleep(0.5)

    return None, None


def _extract_text_from_candidate(resp_data: Dict[str, Any]) -> Optional[str]:
    """Extracts final text from Gemini response candidate structure."""
    try:
        candidates = resp_data.get("candidates", [])
        if not candidates:
            return None
        parts = candidates[0].get("content", {}).get("parts", [])
        text_parts = [p.get("text", "") for p in parts if "text" in p]
        return "\n".join(text_parts).strip() if text_parts else None
    except Exception:
        return None
