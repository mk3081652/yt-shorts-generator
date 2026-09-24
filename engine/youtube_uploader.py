"""
engine/youtube_uploader.py - YouTube Data API v3 integration for 1-Click Shorts Publishing.
Handles Google OAuth2 authentication, multi-channel token caching, chunked resumable video upload,
channel management (list, add, switch, remove, import/export), and YPP compliance.
"""

import os
import json
import time
import logging
import shutil
from typing import Dict, Any, List, Optional, Callable

from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow, Flow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from googleapiclient.errors import HttpError

from engine.config import (
    get_youtube_client_secrets_path,
    get_youtube_token_path,
    get_youtube_tokens_dir
)

logger = logging.getLogger("youtube_uploader")

# Scopes required for upload and channel status check
SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.readonly"
]


def ensure_tokens_dir() -> str:
    """Ensures the multi-channel tokens directory exists and returns its absolute path."""
    t_dir = get_youtube_tokens_dir()
    os.makedirs(t_dir, exist_ok=True)
    return t_dir


def _get_channels_index_path() -> str:
    return os.path.join(ensure_tokens_dir(), "channels.json")


def _get_active_channel_file_path() -> str:
    return os.path.join(ensure_tokens_dir(), "active_channel.txt")


_MIGRATION_RUN = False

def _migrate_legacy_token_if_needed():
    """
    Auto-migrates existing single token.json (or /etc/secrets/token.json)
    into the tokens/ multi-channel storage if not already migrated.
    """
    global _MIGRATION_RUN
    if _MIGRATION_RUN:
        return
    _MIGRATION_RUN = True

    t_dir = ensure_tokens_dir()
    legacy_token_path = get_youtube_token_path()
    if not os.path.exists(legacy_token_path):
        return

    # If channels already exist in tokens directory, no need to re-migrate
    existing_tokens = [f for f in os.listdir(t_dir) if f.endswith(".json") and not f.endswith(".meta.json") and f != "channels.json"]
    if existing_tokens:
        return

    try:
        logger.info(f"[YouTube Auth] Migrating legacy token from {legacy_token_path} to multi-channel storage...")
        creds = Credentials.from_authorized_user_file(legacy_token_path, SCOPES)
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
            except Exception as e:
                logger.warning(f"Could not refresh legacy token during migration: {e}")

        if creds and creds.valid:
            save_channel_credentials(json.loads(creds.to_json()))
            logger.info("[YouTube Auth] Legacy token successfully migrated to multi-channel storage.")
    except Exception as e:
        logger.error(f"[YouTube Auth] Legacy token migration failed: {e}")


def get_active_channel_id() -> Optional[str]:
    """Returns the ID of currently active channel."""
    active_file = _get_active_channel_file_path()
    if os.path.exists(active_file):
        try:
            with open(active_file, "r", encoding="utf-8") as f:
                cid = f.read().strip()
                if cid:
                    return cid
        except Exception:
            pass

    # Fallback to index
    index_path = _get_channels_index_path()
    if os.path.exists(index_path):
        try:
            with open(index_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data.get("active_channel_id")
        except Exception:
            pass

    return None


def set_active_channel(channel_id: str) -> bool:
    """Sets the designated channel_id as active without recursive list calls."""
    if channel_id:
        t_dir = ensure_tokens_dir()
        token_path = os.path.join(t_dir, f"{channel_id}.json")
        if not os.path.exists(token_path):
            return False

    active_file = _get_active_channel_file_path()
    try:
        with open(active_file, "w", encoding="utf-8") as f:
            f.write(channel_id or "")
    except Exception as e:
        logger.warning(f"Failed to write active channel file: {e}")

    index_path = _get_channels_index_path()
    try:
        data = {}
        if os.path.exists(index_path):
            with open(index_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        data["active_channel_id"] = channel_id
        with open(index_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        return True
    except Exception as e:
        logger.error(f"Failed to update channels index with active channel: {e}")
        return False


def list_channels() -> List[Dict[str, Any]]:
    """
    Returns list of all connected YouTube channels with snippet and auth state.
    """
    _migrate_legacy_token_if_needed()
    t_dir = ensure_tokens_dir()
    channels: List[Dict[str, Any]] = []

    active_id = get_active_channel_id()
    token_files = [f for f in os.listdir(t_dir) if f.endswith(".json") and not f.endswith(".meta.json") and f != "channels.json"]

    # Also check if legacy token is present but not in tokens dir
    legacy_path = get_youtube_token_path()
    if not token_files and os.path.exists(legacy_path):
        _migrate_legacy_token_if_needed()
        token_files = [f for f in os.listdir(t_dir) if f.endswith(".json") and not f.endswith(".meta.json") and f != "channels.json"]

    for tf in token_files:
        path = os.path.join(t_dir, tf)
        channel_id = os.path.splitext(tf)[0]
        try:
            creds = Credentials.from_authorized_user_file(path, SCOPES)
            if creds and creds.expired and creds.refresh_token:
                try:
                    creds.refresh(Request())
                    with open(path, "w", encoding="utf-8") as f:
                        f.write(creds.to_json())
                except Exception as e:
                    logger.warning(f"Failed to refresh token for channel {channel_id}: {e}")

            valid = bool(creds and creds.valid)
            info = {
                "channel_id": channel_id,
                "channel_title": "Connected Channel",
                "thumbnail_url": "",
                "authenticated": valid,
                "is_active": (channel_id == active_id)
            }

            # Try to fetch or cached snippet
            cached_meta_path = os.path.join(t_dir, f"{channel_id}.meta.json")
            if os.path.exists(cached_meta_path):
                try:
                    with open(cached_meta_path, "r", encoding="utf-8") as mf:
                        meta = json.load(mf)
                        info["channel_title"] = meta.get("channel_title", info["channel_title"])
                        info["thumbnail_url"] = meta.get("thumbnail_url", "")
                        info["custom_url"] = meta.get("custom_url", "")
                except Exception:
                    pass

            if valid and not info.get("thumbnail_url"):
                try:
                    youtube = build("youtube", "v3", credentials=creds)
                    resp = youtube.channels().list(mine=True, part="snippet").execute()
                    items = resp.get("items", [])
                    if items:
                        snip = items[0].get("snippet", {})
                        real_id = items[0].get("id", channel_id)
                        info["channel_title"] = snip.get("title", info["channel_title"])
                        info["thumbnail_url"] = snip.get("thumbnails", {}).get("default", {}).get("url", "")
                        info["custom_url"] = snip.get("customUrl", "")
                        # Save cache
                        with open(cached_meta_path, "w", encoding="utf-8") as mf:
                            json.dump(info, mf, indent=2)
                except Exception as ex:
                    logger.debug(f"Could not fetch fresh snippet for channel {channel_id}: {ex}")

            channels.append(info)

        except Exception as e:
            logger.error(f"Error inspecting token file {path}: {e}")
            channels.append({
                "channel_id": channel_id,
                "channel_title": f"Corrupted Channel ({channel_id})",
                "thumbnail_url": "",
                "authenticated": False,
                "is_active": (channel_id == active_id),
                "error": str(e)
            })

    # If active_id was not set but we have channels, make the first one active
    if channels and not any(c.get("is_active") for c in channels):
        channels[0]["is_active"] = True
        set_active_channel(channels[0]["channel_id"])

    return channels


def save_channel_credentials(creds_data: Any, meta_info: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Validates credentials data (dict or JSON string), determines channel metadata
    (using provided meta_info or contacting YouTube API), saves to tokens/{channel_id}.json,
    and sets as the active channel.
    """
    t_dir = ensure_tokens_dir()

    if isinstance(creds_data, str):
        try:
            creds_data = json.loads(creds_data)
        except Exception as e:
            raise ValueError(f"Invalid JSON string for credentials: {e}")

    if not isinstance(creds_data, dict):
        raise ValueError("Credentials data must be a valid JSON dictionary.")

    # Build Credentials object
    creds = Credentials.from_authorized_user_info(creds_data, SCOPES)
    if creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
        except Exception as ex:
            logger.warning(f"Could not refresh credentials immediately during save: {ex}")

    channel_id = None
    channel_title = "YouTube Channel"
    thumbnail_url = ""
    custom_url = ""

    if meta_info and isinstance(meta_info, dict) and meta_info.get("channel_id"):
        channel_id = meta_info.get("channel_id")
        channel_title = meta_info.get("channel_title", "YouTube Channel")
        thumbnail_url = meta_info.get("thumbnail_url", "")
        custom_url = meta_info.get("custom_url", "")

    if not channel_id:
        # Contact YouTube to obtain channel metadata
        try:
            youtube = build("youtube", "v3", credentials=creds)
            resp = youtube.channels().list(mine=True, part="snippet").execute()
            items = resp.get("items", [])
            if items:
                snippet = items[0].get("snippet", {})
                channel_id = items[0].get("id")
                channel_title = snippet.get("title", channel_title)
                thumbnail_url = snippet.get("thumbnails", {}).get("default", {}).get("url", "")
                custom_url = snippet.get("customUrl", "")
        except Exception as ex:
            logger.warning(f"Failed to query YouTube API during save: {ex}")

    if not channel_id:
        channel_id = creds_data.get("channel_id") or f"channel_{int(time.time())}"

    # Save credentials into tokens/{channel_id}.json
    target_token_file = os.path.join(t_dir, f"{channel_id}.json")
    with open(target_token_file, "w", encoding="utf-8") as f:
        f.write(creds.to_json())

    # Save channel metadata cache
    target_meta_file = os.path.join(t_dir, f"{channel_id}.meta.json")
    saved_meta = {
        "channel_id": channel_id,
        "channel_title": channel_title,
        "thumbnail_url": thumbnail_url,
        "custom_url": custom_url,
        "authenticated": True
    }
    with open(target_meta_file, "w", encoding="utf-8") as f:
        json.dump(saved_meta, f, indent=2)

    # Set as active channel
    set_active_channel(channel_id)

    # Also sync root token.json for backward compatibility
    root_token = get_youtube_token_path()
    try:
        with open(root_token, "w", encoding="utf-8") as f:
            f.write(creds.to_json())
    except Exception:
        pass

    logger.info(f"[YouTube Auth] Saved channel '{channel_title}' ({channel_id}) to {target_token_file}")
    return meta_info


def remove_channel(channel_id: str) -> bool:
    """Removes a channel token and its cached metadata."""
    t_dir = ensure_tokens_dir()
    token_file = os.path.join(t_dir, f"{channel_id}.json")
    meta_file = os.path.join(t_dir, f"{channel_id}.meta.json")

    removed = False
    if os.path.exists(token_file):
        try:
            os.remove(token_file)
            removed = True
        except Exception as e:
            logger.error(f"Failed to remove token file {token_file}: {e}")

    if os.path.exists(meta_file):
        try:
            os.remove(meta_file)
        except Exception:
            pass

    # If the removed channel was active, switch to another channel
    active_id = get_active_channel_id()
    if active_id == channel_id:
        remaining = list_channels()
        if remaining:
            set_active_channel(remaining[0]["channel_id"])
        else:
            set_active_channel("")

    return removed


def export_channel_credentials(channel_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Exports credentials dict for the specified or active channel."""
    t_dir = ensure_tokens_dir()
    cid = channel_id or get_active_channel_id()
    if not cid:
        legacy_path = get_youtube_token_path()
        if os.path.exists(legacy_path):
            with open(legacy_path, "r", encoding="utf-8") as f:
                return json.load(f)
        return None

    path = os.path.join(t_dir, f"{cid}.json")
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return None


def check_auth_status(channel_id: Optional[str] = None) -> Dict[str, Any]:
    """
    Checks the status of YouTube OAuth authentication:
    - Verifies whether client_secrets.json exists.
    - Inspects connected channels in tokens/ and determines active channel.
    - Returns active channel info and list of all channels.
    """
    client_secrets_path = get_youtube_client_secrets_path()
    secrets_exist = os.path.exists(client_secrets_path)

    channels = list_channels()
    active_cid = channel_id or get_active_channel_id()

    active_channel = None
    if active_cid:
        for c in channels:
            if c.get("channel_id") == active_cid:
                active_channel = c
                break

    if not active_channel and channels:
        active_channel = channels[0]

    token_exist = bool(active_channel and active_channel.get("authenticated"))

    if not secrets_exist and not token_exist:
        return {
            "authenticated": False,
            "client_secrets_found": False,
            "token_found": False,
            "client_secrets_path": client_secrets_path,
            "channels": [],
            "message": "client_secrets.json not found. Add OAuth Client ID in project root or Render Secret Files."
        }

    if active_channel and active_channel.get("authenticated"):
        return {
            "authenticated": True,
            "client_secrets_found": secrets_exist,
            "token_found": True,
            "channel_title": active_channel.get("channel_title", "Connected Channel"),
            "channel_id": active_channel.get("channel_id", ""),
            "thumbnail_url": active_channel.get("thumbnail_url", ""),
            "active_channel_id": active_channel.get("channel_id", ""),
            "channels": channels
        }

    if secrets_exist:
        return {
            "authenticated": False,
            "client_secrets_found": True,
            "token_found": len(channels) > 0,
            "client_secrets_path": client_secrets_path,
            "channels": channels,
            "message": "Client secrets found. Click '+ Add Channel' to link your YouTube channel or import token."
        }

    return {
        "authenticated": False,
        "client_secrets_found": False,
        "token_found": False,
        "client_secrets_path": client_secrets_path,
        "channels": [],
        "message": "YouTube not linked. Connect your channel or import token."
    }


def get_authenticated_service(channel_id: Optional[str] = None):
    """
    Loads valid credentials for specified (or active) channel,
    or executes the local server OAuth flow if running locally with browser.
    """
    client_secrets_path = get_youtube_client_secrets_path()
    t_dir = ensure_tokens_dir()

    cid = channel_id or get_active_channel_id()
    token_path = os.path.join(t_dir, f"{cid}.json") if cid else get_youtube_token_path()

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
            try:
                creds = flow.run_local_server(port=0)
            except Exception as err:
                err_msg = str(err)
                if "runnable browser" in err_msg.lower() or "headless" in err_msg.lower():
                    raise RuntimeError(
                        "Headless environment detected (no desktop browser on host). "
                        "Please use 'Import Token' in the app to paste or upload your token credentials JSON."
                    )
                raise err

            # Save the new channel credentials
            saved_info = save_channel_credentials(json.loads(creds.to_json()))
    return build("youtube", "v3", credentials=creds)


def authorize_new_channel() -> Dict[str, Any]:
    """
    Forces a fresh OAuth flow with Google Account picker ('select_account consent')
    so the user can connect a different YouTube channel or account.
    """
    client_secrets_path = get_youtube_client_secrets_path()
    if not os.path.exists(client_secrets_path):
        raise FileNotFoundError(
            f"YouTube client secrets file not found at: {client_secrets_path}. "
            "Please place client_secrets.json in project root or Render Secret Files."
        )

    flow = InstalledAppFlow.from_client_secrets_file(client_secrets_path, SCOPES)
    try:
        # prompt='select_account consent' forces Google to show the account picker so user can pick ANY account/channel!
        creds = flow.run_local_server(port=0, prompt="select_account consent")
    except Exception as err:
        err_msg = str(err)
        if "runnable browser" in err_msg.lower() or "headless" in err_msg.lower():
            raise RuntimeError(
                "Headless environment detected (no desktop browser on host). "
                "Please use 'Upload token.json' or 'Paste JSON' in the app to link credentials."
            )
        raise err

    return save_channel_credentials(json.loads(creds.to_json()))


def create_web_flow(redirect_uri: str) -> Flow:
    """Creates a standard OAuth2 Web Application Flow for browser redirect OAuth."""
    client_secrets_path = get_youtube_client_secrets_path()
    if not os.path.exists(client_secrets_path):
        raise FileNotFoundError(
            f"YouTube client secrets file not found at: {client_secrets_path}. "
            "Please upload client_secrets.json in project root or Render Secret Files."
        )

    flow = Flow.from_client_secrets_file(
        client_secrets_path,
        scopes=SCOPES,
        redirect_uri=redirect_uri
    )
    # Web Application flow uses client_secret; disable PKCE autogeneration
    # so authorization doesn't require stateful code_verifier across separate HTTP requests.
    flow.autogenerate_code_verifier = False
    return flow




def upload_video_to_youtube(
    video_path: str,
    title: str,
    description: str = "",
    tags: Optional[List[str]] = None,
    privacy_status: str = "unlisted",
    category_id: str = "27",
    made_for_kids: bool = False,
    synthetic_content: bool = True,
    channel_id: Optional[str] = None,
    thumbnail_path: Optional[str] = None,
    progress_callback: Optional[Callable[[str, int], None]] = None
) -> Dict[str, Any]:
    """
    Uploads a video to YouTube using resumable chunked upload.
    - Supports multi-channel target via optional channel_id.
    - Adds #Shorts tag to title/tags if not present to ensure YouTube indexes it as a Short.
    - Adds synthetic content disclosure for YPP policy compliance.
    - Privacy status supports 'public', 'unlisted', or 'private'.
    - Returns Dict with video_id, youtube_url, channel_title, channel_id, and status.
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

        effective_cid = channel_id or get_active_channel_id()
        youtube = get_authenticated_service(channel_id=effective_cid)

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
                mapped_pct = 75 + int(pct * 0.20)
                progress_callback(f"Uploading to YouTube... {pct}%", mapped_pct)

        video_id = response.get("id")
        if not video_id:
            return {"success": False, "error": f"Upload succeeded but no video ID returned: {response}"}

        # Upload Eye-Catching Viral Thumbnail if provided
        if thumbnail_path and os.path.exists(thumbnail_path):
            try:
                if progress_callback:
                    progress_callback("Uploading eye-catching viral thumbnail to YouTube...", 95)
                thumb_media = MediaFileUpload(thumbnail_path, mimetype="image/jpeg")
                youtube.thumbnails().set(
                    videoId=video_id,
                    media_body=thumb_media
                ).execute()
                logger.info(f"[YouTube Upload] Custom thumbnail successfully uploaded for video {video_id}!")
            except Exception as e:
                logger.warning(f"[YouTube Upload] Custom thumbnail upload notice (channel may require phone verification for API custom thumbnails): {e}")

        actual_privacy = response.get("status", {}).get("privacyStatus", norm_privacy)
        logger.info(f"[YouTube Upload] Upload completed! Video ID: {video_id}, Channel: {effective_cid}, Requested: '{norm_privacy}', Assigned: '{actual_privacy}'")

        youtube_url = f"https://www.youtube.com/shorts/{video_id}"
        watch_url = f"https://www.youtube.com/watch?v={video_id}"

        if progress_callback:
            progress_callback(f"Upload complete! Published as {actual_privacy.title()}.", 100)

        # Retrieve channel title for banner display
        ch_title = "YouTube Channel"
        for ch in list_channels():
            if ch.get("channel_id") == effective_cid:
                ch_title = ch.get("channel_title", ch_title)
                break

        return {
            "success": True,
            "video_id": video_id,
            "youtube_url": youtube_url,
            "watch_url": watch_url,
            "title": clean_title,
            "privacy_status": norm_privacy,
            "actual_privacy_status": actual_privacy,
            "channel_id": effective_cid,
            "channel_title": ch_title,
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
