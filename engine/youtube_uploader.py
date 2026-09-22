"""
engine/youtube_uploader.py - YouTube Data API v3 integration for 1-Click Shorts Publishing.
Handles Google OAuth2 authentication, token caching, chunked resumable video upload,
and YPP synthetic media / Shorts metadata compliance.
"""

import os
import json
import logging
from typing import Dict, Any, List, Optional, Callable

from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from googleapiclient.errors import HttpError

from engine.config import get_youtube_client_secrets_path, get_youtube_token_path

logger = logging.getLogger("youtube_uploader")

# Scopes required for upload and channel status check
SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.readonly"
]


def check_auth_status() -> Dict[str, Any]:
    """
    Checks the status of YouTube OAuth authentication:
    - Verifies whether client_secrets.json exists.
    - Verifies whether token.json exists and contains valid/refreshable credentials.
    - Returns channel info if authenticated.
    """
    client_secrets_path = get_youtube_client_secrets_path()
    token_path = get_youtube_token_path()

    secrets_exist = os.path.exists(client_secrets_path)
    token_exist = os.path.exists(token_path)

    if not secrets_exist and not token_exist:
        return {
            "authenticated": False,
            "client_secrets_found": False,
            "token_found": False,
            "client_secrets_path": client_secrets_path,
            "message": "client_secrets.json not found. Place OAuth Client ID JSON in project root or set YOUTUBE_CLIENT_SECRETS_FILE."
        }

    creds = None
    if token_exist:
        try:
            creds = Credentials.from_authorized_user_file(token_path, SCOPES)
            if creds and creds.expired and creds.refresh_token:
                try:
                    creds.refresh(Request())
                    with open(token_path, "w", encoding="utf-8") as token_file:
                        token_file.write(creds.to_json())
                except Exception as e:
                    logger.warning(f"Failed to refresh YouTube token: {e}")
                    creds = None
        except Exception as e:
            logger.error(f"Error reading token file {token_path}: {e}")
            creds = None

    if creds and creds.valid:
        # Fetch channel snippet to display account info
        try:
            youtube = build("youtube", "v3", credentials=creds)
            resp = youtube.channels().list(mine=True, part="snippet").execute()
            items = resp.get("items", [])
            if items:
                snippet = items[0].get("snippet", {})
                return {
                    "authenticated": True,
                    "client_secrets_found": secrets_exist,
                    "token_found": True,
                    "channel_title": snippet.get("title", "Unknown Channel"),
                    "channel_id": items[0].get("id", ""),
                    "thumbnails": snippet.get("thumbnails", {})
                }
            return {
                "authenticated": True,
                "client_secrets_found": secrets_exist,
                "token_found": True,
                "channel_title": "Authenticated Channel"
            }
        except Exception as e:
            return {
                "authenticated": True,
                "client_secrets_found": secrets_exist,
                "token_found": True,
                "channel_title": "Connected (API Quota or Offline)",
                "warning": str(e)
            }

    return {
        "authenticated": False,
        "client_secrets_found": secrets_exist,
        "token_found": token_exist,
        "client_secrets_path": client_secrets_path,
        "message": "Credentials expired or not yet authorized. Click Authorize to connect your YouTube account."
    }


def get_authenticated_service():
    """
    Loads valid credentials or executes the local server OAuth flow.
    Saves credentials into token.json for future unattended runs.
    """
    token_path = get_youtube_token_path()
    client_secrets_path = get_youtube_client_secrets_path()

    creds = None
    if os.path.exists(token_path):
        try:
            creds = Credentials.from_authorized_user_file(token_path, SCOPES)
        except Exception as e:
            logger.warning(f"Could not load credentials from {token_path}: {e}")

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
                with open(token_path, "w", encoding="utf-8") as f:
                    f.write(creds.to_json())
            except Exception as e:
                logger.warning(f"Token refresh failed: {e}. Initiating fresh OAuth flow.")
                creds = None

        if not creds:
            if not os.path.exists(client_secrets_path):
                raise FileNotFoundError(
                    f"YouTube client secrets file not found at: {client_secrets_path}. "
                    "Please download OAuth 2.0 Client credentials JSON from Google Cloud Console."
                )
            flow = InstalledAppFlow.from_client_secrets_file(client_secrets_path, SCOPES)
            creds = flow.run_local_server(port=0)
            with open(token_path, "w", encoding="utf-8") as f:
                f.write(creds.to_json())

    return build("youtube", "v3", credentials=creds)


def upload_video_to_youtube(
    video_path: str,
    title: str,
    description: str = "",
    tags: Optional[List[str]] = None,
    privacy_status: str = "unlisted",
    category_id: str = "27",
    made_for_kids: bool = False,
    synthetic_content: bool = True,
    progress_callback: Optional[Callable[[str, int], None]] = None
) -> Dict[str, Any]:
    """
    Uploads a video to YouTube using resumable chunked upload.
    - Adds #Shorts tag to title/tags if not present to ensure YouTube indexes it as a Short.
    - Adds synthetic content disclosure for YPP policy compliance.
    - Privacy status supports 'public', 'unlisted', or 'private' (default 'unlisted').
    - Returns Dict with video_id, youtube_url, and status.
    """
    if not os.path.exists(video_path):
        return {"success": False, "error": f"Video file not found: {video_path}"}

    file_size = os.path.getsize(video_path)
    if file_size == 0:
        return {"success": False, "error": f"Video file is empty (0 bytes): {video_path}"}

    # Format Title for Shorts
    clean_title = title.strip()
    if "#Shorts" not in clean_title and "#shorts" not in clean_title:
        if len(clean_title) <= 90:
            clean_title = f"{clean_title} #Shorts"
    # Clamp title to 100 chars (YouTube max)
    clean_title = clean_title[:100]

    # Format Tags
    effective_tags = list(tags or [])
    for default_tag in ["Shorts", "YTShorts", "AI"]:
        if default_tag not in effective_tags:
            effective_tags.append(default_tag)

    # Format Description with synthetic media disclosure
    disclaimer = "\n\n---\n✨ Created with AI. Contains synthetic/AI-generated visuals and voice narration."
    full_description = (description.strip() + disclaimer).strip()

    # Normalize privacy status
    norm_privacy = privacy_status.lower().strip()
    if norm_privacy not in ("public", "unlisted", "private"):
        norm_privacy = "unlisted"

    media = None
    try:
        if progress_callback:
            progress_callback("Authenticating with YouTube API...", 70)

        youtube = get_authenticated_service()

        body = {
            "snippet": {
                "title": clean_title,
                "description": full_description,
                "tags": effective_tags,
                "categoryId": category_id,
            },
            "status": {
                "privacyStatus": norm_privacy,
                "selfDeclaredMadeForKids": made_for_kids,
                "embeddable": True,
                "publicStatsViewable": True
            }
        }

        # 2MB chunksize for reliable resumable upload
        media = MediaFileUpload(
            video_path,
            mimetype="video/mp4",
            chunksize=2 * 1024 * 1024,
            resumable=True
        )

        request = youtube.videos().insert(
            part="snippet,status",
            body=body,
            media_body=media
        )

        if progress_callback:
            progress_callback("Uploading video chunks to YouTube...", 75)

        response = None
        while response is None:
            status, response = request.next_chunk()
            if status and progress_callback:
                pct = int(status.progress() * 100)
                # Map upload progress from 75% to 95%
                mapped_pct = 75 + int(pct * 0.20)
                progress_callback(f"Uploading to YouTube... {pct}%", mapped_pct)

        video_id = response.get("id")
        if not video_id:
            return {"success": False, "error": f"Upload succeeded but no video ID returned: {response}"}

        actual_privacy = response.get("status", {}).get("privacyStatus", norm_privacy)
        logger.info(f"[YouTube Upload] Upload completed! Video ID: {video_id}, Requested: '{norm_privacy}', Assigned by YouTube: '{actual_privacy}'")

        youtube_url = f"https://www.youtube.com/shorts/{video_id}"
        watch_url = f"https://www.youtube.com/watch?v={video_id}"

        if progress_callback:
            progress_callback(f"Upload complete! Published as {actual_privacy.title()}.", 100)

        return {
            "success": True,
            "video_id": video_id,
            "youtube_url": youtube_url,
            "watch_url": watch_url,
            "title": clean_title,
            "privacy_status": norm_privacy,
            "actual_privacy_status": actual_privacy,
            "raw_response": response
        }

    except HttpError as e:
        error_details = str(e)
        try:
            error_json = json.loads(e.content.decode("utf-8"))
            error_details = error_json.get("error", {}).get("message", str(e))
        except Exception:
            pass
        logger.error(f"YouTube API HttpError: {error_details}")
        return {"success": False, "error": f"YouTube API error: {error_details}"}
    except Exception as e:
        logger.error(f"YouTube upload failed: {e}")
        return {"success": False, "error": f"Upload failed: {str(e)}"}
    finally:
        if media and hasattr(media, "_fd") and media._fd:
            try:
                media._fd.close()
            except Exception:
                pass

