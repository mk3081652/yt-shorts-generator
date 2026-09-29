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
    max_dur: float = 5.5,
    rapid_mode: bool = False
) -> List[Tuple[str, float]]:
    """
    Intelligent narrative story-beat segmentation:
    - ONE SEGMENT = ONE CLEAR VISUAL IDEA (~3.0s to 5.5s, or ~2.0s to 3.2s in rapid_mode).
    - Splits on:
      1. Explicit delimiters '|||'
      2. Line breaks (\\n+)
      3. Sentence boundaries (. ! ?)
      4. Colons followed by space or newline
      5. Clause boundaries for long sentences (> 14 words, or > 7 words in rapid_mode)
    - 100% Verbatim script preservation: Concatenation of all beats equals the exact original words.
    - Durations proportional to word count, clamped to min_dur.
    """
    clean_script = script_text.strip()
    if not clean_script:
        return []

    words = clean_script.split()
    total_words = len(words)
    if total_words == 0:
        return []

    word_threshold = 7 if rapid_mode else 22
    max_merged_len = 8 if rapid_mode else 24
    effective_min_dur = 1.8 if rapid_mode else min_dur

    # 1. If explicit '|||' delimiters exist, split on them directly
    if '|||' in clean_script:
        raw_parts = [p.strip() for p in clean_script.split('|||') if p.strip()]
    else:
        # 2. Split line by line, then sentence by sentence, preserving meaningful grammar
        raw_parts = []
        for line in clean_script.splitlines():
            line_clean = line.strip()
            if not line_clean:
                continue

            # Protect abbreviations from false sentence splits:
            # e.g. "a.m.", "p.m.", "Mr.", "Dr.", "U.S.", "vs.", "etc."
            abbrev_lookbehind = (
                r'(?<!\ba\.m)(?<!\bp\.m)(?<!\bMr)(?<!\bMrs)(?<!\bMs)(?<!\bDr)'
                r'(?<!\bProf)(?<!\bGen)(?<!\bCol)(?<!\bLt)(?<!\bSt)(?<!\bvs)'
                r'(?<!\betc)(?<!\be\.g)(?<!\bi\.e)(?<!\bU\.S)(?<!\b[A-Z])'
            )
            # Split only on actual sentence terminators (. ! ?)
            sent_chunks = re.split(abbrev_lookbehind + r'([.!?]+(?:\s+|$))', line_clean)
            line_sents = []
            i = 0
            while i < len(sent_chunks):
                s = sent_chunks[i].strip()
                if i + 1 < len(sent_chunks):
                    delim = sent_chunks[i + 1].strip()
                    if delim:
                        s = f"{s} {delim}" if not s.endswith(('.', '!', '?')) else s
                    i += 2
                else:
                    i += 1
                if s:
                    # Clean any trailing punctuation space
                    s = re.sub(r'\s+([.!?])', r'\1', s)
                    line_sents.append(s)

            if not line_sents:
                line_sents = [line_clean]

            # Refine sentences into beats
            for sent in line_sents:
                s_words = sent.split()

                # Dramatic twist check: e.g. "Everything seemed normal… until less than an hour later, the aircraft..."
                m_twist = re.match(r'^(.*?(?:…|\.\.\.)\s*until\s+[^,]+,)\s+(.*)$', sent, re.IGNORECASE)
                if m_twist and len(s_words) > 10:
                    raw_parts.append(m_twist.group(1).strip())
                    raw_parts.append(m_twist.group(2).strip())
                    continue

                if len(s_words) > word_threshold:
                    if rapid_mode:
                        # Rapid mode: split at rhythmic clauses or ~6 word chunks
                        clause_parts = re.split(
                            r'(?:(?<=[,;—\-])\s+|\s+(?=(?:and|but|while|as|where|yet|before|after|with|when|so|because|that|which|beneath|revealed|hidden|containing|towards)\b))',
                            sent,
                            flags=re.IGNORECASE
                        )
                        clause_parts = [cp.strip() for cp in clause_parts if cp.strip()]
                        if len(clause_parts) > 1 and all(len(cp.split()) >= 3 for cp in clause_parts):
                            raw_parts.extend(clause_parts)
                        else:
                            words_in_sent = sent.split()
                            chunk_step = 6
                            for c_idx in range(0, len(words_in_sent), chunk_step):
                                raw_parts.append(" ".join(words_in_sent[c_idx:c_idx + chunk_step]))
                    else:
                        # Standard mode: Keep complete, meaningful sentences (10-18 words).
                        # Only split truly long sentences (> 22 words) at strong clause markers (; , but , while)
                        if any(p in sent for p in [';', '—', ', but ', ', while ', ', however ', ', yet ']):
                            clause_parts = re.split(
                                r'(?<=[;—])\s+|(?<=,)\s+(?=(?:but|while|however|yet|whereas)\b)',
                                sent,
                                flags=re.IGNORECASE
                            )
                            clause_parts = [cp.strip() for cp in clause_parts if cp.strip()]
                            if len(clause_parts) > 1 and all(len(cp.split()) >= 6 for cp in clause_parts):
                                raw_parts.extend(clause_parts)
                                continue
                        raw_parts.append(sent)
                else:
                    raw_parts.append(sent)

    combined_beats = [b for b in raw_parts if b.strip()]
    if not combined_beats:
        combined_beats = [clean_script]

    # Combine tiny orphaned fragments with adjacent segments
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
            if rapid_mode:
                if (curr_len < 3 or b_len < 2) and (curr_len + b_len) <= max_merged_len:
                    curr_beat = f"{curr_beat} {b_clean}"
                else:
                    merged_beats.append(curr_beat)
                    curr_beat = b_clean
            else:
                # In standard mode, preserve clean clause endings (comma, semicolon, ellipsis)
                is_clause_end = curr_beat.rstrip().endswith((',', ';', '—', '…', '...'))
                if (curr_len < 3 or (b_len < 3 and not is_clause_end)) and (curr_len + b_len) <= max_merged_len:
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
        # Guaranteed verbatim fallback: chunk words into segments
        merged_beats = []
        step = 6 if rapid_mode else 14
        for idx in range(0, total_words, step):
            merged_beats.append(" ".join(words[idx:idx + step]))

    # 5. Duration assignment
    beats: List[Tuple[str, float]] = []
    for b in merged_beats:
        b_cnt = len(b.split())
        ratio = b_cnt / max(1, total_words)
        dur = max(effective_min_dur, round(ratio * total_duration, 2))
        beats.append((b, dur))

    sum_dur = sum(d for _, d in beats)
    if sum_dur > 0:
        beats = [(t, max(effective_min_dur, round((d / sum_dur) * total_duration, 2))) for t, d in beats]

    return beats


def create_rapid_story_beats(
    script_text: str,
    total_duration: float = 60.0
) -> List[Tuple[str, float]]:
    """Generates rapid story beats targetting ~2.5s-3.2s per visual cut (18-22 cuts for 60s)."""
    return create_story_beats(
        script_text=script_text,
        total_duration=total_duration,
        min_dur=1.8,
        max_dur=3.2,
        rapid_mode=True
    )
