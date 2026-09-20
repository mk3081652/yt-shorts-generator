"""
engine/beats.py - The single canonical scene and pacing engine.
Preserves script words 100% verbatim. Used by both Auto and Manual modes.
"""

import re
from typing import List, Tuple

STOP_WORDS = {
    'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of', 'with',
    'by', 'from', 'up', 'about', 'into', 'over', 'after', 'beneath', 'under', 'above',
    'is', 'are', 'was', 'were', 'be', 'been', 'being', 'have', 'has', 'had', 'do',
    'does', 'did', 'will', 'would', 'shall', 'should', 'may', 'might', 'must', 'can',
    'could', 'that', 'which', 'who', 'whom', 'this', 'these', 'those', 'am', 'it',
    'its', 'they', 'them', 'their', 'we', 'us', 'our', 'you', 'your', 'he', 'him',
    'his', 'she', 'her', 'how', 'what', 'when', 'where', 'why', 'all', 'any', 'both',
    'each', 'few', 'more', 'most', 'other', 'some', 'such', 'no', 'nor', 'not', 'only',
    'own', 'same', 'so', 'than', 'too', 'very', 's', 't', 'can', 'will', 'just', 'don',
    'should', 'now'
}


def clean_words(text: str) -> List[str]:
    """Clean and tokenize words for semantic matching."""
    clean = re.sub(r'[^a-zA-Z0-9\s]', ' ', text).lower()
    return [w for w in clean.split() if w not in STOP_WORDS and len(w) > 2]


def create_story_beats(
    script_text: str,
    total_duration: float,
    min_dur: float = 2.0,
    max_dur: float = 6.0
) -> List[Tuple[str, float]]:
    """
    Intelligent narrative story-beat segmentation:
    - ONE SEGMENT = ONE CLEAR VISUAL IDEA.
    - Script is analyzed as a complete narrative.
    - Divides into narrative visual beats (sentences and major visual clauses).
    - Verbatim preservation: Original script words are 100% preserved in exact order.
    - Duration calculated from realistic Shorts speaking speed (~0.38s/word, clamped to min 1.5s).
    """
    clean_script = script_text.strip()
    if not clean_script:
        return []

    words = clean_script.split()
    total_words = len(words)
    if total_words == 0:
        return []

    # 1. Split by sentence boundaries (. ! ? or newlines)
    raw_sentences = re.split(r'([.!?]+(?:\s+|\n+|$))', clean_script)
    sentences = []
    i = 0
    while i < len(raw_sentences):
        s = raw_sentences[i].strip()
        if i + 1 < len(raw_sentences):
            delim = raw_sentences[i + 1].strip()
            if delim:
                s = s + delim
            i += 2
        else:
            i += 1
        if s:
            sentences.append(s)

    if not sentences:
        sentences = [clean_script]

    # 2. Refine sentences into narrative visual beats
    # If a sentence is long (> 16 words), check if it can be split at a major clause boundary
    beats_text: List[str] = []
    for sent in sentences:
        s_words = sent.split()
        if len(s_words) > 16:
            clause_parts = re.split(r'(?<=[,;:])\s+(?=(?:and|but|while|as|where|yet|before|after|with|when)\b)', sent, flags=re.IGNORECASE)
            if len(clause_parts) > 1 and all(len(cp.split()) >= 5 for cp in clause_parts):
                beats_text.extend(cp.strip() for cp in clause_parts if cp.strip())
            else:
                sub_parts = re.split(r'([,;:]\s+)', sent)
                merged_parts = []
                curr = ""
                for p in sub_parts:
                    curr += p
                    if len(curr.split()) >= 8:
                        merged_parts.append(curr.strip())
                        curr = ""
                if curr.strip():
                    if merged_parts:
                        merged_parts[-1] += " " + curr.strip()
                    else:
                        merged_parts.append(curr.strip())
                beats_text.extend(merged_parts)
        else:
            beats_text.append(sent)

    combined_beats = [b for b in beats_text if b.strip()]
    if not combined_beats:
        combined_beats = [clean_script]

    # 4. Strict Verbatim Preservation Check:
    # Ensure concatenation of all beats equals the exact original words
    joined_words = " ".join(combined_beats).split()
    if joined_words != words:
        combined_beats = [s for s in sentences if s.strip()]
        if " ".join(combined_beats).split() != words:
            combined_beats = [clean_script]

    # 5. Calculate realistic duration for each beat based on speaking rate
    # Short narration = shorter duration, long narration = longer duration
    beats: List[Tuple[str, float]] = []
    for b in combined_beats:
        b_word_cnt = len(b.split())
        b_ratio = b_word_cnt / max(1, total_words)
        dur = max(1.5, round(b_ratio * total_duration, 2))
        beats.append((b, dur))

    # Normalize sum of durations to match total_duration
    sum_dur = sum(d for _, d in beats)
    if sum_dur > 0:
        beats = [(t, max(1.0, round((d / sum_dur) * total_duration, 2))) for t, d in beats]

    return beats
