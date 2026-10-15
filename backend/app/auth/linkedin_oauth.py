import logging
import urllib.parse
from typing import Dict, Any, Optional, Tuple, List
import httpx
from fastapi import HTTPException

from backend.app.config import get_settings

logger = logging.getLogger("LinkedInOAuth")

LINKEDIN_AUTH_BASE = "https://www.linkedin.com/oauth/v2/authorization"
LINKEDIN_TOKEN_URL = "https://www.linkedin.com/oauth/v2/accessToken"
LINKEDIN_USERINFO_URL = "https://api.linkedin.com/v2/userinfo"
LINKEDIN_POSTS_URL = "https://api.linkedin.com/rest/posts"

# OpenID Connect + Member Posting scopes
DEFAULT_SCOPES = ["openid", "profile", "email", "w_member_social"]


class LinkedInOAuthService:
    """Manages LinkedIn OAuth 2.0 Authorization Code flow and profile retrieval."""

    @classmethod
    def get_client_credentials(cls) -> Tuple[str, Optional[str]]:
        """Retrieves configured LinkedIn Client ID and Secret."""
        settings = get_settings()
        client_id = settings.LINKEDIN_CLIENT_ID or ""
        client_secret = settings.LINKEDIN_CLIENT_SECRET
        return client_id, client_secret

    @classmethod
    def build_authorization_url(
        cls,
        state: str,
        redirect_uri: Optional[str] = None,
        scopes: Optional[List[str]] = None,
    ) -> str:
        """Constructs the LinkedIn OAuth 2.0 consent URL."""
        settings = get_settings()
        client_id, _ = cls.get_client_credentials()
        r_uri = redirect_uri or settings.LINKEDIN_REDIRECT_URI
        scope_str = " ".join(scopes or DEFAULT_SCOPES)

        params = {
            "response_type": "code",
            "client_id": client_id or "placeholder_linkedin_client_id",
            "redirect_uri": r_uri,
            "state": state,
            "scope": scope_str,
        }
        return f"{LINKEDIN_AUTH_BASE}?{urllib.parse.urlencode(params)}"

    @classmethod
    def exchange_code_for_token(
        cls,
        code: str,
        redirect_uri: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Exchanges authorization code for LinkedIn access token."""
        settings = get_settings()
        client_id, client_secret = cls.get_client_credentials()
        r_uri = redirect_uri or settings.LINKEDIN_REDIRECT_URI

        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
        }
        data = {
            "grant_type": "authorization_code",
            "code": code,
            "client_id": client_id,
            "client_secret": client_secret or "",
            "redirect_uri": r_uri,
        }

        try:
            with httpx.Client(timeout=15.0) as client:
                resp = client.post(LINKEDIN_TOKEN_URL, data=data, headers=headers)
                if resp.status_code != 200:
                    logger.error("LinkedIn token exchange failed (%s): %s", resp.status_code, resp.text)
                    raise HTTPException(
                        status_code=400,
                        detail=f"Failed to exchange authorization code with LinkedIn: {resp.text}"
                    )
                return resp.json()
        except httpx.RequestError as exc:
            logger.exception("HTTP error during LinkedIn token exchange: %s", exc)
            raise HTTPException(status_code=502, detail="Network error communicating with LinkedIn API.")

    @classmethod
    def fetch_user_profile(cls, access_token: str) -> Dict[str, Any]:
        """Fetches the authenticated user profile via OpenID Connect userinfo endpoint."""
        headers = {
            "Authorization": f"Bearer {access_token}",
        }
        try:
            with httpx.Client(timeout=10.0) as client:
                resp = client.get(LINKEDIN_USERINFO_URL, headers=headers)
                if resp.status_code != 200:
                    logger.error("Failed to fetch LinkedIn user profile (%s): %s", resp.status_code, resp.text)
                    raise HTTPException(
                        status_code=400,
                        detail="Failed to retrieve user profile from LinkedIn."
                    )
                payload = resp.json()
                sub = payload.get("sub", "")
                name = payload.get("name") or f"{payload.get('given_name', '')} {payload.get('family_name', '')}".strip()
                return {
                    "account_id": f"urn:li:person:{sub}" if sub and not sub.startswith("urn:") else (sub or "urn:li:person:unknown"),
                    "username": name or "LinkedIn Member",
                    "email": payload.get("email", ""),
                    "picture": payload.get("picture", ""),
                    "sub": sub,
                }
        except httpx.RequestError as exc:
            logger.exception("HTTP error fetching LinkedIn user profile: %s", exc)
            raise HTTPException(status_code=502, detail="Network error communicating with LinkedIn API.")

    @classmethod
    def format_post_payload(cls, author_urn: str, commentary: str) -> Dict[str, Any]:
        """Constructs a compliant LinkedIn Posts API payload."""
        return {
            "author": author_urn,
            "commentary": commentary,
            "visibility": "PUBLIC",
            "distribution": {
                "feedDistribution": "MAIN_FEED",
                "targetEntities": [],
                "thirdPartyDistributionChannels": []
            },
            "lifecycleState": "PUBLISHED",
            "isReshareDisabledByAuthor": False
        }
