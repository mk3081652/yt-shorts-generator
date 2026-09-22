import re
import json
import logging
from typing import Dict, List, Any

logger = logging.getLogger(__name__)

VIRAL_HOOKS = [
    "Stop scrolling right now! If you hear this, you are in the lucky 1 percent.",
    "Nobody is talking about this, but it will completely change your perspective.",
    "Whatever you do, NEVER make this one fatal mistake.",
    "Did you know that what scientists just discovered is absolutely terrifying?",
    "I guarantee you have never heard this crazy fact before.",
    "This one secret made millionaires out of ordinary people.",
    "If you think you know the truth about this, prepare to be shocked."
]

VIRAL_TEMPLATES = {
    "mind_blowing_facts": {
        "title": "Mind-Blowing Facts",
        "script": "Did you know that honey never ever spoils? Archaeologists found 3,000-year-old honey in Egyptian tombs that is still completely edible! Also, a cloud can weigh over a million pounds, yet it floats effortlessly in the sky. If your mind is blown, hit subscribe for more daily facts!",
        "category": "Facts & Science"
    },
    "money_psychology": {
        "title": "Millionaire Money Rule",
        "script": "Stop scrolling if you want to be wealthy! Rule number one of the ultra-rich: never trade time for money. Build assets that make you money while you sleep. The average millionaire has seven streams of income. Start building yours today!",
        "category": "Wealth & Business"
    },
    "dark_history": {
        "title": "Dark Unsolved Mystery",
        "script": "In 1518, an inexplicable plague struck Strasbourg. Hundreds of people began dancing uncontrollably in the streets for days until their hearts literally gave out. To this day, science cannot explain what truly caused the Dancing Plague.",
        "category": "Mystery & History"
    },
    "space_terror": {
        "title": "Terrifying Space Discovery",
        "script": "Scientists discovered a black hole moving through deep space at three million miles per hour. It is trailing a chain of newborn stars behind it. If it came anywhere near our solar system, Earth would be swallowed before anyone even noticed.",
        "category": "Space & Sci-Fi"
    },
    "stoic_mindset": {
        "title": "1% Stoic Mindset",
        "script": "Marcus Aurelius once said: You have power over your mind, not outside events. Realize this, and you will find unstoppable strength. Stop worrying about things you cannot control. Focus on what is in front of you.",
        "category": "Motivation & Stoicism"
    }
}

STOP_WORDS = {
    "a", "about", "above", "after", "again", "against", "all", "am", "an", "and",
    "any", "are", "aren't", "as", "at", "be", "because", "been", "before", "being",
    "below", "between", "both", "but", "by", "can't", "cannot", "could", "couldn't",
    "did", "didn't", "do", "does", "doesn't", "doing", "don't", "down", "during",
    "each", "few", "for", "from", "further", "had", "hadn't", "has", "hasn't", "have",
    "haven't", "having", "he", "he'd", "he'll", "he's", "her", "here", "here's", "hers",
    "herself", "him", "himself", "his", "how", "how's", "i", "i'd", "i'll", "i'm",
    "i've", "if", "in", "into", "is", "isn't", "it", "it's", "its", "itself", "let's",
    "me", "more", "most", "mustn't", "my", "myself", "no", "nor", "not", "of", "off",
    "on", "once", "only", "or", "other", "ought", "our", "ours", "ourselves", "out",
    "over", "own", "same", "shan't", "she", "she'd", "she'll", "she's", "should",
    "shouldn't", "so", "some", "such", "than", "that", "that's", "the", "their", "theirs",
    "them", "themselves", "then", "there", "there's", "these", "they", "they'd", "they'll",
    "they're", "they've", "this", "those", "through", "to", "too", "under", "until", "up",
    "very", "was", "wasn't", "we", "we'd", "we'll", "we're", "we've", "were", "weren't",
    "what", "what's", "when", "when's", "where", "where's", "which", "while", "who",
    "who's", "whom", "why", "why's", "with", "won't", "would", "wouldn't", "you", "you'd",
    "you'll", "you're", "you've", "your", "yours", "yourself", "yourselves", "less", "more"
}


def get_viral_hooks() -> List[str]:
    """Return list of viral hook suggestions."""
    return VIRAL_HOOKS


def get_script_templates() -> Dict[str, Any]:
    """Return pre-written viral script templates."""
    return VIRAL_TEMPLATES


def _generate_metadata_nlp_fallback(script: str) -> Dict[str, Any]:
    """
    Deterministic rule-based NLP metadata generator.
    Extracts entities, key subjects, and clauses directly from the script to
    produce high-CTR, contextual titles, descriptions, tags, and hashtags.
    """
    clean = script.strip()
    if not clean:
        clean = "Mind Blowing Facts and Mysteries"

    # Break into sentences
    sentences = [s.strip() for s in re.split(r'(?<=[.!?])\s+', clean) if s.strip()]
    first_sent = sentences[0] if sentences else clean
    first_clean = re.sub(r'[\r\n\t]+', ' ', first_sent).strip()

    # Extract capital-cased multi-word entities (proper nouns / subjects)
    raw_entities = re.findall(r'\b[A-Z][a-zA-Z0-9]*(?:\s+[A-Z0-9][a-zA-Z0-9]*)*\b', clean)
    entities: List[str] = []
    ignored_entity_words = {
        "everything", "everyone", "nothing", "someone", "did", "just", "also",
        "then", "when", "what", "why", "how", "stop", "never", "nobody", "this",
        "at", "in", "on", "watch", "until", "the", "if", "you", "they", "there",
        "from", "with", "into", "seconds", "hours", "minutes", "days", "years"
    }
    for ent in raw_entities:
        ent_parts = ent.split()
        if len(ent_parts) > 1 and ent_parts[0].lower() in {"at", "in", "on", "from", "to", "with", "by", "for", "after", "before", "during"}:
            ent = " ".join(ent_parts[1:])
            ent_parts = ent.split()

        if not any(c.isalpha() for c in ent):
            continue
        if len(ent_parts) == 1 and ent_parts[0].isdigit():
            continue

        ent_low = ent.lower()
        if ent_low not in STOP_WORDS and ent_low not in ignored_entity_words and len(ent) > 2:
            if ent not in entities:
                entities.append(ent)


    # Extract meaningful content words
    words = [re.sub(r'[^a-zA-Z0-9]', '', w) for w in clean.split()]
    meaningful_words = []
    for w in words:
        w_low = w.lower()
        if len(w) >= 3 and any(c.isalpha() for c in w) and not w.isdigit() and w_low not in STOP_WORDS and w_low not in ignored_entity_words:
            if w_low not in [mw.lower() for mw in meaningful_words]:
                meaningful_words.append(w)


    # Pick primary subject / entity
    subject = entities[0] if entities else (meaningful_words[0].capitalize() if meaningful_words else "This Mystery")

    # Construct contextual title
    subject_lower = subject.lower()
    if any(k in subject_lower for k in ("flight", "mh", "plane", "radar", "crash", "sky")):
        title = f"The Vanishing of {subject} ✈️ #shorts"
    elif any(k in subject_lower for k in ("space", "star", "black hole", "universe", "planet", "galaxy")):
        title = f"The Terrifying Secret of {subject} 🌌 #shorts"
    elif any(k in subject_lower for k in ("money", "rich", "wealth", "millionaire", "dollar")):
        title = f"The 1% Rule for {subject} 💰 #shorts"
    elif any(k in subject_lower for k in ("plague", "history", "ancient", "war", "emperor", "tomb")):
        title = f"The Dark Mystery of {subject} ⏳ #shorts"
    elif entities:
        title = f"What Really Happened to {subject}? 😱 #shorts"
    elif len(first_clean) > 10:
        short_hook = first_clean[:45].rstrip(",;:- ")
        title = f"{short_hook}... 🤯 #shorts"
    else:
        title = f"The Secret of {subject} Revealed! ⚡ #shorts"

    # Construct contextual description
    summary = " ".join(sentences[:2]) if len(sentences) >= 2 else first_clean
    desc_lines = [
        summary,
        "",
        "🤔 What do you think really happened? Drop your theory in the comments!",
        "🔔 Subscribe for daily viral shorts, real mysteries, and mind-blowing facts."
    ]

    # Construct targeted tags
    tags: List[str] = []
    for ent in entities[:4]:
        if ent not in tags:
            tags.append(ent)
    for mw in meaningful_words[:6]:
        mw_cap = mw.capitalize()
        if mw_cap not in tags:
            tags.append(mw_cap)

    base_tags = ["shorts", "youtube shorts", "viral shorts", "trending", "mystery", "facts", "shorts feed"]
    for bt in base_tags:
        if bt not in tags and len(tags) < 12:
            tags.append(bt)

    # Construct targeted hashtags
    hashtags_list = []
    for ent in entities[:3]:
        clean_tag = re.sub(r'[^a-zA-Z0-9]', '', ent)
        if clean_tag and len(clean_tag) > 2:
            hashtags_list.append(f"#{clean_tag}")
    for mw in meaningful_words[:3]:
        clean_tag = re.sub(r'[^a-zA-Z0-9]', '', mw.capitalize())
        if clean_tag and f"#{clean_tag}" not in hashtags_list:
            hashtags_list.append(f"#{clean_tag}")
    hashtags_list.extend(["#Shorts", "#Viral", "#Trending"])
    unique_hashtags = list(dict.fromkeys(hashtags_list))[:6]
    hashtags_str = " ".join(unique_hashtags)

    desc_lines.append("")
    desc_lines.append("Created with AI assistance for visual storytelling. Contains synthetic/altered media.")
    desc_lines.append("")
    desc_lines.append(hashtags_str)
    description = "\n".join(desc_lines)

    return {
        "title": title,
        "description": description,
        "tags": tags,
        "hashtags": hashtags_str,
        "altered_or_synthetic_content": True,
        "compliance_notes": (
            "YouTube Partner Program (YPP) Disclosure: This video contains altered or synthetic visuals/audio "
            "generated with AI tools. In YouTube Studio, check 'Altered or synthetic content: Yes'."
        )
    }


def generate_youtube_metadata(script: str) -> Dict[str, Any]:
    """
    Generate viral SEO-optimized YouTube Shorts Title, Description, and Tags
    based on the script content using Gemini AI with smart NLP fallback.
    """
    clean_script = (script or "").strip()
    if not clean_script:
        return _generate_metadata_nlp_fallback("Mind Blowing Facts and Secrets")

    # Try Gemini AI for hyper-tailored viral metadata
    try:
        from engine.llm import generate_content
        prompt = (
            "You are an elite YouTube Shorts Growth & Monetization Specialist.\n"
            "Analyze this spoken voiceover script:\n"
            f'"""{clean_script}"""\n\n'
            "Generate viral, high-CTR YouTube Shorts metadata strictly tailored to the specific story, entities, and events in this script.\n"
            "Return ONLY a valid JSON object with the following keys:\n"
            "{\n"
            '  "title": "A punchy, high-CTR title under 55 characters naming the specific subject with 1-2 emojis and #shorts",\n'
            '  "description": "Engaging description: 2-3 sentences summarizing the exact story from this script, followed by an engaging question for comments, followed by 5-6 targeted hashtags tailored to the topic",\n'
            '  "tags": ["8-12 specific tags about the story subjects, entities, and keywords from the script", "shorts", "viral shorts"],\n'
            '  "hashtags": "5-6 targeted hashtags e.g. #Subject #Mystery #Shorts"\n'
            "}"
        )

        raw_resp, model_used = generate_content(prompt, thinking_level="low", timeout=12)
        if raw_resp:
            clean_json = raw_resp.strip()
            if clean_json.startswith("```"):
                clean_json = re.sub(r"^```(?:json)?\s*", "", clean_json)
                clean_json = re.sub(r"\s*```$", "", clean_json)
            data = json.loads(clean_json)

            title = str(data.get("title", "")).strip()
            description = str(data.get("description", "")).strip()
            tags = data.get("tags", [])
            hashtags = str(data.get("hashtags", "")).strip()

            if title:
                if "#shorts" not in title.lower():
                    title = f"{title} #shorts"
                if not isinstance(tags, list) or len(tags) < 3:
                    tags = [t.strip() for t in str(tags).split(",") if t.strip()]

                if "Created with AI assistance" not in description:
                    description = f"{description}\n\nCreated with AI assistance for visual storytelling. Contains synthetic/altered media."

                return {
                    "title": title,
                    "description": description,
                    "tags": tags,
                    "hashtags": hashtags or "#shorts #viral #trending",
                    "altered_or_synthetic_content": True,
                    "compliance_notes": (
                        "YouTube Partner Program (YPP) Disclosure: This video contains altered or synthetic visuals/audio "
                        "generated with AI tools. In YouTube Studio, check 'Altered or synthetic content: Yes'."
                    )
                }
    except Exception as e:
        logger.warning(f"[Metadata] Gemini metadata generation error, using NLP fallback: {e}")

    # Fallback to deterministic NLP entity extraction
    return _generate_metadata_nlp_fallback(clean_script)
