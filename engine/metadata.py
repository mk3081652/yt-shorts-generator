import random
from typing import Dict, List, Any

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

def get_viral_hooks() -> List[str]:
    """Return list of viral hook suggestions."""
    return VIRAL_HOOKS

def get_script_templates() -> Dict[str, Any]:
    """Return pre-written viral script templates."""
    return VIRAL_TEMPLATES

def generate_youtube_metadata(script: str) -> Dict[str, Any]:
    """
    Generate viral SEO-optimized YouTube Shorts Title, Description, and Tags
    based on the script content.
    """
    # Extract first sentence or key words
    words = script.split()
    first_sentence = script.split('.')[0] if '.' in script else " ".join(words[:8])
    clean_first = first_sentence.replace('!', '').replace('?', '').strip()

    titles = [
        f"{clean_first[:45]}... 😱 #shorts",
        f"The Truth About This Will Shock You! 🤯 #viral",
        f"Why Nobody Talks About This... ⚡ #shorts",
        f"You Won't Believe This Crazy Secret! 🚀 #shorts",
        f"Watch Until The End! 💥 #shorts"
    ]
    
    selected_title = random.choice(titles)
    
    description = (
        f"{selected_title}\n\n"
        f"🔥 Did this surprise you? Share your thoughts in the comments below!\n"
        f"🔔 Subscribe for daily viral shorts, facts and secrets.\n\n"
        f"#shorts #ytshorts #viral #facts #didyouknow #trending #mindblowing #shortsfeed #monetization"
    )
    
    tags = [
        "shorts", "youtube shorts", "viral shorts", "facts", "did you know",
        "mind blowing", "trending", "shorts feed", "viral video", "daily facts",
        "interesting facts", "satisfying", "top 5"
    ]
    
    return {
        "title": selected_title,
        "description": description,
        "tags": tags,
        "hashtags": "#shorts #viral #facts #trending #shortsfeed"
    }
