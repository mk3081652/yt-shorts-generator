"""
engine/thumbnail.py - High-CTR Viral YouTube Thumbnail Generator.
Generates bold, high-contrast, attention-seeking thumbnails with:
- Contrast & saturation enhancements
- High-impact pill badges (TOP SECRET, CLASSIFIED, WHAT THEY FOUND)
- Drawn warning danger icon
- Giant, razor-outlined typography (Electric Yellow & Pure White)
- Glowing neon borders to maximize Click-Through Rate (CTR) in YouTube Search & Feeds.
"""

import os
import re
import subprocess
from typing import Optional, Tuple
from PIL import Image, ImageDraw, ImageFont, ImageEnhance, ImageFilter
import imageio_ffmpeg

FFMPEG_EXE = imageio_ffmpeg.get_ffmpeg_exe()


def _resolve_bold_font(size: int) -> ImageFont.ImageFont:
    """Finds the most impactful bold font available on the host system."""
    candidates = [
        "C:\\Windows\\Fonts\\impact.ttf",
        "C:\\Windows\\Fonts\\arialbd.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
        "assets/fonts/bold.ttf"
    ]
    for c in candidates:
        if os.path.exists(c):
            try:
                return ImageFont.truetype(c, size)
            except Exception:
                pass
    return ImageFont.load_default()


def extract_best_frame_from_video(video_path: str, timestamp: float = 1.2, output_path: Optional[str] = None) -> Optional[str]:
    """Extracts a sharp frame from the rendered video to use as thumbnail backdrop."""
    if not video_path or not os.path.exists(video_path):
        return None

    if not output_path:
        base = os.path.splitext(video_path)[0]
        output_path = f"{base}_frame.jpg"

    cmd = [
        FFMPEG_EXE, "-y",
        "-ss", f"{timestamp:.2f}",
        "-i", os.path.abspath(video_path),
        "-vframes", "1",
        "-q:v", "2",
        os.path.abspath(output_path)
    ]
    res = subprocess.run(cmd, capture_output=True)
    if res.returncode == 0 and os.path.exists(output_path):
        return output_path
    return None


def derive_thumbnail_text(title: str, script: str = "") -> Tuple[str, str, str]:
    """
    Analyzes title and script to extract high-CTR thumb text:
    Returns (badge_text, headline_line1, headline_line2).
    Uses clean ASCII text to guarantee zero font-rendering glitches.
    """
    clean_t = re.sub(r'#\w+', '', title or "").strip()
    clean_t = re.sub(r'[^\w\s\':?!-]', '', clean_t).strip()

    upper_title = clean_t.upper()
    
    badge = "WARNING: TOP SECRET"
    if any(k in upper_title for k in ["SECRET", "CONCEALED", "HIDDEN"]):
        badge = "CLASSIFIED DISCOVERY"
    elif any(k in upper_title for k in ["MYSTERY", "DISCOVERY", "FOUND", "RADAR"]):
        badge = "WHAT THEY FOUND"
    elif any(k in upper_title for k in ["TRUTH", "LIE", "NEVER"]):
        badge = "THEY LIED TO US!"
    elif any(k in upper_title for k in ["SPHINX", "PYRAMID", "EGYPT"]):
        badge = "40FT UNDERGROUND"
    elif any(k in upper_title for k in ["SPACE", "NASA", "BLACK HOLE"]):
        badge = "NASA SILENCED THIS"
    elif any(k in upper_title for k in ["BERMUDA", "MH370", "FLIGHT", "OCEAN"]):
        badge = "UNRESOLVED MYSTERY"

    words = clean_t.split()
    if len(words) <= 3:
        l1 = clean_t.upper()
        l2 = "EXPLAINED!"
    elif len(words) <= 6:
        mid = len(words) // 2
        l1 = " ".join(words[:mid]).upper()
        l2 = " ".join(words[mid:]).upper()
    else:
        l1 = " ".join(words[:3]).upper()
        l2 = " ".join(words[3:6]).upper() + "!"

    if len(l1) > 20:
        l1 = l1[:18] + "..."
    if len(l2) > 20:
        l2 = l2[:18] + "!"

    return badge, l1, l2


def _draw_warning_triangle(draw: ImageDraw.ImageDraw, x: int, y: int, size: int = 34):
    """Draws a bright yellow warning triangle icon with black exclamation mark."""
    h = size
    w = int(size * 1.15)
    points = [(x, y + h), (x + w // 2, y), (x + w, y + h)]
    draw.polygon(points, fill=(255, 230, 0), outline=(0, 0, 0))
    # Exclamation mark
    mid_x = x + w // 2
    draw.line([(mid_x, y + int(h * 0.35)), (mid_x, y + int(h * 0.70))], fill=(0, 0, 0), width=3)
    draw.rectangle([(mid_x - 1, y + int(h * 0.80)), (mid_x + 1, y + int(h * 0.88))], fill=(0, 0, 0))


def generate_viral_thumbnail(
    title: str,
    script: str = "",
    video_path: Optional[str] = None,
    base_image_path: Optional[str] = None,
    output_path: Optional[str] = None,
    width: int = 1280,
    height: int = 720
) -> str:
    """
    Creates a master 1280x720 high-CTR thumbnail for YouTube.
    Combines background frame, saturation pop, dark gradient, alert badge, and giant impact text.
    """
    if not output_path:
        output_path = os.path.abspath("outputs/thumbnail_viral.jpg")
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)

    # 1. Acquire background image
    source_img_path = base_image_path
    if not source_img_path and video_path:
        source_img_path = extract_best_frame_from_video(video_path, timestamp=1.2)

    bg_img = None
    if source_img_path and os.path.exists(source_img_path):
        try:
            bg_img = Image.open(source_img_path).convert("RGB")
        except Exception:
            bg_img = None

    if not bg_img:
        # Create dark atmospheric suspense base
        bg_img = Image.new("RGB", (width, height), color=(14, 18, 30))
        d_base = ImageDraw.Draw(bg_img)
        d_base.ellipse([(width // 4, -100), (width * 3 // 4, height)], fill=(35, 45, 75))

    # Resize/crop to fill target width/height
    w, h = bg_img.size
    target_ratio = width / height
    img_ratio = w / h

    if img_ratio > target_ratio:
        new_w = int(h * target_ratio)
        offset = (w - new_w) // 2
        bg_img = bg_img.crop((offset, 0, offset + new_w, h))
    else:
        new_h = int(w / target_ratio)
        offset = (h - new_h) // 2
        bg_img = bg_img.crop((0, offset, w, offset + new_h))

    bg_img = bg_img.resize((width, height), Image.Resampling.LANCZOS)

    # 2. Enhance visuals (Contrast + Saturation pop for small screens)
    try:
        contrast = ImageEnhance.Contrast(bg_img)
        bg_img = contrast.enhance(1.22)
        color = ImageEnhance.Color(bg_img)
        bg_img = color.enhance(1.25)
    except Exception:
        pass

    # 3. Add heavy dark gradient overlay on text zone (left & bottom)
    gradient = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    d_grad = ImageDraw.Draw(gradient)

    for x in range(int(width * 0.72)):
        alpha = int(225 * (1.0 - (x / (width * 0.72))))
        d_grad.line([(x, 0), (x, height)], fill=(5, 7, 14, alpha))

    for y in range(int(height * 0.4), height):
        alpha = int(190 * ((y - height * 0.4) / (height * 0.6)))
        d_grad.line([(0, y), (width, y)], fill=(5, 7, 14, alpha))

    bg_img.paste(Image.alpha_composite(bg_img.convert("RGBA"), gradient).convert("RGB"))
    draw = ImageDraw.Draw(bg_img)

    # 4. Text and Graphic Badges
    badge_text, line1, line2 = derive_thumbnail_text(title, script)

    font_badge = _resolve_bold_font(34)
    font_main = _resolve_bold_font(92)

    # Top Alert Pill Badge (Red)
    badge_w = int(len(badge_text) * 21) + 85
    badge_box = [(50, 48), (50 + badge_w, 114)]
    draw.rounded_rectangle(badge_box, radius=12, fill=(235, 25, 45))
    
    # Warning triangle icon inside pill badge
    _draw_warning_triangle(draw, x=65, y=62, size=36)
    draw.text((118, 62), badge_text, font=font_badge, fill=(255, 255, 255))

    # Line 1: Electric Yellow with deep black outline
    draw.text((50, 230), line1, font=font_main, fill=(255, 232, 0), stroke_width=8, stroke_fill=(0, 0, 0))

    # Line 2: Pure White with deep black outline
    draw.text((50, 355), line2, font=font_main, fill=(255, 255, 255), stroke_width=8, stroke_fill=(0, 0, 0))

    # 5. Glowing Neon Outer Border (Electric Yellow 8px)
    draw.rectangle([(0, 0), (width - 1, height - 1)], outline=(255, 220, 0), width=8)

    bg_img.save(output_path, "JPEG", quality=95)
    return output_path
