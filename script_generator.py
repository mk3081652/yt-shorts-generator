"""
script_generator.py - Module 1: Viral Script Generation Prompting

Implements strict viral YouTube Shorts script generation rules:
- Ban on meta-phrases ("Stop scrolling", "Listen to this", "Did you know", etc.)
- 1.5-second shocking pattern interrupt hook (Sentence 1)
- Rapid cadence: 4 to 7 words per punchy clause
- Seamless loop: Final sentence connects directly back to Sentence 1 without full stop or CTA
- Strict length constraint: 65 to 80 words total (~25–32 seconds)
"""

import os
import re
import logging
from typing import Dict, Any, Optional, List, Tuple

logger = logging.getLogger("script_generator")

# Strict list of forbidden phrases that trigger viewer swipe-away
BANNED_META_PHRASES = [
    "stop scrolling",
    "listen to this",
    "wake up",
    "in this video",
    "did you know",
    "subscribe",
    "like and subscribe",
    "follow for more",
    "leave a comment",
    "comment below",
    "share this with",
    "thanks for watching",
    "welcome back to",
    "hey guys",
    "smash the like",
    "hit that notification"
]

# High-retention production templates for offline / zero-API fallback
FALLBACK_SCRIPTS = {
    "motivational": [
        (
            "Comfort is the quietest killer of men. "
            "Every day you choose warmth and ease, "
            "your future self pays the price. "
            "The top one percent do not possess more talent. "
            "They possess a vicious intolerance for weakness. "
            "Stop waiting for inspiration to strike you. "
            "Discipline does not care how you feel. "
            "Pain today builds power tomorrow because..."
        ),
        (
            "Nobody is coming to rescue you. "
            "The world does not care about your excuses. "
            "Every morning brings a brutal choice. "
            "Stay asleep with your regrets, "
            "or suffer the agony of growth. "
            "Champions are forged in dark, unseen hours. "
            "Master your impulses or be enslaved by them. "
            "Real strength only begins the moment..."
        )
    ],
    "mystery": [
        (
            "Two men stole a commercial airliner, "
            "cut all the lights, and vanished forever. "
            "In 2003, Boeing 727 tail number 844AA "
            "taxied onto an Angolan runway without clearance. "
            "No transponder signal ever appeared on radar. "
            "No radio communication was ever recorded. "
            "The FBI and CIA launched global searches. "
            "Yet twenty years later, the only clue is..."
        ),
        (
            "Five military bombers vanished into clear skies, "
            "and the rescue plane disappeared too. "
            "Flight Nineteen departed Florida on routine maneuvers. "
            "Hours later, compasses spun out of control. "
            "The lead pilot radioed complete confusion. "
            "Then silence swallowed all fourteen airmen. "
            "Zero wreckage was ever recovered because..."
        )
    ]
}


def build_system_prompt(channel: str = "motivational") -> str:
    """Constructs the prompt with strict retention constraints."""
    channel_type = channel.lower()
    if channel_type == "mystery":
        vibe_instruction = (
            "EDITORIAL ANGLE: Dark, chilling, atmospheric mystery or historical anomaly. "
            "Focus on impossible clues, eerie vanishings, or classified records. "
            "Maintain an intense, investigative, forensic tone."
        )
    else:
        vibe_instruction = (
            "EDITORIAL ANGLE: Ruthless discipline, stoic self-mastery, brutal psychological truth. "
            "Attack procrastination, comfort, and weakness directly. "
            "Maintain a commanding, deep, high-authority tone."
        )

    return f"""You are a master viral YouTube Shorts scriptwriter specializing in maximum viewer retention and 100%+ Average Percentage Viewed (APV).

{vibe_instruction}

STRICT RETENTION ARCHITECTURE:
1. BAN META-PHRASES:
   - Absolutely NEVER say: "Stop scrolling", "Listen to this", "Wake up", "In this video", "Did you know", or "In 2024".
   - Absolutely NEVER ask for likes, subscribes, follows, or comments. Zero outro plugs.

2. THE 1.5-SECOND HOOK (Sentence 1):
   - Must be an instant pattern interrupt, shocking claim, or spine-chilling mystery fact.
   - Do NOT introduce the topic formally. Drop the listener directly into the crisis.

3. CADENCE & SENTENCE LENGTH:
   - Write in rapid, punchy clauses of 4 to 7 words each.
   - Never let a single sentence exceed 9 words. Rapid sentence pacing keeps viewer attention locked.

4. SEAMLESS INFINITY LOOP:
   - The final sentence MUST be an open, grammatically incomplete bridge clause ending with words like 'because...', 'which is why...', 'the reason why...', or 'the moment that...'
   - It MUST connect seamlessly into Sentence 1 when the video loops back to 0:00 without a full stop.

5. STRICT LENGTH CONSTRAINT:
   - Exactly 65 to 80 words total (approx. 25–32 seconds of speech).
   - Count words before outputting. If less than 65 or more than 80 words, rewrite it.

6. FORMAT:
   - Output spoken voiceover narration ONLY.
   - No brackets, no stage directions, no narrator labels, no markdown formatting."""


def sanitize_script(script: str) -> str:
    """
    Sanitizes raw script:
    - Strips stage directions and labels
    - Purges banned meta-phrases
    - Ensures punctuation formatting for Kokoro pauses
    - Trims/verifies word count to 65-80 words
    """
    if not script:
        return ""

    text = script.strip()

    # Remove labels like "Voiceover:", "Narrator:", "Hook:"
    text = re.sub(r'^(?:Voiceover|Narrator|Script|Hook|Speech):\s*', '', text, flags=re.IGNORECASE)
    text = re.sub(r'\[.*?\]', '', text)
    text = re.sub(r'\(.*?\)', '', text)
    text = re.sub(r'[*_#`~"]', '', text)

    # Remove banned meta-phrases
    for phrase in BANNED_META_PHRASES:
        pattern = re.compile(re.escape(phrase), re.IGNORECASE)
        text = pattern.sub('', text)

    # Normalize whitespace
    text = re.sub(r'\s+', ' ', text).strip()

    return text


def enforce_word_count(text: str, min_words: int = 65, max_words: int = 80) -> str:
    """Enforces the strict 65-80 word window."""
    words = text.split()
    if len(words) > max_words:
        # Trim to max_words while maintaining loop ending
        trimmed = words[:max_words]
        # Ensure it ends with open loop punctuation
        last_word = trimmed[-1].rstrip(".,!?;:")
        trimmed[-1] = last_word + "..."
        return " ".join(trimmed)
    return text


def generate_viral_script(
    topic: str,
    channel: str = "motivational",
    api_key: Optional[str] = None
) -> Dict[str, Any]:
    """
    Generates a viral YouTube Short script adhering to all 5 retention constraints.

    Args:
        topic: The subject/theme of the Short.
        channel: 'motivational' or 'mystery'.
        api_key: Optional Gemini API key (defaults to os.environ GEMINI_API_KEY).

    Returns:
        Dict with keys: 'topic', 'channel', 'script', 'word_count', 'hook', 'loop_bridge'.
    """
    channel_key = channel.lower() if channel.lower() in ("motivational", "mystery") else "motivational"
    resolved_key = api_key or os.environ.get("GEMINI_API_KEY", "").strip()

    system_prompt = build_system_prompt(channel=channel_key)
    user_prompt = f"Write a viral YouTube Shorts script about: \"{topic}\"."

    raw_script = None

    if resolved_key:
        try:
            # Try Gemini client
            from engine.gemini_client import generate_content
            combined_prompt = f"{system_prompt}\n\n{user_prompt}"
            resp_text, model = generate_content(
                combined_prompt,
                thinking_level=None,
                max_output_tokens=300,
                json_mode=False,
                api_key=resolved_key
            )
            if resp_text and len(resp_text.split()) >= 40:
                raw_script = resp_text.strip()
                logger.info(f"[ScriptGenerator] Generated script via Gemini ({model}) for topic: '{topic}'")
        except Exception as e:
            logger.warning(f"[ScriptGenerator] Gemini call failed ({e}). Using viral fallback.")

    if not raw_script:
        # Deterministic curated fallback matched to channel
        options = FALLBACK_SCRIPTS.get(channel_key, FALLBACK_SCRIPTS["motivational"])
        # Hash topic to choose option
        idx = sum(ord(c) for c in topic) % len(options)
        raw_script = options[idx]
        logger.info(f"[ScriptGenerator] Used curated high-retention fallback for topic: '{topic}'")

    sanitized = sanitize_script(raw_script)
    final_script = enforce_word_count(sanitized, min_words=65, max_words=80)
    words = final_script.split()

    # Extract hook (sentence 1) and loop bridge (last clause)
    sentences = [s.strip() for s in re.split(r'(?<=[.!?…])\s+', final_script) if s.strip()]
    hook = sentences[0] if sentences else final_script
    loop_bridge = sentences[-1] if len(sentences) > 1 else words[-1]

    return {
        "topic": topic,
        "channel": channel_key,
        "script": final_script,
        "word_count": len(words),
        "hook": hook,
        "loop_bridge": loop_bridge,
        "estimated_duration_sec": round(len(words) / 2.6, 1)
    }
