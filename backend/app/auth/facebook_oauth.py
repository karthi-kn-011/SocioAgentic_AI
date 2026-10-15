import logging
import urllib.parse
from typing import Dict, Any, Optional, Tuple, List
import httpx
from fastapi import HTTPException

from backend.app.config import get_settings

logger = logging.getLogger("FacebookOAuth")

GRAPH_API_VERSION = "v21.0"
FACEBOOK_AUTH_BASE = f"https://www.facebook.com/{GRAPH_API_VERSION}/dialog/oauth"
FACEBOOK_TOKEN_URL = f"https://graph.facebook.com/{GRAPH_API_VERSION}/oauth/access_token"
FACEBOOK_ACCOUNTS_URL = f"https://graph.facebook.com/{GRAPH_API_VERSION}/me/accounts"

DEFAULT_SCOPES = [
    "pages_show_list",
    "pages_read_engagement",
    "pages_manage_posts",
    "public_profile",
]


class FacebookOAuthService:
    """Manages Meta Graph API v21.0 OAuth, Page Access Tokens, and feed publishing helpers."""

    @classmethod
    def get_client_credentials(cls) -> Tuple[str, Optional[str]]:
        """Retrieves configured Meta App ID and App Secret."""
        settings = get_settings()
        app_id = settings.META_APP_ID or ""
        app_secret = settings.META_APP_SECRET
        return app_id, app_secret

    @classmethod
    def build_authorization_url(
        cls,
        state: str,
        redirect_uri: Optional[str] = None,
        scopes: Optional[List[str]] = None,
    ) -> str:
        """Constructs the Meta Facebook Login consent URL."""
        settings = get_settings()
        app_id, _ = cls.get_client_credentials()
        r_uri = redirect_uri or settings.META_REDIRECT_URI
        scope_str = ",".join(scopes or DEFAULT_SCOPES)

        params = {
            "client_id": app_id or "placeholder_meta_app_id",
            "redirect_uri": r_uri,
            "state": state,
            "scope": scope_str,
            "response_type": "code",
        }
        return f"{FACEBOOK_AUTH_BASE}?{urllib.parse.urlencode(params)}"

    @classmethod
    def exchange_code_for_user_token(
        cls,
        code: str,
        redirect_uri: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Exchanges authorization code for a short-lived user access token."""
        settings = get_settings()
        app_id, app_secret = cls.get_client_credentials()
        r_uri = redirect_uri or settings.META_REDIRECT_URI

        params = {
            "client_id": app_id,
            "client_secret": app_secret or "",
            "redirect_uri": r_uri,
            "code": code,
        }

        try:
            with httpx.Client(timeout=15.0) as client:
                resp = client.get(FACEBOOK_TOKEN_URL, params=params)
                if resp.status_code != 200:
                    logger.error("Meta token exchange failed (%s): %s", resp.status_code, resp.text)
                    raise HTTPException(
                        status_code=400,
                        detail=f"Failed to exchange authorization code with Meta: {resp.text}"
                    )
                return resp.json()
        except httpx.RequestError as exc:
            logger.exception("HTTP error during Meta token exchange: %s", exc)
            raise HTTPException(status_code=502, detail="Network error communicating with Meta Graph API.")

    @classmethod
    def exchange_for_long_lived_user_token(
        cls,
        short_lived_token: str,
    ) -> Dict[str, Any]:
        """Exchanges a short-lived user access token for a 60-day long-lived user token."""
        app_id, app_secret = cls.get_client_credentials()
        params = {
            "grant_type": "fb_exchange_token",
            "client_id": app_id,
            "client_secret": app_secret or "",
            "fb_exchange_token": short_lived_token,
        }

        try:
            with httpx.Client(timeout=15.0) as client:
                resp = client.get(FACEBOOK_TOKEN_URL, params=params)
                if resp.status_code != 200:
                    logger.warning("Failed to obtain long-lived user token (%s): %s", resp.status_code, resp.text)
                    return {"access_token": short_lived_token, "expires_in": 7200}
                return resp.json()
        except Exception as exc:
            logger.warning("Exception obtaining long-lived token: %s. Using short-lived token.", exc)
            return {"access_token": short_lived_token, "expires_in": 7200}

    @classmethod
    def fetch_managed_pages(
        cls,
        user_access_token: str,
    ) -> List[Dict[str, Any]]:
        """Queries /me/accounts to retrieve Facebook Pages managed by the user with Page Access Tokens."""
        params = {
            "fields": "id,name,access_token,category,tasks",
            "access_token": user_access_token,
        }

        try:
            with httpx.Client(timeout=15.0) as client:
                resp = client.get(FACEBOOK_ACCOUNTS_URL, params=params)
                if resp.status_code != 200:
                    logger.error("Failed to fetch managed Facebook Pages (%s): %s", resp.status_code, resp.text)
                    raise HTTPException(
                        status_code=400,
                        detail="Failed to retrieve managed Facebook Pages from Meta."
                    )
                data = resp.json().get("data", [])
                pages = []
                for p in data:
                    pages.append({
                        "id": p.get("id"),
                        "name": p.get("name"),
                        "access_token": p.get("access_token"),
                        "category": p.get("category", ""),
                        "tasks": p.get("tasks", []),
                    })
                return pages
        except httpx.RequestError as exc:
            logger.exception("HTTP error fetching managed Facebook Pages: %s", exc)
            raise HTTPException(status_code=502, detail="Network error communicating with Meta Graph API.")

    @classmethod
    def format_page_feed_payload(cls, message: str) -> Dict[str, Any]:
        """Constructs a compliant Meta Graph API feed publication payload."""
        return {
            "message": message,
        }
