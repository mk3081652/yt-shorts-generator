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
    max_dur: float = 5.5
) -> List[Tuple[str, float]]:
    """
    Intelligent narrative story-beat segmentation:
    - ONE SEGMENT = ONE CLEAR VISUAL IDEA (~3.0s to 5.5s).
    - Splits on:
      1. Explicit delimiters '|||'
      2. Line breaks (\n+)
      3. Sentence boundaries (. ! ?)
      4. Colons followed by space or newline
      5. Clause boundaries for long sentences (> 14 words)
    - 100% Verbatim script preservation: Concatenation of all beats equals the exact original words.
    - Durations proportional to word count, clamped to min 1.5s.
    """
    clean_script = script_text.strip()
    if not clean_script:
        return []

    words = clean_script.split()
    total_words = len(words)
    if total_words == 0:
        return []

    # 1. If explicit '|||' delimiters exist, split on them directly
    if '|||' in clean_script:
        raw_parts = [p.strip() for p in clean_script.split('|||') if p.strip()]
    else:
        # 2. Split line by line, then sentence by sentence, then clause by clause
        raw_parts = []
        for line in clean_script.splitlines():
            line_clean = line.strip()
            if not line_clean:
                continue

            # Split line on sentence terminators (. ! ?) or colon followed by space
            # Pattern matches punctuation and captures it with trailing whitespace
            sent_chunks = re.split(r'([.!?]+(?:\s+|$)|:(?:\s+|$))', line_clean)
            line_sents = []
            i = 0
            while i < len(sent_chunks):
                s = sent_chunks[i].strip()
                if i + 1 < len(sent_chunks):
                    delim = sent_chunks[i + 1].strip()
                    if delim:
                        s = s + delim
                    i += 2
                else:
                    i += 1
                if s:
                    line_sents.append(s)

            if not line_sents:
                line_sents = [line_clean]

            # Refine any long sentence (> 14 words) into visual clauses
            for sent in line_sents:
                s_words = sent.split()
                if len(s_words) > 14:
                    # Split at major conjunction clauses
                    clause_parts = re.split(
                        r'(?<=[,;])\s+(?=(?:and|but|while|as|where|yet|before|after|with|when|so|because)\b)',
                        sent,
                        flags=re.IGNORECASE
                    )
                    if len(clause_parts) > 1 and all(len(cp.split()) >= 4 for cp in clause_parts):
                        raw_parts.extend(cp.strip() for cp in clause_parts if cp.strip())
                    else:
                        # Split at comma / semicolon
                        sent_words = sent.split()
                        buf_words = []
                        for w in sent_words:
                            buf_words.append(w)
                            if len(buf_words) >= 7 and w.endswith((',', ';')):
                                raw_parts.append(" ".join(buf_words))
                                buf_words = []
                        if buf_words:
                            if raw_parts and len(buf_words) < 4:
                                raw_parts[-1] += " " + " ".join(buf_words)
                            else:
                                raw_parts.append(" ".join(buf_words))
                else:
                    raw_parts.append(sent)

    combined_beats = [b for b in raw_parts if b.strip()]
    if not combined_beats:
        combined_beats = [clean_script]

    # Combine adjacent tiny beats (< 4 words) if combined <= 14 words
    merged_beats: List[str] = []
    curr_beat = ""
    for b in combined_beats:
        b_clean = b.strip()
        if not b_clean:
            continue
        if not curr_beat:
            curr_beat = b_clean
        else:
            curr_len = len(curr_beat.split())
            b_len = len(b_clean.split())
            if curr_len < 4 and (curr_len + b_len) <= 14:
                curr_beat = f"{curr_beat} {b_clean}"
            elif b_len < 3 and (curr_len + b_len) <= 14:
                curr_beat = f"{curr_beat} {b_clean}"
            else:
                merged_beats.append(curr_beat)
                curr_beat = b_clean
    if curr_beat:
        merged_beats.append(curr_beat)

    if not merged_beats:
        merged_beats = [clean_script]

    # 4. Strict Verbatim Check
    joined_words = " ".join(merged_beats).split()
    if joined_words != words:
        # Guaranteed verbatim fallback: chunk words into 8-12 word segments
        merged_beats = []
        step = 10
        for idx in range(0, total_words, step):
            merged_beats.append(" ".join(words[idx:idx + step]))

    # 5. Duration assignment
    beats: List[Tuple[str, float]] = []
    for b in merged_beats:
        b_cnt = len(b.split())
        ratio = b_cnt / max(1, total_words)
        dur = max(min_dur, round(ratio * total_duration, 2))
        beats.append((b, dur))

    sum_dur = sum(d for _, d in beats)
    if sum_dur > 0:
        beats = [(t, max(1.5, round((d / sum_dur) * total_duration, 2))) for t, d in beats]

    return beats
