import logging
import urllib.parse
from typing import Dict, Any, Optional, Tuple, List
import httpx
from fastapi import HTTPException

from backend.app.config import get_settings
from backend.app.auth.facebook_oauth import (
    FacebookOAuthService,
    GRAPH_API_VERSION,
    FACEBOOK_AUTH_BASE,
)

logger = logging.getLogger("InstagramOAuth")

DEFAULT_INSTAGRAM_SCOPES = [
    "instagram_basic",
    "instagram_content_publish",
    "pages_show_list",
    "pages_read_engagement",
    "public_profile",
]


class InstagramOAuthService:
    """Manages Instagram Business Discovery, Media Container workflow, and Publishing via Graph API v21.0."""

    @classmethod
    def build_authorization_url(
        cls,
        state: str,
        redirect_uri: Optional[str] = None,
        scopes: Optional[List[str]] = None,
    ) -> str:
        """Constructs the Meta consent URL with Instagram Business permissions."""
        settings = get_settings()
        app_id, _ = FacebookOAuthService.get_client_credentials()
        r_uri = redirect_uri or settings.INSTAGRAM_REDIRECT_URI
        scope_str = ",".join(scopes or DEFAULT_INSTAGRAM_SCOPES)

        params = {
            "client_id": app_id or "placeholder_meta_app_id",
            "redirect_uri": r_uri,
            "state": state,
            "scope": scope_str,
            "response_type": "code",
        }
        return f"{FACEBOOK_AUTH_BASE}?{urllib.parse.urlencode(params)}"

    @classmethod
    def fetch_linked_instagram_account(
        cls,
        page_id: str,
        page_access_token: str,
    ) -> Optional[Dict[str, Any]]:
        """Queries the Facebook Page to discover its linked Instagram Business Account."""
        url = f"https://graph.facebook.com/{GRAPH_API_VERSION}/{page_id}"
        params = {
            "fields": "instagram_business_account{id,username,name,profile_picture_url}",
            "access_token": page_access_token,
        }

        try:
            with httpx.Client(timeout=15.0) as client:
                resp = client.get(url, params=params)
                if resp.status_code != 200:
                    logger.error("Failed to query linked Instagram account (%s): %s", resp.status_code, resp.text)
                    return None
                data = resp.json()
                ig_acc = data.get("instagram_business_account")
                if not ig_acc or not ig_acc.get("id"):
                    logger.warning("Facebook Page %s has no linked Instagram Business Account.", page_id)
                    return None
                return {
                    "id": str(ig_acc.get("id")),
                    "username": ig_acc.get("username", "instagram_business"),
                    "name": ig_acc.get("name", "Instagram Business Account"),
                    "profile_picture_url": ig_acc.get("profile_picture_url", ""),
                }
        except Exception as exc:
            logger.exception("Error querying linked Instagram account: %s", exc)
            return None

    @staticmethod
    def validate_media_url(media_url: Optional[str]) -> Tuple[bool, Optional[str]]:
        """Validates that a supported, publicly accessible image/video URL is present.
        
        Instagram Graph API strictly prohibits text-only feed posts.
        """
        if not media_url or not str(media_url).strip():
            return False, "Instagram publication rejected: Instagram strictly requires a publicly accessible image or video URL. Text-only posts cannot be published to Instagram."
        
        url_clean = str(media_url).strip()
        if not (url_clean.startswith("http://") or url_clean.startswith("https://")):
            return False, f"Instagram publication rejected: Invalid media URL scheme for '{media_url}'. URL must start with http:// or https://."
        
        return True, None

    @classmethod
    def create_media_container(
        cls,
        ig_user_id: str,
        image_url: str,
        caption: Optional[str],
        page_access_token: str,
    ) -> str:
        """Step 1 of Instagram publishing: Creates an asynchronous Media Container."""
        url = f"https://graph.facebook.com/{GRAPH_API_VERSION}/{ig_user_id}/media"
        data = {
            "image_url": image_url,
            "access_token": page_access_token,
        }
        if caption and caption.strip():
            data["caption"] = caption.strip()

        try:
            with httpx.Client(timeout=20.0) as client:
                resp = client.post(url, data=data)
                if resp.status_code not in (200, 201):
                    logger.error("Failed to create Instagram media container (%s): %s", resp.status_code, resp.text)
                    raise HTTPException(
                        status_code=400,
                        detail=f"Meta Graph API error creating Instagram container: {resp.text}"
                    )
                creation_id = resp.json().get("id")
                if not creation_id:
                    raise HTTPException(
                        status_code=502,
                        detail="Meta Graph API returned response without creation_id."
                    )
                return str(creation_id)
        except httpx.RequestError as exc:
            logger.exception("HTTP error during Instagram container creation: %s", exc)
            raise HTTPException(status_code=502, detail="Network error communicating with Meta Graph API.")

    @classmethod
    def check_container_status(
        cls,
        creation_id: str,
        page_access_token: str,
    ) -> Dict[str, Any]:
        """Step 2: Checks processing status of the created media container."""
        url = f"https://graph.facebook.com/{GRAPH_API_VERSION}/{creation_id}"
        params = {
            "fields": "status_code,status",
            "access_token": page_access_token,
        }

        try:
            with httpx.Client(timeout=10.0) as client:
                resp = client.get(url, params=params)
                if resp.status_code != 200:
                    logger.warning("Failed to check container status (%s): %s", resp.status_code, resp.text)
                    return {"status_code": "FINISHED"}  # Default to proceed if endpoint unqueried
                return resp.json()
        except Exception as exc:
            logger.warning("Exception checking container status: %s", exc)
            return {"status_code": "FINISHED"}

    @classmethod
    def publish_media_container(
        cls,
        ig_user_id: str,
        creation_id: str,
        page_access_token: str,
    ) -> str:
        """Step 3: Publishes the finished Media Container to the Instagram profile."""
        url = f"https://graph.facebook.com/{GRAPH_API_VERSION}/{ig_user_id}/media_publish"
        data = {
            "creation_id": creation_id,
            "access_token": page_access_token,
        }

        try:
            with httpx.Client(timeout=20.0) as client:
                resp = client.post(url, data=data)
                if resp.status_code not in (200, 201):
                    logger.error("Failed to publish Instagram media container (%s): %s", resp.status_code, resp.text)
                    raise HTTPException(
                        status_code=400,
                        detail=f"Meta Graph API error publishing Instagram container: {resp.text}"
                    )
                media_id = resp.json().get("id")
                if not media_id:
                    raise HTTPException(
                        status_code=502,
                        detail="Meta Graph API returned response without media_id."
                    )
                return str(media_id)
        except httpx.RequestError as exc:
            logger.exception("HTTP error publishing Instagram container: %s", exc)
            raise HTTPException(status_code=502, detail="Network error communicating with Meta Graph API.")
