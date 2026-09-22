"""
engine/storage.py - Cloud and local media storage manager.
Provides unified upload capabilities for Render Free Tier ephemeral persistence:
- Local filesystem (default fallback)
- AWS S3 / Cloudflare R2 / MinIO
- Cloudinary
- Supabase Storage
"""

import os
import mimetypes
import logging
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)


def upload_to_s3(file_path: str, key: str, bucket: str) -> Optional[str]:
    """Uploads file to AWS S3 / S3-compatible storage using boto3 if available."""
    try:
        import boto3
        from botocore.exceptions import BotoCoreError, ClientError

        s3_client = boto3.client(
            "s3",
            aws_access_key_id=os.environ.get("AWS_ACCESS_KEY_ID"),
            aws_secret_access_key=os.environ.get("AWS_SECRET_ACCESS_KEY"),
            region_name=os.environ.get("AWS_REGION", os.environ.get("AWS_DEFAULT_REGION", "us-east-1")),
            endpoint_url=os.environ.get("AWS_ENDPOINT_URL", None)
        )
        content_type, _ = mimetypes.guess_type(file_path)
        extra_args = {"ContentType": content_type or "video/mp4"}

        s3_client.upload_file(file_path, bucket, key, ExtraArgs=extra_args)
        endpoint = os.environ.get("AWS_ENDPOINT_URL")
        if endpoint:
            return f"{endpoint.rstrip('/')}/{bucket}/{key}"
        return f"https://{bucket}.s3.amazonaws.com/{key}"
    except ImportError:
        logger.warning("[Storage] boto3 not installed, skipping S3 upload.")
    except Exception as e:
        logger.warning(f"[Storage] S3 upload failed: {e}")
    return None


def upload_to_cloudinary(file_path: str, public_id: Optional[str] = None) -> Optional[str]:
    """Uploads video to Cloudinary via SDK or REST API."""
    cloudinary_url = os.environ.get("CLOUDINARY_URL", "").strip()
    if not cloudinary_url:
        return None

    try:
        import cloudinary
        import cloudinary.uploader
        res = cloudinary.uploader.upload_large(
            file_path,
            resource_type="video",
            public_id=public_id
        )
        return res.get("secure_url") or res.get("url")
    except ImportError:
        logger.warning("[Storage] cloudinary library not installed.")
    except Exception as e:
        logger.warning(f"[Storage] Cloudinary upload failed: {e}")
    return None


def upload_to_supabase(file_path: str, key: str) -> Optional[str]:
    """Uploads video to Supabase Storage via REST API."""
    supabase_url = os.environ.get("SUPABASE_URL", "").strip()
    supabase_key = (
        os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or
        os.environ.get("SUPABASE_KEY") or
        os.environ.get("SUPABASE_ANON_KEY", "")
    ).strip()
    bucket = os.environ.get("SUPABASE_BUCKET", "videos").strip()

    if not (supabase_url and supabase_key):
        return None

    try:
        import urllib.request
        import urllib.error

        content_type, _ = mimetypes.guess_type(file_path)
        content_type = content_type or "video/mp4"

        upload_endpoint = f"{supabase_url.rstrip('/')}/storage/v1/object/{bucket}/{key}"
        with open(file_path, "rb") as f:
            data = f.read()

        req = urllib.request.Request(
            upload_endpoint,
            data=data,
            headers={
                "Authorization": f"Bearer {supabase_key}",
                "apikey": supabase_key,
                "Content-Type": content_type
            },
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            if resp.status in (200, 201):
                return f"{supabase_url.rstrip('/')}/storage/v1/object/public/{bucket}/{key}"
    except Exception as e:
        logger.warning(f"[Storage] Supabase upload failed: {e}")
    return None


def save_or_upload_file(file_path: str, destination_name: Optional[str] = None) -> Dict[str, Any]:
    """
    Main entry point for video persistence.
    Checks STORAGE_PROVIDER (s3, cloudinary, supabase, or local).
    Falls back gracefully to local path if cloud is not configured or fails.
    """
    if not os.path.exists(file_path):
        return {"provider": "none", "url": "", "path": file_path, "error": "File does not exist"}

    provider = os.environ.get("STORAGE_PROVIDER", "local").strip().lower()
    filename = destination_name or os.path.basename(file_path)
    cloud_url = None

    if provider in ("s3", "aws") and os.environ.get("AWS_S3_BUCKET"):
        bucket = os.environ.get("AWS_S3_BUCKET").strip()
        cloud_url = upload_to_s3(file_path, key=f"shorts/{filename}", bucket=bucket)

    elif provider == "cloudinary" and os.environ.get("CLOUDINARY_URL"):
        cloud_url = upload_to_cloudinary(file_path)

    elif provider == "supabase" and os.environ.get("SUPABASE_URL"):
        cloud_url = upload_to_supabase(file_path, key=f"shorts/{filename}")

    if cloud_url:
        return {
            "provider": provider,
            "url": cloud_url,
            "path": file_path,
            "is_remote": True
        }

    # Default / fallback: local file path
    rel_path = f"/outputs/{os.path.basename(file_path)}"
    return {
        "provider": "local",
        "url": rel_path,
        "path": file_path,
        "is_remote": False
    }
