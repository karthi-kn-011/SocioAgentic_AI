import base64
import logging
import urllib.parse
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, Optional, Tuple
import httpx
from fastapi import HTTPException

from backend.app.config import get_settings

logger = logging.getLogger("TwitterOAuth")

TWITTER_AUTH_BASE = "https://twitter.com/i/oauth2/authorize"
TWITTER_TOKEN_URL = "https://api.twitter.com/2/oauth2/token"
TWITTER_REVOKE_URL = "https://api.twitter.com/2/oauth2/revoke"
TWITTER_USER_URL = "https://api.twitter.com/2/users/me"

DEFAULT_SCOPES = ["tweet.read", "tweet.write", "users.read", "offline.access"]


class TwitterOAuthService:
    """Manages X (Twitter) OAuth 2.0 Authorization Code with PKCE."""

    @classmethod
    def get_client_credentials(cls) -> Tuple[str, Optional[str]]:
        """Retrieves configured Client ID and Secret."""
        settings = get_settings()
        client_id = settings.X_CLIENT_ID or ""
        client_secret = settings.X_CLIENT_SECRET
        return client_id, client_secret

    @classmethod
    def build_authorization_url(
        cls,
        state: str,
        code_challenge: str,
        redirect_uri: Optional[str] = None,
        scopes: Optional[list] = None,
    ) -> str:
        """Constructs the X (Twitter) OAuth 2.0 PKCE consent URL."""
        settings = get_settings()
        client_id, _ = cls.get_client_credentials()
        r_uri = redirect_uri or settings.X_REDIRECT_URI
        scope_str = " ".join(scopes or DEFAULT_SCOPES)

        params = {
            "response_type": "code",
            "client_id": client_id or "placeholder_client_id",
            "redirect_uri": r_uri,
            "scope": scope_str,
            "state": state,
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
        }
        return f"{TWITTER_AUTH_BASE}?{urllib.parse.urlencode(params)}"

    @classmethod
    def exchange_code_for_token(
        cls,
        code: str,
        code_verifier: str,
        redirect_uri: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Exchanges authorization code and PKCE verifier for OAuth 2.0 tokens."""
        settings = get_settings()
        client_id, client_secret = cls.get_client_credentials()
        r_uri = redirect_uri or settings.X_REDIRECT_URI

        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
        }
        if client_id and client_secret:
            basic_auth = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()
            headers["Authorization"] = f"Basic {basic_auth}"

        data = {
            "code": code,
            "grant_type": "authorization_code",
            "client_id": client_id,
            "redirect_uri": r_uri,
            "code_verifier": code_verifier,
        }

        try:
            with httpx.Client(timeout=15.0) as client:
                resp = client.post(TWITTER_TOKEN_URL, data=data, headers=headers)
                if resp.status_code != 200:
                    logger.error("Twitter token exchange failed (%s): %s", resp.status_code, resp.text)
                    raise HTTPException(
                        status_code=400,
                        detail=f"Failed to exchange authorization code with Twitter: {resp.text}"
                    )
                return resp.json()
        except httpx.RequestError as exc:
            logger.exception("HTTP error during Twitter token exchange: %s", exc)
            raise HTTPException(status_code=502, detail="Network error communicating with Twitter API.")

    @classmethod
    def fetch_user_profile(cls, access_token: str) -> Dict[str, str]:
        """Fetches the authenticated user's ID and username (@handle)."""
        headers = {
            "Authorization": f"Bearer {access_token}",
        }
        try:
            with httpx.Client(timeout=10.0) as client:
                resp = client.get(TWITTER_USER_URL, headers=headers)
                if resp.status_code != 200:
                    logger.error("Failed to fetch Twitter user profile (%s): %s", resp.status_code, resp.text)
                    raise HTTPException(
                        status_code=400,
                        detail="Failed to retrieve user profile from Twitter."
                    )
                payload = resp.json()
                data = payload.get("data", {})
                return {
                    "account_id": data.get("id", ""),
                    "username": data.get("username", "twitter_user"),
                    "name": data.get("name", "X User"),
                }
        except httpx.RequestError as exc:
            logger.exception("HTTP error fetching Twitter user profile: %s", exc)
            raise HTTPException(status_code=502, detail="Network error communicating with Twitter API.")

    @classmethod
    def revoke_token(cls, token: str, token_type_hint: str = "access_token") -> bool:
        """Revokes an access or refresh token at Twitter's revocation endpoint."""
        client_id, client_secret = cls.get_client_credentials()
        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
        }
        if client_id and client_secret:
            basic_auth = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()
            headers["Authorization"] = f"Basic {basic_auth}"

        data = {
            "token": token,
            "token_type_hint": token_type_hint,
            "client_id": client_id,
        }

        try:
            with httpx.Client(timeout=10.0) as client:
                resp = client.post(TWITTER_REVOKE_URL, data=data, headers=headers)
                return resp.status_code == 200
        except Exception as exc:
            logger.warning("Twitter token revocation request encountered error: %s", exc)
            return False
