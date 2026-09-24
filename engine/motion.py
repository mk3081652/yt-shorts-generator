"""
engine/motion.py - Video & image motion clipping for YouTube Shorts.
Handles Ken Burns camera moves, video scene clips, and blank failsafe clips.
"""

import os
import time
import urllib.request
import subprocess
from typing import Any, Union
import imageio_ffmpeg

FFMPEG_EXE = imageio_ffmpeg.get_ffmpeg_exe()


def download_image_file(img_url: str, save_path: str, max_retries: int = 3) -> bool:
    """Safely downloads an image with retries and realistic headers."""
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36'
    }
    for attempt in range(max_retries):
        try:
            req = urllib.request.Request(img_url, headers=headers)
            with urllib.request.urlopen(req, timeout=12) as resp:
                content = resp.read()
                if len(content) > 1000:
                    os.makedirs(os.path.dirname(os.path.abspath(save_path)), exist_ok=True)
                    with open(save_path, 'wb') as f:
                        f.write(content)
                    return True
        except Exception as e:
            if attempt < max_retries - 1:
                time.sleep(0.6 * (attempt + 1))
            else:
                print(f"[Motion] Failed to download {img_url} after {max_retries} attempts: {e}")
    return False


MOTION_MAP = {
    "push in": 0,
    "zoom in": 0,
    "push": 0,
    "pull out": 1,
    "zoom out": 1,
    "pull": 1,
    "pan right": 2,
    "right": 2,
    "pan left": 3,
    "left": 3,
    "tilt up": 4,
    "tilt": 4,
    "up": 4,
    "static": 5,
    "none": 5,
}


def create_ken_burns_motion_clip(
    image_path: str,
    duration: float,
    output_path: str,
    motion_index: int = 0,
    motion: Any = None
) -> bool:
    """
    Turns an image into a 1080x1920 9:16 vertical video with continuous cinematic motion:
      0: Dynamic Center Push (Zoom-in from 1.0 to 1.25)
      1: Dramatic Reveal Pull-Out (Zoom-out from 1.25 to 1.0)
      2: Horizontal Pan-Right + Zoom (Glides from left to right)
      3: Horizontal Pan-Left + Zoom (Glides from right to left)
      4: Vertical Tilt-Up + Zoom (Glides upwards)
      5: Static (No camera motion, just scale & crop)
    """
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    total_frames = max(15, int(duration * 30))
    d_str = str(total_frames)

    if motion is not None:
        if isinstance(motion, str):
            m_type = MOTION_MAP.get(motion.strip().lower(), 0)
        else:
            try:
                m_type = int(motion) % 6
            except (ValueError, TypeError):
                m_type = 0
    else:
        m_type = int(motion_index) % 6

    if m_type == 5:
        vf = (
            "scale=1080:1920:force_original_aspect_ratio=increase,"
            "crop=1080:1920,"
            "eq=contrast=1.06:saturation=1.12,"
            "format=yuv420p"
        )
    else:
        if m_type == 0:
            zoom_expr = "min(zoom+0.0022,1.25)"
            x_expr = "iw/2-(iw/zoom/2)"
            y_expr = "ih/2-(ih/zoom/2)"
        elif m_type == 1:
            zoom_expr = "max(1.25-0.0022*on,1.0)"
            x_expr = "iw/2-(iw/zoom/2)"
            y_expr = "ih/2-(ih/zoom/2)"
        elif m_type == 2:
            zoom_expr = "min(zoom+0.0015,1.20)"
            x_expr = f"(iw-iw/zoom)*(on/{d_str})"
            y_expr = "ih/2-(ih/zoom/2)"
        elif m_type == 3:
            zoom_expr = "min(zoom+0.0015,1.20)"
            x_expr = f"(iw-iw/zoom)*(1-on/{d_str})"
            y_expr = "ih/2-(ih/zoom/2)"
        else:
            zoom_expr = "min(zoom+0.0016,1.22)"
            x_expr = "iw/2-(iw/zoom/2)"
            y_expr = f"(ih-ih/zoom)*(1-on/{d_str})"

        vf = (
            f"scale=1080:1920:force_original_aspect_ratio=increase,"
            f"crop=1080:1920,"
            f"zoompan=z='{zoom_expr}':d={d_str}:x='{x_expr}':y='{y_expr}':s=1080x1920:fps=30,"
            f"eq=contrast=1.06:saturation=1.12,"
            f"format=yuv420p"
        )

    cmd = [
        FFMPEG_EXE, "-y",
        "-loop", "1",
        "-i", os.path.abspath(image_path),
        "-vf", vf,
        "-t", f"{duration:.2f}",
        "-r", "30",
        "-c:v", "libx264",
        "-preset", "ultrafast",
        "-threads", "2",
        "-crf", "22",
        os.path.abspath(output_path)
    ]

    res = subprocess.run(cmd, capture_output=True)
    return res.returncode == 0 and os.path.exists(output_path)


def make_blank_clip(duration: float, output_path: str) -> bool:
    """Generates an aesthetic dark cinematic 1080x1920 video clip for empty/quota scenes via lavfi."""
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    cmd = [
        FFMPEG_EXE, "-y",
        "-f", "lavfi",
        "-i", "color=c=0x0b1120:s=1080x1920:r=30",
        "-t", f"{duration:.2f}",
        "-c:v", "libx264",
        "-preset", "ultrafast",
        "-threads", "2",
        "-crf", "22",
        "-pix_fmt", "yuv420p",
        os.path.abspath(output_path)
    ]
    res = subprocess.run(cmd, capture_output=True)
    return res.returncode == 0 and os.path.exists(output_path)


def make_video_scene_clip(src_video_path: str, duration: float, output_path: str) -> bool:
    """Scales, crops to 1080x1920, and trims or loops video to exact duration."""
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    vf = "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,fps=30,format=yuv420p"
    cmd = [
        FFMPEG_EXE, "-y",
        "-stream_loop", "-1",
        "-i", os.path.abspath(src_video_path),
        "-vf", vf,
        "-r", "30",
        "-t", f"{duration:.2f}",
        "-c:v", "libx264",
        "-preset", "ultrafast",
        "-threads", "2",
        "-crf", "22",
        "-an",
        os.path.abspath(output_path)
    ]
    res = subprocess.run(cmd, capture_output=True)
    return res.returncode == 0 and os.path.exists(output_path)
